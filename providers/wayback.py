"""Internet Archive Wayback CDX — earliest capture of a URL (free, no key).

The first snapshot date is a hard upper bound on when a page (or an image
file) was published: the page existed at least by then. Used to
cross-check scraped dates and to date pages that expose no date at all.
"""
import logging
import threading
import time
from datetime import datetime

from .base import BaseProvider

logger = logging.getLogger(__name__)

CDX_URL = 'https://web.archive.org/cdx/search/cdx'


class WaybackProvider(BaseProvider):
    name = 'wayback'
    timeout = (4, 8)


_provider = WaybackProvider()
_cache = {}
_cache_lock = threading.Lock()
# The CDX API rate-limits aggressively: keep at most 2 in flight and back
# off for a while after a 503 instead of stalling every inspection worker.
_gate = threading.BoundedSemaphore(2)
_cooldown_until = 0.0
COOLDOWN_S = 90


def earliest_capture(url):
    """ISO-8601 UTC string of the first 2xx/3xx capture, or None."""
    global _cooldown_until
    if not url:
        return None
    with _cache_lock:
        if url in _cache:
            return _cache[url]
    if time.monotonic() < _cooldown_until:
        return None

    result = None
    try:
        with _gate:
            result = _lookup(url)
    except Exception as e:
        logger.info('wayback lookup failed for %s: %s', url, e)

    with _cache_lock:
        _cache[url] = result
    return result


def _lookup(url):
    global _cooldown_until
    params = {
        'url': url,
        'output': 'json',
        'fl': 'timestamp,statuscode',
        'filter': 'statuscode:[23]..',
        'limit': 1,
        'from': '1996',
    }
    resp = _provider.request('GET', CDX_URL, params=params)
    if resp.status_code == 200:
        rows = resp.json()
        if isinstance(rows, list) and len(rows) >= 2:
            ts = rows[1][0]
            return (datetime.strptime(ts, '%Y%m%d%H%M%S')
                    .strftime('%Y-%m-%dT%H:%M:%SZ'))
        return None
    if resp.status_code in (429, 503):
        _cooldown_until = time.monotonic() + COOLDOWN_S
        logger.warning('wayback rate-limited (%s); pausing lookups %ss',
                       resp.status_code, COOLDOWN_S)
    return None
