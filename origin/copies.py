"""The copy set: every distinct version of the photo we can search with.

Copy #1 is the upload (or the photo cropped out of a post screenshot). A
downscaled re-encoded copy is added at once because Google's fetcher
refuses some files (AI-processed images) but accepts a 512 px re-encode.
Every full-size image later seen on a verified page or obtained from a
platform's media endpoint joins the set. Copies are deduplicated by
perceptual hash so CDN size variants do not trigger repeated searches.
"""
import io
import logging
import os
import threading
from dataclasses import dataclass, field
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

SMALL_COPY_PX = int(os.environ.get('LENS_SMALL_COPY_PX', '512'))
DEDUPE_PHASH = 4
MIN_COPY_PX = 400          # smaller images are thumbnails, not copies worth searching


@dataclass
class Copy:
    id: int
    url: str                      # public URL engines can fetch
    phash: object                 # imagehash.ImageHash
    width: int
    height: int
    source: str                   # upload | small | screenshot | page | platform
    found_on: str = None          # page URL the copy came from
    searched: set = field(default_factory=set)   # engine names already run on it

    @property
    def area(self):
        return self.width * self.height

    def brief(self):
        return {'id': self.id, 'url': self.url, 'size': [self.width, self.height],
                'source': self.source, 'found_on': self.found_on,
                'searched': sorted(self.searched)}


class CopySet:
    def __init__(self):
        self.copies = []
        self._lock = threading.Lock()

    def add(self, url, pil, source, found_on=None):
        """Add a copy (needs its PIL image for the hash). Returns the Copy,
        or the existing duplicate. None when unusable."""
        import imagehash
        if not url or pil is None:
            return None
        try:
            ph = imagehash.phash(pil.convert('RGB'))
        except Exception:
            return None
        w, h = pil.size
        with self._lock:
            for c in self.copies:
                if c.phash - ph <= DEDUPE_PHASH:
                    if c.source in ('upload', 'small', 'screenshot') and source in ('page', 'platform'):
                        continue      # a page's own file is worth searching even if it hashes like the upload
                    # keep the larger URL for the same picture
                    if w * h > c.area and source in ('page', 'platform') and c.source in ('page', 'platform'):
                        c.url, c.width, c.height, c.found_on = url, w, h, found_on
                    return c
            c = Copy(len(self.copies) + 1, url, ph, w, h, source, found_on)
            self.copies.append(c)
            return c

    def unsearched(self, engine, limit=None, prefer=('twimg.com',)):
        """Copies not yet searched on `engine`, largest first, preferred
        hosts (a platform's own media = the poster's file) ahead."""
        with self._lock:
            pool = [c for c in self.copies if engine not in c.searched
                    and (min(c.width, c.height) >= MIN_COPY_PX
                         or c.source in ('upload', 'small', 'screenshot'))]
        pool.sort(key=lambda c: (0 if any(p in urlsplit(c.url).hostname or '' for p in prefer) else 1, -c.area))
        return pool[:limit] if limit else pool

    def mark(self, copy, engine):
        with self._lock:
            copy.searched.add(engine)

    def by_id(self, cid):
        return next((c for c in self.copies if c.id == cid), None)

    def briefs(self):
        return [c.brief() for c in self.copies]


# ------------------------------------------------------------- hosting

def public_url_for_hosted(hosted_url):
    """A plain public URL for an object our storage returned (presigned R2
    link -> R2 public base / app media route). Falls back to the input."""
    try:
        from providers import storage
        key = storage.key_from_presigned_url(hosted_url)
        if key:
            base = os.environ.get('R2_PUBLIC_BASE_URL', '').rstrip('/')
            if base:
                return f'{base}/{key}'
            via_app = storage.public_media_url(key)
            if via_app:
                return via_app
    except Exception as e:
        logger.debug('public url mapping failed: %s', e)
    return hosted_url


def host_bytes(data, hint='copy'):
    """Host bytes and return a plain public URL, or None."""
    try:
        from services.storage_service import host_image
        hosted = host_image(data, filename_hint=hint)
        if hosted:
            pub = public_url_for_hosted(hosted)
            if pub and not urlsplit(pub).query:
                return pub
        if os.environ.get('IMGBB_API_KEY'):
            from providers.imgbb import upload_to_imgbb
            u = upload_to_imgbb(data, expiration=3600)
            if u and u.startswith('http'):
                return u
        return hosted
    except Exception as e:
        logger.info('hosting failed: %s', e)
        return None


def small_copy_bytes(image_bytes, max_px=None):
    """Downscaled, freshly encoded JPEG (metadata dropped); None if already small."""
    max_px = max_px or SMALL_COPY_PX
    try:
        from PIL import Image
        pil = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        if max(pil.size) <= max_px:
            return None
        pil.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        pil.save(buf, format='JPEG', quality=88)
        return buf.getvalue()
    except Exception as e:
        logger.info('small copy failed: %s', e)
        return None


def prepare(image_bytes, image_url):
    """Build the initial copy set from the upload.
    Returns (copyset, primary_pil, extras) where extras = {'screenshot': bool,
    'crop_box': [...]|None}."""
    from PIL import Image
    cs = CopySet()
    extras = {'screenshot': False, 'crop_box': None}
    try:
        pil = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    except Exception:
        return cs, None, extras

    primary_bytes, primary_url, primary_pil = image_bytes, public_url_for_hosted(image_url), pil
    if os.environ.get('SCREENSHOT_CROP', 'true').lower() != 'false':
        try:
            from services.screenshot_crop import crop_photo
            crop, box = crop_photo(image_bytes)
            if crop:
                crop_url = host_bytes(crop, 'crop')
                if crop_url:
                    extras.update(screenshot=True, crop_box=list(box))
                    cs.add(primary_url, pil, 'screenshot')
                    primary_bytes, primary_url = crop, crop_url
                    primary_pil = Image.open(io.BytesIO(crop)).convert('RGB')
        except Exception as e:
            logger.info('screenshot crop skipped: %s', e)
    if primary_url and urlsplit(primary_url).query:
        # presigned link (no public base configured): host a clean copy
        alt = host_bytes(primary_bytes, 'query')
        if alt:
            primary_url = alt
    cs.add(primary_url, primary_pil, 'upload')

    small = small_copy_bytes(primary_bytes)
    if small:
        small_url = host_bytes(small, 'small')
        if small_url:
            try:
                spil = Image.open(io.BytesIO(small)).convert('RGB')
                # forced entry: same hash as the upload, but a different file for Google
                c = Copy(len(cs.copies) + 1, small_url, __import__('imagehash').phash(spil),
                         spil.size[0], spil.size[1], 'small')
                cs.copies.append(c)
            except Exception:
                pass
    return cs, primary_pil, extras
