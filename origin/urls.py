"""URL identity for sightings: two links to the same post compare equal.
Strips tracking parameters, locale query strings, mobile hosts and
trailing slashes; folds twitter.com into x.com."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_DROP_PARAMS = ('utm_', 'fbclid', 'gclid', 'igsh', 'igshid', 'ref', 'ref_src', 'refsrc',
                'lang', 'hl', 'locale', 'src', 's', 't', 'feature', 'mibextid', '__cft__',
                '__tn__', 'rdid', 'share_url', 'sfnsn', 'is_from_webapp', 'sender_device',
                'web_id', 'q', 'srcom')
_HOST_FOLD = {'twitter.com': 'x.com', 'mobile.twitter.com': 'x.com', 'www.twitter.com': 'x.com',
              'www.x.com': 'x.com', 'm.facebook.com': 'www.facebook.com',
              'mbasic.facebook.com': 'www.facebook.com', 'web.facebook.com': 'www.facebook.com',
              'm.youtube.com': 'www.youtube.com', 'youtu.be': 'www.youtube.com'}


def canonical(url):
    """Canonical form or None when the input is not an http(s) URL."""
    if not url or not isinstance(url, str) or not url.lower().startswith(('http://', 'https://')):
        return None
    try:
        parts = urlsplit(url.strip())
    except Exception:
        return None
    host = (parts.hostname or '').lower()
    if not host:
        return None
    host = _HOST_FOLD.get(host, host)
    path = parts.path or '/'
    if host == 'www.youtube.com' and urlsplit(url).hostname == 'youtu.be':
        path, query = '/watch', urlencode({'v': path.strip('/')})
    else:
        keep = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
                if not k.lower().startswith(_DROP_PARAMS) and k.lower() not in _DROP_PARAMS]
        if host == 'www.youtube.com':
            keep = [(k, v) for k, v in keep if k == 'v']
        query = urlencode(sorted(keep))
    if len(path) > 1:
        path = path.rstrip('/')
    return urlunsplit(('https', host, path, query, ''))


def same(a, b):
    ca, cb = canonical(a), canonical(b)
    return bool(ca) and ca == cb
