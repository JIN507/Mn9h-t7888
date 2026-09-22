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
NO_RESULTS_MARK = "hasn't returned any results"


class SerpApiNoResults(requests.RequestException):
    """SerpAPI answered HTTP 200 with `{"error": "... hasn't returned any
    results for this query."}`. Live finding (2026-09-22): this is the SAME
    text Google returns for a URL it could not fetch (a 404 image, a host
    it refuses such as *.r2.dev / r2.cloudflarestorage.com). For
    `visual_matches` it practically always means "image not fetched";
    for `exact_matches` it may also be a genuine empty. Either way it is
    not a normal empty list, so callers can retry with another copy of the
    image and report it honestly."""


def _no_results(data):
    err = data.get('error') if isinstance(data, dict) else None
    return isinstance(err, str) and NO_RESULTS_MARK in err


class SerpApiProvider(BaseProvider):
    name = 'serpapi'
    timeout = (8, 20)


_provider = SerpApiProvider()


def reverse_image_pages(image_url, hl='en', country='us'):
    """Legacy Google "search by image" (`engine=google_reverse_image`).

    Harvests ONLY `image_results` — Google's "pages that include matching
    images" — a different index from Lens, worth a second net. Never
    `inline_images` / organic text results. Rows are 'page_match'
    candidates and go through the thumbnail pre-screen like everything else.
    """
    params = {
        'engine': 'google_reverse_image',
        'image_url': image_url,
        'api_key': os.environ.get('SERPAPI_API_KEY'),
        'hl': hl,
        'gl': country,
    }
    resp = _provider.request('GET', SEARCH_URL, params=params)
    logger.info('google_reverse_image status=%s', resp.status_code)
    if resp.status_code != 200:
        raise requests.RequestException(
            f'SerpAPI HTTP {resp.status_code}: {resp.text[:200]}')
    data = resp.json()
    if _no_results(data):
        raise SerpApiNoResults(f'google_reverse_image: {data.get("error")}')
    out = []
    for item in data.get('image_results') or []:
        if not isinstance(item, dict):
            continue
        link = item.get('link')
        if not link or not str(link).startswith('http'):
            continue
        match = Candidate(link=link, title=item.get('title', '') or '',
                          thumbnail=item.get('thumbnail'),
                          match_type='page_match',
                          provider='google_reverse_image').to_dict()
        if item.get('thumbnail'):
            match['image_url'] = item['thumbnail']
        out.append(match)
    logger.info('google_reverse_image returned %d matching pages', len(out))
    return out


def lens_matches(image_url, lens_type, hl='ar', country='sa', no_cache=False):
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
    if no_cache:
        params['no_cache'] = 'true'   # SerpAPI: bypass its cached (empty) answer
    resp = _provider.request('GET', SEARCH_URL, params=params)
    logger.info('google_lens type=%s status=%s', lens_type, resp.status_code)
    if resp.status_code != 200:
        raise requests.RequestException(
            f'SerpAPI HTTP {resp.status_code}: {resp.text[:200]}')

    data = resp.json()
    if _no_results(data):
        raise SerpApiNoResults(f'google_lens {lens_type}: {data.get("error")}')
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


def web_search(query, hl='en', gl='us', num=10):
    """Google TEXT search (`engine=google`) — the agent's web_search tool.
    Harvests `organic_results`, which is correct for a text query (hard
    rule #5 concerns image matches only). Returns [{link,title,snippet,date}]."""
    params = {
        'engine': 'google',
        'q': query,
        'api_key': os.environ.get('SERPAPI_API_KEY'),
        'hl': hl,
        'gl': gl,
        'num': num,
    }
    resp = _provider.request('GET', SEARCH_URL, params=params, timeout=(8, 30))
    if resp.status_code != 200:
        raise requests.RequestException(
            f'SerpAPI HTTP {resp.status_code}: {resp.text[:200]}')
    data = resp.json()
    out = []
    for item in data.get('organic_results') or []:
        if not isinstance(item, dict) or not item.get('link'):
            continue
        out.append({'link': item['link'], 'title': item.get('title') or '',
                    'snippet': item.get('snippet') or '', 'date': item.get('date')})
    logger.info('serpapi google text search returned %d results', len(out))
    return out


# Legacy alias kept for the pinned test suite / transitional callers
_serpapi_lens_matches = lens_matches
