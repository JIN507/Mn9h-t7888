"""Sightengine provider — genai image detection ("Model 1")."""
import logging
import os

from .base import BaseProvider, DetectionResult, ProviderNotConfigured

logger = logging.getLogger(__name__)

CHECK_URL = 'https://api.sightengine.com/1.0/check.json'


class SightengineProvider(BaseProvider):
    name = 'sightengine'
    timeout = 30


_provider = SightengineProvider()


def check_genai_file(image_path):
    """Run the genai model on a local image file.

    Returns (status_code, parsed_json). Raises ProviderNotConfigured when
    credentials are missing.
    """
    api_user = os.environ.get('SIGHTENGINE_API_USER')
    api_secret = os.environ.get('SIGHTENGINE_API_SECRET')
    if not api_user or not api_secret:
        raise ProviderNotConfigured(
            'SIGHTENGINE_API_USER / SIGHTENGINE_API_SECRET env vars not set')

    with open(image_path, 'rb') as media:
        resp = _provider.request(
            'POST', CHECK_URL,
            files={'media': media},
            data={'models': 'genai',
                  'api_user': api_user,
                  'api_secret': api_secret})
    return resp.status_code, resp.json()


def parse_genai(result) -> DetectionResult:
    """Normalize a successful check.json response."""
    ai_confidence = max(0.0, min(float(result['type']['ai_generated']), 1.0))
    human_confidence = max(0.0, min(1.0 - ai_confidence, 1.0))
    return DetectionResult(
        verdict='ai' if ai_confidence > 0.5 else 'human',
        ai_confidence=ai_confidence,
        human_confidence=human_confidence,
        generator='unknown',  # Sightengine doesn't report generators
        provider='sightengine',
        raw=result,
    )
