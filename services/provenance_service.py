"""Provenance analysis: who published the image first, where it spread.

Harvest: Google Lens (exact+visual matches) merged with Vision Web Detection —
visual-match sections only. Each candidate page is fetched and mined for a
publication date with confidence + evidence tracking.
"""
import concurrent.futures
import json
import logging
import os
import re
import traceback
from datetime import datetime
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from providers.serpapi import lens_matches as _serpapi_lens_matches
from providers.vision import vision_web_detection

logger = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

try:
    import dateparser
    DATEPARSER_AVAILABLE = True
except ImportError:
    DATEPARSER_AVAILABLE = False


def _empty_payload(note):
    return {
        'first_seen': None,
        'timeline': [],
        'related_images': [],
        'stats': {'checked': 0, 'with_dates': 0},
        'note': note
    }


def analyze_provenance(image_url):
    """Full provenance payload for an image URL (never raises)."""
    if not BS4_AVAILABLE:
        return _empty_payload(
            'BeautifulSoup4 dependency not available. '
            'Please install: pip install beautifulsoup4')

    if not os.environ.get('SERPAPI_API_KEY'):
        return _empty_payload('SerpAPI key not configured')

    try:
        logger.info('Provenance: Google Lens harvest for %s', image_url)

        # Harvest ONLY visual-match sections via Google Lens (exact + visual
        # matches), merged with Vision Web Detection — never
        # organic_results / inline_images (they are not image matches).
        matches = []
        lens_errors = []
        for lens_type in ('exact_matches', 'visual_matches'):
            try:
                matches.extend(_serpapi_lens_matches(image_url, lens_type))
            except requests.exceptions.Timeout:
                lens_errors.append(f'timeout:{lens_type}')
            except requests.RequestException as e:
                logger.warning('SerpAPI Lens error (%s): %s', lens_type, e)
                lens_errors.append(f'error:{lens_type}')

        matches.extend(vision_web_detection(image_url))

        if not matches and len(lens_errors) == 2:
            return _empty_payload(f'SerpAPI error: {", ".join(lens_errors)}')

        # Build related-images gallery and tagged candidate URLs
        related_images = []
        match_type_by_url = {}
        candidate_urls = []

        for m in matches:
            link = m.get('link')
            if not (link and link.startswith('http')):
                continue
            if link not in match_type_by_url:
                match_type_by_url[link] = m['match_type']
                candidate_urls.append(link)

            if m.get('thumbnail'):
                try:
                    source_domain = urlparse(link).netloc or 'مصدر غير معروف'
                except Exception:
                    source_domain = 'مصدر غير معروف'
                if not any(ri['original'] == m['thumbnail'] for ri in related_images):
                    related_images.append({
                        'thumbnail': m['thumbnail'],
                        'original': m['thumbnail'],
                        'link': link,
                        'source': source_domain,
                        'title': m.get('title', ''),
                        'match_type': m['match_type']
                    })

        # Exact matches first, then similar, then page mentions; cap at 18
        rank = {'exact': 0, 'similar': 1, 'page_match': 2}
        candidate_urls.sort(key=lambda u: rank[match_type_by_url[u]])
        unique_urls = candidate_urls[:18]

        logger.info('Provenance: %d candidates, %d unique, %d related images',
                    len(candidate_urls), len(unique_urls), len(related_images))

        # Limit related images to 24 items
        related_images = related_images[:24]

        # Process URLs in parallel to extract dates and metadata
        timeline_results = process_urls_for_provenance(unique_urls)
        logger.info('Provenance: processed %d timeline results',
                    len(timeline_results))

        # Tag each timeline entry with its match bucket
        for item in timeline_results:
            item['match_type'] = match_type_by_url.get(item.get('url'))

        # Sort timeline: oldest dated first, undated last
        dated_items = [i for i in timeline_results if i.get('published_at')]
        undated_items = [i for i in timeline_results if not i.get('published_at')]
        dated_items.sort(key=lambda x: x['published_at'] or '9999-12-31T23:59:59Z')
        timeline = dated_items + undated_items

        first_seen = dated_items[0] if dated_items else None

        return {
            'first_seen': first_seen,
            'timeline': timeline,
            'related_images': related_images,
            'stats': {'checked': len(timeline_results),
                      'with_dates': len(dated_items)},
            'note': None
        }

    except requests.exceptions.Timeout:
        logger.warning('Provenance request timeout')
        return _empty_payload('Request timeout. Please try again.')
    except Exception as e:
        logger.error('Provenance error: %s', e)
        traceback.print_exc()
        return _empty_payload(f'Error: {str(e)[:200]}')


def process_urls_for_provenance(urls):
    """Process URLs in parallel to extract dates and metadata"""
    from urllib.parse import urlparse
    import re
    from datetime import datetime

    def extract_page_info(url):
        """Extract title, date, and metadata from a single URL"""
        try:
            # Check if BeautifulSoup is available
            if not BS4_AVAILABLE:
                return {
                    'url': url,
                    'domain': urlparse(url).netloc,
                    'title': 'BeautifulSoup not available',
                    'published_at': None,
                    'confidence': 0.0,
                    'evidence': ['missing_dependency:beautifulsoup4']
                }

            # Set up session with retries
            session = requests.Session()
            retry_strategy = Retry(
                total=2,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)

            # Fetch page with timeout
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = session.get(url, headers=headers, timeout=(5, 10))
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            domain = urlparse(url).netloc

            # Extract title
            title = ''
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text().strip()

            # Try og:title as fallback
            if not title:
                og_title = soup.find('meta', property='og:title')
                if og_title:
                    title = og_title.get('content', '').strip()

            # Fallback to domain if no title
            if not title:
                title = domain

            # Extract published date with evidence tracking
            published_at = None
            confidence = 0.0
            evidence = []

            # High confidence sources
            meta_published = soup.find('meta', property='article:published_time')
            if meta_published and meta_published.get('content'):
                date_str = meta_published.get('content')
                parsed_date = parse_date_string(date_str)
                if parsed_date:
                    published_at = parsed_date
                    confidence = 0.95
                    evidence.append('meta:article:published_time')

            # Try JSON-LD structured data (very high confidence)
            if not published_at:
                json_ld_scripts = soup.find_all('script', type='application/ld+json')
                for script in json_ld_scripts:
                    try:
                        data = json.loads(script.string)
                        # Handle both single object and array
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            date_published = item.get('datePublished') or item.get('dateCreated') or item.get('uploadDate')
                            if date_published:
                                parsed_date = parse_date_string(date_published)
                                if parsed_date:
                                    published_at = parsed_date
                                    confidence = 0.90
                                    evidence.append('jsonld:datePublished')
                                    break
                        if published_at:
                            break
                    except:
                        continue

            # Medium-high confidence sources
            if not published_at:
                selectors = [
                    ('meta[property="og:published_time"]', 'meta:og:published_time', 0.85),
                    ('meta[property="article:published"]', 'meta:article:published', 0.85),
                    ('meta[name="pubdate"]', 'meta:pubdate', 0.80),
                    ('meta[name="publishdate"]', 'meta:publishdate', 0.80),
                    ('meta[name="date"]', 'meta:date', 0.75),
                    ('meta[itemprop="datePublished"]', 'meta:datePublished', 0.80),
                    ('meta[name="article.published"]', 'meta:article.published', 0.80),
                    ('time[datetime]', 'time:datetime', 0.75),
                    ('time[pubdate]', 'time:pubdate', 0.75),
                    ('[itemprop="datePublished"]', 'itemprop:datePublished', 0.70),
                ]

                for selector, evidence_name, conf in selectors:
                    element = soup.select_one(selector)
                    if element:
                        date_str = element.get('content') or element.get('datetime') or element.get_text()
                        if date_str:
                            parsed_date = parse_date_string(date_str.strip())
                            if parsed_date:
                                published_at = parsed_date
                                confidence = conf
                                evidence.append(evidence_name)
                                break
            
            # Try to extract from URL path (e.g., /2024/01/15/article)
            if not published_at:
                url_date_match = re.search(r'/(\d{4})/(\d{1,2})/(\d{1,2})/', url)
                if url_date_match:
                    try:
                        year, month, day = url_date_match.groups()
                        date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        parsed_date = parse_date_string(date_str)
                        if parsed_date:
                            published_at = parsed_date
                            confidence = 0.65
                            evidence.append('url:path_date')
                    except:
                        pass
            
            # Search for date patterns in text
            if not published_at:
                text_content = soup.get_text()[:2000]  # First 2000 chars
                # Look for ISO dates
                date_patterns = [
                    r'\b(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',
                    r'\b(\d{4}-\d{2}-\d{2})',
                    r'\b(\d{1,2}/\d{1,2}/\d{4})',
                ]
                for pattern in date_patterns:
                    match = re.search(pattern, text_content)
                    if match:
                        date_str = match.group(1)
                        parsed_date = parse_date_string(date_str)
                        if parsed_date:
                            published_at = parsed_date
                            confidence = 0.50
                            evidence.append('text:pattern_match')
                            break

            return {
                'url': url,
                'domain': domain,
                'title': title[:200],  # Limit title length
                'published_at': published_at,
                'confidence': confidence,
                'evidence': evidence
            }

        except requests.exceptions.RequestException as e:
            return {
                'url': url,
                'domain': urlparse(url).netloc,
                'title': f'Error: {str(e)[:50]}',
                'published_at': None,
                'confidence': 0.0,
                'evidence': [f'fetch_error:{str(e)[:30]}']
            }
        except Exception as e:
            return {
                'url': url,
                'domain': urlparse(url).netloc,
                'title': f'Parse error: {str(e)[:50]}',
                'published_at': None,
                'confidence': 0.0,
                'evidence': [f'parse_error:{str(e)[:30]}']
            }

    # Process URLs in parallel with ThreadPoolExecutor
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_to_url = {executor.submit(extract_page_info, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url, timeout=60):
            try:
                result = future.result(timeout=10)
                results.append(result)
            except concurrent.futures.TimeoutError:
                url = future_to_url[future]
                results.append({
                    'url': url,
                    'domain': urlparse(url).netloc,
                    'title': 'Timeout error',
                    'published_at': None,
                    'confidence': 0.0,
                    'evidence': ['fetch_error:timeout']
                })
            except Exception as e:
                url = future_to_url[future]
                results.append({
                    'url': url,
                    'domain': urlparse(url).netloc,
                    'title': f'Error: {str(e)[:50]}',
                    'published_at': None,
                    'confidence': 0.0,
                    'evidence': [f'fetch_error:{str(e)[:30]}']
                })

    return results

def parse_date_string(date_str):
    """Parse date string and return ISO 8601 UTC format"""
    try:
        if not date_str:
            return None
        
        # Clean the date string
        date_str = str(date_str).strip()

        # Try dateparser first if available
        if DATEPARSER_AVAILABLE:
            parsed = dateparser.parse(date_str)
            if parsed:
                # Convert to UTC and return ISO format
                utc_dt = parsed.replace(tzinfo=None) if parsed.tzinfo is None else parsed.astimezone().replace(tzinfo=None)
                return utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Fallback to basic datetime parsing with more formats
        from datetime import datetime
        formats = [
            # ISO formats
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            # Common formats
            '%d %B %Y',  # 15 January 2024
            '%B %d, %Y',  # January 15, 2024
            '%d %b %Y',  # 15 Jan 2024
            '%b %d, %Y',  # Jan 15, 2024
            # Slash formats
            '%m/%d/%Y',
            '%d/%m/%Y',
            '%Y/%m/%d',
            # Dash formats
            '%d-%m-%Y',
            '%m-%d-%Y',
            # Others
            '%Y%m%d',
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str[:50], fmt)  # Limit to first 50 chars
                return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            except ValueError:
                continue
        
        # Try to extract just year-month-day if format is complex
        import re
        simple_date = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
        if simple_date:
            try:
                dt = datetime.strptime(simple_date.group(0), '%Y-%m-%d')
                return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            except:
                pass

        return None
    except Exception:
        return None

