"""Origin v2 phase 1: copies, engine answers, page-level verification,
date levels, the one eligibility rule, and the round orchestrator with
fake engines."""
import io

import numpy as np
import pytest
import responses
from PIL import Image, ImageFilter

from origin import copies as cp, dates, engines, report, urls, verify
from origin.budget import Budget


# ------------------------------------------------------------ fixtures

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


def _jpeg(im, q=88):
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=q)
    return buf.getvalue()


def _sig(pil):
    from services.visual_verify import build_query_signature
    s = build_query_signature(pil)
    s['embedding'] = None
    return s


# ------------------------------------------------------------ urls

def test_url_classification():
    assert urls.is_listing('https://www.pinterest.com/uoyuy8733/')
    assert urls.is_listing('https://x.com/svs9111')
    assert not urls.is_listing('https://x.com/svs9111/status/570514380095299584')
    assert urls.is_listing('https://site.example/tag/ships')
    assert urls.is_junk('https://serpapi.com/searches/x/images/y.jpeg') and urls.is_junk('https://lens.google.com/x')
    assert urls.platform_of('https://twitter.com/a/status/1') == 'x'
    assert urls.platform_of('https://it.pinterest.com/pin/1/') == 'pinterest'
    assert urls.platform_of('https://gcaptain.com/a') == 'web'
    assert urls.is_social('https://t.me/s/channel/1') and not urls.is_social('https://news.example/')


# ------------------------------------------------------------ copies

def test_copyset_dedupes_size_variants_and_orders_unsearched():
    cs = cp.CopySet()
    big = _textured(1, (1000, 800))
    a = cs.add('https://a/orig.jpg', big, 'upload')
    b = cs.add('https://a/736x.jpg', big.resize((736, 589)), 'page', found_on='https://p/1')
    assert b is not a and b.source == 'page'               # a page's own file is kept even if it hashes like the upload
    b2 = cs.add('https://a/236x.jpg', big.resize((236, 189)), 'page', found_on='https://p/2')
    assert b2 is b                                         # CDN size variants of the same page copy: one entry
    other = cs.add('https://b/other.jpg', _textured(2, (900, 900)), 'platform', found_on='https://x.com/u/status/1')
    tiny = cs.add('https://c/thumb.jpg', _textured(3, (200, 200)), 'page')
    assert other is not a and tiny is not None
    cs.mark(a, 'lens_exact_en')
    un = cs.unsearched('lens_exact_en')
    assert un == [other, b]                                # largest first; tiny skipped; searched skipped
    assert cs.by_id(other.id) is other and len(cs.briefs()) == 4


def test_small_copy_and_prepare(monkeypatch):
    big = _jpeg(_textured(4, (1600, 900)))
    small = cp.small_copy_bytes(big)
    assert Image.open(io.BytesIO(small)).size == (512, 288)
    assert cp.small_copy_bytes(small) is None
    monkeypatch.setattr(cp, 'host_bytes', lambda data, hint='x': f'https://pub.example/{hint}.jpg')
    monkeypatch.setattr(cp, 'public_url_for_hosted', lambda u: 'https://pub.example/upload.jpg')
    monkeypatch.setenv('SCREENSHOT_CROP', 'false')
    cs, pil, extras = cp.prepare(big, 'https://r2/presigned?X-Amz=1')
    assert [c.source for c in cs.copies] == ['upload', 'small']
    assert cs.copies[0].url == 'https://pub.example/upload.jpg' and cs.copies[1].url == 'https://pub.example/small.jpg'
    assert extras['screenshot'] is False and pil.size == (1600, 900)


# ------------------------------------------------------------ engines

def test_engine_statuses_and_budget(monkeypatch):
    from providers import serpapi
    monkeypatch.setattr(serpapi, 'lens_matches', lambda *a, **k: (_ for _ in ()).throw(serpapi.SerpApiNoResults('x')))
    assert engines.lens_exact('u', copy_id=1).status == 'refused'
    monkeypatch.setattr(serpapi, 'lens_matches', lambda *a, **k: [])
    assert engines.lens_visual('u').status == 'empty'
    monkeypatch.setattr(serpapi, 'lens_matches', lambda *a, **k: [
        {'link': 'https://x.com/a/status/1', 'title': 't', 'thumbnail': 'https://t/1.jpg', 'match_type': 'exact'},
        {'link': 'https://lens.google.com/junk', 'match_type': 'exact'}])
    a = engines.lens_exact('u', copy_id=3)
    assert a.status == 'results' and len(a.candidates) == 1 and a.candidates[0]['copy_id'] == 3
    monkeypatch.setattr(serpapi, 'lens_matches', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    assert engines.lens_exact('u').status == 'error'

    b = Budget(credits=2, seconds=30, pages=10)
    ans = engines.run_parallel([
        ('one', lambda: engines.EngineAnswer('one', 'results', [{'url': 'https://a/1', 'engine': 'one', 'match': 'exact', 'copy_id': 1}], 1), 1),
        ('two', lambda: engines.EngineAnswer('two', 'empty', [], 1), 1),
        ('three', lambda: engines.EngineAnswer('three', 'results', [], 1), 1),
    ], b)
    assert ans['three'].status == 'skipped' and b.spent_credits == 2 and b.skipped[0]['step'] == 'three'
    merged = engines.merge_candidates(ans.values())
    assert merged[0]['canonical'] == 'https://a/1' and merged[0]['engines'] == ['one']


def test_merge_and_rank():
    a1 = engines.EngineAnswer('lens_exact_en', 'results', [
        {'url': 'https://news.example/story?utm_source=x', 'engine': 'lens_exact_en', 'match': 'exact', 'thumb': 'https://t/a.jpg', 'copy_id': 1},
        {'url': 'https://site.example/tag/ships', 'engine': 'lens_exact_en', 'match': 'exact', 'copy_id': 1}])
    a2 = engines.EngineAnswer('yandex', 'results', [
        {'url': 'https://news.example/story', 'engine': 'yandex', 'match': 'similar', 'thumb': 'https://t/b.jpg', 'copy_id': 1},
        {'url': 'https://x.com/u/status/9', 'engine': 'yandex', 'match': 'similar', 'copy_id': 1}])
    merged = engines.merge_candidates([a1, a2])
    story = next(m for m in merged if 'news.example' in m['url'])
    assert story['engines'] == ['lens_exact_en', 'yandex'] and story['match'] == 'exact' and len(story['thumbs']) == 2
    ranked = engines.rank_candidates(merged)
    assert ranked[0]['url'].startswith('https://news.example')          # exact + two engines first
    assert ranked[-1]['url'] == 'https://site.example/tag/ships'        # listing last


# ------------------------------------------------------------ verify

@responses.activate
def test_verify_page_levels(monkeypatch):
    photo = _textured(5)
    sigs = [_sig(photo)]
    other = _textured(6)
    # a) page image matches -> page level, matched_pil returned
    responses.add(responses.GET, 'https://page.example/post', body='<html><img src="https://page.example/p.jpg"></html>', content_type='text/html')
    responses.add(responses.GET, 'https://page.example/p.jpg', body=_jpeg(photo.crop((40, 30, 600, 450))), content_type='image/jpeg')
    v = verify.verify_page('https://page.example/post', sigs, engine_thumbs=['https://t/1.jpg'])
    assert v['image'].level == 'page' and v['image'].kind == 'variant' and v['matched_pil'] is not None
    # b) page shows another picture; engine thumb matches -> engine claim is NOT accepted
    responses.add(responses.GET, 'https://page2.example/post', body='<html><img src="https://page2.example/o.jpg"></html>', content_type='text/html')
    responses.add(responses.GET, 'https://page2.example/o.jpg', body=_jpeg(other), content_type='image/jpeg')
    responses.add(responses.GET, 'https://t/2.jpg', body=_jpeg(photo), content_type='image/jpeg')
    v = verify.verify_page('https://page2.example/post', sigs, engine_thumbs=['https://t/2.jpg'])
    assert v['image'].level == 'none' and v['image'].note == 'page images differ'
    # c) JS-only page (no images) -> engine claim kept as a claim
    responses.add(responses.GET, 'https://js.example/post', body='<html><div id=app></div></html>', content_type='text/html')
    v = verify.verify_page('https://js.example/post', sigs, engine_thumbs=['https://t/2.jpg'])
    assert v['image'].level == 'engine_claim' and v['image'].kind == 'exact'
    # d) X post: syndication photo is platform-level and returns caption + time
    from providers import tweet
    monkeypatch.setattr(tweet, 'tweet_info', lambda url: {'id': '1', 'user': 'u', 'text': 'caption here',
                                                          'created_at': '2015-02-25T09:23:22.000Z',
                                                          'photos': ['https://pbs.example/x.jpg']})
    responses.add(responses.GET, 'https://pbs.example/x.jpg', body=_jpeg(photo), content_type='image/jpeg')
    responses.add(responses.GET, 'https://x.com/u/status/1', body='<html></html>', content_type='text/html')
    v = verify.verify_page('https://x.com/u/status/1', sigs)
    assert v['image'].level == 'platform' and v['caption'] == 'caption here' and v['created_at'].startswith('2015')
    d = dates.for_page('https://x.com/u/status/1', v['html'], None, tweet=v['tweet'])
    assert d.level == 'platform_id' and d.when.startswith('2015-02-25T09:23:22')


# ------------------------------------------------------------ dates

def test_date_levels():
    html_structured = '<html><head><meta property="article:published_time" content="2024-07-19T19:20:46+00:00"></head></html>'
    d = dates.for_page('https://news.example/story', html_structured, None)
    assert d.level == 'structured' and d.when.startswith('2024-07-19T19:20:46')
    d = dates.for_page('https://x.com/a/status/1814337329387175999', None, None)
    assert d.level == 'platform_id' and d.when.startswith('2024-07-19T16:31:42')
    d = dates.for_page('https://site.example/tag/ships', html_structured, None)
    assert d.level == 'weak'                                            # listing: never an origin
    d = dates.for_page('https://old.example/p', None, {'Last-Modified': 'Tue, 22 Sep 2026 10:00:00 GMT'})
    assert d.level in ('weak', 'none')
    d = dates.for_page('https://no.example/p', '<html></html>', None, crawl_date='2020-01-05T00:00:00Z')
    assert d.level == 'none' and d.upper_bound and d.upper_bound.startswith('2020-01-05')
    assert dates.confidence_of('platform_id') == 0.98 and dates.confidence_of('none') is None


# ------------------------------------------------------------ report / rule

def _sight(url, ilevel, dlevel, when, kind='exact', engines_=('lens_exact_en',)):
    return {'url': url, 'canonical': urls.canonical(url), 'title': 't', 'caption': None,
            'image': verify.ImageEvidence(level=ilevel, kind=kind, matched_url='https://m/1.jpg', width=800, height=600),
            'date': dates.DateEvidence(level=dlevel, when=when, sources=[]),
            'match': 'exact', 'engines': list(engines_), 'thumbs': [], 'copy_ids': {1}, 'round': 1}


def test_eligibility_rule_and_payload_shape():
    s_origin = _sight('https://x.com/icg/status/1', 'platform', 'platform_id', '2024-07-19T16:31:42Z', 'variant')
    s_claim = _sight('https://www.facebook.com/VOANews/posts/1', 'engine_claim', 'platform_id', '2021-05-28T08:00:00Z')
    s_weak = _sight('https://blog.example/p', 'page', 'weak', '2019-01-01T00:00:00Z')
    s_listing = _sight('https://site.example/tag/ships', 'page', 'structured', '2020-01-01T00:00:00Z')
    s_exact_later = _sight('https://news.example/story', 'page', 'structured', '2024-07-19T16:43:55Z')
    assert report.eligible(s_origin) and not report.eligible(s_claim) and not report.eligible(s_weak) and not report.eligible(s_listing)
    b = Budget(seconds=10, credits=12, pages=60)
    p = report.build([s_claim, s_weak, s_listing, s_exact_later, s_origin], copies=[], engines={}, budget=b, extras={})
    assert p['engine'] == 'origin_engine' and p['version'] == 2 and p['success']
    assert p['first_seen']['link'] == 'https://x.com/icg/status/1'
    assert p['first_seen']['image_level'] == 'platform' and p['first_seen']['visual']['verdict'] == 'confirmed'
    assert p['first_seen_exact']['link'] == 'https://news.example/story' and p['version_note']
    assert [i['link'] for i in p['timeline']][:2] == ['https://blog.example/p', 'https://site.example/tag/ships']
    assert {l['link'] for l in p['leads']} == {'https://www.facebook.com/VOANews/posts/1', 'https://blog.example/p', 'https://site.example/tag/ships'}
    item = p['timeline'][0]
    for k in ('title', 'link', 'thumbnail', 'source', 'published_at', 'confidence', 'visual', 'date_text', 'type'):
        assert k in item
    claim = next(l for l in p['leads'] if 'VOANews' in l['link'])
    assert claim['visual']['verdict'] == 'ambiguous' and claim['image_level'] == 'engine_claim'


# ------------------------------------------------------------ orchestrator

def test_investigate_rounds_with_fake_engines(monkeypatch):
    from origin import investigate as inv_mod
    photo = _textured(7, (1200, 900))
    upload = _jpeg(photo)
    monkeypatch.setenv('SERPAPI_API_KEY', 'k')
    monkeypatch.setenv('SCREENSHOT_CROP', 'false')
    monkeypatch.setattr(inv_mod, '_download', lambda url: upload)
    monkeypatch.setattr(cp, 'host_bytes', lambda data, hint='x': f'https://pub.example/{hint}.jpg')
    monkeypatch.setattr(cp, 'public_url_for_hosted', lambda u: 'https://pub.example/upload.jpg')

    calls = []

    def fake_lens_exact(url, hl='en', country='us', copy_id=None, no_cache=False):
        calls.append(('lens_exact', hl, url))
        if 'upload' in url:      # the upload is refused by Google
            return engines.EngineAnswer(f'lens_exact_{hl}', 'refused', [], 1, copy_id=copy_id)
        if 'small' in url:
            return engines.EngineAnswer(f'lens_exact_{hl}', 'results', [
                {'url': 'https://pin.example/pin/1', 'engine': 'lens', 'match': 'exact', 'copy_id': copy_id,
                 'thumb': 'https://t/1.jpg'}], 1, copy_id=copy_id)
        # searching with the page copy finds the X origin
        return engines.EngineAnswer(f'lens_exact_{hl}', 'results', [
            {'url': 'https://x.com/orig/status/570514380095299584', 'engine': 'lens', 'match': 'exact', 'copy_id': copy_id}],
            1, copy_id=copy_id)

    def fake_lens_visual(url, hl='en', country='us', copy_id=None, no_cache=False):
        calls.append(('lens_visual', url))
        return engines.EngineAnswer('lens_visual', 'refused' if 'upload' in url else 'results', [], 1, copy_id=copy_id)

    monkeypatch.setattr(engines, 'lens_exact', fake_lens_exact)
    monkeypatch.setattr(engines, 'lens_visual', fake_lens_visual)
    monkeypatch.setattr(engines, 'yandex', lambda url, copy_id=None: engines.EngineAnswer('yandex', 'empty', [], 1, copy_id=copy_id))
    monkeypatch.setattr(engines, 'tineye', lambda url, copy_id=None: engines.EngineAnswer('tineye', 'skipped', note='not configured'))

    def fake_verify(url, sigs, engine_thumbs=(), **k):
        v = {'url': url, 'image': verify.ImageEvidence(), 'html': '<html></html>', 'headers': None,
             'title': 't', 'caption': None, 'created_at': None, 'extra_dates': [], 'tweet': None,
             'matched_pil': None, 'fetch_error': False}
        if 'pin.example' in url:
            v['image'] = verify.ImageEvidence(level='page', kind='variant', matched_url='https://pinimg.example/orig.jpg',
                                              width=1000, height=800, inliers=120)
            v['matched_pil'] = photo.resize((1000, 800))
            v['html'] = '<html><head><meta property="article:published_time" content="2022-02-01T12:57:53+00:00"></head></html>'
        if 'x.com/orig' in url:
            v['image'] = verify.ImageEvidence(level='platform', kind='variant', matched_url='https://pbs.example/o.jpg',
                                              width=1024, height=1024, inliers=250)
            v['matched_pil'] = photo.resize((1024, 1024))
            v['tweet'] = {'created_at': '2015-02-25T09:23:22.000Z', 'text': 'صورة قديمة'}
            v['caption'] = 'صورة قديمة'
        return v
    monkeypatch.setattr(verify, 'verify_page', fake_verify)

    payload = inv_mod.investigate('https://r2/upload.jpg?X-Amz=1', progress=lambda m: None)
    assert payload['success'] and payload['first_seen']['link'] == 'https://x.com/orig/status/570514380095299584'
    assert payload['first_seen']['published_at'].startswith('2015-02-25T09:23:22')
    assert payload['first_seen']['image_level'] == 'platform' and payload['first_seen']['date_level'] == 'platform_id'
    assert payload['version_note']
    assert payload['engines']['lens_visual']['status'] == 'refused' and payload['engines']['lens_visual@small']['status'] == 'results'
    assert payload['engines']['lens_exact_en']['status'] == 'refused'            # visual refused too => really refused
    assert payload['budget']['credits'] <= 12
    assert [c['source'] for c in payload['copies']][:2] == ['upload', 'small']
    assert any(c['source'] == 'page' for c in payload['copies'])                 # the pin's original joined the set
    assert any(r.get('copies') for r in payload['rounds'])                       # round 2 ran on it
    links = [i['link'] for i in payload['timeline']]
    assert links[0] == 'https://x.com/orig/status/570514380095299584' and 'https://pin.example/pin/1' in links


def test_rank_uses_date_hints_thumb_verdicts_and_social_cap():
    cands = []
    for i in range(15):
        # 15 X posts with ascending ids => the EARLIEST (smallest snowflake) must come first
        tid = 1814337329387175999 + i * 4194304000   # ~+1000 s each
        cands.append({'url': f'https://x.com/u{i}/status/{tid}', 'engine': 'lens', 'match': 'exact',
                      'engines': ['lens'], 'thumbs': []})
    cands.append({'url': 'https://news.example/a', 'engine': 'lens', 'match': 'exact', 'engines': ['lens'], 'thumbs': [],
                  'thumb_check': {'verdict': 'differs'}})
    cands.append({'url': 'https://blog.example/b', 'engine': 'yandex', 'match': 'similar', 'engines': ['yandex'], 'thumbs': [],
                  'thumb_check': {'verdict': 'match'}})
    ranked = engines.rank_candidates(cands, per_domain=3, limit=20)
    assert ranked[0]['url'] == 'https://x.com/u0/status/1814337329387175999'  # earliest dated post first
    assert sum(1 for c in ranked[:12] if 'x.com' in c['url']) == 12           # social cap 12, in id order
    assert ranked[12]['url'] == 'https://blog.example/b'                      # then the thumbnail match
    assert ranked[-1]['url'] == 'https://news.example/a'                      # thumbnail differs: last
    assert engines.date_hint(cands[0]).startswith('2024-07-19T16:31:42')


def test_prescreen_marks_thumbnail_matches(monkeypatch):
    from origin import prescreen
    photo = _textured(9)
    sigs = [_sig(photo)]
    imgs = {'https://t/match.jpg': photo.resize((320, 240)), 'https://t/other.jpg': _textured(10).resize((320, 240))}
    monkeypatch.setattr(prescreen, '_fetch', lambda url: imgs[url])
    cands = [{'url': 'https://a/1', 'thumbs': ['https://t/match.jpg']},
             {'url': 'https://a/2', 'thumbs': ['https://t/other.jpg']},
             {'url': 'https://a/3', 'thumbs': []}]
    counts = prescreen.run(cands, sigs, time_left_s=60)
    assert cands[0]['thumb_check']['verdict'] == 'match' and cands[1]['thumb_check']['verdict'] == 'differs'
    assert cands[2]['thumb_check']['verdict'] == 'unknown' and counts['match'] == 1 and counts['differs'] == 1


# ------------------------------------------------------------ phase 2: identification

def test_identify_text_pool_queries_and_search(monkeypatch):
    from origin import identify
    from providers import deepseek, xai
    cands = [{'url': 'https://x.com/a/status/1', 'title': 'ذكريات الماضي on X: الفنان عبدالمجيد عبدالله والفنان نبيل شعيل'},
             {'url': 'https://lens.google.com/x', 'title': 'junk'},
             {'url': 'https://p.example/2', 'title': 'Discover 17 ideas'}]
    sights = [{'image': verify.ImageEvidence(level='platform'), 'caption': 'صورة قديمة ل عبدالمجيد عبدالله و نبيل شعيل و راشد الماجد', 'title': 't'},
              {'image': verify.ImageEvidence(level='none'), 'caption': 'ignored', 'title': 'ignored'}]
    titles, captions = identify.text_pool(cands, sights)
    assert len(titles) == 2 and 'junk' not in titles and captions == ['صورة قديمة ل عبدالمجيد عبدالله و نبيل شعيل و راشد الماجد', 't']

    monkeypatch.setattr(deepseek, 'configured', lambda: True)
    monkeypatch.setattr(deepseek, 'chat_json', lambda system, user, **k: {
        'people': ['عبدالمجيد عبدالله', 'نبيل شعيل', 'راشد الماجد'], 'place': None, 'place_ar': None,
        'event': None, 'event_ar': None, 'detail': 'Pepsi can',
        'queries_ar': ['عبدالمجيد عبدالله نبيل شعيل راشد الماجد بيبسي صورة'], 'queries_en': ['Abdul Majeed Abdullah Nabeel Shuail Pepsi photo'],
        'x_question': 'earliest X post of this photo', 'confidence': 'high'})
    ident = identify.identify('', titles, captions)
    assert ident['label'] == 'استنتاج' and identify.queries_of(ident) == [
        'عبدالمجيد عبدالله نبيل شعيل راشد الماجد بيبسي صورة', 'Abdul Majeed Abdullah Nabeel Shuail Pepsi photo',
        'عبدالمجيد عبدالله نبيل شعيل راشد الماجد Pepsi can site:x.com']

    seen_q = []
    monkeypatch.setattr(engines, 'google_text', lambda q, hl='en', gl='us', num=20: seen_q.append((q, hl)) or
                        engines.EngineAnswer('text', 'results', [{'url': 'https://x.com/svs9111/status/570514380095299584',
                                                                  'engine': 'text', 'match': 'text', 'copy_id': None}], 1))
    b = Budget(credits=12, seconds=60, pages=10)
    ans = identify.text_search(ident, b)
    assert set(ans) == {'text1', 'text2', 'text3'} and b.spent_credits == 3 and seen_q[0][1] == 'ar' and seen_q[1][1] == 'en'
    assert seen_q[2][0].endswith('site:x.com')

    monkeypatch.setattr(xai, 'configured', lambda: True)
    monkeypatch.setattr(xai, 'search_origin', lambda img, q: {'urls': ['https://x.com/svs9111/status/570514380095299584', 'https://google.com/x'], 'text': 'ok'})
    g = identify.grok_search(ident, b'img')
    assert g.status == 'results' and len(g.candidates) == 1 and g.credits == 0
    monkeypatch.setattr(xai, 'search_origin', lambda img, q: {'error': 'no credits', 'urls': []})
    assert identify.grok_search(ident, b'img').status == 'error'
    monkeypatch.setattr(xai, 'configured', lambda: False)
    assert identify.grok_search(ident, b'img').status == 'skipped'


def test_investigate_identification_track_reaches_the_x_post(monkeypatch):
    """Engines never return the X post (as with the Maersk photo); the
    identification track's text search does; it gets verified and wins."""
    from origin import investigate as inv_mod, identify
    photo = _textured(8, (1000, 700))
    upload = _jpeg(photo)
    monkeypatch.setenv('SERPAPI_API_KEY', 'k')
    monkeypatch.setenv('SCREENSHOT_CROP', 'false')
    monkeypatch.setattr(inv_mod, '_download', lambda url: upload)
    monkeypatch.setattr(cp, 'host_bytes', lambda data, hint='x': f'https://pub.example/{hint}.jpg')
    monkeypatch.setattr(cp, 'public_url_for_hosted', lambda u: 'https://pub.example/upload.jpg')
    monkeypatch.setattr(engines, 'lens_exact', lambda url, hl='en', country='us', copy_id=None, no_cache=False:
                        engines.EngineAnswer(f'lens_exact_{hl}', 'results', [
                            {'url': 'https://news.example/story', 'engine': 'lens', 'match': 'exact', 'copy_id': copy_id,
                             'title': 'Indian Coast Guard battles fire on Maersk Frankfurt'}], 1, copy_id=copy_id))
    monkeypatch.setattr(engines, 'lens_visual', lambda url, hl='en', country='us', copy_id=None, no_cache=False:
                        engines.EngineAnswer('lens_visual', 'empty', [], 1, copy_id=copy_id))
    monkeypatch.setattr(engines, 'yandex', lambda url, copy_id=None: engines.EngineAnswer('yandex', 'empty', [], 1, copy_id=copy_id))
    monkeypatch.setattr(engines, 'tineye', lambda url, copy_id=None: engines.EngineAnswer('tineye', 'skipped', note='not configured'))
    monkeypatch.setattr(identify, 'describe', lambda b: 'a container ship on fire')
    monkeypatch.setattr(identify, 'identify', lambda d, t, c: {'people': [], 'event': 'Maersk Frankfurt fire', 'event_ar': 'حريق سفينة',
                                                               'queries_ar': ['حريق سفينة ميرسك فرانكفورت صورة'], 'queries_en': ['Maersk Frankfurt fire Indian Coast Guard photo'],
                                                               'x_question': 'earliest post', 'label': 'استنتاج'})
    monkeypatch.setattr(engines, 'google_text', lambda q, hl='en', gl='us', num=20: engines.EngineAnswer('text', 'results', [
        {'url': 'https://x.com/IndiaCoastGuard/status/1814337329387175999', 'engine': 'text', 'match': 'text', 'copy_id': None}], 1))
    monkeypatch.setattr(identify, 'grok_search', lambda ident, b, progress=None: engines.EngineAnswer('grok', 'skipped', note='not configured'))

    def fake_verify(url, sigs, engine_thumbs=(), **k):
        v = {'url': url, 'image': verify.ImageEvidence(), 'html': '<html></html>', 'headers': None, 'title': 't',
             'caption': None, 'created_at': None, 'extra_dates': [], 'tweet': None, 'matched_pil': None, 'fetch_error': False}
        if 'news.example' in url:
            v['image'] = verify.ImageEvidence(level='page', kind='exact', matched_url='https://news.example/i.jpg', width=1200, height=800)
            v['html'] = '<html><head><meta property="article:published_time" content="2024-07-19T19:20:46+00:00"></head></html>'
        if 'IndiaCoastGuard' in url:
            v['image'] = verify.ImageEvidence(level='platform', kind='variant', matched_url='https://pbs.example/icg.jpg', width=1024, height=768, inliers=235)
            v['tweet'] = {'created_at': '2024-07-19T16:31:42.000Z', 'text': 'ICG ships fighting fire'}
        return v
    monkeypatch.setattr(verify, 'verify_page', fake_verify)

    payload = inv_mod.investigate('https://r2/upload.jpg?X-Amz=1', progress=lambda m: None)
    assert payload['first_seen']['link'] == 'https://x.com/IndiaCoastGuard/status/1814337329387175999'
    assert payload['first_seen']['published_at'].startswith('2024-07-19T16:31:42')
    assert payload['identity']['event'] == 'Maersk Frankfurt fire' and payload['identity']['label'] == 'استنتاج'
    assert payload['engines']['text1']['status'] == 'results' and payload['budget']['credits'] <= 12
    assert any(r.get('round') == 'identify' for r in payload['rounds'])


def test_round_one_leaves_pages_for_later_rounds():
    from origin import investigate as inv_mod
    b = Budget(seconds=60, credits=12, pages=50)
    inv = inv_mod.Investigation('https://img', lambda m: None, b)
    inv.sigs = [object()]
    inv._verify_one = lambda c, r: None
    cands = [{'url': f'https://s{i}.example/p', 'canonical': f'https://s{i}.example/p'} for i in range(60)]
    inv.verify_many(cands, 1, reserve=30)
    assert b.spent_pages == 20 and b.skipped[0]['step'] == 'verify round 1' and 'not fetched' in b.skipped[0]['reason']
    inv.verify_many(cands[:25], 4, time_cap=5)
    assert b.spent_pages == 45                         # later rounds still get their pages


# ------------------------------------------------------------ phase 3: video

@responses.activate
def test_verify_reports_which_frame_matched():
    f0, f1 = _textured(31), _textured(32)
    sigs = [_sig(f0), _sig(f1)]
    responses.add(responses.GET, 'https://page.example/v', body='<html><img src="https://page.example/f1.jpg"></html>', content_type='text/html')
    responses.add(responses.GET, 'https://page.example/f1.jpg', body=_jpeg(f1.crop((30, 20, 600, 460))), content_type='image/jpeg')
    v = verify.verify_page('https://page.example/v', sigs)
    assert v['image'].level == 'page' and v['image'].frame == 1


def test_video_investigation_scenes(monkeypatch):
    from origin import investigate as inv_mod, identify
    f0, f1 = _textured(33, (1000, 700)), _textured(34, (1000, 700))
    data = {'https://r2/f0.jpg': _jpeg(f0), 'https://r2/f1.jpg': _jpeg(f1)}
    monkeypatch.setenv('SERPAPI_API_KEY', 'k')
    monkeypatch.setenv('SCREENSHOT_CROP', 'false')
    monkeypatch.setattr(inv_mod, '_download', lambda url: data[url.split('?')[0]])
    monkeypatch.setattr(cp, 'host_bytes', lambda d, hint='x': f'https://pub.example/{hint}.jpg')
    monkeypatch.setattr(cp, 'public_url_for_hosted', lambda u: u.split('?')[0].replace('r2/', 'pub.example/'))
    searched = []
    monkeypatch.setattr(engines, 'lens_exact', lambda url, hl='en', country='us', copy_id=None, no_cache=False:
                        searched.append((url, hl)) or engines.EngineAnswer(f'lens_exact_{hl}', 'results', [
                            {'url': 'https://x.com/a/status/1814337329387175999' if 'f0' in url else 'https://x.com/b/status/1814515949699322069',
                             'engine': 'lens', 'match': 'exact', 'copy_id': copy_id}], 1, copy_id=copy_id))
    monkeypatch.setattr(engines, 'lens_visual', lambda url, hl='en', country='us', copy_id=None, no_cache=False: engines.EngineAnswer('lens_visual', 'empty', [], 1, copy_id=copy_id))
    monkeypatch.setattr(engines, 'yandex', lambda url, copy_id=None: engines.EngineAnswer('yandex', 'empty', [], 1, copy_id=copy_id))
    monkeypatch.setattr(engines, 'tineye', lambda url, copy_id=None: engines.EngineAnswer('tineye', 'skipped', note='not configured'))
    monkeypatch.setattr(identify, 'describe', lambda b: '')
    monkeypatch.setattr(identify, 'identify', lambda d, t, c: None)

    def fake_verify(url, sigs, engine_thumbs=(), **k):
        v = {'url': url, 'image': verify.ImageEvidence(), 'html': '<html></html>', 'headers': None, 'title': 't',
             'caption': None, 'created_at': None, 'extra_dates': [], 'tweet': None, 'matched_pil': None, 'fetch_error': False}
        frame = 0 if '/a/' in url else 1
        v['image'] = verify.ImageEvidence(level='platform', kind='exact', matched_url=f'https://pbs.example/{frame}.jpg', width=1000, height=700, frame=frame)
        v['tweet'] = {'created_at': '2024-07-19T16:31:42.000Z' if frame == 0 else '2024-07-20T04:21:26.000Z', 'text': 't'}
        return v
    monkeypatch.setattr(verify, 'verify_page', fake_verify)

    payload = inv_mod.investigate('https://r2/f0.jpg?X=1', progress=lambda m: None, extra_frame_urls=['https://r2/f1.jpg?X=1'])
    assert any('f1' in u for u, hl in searched)                                     # the second frame got its own Lens search
    assert payload['first_seen']['link'] == 'https://x.com/a/status/1814337329387175999'
    assert [s['frame'] for s in payload['scenes']] == [1, 2]
    assert payload['scenes'][1]['first_seen']['link'] == 'https://x.com/b/status/1814515949699322069'
    assert payload['stats']['frames'] == 2 and payload['budget']['credits'] <= 20


def test_thin_lens_answer_is_retried_uncached_once(monkeypatch):
    from origin import investigate as inv_mod, identify
    photo = _textured(41, (900, 700))
    monkeypatch.setenv('SERPAPI_API_KEY', 'k'); monkeypatch.setenv('SCREENSHOT_CROP', 'false')
    monkeypatch.setattr(inv_mod, '_download', lambda url: _jpeg(photo))
    monkeypatch.setattr(inv_mod, '_prior_sightings', lambda sig: [])
    monkeypatch.setattr(inv_mod, '_remember', lambda d, u, p: None)
    monkeypatch.setattr(cp, 'host_bytes', lambda d, hint='x': f'https://pub.example/{hint}.jpg')
    monkeypatch.setattr(cp, 'public_url_for_hosted', lambda u: 'https://pub.example/upload.jpg')
    calls = []
    monkeypatch.setattr(engines, 'lens_exact', lambda url, hl='en', country='us', copy_id=None, no_cache=False:
                        calls.append((hl, no_cache)) or engines.EngineAnswer(f'lens_exact_{hl}', 'results', [
                            {'url': 'https://news.example/one', 'engine': 'lens', 'match': 'exact', 'copy_id': copy_id}], 1, copy_id=copy_id))
    monkeypatch.setattr(engines, 'lens_visual', lambda url, hl='en', country='us', copy_id=None, no_cache=False: engines.EngineAnswer('lens_visual', 'empty', [], 1, copy_id=copy_id))
    monkeypatch.setattr(engines, 'yandex', lambda url, copy_id=None: engines.EngineAnswer('yandex', 'empty', [], 1, copy_id=copy_id))
    monkeypatch.setattr(engines, 'tineye', lambda url, copy_id=None: engines.EngineAnswer('tineye', 'skipped', note='n/c'))
    monkeypatch.setattr(identify, 'describe', lambda b: '')
    monkeypatch.setattr(identify, 'identify', lambda d, t, c: None)
    monkeypatch.setattr(verify, 'verify_page', lambda url, sigs, engine_thumbs=(), **k: {
        'url': url, 'image': verify.ImageEvidence(), 'html': '', 'headers': None, 'title': 't', 'caption': None,
        'created_at': None, 'extra_dates': [], 'tweet': None, 'matched_pil': None, 'fetch_error': False})
    payload = inv_mod.investigate('https://r2/u.jpg?X=1', progress=lambda m: None)
    assert ('en', True) in calls and ('ar', True) in calls                     # both thin answers retried uncached
    assert payload['engines']['lens_exact_en@retry']['status'] == 'results'
    assert payload['first_seen'] is None and payload['prior_sightings'] == []
