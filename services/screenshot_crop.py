"""Screenshot -> the photo inside it.

Many queries are phone screenshots of a post (app chrome, caption, white
bands). Exact-match engines index the PHOTO, never the composite, so they
return nothing. An analyst crops first; this does the same automatically:
the photo is the largest contiguous band of rows (then columns) with real
image variance, framed by flat UI areas.
"""
import io
import logging

logger = logging.getLogger(__name__)

MIN_AREA_FRACTION = 0.12     # crop must cover at least this much of the screenshot
MAX_AREA_FRACTION = 0.92     # ...and less than this (otherwise it IS the photo)
FLAT_STD = 6.0               # grey std across a row/col: below = flat UI band (white/black)
MIN_BAND_PX = 120
MIN_FLAT_FRACTION = 0.05     # a real UI band next to the photo: >= 5% of the side


def _runs(mask):
    """Contiguous True runs as (start, end) pairs."""
    runs, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def _smooth(a, k=9):
    import numpy as np
    if len(a) < k:
        return a
    kernel = np.ones(k) / k
    return np.convolve(a, kernel, mode='same')


def detect_photo_region(image_bytes):
    """Return (left, top, right, bottom) of the embedded photo, or None when
    the image does not look like a screenshot with a dominant photo band."""
    try:
        import numpy as np
        from PIL import Image
        pil = Image.open(io.BytesIO(image_bytes)).convert('L')
    except Exception:
        return None
    w, h = pil.size
    if w < 200 or h < 200:
        return None
    arr = np.asarray(pil, dtype=np.float32)

    row_std = _smooth(arr.std(axis=1))
    flat_rows = row_std < FLAT_STD
    rows = [(a, b) for a, b in _runs(~flat_rows) if b - a >= MIN_BAND_PX]
    if not rows:
        return None
    top, bottom = max(rows, key=lambda r: r[1] - r[0])
    # a screenshot has a genuinely flat UI band above or below the photo
    flat_above = flat_rows[:top].sum() if top > 0 else 0
    flat_below = flat_rows[bottom:].sum() if bottom < h else 0
    if max(flat_above, flat_below) < MIN_FLAT_FRACTION * h:
        return None

    band = arr[top:bottom]
    col_std = _smooth(band.std(axis=0))
    cols = [(a, b) for a, b in _runs(col_std >= FLAT_STD) if b - a >= MIN_BAND_PX]
    if not cols:
        return None
    left, right = max(cols, key=lambda c: c[1] - c[0])

    area = (right - left) * (bottom - top) / float(w * h)
    if area < MIN_AREA_FRACTION or area > MAX_AREA_FRACTION:
        return None
    # trim a hair so UI borders / rounded corners do not enter the crop
    pad = 2
    return (left + pad, top + pad, max(left + pad + 1, right - pad), max(top + pad + 1, bottom - pad))


def crop_photo(image_bytes, quality=92):
    """Bytes of the embedded photo as JPEG, plus the box; (None, None) when
    no crop is warranted."""
    box = detect_photo_region(image_bytes)
    if not box:
        return None, None
    try:
        from PIL import Image
        pil = Image.open(io.BytesIO(image_bytes)).convert('RGB').crop(box)
        buf = io.BytesIO()
        pil.save(buf, format='JPEG', quality=quality)
        logger.info('screenshot crop: box=%s size=%s', box, pil.size)
        return buf.getvalue(), box
    except Exception as e:
        logger.info('screenshot crop failed: %s', e)
        return None, None
