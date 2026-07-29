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
from urllib.parse import urljoin, urlparse

import requests

from services.embedding_service import (embed_image, cosine_similarity,
                                        encoder_available,
                                        visual_verify_enabled)

logger = logging.getLogger(__name__)

PHASH_SAME_MAX_DISTANCE = 8
SIM_CONFIRM = 0.90
SIM_AMBIGUOUS = 0.75
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

    sig = {
        'phash': imagehash.phash(pil),
        'dhash': imagehash.dhash(pil),
        'embedding': embed_image(pil) if encoder_available() else None,
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

def fetch_and_verify(url, query_sig, max_images=3, timeout=(5, 10)):
    """Verify that `url`'s page actually shows the query image."""
    import io
    from PIL import Image

    out = {'url': url, 'verdict': 'error', 'match_kind': None,
           'similarity': None, 'phash_distance': None,
           'matched_image_url': None, 'checked_images': 0}

    try:
        page = requests.get(url, headers=UA, timeout=timeout)
        page.raise_for_status()
    except Exception as e:
        logger.info('fetch_and_verify: page fetch failed for %s: %s', url, e)
        return out

    candidates = extract_candidate_images(page.text, url)[:max_images]
    if not candidates:
        out['verdict'] = 'no_image'
        return out

    best_sim = None
    best_dist = None
    best_url = None

    for img_url in candidates:
        try:
            r = requests.get(img_url, headers=UA, timeout=timeout, stream=True)
            r.raise_for_status()
            data = r.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
            if len(data) > MAX_IMAGE_BYTES:
                continue
            pil = Image.open(io.BytesIO(data)).convert('RGB')
        except Exception:
            continue

        out['checked_images'] += 1

        distance = _hash_distance(query_sig, pil)
        if distance is not None and (best_dist is None or distance < best_dist):
            best_dist = distance
            if distance <= PHASH_SAME_MAX_DISTANCE:
                out.update(verdict='confirmed', match_kind='exact',
                           phash_distance=distance, matched_image_url=img_url)
                return out

        if query_sig.get('embedding') is not None:
            sim = cosine_similarity(query_sig['embedding'], embed_image(pil))
            if sim is not None and (best_sim is None or sim > best_sim):
                best_sim = sim
                best_url = img_url

    out['phash_distance'] = best_dist
    if best_sim is not None:
        out['similarity'] = round(best_sim, 4)
        out['matched_image_url'] = best_url
        if best_sim >= SIM_CONFIRM:
            out.update(verdict='confirmed', match_kind='variant')
        elif best_sim >= SIM_AMBIGUOUS:
            out['verdict'] = 'ambiguous'
        else:
            out['verdict'] = 'rejected'
    else:
        # pHash didn't confirm and no encoder — don't silently drop results
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
