"""The operator gate: one account from the environment, a signed cookie,
every /api route closed without it except the gate, health and public media."""
import pytest


@pytest.fixture
def gated(client, monkeypatch):
    monkeypatch.setenv('GATE_ENABLED', 'true')
    monkeypatch.setenv('APP_LOGIN_USER', 'admin')
    monkeypatch.setenv('APP_LOGIN_PASSWORD', 'correct horse battery staple')
    return client


def test_api_is_closed_without_the_cookie(gated):
    assert gated.get('/api/gate/me').status_code == 401
    r = gated.post('/api/direct-search', json={'query': 'x'})
    assert r.status_code == 401 and r.get_json()['gate'] is True
    assert gated.get('/api/gate/login').status_code in (405, 200)            # gate routes themselves are open
    assert gated.get('/reverse-search').status_code == 200                    # the SPA shell still loads


def test_login_sets_cookie_and_opens_the_api(gated):
    bad = gated.post('/api/gate/login', json={'username': 'admin', 'password': 'nope'})
    assert bad.status_code == 401
    ok = gated.post('/api/gate/login', json={'username': 'admin', 'password': 'correct horse battery staple'})
    assert ok.status_code == 200 and 'tq_gate=' in ok.headers.get('Set-Cookie', '') and 'HttpOnly' in ok.headers['Set-Cookie']
    me = gated.get('/api/gate/me')
    assert me.status_code == 200 and me.get_json()['username'] == 'admin'
    assert gated.post('/api/direct-search', json={}).status_code == 400      # past the gate: normal validation
    gated.post('/api/gate/logout')
    assert gated.get('/api/gate/me').status_code == 401


def test_unconfigured_password_is_refused_loudly(gated, monkeypatch):
    monkeypatch.setenv('APP_LOGIN_PASSWORD', '')
    r = gated.post('/api/gate/login', json={'username': 'admin', 'password': 'anything'})
    assert r.status_code == 500 and 'APP_LOGIN_PASSWORD' in r.get_json()['error']


def test_gate_disabled_reports_open(client, monkeypatch):
    monkeypatch.setenv('GATE_ENABLED', 'false')
    r = client.get('/api/gate/me')
    assert r.status_code == 200 and r.get_json()['gate'] is False
