"""TinEye provider — the "first seen" specialist.

TinEye is the only commercial engine that orders matches by the date it
first crawled the image (`sort=crawl_date&order=asc`). Each backlink carries
its own crawl_date, which is an independent upper bound on when the image
was published on that page.
"""
import logging
import os

import requests

from .base import BaseProvider, Candidate

logger = logging.getLogger(__name__)

SEARCH_URL = 'https://api.tineye.com/rest/search/'


class TinEyeProvider(BaseProvider):
    name = 'tineye'
    timeout = (8, 30)


_provider = TinEyeProvider()


def configured():
    return bool(os.environ.get('TINEYE_API_KEY'))


def search_by_url(image_url, limit=50):
    """Reverse search ordered by TinEye crawl date (oldest first).

    Returns a list of normalized match dicts (Candidate + `crawl_date`,
    `image_url`, `score`). Empty list when the key is missing; raises
    requests.RequestException on HTTP failures.
    """
    if not configured():
        return []
    params = {
        'url': image_url,
        'sort': 'crawl_date',
        'order': 'asc',
        'limit': limit,
    }
    headers = {'x-api-key': os.environ.get('TINEYE_API_KEY', '')}
    resp = _provider.request('GET', SEARCH_URL, params=params, headers=headers)
    if resp.status_code != 200:
        raise requests.RequestException(
            f'TinEye HTTP {resp.status_code}: {resp.text[:200]}')

    data = resp.json()
    results = data.get('results') or data
    matches = results.get('matches') if isinstance(results, dict) else None
    out = []
    for match in matches or []:
        if not isinstance(match, dict):
            continue
        matched_image = match.get('image_url')
        for backlink in match.get('backlinks') or []:
            if not isinstance(backlink, dict):
                continue
            page = backlink.get('backlink') or backlink.get('url')
            if not page or not str(page).startswith('http'):
                continue
            item = Candidate(
                link=page,
                title='',
                thumbnail=backlink.get('url') or matched_image,
                match_type='exact',
                provider='tineye',
            ).to_dict()
            item['crawl_date'] = backlink.get('crawl_date')
            item['image_url'] = backlink.get('url') or matched_image
            item['score'] = match.get('score')
            out.append(item)
    logger.info('TinEye returned %d backlinks', len(out))
    return out
