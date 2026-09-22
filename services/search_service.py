"""Reverse-search and direct-search business logic.

Hard rule (CLAUDE.md #5): harvest visual-match sections ONLY. Zenserp
`organic` / SerpAPI `organic_results` are never image matches.
"""
import concurrent.futures
import logging
import re
import traceback

import requests

from providers.serpapi import lens_matches as _serpapi_lens_matches
from providers.vision import vision_web_detection

logger = logging.getLogger(__name__)

try:
    import dateparser
    DATEPARSER_AVAILABLE = True
except ImportError:
    DATEPARSER_AVAILABLE = False

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


def _make_translator():
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='auto', target='ar')

        def translate_text(text):
            if not text:
                return text
            try:
                # Don't translate if already looks Arabic (simple heuristic)
                if any('؀' <= char <= 'ۿ' for char in text[:10]):
                    return text
                return translator.translate(text)
            except Exception:
                return text
    except ImportError:
        logger.warning('deep_translator not found, skipping translation')

        def translate_text(text):
            return text
    return translate_text


def _parse_zenserp_item(item, source_type='web'):
    """Parse one Zenserp result into a timeline item (no translation yet)."""
    title = item.get('title', 'No Title')
    link = item.get('url') or item.get('link') or item.get('destination')
    snippet = item.get('description') or item.get('snippet') or item.get('title')
    thumbnail = item.get('thumbnail') or item.get('image')

    # Extract date
    date_str = (item.get('date') or item.get('snippet_highlighted_words', [None])[0]
                if isinstance(item.get('snippet_highlighted_words'), list) else None)

    # Extract date from snippet text if date_str is missing
    if not date_str and snippet:
        date_candidates = []

        # 1. Standard Date: "Oct 25, 2023" or "2023-10-25"
        match_std = re.search(
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b|\b\d{4}-\d{2}-\d{2}\b',
            snippet, re.IGNORECASE)
        if match_std:
            date_candidates.append(match_std.group(0))

        # 2. Relative English: "2 hours ago", "5 mins ago"
        match_rel_en = re.search(
            r'\b\d+\s+(?:sec|min|hour|day|week|month|year)s?\s+ago\b',
            snippet, re.IGNORECASE)
        if match_rel_en:
            date_candidates.append(match_rel_en.group(0))

        # 3. Relative Arabic: "منذ 3 ساعات", "منذ يومين"
        match_rel_ar = re.search(
            r'\bمنذ\s+(?:\d+|يومين|ساعتين)\s+(?:ثواني|ثانية|دقائق|دقيقة|ساعات|ساعة|أيام|يوم|أسابيع|أسبوع|أشهر|شهر|سنوات|سنة)\b',
            snippet)
        if match_rel_ar:
            date_candidates.append(match_rel_ar.group(0))

        if date_candidates:
            date_str = date_candidates[0]

    # Try to extract domain
    domain = 'Web'
    if link:
        try:
            from urllib.parse import urlparse
            domain = urlparse(link).netloc
        except Exception:
            pass

    # Timestamp parsing with Arabic/English hints
    timestamp = None
    if date_str:
        try:
            if DATEPARSER_AVAILABLE:
                dt = dateparser.parse(date_str, languages=['ar', 'en'])
                if dt:
                    timestamp = dt.isoformat()
        except Exception:
            pass

    return {
        'title': title,
        'link': link,
        'snippet': snippet,
        'thumbnail': thumbnail,
        'date_text': date_str,
        'timestamp': timestamp,
        'source': domain,
        'type': source_type
    }


def build_direct_search_timeline(zenserp_data, image_mode):
    """Turn a Zenserp response into the translated, date-sorted timeline.

    Image mode harvests visual-match sections ONLY (similar_images,
    pages_with_matching_images) — never `organic`. Text mode uses `organic`.
    """
    translate_text = _make_translator()
    items_to_process = []

    if image_mode:
        sections_to_check = [
            ('reverse_image_results', {'similar_images': 'similar',
                                       'pages_with_matching_images': 'page_match'}),
        ]
    else:
        sections_to_check = [
            ('organic', None),
            ('image_results', None),
        ]

    for section, subsections in sections_to_check:
        if section in zenserp_data:
            data_section = zenserp_data[section]

            # Nested structure (reverse_image_results)
            if subsections and isinstance(data_section, dict):
                for sub, match_type in subsections.items():
                    if sub in data_section and data_section[sub]:
                        for item in data_section[sub]:
                            items_to_process.append(
                                _parse_zenserp_item(item, match_type))

            # List structure (organic, image_results)
            elif isinstance(data_section, list):
                for item in data_section:
                    items_to_process.append(
                        _parse_zenserp_item(item, 'organic'))

    # Remove duplicates based on link
    seen_links = set()
    unique_items = []
    for item in items_to_process:
        if item['link'] and item['link'] not in seen_links:
            seen_links.add(item['link'])
            unique_items.append(item)

    # Sort: dated items first (oldest -> newest), undated last
    unique_items.sort(key=lambda x: (x['timestamp'] is None, x['timestamp']))

    # Limit to top 20 BEFORE translation to save time
    final_items = unique_items[:20]

    logger.info('Translating %d items', len(final_items))

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        def translate_item(item):
            if not item['title'] and not item['snippet']:
                return item
            if item['title']:
                item['title'] = translate_text(item['title'])
            if item['snippet']:
                item['snippet'] = translate_text(item['snippet'])
            return item

        timeline = list(executor.map(translate_item, final_items))

    logger.info('Total filtered timeline items: %d', len(timeline))
    return timeline
