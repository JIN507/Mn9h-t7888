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
from services.visual_verify import (build_query_signature_from_url,
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

FIRST_SEEN_MIN_CONFIDENCE = 0.5


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


# ------------------------------------------------------------------ harvest

LENS_EXACT_RETRIES = 1
LENS_RETRY_DELAY_S = float(os.environ.get('LENS_RETRY_DELAY_S', '2'))


def _lens_exact_with_retry(image_url, hl, country):
    """Lens exact matches are the backbone of the harvest; SerpAPI has
    transient blips (connection resets, empty 200s). Retry once."""
    last_error = None
    for attempt in range(LENS_EXACT_RETRIES + 1):
        try:
            got = lens_matches(image_url, 'exact_matches', hl=hl, country=country)
            if got:
                return got
            logger.info('lens exact %s/%s empty (attempt %d)', hl, country, attempt + 1)
        except Exception as e:
            last_error = e
            logger.info('lens exact %s/%s failed (attempt %d): %s', hl, country,
                        attempt + 1, e)
        if attempt < LENS_EXACT_RETRIES:
            time.sleep(LENS_RETRY_DELAY_S)
    if last_error is not None:
        raise last_error
    return []


def _harvest(image_url, progress, engines_status, *, include_visual=True):
    """Run every candidate generator in parallel. Returns raw match dicts."""
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
    if not tineye_provider.configured():
        tasks.pop('tineye')
        engines_status['tineye'] = {'ok': False, 'count': 0,
                                    'note': 'not configured'}
    if not vision_provider.configured():
        tasks.pop('vision')
        engines_status['vision'] = {'ok': False, 'count': 0,
                                    'note': 'not configured'}

    matches = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as ex:
        futures = {ex.submit(fn): name for name, fn in tasks.items()}
        try:
            for fut in concurrent.futures.as_completed(futures, timeout=90):
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
                'crawl_date': None, 'is_image': is_image_url(canon),
            }
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


def prioritize(candidates, limit, per_domain):
    """Exact/TinEye/multi-engine first; cap per domain; cap total."""
    def score(c):
        s = MATCH_RANK.get(c['match_type'], 9) * 10
        s -= 4 * min(len(c['providers']), 3)          # corroborated by engines
        if c['crawl_date']:
            s -= 5                                    # TinEye dated it
        if any(h in c['domain'] for h in SOCIAL_HOSTS):
            s -= 2                                    # origins are often social
        if c['is_image']:
            s += 3                                    # bare files: weak pages
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
            out['title'] = _title_from_html(html, out['title'])
            out['snippet'] = _page_text_snippet(html)
            evidence.extend(de.html_date_evidence(html, url))
        else:
            out['fetch_error'] = True
        visual = verify_html(html, url, query_sig,
                             extra_image_urls=cand.get('engine_images') or [],
                             keep_bytes=True) if query_sig else {'verdict': 'unverified'}

    blob = visual.pop('matched_image_bytes', None)
    img_headers = visual.pop('matched_headers', None)
    size = visual.pop('matched_size', None)
    out['visual'] = {k: visual.get(k) for k in
                     ('verdict', 'match_kind', 'similarity', 'phash_distance',
                      'matched_image_url')}
    if size:
        out['image_size'] = list(size)
    if blob:
        out['captured_at'] = de.exif_capture_date(blob)
    if img_headers:
        evidence.extend(de.header_date_evidence(img_headers))
    if cand.get('is_image') and headers is None and img_headers is None:
        pass

    strong = any(e['confidence'] >= 0.9 for e in evidence)
    if use_wayback and not strong and out['visual']['verdict'] != 'rejected':
        wb = wayback_provider.earliest_capture(url)
        if wb:
            bounds.append({'date': wb, 'confidence': 0.6,
                           'source': 'wayback:first_capture'})

    resolved = de.resolve_published_at(evidence, bounds)
    out.update({k: resolved[k] for k in
                ('published_at', 'confidence', 'evidence', 'bound',
                 'is_upper_bound')})

    if strict and out['visual']['verdict'] != 'confirmed':
        out['dropped'] = 'text_pivot_unconfirmed'
    return out


def inspect_many(cands, query_sig, workers, progress, *, strict=False):
    results = []
    if not cands:
        return results
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(inspect_candidate, c, query_sig, strict=strict): c
                   for c in cands}
        done = 0
        try:
            for fut in concurrent.futures.as_completed(futures, timeout=150):
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
    return results


# ------------------------------------------------------------------- assess

def _eligible_first(item):
    v = item['visual']['verdict']
    if v == 'rejected' or item.get('dropped'):
        return False
    if not item['published_at'] or item['confidence'] < FIRST_SEEN_MIN_CONFIDENCE:
        return False
    if v == 'confirmed':
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


def assess(timeline):
    dated = [i for i in timeline if _eligible_first(i)]
    dated.sort(key=_first_seen_key)
    return dated[0] if dated else None


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
            'visual', 'captured_at', 'image_size', 'origin_round')
    item = {k: i.get(k) for k in keep}
    item['link'] = i['url']
    item['type'] = i['match_type']
    item['evidence'] = [{'source': e['source'], 'date': e['date'],
                         'confidence': e['confidence']} for e in (i.get('evidence') or [])[:5]]
    return item


# --------------------------------------------------------------------- main

def investigate_origin(image_url, *, progress=None, budget=None):
    """Full origin investigation for a hosted image URL. Never raises."""
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
    query_sig = build_query_signature_from_url(image_url)

    # ---- round 0: harvest + inspect
    progress('جاري البحث في المحركات (Lens, Vision, TinEye, Yandex)...')
    raw = _harvest(image_url, progress, engines_status)
    seen = set()
    cands = merge_candidates(raw, seen)
    seen.update(c['canonical'] for c in cands)
    chosen = prioritize(cands, budget['max_inspect'], budget['per_domain'])
    progress(f'{len(cands)} مرشحاً فريداً — فحص {len(chosen)} صفحة...')
    timeline = inspect_many(chosen, query_sig, budget['workers'], progress)
    first_seen = assess(timeline)
    rounds.append({'round': 0, 'candidates': len(cands), 'inspected': len(chosen),
                   'first_seen': first_seen['published_at'] if first_seen else None})

    # ---- expansion rounds
    for r in range(1, budget['max_rounds'] + 1):
        if time_left() < 30:
            break
        new_cands = []
        if r == 1:
            new_cands += _lens_pivot(first_seen, timeline, image_url, seen,
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
    kept = [i for i in timeline if i['visual']['verdict'] != 'rejected'
            and not i.get('dropped')]
    dated = sorted([i for i in kept if i['published_at']], key=_first_seen_key)
    undated = [i for i in kept if not i['published_at']]
    ordered = dated + undated

    stats = {
        'checked': len(timeline),
        'with_dates': len(dated),
        'visually_confirmed': sum(1 for i in timeline if i['visual']['verdict'] == 'confirmed'),
        'visually_rejected': sum(1 for i in timeline if i['visual']['verdict'] == 'rejected'),
        'ambiguous': sum(1 for i in timeline if i['visual']['verdict'] == 'ambiguous'),
        'elapsed_s': round(time.monotonic() - started, 1),
        'visual_verification': bool(query_sig and query_sig.get('embedding') is not None),
    }
    payload = {
        'success': True,
        'engine': 'origin_engine',
        'first_seen': _public_item(first_seen) if first_seen else None,
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
    timeline = []
    for i in report.get('timeline') or []:
        published = i.get('published_at')
        if published:
            date_found = published[:10]
            if i.get('is_upper_bound'):
                date_found = 'على الأقل منذ ' + date_found
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
        'raw': {},
    }


def _empty(note):
    return {'success': False, 'engine': 'origin_engine', 'first_seen': None,
            'timeline': [], 'stats': {'checked': 0, 'with_dates': 0},
            'engines': {}, 'rounds': [], 'narrative': None, 'note': note,
            'error': note}
