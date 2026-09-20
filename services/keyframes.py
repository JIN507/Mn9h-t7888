"""Keyframe selection for video provenance.

A video's origin search needs a handful of frames that are (a) not black,
blurry or near-duplicate and (b) as visually different from each other as
possible, so that a candidate page showing ANY moment of the clip can be
matched. Greedy max-min selection on perceptual hashes does that cheaply.
"""
import io
import logging

logger = logging.getLogger(__name__)

MIN_STD = 12.0          # grey-level std below this = black/flat frame
MIN_SHARPNESS = 25.0    # Laplacian variance below this = blur/transition


def _frame_features(data):
    """(phash, std, sharpness) for one JPEG/PNG frame, or None."""
    import imagehash
    from PIL import Image, ImageFilter, ImageStat
    try:
        pil = Image.open(io.BytesIO(data)).convert('RGB')
    except Exception:
        return None
    grey = pil.convert('L').resize((160, 90))
    std = ImageStat.Stat(grey).stddev[0]
    edges = grey.filter(ImageFilter.FIND_EDGES)
    sharp = ImageStat.Stat(edges).var[0]
    return imagehash.phash(pil), std, sharp


def select_keyframes(frames, k=4):
    """frames: list of image bytes. Returns indices of up to k distinct,
    usable frames — the first pick is the sharpest frame in the middle
    third of the clip (titles/black leaders live at the ends)."""
    feats = []
    for i, data in enumerate(frames):
        f = _frame_features(data)
        if f is None:
            continue
        ph, std, sharp = f
        if std < MIN_STD or sharp < MIN_SHARPNESS:
            continue
        feats.append((i, ph, sharp))
    if not feats:
        return list(range(min(k, len(frames))))

    n = len(frames)
    middle = [f for f in feats if n // 3 <= f[0] <= 2 * n // 3] or feats
    first = max(middle, key=lambda f: f[2])
    chosen = [first]
    while len(chosen) < k and len(chosen) < len(feats):
        best, best_gap = None, -1
        for f in feats:
            if any(f[0] == c[0] for c in chosen):
                continue
            gap = min(f[1] - c[1] for c in chosen)     # hamming distance
            if gap > best_gap:
                best, best_gap = f, gap
        if best is None or best_gap < 6:                # near-duplicate of a pick
            break
        chosen.append(best)
    return sorted(c[0] for c in chosen)
