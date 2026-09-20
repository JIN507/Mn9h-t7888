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


def test_video_consensus_promotes_clustered_ambiguous_sightings():
    from services import origin_engine as oe

    def amb(url, date, sim=0.81):
        return {'url': url, 'published_at': date, 'confidence': 0.95, 'match_type': 'exact',
                'visual': {'verdict': 'ambiguous', 'match_kind': None, 'similarity': sim}}
    tl = [amb(f'https://s{i}.example/p', f'2026-03-0{8 if i else 7}T10:00:00Z') for i in range(6)]
    tl.append(amb('https://late.example/p', '2026-04-09T10:00:00Z'))          # outside window
    tl.append(amb('https://weak.example/p', '2026-03-08T11:00:00Z', sim=0.70))  # too dissimilar
    assert oe.assess(tl) is None
    assert oe.video_consensus(tl) == 6
    first = oe.assess(tl)
    assert first['url'] == 'https://s0.example/p' and first['probable'] is True
    assert first['visual']['verdict'] == 'probable'
    assert tl[-2]['visual']['verdict'] == 'ambiguous' and tl[-1]['visual']['verdict'] == 'ambiguous'
    # never promotes when a real confirmation exists, or the cluster is thin
    confirmed = dict(amb('https://c.example/p', '2026-03-08T09:00:00Z'), visual={'verdict': 'confirmed', 'match_kind': 'exact', 'similarity': 0.99})
    assert oe.video_consensus([confirmed] + tl[:5]) == 0
    assert oe.video_consensus([amb(f'https://t{i}.example', '2026-03-08T10:00:00Z') for i in range(3)]) == 0


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


@responses.activate
def test_direct_search_accepts_image_urls_for_video(client, monkeypatch):
    seen = {}

    def fake(image_url, progress=None, budget=None, extra_frame_urls=None):
        seen['primary'] = image_url
        seen['extra'] = extra_frame_urls
        return {'success': True, 'timeline': [], 'first_seen': None, 'engines': {'lens_exact_en': {'ok': True, 'count': 0}},
                'stats': {}, 'rounds': [], 'narrative': None, 'note': None}
    import services.origin_engine as oe
    monkeypatch.setattr(oe, 'investigate_origin', fake)
    r = client.post('/api/direct-search', json={
        'image_urls': ['https://i.example/f1.jpg', 'https://i.example/f2.jpg',
                       'https://i.example/f3.jpg', 'https://i.example/f4.jpg', 'https://i.example/f5.jpg'],
        'image_hash': 'video-hash-1'})
    assert r.status_code == 202
    state = client.get(r.get_json()['status_url']).get_json()
    assert state['status'] == 'finished'
    assert seen['primary'] == 'https://i.example/f1.jpg'
    assert seen['extra'] == ['https://i.example/f2.jpg', 'https://i.example/f3.jpg',
                             'https://i.example/f4.jpg', 'https://i.example/f5.jpg']
