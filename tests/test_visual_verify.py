"""Tier-1 visual verification: fixtures (same/cropped/different), verdict
bands, candidate extraction, post-filter, and the internal vector index.

A deterministic fake encoder is injected so band behavior is exact; the
real DINOv2 encoder has a separate opt-in test (RUN_ML_TESTS=1)."""
import io
import os

import numpy as np
import pytest
import responses

from services import embedding_service
from services.visual_verify import (fetch_and_verify, build_query_signature,
                                    extract_candidate_images,
                                    apply_visual_post_filter)


# ---------------------------------------------------------------- fixtures

def _make_image(seed, size=(256, 256)):
    """Deterministic textured image (noise + structure) as a PIL image."""
    from PIL import Image
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, (size[1] // 8, size[0] // 8, 3), dtype='uint8')
    return Image.fromarray(arr, 'RGB').resize(size, Image.NEAREST)


def _png(pil):
    buf = io.BytesIO()
    pil.save(buf, format='PNG')
    return buf.getvalue()


def _solid(color, size=(300, 300)):
    from PIL import Image
    return Image.new('RGB', size, color)


@pytest.fixture()
def query_image():
    return _make_image(seed=1)


@pytest.fixture()
def cropped_image(query_image):
    w, h = query_image.size
    return query_image.crop((int(w * .15), int(h * .15),
                             int(w * .9), int(h * .9)))


@pytest.fixture()
def different_image():
    return _make_image(seed=99)


# Fake encoder: dominant channel -> fixed vector, giving exact cosine values
# vs the query vector [1,0,0]: red=1.0, green=0.8, blue=0.3
_VECS = {
    'r': np.array([1.0, 0.0, 0.0], dtype='float32'),
    'g': np.array([0.8, 0.6, 0.0], dtype='float32'),
    'b': np.array([0.3, 0.95394, 0.0], dtype='float32'),
}


def _fake_encoder(pil):
    r, g, b = pil.resize((1, 1)).getpixel((0, 0))
    if max(r, g, b) - min(r, g, b) < 60:
        # textured/noise fixtures (query + its crop) — no dominant channel:
        # model them as the same instance, like real DINOv2 would
        return _VECS['r']
    channel = 'rgb'[int(np.argmax([r, g, b]))]
    return _VECS[channel]


@pytest.fixture()
def fake_encoder(app):
    embedding_service.set_encoder_for_testing(_fake_encoder)
    yield
    embedding_service.set_encoder_for_testing(None)


def _mock_page(page_url, img_url, img_bytes):
    responses.add(responses.GET, page_url, status=200, body=(
        f'<html><head><meta property="og:image" content="{img_url}"/>'
        f'</head><body></body></html>'))
    responses.add(responses.GET, img_url, body=img_bytes, status=200,
                  content_type='image/png', stream=True)


def _query_sig(query_image, embedding):
    sig = build_query_signature(_png(query_image))
    sig['embedding'] = embedding
    return sig


# ---------------------------------------------------------- verdict bands

@responses.activate
def test_same_image_confirmed_by_phash(app, fake_encoder, query_image):
    """Identical bytes -> pHash distance 0 -> confirmed 'exact'."""
    _mock_page('https://site.example/post', 'https://cdn.example/q.png',
               _png(query_image))
    sig = _query_sig(query_image, _VECS['r'])
    out = fetch_and_verify('https://site.example/post', sig)
    assert out['verdict'] == 'confirmed'
    assert out['match_kind'] == 'exact'
    assert out['phash_distance'] == 0


@responses.activate
def test_cropped_image_needs_embedding(app, fake_encoder, query_image,
                                       cropped_image):
    """A crop breaks pHash (distance > 8) — embeddings still confirm it.

    Fake encoder maps both textured images to the red vector => sim 1.0,
    which is the crop-invariance the real DINOv2 provides."""
    d = (build_query_signature(_png(query_image))['phash']
         - build_query_signature(_png(cropped_image))['phash'])
    assert d > 8, 'fixture must actually defeat pHash'

    _mock_page('https://site.example/crop', 'https://cdn.example/crop.png',
               _png(cropped_image))
    sig = _query_sig(query_image, _VECS['r'])
    out = fetch_and_verify('https://site.example/crop', sig)
    assert out['verdict'] == 'confirmed'
    assert out['match_kind'] == 'variant'
    assert out['similarity'] >= 0.90


@responses.activate
def test_ambiguous_band(app, fake_encoder, query_image):
    """Similarity 0.8 lands in the 0.75-0.90 escalation band."""
    _mock_page('https://site.example/amb', 'https://cdn.example/amb.png',
               _png(_solid((10, 200, 10))))   # green -> sim 0.8
    sig = _query_sig(query_image, _VECS['r'])
    out = fetch_and_verify('https://site.example/amb', sig)
    assert out['verdict'] == 'ambiguous'
    assert 0.75 <= out['similarity'] < 0.90


@responses.activate
def test_different_image_rejected(app, fake_encoder, query_image):
    """Similarity 0.3 -> rejected: today's unrelated noise dies here."""
    _mock_page('https://site.example/diff', 'https://cdn.example/diff.png',
               _png(_solid((10, 10, 220))))   # blue -> sim 0.3
    sig = _query_sig(query_image, _VECS['r'])
    out = fetch_and_verify('https://site.example/diff', sig)
    assert out['verdict'] == 'rejected'
    assert out['similarity'] < 0.75


@responses.activate
def test_no_encoder_is_unverified_not_rejected(app, query_image,
                                               different_image):
    """Without an encoder, a non-pHash-match must NOT be dropped."""
    embedding_service.set_encoder_for_testing(None)
    _mock_page('https://site.example/ne', 'https://cdn.example/ne.png',
               _png(different_image))
    sig = build_query_signature(_png(query_image))
    sig['embedding'] = None
    out = fetch_and_verify('https://site.example/ne', sig)
    assert out['verdict'] == 'unverified'


@responses.activate
def test_page_without_images(app, fake_encoder, query_image):
    responses.add(responses.GET, 'https://site.example/none', status=200,
                  body='<html><body><p>text only</p></body></html>')
    out = fetch_and_verify('https://site.example/none',
                           _query_sig(query_image, _VECS['r']))
    assert out['verdict'] == 'no_image'


# ------------------------------------------------- candidate extraction

def test_extract_candidate_images_priority_and_floor():
    html = '''
    <html><head>
      <meta property="og:image" content="/main.jpg"/>
      <script type="application/ld+json">{"image": "https://cdn.x/ld.jpg"}</script>
    </head><body>
      <img src="/icon.png" width="32" height="32"/>
      <img src="/big.png" width="800" height="600"/>
      <img src="data:image/gif;base64,R0lGOD"/>
      <img src="/vector.svg" width="500"/>
      <img src="/main.jpg"/>
    </body></html>'''
    urls = extract_candidate_images(html, 'https://site.example/post')
    assert urls[0] == 'https://site.example/main.jpg'   # og:image first
    assert 'https://cdn.x/ld.jpg' in urls               # JSON-LD picked up
    assert 'https://site.example/big.png' in urls
    assert not any('icon' in u for u in urls)           # size floor
    assert not any(u.endswith('.svg') or u.startswith('data:') for u in urls)
    assert urls.count('https://site.example/main.jpg') == 1  # deduped


# ---------------------------------------------------------- post-filter

@responses.activate
def test_post_filter_drops_rejected_and_annotates(app, fake_encoder,
                                                  query_image):
    query_url = 'https://r2.example/query.png'
    responses.add(responses.GET, query_url, body=_png(query_image),
                  status=200, content_type='image/png')
    _mock_page('https://good.example/a', 'https://cdn.example/a.png',
               _png(query_image))                       # exact -> confirmed
    _mock_page('https://bad.example/b', 'https://cdn.example/b.png',
               _png(_solid((10, 10, 220))))             # blue -> rejected

    items = [{'link': 'https://good.example/a', 'title': 'good'},
             {'link': 'https://bad.example/b', 'title': 'bad'}]
    survivors, summary = apply_visual_post_filter(
        items, query_url, url_field='link', max_workers=1)

    assert [i['title'] for i in survivors] == ['good']
    assert survivors[0]['visual']['verdict'] == 'confirmed'
    assert summary == {'enabled': True, 'checked': 2, 'rejected': 1,
                       'confirmed': 1, 'ambiguous': 0}


@responses.activate
def test_post_filter_passthrough_when_query_unavailable(app, fake_encoder):
    responses.add(responses.GET, 'https://r2.example/gone.png', status=404)
    items = [{'link': 'https://x.example/1'}]
    survivors, summary = apply_visual_post_filter(
        items, 'https://r2.example/gone.png')
    assert survivors == items
    assert summary['enabled'] is False


# ---------------------------------------------------------- vector index

def test_vector_index_store_and_find(app, fake_encoder):
    from services.vector_index import store_signature, find_similar
    with app.app_context():
        a = store_signature('a' * 64, embedding=[1.0, 0.0, 0.0], source='query')
        assert a is not None
        assert store_signature('a' * 64, embedding=[1.0, 0, 0]) == a  # dedup

        store_signature('b' * 64, embedding=[0.8, 0.6, 0.0], source='sighting')
        store_signature('c' * 64, embedding=[0.0, 1.0, 0.0], source='query')

        hits = find_similar([1.0, 0.0, 0.0], min_similarity=0.75)
        hashes = [h['media_hash'] for h in hits]
        assert 'a' * 64 in hashes and 'b' * 64 in hashes
        assert 'c' * 64 not in hashes
        assert hits[0]['media_hash'] == 'a' * 64  # best first


@responses.activate
def test_upload_indexes_query_image(client, app, monkeypatch, png_bytes,
                                    fake_encoder):
    monkeypatch.setenv('VISUAL_VERIFY', 'true')
    responses.add(responses.POST, 'https://api.imgbb.com/1/upload',
                  json={'success': True,
                        'data': {'url': 'https://i.ibb.co/x.png'}}, status=200)
    r = client.post('/api/upload', data={'file': (io.BytesIO(png_bytes), 'v.png')},
                    content_type='multipart/form-data')
    d = r.get_json()
    from models import db, ImageVector
    with app.app_context():
        row = (db.session.query(ImageVector)
               .filter_by(media_hash=d['image_hash']).first())
        assert row is not None
        assert row.phash and row.embedding is not None
        assert row.source == 'query'


# ------------------------------------------------ real model (opt-in)

def _structured_scene(kind, size=(448, 448)):
    """Distinctive synthetic scenes (uniform noise fools semantic encoders —
    two noise images embed as the same 'texture', which is exactly why the
    Session-9 benchmark uses real photographs)."""
    from PIL import Image, ImageDraw
    img = Image.new('RGB', size, (235, 225, 200) if kind == 'a' else (30, 40, 90))
    d = ImageDraw.Draw(img)
    if kind == 'a':
        d.rectangle([40, 260, 400, 420], fill=(160, 60, 40))     # building
        d.polygon([(40, 260), (220, 140), (400, 260)], fill=(90, 30, 20))
        d.ellipse([320, 40, 400, 120], fill=(250, 210, 60))      # sun
        for x in range(60, 380, 40):
            d.rectangle([x, 300, x + 18, 340], fill=(240, 240, 255))
    else:
        for i in range(0, 500, 36):                              # night waves
            d.arc([i - 120, 200, i + 120, 440], 200, 340, fill=(120, 200, 255), width=6)
        d.ellipse([60, 60, 130, 130], fill=(240, 240, 240))      # moon
        for x, y in [(200, 80), (280, 130), (350, 60), (150, 150)]:
            d.ellipse([x, y, x + 6, y + 6], fill=(255, 255, 255))
    return img


@pytest.mark.skipif(os.environ.get('RUN_ML_TESTS') != '1',
                    reason='set RUN_ML_TESTS=1 (downloads DINOv2 weights)')
def test_real_dinov2_ordering():
    embedding_service.set_encoder_for_testing(None)
    scene = _structured_scene('a')
    w, h = scene.size
    crop = scene.crop((int(w * .2), int(h * .2), int(w * .95), int(h * .95)))
    other = _structured_scene('b')

    e_same = embedding_service.embed_image(scene)
    assert e_same is not None, 'encoder failed to load'
    s_same = embedding_service.cosine_similarity(e_same, e_same)
    s_crop = embedding_service.cosine_similarity(
        e_same, embedding_service.embed_image(crop))
    s_diff = embedding_service.cosine_similarity(
        e_same, embedding_service.embed_image(other))

    assert s_same > 0.999
    assert s_crop > s_diff, f'crop {s_crop:.3f} must beat different {s_diff:.3f}'
    assert s_crop - s_diff > 0.05, 'bands need meaningful separation'
