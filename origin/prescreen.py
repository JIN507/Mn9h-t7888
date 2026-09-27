"""Thumbnail pre-screen: which candidates deserve a page fetch.

Engines return hundreds of rows; the page budget covers a few dozen. Each
row's engine thumbnail is compared to the query (hash, then keypoint
geometry) in parallel — no credits, ~10 s for 150 rows. Rows whose
thumbnail is the photo go first; rows whose thumbnail is clearly another
picture go last. A thumbnail match is a RANKING signal only: the page must
still confirm (origin/verify.py).
"""
import concurrent.futures
import io
import logging

import requests

from services import geometric_verify
from services.visual_verify import UA, MAX_IMAGE_BYTES, _hash_distance

logger = logging.getLogger(__name__)

WORKERS = 16
TIMEOUT = (3, 6)
MAX_ROWS = 150
PHASH_MATCH = 12


def _fetch(url):
    from PIL import Image
    r = requests.get(url, headers=UA, timeout=TIMEOUT, stream=True)
    r.raise_for_status()
    data = r.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
    if len(data) > MAX_IMAGE_BYTES:
        return None
    return Image.open(io.BytesIO(data)).convert('RGB')


def _score(cand, sigs):
    for url in (cand.get('thumbs') or [])[:2]:
        try:
            pil = _fetch(url)
        except Exception:
            continue
        if pil is None:
            continue
        dists = [d for d in (_hash_distance(s, pil) for s in sigs) if d is not None]
        dist = min(dists) if dists else None
        if dist is not None and dist <= PHASH_MATCH:
            return 'match', dist, None
        g = geometric_verify.same_scene(sigs, pil)
        if g.get('same_scene'):
            return 'match', dist, g.get('inliers')
        if g.get('same_scene') is False:
            return 'differs', dist, g.get('inliers')
        return 'unknown', dist, None
    return 'unknown', None, None


def run(cands, sigs, time_left_s=30, progress=None):
    """Sets cand['thumb_check'] = {'verdict': match|differs|unknown, 'phash', 'inliers'}
    on the first MAX_ROWS candidates with thumbnails. Returns counts."""
    todo = [c for c in cands[:MAX_ROWS] if c.get('thumbs')]
    for c in cands:
        c.setdefault('thumb_check', {'verdict': 'unknown', 'phash': None, 'inliers': None})
    if not todo or not sigs or time_left_s < 8:
        return {'match': 0, 'differs': 0, 'unknown': len(cands)}
    if progress:
        progress(f'فرز {len(todo)} مرشحاً عبر المصغّرات...')
    counts = {'match': 0, 'differs': 0, 'unknown': 0}
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(WORKERS, len(todo)))
    futures = {ex.submit(_score, c, sigs): c for c in todo}
    try:
        for fut in concurrent.futures.as_completed(futures, timeout=min(45, max(8, time_left_s - 5))):
            c = futures[fut]
            try:
                verdict, dist, inl = fut.result()
            except Exception:
                verdict, dist, inl = 'unknown', None, None
            c['thumb_check'] = {'verdict': verdict, 'phash': dist, 'inliers': inl}
            counts[verdict] = counts.get(verdict, 0) + 1
    except concurrent.futures.TimeoutError:
        pass
    finally:
        ex.shutdown(wait=False)
    counts['unknown'] += sum(1 for c in cands if c['thumb_check']['verdict'] == 'unknown') - counts.get('unknown', 0)
    return counts
