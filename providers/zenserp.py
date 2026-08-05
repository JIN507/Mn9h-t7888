"""Zenserp provider — SERP text search + legacy reverse image search.

Hard rule for callers: never treat the `organic` sections of a reverse-image
response as image matches — only `similar_images` and
`pages_with_matching_images` are match sections.
"""
import logging
import os

from .base import BaseProvider

logger = logging.getLogger(__name__)

SEARCH_URL = 'https://app.zenserp.com/api/v2/search'


class ZenserpProvider(BaseProvider):
    name = 'zenserp'
    timeout = 60


_provider = ZenserpProvider()


def _headers():
    return {'apikey': os.environ.get('ZENSERP_API_KEY', '')}


def reverse_image_search(image_url, gl='us', hl='en'):
    """Reverse image search — returns the raw Response."""
    params = {'image_url': image_url, 'gl': gl, 'hl': hl}
    logger.info('zenserp reverse image search: %s', image_url)
    return _provider.request('GET', SEARCH_URL, headers=_headers(),
                             params=params, timeout=60)


def text_search(query, num=40, gl='sa', hl='ar'):
    """Text SERP search — returns the raw Response."""
    params = {'q': query, 'num': num, 'gl': gl, 'hl': hl}
    return _provider.request('GET', SEARCH_URL, headers=_headers(),
                             params=params, timeout=30)
