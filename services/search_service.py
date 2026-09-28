"""Search persistence, cache lookup and the manual engine links.

Hard rule (CLAUDE.md #5): harvest visual-match sections ONLY. SerpAPI
`organic_results` are never image matches.
"""
import logging
import traceback

import requests

from providers.serpapi import lens_matches as _serpapi_lens_matches
from providers.vision import vision_web_detection

logger = logging.getLogger(__name__)

# Ranking used when deduplicating matches: strongest bucket wins
MATCH_RANK = {'exact': 0, 'similar': 1, 'page_match': 2}


def persist_search(user_id, search_type, *, query=None, image_url=None,
                   image_hash=None, image_phash=None, results=None,
                   raw_response=None, processing_time_ms=None):
    """Persist a Search + SearchResult rows. Never raises. Returns search id.

    `results` items: dicts with url/title/snippet/thumbnail/domain/
    published_at (datetime|None)/confidence.
    """
    from models import db, Search, SearchResult
    try:
        search = Search(
            user_id=user_id,
            search_type=search_type,
            query=query,
            image_url=image_url,
            image_hash=image_hash,
            image_phash=image_phash,
            result_count=len(results or []),
            processing_time_ms=processing_time_ms,
            raw_response=raw_response,
        )
        db.session.add(search)
        db.session.flush()
        for rank, item in enumerate(results or []):
            url = item.get('url')
            if not url:
                continue
            db.session.add(SearchResult(
                search_id=search.id,
                url=url[:2000],
                title=(item.get('title') or '')[:500] or None,
                snippet=item.get('snippet'),
                thumbnail_url=(item.get('thumbnail') or None),
                domain=(item.get('domain') or None),
                published_at=item.get('published_at'),
                confidence=item.get('confidence'),
                rank=rank,
            ))
        db.session.commit()
        return search.id
    except Exception as e:
        logger.error('Failed to persist search: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def find_cached_search(search_type, image_hash):
    """Most recent Search row for the same query-image hash, or None."""
    if not image_hash:
        return None
    from models import db, Search
    try:
        return (db.session.query(Search)
                .filter_by(search_type=search_type, image_hash=image_hash)
                .order_by(Search.created_at.desc())
                .first())
    except Exception as e:
        logger.error('Search cache lookup failed: %s', e)
        return None


def parse_iso_datetime(value):
    """ISO string -> naive datetime, or None."""
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')) \
                       .replace(tzinfo=None)
    except Exception:
        return None


def manual_search_image_url(image_url):
    """The address the manual engine links carry. A presigned R2 link has
    its own query string (breaks when pasted raw into another URL) and dies
    in 15 minutes; prefer the app's plain public route (production), else a
    24-hour presigned link."""
    try:
        from providers import storage
        key = storage.key_from_presigned_url(image_url)
        if key:
            return storage.public_media_url(key) or storage.presigned_get_url(key, expires=86400) or image_url
    except Exception as e:
        logger.debug('manual link url fallback: %s', e)
    return image_url


def search_images(image_url):
    """Manual reverse-image links (Google Lens, Bing, Yandex, TinEye). The
    image address is percent-encoded so the engines receive it intact."""
    from urllib.parse import quote
    target = quote(manual_search_image_url(image_url), safe='')
    return {
        'google': f"https://lens.google.com/uploadbyurl?url={target}",
        'bing': f"https://www.bing.com/images/search?q=imgurl:{target}&view=detailv2&iss=sbi",
        'yandex': f"https://yandex.com/images/search?rpt=imageview&url={target}",
        'tineye': f"https://tineye.com/search?url={target}",
    }


def scrape_reverse_search(image_url):
    """Reverse image search: SerpAPI Google Lens (exact + visual matches)
    merged with Google Vision Web Detection. Visual-match sections only.
    Returns the legacy structure ('links') plus a normalized 'matches' list
    where every result is tagged exact|similar|page_match.
    """
    try:
        logger.info('Starting reverse image search (Lens + Vision) for %s',
                    image_url)
        search_links = search_images(image_url)

        matches = []
        errors = []
        for lens_type in ('exact_matches', 'visual_matches'):
            try:
                matches.extend(_serpapi_lens_matches(image_url, lens_type))
            except requests.exceptions.Timeout as e:
                errors.append(f'SerpAPI timeout ({lens_type}): {e}')
            except requests.RequestException as e:
                logger.warning('SerpAPI failed (%s): %s', lens_type, e)
                errors.append(f'SerpAPI failed ({lens_type}): {e}')

        # Second source: Google Vision Web Detection (never raises)
        matches.extend(vision_web_detection(image_url))

        # De-duplicate by link, preserving order; 'exact' wins over weaker buckets
        by_link = {}
        for m in matches:
            prev = by_link.get(m['link'])
            if prev is None or MATCH_RANK[m['match_type']] < MATCH_RANK[prev['match_type']]:
                by_link[m['link']] = m
        uniq_matches = list(by_link.values())
        uniq_matches.sort(key=lambda m: MATCH_RANK[m['match_type']])

        result = {
            'links': [m['link'] for m in uniq_matches],
            'matches': uniq_matches,
            'search_urls': search_links,
            'source': 'Google Lens + Vision',
            'success': True
        }
        if errors and not uniq_matches:
            result['error'] = '; '.join(errors)
        return result

    except Exception as e:
        traceback.print_exc()
        return {
            'links': [],
            'matches': [],
            'search_urls': {},
            'error': str(e),
            'success': False
        }
