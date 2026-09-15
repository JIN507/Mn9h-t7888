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


def lens_matches(image_url, lens_type, hl='ar', country='sa'):
    """One Google Lens call (`type=exact_matches` or `visual_matches`).

    Returns normalized match dicts tagged by the response section they
    came from: exact_matches -> 'exact', visual_matches -> 'similar'.
    Locale defaults to ar/SA; the origin engine also fans out to en/US
    because Google's index differs per market.
    """
    params = {
        'engine': 'google_lens',
        'url': image_url,
        'type': lens_type,
        'api_key': os.environ.get('SERPAPI_API_KEY'),
        'hl': hl,
        'country': country,
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
            match = Candidate(
                link=link,
                title=item.get('title', ''),
                thumbnail=item.get('thumbnail') or item.get('image'),
                match_type=match_type,
                provider='google_lens',
            ).to_dict()
            if item.get('image'):
                match['image_url'] = item['image']
            matches.append(match)
    return matches


# Legacy alias kept for the pinned test suite / transitional callers
_serpapi_lens_matches = lens_matches
