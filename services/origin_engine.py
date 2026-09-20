"""Origin Engine — "who published this image first?" as a bounded agent loop.

    HARVEST   Lens exact (en/US + ar/SA) + Lens visual + Vision Web Detection
              + TinEye (crawl-date ordered) + Yandex  — all in parallel
    TIER 0    canonical-URL dedup, junk domains, per-domain cap, priority
    INSPECT   one fetch per candidate ->  date evidence  (date_evidence.py)
                                       +  visual verify  (visual_verify.py)
                                       +  bounds: TinEye crawl / Wayback
    ASSESS    earliest visually-confirmed, well-dated sighting = first_seen
    EXPAND    (bounded)  a) Lens pivot on the best matched ORIGINAL image
                         b) LLM text pivot: DeepSeek reads captions/credits
                            -> targeted queries -> Zenserp text SERP -> only
                            visually CONFIRMED pages may enter
              stop when a round finds nothing earlier, or budget is spent
    REPORT    first_seen + verified timeline + evidence + engines + rounds
              (+ Arabic narrative from DeepSeek when configured)

Nothing enters the timeline visually rejected; nothing is called "first"
without a dated, confidence-scored evidence chain.
"""
import concurrent.futures
import logging
import os
import re
import time
from collections import defaultdict
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from providers import deepseek
from providers import tineye as tineye_provider
from providers import wayback as wayback_provider
from providers import yandex as yandex_provider
from providers.serpapi import lens_matches
from providers import vision as vision_provider
from providers.vision import vision_web_detection
from services import date_evidence as de
from services.visual_verify import (build_query_signature,
                                    build_query_signature_from_url,
                                    fetch_page, verify_html)

logger = logging.getLogger(__name__)

MATCH_RANK = {'exact': 0, 'similar': 1, 'page_match': 2, 'organic': 3}
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.avif')
TRACKING_PARAMS = ('utm_', 'fbclid', 'gclid', 'igshid', 'ref_src', 'ref_url',
                   'mc_cid', 'mc_eid', '_ga', 'yclid', 'ocid', 'cmpid')
JUNK_HOSTS = ('google.', 'lens.google', 'bing.com', 'yandex.', 'tineye.com',
              'duckduckgo.com', 'webcache.googleusercontent.com',
              'translate.goog', 'archive.org', 'archive.ph')
SOCIAL_HOSTS = ('twitter.com', 'x.com', 'facebook.com', 'instagram.com',
                't.me', 'telegram.me', 'reddit.com', 'tiktok.com',
                'youtube.com', 'youtu.be', 'threads.net', 'vk.com')
# Listing/index pages (topic, tag, author, category, pagination, home) show
# whatever is newest: they are never an origin and their archive history
# says nothing about when a given image appeared on them.
_LISTING_RE = re.compile(
    r'(^/$)|/(topic|topics|tag|tags|category|categories|author|authors|'
    r'search|archive|archives|latest|photos|gallery|galleries|videos)(/|$)|'
    r'/page/\d+(/|$)|[?&](page|p)=\d+', re.IGNORECASE)
_THUMB_HOSTS = ('gstatic.com', 'ggpht.com', 'bing.net', 'yandex.net',
                'tineye.com', 'pinimg.com')

DEFAULT_BUDGET = {
    'max_rounds': 2,          # expansion rounds after the initial harvest
    'max_inspect': 28,        # page inspections in round 0
    'max_inspect_round': 12,  # per expansion round
    'per_domain': 3,
    'max_llm_calls': 3,
    'max_text_queries': 3,
    'soft_time_s': 170,
    'workers': 8,
}

# "First seen" needs a strongly dated page: platform IDs, publish tags,
# structured data, or a heuristic date corroborated by a second source.
# An htmldate-only guess (0.80) on a dynamic page has repeatedly produced
# false origins in live runs; such pages are reported as earlier_hints.
FIRST_SEEN_MIN_CONFIDENCE = 0.84
THUMBNAIL_MIN_PX = 250
# A low-res engine thumbnail can confirm a *variant* only if the perceptual
# hash agrees too: semantic embeddings score look-alike scenes (another
# ship fire at dusk) above 0.94.
THUMB_VARIANT_MAX_PHASH = 14
# Temporal outlier: a single thumbnail-only variant dated this many days
# before the dense cluster of strongly dated sightings is a look-alike
# until proven otherwise (reported as a hint, never as first seen).
OUTLIER_GAP_DAYS = 120
OUTLIER_COMPANION_DAYS = 45


def _noop(_msg):
    pass


# ------------------------------------------------------------------ tier 0

def canonical_url(url):
    try:
        p = urlparse(url.strip())
        if p.scheme not in ('http', 'https'):
            return None
        host = p.netloc.lower()
        if host.startswith('www.'):
            host = host[4:]
        if host.startswith('mobile.') or host.startswith('m.'):
            host = host.split('.', 1)[1]
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
                 if not k.lower().startswith(TRACKING_PARAMS)]
        path = re.sub(r'/+$', '', p.path) or '/'
        return urlunparse(('https', host, path, '', urlencode(query), ''))
    except Exception:
        return None


def is_junk(url):
    host = urlparse(url).netloc.lower()
    return any(j in host for j in JUNK_HOSTS)


def is_image_url(url):
    return urlparse(url).path.lower().endswith(IMAGE_EXT)


def domain_of(url):
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith('www.') else host


def is_social(url):
    host = urlparse(url).netloc.lower()
    return any(h in host for h in SOCIAL_HOSTS)


def is_listing_url(url):
    try:
        p = urlparse(url)
    except Exception:
        return False
    path = re.sub(r'/+$', '', p.path) or '/'
    return bool(_LISTING_RE.search(path + ('?' + p.query if p.query else '')))


# ------------------------------------------------------------------ harvest

LENS_EXACT_RETRIES = 2
HARVEST_TIMEOUT_S = 60     # slow engines are dropped, not waited for
INSPECT_TIMEOUT_S = 90     # per inspection batch
LENS_RETRY_DELAY_S = float(os.environ.get('LENS_RETRY_DELAY_S', '2'))


def _lens_exact_with_retry(image_url, hl, country):
    """Lens exact matches are the backbone of the harvest; SerpAPI has
    transient blips (connection resets, empty 200s that it then caches).
    Retry twice, bypassing SerpAPI's cache on the retries."""
    last_error = None
    for attempt in range(LENS_EXACT_RETRIES + 1):
        try:
            got = lens_matches(image_url, 'exact_matches', hl=hl, country=country,
                               no_cache=attempt > 0)
            if got:
                return got
            logger.info('lens exact %s/%s empty (attempt %d)', hl, country, attempt + 1)
        except Exception as e:
            last_error = e
            logger.info('lens exact %s/%s failed (attempt %d): %s', hl, country,
                        attempt + 1, e)
        if attempt < LENS_EXACT_RETRIES:
            time.sleep(LENS_RETRY_DELAY_S * (attempt + 1))
    if last_error is not None:
        raise last_error
    return []


def _browser_engine(name):
    """Playwright-driven engines (TinEye / Bing websites) — optional dep.
    Bing is off unless BING_WEB=true: its URL-paste flow stopped returning
    results to headless browsers (Sept 2026) and cost ~10 s per run."""
    if name == 'bing_web' and os.environ.get('BING_WEB', 'false').lower() != 'true':
        return None
    try:
        from providers import browser_search
    except Exception:  # playwright not installed
        return None
    if not browser_search.configured():
        return None
    return getattr(browser_search, name, None)


SEARCH_COPY_TTL_S = 3600


def _download_bytes(image_url, timeout=(5, 20)):
    try:
        r = requests.get(image_url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception as e:
        logger.warning('cannot download query image: %s', e)
        return None


def search_copy_url(image_bytes, image_url):
    """A clean, public, extension-bearing URL of the query image for the
    engines. Presigned R2 links (long query strings) are rejected by Yandex
    ('not publicly accessible') and are flaky with Lens; an expiring ImgBB
    copy is accepted everywhere. The image is being sent to those engines
    anyway, so the copy adds no exposure. Falls back to image_url."""
    if not image_bytes or os.environ.get('SEARCH_COPY', 'imgbb').lower() == 'none':
        return image_url
    try:
        parsed = urlparse(image_url)
        if not parsed.query:
            return image_url          # already a plain public URL
    except Exception:
        return image_url
    # Option A: the R2 bucket has public access (r2.dev or custom domain):
    # same object, plain URL, no upload needed.
    public_base = os.environ.get('R2_PUBLIC_BASE_URL', '').rstrip('/')
    if public_base and 'r2.cloudflarestorage.com' in parsed.netloc:
        key = parsed.path.lstrip('/').split('/', 1)[-1]   # drop the bucket segment
        if key:
            return f'{public_base}/{key}'
    # Option B: an expiring ImgBB copy.
    if not os.environ.get('IMGBB_API_KEY'):
        logger.warning('search copy: no R2_PUBLIC_BASE_URL and no IMGBB_API_KEY — '
                       'engines get the presigned link (Yandex will reject it)')
        return image_url
    try:
        from providers.imgbb import upload_to_imgbb
        url = upload_to_imgbb(image_bytes, expiration=SEARCH_COPY_TTL_S)
        if url and url.startswith('http'):
            logger.info('search copy hosted for engines (expires in %ss)', SEARCH_COPY_TTL_S)
            return url
    except Exception as e:
        logger.warning('search copy upload failed: %s', e)
    return image_url


def engine_table(image_url, *, include_visual=True):
    """name -> zero-arg callable for every engine that is configured.
    Also returns {name: note} for engines that are NOT available."""
    tasks = {
        'lens_exact_en': lambda: _lens_exact_with_retry(image_url, 'en', 'us'),
        'lens_exact_ar': lambda: _lens_exact_with_retry(image_url, 'ar', 'sa'),
        'vision': lambda: vision_web_detection(image_url),
        'tineye': lambda: tineye_provider.search_by_url(image_url),
        'yandex': lambda: yandex_provider.reverse_image(image_url),
    }
    if include_visual:
        tasks['lens_visual'] = lambda: lens_matches(
            image_url, 'visual_matches', hl='en', country='us')
    unavailable = {}
    if not tineye_provider.configured():
        tasks.pop('tineye')
        web = _browser_engine('tineye_web')
        if web is not None:
            tasks['tineye_web'] = lambda: web(image_url)
        else:
            unavailable['tineye'] = 'not configured'
    if not vision_provider.configured():
        tasks.pop('vision')
        unavailable['vision'] = 'not configured'
    bing = _browser_engine('bing_web')
    if bing is not None:
        tasks['bing_web'] = lambda: bing(image_url)
    else:
        unavailable['bing'] = 'not configured'
    return tasks, unavailable


ENGINE_NAMES = ('lens_exact_en', 'lens_exact_ar', 'lens_visual', 'yandex',
                'tineye', 'tineye_web', 'vision', 'bing_web')


def harvest_engine(name, image_url):
    """Run ONE engine (agent tool). Returns (matches, status_dict)."""
    tasks, unavailable = engine_table(image_url)
    if name not in tasks:
        note = (unavailable.get(name) or unavailable.get(name.replace('_web', ''))
                or ('not configured' if name in ENGINE_NAMES else 'unknown engine'))
        return [], {'ok': False, 'count': 0, 'note': note}
    try:
        got = tasks[name]() or []
        return got, {'ok': True, 'count': len(got)}
    except Exception as e:
        logger.warning('engine %s failed: %s', name, e)
        return [], {'ok': False, 'count': 0, 'note': str(e)[:120]}


MAX_EXTRA_FRAMES = 7          # extra frames that get their own Lens search (a clip's scenes differ)
MAX_SIGNATURE_FRAMES = 11     # extra frames used for visual matching
VIDEO_CONSENSUS_MIN = 5       # ambiguous sightings of the same scene ...
VIDEO_CONSENSUS_SIM = 0.78    # ... at least this similar ...
VIDEO_CONSENSUS_WINDOW_DAYS = 3  # ... within this window => probable match


def _harvest(image_url, progress, engines_status, *, include_visual=True,
             extra_frame_urls=None):
    """Run every candidate generator in parallel. Returns raw match dicts.
    extra_frame_urls (video mode): more frames of the same clip, each gets
    a Lens exact search of its own — pages often show a different moment."""
    tasks, unavailable = engine_table(image_url, include_visual=include_visual)
    for name, note in unavailable.items():
        engines_status[name] = {'ok': False, 'count': 0, 'note': note}
    for n, frame in enumerate((extra_frame_urls or [])[:MAX_EXTRA_FRAMES], start=2):
        tasks[f'lens_exact_en@frame{n}'] = (
            lambda f=frame: _tag_frame(_lens_exact_with_retry(f, 'en', 'us'), n))

    matches = []
    # No context manager: a straggling engine must not block the run
    # (shutdown(wait=False) lets it finish in the background, ignored).
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks))
    futures = {ex.submit(fn): name for name, fn in tasks.items()}
    try:
        for fut in concurrent.futures.as_completed(futures, timeout=HARVEST_TIMEOUT_S):
            name = futures[fut]
            try:
                got = fut.result() or []
                engines_status[name] = {'ok': True, 'count': len(got)}
                matches.extend(got)
                progress(f'{name}: {len(got)} نتيجة')
            except Exception as e:  # provider failures never stop the run
                logger.warning('engine %s failed: %s', name, e)
                engines_status[name] = {'ok': False, 'count': 0,
                                        'note': str(e)[:120]}
    except concurrent.futures.TimeoutError:
        for fut, name in futures.items():
            if not fut.done():
                engines_status[name] = {'ok': False, 'count': 0,
                                        'note': 'timeout'}
                fut.cancel()
    finally:
        ex.shutdown(wait=False)
    return matches


def _tag_frame(matches, n):
    for m in matches or []:
        m['frame'] = n
    return matches


def merge_candidates(matches, seen=None):
    """Tier 0: dedupe by canonical URL, keep best bucket + all providers."""
    seen = seen or set()
    merged = {}
    for m in matches:
        link = m.get('link')
        if not link:
            continue
        canon = canonical_url(link)
        if not canon or canon in seen or is_junk(canon):
            continue
        entry = merged.get(canon)
        if entry is None:
            entry = merged[canon] = {
                'url': link, 'canonical': canon, 'domain': domain_of(canon),
                'title': m.get('title') or '', 'match_type': m.get('match_type', 'similar'),
                'providers': [], 'engine_images': [], 'thumbnail': m.get('thumbnail'),
                'crawl_date': None, 'is_image': is_image_url(canon), 'frames': [],
            }
        frame = m.get('frame', 1)
        if frame not in entry['frames']:
            entry['frames'].append(frame)
        if MATCH_RANK.get(m.get('match_type'), 9) < MATCH_RANK.get(entry['match_type'], 9):
            entry['match_type'] = m['match_type']
        if m.get('provider') and m['provider'] not in entry['providers']:
            entry['providers'].append(m['provider'])
        for key in ('image_url', 'thumbnail'):
            img = m.get(key)
            if img and img.startswith('http') and img not in entry['engine_images']:
                entry['engine_images'].append(img)
        if not entry['title'] and m.get('title'):
            entry['title'] = m['title']
        if m.get('crawl_date') and (entry['crawl_date'] is None
                                    or m['crawl_date'] < entry['crawl_date']):
            entry['crawl_date'] = m['crawl_date']
    return list(merged.values())


def prioritize(candidates, limit, per_domain, by_frame=False):
    """Exact/TinEye/multi-engine first; cap per domain; cap total.
    by_frame (video): round-robin across the frames that produced the
    candidates so one busy scene cannot crowd out the others."""
    if by_frame:
        groups = defaultdict(list)
        for c in candidates:
            groups[min(c.get('frames') or [1])].append(c)
        if len(groups) > 1:
            ranked = {f: prioritize(cs, limit, per_domain) for f, cs in groups.items()}
            out, per, seen_urls = [], defaultdict(int), set()
            while len(out) < limit and any(ranked.values()):
                for f in sorted(ranked):
                    while ranked[f]:
                        c = ranked[f].pop(0)
                        if c['canonical'] in seen_urls or per[c['domain']] >= per_domain:
                            continue
                        seen_urls.add(c['canonical'])
                        per[c['domain']] += 1
                        out.append(c)
                        break
                    if len(out) >= limit:
                        break
            return out
    def score(c):
        s = MATCH_RANK.get(c['match_type'], 9) * 10
        s -= 4 * min(len(c['providers']), 3)          # corroborated by engines
        if c['crawl_date']:
            s -= 5                                    # TinEye dated it
        if any(h in c['domain'] for h in SOCIAL_HOSTS):
            s -= 4                                    # origins are often social; exact timestamps
        if c['is_image']:
            s += 3                                    # bare files: weak pages
        if is_listing_url(c['url']):
            s += 6                                    # topic/tag/home pages: never origins
        return s

    ranked = sorted(candidates, key=score)
    per = defaultdict(int)
    out = []
    for c in ranked:
        if per[c['domain']] >= per_domain:
            continue
        per[c['domain']] += 1
        out.append(c)
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ inspect

def _title_from_html(html, fallback):
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        og = soup.find('meta', property='og:title')
        if og and og.get('content'):
            return og['content'].strip()[:200]
        if soup.title and soup.title.string:
            return soup.title.string.strip()[:200]
    except Exception:
        pass
    return fallback


def _page_text_snippet(html, limit=600):
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        desc = soup.find('meta', property='og:description') or \
            soup.find('meta', attrs={'name': 'description'})
        text = (desc.get('content', '') if desc else '') + ' ' + \
            soup.get_text(' ', strip=True)
        return re.sub(r'\s+', ' ', text)[:limit]
    except Exception:
        return ''


def inspect_candidate(cand, query_sig, *, use_wayback=True, strict=False):
    """One candidate -> dated + visually-verified sighting (never raises)."""
    url = cand['url']
    out = {
        'url': url, 'domain': cand['domain'], 'title': cand.get('title') or cand['domain'],
        'match_type': cand['match_type'], 'providers': cand['providers'],
        'thumbnail': cand.get('thumbnail'), 'published_at': None,
        'confidence': 0.0, 'evidence': [], 'bound': None, 'is_upper_bound': False,
        'visual': {'verdict': 'unverified'}, 'captured_at': None,
        'image_size': None, 'snippet': '', 'origin_round': cand.get('round', 0),
        'is_listing': is_listing_url(url), 'frames': cand.get('frames') or [1],
    }
    evidence = list(de.platform_date(url)) + list(de.url_path_date(url))
    bounds = []
    if cand.get('crawl_date'):
        dt = de.parse_date(cand['crawl_date'])
        if dt:
            bounds.append({'date': de.to_iso(dt), 'confidence': 0.75,
                           'source': 'tineye:crawl_date'})

    html = ''
    headers = None
    if cand.get('is_image'):
        visual = verify_html('', url, query_sig, extra_image_urls=[url],
                             keep_bytes=True) if query_sig else {'verdict': 'unverified'}
    else:
        page = fetch_page(url)
        if page is not None:
            html = page.text or ''
            headers = page.headers
        # Platforms that refuse plain fetches or hide dates behind JS:
        # ask them the way they answer (embed page / crawler UA). This
        # also yields the post's HTML (og:image) for visual verification.
        social = is_social(url)
        if social and not any(e['confidence'] >= 0.9 for e in evidence):
            ev, platform_html = de.platform_fetch_date(url)
            evidence.extend(ev)
            if platform_html and not html:
                html = platform_html
        if html:
            out['title'] = _title_from_html(html, out['title'])
            out['snippet'] = _page_text_snippet(html)
            evidence.extend(de.html_date_evidence(html, url))
        elif page is None:
            out['fetch_error'] = True
        visual = verify_html(html, url, query_sig,
                             extra_image_urls=cand.get('engine_images') or [],
                             keep_bytes=True) if query_sig else {'verdict': 'unverified'}

    blob = visual.pop('matched_image_bytes', None)
    img_headers = visual.pop('matched_headers', None)
    size = visual.pop('matched_size', None)
    matched_from = visual.pop('matched_from', 'page')
    out['visual'] = {k: visual.get(k) for k in
                     ('verdict', 'match_kind', 'similarity', 'phash_distance',
                      'matched_image_url')}
    out['visual']['matched_from'] = matched_from
    if (out['visual']['verdict'] == 'confirmed' and out['visual']['match_kind'] == 'variant'
            and matched_from == 'engine'
            and (out['visual']['phash_distance'] is None
                 or out['visual']['phash_distance'] > THUMB_VARIANT_MAX_PHASH)):
        out['visual']['verdict'] = 'ambiguous'
        out['visual']['note'] = 'engine thumbnail: embedding agrees, hash does not'
    if size:
        out['image_size'] = list(size)
        # A tiny variant is a sidebar/related-post thumbnail, not the page's
        # own use of the image: keep it in the timeline, never call it first.
        # (Engine-provided thumbnails are exempt: JS-only pages such as X
        # expose no images to fetch, so the engine's thumb is all we have.)
        if (min(size) < THUMBNAIL_MIN_PX and out['visual']['match_kind'] == 'variant'
                and matched_from == 'page'):
            out['visual']['thumbnail_only'] = True
    if blob:
        out['captured_at'] = de.exif_capture_date(blob)
    if img_headers:
        evidence.extend(de.header_date_evidence(img_headers))

    # The matched image FILE's upload date (/uploads/2025/05/...) is a LOWER
    # bound on when the image was on this page: an article dated 2017 that
    # serves the image from a 2025 upload path re-used it in 2025.
    lower = None
    img_url = out['visual'].get('matched_image_url')
    if img_url and not any(h in img_url for h in _THUMB_HOSTS):
        for e in de.url_path_date(img_url):
            lower = e
            break
    if lower:
        evidence = [dict(e, confidence=min(e['confidence'], 0.4),
                         source=e['source'] + '?before_image_upload')
                    if e['date'] < lower['date'][:10] and not e['source'].startswith('platform:')
                    else e for e in evidence]

    # Archive bounds: only when the page itself gave nothing solid, never
    # for listing pages (dynamic) or social posts (archive rarely has them,
    # and their own IDs/meta are far better).
    strong = any(e['confidence'] >= 0.8 for e in evidence)
    if (use_wayback and not strong and out['visual']['verdict'] != 'rejected'
            and not out['is_listing'] and not is_social(url)):
        wb = wayback_provider.earliest_capture(url)
        if wb:
            bounds.append({'date': wb, 'confidence': 0.6,
                           'source': 'wayback:first_capture'})
        # the matched image FILE's first capture is a bound on the image
        # itself (listing-proof), when it is hosted by the site, not a CDN thumb
        img = out['visual'].get('matched_image_url')
        if img and not any(h in img for h in _THUMB_HOSTS):
            wbi = wayback_provider.earliest_capture(img)
            if wbi:
                bounds.append({'date': wbi, 'confidence': 0.65,
                               'source': 'wayback:image_first_capture'})

    resolved = de.resolve_published_at(evidence, bounds)
    out.update({k: resolved[k] for k in
                ('published_at', 'confidence', 'evidence', 'bound',
                 'is_upper_bound')})
    out['is_lower_bound'] = False
    if lower and (out['published_at'] is None or out['published_at'] < lower['date']):
        # The page's own date predates the image file: the image was added
        # later. All we know is "not before the upload month" — a lower
        # bound, reported as such and never eligible as first seen.
        out['published_at'] = lower['date']
        out['confidence'] = 0.5
        out['is_lower_bound'] = True
        out['evidence'] = [{'date': lower['date'], 'confidence': 0.5,
                            'source': 'image:upload_path_date'}] + list(out['evidence'])

    if strict and out['visual']['verdict'] != 'confirmed':
        out['dropped'] = 'text_pivot_unconfirmed'
    return out


def inspect_many(cands, query_sig, workers, progress, *, strict=False):
    results = []
    if not cands:
        return results
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    futures = {ex.submit(inspect_candidate, c, query_sig, strict=strict): c
               for c in cands}
    done = 0
    try:
        for fut in concurrent.futures.as_completed(futures, timeout=INSPECT_TIMEOUT_S):
            done += 1
            try:
                results.append(fut.result())
            except Exception as e:
                c = futures[fut]
                logger.info('inspect failed %s: %s', c['url'], e)
            if done % 5 == 0:
                progress(f'تم فحص {done}/{len(cands)} صفحة')
    except concurrent.futures.TimeoutError:
        logger.warning('inspect_many: %d/%d pages timed out',
                       len(cands) - done, len(cands))
        for fut in futures:
            fut.cancel()
    finally:
        ex.shutdown(wait=False)
    return results


# ------------------------------------------------------------------- assess

def _eligible_first(item):
    v = item['visual']['verdict']
    if v == 'rejected' or item.get('dropped') or item.get('is_listing'):
        return False
    if item.get('temporal_outlier'):
        return False
    if item['visual'].get('thumbnail_only') or item.get('is_lower_bound'):
        return False
    if not item['published_at'] or item['confidence'] < FIRST_SEEN_MIN_CONFIDENCE:
        return False
    if v in ('confirmed', 'probable'):
        return True
    # No encoder / no images extracted: trust only engine-declared exact matches
    return v in ('unverified', 'no_image') and item['match_type'] == 'exact'


def _first_seen_key(item):
    """Order by DAY, then confidence, then time.

    Many extractors only know the day (htmldate, URL paths -> midnight), so
    comparing full timestamps would let a vague "2024-07-19T00:00:00Z" beat
    an exact "2024-07-19T16:31:42Z" tweet ID. Same-day sightings are settled
    by evidence strength instead.
    """
    return (item['published_at'][:10], -item['confidence'], item['published_at'])


def _days(iso):
    from datetime import datetime
    return datetime.strptime(iso[:10], '%Y-%m-%d').toordinal()


def _is_temporal_outlier(item, eligible):
    """True when `item` is a thumbnail-only variant far ahead of the
    cluster of strongly dated sightings, with no companion near its date."""
    v = item['visual']
    if not (v.get('match_kind') == 'variant' and v.get('matched_from') == 'engine'):
        return False
    strong = sorted(_days(i['published_at']) for i in eligible
                    if i is not item and i.get('confidence', 0) >= 0.9)
    if len(strong) < 5:
        return False
    d = _days(item['published_at'])
    cluster_start = strong[len(strong) // 10]            # 10th percentile
    if d >= cluster_start - OUTLIER_GAP_DAYS:
        return False
    companions = [x for x in strong if abs(x - d) <= OUTLIER_COMPANION_DAYS]
    return not companions


def video_consensus(timeline):
    """Video mode fallback. Posters of OTHER moments of the clip never
    pass exact/variant confirmation; but when many independent, dated
    sightings of the same scene cluster within a few days, the clip is
    the same clip. Marks that cluster 'probable' (clearly labeled) so an
    earliest sighting can be named. Returns the number promoted."""
    if any(i['visual']['verdict'] == 'confirmed' for i in timeline):
        return 0
    pool = [i for i in timeline
            if i['visual']['verdict'] == 'ambiguous' and i.get('published_at')
            and (i['visual'].get('similarity') or 0) >= VIDEO_CONSENSUS_SIM
            and not i.get('is_listing')]
    if len(pool) < VIDEO_CONSENSUS_MIN:
        return 0
    pool.sort(key=lambda i: i['published_at'])
    days = [_days(i['published_at']) for i in pool]
    best_start, best_n = 0, 0
    for a in range(len(pool)):
        n = sum(1 for d in days[a:] if d - days[a] <= VIDEO_CONSENSUS_WINDOW_DAYS)
        if n > best_n:
            best_start, best_n = a, n
    if best_n < VIDEO_CONSENSUS_MIN:
        return 0
    anchor = days[best_start]
    promoted = 0
    for i, d in zip(pool, days):
        if 0 <= d - anchor <= VIDEO_CONSENSUS_WINDOW_DAYS:
            i['visual']['verdict'] = 'probable'
            i['visual']['match_kind'] = 'video_consensus'
            i['probable'] = True
            promoted += 1
    return promoted


def assess(timeline):
    dated = [i for i in timeline if _eligible_first(i)]
    dated.sort(key=_first_seen_key)
    for i in dated:
        if _is_temporal_outlier(i, dated):
            i['temporal_outlier'] = True
        else:
            return i
    return None


def earliest_by_frame(timeline):
    """Video mode: the earliest eligible sighting per source frame (scene).
    Returns {frame_no: item} for frames that produced any eligible sighting."""
    out = {}
    for item in sorted([i for i in timeline if _eligible_first(i)], key=_first_seen_key):
        for f in item.get('frames') or [1]:
            out.setdefault(f, item)
    return out


def earlier_hints(timeline, first_seen, limit=5):
    """Visually-confirmed sightings dated EARLIER than first_seen that did
    not meet the first-seen bar (weak date, lower bound, listing page,
    thumbnail). Shown to the analyst as leads, never as the answer."""
    if not first_seen:
        return []
    cutoff = first_seen['published_at'][:10]
    hints = [i for i in timeline
             if i.get('published_at') and i['published_at'][:10] < cutoff
             and i['visual']['verdict'] in ('confirmed', 'ambiguous')
             and not i.get('dropped') and not _eligible_first(i)]
    hints.sort(key=_first_seen_key)
    return hints[:limit]


# ------------------------------------------------------------------- expand

def _lens_pivot(first_seen, timeline, image_url, seen, progress, engines_status):
    """Re-search Lens using the best matched ORIGINAL image (higher-res,
    un-cropped copies return far more exact matches than a screenshot)."""
    pool = [i for i in timeline if i['visual'].get('matched_image_url')
            and i['visual']['verdict'] == 'confirmed']
    if not pool:
        return []
    pool.sort(key=lambda i: -(i['image_size'][0] * i['image_size'][1])
              if i.get('image_size') else 0)
    pivot = pool[0]['visual']['matched_image_url']
    if canonical_url(pivot) == canonical_url(image_url):
        return []
    progress('إعادة البحث بالنسخة الأصلية عالية الدقة...')
    raw = []
    for hl, country in (('en', 'us'), ('ar', 'sa')):
        try:
            raw.extend(lens_matches(pivot, 'exact_matches', hl=hl, country=country))
        except Exception as e:
            logger.info('lens pivot failed: %s', e)
    engines_status['lens_pivot'] = {'ok': True, 'count': len(raw),
                                    'pivot_image': pivot}
    return merge_candidates(raw, seen)


_PLAN_SYSTEM = (
    'You are an OSINT image-provenance analyst. You receive pages where an '
    'image was found. Infer what the image shows and who most likely '
    'published it FIRST. Return strict JSON: {"queries": [<=3 short web '
    'search queries (mix Arabic and English) that would surface the '
    'ORIGINAL post/article, e.g. "<event> <place> <month year> photo">], '
    '"credited_sources": [names/handles/outlets credited as the photo '
    'source in captions like "Photo: Reuters/…" or "via @handle"], '
    '"earliest_hint": "<date or null>", "notes": "<one line>"}. '
    'Never invent facts absent from the input.'
)


def _llm_text_pivot(timeline, first_seen, seen, progress, engines_status,
                    budget, llm_calls):
    """DeepSeek reads captions/credits -> text queries -> Zenserp SERP.
    Only visually CONFIRMED pages may enter from this path."""
    if not deepseek.configured() or not os.environ.get('ZENSERP_API_KEY'):
        return [], llm_calls, None
    if llm_calls >= budget['max_llm_calls']:
        return [], llm_calls, None

    top = sorted([i for i in timeline if not i.get('dropped')],
                 key=lambda i: (i['published_at'] or '9999', -i['confidence']))[:12]
    lines = []
    for i in top:
        lines.append(f"- [{i['published_at'] or 'undated'}] {i['domain']} | "
                     f"{i['title'][:120]} | {i['snippet'][:250]}")
    user = ('Pages where the image appears (earliest first):\n' + '\n'.join(lines)
            + '\n\nCurrent earliest confirmed: '
            + (f"{first_seen['published_at']} {first_seen['domain']}" if first_seen else 'none'))
    progress('التخطيط للبحث النصي (DeepSeek)...')
    plan = deepseek.chat_json(_PLAN_SYSTEM, user, max_tokens=600)
    llm_calls += 1
    if not plan:
        return [], llm_calls, None

    queries = [q for q in (plan.get('queries') or []) if isinstance(q, str)][:budget['max_text_queries']]
    for src in (plan.get('credited_sources') or [])[:2]:
        if isinstance(src, str) and src and len(queries) < budget['max_text_queries'] + 1:
            queries.append(f'{src} photo')
    if not queries:
        return [], llm_calls, plan

    from providers.zenserp import text_search
    raw = []
    for q in queries:
        try:
            resp = text_search(q, num=10, gl='us', hl='en')
            if resp.status_code != 200:
                continue
            data = resp.json()
            for item in (data.get('organic') or [])[:10]:
                link = item.get('url') or item.get('link')
                if link:
                    raw.append({'link': link, 'title': item.get('title', ''),
                                'match_type': 'organic', 'provider': 'text_pivot',
                                'thumbnail': None})
        except Exception as e:
            logger.info('text pivot query failed: %s', e)
    engines_status['text_pivot'] = {'ok': True, 'count': len(raw), 'queries': queries}
    return merge_candidates(raw, seen), llm_calls, plan


# ------------------------------------------------------------------- report

_NARRATIVE_SYSTEM = (
    'أنت محلل تحقق من الصور. اكتب ملخصاً عربياً موجزاً (4-6 جمل) عن أول ظهور '
    'للصورة وانتشارها اعتماداً فقط على البيانات المعطاة. اذكر النطاق والتاريخ '
    'ونوع الدليل لكل ادعاء. إن كان التاريخ حداً أعلى (أرشيف/زحف) فقل "على الأقل منذ". '
    'لا تخترع معلومات. إن لم يوجد مصدر مؤكد فقل ذلك بوضوح.'
)


def _narrative(payload, llm_calls, budget):
    if not deepseek.configured() or llm_calls >= budget['max_llm_calls']:
        return None
    fs = payload.get('first_seen')
    lines = []
    for i in payload['timeline'][:10]:
        ev = ', '.join(e['source'] for e in i.get('evidence', [])[:3])
        lines.append(f"- {i['published_at'] or 'بدون تاريخ'} | {i['domain']} | "
                     f"{i['title'][:90]} | ثقة {i['confidence']:.2f} | "
                     f"بصري {i['visual'].get('verdict')} | أدلة: {ev}")
    user = ('أول ظهور مؤكد: ' + (f"{fs['published_at']} على {fs['domain']} ({fs['url']})"
                               if fs else 'لا يوجد') + '\n'
            + f"عدد المطابقات المفحوصة: {payload['stats']['checked']}, "
              f"المؤكدة بصرياً: {payload['stats']['visually_confirmed']}, "
              f"المرفوضة: {payload['stats']['visually_rejected']}\n"
            + 'الخط الزمني:\n' + '\n'.join(lines))
    return deepseek.chat(_NARRATIVE_SYSTEM, user, max_tokens=500, temperature=0.3)


def _public_item(i):
    keep = ('url', 'domain', 'title', 'match_type', 'providers', 'thumbnail',
            'published_at', 'confidence', 'evidence', 'bound', 'is_upper_bound',
            'visual', 'captured_at', 'image_size', 'origin_round', 'is_listing',
            'is_lower_bound', 'temporal_outlier', 'probable', 'frames')
    item = {k: i.get(k) for k in keep}
    item['link'] = i['url']
    item['type'] = i['match_type']
    item['evidence'] = [{'source': e['source'], 'date': e['date'],
                         'confidence': e['confidence']} for e in (i.get('evidence') or [])[:5]]
    return item


# --------------------------------------------------------------------- main

def frame_signatures(primary_bytes, extra_frame_urls):
    """Query signature list: the primary image + every downloadable extra
    frame (video mode). A single dict when there are no extras."""
    primary = build_query_signature(primary_bytes) if primary_bytes else None
    if not extra_frame_urls:
        return primary
    sigs = [primary] if primary else []
    for url in extra_frame_urls[:MAX_SIGNATURE_FRAMES]:
        data = _download_bytes(url)
        sig = build_query_signature(data) if data else None
        if sig:
            sigs.append(sig)
    return sigs or None


def investigate_origin(image_url, *, progress=None, budget=None,
                       extra_frame_urls=None):
    """Full origin investigation for a hosted image URL. Never raises.
    extra_frame_urls: other frames of the same video (video mode)."""
    progress = progress or _noop
    budget = {**DEFAULT_BUDGET, **(budget or {})}
    started = time.monotonic()
    engines_status = {}
    rounds = []
    llm_calls = 0

    def time_left():
        return budget['soft_time_s'] - (time.monotonic() - started)

    if not os.environ.get('SERPAPI_API_KEY'):
        return _empty('SerpAPI key not configured')

    progress('جاري تجهيز بصمة الصورة...')
    image_bytes = _download_bytes(image_url)
    query_sig = frame_signatures(image_bytes, extra_frame_urls)
    search_url = search_copy_url(image_bytes, image_url)

    # ---- round 0: harvest + inspect
    progress('جاري البحث في المحركات (Lens, Vision, TinEye, Yandex)...')
    raw = _harvest(search_url, progress, engines_status,
                   extra_frame_urls=extra_frame_urls)
    seen = set()
    cands = merge_candidates(raw, seen)
    seen.update(c['canonical'] for c in cands)
    n_frames = 1 + len(extra_frame_urls or [])
    limit = min(48, budget['max_inspect'] + 5 * (n_frames - 1))
    chosen = prioritize(cands, limit, budget['per_domain'], by_frame=n_frames > 1)
    progress(f'{len(cands)} مرشحاً فريداً — فحص {len(chosen)} صفحة...')
    timeline = inspect_many(chosen, query_sig, budget['workers'], progress)
    if extra_frame_urls:
        video_consensus(timeline)
    first_seen = assess(timeline)
    rounds.append({'round': 0, 'candidates': len(cands), 'inspected': len(chosen),
                   'first_seen': first_seen['published_at'] if first_seen else None})

    # ---- expansion rounds
    for r in range(1, budget['max_rounds'] + 1):
        if time_left() < 30:
            break
        new_cands = []
        if r == 1:
            new_cands += _lens_pivot(first_seen, timeline, search_url, seen,
                                     progress, engines_status)
        pivot_cands, llm_calls, plan = _llm_text_pivot(
            timeline, first_seen, seen, progress, engines_status, budget, llm_calls)
        strict_urls = {c['canonical'] for c in pivot_cands}
        new_cands += pivot_cands
        if not new_cands:
            rounds.append({'round': r, 'candidates': 0, 'inspected': 0,
                           'stopped': 'no_new_candidates'})
            break
        seen.update(c['canonical'] for c in new_cands)
        for c in new_cands:
            c['round'] = r
        chosen = prioritize(new_cands, budget['max_inspect_round'], budget['per_domain'])
        progress(f'الجولة {r}: فحص {len(chosen)} صفحة جديدة...')
        pivot_part = [c for c in chosen if c['canonical'] in strict_urls]
        engine_part = [c for c in chosen if c['canonical'] not in strict_urls]
        new_items = inspect_many(engine_part, query_sig, budget['workers'], progress)
        new_items += inspect_many(pivot_part, query_sig, budget['workers'],
                                  progress, strict=True)
        timeline.extend(new_items)
        before = first_seen['published_at'] if first_seen else None
        first_seen = assess(timeline)
        after = first_seen['published_at'] if first_seen else None
        rounds.append({'round': r, 'candidates': len(new_cands),
                       'inspected': len(chosen), 'first_seen': after,
                       'plan': (plan or {}).get('notes') if plan else None,
                       'improved': bool(after and (before is None or after < before))})
        if not rounds[-1]['improved']:
            break

    # ---- report
    if extra_frame_urls:
        video_consensus(timeline)
        first_seen = assess(timeline)
    kept = [i for i in timeline if i['visual']['verdict'] != 'rejected'
            and not i.get('dropped')]
    dated = sorted([i for i in kept if i['published_at']], key=_first_seen_key)
    undated = [i for i in kept if not i['published_at']]
    ordered = dated + undated

    stats = {
        'checked': len(timeline),
        'with_dates': len(dated),
        'visually_confirmed': sum(1 for i in timeline if i['visual']['verdict'] == 'confirmed'),
        'probable': sum(1 for i in timeline if i['visual']['verdict'] == 'probable'),
        'visually_rejected': sum(1 for i in timeline if i['visual']['verdict'] == 'rejected'),
        'ambiguous': sum(1 for i in timeline if i['visual']['verdict'] == 'ambiguous'),
        'elapsed_s': round(time.monotonic() - started, 1),
        'visual_verification': _has_embedding(query_sig),
        'frames': 1 + len(extra_frame_urls or []),
    }
    payload = {
        'success': True,
        'engine': 'origin_engine',
        'first_seen': _public_item(first_seen) if first_seen else None,
        'earlier_hints': [_public_item(i) for i in earlier_hints(timeline, first_seen)],
        'scenes': ([{'frame': f, 'first_seen': _public_item(i)}
                    for f, i in sorted(earliest_by_frame(timeline).items())]
                   if extra_frame_urls else []),
        'timeline': [_public_item(i) for i in ordered],
        'stats': stats,
        'engines': engines_status,
        'rounds': rounds,
        'narrative': None,
        'note': None if ordered else (
            'لم يُعثر على أي ظهور مؤكد للصورة في المحركات المفحوصة — قد تكون '
            'أصلية، من مصدر خاص، أو مولّدة بالذكاء الاصطناعي.'),
    }
    if ordered and time_left() > 10:
        progress('كتابة الملخص...')
        payload['narrative'] = _narrative(payload, llm_calls, budget)
    progress('اكتمل تحليل المصدر')
    return payload


def to_search_payload(report):
    """Shape an investigate_origin() report for /api/direct-search consumers.

    Timeline items keep the legacy fields the page already renders
    (title/link/type/date_found/source/thumbnail/snippet/timestamp) and gain
    the evidence fields (published_at/confidence/is_upper_bound/evidence/
    visual/providers/origin_round). first_seen, narrative, engines, stats and
    rounds ride alongside.
    """
    # Timeline reads as "origin, then the spread": weakly-dated / lower-bound
    # / listing pages that sort before first_seen are shown in earlier_hints
    # and moved to the end here so "الأول" is the first row.
    hint_urls = {h.get('url') for h in (report.get('earlier_hints') or [])}
    fs = report.get('first_seen') or {}
    cutoff = (fs.get('published_at') or '')[:10]

    def _before_origin(i):
        return (i.get('url') in hint_urls or
                (cutoff and (i.get('published_at') or '')[:10] < cutoff
                 and i.get('url') != fs.get('url')))
    items = report.get('timeline') or []
    items = [i for i in items if not _before_origin(i)] +             [i for i in items if _before_origin(i)]
    timeline = []
    for i in items:
        published = i.get('published_at')
        if published:
            date_found = published[:10]
            if i.get('is_upper_bound'):
                date_found = 'على الأقل منذ ' + date_found
            elif i.get('is_lower_bound'):
                date_found = 'ليس قبل ' + date_found
        else:
            date_found = 'بدون تاريخ'
        timeline.append({
            'title': i.get('title') or i.get('domain'),
            'link': i.get('url'),
            'snippet': None,
            'thumbnail': i.get('thumbnail'),
            'date_text': date_found,
            'date_found': date_found,
            'timestamp': published,
            'source': i.get('domain'),
            'type': i.get('match_type') or 'similar',
            'published_at': published,
            'confidence': i.get('confidence'),
            'is_upper_bound': bool(i.get('is_upper_bound')),
            'evidence': i.get('evidence') or [],
            'visual': i.get('visual') or {'verdict': 'unverified'},
            'providers': i.get('providers') or [],
            'captured_at': i.get('captured_at'),
            'origin_round': i.get('origin_round', 0),
        })
    return {
        'success': bool(report.get('success')),
        'engine': 'origin_engine',
        'timeline': timeline,
        'total': len(timeline),
        'first_seen': report.get('first_seen'),
        'narrative': report.get('narrative'),
        'engines': report.get('engines') or {},
        'stats': report.get('stats') or {},
        'rounds': report.get('rounds') or [],
        'note': report.get('note'),
        'agent': report.get('agent'),
        'earlier_hints': report.get('earlier_hints') or [],
        'scenes': report.get('scenes') or [],
        'raw': {},
    }


def _has_embedding(query_sig):
    sigs = query_sig if isinstance(query_sig, list) else [query_sig]
    return any(s and s.get('embedding') is not None for s in sigs)


def _empty(note):
    return {'success': False, 'engine': 'origin_engine', 'first_seen': None,
            'timeline': [], 'stats': {'checked': 0, 'with_dates': 0},
            'engines': {}, 'rounds': [], 'narrative': None, 'note': note,
            'error': note}
