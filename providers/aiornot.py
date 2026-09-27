"""AIOrNot provider — image / voice / text / video AI detection.

NOTE: voice is still on the v1 endpoint; everything else is v2. Migrate voice
to v2 during Phase 4 (see CLAUDE.md landmines).
"""
import logging
import os
import uuid

from .base import BaseProvider, DetectionResult

logger = logging.getLogger(__name__)

IMAGE_SYNC_URL = 'https://api.aiornot.com/v2/image/sync'
TEXT_SYNC_URL = 'https://api.aiornot.com/v2/text/sync'
VIDEO_SYNC_URL = 'https://api.aiornot.com/v2/video/sync'
VOICE_REPORT_URL = 'https://api.aiornot.com/v1/reports/voice'


class AiorNotProvider(BaseProvider):
    name = 'aiornot'
    timeout = 60


_provider = AiorNotProvider()


def _auth_headers():
    return {'Authorization':
            f"Bearer {os.environ.get('AIORNOT_API_KEY', '')}"}


def post_image_file(image_path, timeout=None):
    """POST a local image to v2/image/sync — returns the raw Response."""
    with open(image_path, 'rb') as image_file:
        return _provider.request(
            'POST', IMAGE_SYNC_URL,
            headers=_auth_headers(),
            files={'image': image_file},
            params={'external_id': f'bahith-{uuid.uuid4().hex[:8]}'},
            timeout=timeout)


def post_voice_file(audio_path):
    """POST a local audio file to v1/reports/voice — returns the raw Response."""
    with open(audio_path, 'rb') as audio_file:
        return _provider.request(
            'POST', VOICE_REPORT_URL,
            headers=_auth_headers(),
            files={'file': audio_file},
            timeout=120)


def post_text(text, include_annotations=True):
    """POST text to v2/text/sync — returns the raw Response."""
    return _provider.request(
        'POST', TEXT_SYNC_URL,
        headers=_auth_headers(),
        # the endpoint accepts multipart/form-data only (a urlencoded or JSON body
        # is answered with "Invalid boundary"); the flag must be "true"/"false"
        files={'text': (None, text)},
        params={'include_annotations': 'true' if include_annotations else 'false'},
        timeout=60)


def post_video_file(video_path, filename):
    """POST a local video to v2/video/sync — returns the raw Response."""
    with open(video_path, 'rb') as f:
        return _provider.request(
            'POST', VIDEO_SYNC_URL,
            headers={**_auth_headers(), 'Accept': 'application/json'},
            data={'only': ['ai_video', 'ai_voice', 'ai_music',
                           'deepfake_video']},
            files=[('video', (filename, f, 'application/octet-stream'))],
            timeout=120)


def parse_image_report(result) -> DetectionResult:
    """Normalize a v2/image/sync response body."""
    report = result.get('report', {}).get('ai_generated', {})
    if not report:
        logger.warning('Unexpected AIOrNot response structure')
        return DetectionResult(verdict='unknown', ai_confidence=0.0,
                               human_confidence=1.0, provider='aiornot',
                               raw=result)

    verdict = report.get('verdict', '').lower()
    generators = report.get('generator', {})
    generator, max_confidence = 'unknown', 0
    for gen_name, confidence in generators.items():
        if isinstance(confidence, (int, float)) and confidence > max_confidence:
            max_confidence = confidence
            generator = gen_name
        elif isinstance(confidence, dict) and 'confidence' in confidence:
            conf_value = confidence.get('confidence', 0)
            if conf_value > max_confidence:
                max_confidence = conf_value
                generator = gen_name

    return DetectionResult(
        verdict='ai' if verdict == 'ai' else 'human',
        ai_confidence=report.get('ai', {}).get('confidence', 0.0),
        human_confidence=report.get('human', {}).get('confidence', 0.0),
        generator=generator,
        generator_confidence=max_confidence,
        provider='aiornot',
        raw=result,
    )
