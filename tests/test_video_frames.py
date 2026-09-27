"""Video provenance: multi-frame query signatures and keyframe selection."""
import io

import numpy as np
import responses

from services import keyframes
from services.visual_verify import build_query_signature, verify_html


def _img(seed, size=(256, 256), flat=False):
    from PIL import Image
    if flat:
        return Image.new('RGB', size, (20, 20, 20))
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, (size[1] // 8, size[0] // 8, 3), dtype='uint8')
    return Image.fromarray(arr, 'RGB').resize(size, Image.NEAREST)


def _png(pil):
    buf = io.BytesIO()
    pil.save(buf, format='PNG')
    return buf.getvalue()


@responses.activate
def test_verify_html_matches_any_frame_of_the_clip(monkeypatch):
    """A page that shows frame B of the clip is confirmed when the query
    is [frame A, frame B] — the single-frame query rejected it before."""
    import services.embedding_service as es
    monkeypatch.setattr(es, 'encoder_available', lambda: False)
    monkeypatch.setattr('services.visual_verify.encoder_available', lambda: False)
    frame_a, frame_b = _img(1), _img(2)
    sig_a, sig_b = build_query_signature(_png(frame_a)), build_query_signature(_png(frame_b))
    responses.add(responses.GET, 'https://cdn.example/still.png', body=_png(frame_b),
                  content_type='image/png')
    html = '<html><head><meta property="og:image" content="https://cdn.example/still.png"></head></html>'
    single = verify_html(html, 'https://site.example/v', sig_a)
    multi = verify_html(html, 'https://site.example/v', [sig_a, sig_b])
    assert single['verdict'] in ('rejected', 'ambiguous', 'unverified')
    assert multi['verdict'] == 'confirmed' and multi['match_kind'] == 'exact'
    assert multi['phash_distance'] == 0


def test_youtube_storyboard_frames_are_candidate_images():
    from services.visual_verify import video_frame_urls
    urls = video_frame_urls('https://www.youtube.com/watch?v=IZ0ldhWOR1A&t=3s')
    assert urls[0].endswith('/IZ0ldhWOR1A/maxresdefault.jpg') and len(urls) == 4
    assert video_frame_urls('https://www.youtube.com/shorts/IZ0ldhWOR1A')[1].endswith('/hq1.jpg')
    assert video_frame_urls('https://youtu.be/IZ0ldhWOR1A') and not video_frame_urls('https://news.example/a')


def test_select_keyframes_prefers_distinct_sharp_frames():
    frames = [_png(_img(0, flat=True)),      # black leader
              _png(_img(1)), _png(_img(1)),  # duplicate pair
              _png(_img(2)), _png(_img(3)),
              _png(_img(0, flat=True))]      # black tail
    picks = keyframes.select_keyframes(frames, k=4)
    assert 0 not in picks and 5 not in picks           # flat frames skipped
    assert not ({1, 2} <= set(picks))                  # duplicates collapse to one
    assert len(picks) == 3 and picks == sorted(picks)
    # a usable opening frame is always kept (posters are often frame 0)
    picks = keyframes.select_keyframes([_png(_img(7))] + frames[1:], k=4)
    assert 0 in picks
    assert keyframes.select_keyframes([], k=4) == []
    assert keyframes.select_keyframes([b'not an image'], k=2) == [0]
