"""Geometric verification: are two images the SAME photograph?

Perceptual hashes break on crops and re-framing; semantic embeddings score
look-alike scenes (another ship fire at dusk, another group of men in
thobes) as high as real copies. Local keypoints + a RANSAC homography are
the classical answer: the same photo — cropped, upscaled, AI-"restored",
outpainted, recoloured, watermarked, black-and-white — shares hundreds of
geometrically consistent keypoints; a different photo of a similar scene
shares a handful.

Calibration (2026-09-22, SIFT, 800 px, ratio test 0.75, RANSAC 5 px):
  same photo, AI-restored + widened ........ 251 inliers
  same photo, hard crop + B&W + overlays ... 107
  same photo vs its 200 px thumbnail ........ 88
  unrelated photos (5 pairs) ................ 5-15

Inlier counts alone are not enough (2026-09-29, production): a repeating
texture (a shemagh's weave) gave 37 "inliers" between two different photos of
one man. The fitted transform was degenerate: 37 points collapsed onto 5,
squeezed 35:1, covering 1% of the image. A real copy maps distinct points to
distinct points with a near-uniform scale (measured 1.00-1.01) over a fifth of
the picture or more, so the transform itself is checked (plausible()).
"""
import logging
import os

logger = logging.getLogger(__name__)

MAX_SIDE = 800
NFEATURES = 1500
RATIO_TEST = 0.75
RANSAC_PX = 5.0
MIN_INLIERS = int(os.environ.get('GEOM_MIN_INLIERS', '30'))
MIN_INLIER_RATIO = 0.6          # inliers / good matches
MIN_KEYPOINTS_TO_JUDGE = 150    # below this an image is too flat to say "different"
MIN_DISTINCT = 20               # inlier points that are really different points, on each side
MAX_ANISOTROPY = 2.5            # x-scale / y-scale of the transform (a stretched copy stays under 2)
MIN_COVER = 0.10                # share of one image the inliers must span (hull area)


def available():
    if os.environ.get('GEOMETRIC_VERIFY', 'true').lower() == 'false':
        return False
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def features(pil):
    """SIFT keypoints + descriptors of a PIL image (downscaled to MAX_SIDE).
    Returns {'pts': float32[N,2], 'desc': float32[N,128], 'n': N} or None."""
    if not available():
        return None
    try:
        import cv2
        import numpy as np
        gray = np.asarray(pil.convert('L'))
        h, w = gray.shape
        scale = MAX_SIDE / float(max(h, w))
        if scale < 1:
            gray = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))),
                              interpolation=cv2.INTER_AREA)
        kps, desc = cv2.SIFT_create(nfeatures=NFEATURES).detectAndCompute(gray, None)
        if desc is None or len(kps) < 8:
            return {'pts': None, 'desc': None, 'n': len(kps or [])}
        pts = np.float32([k.pt for k in kps])
        return {'pts': pts, 'desc': desc, 'n': len(kps), 'size': (gray.shape[1], gray.shape[0])}
    except Exception as e:
        logger.info('geometric features failed: %s', e)
        return None


def _cover(pts, size):
    """Share of the image area inside the convex hull of the points."""
    import cv2
    import numpy as np
    if len(pts) < 3:
        return 0.0
    if size:
        area = float(size[0] * size[1])
    else:
        area = float(pts[:, 0].max() * pts[:, 1].max())
    if area <= 0:
        return 0.0
    return float(cv2.contourArea(cv2.convexHull(np.float32(pts)))) / area


def plausible(H, src, dst, size_a=None, size_b=None):
    """Is the fitted transform one a copy of a photo can produce?
    Returns {'ok', 'distinct', 'anisotropy', 'cover', 'why'}."""
    import numpy as np
    out = {'ok': False, 'distinct': 0, 'anisotropy': None, 'cover': 0.0, 'why': None}
    if H is None or len(src) < 4:
        out['why'] = 'no transform'
        return out
    out['distinct'] = int(min(len(np.unique(np.round(src), axis=0)),
                              len(np.unique(np.round(dst), axis=0))))
    A = np.asarray(H, dtype='float64')[:2, :2]
    sv = np.linalg.svd(A, compute_uv=False)
    out['anisotropy'] = round(float(sv[0] / max(sv[1], 1e-9)), 2)
    out['cover'] = round(max(_cover(src, size_a), _cover(dst, size_b)), 3)
    if out['distinct'] < MIN_DISTINCT:
        out['why'] = 'points collapse'
    elif float(np.linalg.det(A)) <= 0:
        out['why'] = 'mirrored transform'
    elif out['anisotropy'] > MAX_ANISOTROPY:
        out['why'] = 'squeezed transform'
    elif out['cover'] < MIN_COVER:
        out['why'] = 'matches in one spot'
    else:
        out['ok'] = True
    return out


def match(fa, fb):
    """Compare two feature sets. Returns
    {'good', 'inliers', 'ratio', 'same_scene': bool|None, 'rejected': why|None}
    same_scene is None when either image is too flat to judge."""
    out = {'good': 0, 'inliers': 0, 'ratio': 0.0, 'same_scene': None, 'rejected': None}
    if not fa or not fb or fa.get('desc') is None or fb.get('desc') is None:
        return out
    try:
        import cv2
        import numpy as np
        knn = cv2.BFMatcher(cv2.NORM_L2).knnMatch(fa['desc'], fb['desc'], k=2)
        good = [p[0] for p in knn if len(p) == 2 and p[0].distance < RATIO_TEST * p[1].distance]
        out['good'] = len(good)
        judgeable = fa['n'] >= MIN_KEYPOINTS_TO_JUDGE and fb['n'] >= MIN_KEYPOINTS_TO_JUDGE
        if len(good) >= 8:
            src = np.float32([fa['pts'][g.queryIdx] for g in good])
            dst = np.float32([fb['pts'][g.trainIdx] for g in good])
            H, mask = cv2.findHomography(src, dst, cv2.RANSAC, RANSAC_PX)
            inl = int(mask.sum()) if mask is not None else 0
            out['inliers'] = inl
            out['ratio'] = round(inl / float(len(good)), 3)
            if inl >= MIN_INLIERS and out['ratio'] >= MIN_INLIER_RATIO:
                keep = mask.ravel().astype(bool)
                check = plausible(H, src[keep], dst[keep], fa.get('size'), fb.get('size'))
                if not check['ok']:
                    out['rejected'] = check['why']
                    out['same_scene'] = False
                    return out
        if out['inliers'] >= MIN_INLIERS and out['ratio'] >= MIN_INLIER_RATIO:
            out['same_scene'] = True
        elif judgeable:
            out['same_scene'] = False
        return out
    except Exception as e:
        logger.info('geometric match failed: %s', e)
        return out


def same_scene(sigs, pil):
    """Best geometric match between a candidate image and any query
    signature carrying features. Returns the match dict (same_scene may be
    None) — never raises."""
    best = {'good': 0, 'inliers': 0, 'ratio': 0.0, 'same_scene': None}
    feats = [s.get('geom') for s in sigs if s and s.get('geom')]
    if not feats:
        return best
    fb = features(pil)
    if not fb:
        return best
    for fa in feats:
        m = match(fa, fb)
        if m['inliers'] > best['inliers'] or (best['same_scene'] is None and m['same_scene'] is not None):
            best = m
        if best['same_scene']:
            break
    return best
