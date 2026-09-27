"""Phase 2: hashing, persistence, cache hits, metering, admin spend view."""
import io

import responses

IMGBB_URL = 'https://api.imgbb.com/1/upload'
HOSTED_IMG = 'https://i.ibb.co/test/img.png'


def mock_imgbb(rsps):
    rsps.add(responses.POST, IMGBB_URL,
             json={'success': True, 'data': {'url': HOSTED_IMG}}, status=200)


def mock_image_download(rsps, png):
    rsps.add(responses.GET, HOSTED_IMG, body=png, status=200,
             content_type='image/png')


def _detect(client, png_bytes, force=False):
    data = {'service': 'aiornot', 'image': (io.BytesIO(png_bytes), 'x.png')}
    if force:
        data['force'] = 'true'
    return client.post('/api/ai-detection', data=data,
                       content_type='multipart/form-data')


AIORNOT_JSON = {'id': 'r1', 'report': {'ai_generated': {
    'verdict': 'ai', 'ai': {'confidence': 0.9}, 'human': {'confidence': 0.1},
    'generator': {'flux': 0.7}}}}


@responses.activate
def test_detection_persists_and_caches(client, app, png_bytes):
    responses.add(responses.POST, 'https://api.aiornot.com/v2/image/sync',
                  json=AIORNOT_JSON, status=200)

    # First run: real spend, persisted
    d1 = _detect(client, png_bytes).get_json()
    assert d1['success'] is True
    assert d1.get('analysis_id')
    assert 'cached' not in d1

    from models import db, Analysis
    with app.app_context():
        row = db.session.get(Analysis, d1['analysis_id'])
        assert row is not None
        assert row.analysis_type == 'ai_image'
        assert row.service == 'aiornot'
        assert row.is_ai_generated is True
        assert row.media_hash and len(row.media_hash) == 64
        assert row.media_phash  # PNG -> perceptual hash computed

    # Second run, same bytes: cache hit — no imgbb/aiornot calls needed
    d2 = _detect(client, png_bytes).get_json()
    assert d2['cached'] is True
    assert d2['analysis_id'] == d1['analysis_id']
    assert d2['verdict'] == d1['verdict']

    # force=true bypasses the cache and spends again
    d3 = _detect(client, png_bytes, force=True).get_json()
    assert 'cached' not in d3


@responses.activate
def test_upload_returns_hashes(client, png_bytes):
    mock_imgbb(responses)
    r = client.post('/api/upload', data={
        'file': (io.BytesIO(png_bytes), 'x.png'),
    }, content_type='multipart/form-data')
    d = r.get_json()
    assert len(d['image_hash']) == 64
    assert d['image_phash']


@responses.activate
def test_image_source_search_persists_and_caches(client, app, png_bytes):
    mock_imgbb(responses)
    responses.add(responses.GET, 'https://serpapi.com/search.json',
                  json={'exact_matches': [
                      {'link': 'https://a.example/1', 'title': 'A',
                       'thumbnail': 't1'}]}, status=200)
    responses.add(responses.GET, 'https://serpapi.com/search.json',
                  json={'visual_matches': []}, status=200)

    body = {'file': (io.BytesIO(png_bytes), 'q.png')}
    d1 = client.post('/api/image-source-search', data=body,
                     content_type='multipart/form-data').get_json()
    assert d1['success'] is True and d1.get('search_id')

    from models import db, Search, SearchResult
    with app.app_context():
        search = db.session.get(Search, d1['search_id'])
        assert search.search_type == 'reverse'
        assert search.image_hash and search.image_phash
        assert search.result_count == 1
        urls = [r.url for r in search.results]
        assert urls == ['https://a.example/1']

    # same file again -> cache hit, no new provider calls
    d2 = client.post('/api/image-source-search',
                     data={'file': (io.BytesIO(png_bytes), 'q.png')},
                     content_type='multipart/form-data').get_json()
    assert d2['cached'] is True
    assert d2['search_id'] == d1['search_id']


def _finished_job(client, response):
    assert response.status_code == 202
    body = response.get_json()
    state = client.get(body['status_url']).get_json()
    assert state['status'] == 'finished', state
    return state['result']


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


def test_direct_search_cache_by_hash(client, app, monkeypatch):
    import origin.investigate as inv_mod
    calls = []
    monkeypatch.setattr(inv_mod, 'investigate',
                        lambda url, progress=None, extra_frame_urls=None, **kw: calls.append(url) or _fake_origin_payload())

    fake_hash = 'f' * 64
    r1 = client.post('/api/direct-search', json={
        'image_url': HOSTED_IMG, 'image_hash': fake_hash})
    d1 = _finished_job(client, r1)['payload']
    assert d1['success'] is True and d1.get('search_id') and len(calls) == 1

    # repeat with same hash -> served from DB, no investigation
    d2 = client.post('/api/direct-search', json={
        'image_url': HOSTED_IMG, 'image_hash': fake_hash}).get_json()
    assert d2['cached'] is True and len(calls) == 1
    assert d2['timeline'] == d1['timeline']

    # rerun flag bypasses cache
    r3 = client.post('/api/direct-search', json={
        'image_url': HOSTED_IMG, 'image_hash': fake_hash,
        'rerun': True})
    d3 = _finished_job(client, r3)['payload']
    assert 'cached' not in d3 and len(calls) == 2


@responses.activate
def test_provider_calls_metered(client, app, png_bytes):
    mock_imgbb(responses)
    r = client.post('/api/upload', data={
        'file': (io.BytesIO(png_bytes), 'x.png'),
    }, content_type='multipart/form-data')
    assert r.status_code == 200

    from models import db, ProviderCall
    with app.app_context():
        rows = db.session.query(ProviderCall).filter_by(provider='imgbb').all()
        assert rows, 'imgbb call was not metered'
        assert rows[-1].ok is True
        assert rows[-1].latency_ms is not None


def test_admin_provider_usage_endpoint(client, app):
    # anonymous / non-admin refused
    assert client.get('/api/admin/provider-usage').status_code == 401

    r = client.post('/api/auth/register', json={
        'email': 'spend-admin@example.com', 'password': 'secret123'})
    token = r.get_json()['token']
    assert client.get('/api/admin/provider-usage',
                      headers={'Authorization': f'Bearer {token}'}).status_code == 403

    from models import db, User
    with app.app_context():
        user = db.session.query(User).filter_by(
            email='spend-admin@example.com').one()
        user.is_admin = True
        db.session.commit()

    d = client.get('/api/admin/provider-usage',
                   headers={'Authorization': f'Bearer {token}'}).get_json()
    assert d['success'] is True
    assert isinstance(d['providers'], list)
    assert isinstance(d['daily'], list)
