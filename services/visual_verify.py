"""Tier-1 visual verification: confirm a candidate page actually shows the
query image before it enters any timeline (VISUAL_VERIFICATION_ENGINE.md §2).

fetch_and_verify(url, query_sig):
  page fetch -> extract og:image / JSON-LD / large <img> -> download top few
  -> pHash+dHash vs query (Hamming <= 8 => same image, near certainty)
  -> else DINOv2 embedding cosine:
       >= 0.90        confirmed (variant)
       0.75 - 0.90    ambiguous (Tier-2 VLM escalation later)
       <  0.75        rejected  (where today's unrelated results die)

Verification is per-page, not per-thumbnail — the check search engines
never do.
"""
import concurrent.futures
import json
import logging
import re
from urllib.parse import urljoin, urlparse

import requests

from services.embedding_service import (embed_image, cosine_similarity,
                                        encoder_available,
                                        visual_verify_enabled)

logger = logging.getLogger(__name__)

PHASH_SAME_MAX_DISTANCE = 8
SIM_CONFIRM = 0.90
SIM_AMBIGUOUS = 0.75
GEOM_MIN_SIM = 0.55      # run geometry on candidates at least this similar (or hash-close)
GEOM_MAX_PHASH = 26
PAGE_CHECKS_AFTER_ENGINE_HIT = 3   # page images compared after an engine-thumbnail hash hit
MAX_IMAGE_BYTES = 8 * 1024 * 1024
UA = {'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                     'AppleWebKit/537.36 (KHTML, like Gecko) '
                     'Chrome/120.0 Safari/537.36')}


# ------------------------------------------------------------- signatures

def build_query_signature(image):
    """image: bytes | path | PIL -> {'phash','dhash','embedding'} or None."""
    import io
    import imagehash
    from PIL import Image

    try:
        if isinstance(image, (bytes, bytearray)):
            pil = Image.open(io.BytesIO(image)).convert('RGB')
        elif isinstance(image, Image.Image):
            pil = image.convert('RGB')
        else:
            pil = Image.open(image).convert('RGB')
    except Exception as e:
        logger.warning('Cannot open query image: %s', e)
        return None

    from services import geometric_verify
    sig = {
        'phash': imagehash.phash(pil),
        'dhash': imagehash.dhash(pil),
        'embedding': embed_image(pil) if encoder_available() else None,
        'geom': geometric_verify.features(pil),
        'size': pil.size,
    }
    return sig


def build_query_signature_from_url(image_url, timeout=(5, 15)):
    """Download the query image (e.g. its R2 presigned URL) and sign it."""
    try:
        r = requests.get(image_url, headers=UA, timeout=timeout)
        r.raise_for_status()
        return build_query_signature(r.content)
    except Exception as e:
        logger.warning('Cannot download query image: %s', e)
        return None


def _hash_distance(sig, pil):
    import imagehash
    try:
        d_p = sig['phash'] - imagehash.phash(pil)
        d_d = sig['dhash'] - imagehash.dhash(pil)
        # imagehash returns numpy ints — cast, or json.dumps chokes downstream
        return int(min(d_p, d_d))
    except Exception:
        return None


# ------------------------------------------------------- candidate images

_YT_ID = re.compile(r'(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})')


_IG_CODE = re.compile(r'instagram\.com/(?:[A-Za-z0-9_.]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]{9,12})')


def platform_image_urls(page_url):
    """Direct image URLs a platform exposes for a post even when the page
    itself hides them from us. Instagram: the /media/ redirect. X/Twitter:
    the post's photos at full resolution via the syndication endpoint."""
    m = _IG_CODE.search(page_url or '')
    if m:
        return [f'https://www.instagram.com/p/{m.group(1)}/media/?size=l']
    from providers import tweet
    if tweet.status_id(page_url or ''):
        info = tweet.tweet_info(page_url)
        if info and info.get('photos'):
            return list(info['photos'])[:4]
    return []


def video_frame_urls(page_url):
    """Free extra frames for video candidates: YouTube's storyboard
    thumbnails (0 = poster, 1/2/3 = 25/50/75%)."""
    m = _YT_ID.search(page_url or '')
    if not m:
        return []
    vid = m.group(1)
    return [f'https://i.ytimg.com/vi/{vid}/maxresdefault.jpg',
            f'https://i.ytimg.com/vi/{vid}/hq1.jpg',
            f'https://i.ytimg.com/vi/{vid}/hq2.jpg',
            f'https://i.ytimg.com/vi/{vid}/hq3.jpg']


def extract_candidate_images(html, base_url):
    """Meaningful image URLs from a page: og/twitter meta, JSON-LD, then
    <img> tags above a size floor. Ordered by priority, deduplicated."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, 'html.parser')
    found = []

    def add(url):
        if not url or url.startswith('data:'):
            return
        absolute = urljoin(base_url, url.strip())
        if not absolute.startswith('http'):
            return
        if urlparse(absolute).path.lower().endswith('.svg'):
            return
        if absolute not in found:
            found.append(absolute)

    # 1. Social meta tags — the page's own statement of its main image
    for prop in ('og:image', 'og:image:url', 'twitter:image',
                 'twitter:image:src'):
        for tag in soup.find_all('meta', attrs={'property': prop}) + \
                soup.find_all('meta', attrs={'name': prop}):
            add(tag.get('content'))

    # 2. JSON-LD "image"
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '')
        except Exception:
            continue
        for item in (data if isinstance(data, list) else [data]):
            if not isinstance(item, dict):
                continue
            image = item.get('image')
            for value in (image if isinstance(image, list) else [image]):
                if isinstance(value, str):
                    add(value)
                elif isinstance(value, dict):
                    add(value.get('url'))

    # 3. <img> tags above the size floor (when size attributes exist)
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-original')
        try:
            w = int(str(img.get('width', '')).rstrip('px') or 0)
            h = int(str(img.get('height', '')).rstrip('px') or 0)
        except ValueError:
            w = h = 0
        if (w and w < 100) or (h and h < 100):
            continue  # declared tiny — sidebar/icon
        add(src)

    return found


# ---------------------------------------------------------- verification

def fetch_page(url, timeout=(5, 10)):
    """GET a candidate page. Returns the Response or None (never raises)."""
    try:
        page = requests.get(url, headers=UA, timeout=timeout)
        page.raise_for_status()
        return page
    except Exception as e:
        logger.info('fetch_page failed for %s: %s', url, e)
        return None


def fetch_and_verify(url, query_sig, max_images=3, timeout=(5, 10)):
    """Verify that `url`'s page actually shows the query image."""
    page = fetch_page(url, timeout=timeout)
    if page is None:
        return {'url': url, 'verdict': 'error', 'match_kind': None,
                'similarity': None, 'phash_distance': None,
                'matched_image_url': None, 'checked_images': 0}
    return verify_html(page.text, url, query_sig, max_images=max_images,
                       timeout=timeout)


def verify_html(html, url, query_sig, max_images=3, timeout=(5, 10),
                extra_image_urls=None, keep_bytes=False):
    """Verify against an already-fetched page body.

    extra_image_urls: engine-reported image URLs for this page (TinEye /
    Vision) checked first — they are the engine's own pointer to the match.
    keep_bytes: also return the matched image bytes + headers (for EXIF /
    Last-Modified evidence) under 'matched_image_bytes'/'matched_headers'.
    """
    import io
    from PIL import Image

    out = {'url': url, 'verdict': 'error', 'match_kind': None,
           'similarity': None, 'phash_distance': None,
           'matched_image_url': None, 'checked_images': 0}

    # Video mode: several query frames — a page showing ANY of them counts.
    sigs = [s for s in (query_sig if isinstance(query_sig, list) else [query_sig]) if s]
    if not sigs:
        out['verdict'] = 'unverified'
        return out
    query_embeddings = [s['embedding'] for s in sigs if s.get('embedding') is not None]

    candidates = []
    engine_given = set()
    for extra in extra_image_urls or []:
        if extra and extra.startswith('http') and extra not in candidates:
            candidates.append(extra)
            engine_given.add(extra)
    for found in extract_candidate_images(html or '', url):
        if found not in candidates:
            candidates.append(found)
    platform = platform_image_urls(url)
    frames = video_frame_urls(url)
    for f in reversed(platform):          # the platform's own media first
        if f not in candidates:
            candidates.insert(0, f)
    for f in frames:
        if f not in candidates:
            candidates.append(f)
    candidates = candidates[:max_images + len(extra_image_urls or []) + len(frames) + len(platform)]
    if not candidates:
        out['verdict'] = 'no_image'
        return out

    best_sim = None
    best_dist = None
    best_url = None
    best_blob = None
    best_geom = None
    engine_claim = None          # an engine thumbnail matched (hash or geometry): a claim
    page_checked = 0
    page_rejected = 0
    from services import geometric_verify

    def _hit(kind, img_url, pil, data, headers, from_engine, distance, sim, geom):
        h = dict(verdict='confirmed', match_kind=kind, phash_distance=distance,
                 similarity=round(sim, 4) if sim is not None else None,
                 matched_image_url=img_url, matched_size=pil.size,
                 matched_from='engine' if from_engine else 'page')
        if geom is not None:
            h['geometry'] = {k: geom.get(k) for k in ('inliers', 'good', 'ratio', 'same_scene')}
        if keep_bytes:
            h['matched_image_bytes'] = data
            h['matched_headers'] = dict(headers)
        return h

    for img_url in candidates:
        from_engine = img_url in engine_given
        if engine_claim is not None and not from_engine and page_checked >= PAGE_CHECKS_AFTER_ENGINE_HIT:
            break
        try:
            headers = UA
            if ('instagram.com' in img_url and '/media' in img_url) or 'lookaside.fbsbx.com' in img_url:
                from services.date_evidence import CRAWLER_UA
                headers = CRAWLER_UA
            r = requests.get(img_url, headers=headers, timeout=timeout, stream=True)
            r.raise_for_status()
            data = r.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
            if len(data) > MAX_IMAGE_BYTES:
                continue
            pil = Image.open(io.BytesIO(data)).convert('RGB')
        except Exception:
            continue

        out['checked_images'] += 1
        if not from_engine:
            page_checked += 1

        distances = [d for d in (_hash_distance(s, pil) for s in sigs) if d is not None]
        distance = min(distances) if distances else None
        if distance is not None and (best_dist is None or distance < best_dist):
            best_dist = distance
        if distance is not None and distance <= PHASH_SAME_MAX_DISTANCE:
            hit = _hit('exact', img_url, pil, data, r.headers, from_engine, distance, None, None)
            if not from_engine:
                out.update(hit)
                return out               # the page itself shows the image
            if engine_claim is None:
                engine_claim = hit       # remember the claim, look at the page's own images
            continue

        sim = None
        if query_embeddings:
            cand_emb = embed_image(pil)
            sims = [x for x in (cosine_similarity(q, cand_emb) for q in query_embeddings)
                    if x is not None]
            sim = max(sims) if sims else None
            if sim is not None and (best_sim is None or sim > best_sim):
                best_sim = sim
                if not (best_geom or {}).get('same_scene'):   # a geometric match is never overwritten
                    best_url = img_url
                    best_blob = (data, dict(r.headers), pil.size)

        # Geometry decides the grey zone: a re-framed / restored / cropped
        # copy confirms on keypoints, a look-alike scene does not.
        worth_geometry = ((sim is not None and sim >= GEOM_MIN_SIM)
                          or (sim is None and distance is not None and distance <= GEOM_MAX_PHASH)
                          or (engine_claim is not None and not from_engine))   # page must confirm the claim
        page_must_confirm = engine_claim is not None and not from_engine
        if worth_geometry and (page_must_confirm or not (best_geom or {}).get('same_scene')):
            g = geometric_verify.same_scene(sigs, pil)
            if best_geom is None or g['inliers'] > best_geom['inliers'] or g['same_scene']:
                best_geom = dict(g, image_url=img_url)
            if g['same_scene']:
                hit = _hit('variant', img_url, pil, data, r.headers, from_engine, distance, sim, g)
                if not from_engine:
                    out.update(hit)
                    return out           # the page itself shows the image
                if engine_claim is None:
                    engine_claim = hit
                continue
            if not from_engine and g['same_scene'] is False:
                page_rejected += 1

    out['phash_distance'] = best_dist
    geom_no = (best_geom or {}).get('same_scene') is False
    if best_geom is not None:
        out['geometry'] = {k: best_geom.get(k) for k in ('inliers', 'good', 'ratio', 'same_scene')}
    if engine_claim is not None:
        # Only the engine's thumbnail matched. Page images that geometry
        # rejects contradict it; unverifiable pages keep the engine claim.
        out.update(engine_claim)
        if page_checked and page_rejected == page_checked:
            out.update(verdict='ambiguous', match_kind=None,
                       note='engine thumbnail matches, the page\'s own images do not')
        return out
    if best_sim is not None:
        out['similarity'] = round(best_sim, 4)
        out['matched_image_url'] = best_url
        if best_blob is not None:
            out['matched_size'] = best_blob[2]
            out['matched_from'] = 'engine' if best_url in engine_given else 'page'
            if keep_bytes:
                out['matched_image_bytes'] = best_blob[0]
                out['matched_headers'] = best_blob[1]
        if best_sim >= SIM_CONFIRM:
            if geom_no:
                out.update(verdict='ambiguous', match_kind=None,
                           note='embedding agrees, geometry does not (look-alike scene?)')
            else:
                out.update(verdict='confirmed', match_kind='variant')
        elif best_sim >= SIM_AMBIGUOUS:
            out['verdict'] = 'rejected' if geom_no else 'ambiguous'
        else:
            out['verdict'] = 'rejected'
    else:
        # pHash didn't confirm and no encoder — don't silently drop results
        # (a negative geometry alone is not enough to reject without an encoder)
        out['verdict'] = 'unverified'
    return out

def apply_visual_post_filter(items, query_image_url, url_field='link',
                             max_pages=8, max_workers=4):
    """Tier-1 post-filter over existing search/provenance results.

    Annotates each item with item['visual'] and DROPS 'rejected' ones.
    Returns (surviving_items, summary_dict). Never raises; on any setup
    failure the items pass through unchanged.
    """
    summary = {'enabled': True, 'checked': 0, 'rejected': 0,
               'confirmed': 0, 'ambiguous': 0}

    query_sig = build_query_signature_from_url(query_image_url)
    if query_sig is None:
        summary['enabled'] = False
        summary['note'] = 'query image unavailable'
        return items, summary

    to_verify = [i for i in items if i.get(url_field)][:max_pages]
    passthrough = items[len(to_verify):] if len(items) > len(to_verify) else []

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch_and_verify, item[url_field], query_sig): item
                   for item in to_verify}
        for future in concurrent.futures.as_completed(futures, timeout=120):
            item = futures[future]
            try:
                results[id(item)] = future.result()
            except Exception as e:
                results[id(item)] = {'verdict': 'error', 'url': item[url_field],
                                     'error': str(e)[:100]}

    surviving = []
    for item in to_verify:
        verdict_info = results.get(id(item), {'verdict': 'error'})
        item = dict(item)
        item['visual'] = {k: verdict_info.get(k) for k in
                          ('verdict', 'match_kind', 'similarity',
                           'phash_distance')}
        summary['checked'] += 1
        verdict = verdict_info.get('verdict')
        if verdict == 'rejected':
            summary['rejected'] += 1
            continue  # this is where the unrelated results die
        if verdict == 'confirmed':
            summary['confirmed'] += 1
        elif verdict == 'ambiguous':
            summary['ambiguous'] += 1
        surviving.append(item)

    return surviving + list(passthrough), summary
