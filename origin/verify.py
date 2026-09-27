"""Page-level verification: does THIS page show the photo, and which file?

Image evidence, one axis:
  platform      the platform's own media for the post (X syndication photo,
                Instagram /media, Facebook crawler image, Telegram embed,
                TikTok oEmbed cover, YouTube storyboard) matched the query
  page          an image found in the page's HTML matched the query
  engine_claim  only the search engine's thumbnail matched — the page itself
                could not be checked (JavaScript-only) or showed other images
  none

Matching: perceptual hash (same file) then keypoint geometry (same photo
re-framed / restored / recoloured). Embeddings are not used for verdicts.
A page- or platform-level match returns the matched PIL image so the
orchestrator can add it as a new copy.
"""
import io
import logging
from dataclasses import dataclass

import requests

from origin import urls
from services import geometric_verify
from services.visual_verify import (UA, MAX_IMAGE_BYTES, extract_candidate_images,
                                    video_frame_urls, _hash_distance)
from services.date_evidence import CRAWLER_UA, platform_fetch_date

logger = logging.getLogger(__name__)

PHASH_SAME = 8
MAX_PAGE_IMAGES = 4
MAX_PLATFORM_IMAGES = 4
MAX_ENGINE_THUMBS = 2


@dataclass
class ImageEvidence:
    level: str = 'none'              # platform | page | engine_claim | none
    kind: str = None                 # exact | variant
    matched_url: str = None
    width: int = 0
    height: int = 0
    phash: int = None
    inliers: int = 0
    checked: int = 0
    note: str = None
    frame: int = None                # which query frame matched (video), 0 = the primary image

    def brief(self):
        return {'level': self.level, 'kind': self.kind, 'matched_url': self.matched_url,
                'size': [self.width, self.height] if self.width else None,
                'phash': self.phash, 'inliers': self.inliers, 'checked': self.checked,
                'note': self.note, 'frame': self.frame}


def _fetch_image(url, timeout=(5, 12)):
    from PIL import Image
    headers = UA
    if ('instagram.com' in url and '/media' in url) or 'lookaside.fbsbx.com' in url:
        headers = CRAWLER_UA
    r = requests.get(url, headers=headers, timeout=timeout, stream=True)
    r.raise_for_status()
    data = r.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError('image too large')
    return Image.open(io.BytesIO(data)).convert('RGB'), r.headers


def _compare(sigs, pil):
    """(kind|None, phash_distance, geometry dict|None, frame index|None)"""
    per = [(_hash_distance(s, pil), i) for i, s in enumerate(sigs)]
    per = [(d, i) for d, i in per if d is not None]
    dist, frame = min(per) if per else (None, None)
    if dist is not None and dist <= PHASH_SAME:
        return 'exact', dist, None, frame
    best = None
    for i, s in enumerate(sigs):
        g = geometric_verify.same_scene([s], pil)
        if g.get('same_scene'):
            return 'variant', dist, g, i
        if best is None or (g.get('inliers') or 0) > (best[0].get('inliers') or 0):
            best = (g, i)
    return None, dist, (best[0] if best else None), None


def platform_media(url):
    """(image_urls, info) — the platform's own media for a post + metadata
    {'caption','created_at','html','extra_dates'}."""
    info = {'caption': None, 'created_at': None, 'html': None, 'extra_dates': [], 'tweet': None}
    p = urls.platform_of(url)
    images = []
    try:
        if p == 'x':
            from providers import tweet
            t = tweet.tweet_info(url)
            if t:
                images = list(t.get('photos') or [])[:MAX_PLATFORM_IMAGES]
                info.update(caption=t.get('text'), created_at=t.get('created_at'), tweet=t)
        elif p == 'instagram':
            from services.visual_verify import platform_image_urls
            images = platform_image_urls(url)
        elif p == 'tiktok':
            from providers import tiktok
            o = tiktok.oembed(url)
            if o:
                if o.get('thumbnail_url'):
                    images = [o['thumbnail_url']]
                info['caption'] = o.get('title')
        elif p == 'youtube':
            images = video_frame_urls(url)[:MAX_PLATFORM_IMAGES]
        elif p in ('facebook', 'telegram'):
            ev, html = platform_fetch_date(url)
            info['extra_dates'] = ev or []
            info['html'] = html
    except Exception as e:
        logger.info('platform media failed for %s: %s', url, e)
    return images, info


def _title_and_text(html, fallback):
    title, text = fallback, ''
    try:
        from bs4 import BeautifulSoup
        import re
        soup = BeautifulSoup(html, 'html.parser')
        og = soup.find('meta', property='og:title')
        if og and og.get('content'):
            title = og['content'].strip()[:200]
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()[:200]
        desc = soup.find('meta', property='og:description') or soup.find('meta', attrs={'name': 'description'})
        text = (desc.get('content', '') if desc else '')[:400]
        if not text:
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            text = re.sub(r'\s+', ' ', soup.get_text(' ', strip=True))[:400]
    except Exception:
        pass
    return title, text


def verify_page(url, sigs, *, engine_thumbs=(), timeout=(5, 10), fetch=True):
    """Returns a dict:
       image: ImageEvidence, html, headers, title, caption, created_at,
       extra_dates, tweet, matched_pil (PIL for page/platform matches)"""
    out = {'url': url, 'image': ImageEvidence(), 'html': None, 'headers': None,
           'title': urls.domain_of(url), 'caption': None, 'created_at': None,
           'extra_dates': [], 'tweet': None, 'matched_pil': None, 'fetch_error': False}
    if not sigs:
        return out
    plat_images, info = platform_media(url)
    out.update({k: info[k] for k in ('caption', 'created_at', 'extra_dates', 'tweet')})
    html, headers = info.get('html'), None
    if fetch and html is None and not urls.is_image_url(url):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            if r.status_code == 200:
                html, headers = r.text or '', r.headers
            else:
                out['fetch_error'] = True
        except Exception as e:
            logger.info('fetch failed for %s: %s', url, e)
            out['fetch_error'] = True
    out['html'], out['headers'] = html, headers
    if html:
        out['title'], text = _title_and_text(html, out['title'])
        if not out['caption']:
            out['caption'] = text

    page_images = []
    if urls.is_image_url(url):
        page_images = [url]
    elif html:
        page_images = extract_candidate_images(html, url)[:MAX_PAGE_IMAGES]

    ev = out['image']
    # 1) platform media, 2) page images — either confirms the page itself
    for level, group in (('platform', plat_images), ('page', page_images)):
        for img_url in group:
            try:
                pil, _ = _fetch_image(img_url, timeout)
            except Exception:
                continue
            ev.checked += 1
            kind, dist, g, frame = _compare(sigs, pil)
            if kind:
                ev.level, ev.kind, ev.matched_url = level, kind, img_url
                ev.width, ev.height, ev.phash = pil.size[0], pil.size[1], dist
                ev.inliers = int((g or {}).get('inliers') or 0)
                ev.frame = frame
                out['matched_pil'] = pil
                return out
            if g and g.get('same_scene') is False:
                ev.note = 'page images differ'
    # 3) engine thumbnails: a claim, only when the page could not contradict it
    if ev.note != 'page images differ':
        for img_url in list(engine_thumbs)[:MAX_ENGINE_THUMBS]:
            try:
                pil, _ = _fetch_image(img_url, timeout)
            except Exception:
                continue
            ev.checked += 1
            kind, dist, g, frame = _compare(sigs, pil)
            if kind:
                ev.level, ev.kind, ev.matched_url = 'engine_claim', kind, img_url
                ev.width, ev.height, ev.phash = pil.size[0], pil.size[1], dist
                ev.inliers = int((g or {}).get('inliers') or 0)
                ev.frame = frame
                ev.note = 'page not checkable' if not page_images else 'page images not judged'
                return out
    return out
