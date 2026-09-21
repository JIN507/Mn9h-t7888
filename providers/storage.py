"""Cloudflare R2 (S3-compatible) — private media storage with presigned URLs.

Replaces public ImgBB hosting (plan §3.4): user uploads go to a PRIVATE
bucket and external APIs receive short-lived presigned GET URLs instead of
permanent public links.

Config (env): R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
R2_BUCKET. The endpoint is derived from the account id.
"""
import base64
import logging
import os
import re
import time
import uuid

from .base import _meter

logger = logging.getLogger(__name__)

PRESIGN_EXPIRES = 900  # 15 minutes — long enough for any provider fetch

_client = None

REQUIRED_ENV = ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID',
                'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')


def is_configured():
    return all(os.environ.get(k) for k in REQUIRED_ENV)


def _get_client():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config as BotoConfig
        _client = boto3.client(
            's3',
            endpoint_url=(f"https://{os.environ['R2_ACCOUNT_ID']}"
                          '.r2.cloudflarestorage.com'),
            aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
            aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
            region_name='auto',
            config=BotoConfig(signature_version='s3v4',
                              retries={'max_attempts': 2}),
        )
    return _client


def _sniff_content_type(data):
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png', '.png'
    if data[:2] == b'\xff\xd8':
        return 'image/jpeg', '.jpg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif', '.gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp', '.webp'
    return 'application/octet-stream', ''


def _decode_image_data(image_data):
    """bytes | file-like | base64 str | data URL -> raw bytes."""
    if hasattr(image_data, 'read'):
        image_data = image_data.read()
    if isinstance(image_data, str):
        if image_data.startswith('data:image'):
            image_data = re.sub(r'^data:image/[^;]+;base64,', '', image_data)
        image_data = base64.b64decode(image_data)
    return image_data


def upload_bytes(data, key, content_type='application/octet-stream'):
    """PUT an object into the private bucket. Returns the key or None."""
    started = time.monotonic()
    try:
        _get_client().put_object(
            Bucket=os.environ['R2_BUCKET'], Key=key,
            Body=data, ContentType=content_type)
        _meter('r2', 'PUT', key, 200, time.monotonic() - started)
        return key
    except Exception as e:
        _meter('r2', 'PUT', key, None, time.monotonic() - started, error=e)
        logger.error('R2 upload failed for %s: %s', key, e)
        return None


def public_base_url():
    """Where this app is reachable from the internet (production):
    PUBLIC_BASE_URL, else Render's RENDER_EXTERNAL_URL. Empty locally."""
    return (os.environ.get('PUBLIC_BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL') or '').rstrip('/')


def media_token(key):
    """Unguessable token for a public media path (HMAC of the object key)."""
    import hashlib
    import hmac
    secret = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    return hmac.new(secret.encode(), key.encode(), hashlib.sha256).hexdigest()[:32]


def public_media_url(key):
    """Plain public URL of a private object, served through /api/media by
    this app — what reverse-image engines (Yandex) can fetch. None when the
    app has no public base URL (local dev)."""
    base = public_base_url()
    if not base or not key:
        return None
    return f'{base}/api/media/{media_token(key)}/{key}'


def key_from_presigned_url(url):
    """'https://acct.r2.cloudflarestorage.com/<bucket>/uploads/x.jpg?...' -> 'uploads/x.jpg'"""
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        if 'r2.cloudflarestorage.com' not in p.netloc:
            return None
        parts = p.path.lstrip('/').split('/', 1)
        return parts[1] if len(parts) == 2 and parts[1] else None
    except Exception:
        return None


def presigned_get_url(key, expires=PRESIGN_EXPIRES):
    """Short-lived GET URL for a private object. Returns None on failure."""
    try:
        return _get_client().generate_presigned_url(
            'get_object',
            Params={'Bucket': os.environ['R2_BUCKET'], 'Key': key},
            ExpiresIn=expires)
    except Exception as e:
        logger.error('R2 presign failed for %s: %s', key, e)
        return None


def upload_image(image_data, filename_hint='image'):
    """Upload an image (bytes/file/base64/data-URL) and return a presigned
    GET URL valid for PRESIGN_EXPIRES seconds. None on failure."""
    try:
        data = _decode_image_data(image_data)
    except Exception as e:
        logger.error('Could not decode image data: %s', e)
        return None
    content_type, ext = _sniff_content_type(data)
    key = f'uploads/{uuid.uuid4().hex}{ext}'
    if upload_bytes(data, key, content_type) is None:
        return None
    return presigned_get_url(key)
