"""Origin Engine: tier-0 hygiene, candidate ranking, first-seen assessment,
and a full investigate_origin() run against fake engines and fake pages.

Every network-facing function is monkeypatched at the engine's import site
so the loop's logic is exercised deterministically."""
import pytest

from services import origin_engine as oe


# ----------------------------------------------------------------- tier 0

def test_canonical_url_strips_tracking_www_mobile_and_slash():
    assert oe.canonical_url('http://www.News.example/a/?utm_source=x&id=2') \
        == 'https://news.example/a?id=2'
    assert oe.canonical_url('https://m.site.example/p') == 'https://site.example/p'
    assert oe.canonical_url('ftp://x') is None
    assert oe.canonical_url('') is None


def test_is_listing_url_and_social():
    for u in ('https://economictimes.indiatimes.com/topic/merchant-navy',
              'https://gcaptain.com/author/mike/page/13/',
              'https://site.example/tag/fire', 'https://site.example/',
              'https://site.example/news?page=3'):
        assert oe.is_listing_url(u), u
    for u in ('https://gcaptain.com/major-fire-breaks-out/',
              'https://x.com/IndiaCoastGuard/status/1814337329387175999',
              'https://news.example/2024/07/19/story'):
        assert not oe.is_listing_url(u), u
    assert oe.is_social('https://x.com/a/status/1') and not oe.is_social('https://news.example/a')


def test_listing_pages_never_first_and_rank_last():
    listing = _item('https://news.example/topic/x', '2016-01-01T00:00:00Z', 0.99, 'confirmed')
    listing['is_listing'] = True
    article = _item('https://news.example/2024/07/20/story', '2024-07-20T00:00:00Z', 0.9, 'confirmed')
    assert oe.assess([listing, article])['url'] == article['url']
    cands = [{'url': 'https://a.example/topic/x', 'canonical': 'https://a.example/topic/x',
              'domain': 'a.example', 'match_type': 'exact', 'providers': ['tineye_web'],
              'crawl_date': '2019', 'is_image': False},
             {'url': 'https://x.com/u/status/1', 'canonical': 'https://x.com/u/status/1',
              'domain': 'x.com', 'match_type': 'exact', 'providers': ['google_lens'],
              'crawl_date': None, 'is_image': False}]
    assert oe.prioritize(cands, 2, 3)[0]['url'] == 'https://x.com/u/status/1'


def test_is_junk_and_image_url():
    assert oe.is_junk('https://lens.google.com/x')
    assert oe.is_junk('https://web.archive.org/web/2020/x')
    assert not oe.is_junk('https://news.example/x')
    assert oe.is_image_url('https://cdn.example/a/b.JPG')
    assert not oe.is_image_url('https://cdn.example/a/b')


def test_merge_candidates_dedupes_and_keeps_best_bucket():
    raw = [
        {'link': 'https://www.news.example/story?utm_x=1', 'title': '',
         'match_type': 'similar', 'provider': 'yandex', 'thumbnail': 'https://t/1'},
        {'link': 'https://news.example/story', 'title': 'Story',
         'match_type': 'exact', 'provider': 'google_lens',
         'image_url': 'https://news.example/full.jpg'},
        {'link': 'https://google.com/search?q=x', 'match_type': 'exact', 'provider': 'x'},
        {'link': 'https://news.example/story', 'match_type': 'exact',
         'provider': 'tineye', 'crawl_date': '2019-01-03T00:00:00'},
    ]
    merged = oe.merge_candidates(raw)
    assert len(merged) == 1
    c = merged[0]
    assert c['match_type'] == 'exact'
    assert c['providers'] == ['yandex', 'google_lens', 'tineye']
    assert c['title'] == 'Story'
    assert 'https://news.example/full.jpg' in c['engine_images']
    assert c['crawl_date'] == '2019-01-03T00:00:00'
    # already-seen canonical URLs are skipped in later rounds
    assert oe.merge_candidates(raw, seen={c['canonical']}) == []


def test_prioritize_orders_and_caps_per_domain():
    def cand(url, mt, providers=(), crawl=None):
        return {'url': url, 'canonical': url, 'domain': oe.domain_of(url),
                'match_type': mt, 'providers': list(providers),
                'crawl_date': crawl, 'is_image': oe.is_image_url(url)}
    cands = [
        cand('https://a.example/1', 'similar'),
        cand('https://a.example/2', 'similar'),
        cand('https://a.example/3', 'similar'),
        cand('https://b.example/x', 'exact', ('google_lens', 'tineye'), '2019'),
        cand('https://c.example/img.jpg', 'exact'),
        cand('https://x.com/u/status/1', 'similar'),
    ]
    out = oe.prioritize(cands, limit=10, per_domain=2)
    urls = [c['url'] for c in out]
    assert urls[0] == 'https://b.example/x'            # exact + 2 engines + dated
    assert urls.index('https://x.com/u/status/1') < urls.index('https://a.example/1')
    assert sum(u.startswith('https://a.example') for u in urls) == 2
    assert len(oe.prioritize(cands, limit=3, per_domain=3)) == 3


# ---------------------------------------------------------------- harvest

def test_lens_exact_retries_twice_uncached(monkeypatch):
    """Live finding: SerpAPI returns empty 200s for Lens exact and then
    serves them from cache. Retry twice, bypassing the cache on retries."""
    monkeypatch.setattr(oe, 'LENS_RETRY_DELAY_S', 0)
    calls = []

    def flaky(image_url, lens_type, hl='ar', country='sa', no_cache=False):
        calls.append(no_cache)
        if len(calls) == 1:
            raise RuntimeError('connection reset')
        if len(calls) == 2:
            return []
        return [{'link': 'https://ok.example', 'match_type': 'exact', 'provider': 'google_lens'}]

    monkeypatch.setattr(oe, 'lens_matches', flaky)
    got = oe._lens_exact_with_retry('u', 'en', 'us')    # error, empty, ok
    assert got and calls == [False, True, True]

    calls.clear()
    monkeypatch.setattr(oe, 'lens_matches',
                        lambda *a, **k: calls.append(1) or [])
    assert oe._lens_exact_with_retry('u', 'en', 'us') == []
    assert len(calls) == 3                               # all attempts empty -> []


# ----------------------------------------------------------------- assess

def _item(url, published, conf, verdict, mt='exact'):
    return {'url': url, 'published_at': published, 'confidence': conf,
            'visual': {'verdict': verdict}, 'match_type': mt}


def test_assess_picks_earliest_eligible_only():
    timeline = [
        _item('https://fake.example', '2010-01-01T00:00:00Z', 0.99, 'rejected'),
        _item('https://weak.example', '2011-01-01T00:00:00Z', 0.3, 'confirmed'),
        _item('https://htmldate-only.example', '2011-06-01T00:00:00Z', 0.8, 'confirmed'),
        _item('https://sim.example', '2012-01-01T00:00:00Z', 0.9, 'unverified', 'similar'),
        _item('https://ok.example', '2013-01-01T00:00:00Z', 0.9, 'unverified', 'exact'),
        _item('https://later.example', '2014-01-01T00:00:00Z', 0.95, 'confirmed'),
    ]
    first = oe.assess(timeline)
    assert first['url'] == 'https://ok.example'
    assert oe.assess([]) is None
    # weakly dated / rejected earlier pages are surfaced as hints, not answers
    hints = oe.earlier_hints(timeline, first)
    assert [h['url'] for h in hints] == ['https://weak.example',
                                         'https://htmldate-only.example']
    assert oe.earlier_hints(timeline, None) == []


def test_thumbnail_only_and_image_upload_date_rules(monkeypatch):
    """Live finding: a 2017 article served the photo from a 2025 upload
    path via a 390x220 related-post thumbnail and was named first seen."""
    page = ('<html><head><title>old</title>'
            '<meta property="article:published_time" content="2017-10-09T05:26:40Z">'
            '</head></html>')
    monkeypatch.setattr(oe, 'fetch_page', lambda url, timeout=None: type('P', (), {'text': page, 'headers': {}})())
    monkeypatch.setattr(oe, 'verify_html', lambda html, url, sig, **kw: {
        'verdict': 'confirmed', 'match_kind': 'variant', 'similarity': 0.94,
        'phash_distance': 13, 'checked_images': 2,
        'matched_image_url': 'https://old.example/wp-content/uploads/2025/05/fire.webp?resize=390,220',
        'matched_size': (390, 220), 'matched_from': 'page'})
    monkeypatch.setattr(oe.wayback_provider, 'earliest_capture', lambda u: None)
    cand = {'url': 'https://old.example/story-284665/', 'canonical': 'https://old.example/story-284665',
            'domain': 'old.example', 'match_type': 'exact', 'providers': ['google_lens'],
            'engine_images': [], 'thumbnail': None, 'crawl_date': None, 'is_image': False}
    item = oe.inspect_candidate(cand, {'phash': 'p'}, use_wayback=False)
    assert item['visual']['thumbnail_only'] is True
    assert item['published_at'] == '2025-05-01T00:00:00Z'     # image upload date, not 2017
    assert item['is_lower_bound'] is True and item['confidence'] == 0.5
    sources = {e['source'] for e in item['evidence']}
    assert 'image:upload_path_date' in sources
    assert 'meta:article:published_time?before_image_upload' in sources
    assert not oe._eligible_first(item)                       # thumbnails are never first
    # a lower bound alone (big image, old article) is also never "first"
    item['visual'].pop('thumbnail_only')
    assert not oe._eligible_first(item)

    # JS-only pages (X) verify against the ENGINE's small thumbnail: exempt
    monkeypatch.setattr(oe, 'fetch_page', lambda url, timeout=None: type('P', (), {'text': '<html></html>', 'headers': {}})())
    monkeypatch.setattr(oe, 'verify_html', lambda html, url, sig, **kw: {
        'verdict': 'confirmed', 'match_kind': 'variant', 'similarity': 0.91,
        'phash_distance': 10, 'checked_images': 1,
        'matched_image_url': 'https://encrypted-tbn0.gstatic.com/images?q=x',
        'matched_size': (259, 194), 'matched_from': 'engine'})
    cand = {'url': 'https://x.com/IndiaCoastGuard/status/1814337329387175999',
            'canonical': 'https://x.com/IndiaCoastGuard/status/1814337329387175999',
            'domain': 'x.com', 'match_type': 'exact', 'providers': ['google_lens'],
            'engine_images': ['https://encrypted-tbn0.gstatic.com/images?q=x'],
            'thumbnail': None, 'crawl_date': None, 'is_image': False}
    post = oe.inspect_candidate(cand, {'phash': 'p'}, use_wayback=False)
    assert not post['visual'].get('thumbnail_only')
    assert post['published_at'] == '2024-07-19T16:31:42Z' and oe._eligible_first(post)
    assert oe.to_search_payload({'success': True, 'timeline': [item]})['timeline'][0]['date_found']         == 'ليس قبل 2025-05-01'


def test_assess_same_day_exact_timestamp_beats_day_precision():
    """Live finding (Maersk Frankfurt fire): htmldate gave a news site
    2024-07-19T00:00:00Z while the Coast Guard tweet ID gave 16:31:42Z the
    same day. The tweet (0.99) is the origin, not the midnight guess (0.80)."""
    timeline = [
        _item('https://news.example/story', '2024-07-19T00:00:00Z', 0.80, 'confirmed'),
        _item('https://x.com/IndiaCoastGuard/status/1', '2024-07-19T16:31:42Z', 0.99, 'confirmed'),
        _item('https://later.example', '2024-07-20T01:00:00Z', 0.99, 'confirmed'),
    ]
    assert oe.assess(timeline)['url'] == 'https://x.com/IndiaCoastGuard/status/1'


# ------------------------------------------------------------- full loop

PAGES = {
    'https://news.example/2020/06/01/original': (
        '<html><head><title>Original report</title>'
        '<meta property="article:published_time" content="2020-06-01T08:30:00Z">'
        '<meta property="og:image" content="https://news.example/full.jpg">'
        '</head><body>Photo: Reuters</body></html>'),
    'https://x.com/someone/status/1700000000000000000': (
        '<html><head><title>tweet</title></head><body>repost</body></html>'),
    'https://lookalike.example/other': (
        '<html><head><title>Different photo</title>'
        '<meta property="article:published_time" content="2001-01-01T00:00:00Z">'
        '</head></html>'),
}
VERDICTS = {
    'https://news.example/2020/06/01/original': {
        'verdict': 'confirmed', 'match_kind': 'exact', 'similarity': 0.97,
        'phash_distance': 2, 'matched_image_url': 'https://news.example/full.jpg',
        'matched_size': (1600, 1200), 'checked_images': 1},
    'https://x.com/someone/status/1700000000000000000': {
        'verdict': 'confirmed', 'match_kind': 'variant', 'similarity': 0.92,
        'phash_distance': 12, 'matched_image_url': 'https://pbs.example/1.jpg',
        'matched_size': (800, 600), 'checked_images': 1},
    'https://lookalike.example/other': {
        'verdict': 'rejected', 'match_kind': None, 'similarity': 0.2,
        'phash_distance': 30, 'matched_image_url': None, 'checked_images': 1},
}


class _FakePage:
    def __init__(self, text):
        self.text = text
        self.headers = {}


@pytest.fixture()
def fake_world(monkeypatch):
    calls = {'lens': [], 'wayback': []}

    def lens(image_url, lens_type, hl='ar', country='sa', no_cache=False):
        calls['lens'].append((image_url, lens_type, hl))
        if image_url == 'https://news.example/full.jpg':   # pivot round
            return [{'link': 'https://x.com/someone/status/1700000000000000000',
                     'title': 'tweet', 'match_type': 'exact', 'provider': 'google_lens'}]
        if lens_type == 'exact_matches':
            return [{'link': 'https://news.example/2020/06/01/original',
                     'title': 'Original', 'match_type': 'exact', 'provider': 'google_lens'}]
        return [{'link': 'https://lookalike.example/other', 'title': 'Other',
                 'match_type': 'similar', 'provider': 'google_lens'}]

    def wayback(url):
        calls['wayback'].append(url)
        return '2023-10-01T00:00:00Z' if 'x.com' in url else None

    monkeypatch.setattr(oe, 'lens_matches', lens)
    monkeypatch.setattr(oe.vision_provider, 'configured', lambda: True)
    monkeypatch.setattr(oe, 'vision_web_detection', lambda u: [])
    monkeypatch.setattr(oe.yandex_provider, 'reverse_image',
                        lambda u: (_ for _ in ()).throw(RuntimeError('yandex down')))
    monkeypatch.setattr(oe.tineye_provider, 'configured', lambda: False)
    monkeypatch.setattr(oe.wayback_provider, 'earliest_capture', wayback)
    monkeypatch.setattr(oe, '_download_bytes', lambda u, timeout=None: b'\x89PNGfake')
    monkeypatch.setattr(oe, 'build_query_signature',
                        lambda b: {'phash': 'p', 'dhash': 'd', 'embedding': [0.1]})
    monkeypatch.setenv('SEARCH_COPY', 'none')
    monkeypatch.setattr(oe, 'fetch_page',
                        lambda url, timeout=None: _FakePage(PAGES[url]) if url in PAGES else None)
    monkeypatch.setattr(oe, 'verify_html',
                        lambda html, url, sig, **kw: dict(VERDICTS.get(url, {'verdict': 'no_image'})))
    monkeypatch.setattr(oe.deepseek, 'configured', lambda: False)
    monkeypatch.setenv('SERPAPI_API_KEY', 'test')
    return calls


def test_investigate_origin_finds_first_seen_and_expands(fake_world):
    progress = []
    report = oe.investigate_origin('https://r2.example/query.jpg',
                                   progress=progress.append)
    assert report['success'] is True

    fs = report['first_seen']
    assert fs['url'] == 'https://news.example/2020/06/01/original'
    assert fs['published_at'] == '2020-06-01T08:30:00Z'
    assert fs['is_upper_bound'] is False
    assert fs['visual']['verdict'] == 'confirmed'
    sources = {e['source'] for e in fs['evidence']}
    assert {'meta:article:published_time', 'url:path_date'} <= sources
    assert fs['confidence'] >= 0.95

    links = [i['link'] for i in report['timeline']]
    assert links[0] == fs['url']
    assert 'https://x.com/someone/status/1700000000000000000' in links   # from Lens pivot
    assert 'https://lookalike.example/other' not in links               # visually rejected

    tweet = next(i for i in report['timeline'] if 'x.com' in i['link'])
    assert tweet['published_at'] == '2023-09-08T04:15:59Z'   # snowflake beats wayback bound
    assert tweet['origin_round'] == 1

    assert report['engines']['yandex']['ok'] is False
    assert report['engines']['tineye']['note'] == 'not configured'
    assert report['engines']['lens_pivot']['pivot_image'] == 'https://news.example/full.jpg'
    assert any(call[0] == 'https://news.example/full.jpg' for call in fake_world['lens'])

    assert report['stats']['visually_rejected'] == 1
    assert report['stats']['checked'] == 3
    assert report['rounds'][0]['first_seen'] == '2020-06-01T08:30:00Z'
    assert report['rounds'][1]['improved'] is False   # pivot found later sightings only
    assert len(report['rounds']) == 2                  # loop stopped: nothing earlier
    assert report['narrative'] is None                 # DeepSeek not configured
    assert any('Lens' in m or 'lens' in m for m in progress)


def test_search_copy_url_uses_expiring_imgbb_for_presigned_links(monkeypatch):
    calls = []
    import providers.imgbb as imgbb
    monkeypatch.setattr(imgbb, 'upload_to_imgbb',
                        lambda data, expiration=None: calls.append(expiration) or 'https://i.ibb.co/x/q.jpg')
    monkeypatch.setenv('IMGBB_API_KEY', 'k')
    monkeypatch.setenv('SEARCH_COPY', 'imgbb')
    presigned = 'https://acct.r2.cloudflarestorage.com/b/uploads/a.jpg?X-Amz-Signature=abc'
    assert oe.search_copy_url(b'img', presigned) == 'https://i.ibb.co/x/q.jpg'
    assert calls == [oe.SEARCH_COPY_TTL_S]
    # plain public URLs pass through untouched; opt-out honoured
    assert oe.search_copy_url(b'img', 'https://gcaptain.com/a.jpeg') == 'https://gcaptain.com/a.jpeg'
    monkeypatch.setenv('SEARCH_COPY', 'none')
    assert oe.search_copy_url(b'img', presigned) == presigned
    monkeypatch.setenv('SEARCH_COPY', 'imgbb')
    monkeypatch.delenv('IMGBB_API_KEY')
    assert oe.search_copy_url(b'img', presigned) == presigned
    # public R2 bucket: same object through the public base, no upload
    monkeypatch.setenv('R2_PUBLIC_BASE_URL', 'https://pub-123.r2.dev/')
    assert oe.search_copy_url(b'img', presigned) == 'https://pub-123.r2.dev/uploads/a.jpg'


def test_bing_web_engine_is_off_by_default(monkeypatch):
    monkeypatch.delenv('BING_WEB', raising=False)
    assert oe._browser_engine('bing_web') is None
    tasks, unavailable = oe.engine_table('https://x/q.jpg')
    assert 'bing_web' not in tasks and unavailable['bing'] == 'not configured'


def test_investigate_origin_without_serpapi_key(monkeypatch):
    monkeypatch.delenv('SERPAPI_API_KEY', raising=False)
    report = oe.investigate_origin('https://r2.example/q.jpg')
    assert report['success'] is False and report['timeline'] == []


def test_to_search_payload_keeps_legacy_fields(fake_world):
    report = oe.investigate_origin('https://r2.example/query.jpg')
    payload = oe.to_search_payload(report)
    assert payload['engine'] == 'origin_engine'
    assert payload['total'] == len(payload['timeline'])
    first = payload['timeline'][0]
    for key in ('title', 'link', 'type', 'date_found', 'source', 'timestamp',
                'published_at', 'confidence', 'evidence', 'visual', 'providers'):
        assert key in first
    assert first['date_found'] == '2020-06-01'
    assert first['source'] == 'news.example'
    assert payload['first_seen']['url'] == first['link']


def test_to_search_payload_puts_earlier_hints_last():
    fs = {'url': 'https://x.com/a/status/1', 'domain': 'x.com', 'match_type': 'exact',
          'published_at': '2024-07-19T16:31:42Z', 'confidence': 0.99}
    weak = {'url': 'https://old.example/topic/x', 'domain': 'old.example', 'match_type': 'exact',
            'published_at': '2023-10-25T00:00:00Z', 'confidence': 0.8}
    later = {'url': 'https://news.example/s', 'domain': 'news.example', 'match_type': 'exact',
             'published_at': '2024-07-20T00:00:00Z', 'confidence': 0.95}
    unverified = {'url': 'https://port.example/detail/x', 'domain': 'port.example', 'match_type': 'exact',
                  'published_at': '2023-10-25T00:00:00Z', 'confidence': 0.8, 'visual': {'verdict': 'unverified'}}
    payload = oe.to_search_payload({'success': True, 'first_seen': fs,
                                    'earlier_hints': [weak], 'timeline': [unverified, weak, fs, later]})
    assert [i['link'] for i in payload['timeline']] == [fs['url'], later['url'], unverified['url'], weak['url']]
    assert payload['earlier_hints'] == [weak]


def test_to_search_payload_marks_upper_bounds_and_undated():
    payload = oe.to_search_payload({'success': True, 'timeline': [
        {'url': 'https://a.example', 'domain': 'a.example', 'match_type': 'exact',
         'published_at': '2019-05-05T00:00:00Z', 'is_upper_bound': True},
        {'url': 'https://b.example', 'domain': 'b.example', 'match_type': 'similar'},
    ]})
    assert payload['timeline'][0]['date_found'] == 'على الأقل منذ 2019-05-05'
    assert payload['timeline'][1]['date_found'] == 'بدون تاريخ'
    assert payload['timeline'][1]['title'] == 'b.example'
