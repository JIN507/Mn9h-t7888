"""Where uploaded media gets hosted so external APIs can fetch it.

Default: Cloudflare R2 — private bucket + 15-minute presigned GET URLs
(the privacy fix from plan §3.4). ImgBB remains as a rollback path until
cutover is confirmed:

  STORAGE_BACKEND=imgbb   -> force ImgBB (rollback switch)
  IMGBB_FALLBACK=false    -> fail instead of falling back when R2 errors

Once R2 is verified in production, delete providers/imgbb.py and the
fallback branch here.
"""
import logging
import os

logger = logging.getLogger(__name__)


def host_image(image_data, filename_hint='image'):
    """Host an image; returns a fetchable URL or None.

    Detection APIs accept direct file upload and must NOT use this —
    hosting is only for providers that require a URL (SerpAPI, Zenserp,
    Vision, xAI, manual engine links).
    """
    from providers import storage
    from providers.imgbb import upload_to_imgbb

    backend = os.environ.get('STORAGE_BACKEND', 'r2').lower()
    if backend != 'imgbb' and storage.is_configured():
        url = storage.upload_image(image_data, filename_hint)
        if url:
            return url
        if os.environ.get('IMGBB_FALLBACK', 'true').lower() == 'false':
            logger.error('R2 upload failed and IMGBB_FALLBACK is disabled')
            return None
        logger.warning('R2 upload failed — falling back to ImgBB')
    elif backend != 'imgbb':
        logger.info('R2 not configured — using ImgBB (set R2_* env vars '
                    'to enable private storage)')
    return upload_to_imgbb(image_data)
