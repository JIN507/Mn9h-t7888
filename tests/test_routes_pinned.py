"""Route-level behavior pins.

These tests exercise the HTTP routes with mocked provider HTTP (responses lib)
and pin the exact response shapes. They must stay green, unchanged, across the
monolith split — routes are the contract.
"""
import base64
import io
import json

import responses

IMGBB_URL = 'https://api.imgbb.com/1/upload'
HOSTED_IMG = 'https://i.ibb.co/test/img.png'


def mock_imgbb(rsps):
    rsps.add(responses.POST, IMGBB_URL,
             json={'success': True, 'data': {'url': HOSTED_IMG}}, status=200)


def mock_image_download(rsps, png):
    rsps.add(responses.GET, HOSTED_IMG, body=png, status=200,
             content_type='image/png')


# ---------------------------------------------------------------- detection

@responses.activate
def test_ai_detection_aiornot(client, png_bytes):
    responses.add(
        responses.POST, 'https://api.aiornot.com/v2/image/sync',
        json={'id': 'r1', 'report': {'ai_generated': {
            'verdict': 'ai',
            'ai': {'confidence': 0.97},
            'human': {'confidence': 0.03},
            'generator': {'midjourney': 0.8, 'dalle': 0.1},
        }}}, status=200)

    r = client.post('/api/ai-detection', data={
        'service': 'aiornot',
        'image': (io.BytesIO(png_bytes), 'x.png'),
    }, content_type='multipart/form-data')
    d = r.get_json()
    assert r.status_code == 200
    assert d['success'] is True
    assert d['is_ai'] is True
    assert d['confidence_ai'] == 0.97
    assert d['confidence_human'] == 0.03
    assert d['generator'] == 'midjourney'
    assert d['generator_confidence'] == 0.8
    assert d['source'] == 'AI-or-Not'
    assert d['imageUrl'] is None  # direct file upload — nothing is hosted
    assert 'الذكاء الاصطناعي' in d['verdict']


@responses.activate
def test_ai_detection_aiornot_human(client, png_bytes):
    responses.add(
        responses.POST, 'https://api.aiornot.com/v2/image/sync',
        json={'id': 'r2', 'report': {'ai_generated': {
            'verdict': 'human',
            'ai': {'confidence': 0.02},
            'human': {'confidence': 0.98},
            'generator': {},
        }}}, status=200)

    r = client.post('/api/ai-detection', data={
        'service': 'aiornot',
        'image': (io.BytesIO(png_bytes), 'x.png'),
    }, content_type='multipart/form-data')
    d = r.get_json()
    assert d['is_ai'] is False
    assert d['generator'] == 'unknown'
    assert 'حقيقية' in d['verdict']


@responses.activate
def test_ai_detection_sightengine(client, png_bytes):
    responses.add(
        responses.POST, 'https://api.sightengine.com/1.0/check.json',
        json={'status': 'success', 'type': {'ai_generated': 0.83}}, status=200)

    r = client.post('/api/ai-detection', data={
        'service': 'thehive',
        'image': (io.BytesIO(png_bytes), 'x.png'),
    }, content_type='multipart/form-data')
    d = r.get_json()
    assert r.status_code == 200
    assert d['is_ai'] is True
    assert d['confidence_ai'] == 0.83
    assert abs(d['confidence_human'] - 0.17) < 1e-9
    assert d['generator'] == 'unknown'
    assert d['source'] == 'Model-1'
    assert d['success'] is True


@responses.activate
def test_ai_detection_sightengine_api_error(client, png_bytes):
    responses.add(
        responses.POST, 'https://api.sightengine.com/1.0/check.json',
        json={'status': 'failure', 'error': {'message': 'bad'}}, status=200)

    r = client.post('/api/ai-detection', data={
        'service': 'thehive',
        'image': (io.BytesIO(png_bytes), 'x.png'),
    }, content_type='multipart/form-data')
    # scrape_thehive returns an error dict -> route maps to 500
    assert r.status_code == 500
    assert r.get_json()['success'] is False


def test_ai_detection_unknown_service(client, png_bytes):
    r = client.post('/api/ai-detection', data={
        'service': 'nope',
        'image': (io.BytesIO(png_bytes), 'x.png'),
    }, content_type='multipart/form-data')
    assert r.status_code == 400


@responses.activate
def test_text_detection(client):
    responses.add(
        responses.POST, 'https://api.aiornot.com/v2/text/sync',
        json={'report': {'ai_text': {
            'confidence': 0.9, 'is_detected': True,
            'annotations': [['first paragraph', 0.2], ['second one', 0.4]],
        }}}, status=200)

    r = client.post('/api/text-detection',
                    json={'text': 'x' * 40})
    d = r.get_json()
    assert r.status_code == 200
    assert d['success'] is True
    assert d['is_ai'] is True
    assert d['confidence_ai'] == 0.9
    assert abs(d['confidence_human'] - 0.1) < 1e-9
    assert len(d['annotations']) == 2
    assert d['annotations'][0] == {
        'text': 'first paragraph', 'is_ai': True, 'confidence': 0.9}


def test_text_detection_too_short(client):
    r = client.post('/api/text-detection', json={'text': 'short'})
    assert r.status_code == 400


@responses.activate
def test_verify_audio(client):
    responses.add(
        responses.POST, 'https://api.aiornot.com/v1/reports/voice',
        json={'id': 'aud1', 'created_at': '2026-01-01T00:00:00',
              'report': {'verdict': 'ai', 'confidence': 0.88,
                         'duration': 12.5, 'md5': 'abc'}},
        status=200)

    r = client.post('/api/verify-audio', data={
        'audio': (io.BytesIO(b'RIFF-fake-audio'), 'clip.mp3'),
    }, content_type='multipart/form-data')
    d = r.get_json()
    assert r.status_code == 200
    assert d['success'] is True
    assert d['is_ai_generated'] is True
    assert d['confidence'] == 0.88
    assert d['duration'] == 12.5
    assert d['md5'] == 'abc'
    assert d['details']['verdict'] == 'ai'
    assert d['details']['format'] == 'MP3'


def _finished_job(client, response):
    """Follow the 202 job contract to the finished result."""
    assert response.status_code == 202
    body = response.get_json()
    assert body['success'] is True and body['job_id']
    state = client.get(body['status_url']).get_json()
    assert state['status'] == 'finished', state
    return state['result']


@responses.activate
def test_analyze_video_job(client):
    payload = {'id': 'v1', 'report': {'ai_video': {'verdict': 'human'}}}
    responses.add(responses.POST, 'https://api.aiornot.com/v2/video/sync',
                  json=payload, status=200)

    r = client.post('/api/analyze-video', data={
        'file': (io.BytesIO(b'fake-video-bytes'), 'clip.mp4'),
    }, content_type='multipart/form-data')
    result = _finished_job(client, r)
    assert result['status'] == 200
    assert result['payload'] == {'success': True, 'data': payload}


@responses.activate
def test_job_sse_stream(client):
    payload = {'id': 'v2', 'report': {'ai_video': {'verdict': 'ai'}}}
    responses.add(responses.POST, 'https://api.aiornot.com/v2/video/sync',
                  json=payload, status=200)
    r = client.post('/api/analyze-video', data={
        'file': (io.BytesIO(b'fake-video-bytes'), 'clip2.mp4'),
    }, content_type='multipart/form-data')
    events_url = r.get_json()['events_url']

    sse = client.get(events_url)
    assert sse.status_code == 200
    assert sse.mimetype == 'text/event-stream'
    text = sse.get_data(as_text=True)
    assert 'event: result' in text
    assert '"success": true' in text

    assert client.get('/api/jobs/nonexistent-id').status_code == 404


# ---------------------------------------------------------------- search

@responses.activate
def test_upload_returns_engine_links(client, png_bytes):
    mock_imgbb(responses)
    r = client.post('/api/upload', data={
        'file': (io.BytesIO(png_bytes), 'x.png'),
    }, content_type='multipart/form-data')
    d = r.get_json()
    assert r.status_code == 200
    assert d['imageUrl'] == HOSTED_IMG
    assert set(d['searchResults'].keys()) == {'google', 'bing', 'yandex', 'tineye'}
    from urllib.parse import quote
    assert quote(HOSTED_IMG, safe='') in d['searchResults']['google']


@responses.activate

def _fake_origin_payload():
    return {'success': True, 'engine': 'origin_engine', 'version': 2,
            'first_seen': {'url': 'https://s.example', 'link': 'https://s.example', 'title': 'S', 'thumbnail': None,
                           'source': 's.example', 'published_at': '2024-01-01T00:00:00Z', 'confidence': 0.9,
                           'image_level': 'page', 'date_level': 'structured', 'visual': {'verdict': 'confirmed'}, 'evidence': []},
            'first_seen_exact': None, 'version_note': None,
            'timeline': [{'link': 'https://s.example', 'title': 'S', 'thumbnail': None, 'source': 's.example',
                          'published_at': '2024-01-01T00:00:00Z', 'confidence': 0.9, 'type': 'similar',
                          'visual': {'verdict': 'confirmed'}, 'evidence': []}],
            'total': 1, 'leads': [], 'copies': [], 'engines': {}, 'budget': {'credits': 4}, 'stats': {'checked': 1},
            'rounds': [], 'note': None, 'identity': None, 'scenes': [], 'screenshot': False}


def test_direct_search_image_mode_runs_origin_v2(client, monkeypatch):
    import origin.investigate as inv_mod
    monkeypatch.setattr(inv_mod, 'investigate',
                        lambda url, progress=None, extra_frame_urls=None, **kw: _fake_origin_payload())
    r = client.post('/api/direct-search', json={'image_url': HOSTED_IMG})
    d = _finished_job(client, r)['payload']
    assert d['success'] is True and d['engine'] == 'origin_engine' and d['version'] == 2
    assert d['first_seen']['link'] == 'https://s.example' and d.get('search_id')


def test_direct_search_image_mode_reports_engine_failure(client, monkeypatch):
    import origin.investigate as inv_mod
    monkeypatch.setattr(inv_mod, 'investigate',
                        lambda url, progress=None, extra_frame_urls=None, **kw: {'success': False, 'note': 'SerpAPI key not configured'})
    r = client.post('/api/direct-search', json={'image_url': HOSTED_IMG})
    res = _finished_job(client, r)
    assert res['status'] == 502 and 'SerpAPI' in res['payload']['error']


@responses.activate
def test_direct_search_text_mode_uses_google_organic(client):
    responses.add(
        responses.GET, 'https://serpapi.com/search.json',
        json={'organic_results': [
            {'title': 'T', 'link': 'https://t.example', 'snippet': 'x', 'date': 'Jan 1, 2024'}]},
        status=200)

    r = client.post('/api/direct-search', json={'query': 'اختبار'})
    d = _finished_job(client, r)['payload']
    assert d['success'] is True and d['engine'] == 'google_text'
    assert d['total'] == 1
    assert d['timeline'][0]['type'] == 'organic'
    assert d['timeline'][0]['link'] == 'https://t.example'
    assert 'engine=google' in responses.calls[0].request.url


@responses.activate
def test_image_source_search_lens_harvest(client, png_bytes):
    mock_imgbb(responses)
    responses.add(
        responses.GET, 'https://serpapi.com/search.json',
        json={'exact_matches': [
            {'link': 'https://a.example/1', 'title': 'A', 'thumbnail': 't1'}],
            'organic_results': [{'link': 'https://noise.example'}]},
        status=200)
    responses.add(
        responses.GET, 'https://serpapi.com/search.json',
        json={'visual_matches': [
            {'link': 'https://b.example/2', 'title': 'B', 'thumbnail': 't2'}],
            'inline_images': [{'link': 'https://noise2.example'}]},
        status=200)

    r = client.post('/api/image-source-search', data={
        'file': (io.BytesIO(png_bytes), 'x.png'),
    }, content_type='multipart/form-data')
    d = r.get_json()
    assert r.status_code == 200
    assert d['success'] is True
    assert d['links'] == ['https://a.example/1', 'https://b.example/2']


@responses.activate
def test_xai_context_job(client):
    responses.add(
        responses.POST, 'https://api.x.ai/v1/responses',
        json={'output': [
            {'role': 'assistant', 'type': 'message', 'content': [
                {'type': 'output_text', 'text': 'خلاصة التحقيق'}]},
        ]}, status=200)

    r = client.post('/api/xai-context', json={'image_url': HOSTED_IMG})
    result = _finished_job(client, r)
    assert result['status'] == 200
    assert result['payload']['success'] is True
    assert result['payload']['summary'] == 'خلاصة التحقيق'


# ---------------------------------------------------------------- provenance

@responses.activate
def test_provenance_tags_timeline(client):
    responses.add(
        responses.GET, 'https://serpapi.com/search.json',
        json={'exact_matches': [
            {'link': 'https://exact.example/p', 'title': 'E', 'thumbnail': 't'}]},
        status=200)
    responses.add(
        responses.GET, 'https://serpapi.com/search.json',
        json={'visual_matches': [
            {'link': 'https://similar.example/p', 'title': 'V', 'thumbnail': 't2'}]},
        status=200)
    # page fetches during provenance processing fail fast under responses,
    # which still yields (undated) timeline entries — good enough to pin tags
    r = client.post('/api/provenance', json={'image_url': HOSTED_IMG})
    result = _finished_job(client, r)
    assert result['status'] == 200
    d = result['payload']
    types = {i['url']: i['match_type'] for i in d['timeline']}
    assert types == {'https://exact.example/p': 'exact',
                     'https://similar.example/p': 'similar'}
    ri = {i['link']: i['match_type'] for i in d['related_images']}
    assert ri == {'https://exact.example/p': 'exact',
                  'https://similar.example/p': 'similar'}


# ---------------------------------------------------------------- auth & data

def test_auth_register_login_me_flow(client):
    email = 'pin-user@example.com'
    r = client.post('/api/auth/register', json={
        'email': email, 'password': 'secret123', 'display_name': 'Pin'})
    assert r.status_code == 201
    token = r.get_json()['token']
    assert r.get_json()['user']['email'] == email

    r = client.post('/api/auth/login', json={
        'email': email, 'password': 'secret123'})
    assert r.status_code == 200
    token = r.get_json()['token']

    r = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert r.get_json()['user']['email'] == email

    # keywords CRUD
    h = {'Authorization': f'Bearer {token}'}
    r = client.post('/api/user/keywords', json={'keyword': 'حرب'}, headers=h)
    assert r.status_code == 201
    kid = r.get_json()['keyword']['id']
    r = client.get('/api/user/keywords', headers=h)
    assert [k['keyword'] for k in r.get_json()['keywords']] == ['حرب']
    r = client.delete(f'/api/user/keywords/{kid}', headers=h)
    assert r.status_code == 200

    # user-scoped lists respond
    assert client.get('/api/user/searches', headers=h).status_code == 200
    assert client.get('/api/user/analyses', headers=h).status_code == 200
    assert client.get('/api/user/files', headers=h).status_code == 200

    # admin endpoints refuse non-admin
    assert client.get('/api/admin/users', headers=h).status_code == 403


def test_auth_login_bad_credentials(client):
    r = client.post('/api/auth/login', json={
        'email': 'nobody@example.com', 'password': 'wrong'})
    assert r.status_code == 401


def test_catalog_public_endpoints(client):
    assert client.get('/api/countries').status_code == 200
    assert client.get('/api/sources').status_code == 200


def test_spa_served(client):
    r = client.get('/')
    assert r.status_code == 200
    assert b'<div id="root">' in r.data


def test_export_roundtrip(client):
    payload = {'a': 1, 'b': ['x']}
    r = client.post('/api/export', json=payload)
    assert r.status_code == 200
    assert r.get_json() == payload
    assert 'attachment' in r.headers['Content-Disposition']


def test_upload_rejects_non_image_bytes(client):
    """A .jpg that is really HTML must not be hosted or searched."""
    import io as _io
    r = client.post('/api/upload', data={'file': (_io.BytesIO(b'<!doctype html><html></html>'), 'fake.jpg')},
                    content_type='multipart/form-data')
    assert r.status_code == 400
    assert r.get_json()['success'] is False


def test_manual_engine_links_are_encoded(monkeypatch):
    """Presigned R2 links carry their own '?' and '&': the manual engine
    links must percent-encode them (and prefer a plain public URL)."""
    from services import search_service
    from providers import storage
    presigned = 'https://acct.r2.cloudflarestorage.com/b/uploads/a.jpg?X-Amz-Signature=abc&X-Amz-Expires=900'
    monkeypatch.setattr(storage, 'public_media_url', lambda key: None)
    monkeypatch.setattr(storage, 'presigned_get_url', lambda key, expires=None: f'https://r2.example/{key}?sig=long&exp={expires}')
    links = search_images = search_service.search_images(presigned)
    for url in links.values():
        assert '&exp=86400' not in url and 'exp%3D86400' in url        # inner params encoded
        assert url.count('?') == 1
    assert links['google'].startswith('https://lens.google.com/uploadbyurl?url=https%3A%2F%2Fr2.example%2Fuploads%2Fa.jpg')
    monkeypatch.setattr(storage, 'public_media_url', lambda key: f'https://tahaqqaq.onrender.com/api/media/t/{key}')
    assert 'tahaqqaq.onrender.com%2Fapi%2Fmedia' in search_service.search_images(presigned)['yandex']
