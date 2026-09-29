"""Guards added after a production false match (2026-09-29): a different
photo of the same man was accepted through a repeating texture, on a profile
page. Three rules are pinned here: the fitted transform must be one a copy can
produce, profile pages are never an origin, and unconfirmed engine rows are
shown to the reader without feeding the decision."""
import numpy as np

from origin import report, urls
from origin.dates import DateEvidence
from origin.verify import ImageEvidence
from services import geometric_verify as gv


def _grid(n, step=20.0, origin=(50.0, 50.0)):
    side = int(np.ceil(np.sqrt(n)))
    pts = [(origin[0] + step * (i % side), origin[1] + step * (i // side)) for i in range(n)]
    return np.float32(pts)


def test_transform_of_a_real_copy_is_plausible():
    src = _grid(64, step=60.0)
    H = np.array([[0.5, 0, 10], [0, 0.5, 5], [0, 0, 1]], dtype='float64')     # a half-size copy
    dst = np.float32([(0.5 * x + 10, 0.5 * y + 5) for x, y in src])
    out = gv.plausible(H, src, dst, (800, 640), (400, 320))
    assert out['ok'], out
    assert out['distinct'] == 64 and out['anisotropy'] == 1.0


def test_points_collapsing_onto_a_few_are_refused():
    # the production case: 37 inliers landing on 5 points of the other image
    src = _grid(37)
    five = np.float32([(100, 100), (103, 100), (100, 104), (104, 104), (102, 102)])
    dst = np.float32([five[i % 5] for i in range(37)])
    H = np.array([[0.26, 0, 90], [0, 0.0073, 100], [0, 0, 1]], dtype='float64')
    out = gv.plausible(H, src, dst, (800, 640), (214, 381))
    assert not out['ok'] and out['why'] == 'points collapse'


def test_squeezed_transform_is_refused():
    src = _grid(64)
    H = np.array([[1.0, 0, 0], [0, 0.1, 0], [0, 0, 1]], dtype='float64')
    dst = np.float32([(x, 0.1 * y) for x, y in src])
    out = gv.plausible(H, src, dst, (800, 640), (800, 640))
    assert not out['ok'] and out['why'] == 'squeezed transform'


def test_matches_confined_to_one_spot_are_refused():
    # a shared logo: plenty of distinct points, all inside 1% of both images
    src = _grid(36, step=4.0)
    H = np.eye(3)
    out = gv.plausible(H, src, src.copy(), (800, 640), (800, 640))
    assert not out['ok'] and out['why'] == 'matches in one spot'


def test_profiles_and_channels_are_listings():
    for u in ('https://www.snapchat.com/@someone',
              'https://www.snapchat.com/add/someone',
              'https://om.linkedin.com/in/some-person-286910376',
              'https://www.linkedin.com/company/acme',
              'https://www.youtube.com/@channel',
              'https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv/videos',
              'https://t.me/somechannel',
              'https://t.me/s/somechannel',
              'https://www.reddit.com/r/pics'):
        assert urls.is_listing(u), u


def test_posts_are_not_listings():
    for u in ('https://www.linkedin.com/posts/some-person_topic-activity-7372549608822038528-Z8S-',
              'https://www.instagram.com/p/DK2uuidoB7V/',
              'https://t.me/somechannel/1234',
              'https://www.youtube.com/watch?v=abcdefghijk',
              'https://www.reddit.com/r/pics/comments/abc/title',
              'https://x.com/someone/status/570514380095299584',
              'https://www.facebook.com/groups/1362264327769433/posts/1955369401792253/'):
        assert not urls.is_listing(u), u


def _sighting(url, level, when=None, date_level='none'):
    return {'url': url, 'canonical': urls.canonical(url), 'title': 't', 'caption': None,
            'image': ImageEvidence(level=level, kind='exact' if level != 'none' else None),
            'date': DateEvidence(when=when, level=date_level), 'match': 'similar',
            'engines': ['lens_visual'], 'thumbs': [], 'copy_ids': set(), 'round': 1}


def _cand(url, match='similar', thumb='https://img.example/t.jpg', **extra):
    return dict({'url': url, 'canonical': urls.canonical(url), 'title': 'row', 'thumb': thumb,
                 'image_url': None, 'match': match, 'engines': ['lens_visual'], 'thumbs': [thumb] if thumb else []},
                **extra)


class _Budget:
    mode = 'quick'

    def snapshot(self):
        return {'seconds': 1.0, 'mode': 'quick'}


def test_unconfirmed_engine_rows_are_listed_and_do_not_decide():
    confirmed = 'https://www.instagram.com/p/DK2uuidoB7V/'
    rejected = 'https://example.com/look-alike'
    unchecked = 'https://example.org/never-opened'
    text_row = 'https://example.net/article'
    sightings = [_sighting(confirmed, 'platform', '2025-06-13T20:55:56Z', 'platform_id'),
                 _sighting(rejected, 'none', '2019-01-01T00:00:00Z', 'structured')]
    cands = [_cand(confirmed, 'exact'), _cand(rejected), _cand(unchecked, 'exact'),
             _cand(text_row, 'text', thumb=None)]
    payload = report.build(sightings, copies=[], engines={}, budget=_Budget(), extras={}, candidates=cands)

    assert payload['first_seen']['url'] == confirmed                 # the rejected 2019 page never decides
    links = [r['link'] for r in payload['similar']]
    assert links == [unchecked, rejected]                            # exact rows first; confirmed and text rows left out
    assert payload['similar'][0]['checked'] is False and payload['similar'][1]['checked'] is True
    assert payload['stats']['candidates'] == 4 and payload['stats']['similar'] == 2


def test_profile_page_is_never_the_first_appearance():
    profile = 'https://www.snapchat.com/@someone'
    post = 'https://www.instagram.com/p/DK2uuidoB7V/'
    sightings = [_sighting(profile, 'page', '2021-10-22T18:26:59Z', 'structured'),
                 _sighting(post, 'platform', '2025-06-13T20:55:56Z', 'platform_id')]
    payload = report.build(sightings, copies=[], engines={}, budget=_Budget(), extras={}, candidates=[])
    assert payload['first_seen']['url'] == post
