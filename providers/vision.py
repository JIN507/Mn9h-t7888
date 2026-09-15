"""Google Cloud Vision provider — Web Detection as a reverse-search source.

Credentials come exclusively from GOOGLE_APPLICATION_CREDENTIALS (a file path;
the file itself is gitignored and must never be committed).
"""
import logging
import os

from .base import Candidate

logger = logging.getLogger(__name__)

try:
    from google.cloud import vision
    VISION_API_AVAILABLE = True
except ImportError:  # pragma: no cover
    vision = None
    VISION_API_AVAILABLE = False
    logger.warning('google-cloud-vision not installed; Vision provider disabled')

# Local dev convenience: pick up a credentials file next to the project root
if VISION_API_AVAILABLE and not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
    _local = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          'google-credentials.json')
    if os.path.exists(_local):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = _local
        logger.info('Google Cloud credentials set from local file')


def configured():
    return bool(VISION_API_AVAILABLE
                and os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))


def vision_web_detection(image_url):
    """Web Detection matches, normalized. Empty list on any failure.

    Buckets: full_matching_images -> 'exact', partial_matching_images ->
    'similar', pages_with_matching_images -> 'page_match'.
    """
    if not VISION_API_AVAILABLE:
        return []
    if not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        return []
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image()
        image.source.image_uri = image_url
        annotations = client.web_detection(image=image).web_detection

        matches = []
        for img in annotations.full_matching_images:
            if img.url:
                matches.append(Candidate(
                    link=img.url, thumbnail=img.url,
                    match_type='exact', provider='google_vision').to_dict())
        for img in annotations.partial_matching_images:
            if img.url:
                matches.append(Candidate(
                    link=img.url, thumbnail=img.url,
                    match_type='similar', provider='google_vision').to_dict())
        for page in annotations.pages_with_matching_images:
            if page.url:
                thumb = (page.full_matching_images[0].url
                         if page.full_matching_images else
                         (page.partial_matching_images[0].url
                          if page.partial_matching_images else None))
                matches.append(Candidate(
                    link=page.url, title=page.page_title or '',
                    thumbnail=thumb, match_type='page_match',
                    provider='google_vision').to_dict())
        logger.info('Vision Web Detection returned %d matches', len(matches))
        return matches
    except Exception as e:
        logger.warning('Vision Web Detection failed: %s', e)
        return []


# Clean alias for new callers
web_detection_matches = vision_web_detection
