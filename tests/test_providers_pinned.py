"""Function-level pins for provider parsing.

`impl()` resolves each function from its future home (providers/ or services/)
first and falls back to the app module, so these tests stay green before,
during, and after the monolith split.
"""
import importlib
from unittest.mock import MagicMock, patch

import pytest
import responses


def impl(candidates, attr):
    for mod_name in candidates:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        if hasattr(mod, attr):
            return mod, getattr(mod, attr)
    pytest.fail(f'{attr} not found in any of {candidates}')


# ---------------------------------------------------------------- serpapi lens

@responses.activate
def test_lens_matches_harvests_only_match_sections(app):
    _, lens = impl(['providers.serpapi', 'app'], '_serpapi_lens_matches')
    responses.add(
        responses.GET, 'https://serpapi.com/search.json',
        json={
            'exact_matches': [{'link': 'https://e.example', 'title': 'E',
                               'thumbnail': 'te'}],
            'visual_matches': [{'link': 'https://v.example', 'title': 'V',
                                'thumbnail': 'tv'}],
            'organic_results': [{'link': 'https://noise.example'}],
            'inline_images': [{'link': 'https://noise2.example'}],
            'image_results': [{'link': 'https://noise3.example'}],
        }, status=200)

    out = lens('https://img.example/x.jpg', 'exact_matches')
    assert [(m['link'], m['match_type']) for m in out] == [
        ('https://e.example', 'exact'), ('https://v.example', 'similar')]
    assert all(m['provider'] == 'google_lens' for m in out)


@responses.activate
def test_lens_matches_raises_on_http_error(app):
    _, lens = impl(['providers.serpapi', 'app'], '_serpapi_lens_matches')
    responses.add(responses.GET, 'https://serpapi.com/search.json',
                  body='quota exceeded', status=429)
    import requests as _requests
    with pytest.raises(_requests.RequestException):
        lens('https://img.example/x.jpg', 'visual_matches')


# ---------------------------------------------------------------- vision

def _fake_annotations():
    def img(url):
        m = MagicMock()
        m.url = url
        return m

    ann = MagicMock()
    ann.full_matching_images = [img('https://full.example/a.jpg')]
    ann.partial_matching_images = [img('https://part.example/b.jpg')]
    page = MagicMock()
    page.url = 'https://page.example/post'
    page.page_title = 'Some Page'
    page.full_matching_images = [img('https://full.example/a.jpg')]
    page.partial_matching_images = []
    ann.pages_with_matching_images = [page]
    return ann


def test_vision_web_detection_buckets(app, monkeypatch):
    mod, fn = impl(['providers.vision', 'app'], 'vision_web_detection')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', 'dummy.json')

    fake_client = MagicMock()
    fake_client.web_detection.return_value.web_detection = _fake_annotations()
    with patch.object(mod.vision, 'ImageAnnotatorClient', return_value=fake_client):
        out = fn('https://img.example/x.jpg')

    got = [(m['link'], m['match_type'], m['provider']) for m in out]
    assert got == [
        ('https://full.example/a.jpg', 'exact', 'google_vision'),
        ('https://part.example/b.jpg', 'similar', 'google_vision'),
        ('https://page.example/post', 'page_match', 'google_vision'),
    ]
    # page mention carries a thumbnail from its matching images
    assert out[2]['thumbnail'] == 'https://full.example/a.jpg'
    assert out[2]['title'] == 'Some Page'


def test_vision_web_detection_no_credentials_returns_empty(app, monkeypatch):
    _, fn = impl(['providers.vision', 'app'], 'vision_web_detection')
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
    assert fn('https://img.example/x.jpg') == []


# ---------------------------------------------------------------- imgbb

@responses.activate
def test_imgbb_upload_success(app, png_bytes):
    import base64
    _, upload = impl(['providers.imgbb', 'app'], 'upload_to_imgbb')
    responses.add(responses.POST, 'https://api.imgbb.com/1/upload',
                  json={'success': True,
                        'data': {'url': 'https://i.ibb.co/ok.png'}},
                  status=200)
    b64 = base64.b64encode(png_bytes).decode()
    assert upload(b64) == 'https://i.ibb.co/ok.png'


@responses.activate
def test_imgbb_upload_failure_returns_none(app, png_bytes):
    import base64
    _, upload = impl(['providers.imgbb', 'app'], 'upload_to_imgbb')
    responses.add(responses.POST, 'https://api.imgbb.com/1/upload',
                  json={'success': False,
                        'error': {'message': 'invalid key'}},
                  status=400)
    b64 = base64.b64encode(png_bytes).decode()
    assert upload(b64) is None


# ---------------------------------------------------------------- reverse search merge

@responses.activate
def test_scrape_reverse_search_merges_and_ranks(app):
    mod, fn = impl(['services.search_service', 'app'], 'scrape_reverse_search')
    responses.add(
        responses.GET, 'https://serpapi.com/search.json',
        json={'exact_matches': [
            {'link': 'https://dup.example', 'title': 'E', 'thumbnail': 't'}]},
        status=200)
    responses.add(
        responses.GET, 'https://serpapi.com/search.json',
        json={'visual_matches': [
            {'link': 'https://dup.example', 'title': 'E again', 'thumbnail': 't'},
            {'link': 'https://sim.example', 'title': 'S', 'thumbnail': 't2'}]},
        status=200)

    with patch.object(mod, 'vision_web_detection', return_value=[
            {'title': '', 'link': 'https://pg.example', 'thumbnail': None,
             'match_type': 'page_match', 'provider': 'google_vision'}]):
        out = fn('https://img.example/x.jpg')

    assert out['success'] is True
    # dedup keeps the strongest bucket and orders exact > similar > page_match
    assert [(m['link'], m['match_type']) for m in out['matches']] == [
        ('https://dup.example', 'exact'),
        ('https://sim.example', 'similar'),
        ('https://pg.example', 'page_match')]
    assert out['links'] == ['https://dup.example', 'https://sim.example',
                            'https://pg.example']
    assert set(out['search_urls'].keys()) == {'google', 'bing', 'yandex', 'tineye'}
