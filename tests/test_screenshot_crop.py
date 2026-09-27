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


def test_instagram_media_redirect_is_a_candidate_image():
    from services.visual_verify import platform_image_urls
    assert platform_image_urls('https://www.instagram.com/p/DK2uuidoB7V/') == \
        ['https://www.instagram.com/p/DK2uuidoB7V/media/?size=l']
    assert platform_image_urls('https://www.instagram.com/reel/DWucDsUM2TG/?hl=fi')[0].endswith('/DWucDsUM2TG/media/?size=l')
    assert platform_image_urls('https://www.instagram.com/kingsalmannaa/') == []
    assert platform_image_urls('https://www.instagram.com/abdulmajeedphoto/p/DMLY25ZsvNA/') == \
        ['https://www.instagram.com/p/DMLY25ZsvNA/media/?size=l']


def test_letterboxed_video_frame_is_not_a_screenshot():
    """A phone video frame with black bars above and below is NOT a post
    screenshot: cropping it would throw away the frame we need to search."""
    canvas = np.zeros((900, 400, 3), dtype='uint8')               # black bars
    canvas[200:600, 0:400] = _noise(400, 400, 4)
    assert sc.detect_photo_region(_jpeg(canvas)) is None
    assert sc.detect_photo_region(_screenshot()) is not None       # white UI still detected
