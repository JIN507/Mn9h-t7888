"""Browser-driven reverse image search (Playwright/Chromium) — engines that
have no API key: the TinEye website and Bing Visual Search.

The browser only fetches the rendered page; parsing is pure Python
(`parse_tineye_html`, `parse_bing_html`) so it is unit-testable and easy to
repair when a site changes its markup.

  tineye_web(image_url) -> matches sorted oldest-first. Each carries
      crawl_date (when TinEye saw that copy) and first_indexed (when TinEye
      first saw the image anywhere) — both are upper bounds on publication.
  bing_web(image_url)   -> Bing turns the image into a text query (its
      auto-caption) and answers with web results. Returned as 'organic'
      leads (must be visually confirmed to enter a timeline) + the caption.

Opt out with BROWSER_SEARCH=false. Unavailable (no playwright / no
chromium) => configured() is False and the engine is skipped.
"""
import base64
import logging
import os
import re
import threading
from urllib.parse import quote, urlparse, parse_qs

from .base import Candidate

logger = logging.getLogger(__name__)

TINEYE_SEARCH = 'https://tineye.com/search?url={url}&sort=crawl_date&order=asc'
BING_SBI = ('https://www.bing.com/images/search?view=detailv2&iss=sbi&form=SBIVSP'
            '&sbisrc=UrlPaste&q=imgurl:{url}')
NAV_TIMEOUT_MS = 25000
RESULT_TIMEOUT_MS = 20000
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0 Safari/537.36')

_state = {'checked': False, 'ok': False}
_lock = threading.Lock()


def configured():
    """Playwright importable, chromium present, and not opted out."""
    if os.environ.get('BROWSER_SEARCH', 'true').lower() == 'false':
        return False
    with _lock:
        if _state['checked']:
            return _state['ok']
        _state['checked'] = True
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
            _state['ok'] = True
        except Exception as e:
            logger.info('browser search unavailable: %s', str(e)[:160])
            _state['ok'] = False
        return _state['ok']


def _render(url, wait_selector=None, settle_ms=1500):
    """Load `url` in headless Chromium; return (final_url, html)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=UA, locale='en-US',
                                      viewport={'width': 1280, 'height': 900})
            page = ctx.new_page()
            page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until='domcontentloaded')
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=RESULT_TIMEOUT_MS)
                except Exception:
                    pass  # no results / slow — parse whatever rendered
            page.wait_for_timeout(settle_ms)
            return page.url, page.content()
        finally:
            browser.close()


# ---------------------------------------------------------------- TinEye

def parse_tineye_html(html):
    """Rendered TinEye results -> list of match dicts (+ first_indexed)."""
    from bs4 import BeautifulSoup
    from services.date_evidence import parse_date, to_iso

    soup = BeautifulSoup(html or '', 'html.parser')
    first_indexed = None
    m = re.search(r'First indexed by TinEye on\s+([A-Za-z]+ \d{1,2}, \d{4})',
                  soup.get_text(' ', strip=True))
    if m:
        first_indexed = to_iso(parse_date(m.group(1)))

    out = []
    for link in soup.select('a[data-test="match-link"]'):
        page_url = link.get('href')
        if not page_url or not page_url.startswith('http'):
            continue
        container = link
        for _ in range(6):
            if container.parent is None:
                break
            container = container.parent
            if container.select_one('[data-test="crawl-date"]'):
                break
        crawl = container.select_one('[data-test="crawl-date"]')
        crawl_iso = to_iso(parse_date(crawl.get_text(strip=True))) if crawl else None
        image_url = None
        for a in container.select('a[href^="http"]'):
            href = a.get('href', '')
            if href != page_url and re.search(r'\.(jpe?g|png|webp|gif|avif)(\?|$)',
                                              href, re.IGNORECASE):
                image_url = href
                break
        size = None
        sm = re.search(r'(\d{2,5})\s*x\s*(\d{2,5})', container.get_text(' ', strip=True))
        if sm:
            size = [int(sm.group(1)), int(sm.group(2))]
        item = Candidate(link=page_url, title='', thumbnail=image_url,
                         match_type='exact', provider='tineye_web').to_dict()
        item['crawl_date'] = crawl_iso
        item['first_indexed'] = first_indexed
        item['image_url'] = image_url
        item['image_size'] = size
        out.append(item)
    return out


def tineye_web(image_url, max_pages=2):
    """TinEye website search, oldest first. Returns match dicts; [] when
    nothing found; raises on browser failure (caller logs + continues)."""
    url = TINEYE_SEARCH.format(url=quote(image_url, safe=''))
    final, html = _render(url, wait_selector='a[data-test="match-link"], .no-results')
    matches = parse_tineye_html(html)
    seen = {m['link'] for m in matches}
    # follow pagination on the hashed results URL
    page = 2
    while matches and page <= max_pages and '/search/' in final:
        base = re.sub(r'([?&])page=\d+', r'\1page=%d' % page, final)
        if base == final:
            base = final + ('&' if '?' in final else '?') + f'page={page}'
        try:
            _, more_html = _render(base, wait_selector='a[data-test="match-link"]',
                                   settle_ms=800)
        except Exception as e:
            logger.info('tineye page %d failed: %s', page, e)
            break
        more = [m for m in parse_tineye_html(more_html) if m['link'] not in seen]
        if not more:
            break
        matches.extend(more)
        seen.update(m['link'] for m in more)
        page += 1
    logger.info('TinEye web returned %d matches (first_indexed=%s)',
                len(matches), matches[0]['first_indexed'] if matches else None)
    return matches


# ------------------------------------------------------------------ Bing

def parse_bing_html(html, final_url=''):
    """Bing visual search lands on a text SERP for its auto-caption.
    Returns (caption, leads[]) — leads are 'organic' (need confirmation)."""
    from bs4 import BeautifulSoup
    caption = None
    try:
        q = parse_qs(urlparse(final_url).query).get('q')
        if q and not q[0].startswith('imgurl:'):
            caption = q[0]
    except Exception:
        pass
    soup = BeautifulSoup(html or '', 'html.parser')
    leads = []
    for li in soup.select('li.b_algo'):
        a = li.select_one('h2 a[href^="http"]') or li.select_one('a[href^="http"]')
        if not a:
            continue
        href = unwrap_bing_redirect(a.get('href'))
        if not href or 'bing.com' in href or 'microsoft.com' in href:
            continue
        item = Candidate(link=href, title=a.get_text(' ', strip=True)[:200],
                         thumbnail=None, match_type='organic',
                         provider='bing_web').to_dict()
        snippet = li.select_one('.b_caption p, p')
        item['snippet'] = snippet.get_text(' ', strip=True)[:200] if snippet else ''
        item['caption'] = caption
        leads.append(item)
    return caption, leads


def unwrap_bing_redirect(href):
    """bing.com/ck/a?...&u=a1<base64url> -> the real target URL."""
    if not href:
        return None
    if 'bing.com/ck/a' not in href:
        return href
    try:
        u = parse_qs(urlparse(href).query).get('u', [''])[0]
        if u.startswith('a1'):
            u = u[2:]
        u += '=' * (-len(u) % 4)
        real = base64.urlsafe_b64decode(u).decode('utf-8', 'replace')
        return real if real.startswith('http') else None
    except Exception:
        return None


def bing_search(image_url):
    """Bing Visual Search via the website -> (auto_caption, leads)."""
    url = BING_SBI.format(url=quote(image_url, safe=''))
    final, html = _render(url, wait_selector='li.b_algo, a.iusc', settle_ms=2500)
    caption, leads = parse_bing_html(html, final)
    logger.info('Bing web: caption=%r leads=%d', caption, len(leads))
    return caption, leads


def bing_web(image_url):
    """Harvest-table entry point: just the leads."""
    return bing_search(image_url)[1]


def bing_caption(image_url):
    """Just the auto-caption Bing assigns to the image (agent text lead)."""
    url = BING_SBI.format(url=quote(image_url, safe=''))
    final, html = _render(url, wait_selector='li.b_algo, a.iusc', settle_ms=1500)
    caption, _ = parse_bing_html(html, final)
    return caption
