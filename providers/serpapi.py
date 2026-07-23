"""SerpAPI provider — Google Lens is the engine of record for reverse search.

Hard rule: harvest ONLY visual-match sections (exact_matches/visual_matches).
Never organic_results or inline_images — they are not image matches.
"""
import logging
import os

import requests

from .base import BaseProvider, Candidate

logger = logging.getLogger(__name__)

SEARCH_URL = 'https://serpapi.com/search.json'


class SerpApiProvider(BaseProvider):
    name = 'serpapi'
    timeout = (8, 20)


_provider = SerpApiProvider()


def lens_matches(image_url, lens_type):
    """One Google Lens call (`type=exact_matches` or `visual_matches`).

    Returns normalized match dicts tagged by the response section they
    came from: exact_matches -> 'exact', visual_matches -> 'similar'.
    """
    params = {
        'engine': 'google_lens',
        'url': image_url,
        'type': lens_type,
        'api_key': os.environ.get('SERPAPI_API_KEY'),
        'hl': 'ar',
        'country': 'sa',
    }
    resp = _provider.request('GET', SEARCH_URL, params=params)
    logger.info('google_lens type=%s status=%s', lens_type, resp.status_code)
    if resp.status_code != 200:
        raise requests.RequestException(
            f'SerpAPI HTTP {resp.status_code}: {resp.text[:200]}')

    data = resp.json()
    matches = []
    for key, match_type in (('exact_matches', 'exact'),
                            ('visual_matches', 'similar')):
        val = data.get(key)
        if not isinstance(val, list):
            continue
        for item in val:
            if not isinstance(item, dict):
                continue
            link = item.get('link')
            if not link:
                continue
            matches.append(Candidate(
                link=link,
                title=item.get('title', ''),
                thumbnail=item.get('thumbnail') or item.get('image'),
                match_type=match_type,
                provider='google_lens',
            ).to_dict())
    return matches


# Legacy alias kept for the pinned test suite / transitional callers
_serpapi_lens_matches = lens_matches
