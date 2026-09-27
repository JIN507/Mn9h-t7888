"""An engine thumbnail that hashes like the query is a claim: the page's own
images decide when they can be checked; engine-only sightings far ahead of
the dated cluster are outliers; the agent's page-verified pick outranks an
engine-only deterministic first seen."""
import io

import numpy as np
import responses
from PIL import Image, ImageFilter

from services import visual_verify as vv
from services import origin_engine as oe


def _textured(seed, size=(640, 480)):
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, (size[1], size[0], 3), dtype='uint8')
    im = Image.fromarray(arr, 'RGB').filter(ImageFilter.GaussianBlur(2))
    a = np.asarray(im).copy()
    for _ in range(60):
        x, y = rng.integers(0, size[0] - 40), rng.integers(0, size[1] - 40)
        w, h = rng.integers(8, 40), rng.integers(8, 40)
        a[y:y + h, x:x + w] = rng.integers(0, 255, 3)
    return Image.fromarray(a, 'RGB')


def _jpeg(im):
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=88)
    return buf.getvalue()


@responses.activate
def test_engine_thumbnail_claim_is_overruled_by_the_pages_own_image():
    query = _textured(11)
    sig = vv.build_query_signature(_jpeg(query))
    sig['embedding'] = None
    other = _textured(12)
    responses.add(responses.GET, 'https://engine.example/thumb.jpg', body=_jpeg(query), content_type='image/jpeg')
    responses.add(responses.GET, 'https://page.example/photo.jpg', body=_jpeg(other), content_type='image/jpeg')
    html = '<html><img src="https://page.example/photo.jpg"></html>'
    out = vv.verify_html(html, 'https://page.example/post', sig,
                         extra_image_urls=['https://engine.example/thumb.jpg'])
    assert out['verdict'] == 'ambiguous' and 'engine thumbnail' in out['note']
    assert out['matched_from'] == 'engine' and out['checked_images'] == 2

    # page image confirms -> page-level exact match
    responses.add(responses.GET, 'https://page2.example/photo.jpg', body=_jpeg(query), content_type='image/jpeg')
    out = vv.verify_html('<html><img src="https://page2.example/photo.jpg"></html>', 'https://page2.example/post', sig,
                         extra_image_urls=['https://engine.example/thumb.jpg'])
    assert out['verdict'] == 'confirmed' and out['match_kind'] == 'exact' and out['matched_from'] == 'page'

    # no page image at all (JS-only page) -> the engine claim stands, as before
    out = vv.verify_html('<html></html>', 'https://x.example/post', sig,
                         extra_image_urls=['https://engine.example/thumb.jpg'])
    assert out['verdict'] == 'confirmed' and out['matched_from'] == 'engine'


def test_engine_only_exact_far_ahead_of_cluster_is_an_outlier():
    def item(day, kind, source='engine'):
        return {'published_at': f'{day}T10:00:00Z', 'confidence': 0.96, 'url': day,
                'visual': {'verdict': 'confirmed', 'match_kind': kind, 'matched_from': source}}
    cluster = [item(f'2024-07-{d:02d}', 'exact', 'page') for d in range(19, 26)]
    voa = item('2021-05-28', 'exact')                    # engine thumbnail only
    assert oe._is_temporal_outlier(voa, cluster + [voa]) is True
    voa_page = item('2021-05-28', 'exact', 'page')
    assert oe._is_temporal_outlier(voa_page, cluster + [voa_page]) is False
    assert oe.assess(cluster + [voa])['url'] == '2024-07-19'


def test_eligibility_honours_engine_only_outranked():
    it = {'published_at': '2021-05-28T10:00:00Z', 'confidence': 0.96,
          'visual': {'verdict': 'confirmed', 'match_kind': 'exact', 'matched_from': 'engine'}}
    assert oe._eligible_first(it) is True
    it['engine_only_outranked'] = 'https://x.com/real/status/1'
    assert oe._eligible_first(it) is False
