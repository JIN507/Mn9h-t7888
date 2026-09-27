"""TikTok oEmbed: the post's cover image, title and author without a key.
Photo posts and videos both answer; the thumbnail is what we can compare
against the query since the page itself is JavaScript-only."""
import logging
import threading

import requests

logger = logging.getLogger(__name__)

OEMBED_URL = 'https://www.tiktok.com/oembed'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/128.0 Safari/537.36'}
_cache = {}
_lock = threading.Lock()


def oembed(url, timeout=(5, 12)):
    """{'thumbnail_url','title','author_name','author_url'} or None. Cached."""
    if not url or 'tiktok.com' not in url:
        return None
    key = url.split('?')[0]
    with _lock:
        if key in _cache:
            return _cache[key]
    info = None
    try:
        r = requests.get(OEMBED_URL, params={'url': key}, headers=UA, timeout=timeout)
        if r.status_code == 200:
            d = r.json()
            if isinstance(d, dict) and (d.get('thumbnail_url') or d.get('title')):
                info = {k: d.get(k) for k in ('thumbnail_url', 'title', 'author_name', 'author_url')}
    except Exception as e:
        logger.info('tiktok oembed failed for %s: %s', key, e)
    with _lock:
        _cache[key] = info
    return info


def clear_cache():
    with _lock:
        _cache.clear()
