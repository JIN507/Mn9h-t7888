"""Publication-date evidence for a candidate page (origin engine Tier 3).

Every extractor returns evidence dicts: {'date': ISO-8601 UTC string,
'confidence': 0..1, 'source': 'meta:article:published_time' | ...}.
`resolve_published_at` combines page evidence with hard upper bounds
(Wayback first capture, TinEye crawl date) into one dated verdict:

  - platform IDs (X/Twitter snowflake) are exact and unforgeable  -> 0.98
  - article:published_time / JSON-LD datePublished                  -> 0.95/0.90
  - htmldate (original_date=True) — best general-purpose extractor -> 0.80
  - other meta/time selectors                                        -> 0.70-0.85
  - URL path /YYYY/MM/DD/                                            -> 0.65
  - visible text pattern                                             -> 0.45
  - bounds: a page cannot be newer than its first archive capture;
    if page evidence is LATER than a bound, the bound wins.
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

try:
    import dateparser
    DATEPARSER_AVAILABLE = True
except ImportError:  # pragma: no cover
    DATEPARSER_AVAILABLE = False

try:
    from htmldate import find_date as _htmldate_find
    HTMLDATE_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _htmldate_find = None
    HTMLDATE_AVAILABLE = False

TWITTER_EPOCH_MS = 1288834974657
_MIN_YEAR = 1995


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _plausible(dt):
    return (dt is not None and dt.year >= _MIN_YEAR
            and dt <= _now() + timedelta(days=1))


def to_iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_date(value):
    """Loose string -> naive UTC datetime, or None (never raises)."""
    if not value:
        return None
    text = str(value).strip()[:80]
    if not text:
        return None
    try:
        if re.match(r'^\d{4}-\d{2}-\d{2}', text):
            iso = text.replace('Z', '+00:00')
            try:
                dt = datetime.fromisoformat(iso[:32])
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt if _plausible(dt) else None
            except ValueError:
                pass
        if text.isdigit() and len(text) in (10, 13):
            ts = int(text) / (1000 if len(text) == 13 else 1)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
            return dt if _plausible(dt) else None
        if DATEPARSER_AVAILABLE:
            dt = dateparser.parse(text, languages=['en', 'ar', 'fr', 'ru'],
                                  settings={'RETURN_AS_TIMEZONE_AWARE': False,
                                            'PREFER_DAY_OF_MONTH': 'first'})
            if dt is not None and _plausible(dt):
                return dt
        for fmt in ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d',
                    '%d %B %Y', '%B %d, %Y', '%d %b %Y', '%b %d, %Y',
                    '%Y/%m/%d', '%d/%m/%Y', '%Y%m%d'):
            try:
                dt = datetime.strptime(text[:40], fmt)
                return dt if _plausible(dt) else None
            except ValueError:
                continue
    except Exception:
        return None
    return None


# ------------------------------------------------------------ extractors

def platform_date(url):
    """Exact timestamps encoded in platform IDs (no fetch needed)."""
    out = []
    host = urlparse(url).netloc.lower()
    m = re.search(r'/status(?:es)?/(\d{15,20})', url)
    if m and any(h in host for h in ('twitter.com', 'x.com', 'nitter')):
        try:
            ms = (int(m.group(1)) >> 22) + TWITTER_EPOCH_MS
            dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
            dt = dt.replace(tzinfo=None)
            if _plausible(dt):
                out.append({'date': to_iso(dt), 'confidence': 0.98,
                            'source': 'platform:twitter_snowflake'})
        except (ValueError, OverflowError, OSError):
            pass
    return out


def url_path_date(url):
    path = urlparse(url).path
    m = (re.search(r'/((?:19|20)\d{2})/(\d{1,2})/(\d{1,2})(?:/|$)', path)
         or re.search(r'/((?:19|20)\d{2})-(\d{2})-(\d{2})(?:[/-]|$)', path))
    if m:
        y, mo, d = m.groups()
        dt = parse_date(f'{y}-{int(mo):02d}-{int(d):02d}')
        if dt:
            return [{'date': to_iso(dt), 'confidence': 0.65,
                     'source': 'url:path_date'}]
    m = re.search(r'/((?:19|20)\d{2})/(\d{1,2})(?:/|$)', path)
    if m:
        y, mo = m.groups()
        dt = parse_date(f'{y}-{int(mo):02d}-01')
        if dt:
            return [{'date': to_iso(dt), 'confidence': 0.40,
                     'source': 'url:path_month'}]
    return []


_META_SELECTORS = [
    ('meta[property="article:published_time"]', 'meta:article:published_time', 0.95),
    ('meta[property="og:published_time"]', 'meta:og:published_time', 0.85),
    ('meta[property="article:published"]', 'meta:article:published', 0.85),
    ('meta[name="parsely-pub-date"]', 'meta:parsely-pub-date', 0.85),
    ('meta[name="pubdate"]', 'meta:pubdate', 0.80),
    ('meta[name="publishdate"]', 'meta:publishdate', 0.80),
    ('meta[name="publish-date"]', 'meta:publish-date', 0.80),
    ('meta[name="article.published"]', 'meta:article.published', 0.80),
    ('meta[itemprop="datePublished"]', 'meta:datePublished', 0.80),
    ('meta[name="dc.date.issued"]', 'meta:dc.date.issued', 0.80),
    ('meta[name="DC.date.issued"]', 'meta:dc.date.issued', 0.80),
    ('meta[name="sailthru.date"]', 'meta:sailthru.date', 0.75),
    ('meta[name="date"]', 'meta:date', 0.70),
    ('time[datetime][pubdate]', 'time:pubdate', 0.80),
    ('time[itemprop="datePublished"]', 'time:datePublished', 0.80),
    ('time[datetime]', 'time:datetime', 0.65),
    ('[itemprop="datePublished"]', 'itemprop:datePublished', 0.65),
]


def _jsonld_dates(soup):
    out = []
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '')
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            if '@graph' in item and isinstance(item['@graph'], list):
                stack.extend(item['@graph'])
            for key, conf in (('datePublished', 0.90), ('dateCreated', 0.85),
                              ('uploadDate', 0.90)):
                dt = parse_date(item.get(key))
                if dt:
                    out.append({'date': to_iso(dt), 'confidence': conf,
                                'source': f'jsonld:{key}'})
    return out


def html_date_evidence(html, url):
    """All date evidence found in an HTML document."""
    out = []
    if not html:
        return out
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
    except Exception:
        soup = None

    if soup is not None:
        out.extend(_jsonld_dates(soup))
        for selector, name, conf in _META_SELECTORS:
            try:
                el = soup.select_one(selector)
            except Exception:
                continue
            if el is None:
                continue
            raw = el.get('content') or el.get('datetime') or el.get_text()
            dt = parse_date(raw)
            if dt:
                out.append({'date': to_iso(dt), 'confidence': conf,
                            'source': name})

    if HTMLDATE_AVAILABLE:
        try:
            found = _htmldate_find(html, url=url, original_date=True,
                                   extensive_search=False,
                                   outputformat='%Y-%m-%dT%H:%M:%S')
            dt = parse_date(found)
            if dt:
                out.append({'date': to_iso(dt), 'confidence': 0.80,
                            'source': 'htmldate:original'})
        except Exception as e:
            logger.debug('htmldate failed for %s: %s', url, e)

    if soup is not None and not out:
        try:
            text = soup.get_text(' ', strip=True)[:3000]
        except Exception:
            text = ''
        for pattern in (r'\b(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',
                        r'\b(\d{4}-\d{2}-\d{2})\b',
                        r'\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:19|20)\d{2})\b',
                        r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+(?:19|20)\d{2})\b'):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                dt = parse_date(m.group(1))
                if dt:
                    out.append({'date': to_iso(dt), 'confidence': 0.45,
                                'source': 'text:pattern_match'})
                    break
    return out


def header_date_evidence(headers, source='http:last-modified'):
    """Last-Modified of a static asset (weak: CDNs rewrite it)."""
    if not headers:
        return []
    raw = headers.get('Last-Modified') or headers.get('last-modified')
    dt = parse_date(raw)
    if dt and dt < _now():
        return [{'date': to_iso(dt), 'confidence': 0.35, 'source': source}]
    return []


def exif_capture_date(image_bytes):
    """EXIF DateTimeOriginal of an image file (when the photo was TAKEN,
    which is not its publish date — reported separately as captured_at)."""
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        exif = img.getexif()
        for tag in (36867, 36868, 306):  # DateTimeOriginal, Digitized, DateTime
            raw = exif.get(tag)
            if not raw and hasattr(exif, 'get_ifd'):
                try:
                    raw = exif.get_ifd(0x8769).get(tag)
                except Exception:
                    raw = None
            if raw:
                dt = parse_date(str(raw).replace(':', '-', 2))
                if dt:
                    return to_iso(dt)
    except Exception:
        pass
    return None


# --------------------------------------------------------------- resolve

def resolve_published_at(evidence, bounds=None):
    """Combine page evidence + upper bounds into one dated verdict.

    evidence: list of {'date','confidence','source'} (page-level claims)
    bounds:   list of the same shape whose dates are UPPER bounds
              (first archive capture, engine crawl date)
    Returns {'published_at', 'confidence', 'evidence': [...], 'bound': {...}}
    """
    evidence = [e for e in (evidence or []) if e.get('date')]
    bounds = [b for b in (bounds or []) if b.get('date')]

    best = None
    if evidence:
        # Highest confidence wins; ties -> earliest date
        evidence.sort(key=lambda e: (-e['confidence'], e['date']))
        best = dict(evidence[0])
        # Independent corroboration (same day from 2+ sources) raises trust
        same_day = {e['source'].split(':')[0] for e in evidence
                    if e['date'][:10] == best['date'][:10]}
        if len(same_day) >= 2:
            best['confidence'] = min(0.99, best['confidence'] + 0.04)

    earliest_bound = min(bounds, key=lambda b: b['date']) if bounds else None

    if best is None and earliest_bound is not None:
        return {'published_at': earliest_bound['date'],
                'confidence': earliest_bound['confidence'],
                'evidence': [earliest_bound], 'bound': earliest_bound,
                'is_upper_bound': True}

    if best is not None and earliest_bound is not None \
            and best['date'] > earliest_bound['date']:
        # Page claims a date AFTER it was already archived/crawled: the
        # claim is stale (re-dated repost, updated timestamp). Trust the bound.
        return {'published_at': earliest_bound['date'],
                'confidence': max(earliest_bound['confidence'], 0.6),
                'evidence': [earliest_bound] + evidence,
                'bound': earliest_bound, 'is_upper_bound': True}

    if best is None:
        return {'published_at': None, 'confidence': 0.0, 'evidence': [],
                'bound': None, 'is_upper_bound': False}

    return {'published_at': best['date'], 'confidence': best['confidence'],
            'evidence': evidence, 'bound': earliest_bound,
            'is_upper_bound': False}
