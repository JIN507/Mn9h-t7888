"""Date evidence for a sighting, on one axis:

  platform_id  the post's own identifier or timestamp (X snowflake, Instagram
               shortcode, TikTok id, tweet syndication time, Facebook
               creation_time, Telegram message time, YouTube API)
  structured   the page's declared publication date (article:published_time,
               JSON-LD datePublished, <time datetime>)
  weak         guesses (htmldate, URL path, text patterns, Last-Modified)
  none

Upper bounds (TinEye crawl date, first Wayback capture) never become the
date; they are kept alongside as `upper_bound`.
Listing pages are capped at `weak`: whatever they show is not "published then".
"""
from dataclasses import dataclass, field

from services import date_evidence as de
from origin import urls

LEVEL_RANK = {'platform_id': 3, 'structured': 2, 'weak': 1, 'none': 0}
CONFIDENCE = {'platform_id': 0.98, 'structured': 0.9, 'weak': 0.4, 'none': None}


@dataclass
class DateEvidence:
    level: str = 'none'
    when: str = None                 # ISO-8601 UTC
    sources: list = field(default_factory=list)   # [{'source','date','confidence'}]
    upper_bound: str = None

    def brief(self):
        return {'level': self.level, 'when': self.when, 'upper_bound': self.upper_bound,
                'sources': self.sources[:5]}


def _level_of(source):
    s = (source or '').lower()
    if s.startswith('platform:') or s.startswith('api:'):
        return 'platform_id'
    if s.startswith(('meta:', 'jsonld:', 'time:')):
        return 'structured'
    return 'weak'


def for_page(url, html=None, headers=None, *, tweet=None, extra=None, crawl_date=None):
    """Combine every date signal for one page into a DateEvidence.
    tweet: providers.tweet.tweet_info() result (created_at)
    extra: additional evidence dicts (e.g. from platform_fetch_date)."""
    evidence = []
    try:
        evidence.extend(de.platform_date(url) or [])
    except Exception:
        pass
    if tweet and tweet.get('created_at'):
        dt = de.parse_date(tweet['created_at'])
        if dt:
            evidence.append({'date': de.to_iso(dt), 'confidence': 0.98, 'source': 'platform:tweet_time'})
    for e in extra or []:
        if e and e.get('date'):
            evidence.append(e)
    if html:
        try:
            evidence.extend(de.html_date_evidence(html, url) or [])
        except Exception:
            pass
    if headers:
        try:
            evidence.extend(de.header_date_evidence(headers) or [])
        except Exception:
            pass
    bounds = []
    if crawl_date:
        dt = de.parse_date(crawl_date)
        if dt:
            bounds.append({'date': de.to_iso(dt), 'confidence': 0.75, 'source': 'tineye:crawl_date'})

    resolved = de.resolve_published_at(evidence, bounds)
    out = DateEvidence()
    out.sources = [{'source': e['source'], 'date': e['date'], 'confidence': e['confidence']}
                   for e in sorted(evidence, key=lambda e: -e['confidence'])][:6]
    upper = min((b['date'] for b in bounds), default=None)
    if resolved.get('is_upper_bound'):
        out.upper_bound = resolved.get('published_at') or upper
        return out
    out.upper_bound = upper
    when = resolved.get('published_at')
    if not when:
        return out
    # the level is that of the best-ranked source that agrees with the resolved day
    day = when[:10]
    agreeing = [e for e in evidence if (e.get('date') or '')[:10] == day]
    best = max((LEVEL_RANK[_level_of(e['source'])] for e in agreeing), default=1)
    level = next(k for k, v in LEVEL_RANK.items() if v == best)
    if urls.is_listing(url) and level != 'platform_id':
        level = 'weak'
    out.level, out.when = level, when
    return out


def confidence_of(level):
    return CONFIDENCE.get(level)


def earlier(a, b):
    """Order key: day first, then evidence level, then time (day-only dates
    must not beat exact timestamps of the same day)."""
    return (a[:10], ) < (b[:10], )
