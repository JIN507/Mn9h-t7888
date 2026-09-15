"""Yandex reverse image search via SerpAPI (`engine=yandex_images`).

Yandex is the strongest engine for faces and for content Google
under-indexes (Russian/Arabic/Telegram ecosystems). Same SerpAPI key.
Only visual-match sections are harvested — never text/organic results.
"""
import logging
import os

import requests

from .base import BaseProvider, Candidate

logger = logging.getLogger(__name__)

SEARCH_URL = 'https://serpapi.com/search.json'


class YandexProvider(BaseProvider):
    name = 'yandex'
    timeout = (8, 25)


_provider = YandexProvider()


def _first_url(*values):
    for v in values:
        if isinstance(v, str) and v.startswith('http'):
            return v
        if isinstance(v, dict):
            for key in ('link', 'url', 'source'):
                if isinstance(v.get(key), str) and v[key].startswith('http'):
                    return v[key]
    return None


def reverse_image(image_url):
    """Yandex reverse search. Returns normalized match dicts.

    Harvested sections (all visual matches by construction):
      - `image_results`  -> 'similar' (visually similar images w/ source page)
      - `sites` / `pages_with_matching_images` -> 'page_match'
    """
    params = {
        'engine': 'yandex_images',
        'url': image_url,
        'api_key': os.environ.get('SERPAPI_API_KEY'),
    }
    resp = _provider.request('GET', SEARCH_URL, params=params)
    logger.info('yandex_images status=%s', resp.status_code)
    if resp.status_code != 200:
        raise requests.RequestException(
            f'SerpAPI(Yandex) HTTP {resp.status_code}: {resp.text[:200]}')

    data = resp.json()
    out = []
    for item in data.get('image_results') or []:
        if not isinstance(item, dict):
            continue
        link = _first_url(item.get('link'), item.get('source'),
                          item.get('original_image'))
        if not link:
            continue
        thumb = _first_url(item.get('thumbnail'), item.get('original_image'))
        out.append(Candidate(
            link=link, title=item.get('title', '') or '',
            thumbnail=thumb, match_type='similar',
            provider='yandex').to_dict())

    for key in ('sites', 'pages_with_matching_images'):
        for item in data.get(key) or []:
            if not isinstance(item, dict):
                continue
            link = _first_url(item.get('link'), item.get('url'))
            if not link:
                continue
            out.append(Candidate(
                link=link, title=item.get('title', '') or '',
                thumbnail=_first_url(item.get('thumbnail'), item.get('image')),
                match_type='page_match', provider='yandex').to_dict())

    logger.info('Yandex returned %d matches', len(out))
    return out
