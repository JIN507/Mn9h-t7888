"""ImgBB provider — DEPRECATED public image hosting.

Kept only as the rollback path behind services/storage_service.host_image
(STORAGE_BACKEND=imgbb / automatic fallback on R2 errors). Once R2 is
verified in production, delete this module, the fallback branch, and the
IMGBB_API_KEY env var.
"""
import base64
import io
import logging
import os
import re
import tempfile

from .base import BaseProvider

logger = logging.getLogger(__name__)

UPLOAD_URL = 'https://api.imgbb.com/1/upload'


class ImgBBProvider(BaseProvider):
    name = 'imgbb'
    timeout = 30


_provider = ImgBBProvider()


def upload_to_imgbb(image_data, expiration=None):
    """Upload an image (bytes, file-like, or base64 str) — returns URL or None.
    `expiration` (seconds, 60..15552000) makes ImgBB delete it afterwards."""
    api_key = os.environ.get('IMGBB_API_KEY')
    if not api_key:
        logger.error('IMGBB_API_KEY not configured; upload skipped')
        return None
    form = {'key': api_key}
    if expiration:
        form['expiration'] = int(expiration)

    try:
        if isinstance(image_data, bytes) or hasattr(image_data, 'read'):
            response = _provider.request(
                'POST', UPLOAD_URL,
                data=form, files={'image': image_data})

        elif isinstance(image_data, str):
            # Clean data URL prefix if present
            if image_data.startswith('data:image'):
                image_data = re.sub(r'^data:image/[^;]+;base64,', '',
                                    image_data)
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(base64.b64decode(image_data)))
                fd, temp_path = tempfile.mkstemp(suffix='.png')
                os.close(fd)
                img.save(temp_path)
                try:
                    with open(temp_path, 'rb') as img_file:
                        response = _provider.request(
                            'POST', UPLOAD_URL,
                            data=form, files={'image': img_file})
                finally:
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
            except Exception as e:
                logger.warning('Image decode failed (%s); falling back to '
                               'raw string upload', e)
                response = _provider.request(
                    'POST', UPLOAD_URL,
                    data=form, files={'image': image_data})
        else:
            logger.error('Unsupported image data type: %s', type(image_data))
            return None

        try:
            json_data = response.json()
        except ValueError as e:
            logger.error('ImgBB returned non-JSON response: %s', e)
            return None

        if response.status_code == 200 and json_data.get('success'):
            return json_data['data']['url']

        error_message = json_data.get('error', {}).get('message',
                                                       'Unknown error')
        logger.error('ImgBB upload failed: %s', error_message)
        return None

    except Exception as e:
        logger.error('Error uploading to ImgBB: %s', e)
        return None
