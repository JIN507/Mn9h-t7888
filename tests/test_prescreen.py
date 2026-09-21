"""Thumbnail pre-screen: candidates are ranked by comparing the engine
thumbnail to the query before any page fetch; clear misses are dropped."""
import io

import numpy as np

from services import origin_engine as oe
from services.visual_verify import build_query_signature


def _img(seed, size=(256, 256)):
    from PIL import Image
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, (size[1] // 8, size[0] // 8, 3), dtype='uint8')
    return Image.fromarray(arr, 'RGB').resize(size, Image.NEAREST)


def _png(pil):
    buf = io.BytesIO()
    pil.save(buf, format='PNG')
    return buf.getvalue()


def _cand(url, thumb, mt='similar'):
    return {'url': url, 'canonical': url, 'domain': oe.domain_of(url), 'match_type': mt,
            'providers': ['google_lens'], 'engine_images': [thumb] if thumb else [],
            'thumbnail': thumb, 'crawl_date': None, 'is_image': False, 'frames': [1]}


def test_prescreen_ranks_real_matches_first_and_drops_misses(monkeypatch):
    monkeypatch.setattr('services.visual_verify.encoder_available', lambda: False)
    query = _img(1)
    sig = build_query_signature(_png(query))
    same = query.resize((120, 90))                      # engine thumb of the same photo
    other = _img(2).resize((120, 90))                   # thumb of a different photo
    thumbs = {'https://t/same.jpg': same, 'https://t/other.jpg': other}
    monkeypatch.setattr(oe, '_fetch_thumb', lambda url, timeout=None: thumbs.get(url))
    # no encoder in tests: pHash decides matches; a "reject" needs an embedding,
    # so a hash miss stays 'unknown' (kept, ranked by the old heuristics)
    cands = [_cand('https://blog.example/other', 'https://t/other.jpg', 'exact'),
             _cand('https://news.example/same', 'https://t/same.jpg', 'similar'),
             _cand('https://nothumb.example/p', None, 'exact')]
    matches, rejects, unknown = oe.prescreen_candidates(cands, sig)
    assert matches == 1 and rejects == 0
    assert cands[1]['prescreen']['verdict'] == 'match'
    assert cands[1]['prescreen']['phash_distance'] <= oe.PRESCREEN_MATCH_PHASH
    assert cands[0]['prescreen']['verdict'] == 'unknown'
    assert cands[2]['prescreen']['verdict'] == 'unknown'
    ranked = oe.prioritize(cands, 10, 3)
    assert ranked[0]['url'] == 'https://news.example/same'      # thumbnail match beats 'exact' label


def test_prescreen_reject_with_embedding_drops_candidate(monkeypatch):
    monkeypatch.setattr(oe, '_fetch_thumb', lambda url, timeout=None: _img(9))
    monkeypatch.setattr(oe, 'embed_image', lambda pil: np.array([0.0, 1.0]))
    sig = {'phash': None, 'dhash': None, 'embedding': np.array([1.0, 0.0])}
    monkeypatch.setattr(oe, '_hash_distance', lambda s, pil: 30)
    keep_tineye = _cand('https://old.example/p', 'https://t/x.jpg')
    keep_tineye['crawl_date'] = '2019-01-01T00:00:00Z'
    cands = [_cand('https://lookalike.example/p', 'https://t/x.jpg', 'exact'), keep_tineye]
    matches, rejects, _ = oe.prescreen_candidates(cands, sig)
    assert rejects == 2 and matches == 0
    ranked = oe.prioritize(cands, 10, 3)
    assert [c['url'] for c in ranked] == ['https://old.example/p']   # dated TinEye row survives


def test_prescreen_without_signature_or_thumbs_is_noop():
    cands = [_cand('https://a.example', None)]
    assert oe.prescreen_candidates(cands, None) == (0, 0, 1)
    assert oe.prescreen_candidates(cands, {'phash': 'p'}) == (0, 0, 1)
    assert cands[0]['prescreen']['verdict'] == 'unknown'
