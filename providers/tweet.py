"""X / Twitter post data without an API key.

x.com pages are JavaScript-only, so a plain fetch yields no image and no
text; the visual check then has to rely on an engine thumbnail. Twitter's
own syndication endpoint (the one embedded tweets use) returns the post's
photos, text and timestamp as JSON; FixTweet's public API is the fallback.
Photos come back at full resolution (`?name=orig`) — the closest thing to
the ORIGINAL file that exact-match indexes know.
"""
import logging
import math
import re
import string
import threading

import requests

logger = logging.getLogger(__name__)

SYNDICATION_URL = 'https://cdn.syndication.twimg.com/tweet-result'
FX_URL = 'https://api.fxtwitter.com/{user}/status/{tid}'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/128.0 Safari/537.36'}
_STATUS = re.compile(r'(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})/status(?:es)?/(\d{15,20})')
_cache = {}
_lock = threading.Lock()
_DIGITS = string.digits + string.ascii_lowercase


def status_id(url):
    """(user, id) for an X/Twitter post URL, else None."""
    m = _STATUS.search(url or '')
    return (m.group(1), m.group(2)) if m else None


def syndication_token(tid):
    """Twitter's embed token: ((id / 1e15) * pi) in base 36, zeros and the
    point removed — what the embed script computes client-side."""
    n = (int(tid) / 1e15) * math.pi
    ip, frac = int(n), n - int(n)
    s = ''
    while ip:
        s = _DIGITS[ip % 36] + s
        ip //= 36
    for _ in range(12):
        frac *= 36
        d = int(frac)
        s += _DIGITS[d]
        frac -= d
    return s.replace('0', '')


def _orig(url):
    if not url:
        return None
    base = url.split('?')[0]
    return base + '?name=orig'


def tweet_info(url, timeout=(5, 12)):
    """{'id','user','text','created_at','photos':[full-res urls]} or None.
    Cached per post for the process lifetime. Never raises."""
    ref = status_id(url)
    if not ref:
        return None
    user, tid = ref
    with _lock:
        if tid in _cache:
            return _cache[tid]
    info = None
    try:
        r = requests.get(SYNDICATION_URL, params={'id': tid, 'token': syndication_token(tid), 'lang': 'en'},
                         headers=UA, timeout=timeout)
        if r.status_code == 200 and r.headers.get('content-type', '').startswith('application/json'):
            d = r.json()
            if isinstance(d, dict) and (d.get('photos') or d.get('text')):
                info = {'id': tid, 'user': (d.get('user') or {}).get('screen_name') or user,
                        'text': d.get('text') or '', 'created_at': d.get('created_at'),
                        'photos': [_orig(p.get('url')) for p in d.get('photos') or [] if p.get('url')]}
    except Exception as e:
        logger.info('tweet syndication failed for %s: %s', tid, e)
    if info is None:
        try:
            r = requests.get(FX_URL.format(user=user, tid=tid), headers=UA, timeout=timeout)
            tw = (r.json().get('tweet') or {}) if r.status_code == 200 else {}
            if tw:
                info = {'id': tid, 'user': (tw.get('author') or {}).get('screen_name') or user,
                        'text': tw.get('text') or '', 'created_at': tw.get('created_at'),
                        'photos': [_orig(p.get('url')) for p in (tw.get('media') or {}).get('photos') or []
                                   if p.get('url')]}
        except Exception as e:
            logger.info('fxtwitter failed for %s: %s', tid, e)
    with _lock:
        _cache[tid] = info
    return info


def clear_cache():
    with _lock:
        _cache.clear()
