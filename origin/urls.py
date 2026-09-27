"""URL identity and classification for sightings.

canonical(): two links to the same post compare equal (tracking and locale
parameters dropped, mobile hosts folded, twitter.com -> x.com).
Classification: junk (search engines, caches), social platforms, listing
pages (topic/tag/profile/pagination — never an origin), image files.
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_DROP_PARAMS = ('utm_', 'fbclid', 'gclid', 'igsh', 'igshid', 'ref', 'ref_src', 'refsrc',
                'lang', 'hl', 'locale', 'src', 's', 't', 'feature', 'mibextid', '__cft__',
                '__tn__', 'rdid', 'share_url', 'sfnsn', 'is_from_webapp', 'sender_device',
                'web_id', 'q', 'srcom')
_X_STATUS = re.compile(r'^/(?:[A-Za-z0-9_]{1,15}|i/web|i)/status(?:es)?/(\d{15,20})(?:/.*)?$')
_HOST_FOLD = {'twitter.com': 'x.com', 'mobile.twitter.com': 'x.com', 'www.twitter.com': 'x.com',
              'www.x.com': 'x.com', 'm.facebook.com': 'www.facebook.com',
              'mbasic.facebook.com': 'www.facebook.com', 'web.facebook.com': 'www.facebook.com',
              'm.youtube.com': 'www.youtube.com', 'youtu.be': 'www.youtube.com'}

JUNK_HOSTS = ('google.', 'lens.google', 'bing.com', 'yandex.', 'tineye.com',
              'duckduckgo.com', 'webcache.googleusercontent.com',
              'translate.goog', 'archive.org', 'archive.ph', 'serpapi.com')
SOCIAL_HOSTS = ('twitter.com', 'x.com', 'facebook.com', 'instagram.com',
                't.me', 'telegram.me', 'reddit.com', 'tiktok.com',
                'youtube.com', 'youtu.be', 'threads.net', 'threads.com', 'vk.com')
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif', '.bmp')
# Listing/index pages show whatever is newest: never an origin.
_LISTING_RE = re.compile(
    r'(^/$)|/(topic|topics|tag|tags|category|categories|author|authors|'
    r'search|archive|archives|latest|photos|gallery|galleries|videos|discover|explore|hashtag)(/|$)|'
    r'/page/\d+(/|$)|[?&](page|p)=\d+', re.IGNORECASE)
# Social profile roots (no post id) are listings too.
_PROFILE_RE = re.compile(
    r'^https://(x\.com|www\.instagram\.com|www\.tiktok\.com|www\.facebook\.com|www\.pinterest\.[a-z.]+|'
    r'[a-z]{2}\.pinterest\.com|www\.threads\.(net|com))/@?[A-Za-z0-9_.-]+/?$')


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
    if host == 'x.com':
        m = _X_STATUS.match(path)
        if m:
            path, query = f'/i/status/{m.group(1)}', ''
    return urlunsplit(('https', host, path, query, ''))


def same(a, b):
    ca, cb = canonical(a), canonical(b)
    return bool(ca) and ca == cb


def host_of(url):
    try:
        return (urlsplit(url).hostname or '').lower()
    except Exception:
        return ''


def domain_of(url):
    h = host_of(url)
    return h[4:] if h.startswith('www.') else h


def is_junk(url):
    h = host_of(url)
    return not h or any(j in h for j in JUNK_HOSTS)


def is_social(url):
    h = host_of(url)
    return any(h == s or h.endswith('.' + s) for s in SOCIAL_HOSTS)


def is_image_url(url):
    try:
        return urlsplit(url).path.lower().endswith(IMAGE_EXT)
    except Exception:
        return False


def is_listing(url):
    c = canonical(url)
    if not c:
        return False
    parts = urlsplit(c)
    path = parts.path or '/'
    if _LISTING_RE.search(path + ('?' + parts.query if parts.query else '')):
        return True
    return bool(_PROFILE_RE.match(c))


def platform_of(url):
    """x | instagram | facebook | tiktok | telegram | youtube | reddit | pinterest | threads | web"""
    h = host_of(url)
    for key, hosts in (('x', ('x.com', 'twitter.com')), ('instagram', ('instagram.com',)),
                       ('facebook', ('facebook.com',)), ('tiktok', ('tiktok.com',)),
                       ('telegram', ('t.me', 'telegram.me')), ('youtube', ('youtube.com', 'youtu.be')),
                       ('reddit', ('reddit.com',)), ('pinterest', ('pinterest.',)),
                       ('threads', ('threads.net', 'threads.com'))):
        if any(h == x or h.endswith('.' + x) or (x.endswith('.') and x in h) for x in hosts):
            return key
    return 'web'
