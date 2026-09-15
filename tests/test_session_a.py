"""Session A: direct-search resilience — retry-once + Google Lens fallback.

Image mode now runs the Origin Engine first (Lens/Vision/Yandex via
SerpAPI). When every engine fails (SerpAPI unreachable) the job degrades
to the legacy Zenserp -> Lens path these tests originally pinned."""
import responses

HOSTED_IMG = 'https://i.ibb.co/test/img.png'
ZEN = 'https://app.zenserp.com/api/v2/search'
SERP = 'https://serpapi.com/search.json'


def _finished_job(client, response):
    assert response.status_code == 202
    body = response.get_json()
    state = client.get(body['status_url']).get_json()
    assert state['status'] == 'finished', state
    return state['result']


@responses.activate
def test_zenserp_retry_once_then_succeed(client):
    """SerpAPI unreachable -> Origin Engine yields nothing -> legacy path:
    first Zenserp 500 is retried (failures are unbilled); success on #2."""
    responses.add(responses.GET, ZEN, json={'errors': {'unknown_error': 'x'}},
                  status=500)
    responses.add(responses.GET, ZEN, json={'reverse_image_results': {
        'similar_images': [{'title': 'S', 'url': 'https://s.example'}],
        'pages_with_matching_images': [], 'organic': []}}, status=200)

    r = client.post('/api/direct-search', json={'image_url': HOSTED_IMG})
    result = _finished_job(client, r)
    assert result['status'] == 200
    d = result['payload']
    assert d['engine'] == 'zenserp'
    assert [i['link'] for i in d['timeline']] == ['https://s.example']
    zen_calls = [c for c in responses.calls if ZEN in c.request.url]
    assert len(zen_calls) == 2


@responses.activate
def test_image_mode_runs_origin_engine(client):
    """SerpAPI answers -> the Origin Engine owns image mode: Zenserp is
    never called, results carry evidence fields, and the run is persisted
    so the next upload of the same image is a cache hit."""
    responses.add(responses.GET, SERP, json={'exact_matches': [
        {'link': 'https://news.example/2020/06/01/story', 'title': 'الخبر الأصلي',
         'thumbnail': 'https://t/1'}]}, status=200)
    responses.add(responses.GET, SERP, json={'visual_matches': [
        {'link': 'https://blog.example/copy', 'title': 'نسخة',
         'thumbnail': 'https://t/2'}]}, status=200)
    responses.add(responses.GET, 'https://web.archive.org/cdx/search/cdx',
                  json=[], status=200)

    r = client.post('/api/direct-search', json={'image_url': HOSTED_IMG,
                                                'image_hash': 'h-origin-1'})
    result = _finished_job(client, r)
    assert result['status'] == 200
    d = result['payload']
    assert d['engine'] == 'origin_engine'
    assert not any(ZEN in c.request.url for c in responses.calls)
    got = {i['link']: i['type'] for i in d['timeline']}
    assert 'https://news.example/2020/06/01/story' in got
    assert got['https://news.example/2020/06/01/story'] == 'exact'
    story = next(i for i in d['timeline'] if 'news.example' in i['link'])
    assert story['source'] == 'news.example'
    assert story['date_found'] == '2020-06-01'          # url path date
    assert story['visual']['verdict'] in ('unverified', 'error', 'no_image')
    assert story['evidence'][0]['source'] == 'url:path_date'
    assert 'first_seen' in d and 'engines' in d and 'stats' in d
    assert d['engines']['lens_exact_en']['ok'] is True
    assert d.get('search_id')

    # repeat upload -> instant cache hit carrying the full report
    r2 = client.post('/api/direct-search', json={'image_url': HOSTED_IMG,
                                                 'image_hash': 'h-origin-1'})
    assert r2.status_code == 200
    body = r2.get_json()
    assert body['cached'] is True and body['engine'] == 'origin_engine'
    assert 'engines' in body and body['timeline']


@responses.activate
def test_serpapi_down_falls_back_to_legacy_lens_scrape(client):
    """Every Origin-Engine engine fails AND Zenserp fails twice -> the legacy
    Lens scrape path (also SerpAPI) is the last resort; here it works."""
    # Origin Engine: lens exact en/ar (x2 with retry) + lens visual + yandex
    for _ in range(6):
        responses.add(responses.GET, SERP, status=429, body='quota')
    responses.add(responses.GET, ZEN, json={'errors': {'unknown_error': 'x'}},
                  status=500)
    responses.add(responses.GET, ZEN, json={'errors': {'unknown_error': 'x'}},
                  status=500)
    responses.add(responses.GET, SERP, json={'exact_matches': [
        {'link': 'https://news.example/story', 'title': 'الخبر الأصلي',
         'thumbnail': 't1'}]}, status=200)
    responses.add(responses.GET, SERP, json={'visual_matches': [
        {'link': 'https://blog.example/copy', 'title': 'نسخة',
         'thumbnail': 't2'}]}, status=200)

    r = client.post('/api/direct-search', json={'image_url': HOSTED_IMG})
    result = _finished_job(client, r)
    assert result['status'] == 200
    d = result['payload']
    assert d['engine'] == 'google_lens_fallback'
    got = {i['link']: i['type'] for i in d['timeline']}
    assert got == {'https://news.example/story': 'exact',
                   'https://blog.example/copy': 'similar'}
    assert d.get('search_id')


@responses.activate
def test_everything_down_returns_clear_error(client):
    responses.add(responses.GET, ZEN, status=500, json={})
    responses.add(responses.GET, ZEN, status=500, json={})
    responses.add(responses.GET, SERP, status=429, body='quota')
    responses.add(responses.GET, SERP, status=429, body='quota')

    r = client.post('/api/direct-search', json={'image_url': HOSTED_IMG})
    result = _finished_job(client, r)
    assert result['status'] == 502
    assert result['payload']['success'] is False


@responses.activate
def test_text_mode_no_lens_fallback(client):
    """Text search can't fall back to Lens — clean 502 payload instead."""
    responses.add(responses.GET, ZEN, status=500, json={})
    responses.add(responses.GET, ZEN, status=500, json={})

    r = client.post('/api/direct-search', json={'query': 'اختبار'})
    result = _finished_job(client, r)
    assert result['status'] == 502
    assert 'Zenserp' in result['payload']['error']
