"""Keypoint geometry confirms re-framed / restored / cropped copies of the
same photograph and refuses look-alike images that embeddings over-score."""
import io

import numpy as np
from PIL import Image, ImageFilter

from services import geometric_verify as gv
from services import visual_verify as vv


def _textured(seed, size=(640, 480)):
    """A busy synthetic 'photo': blurred noise + hard-edged shapes so SIFT
    finds stable, distinctive keypoints."""
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, (size[1], size[0], 3), dtype='uint8')
    im = Image.fromarray(arr, 'RGB').filter(ImageFilter.GaussianBlur(2))
    a = np.asarray(im).copy()
    for _ in range(60):
        x, y = rng.integers(0, size[0] - 40), rng.integers(0, size[1] - 40)
        w, h = rng.integers(8, 40), rng.integers(8, 40)
        a[y:y + h, x:x + w] = rng.integers(0, 255, 3)
    return Image.fromarray(a, 'RGB')


def _jpeg(im, q=85):
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=q)
    return buf.getvalue()


def test_same_photo_variants_match_and_unrelated_do_not():
    orig = _textured(1)
    fo = gv.features(orig)
    assert fo and fo['n'] >= gv.MIN_KEYPOINTS_TO_JUDGE
    crop = orig.crop((80, 60, 560, 420)).resize((720, 540))          # crop + upscale
    grey = orig.convert('L').convert('RGB').resize((400, 300))       # recolour + downscale
    wide = Image.new('RGB', (900, 480), (200, 200, 200)); wide.paste(orig, (130, 0))  # outpainted
    for variant in (crop, grey, wide):
        m = gv.match(fo, gv.features(variant))
        assert m['same_scene'] is True and m['inliers'] >= gv.MIN_INLIERS, m
    other = _textured(2)
    m = gv.match(fo, gv.features(other))
    assert m['same_scene'] is False and m['inliers'] < gv.MIN_INLIERS, m
    # too flat to judge -> None, never a false "different"
    flat = Image.new('RGB', (400, 400), (255, 255, 255))
    assert gv.match(fo, gv.features(flat))['same_scene'] is None


def test_signature_carries_geometry_and_verify_confirms_a_restored_copy(monkeypatch):
    """verify_html: the page image is a re-framed copy whose pHash is far
    off and whose (stubbed) embedding sits in the ambiguous band — geometry
    turns it into a confirmed variant."""
    import responses
    orig = _textured(3)
    query = orig.crop((100, 40, 600, 440)).resize((1000, 800))
    sig = vv.build_query_signature(_jpeg(query))
    assert sig['geom'] and sig['size'] == (1000, 800)
    # stub the encoder so similarity is ambiguous (0.8) for any image
    from services import embedding_service as es
    sig['embedding'] = np.ones(4, dtype='float32')
    monkeypatch.setattr(vv, 'embed_image', lambda pil: np.array([0.8, 0.6, 0, 0], dtype='float32'))
    monkeypatch.setattr(vv, 'cosine_similarity', lambda a, b: 0.80)
    with responses.RequestsMock() as rs:
        rs.add(responses.GET, 'https://page.example/photo.jpg', body=_jpeg(orig), content_type='image/jpeg')
        out = vv.verify_html('<html><img src="https://page.example/photo.jpg"></html>',
                             'https://page.example/post', sig)
    assert out['verdict'] == 'confirmed' and out['match_kind'] == 'variant'
    assert out['geometry']['same_scene'] is True and out['geometry']['inliers'] >= gv.MIN_INLIERS
    assert out['matched_image_url'] == 'https://page.example/photo.jpg'

    # look-alike: embedding says 0.95 but geometry says different -> ambiguous, never confirmed
    other = _textured(4)
    monkeypatch.setattr(vv, 'cosine_similarity', lambda a, b: 0.95)
    with responses.RequestsMock() as rs:
        rs.add(responses.GET, 'https://page.example/other.jpg', body=_jpeg(other), content_type='image/jpeg')
        out = vv.verify_html('<html><img src="https://page.example/other.jpg"></html>',
                             'https://page.example/post2', sig)
    assert out['verdict'] == 'ambiguous' and out['geometry']['same_scene'] is False
    assert 'geometry' in (out.get('note') or '')
