"""Screenshot auto-crop: find the photo inside a post screenshot, leave
plain photos alone; the engine searches the crop and keeps the screenshot
as a second signature; Instagram posts verify via the /media redirect."""
import io

import numpy as np

from services import screenshot_crop as sc


def _noise(w, h, seed):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, (h, w, 3), dtype='uint8')


def _jpeg(arr):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(arr, 'RGB').save(buf, format='JPEG', quality=90)
    return buf.getvalue()


def _screenshot():
    """White phone UI (400x900) with a noisy 'photo' from y=200 to y=600."""
    canvas = np.full((900, 400, 3), 255, dtype='uint8')
    canvas[200:600, 0:400] = _noise(400, 400, 1)
    canvas[650:670, 40:360] = 40                     # a caption line
    return _jpeg(canvas)


def test_detects_photo_band_in_screenshot_only():
    box = sc.detect_photo_region(_screenshot())
    assert box is not None
    l, t, r, b = box
    assert 190 <= t <= 215 and 590 <= b <= 615 and l <= 5 and r >= 395
    crop, box2 = sc.crop_photo(_screenshot())
    assert crop and box2 == box
    assert sc.detect_photo_region(_jpeg(_noise(600, 400, 2))) is None       # plain photo
    assert sc.detect_photo_region(b'not an image') is None


def test_engine_searches_the_crop_and_keeps_screenshot_signature(monkeypatch):
    from services import origin_engine as oe
    calls = {'lens': [], 'sig': None}

    def lens(image_url, lens_type, hl='ar', country='sa', no_cache=False):
        calls['lens'].append((image_url, lens_type))
        return []
    monkeypatch.setattr(oe, 'lens_matches', lens)
    monkeypatch.setattr(oe, 'LENS_RETRY_DELAY_S', 0)
    monkeypatch.setattr(oe.vision_provider, 'configured', lambda: False)
    monkeypatch.setattr(oe.tineye_provider, 'configured', lambda: False)
    monkeypatch.setattr(oe, '_browser_engine', lambda name: None)
    monkeypatch.setattr(oe.yandex_provider, 'reverse_image', lambda u: [])
    monkeypatch.setattr(oe, 'reverse_image_pages', lambda u, **k: [])
    monkeypatch.setattr(oe.wayback_provider, 'archive_url', lambda u, **k: {'url': None, 'status': 'failed'})
    monkeypatch.setattr(oe, '_download_bytes', lambda u, timeout=None: b'bytes:' + u.encode())
    monkeypatch.setattr(oe, 'screenshot_crop_url',
                        lambda data: (b'cropbytes', 'https://host.example/crop.jpg', [0, 200, 400, 600]))

    def sigs(primary_bytes, extras):
        calls['sig'] = (primary_bytes, list(extras or []))
        return {'phash': 'p'}
    monkeypatch.setattr(oe, 'frame_signatures', sigs)
    monkeypatch.setenv('SERPAPI_API_KEY', 'test')
    monkeypatch.setenv('SEARCH_COPY', 'none')
    report = oe.investigate_origin('https://r2.example/shot.jpg')
    searched = {u for u, t in calls['lens'] if t == 'exact_matches'}
    assert 'https://host.example/crop.jpg' in searched            # engines got the photo
    assert 'https://r2.example/shot.jpg' in searched              # screenshot searched once too
    assert calls['sig'] == (b'cropbytes', ['https://r2.example/shot.jpg'])
    assert report['engines']['screenshot_crop'] == {'ok': True, 'count': 1, 'box': [0, 200, 400, 600]}


def test_instagram_media_redirect_is_a_candidate_image():
    from services.visual_verify import platform_image_urls
    assert platform_image_urls('https://www.instagram.com/p/DK2uuidoB7V/') == \
        ['https://www.instagram.com/p/DK2uuidoB7V/media/?size=l']
    assert platform_image_urls('https://www.instagram.com/reel/DWucDsUM2TG/?hl=fi')[0].endswith('/DWucDsUM2TG/media/?size=l')
    assert platform_image_urls('https://www.instagram.com/kingsalmannaa/') == []
