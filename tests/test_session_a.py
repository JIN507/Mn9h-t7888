"""Session A: direct-search resilience — retry-once + Google Lens fallback."""
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
    """First Zenserp 500 is retried (failures are unbilled); success on #2."""
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
def test_zenserp_down_falls_back_to_lens(client):
    """Both Zenserp attempts fail -> timeline built from the Lens harvest."""
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
    assert d['timeline'][0]['source'] == 'news.example'
    assert d.get('search_id')  # fallback results are persisted + cacheable


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
