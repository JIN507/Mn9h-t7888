"""Exact-match "no results" is a genuine empty when the visual pass fetched
the image; geometry-confirmed sightings survive the temporal-outlier rule;
a derivative query triggers a Lens search with the page's original copy."""
from services import origin_engine as oe


def test_reconcile_exact_no_results_when_visual_fetched():
    st = {'lens_visual': {'ok': True, 'count': 3},
          'lens_exact_en': {'ok': False, 'count': 0, 'note': 'fetch_failed'},
          'lens_exact_en@frame2': {'ok': False, 'count': 0, 'note': 'fetch_failed'}}
    oe.reconcile_fetch_status(st)
    assert st['lens_exact_en'] == {'ok': True, 'count': 0, 'note': 'no exact matches'}
    assert st['lens_exact_en@frame2']['note'] == 'fetch_failed'      # other frame, other fetch
    st2 = {'lens_visual': {'ok': False, 'count': 0, 'note': 'fetch_failed'},
           'lens_exact_en': {'ok': False, 'count': 0, 'note': 'fetch_failed'}}
    oe.reconcile_fetch_status(st2)
    assert st2['lens_exact_en']['note'] == 'fetch_failed'


def test_geometry_confirmed_variant_is_never_a_temporal_outlier():
    def item(day, geom):
        return {'published_at': f'{day}T10:00:00Z', 'confidence': 0.94,
                'visual': {'verdict': 'confirmed', 'match_kind': 'variant', 'matched_from': 'engine',
                           'geometry': {'same_scene': geom}}}
    cluster = [item(f'2022-0{m}-01', None) for m in range(1, 7)]
    early = item('2019-02-08', True)
    assert oe._is_temporal_outlier(early, cluster + [early]) is False
    early_no_geom = item('2019-02-08', None)
    assert oe._is_temporal_outlier(early_no_geom, cluster + [early_no_geom]) is True


def test_original_image_for_pivot_prefers_largest_page_copy():
    tl = [{'visual': {'verdict': 'confirmed', 'match_kind': 'variant', 'matched_from': 'page',
                      'geometry': {'same_scene': True}, 'matched_image_url': 'https://a/small.jpg'},
           'image_size': [236, 236]},
          {'visual': {'verdict': 'confirmed', 'match_kind': 'variant', 'matched_from': 'page',
                      'geometry': {'same_scene': True}, 'matched_image_url': 'https://a/big.jpg'},
           'image_size': [1024, 1024]},
          {'visual': {'verdict': 'confirmed', 'match_kind': 'variant', 'matched_from': 'engine',
                      'geometry': {'same_scene': True}, 'matched_image_url': 'https://thumb/x.jpg'},
           'image_size': [2000, 2000]}]
    assert oe.original_image_for_pivot(tl) == 'https://a/big.jpg'
    tl.append({'visual': {'verdict': 'confirmed', 'match_kind': 'variant', 'matched_from': 'page',
                          'geometry': {'same_scene': True}, 'matched_image_url': 'https://b/other.jpg'},
               'image_size': [500, 500]})
    # largest first, at most two per host, engine thumbnails never
    assert oe.original_images_for_pivot(tl) == ['https://a/big.jpg', 'https://b/other.jpg', 'https://a/small.jpg']
    assert oe.original_images_for_pivot(tl, exclude={'https://a/big.jpg'}) == ['https://b/other.jpg', 'https://a/small.jpg']
    tl.append({'visual': {'verdict': 'confirmed', 'match_kind': 'variant', 'matched_from': 'page',
                          'geometry': {'same_scene': True}, 'matched_image_url': 'https://a/mid.jpg'},
               'image_size': [700, 700]})
    assert oe.original_images_for_pivot(tl) == ['https://a/big.jpg', 'https://a/mid.jpg', 'https://b/other.jpg']
    tl.append({'visual': {'verdict': 'confirmed', 'match_kind': 'exact', 'matched_image_url': 'https://a/same.jpg'}})
    assert oe.original_image_for_pivot(tl) is None
