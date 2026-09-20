"""Origin-engine providers: TinEye, Yandex (SerpAPI), Wayback CDX, DeepSeek.
All HTTP is mocked with `responses`; parsing is pinned to fixture shapes."""
import os

import pytest
import responses

from providers import deepseek, tineye, wayback, yandex

SERP = 'https://serpapi.com/search.json'


# ---------------------------------------------------------------- TinEye

def test_tineye_not_configured_returns_empty(monkeypatch):
    monkeypatch.delenv('TINEYE_API_KEY', raising=False)
    assert tineye.configured() is False
    assert tineye.search_by_url('https://img.example/a.jpg') == []


@responses.activate
def test_tineye_parses_backlinks_with_crawl_dates(monkeypatch):
    monkeypatch.setenv('TINEYE_API_KEY', 'k')
    responses.add(responses.GET, tineye.SEARCH_URL, json={'results': {'matches': [
        {'image_url': 'https://cdn.example/full.jpg', 'score': 91.2,
         'backlinks': [
             {'backlink': 'https://news.example/2019/01/02/story',
              'url': 'https://news.example/img/full.jpg',
              'crawl_date': '2019-01-03T00:00:00'},
             {'backlink': 'ftp://ignored', 'url': 'x', 'crawl_date': '2019'},
         ]}]}}, status=200)
    got = tineye.search_by_url('https://img.example/a.jpg')
    assert len(got) == 1
    item = got[0]
    assert item['link'] == 'https://news.example/2019/01/02/story'
    assert item['match_type'] == 'exact' and item['provider'] == 'tineye'
    assert item['crawl_date'] == '2019-01-03T00:00:00'
    assert item['image_url'] == 'https://news.example/img/full.jpg'
    sent = responses.calls[0].request
    assert sent.headers['x-api-key'] == 'k'
    assert 'sort=crawl_date' in sent.url and 'order=asc' in sent.url


@responses.activate
def test_tineye_http_error_raises(monkeypatch):
    monkeypatch.setenv('TINEYE_API_KEY', 'k')
    responses.add(responses.GET, tineye.SEARCH_URL, status=403, body='nope')
    import requests
    with pytest.raises(requests.RequestException):
        tineye.search_by_url('https://img.example/a.jpg')


# ---------------------------------------------------------------- Yandex

@responses.activate
def test_yandex_harvests_visual_sections_only():
    responses.add(responses.GET, SERP, json={
        'image_results': [
            {'title': 'صورة', 'link': 'https://site.example/p1',
             'thumbnail': 'https://t/1.jpg', 'original_image': 'https://o/1.jpg'},
            {'title': 'no link', 'thumbnail': 'https://t/2.jpg'},
        ],
        'sites': [{'title': 'Site', 'link': 'https://other.example/page'}],
        'organic_results': [{'link': 'https://never.example'}],
    }, status=200)
    got = yandex.reverse_image('https://img.example/a.jpg')
    links = {g['link']: g['match_type'] for g in got}
    assert links == {'https://site.example/p1': 'similar',
                     'https://other.example/page': 'page_match'}
    assert all(g['provider'] == 'yandex' for g in got)
    assert 'engine=yandex_images' in responses.calls[0].request.url


@responses.activate
def test_yandex_similar_images_section():
    responses.add(responses.GET, SERP, json={
        'image_results': [],
        'similar_images': [{'link': 'https://blog.example/p', 'image': 'https://i/1.jpg'},
                           {'link': 'https://yandex.ru/images/x', 'image': 'https://i/2.jpg'}],
    }, status=200)
    got = yandex.reverse_image('https://img.example/a.jpg')
    assert [(g['link'], g['match_type']) for g in got] == [('https://blog.example/p', 'similar')]


# ------------------------------------------------------------------ Grok

def test_xai_parse_search_output_collects_text_and_urls():
    from providers import xai
    body = {'output': [
        {'type': 'x_search_call', 'status': 'completed', 'results': [{'url': 'https://x.com/a/status/1'}]},
        {'type': 'message', 'content': [{'type': 'output_text',
            'text': 'Earliest: https://x.com/IndiaCoastGuard/status/1814337329387175999 (19 Jul 2024).',
            'annotations': [{'type': 'url_citation', 'url': 'https://gcaptain.com/major-fire/'}]}]},
    ]}
    out = xai.parse_search_output(body)
    assert 'Earliest' in out['text']
    assert out['urls'][:3] == ['https://x.com/a/status/1', 'https://gcaptain.com/major-fire/',
                               'https://x.com/IndiaCoastGuard/status/1814337329387175999']


@responses.activate
def test_xai_search_origin_reports_missing_credits(monkeypatch):
    from providers import xai
    monkeypatch.setenv('XAI_API_KEY', 'k')
    responses.add(responses.POST, xai.RESPONSES_URL, status=403,
                  json={'code': 'permission-denied', 'error': 'team does not have any credits'})
    res = xai.search_origin('https://img/q.jpg', 'find it')
    assert res['urls'] == [] and 'no credits' in res['error']


# --------------------------------------------------------------- Wayback

@responses.activate
def test_wayback_earliest_capture_parses_and_caches():
    wayback._cache.clear()
    responses.add(responses.GET, wayback.CDX_URL, json=[
        ['timestamp', 'statuscode'], ['20150321104455', '200']], status=200)
    url = 'https://news.example/story'
    assert wayback.earliest_capture(url) == '2015-03-21T10:44:55Z'
    assert wayback.earliest_capture(url) == '2015-03-21T10:44:55Z'
    assert len(responses.calls) == 1  # second call served from cache


@responses.activate
def test_wayback_no_capture_or_error_is_none():
    wayback._cache.clear()
    responses.add(responses.GET, wayback.CDX_URL, json=[], status=200)
    assert wayback.earliest_capture('https://new.example/x') is None
    responses.add(responses.GET, wayback.CDX_URL, status=503, body='')
    assert wayback.earliest_capture('https://new.example/y') is None
    assert wayback.earliest_capture('') is None


# -------------------------------------------------------------- DeepSeek

def test_deepseek_reads_misspelled_env_alias(monkeypatch):
    for name in deepseek._KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    assert deepseek.configured() is False
    monkeypatch.setenv('Deapseak_key', 'sk-x')   # the name Faisal used in .env
    assert deepseek.api_key() == 'sk-x'
    assert deepseek.configured() is True


def test_deepseek_chat_without_key_is_none(monkeypatch):
    for name in deepseek._KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    assert deepseek.chat('s', 'u') is None
    assert deepseek.chat_json('s', 'u') is None


@responses.activate
def test_deepseek_chat_json_tolerates_prose_around_json(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-x')
    responses.add(responses.POST, deepseek.CHAT_URL, json={'choices': [
        {'message': {'content': 'Sure:\n{"queries": ["a", "b"]}\nDone.'}}]},
        status=200)
    assert deepseek.chat_json('s', 'u') == {'queries': ['a', 'b']}
    body = responses.calls[0].request.body
    assert b'"response_format"' in body and b'json_object' in body
    assert responses.calls[0].request.headers['Authorization'] == 'Bearer sk-x'


@responses.activate
def test_deepseek_describe_frames_sends_several_images(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-x')
    responses.add(responses.POST, deepseek.CHAT_URL, json={'choices': [
        {'message': {'content': '{"summary_ar": "فيديو", "scenes": [{"frames": [1, 2], "description": "a"}]}'}}]},
        status=200)
    out = deepseek.describe_frames([b'f1', b'f2', b'f3', b'f4', b'f5'], 'describe', max_frames=4)
    assert out['summary_ar'] == 'فيديو'
    import json as _json
    body = _json.loads(responses.calls[0].request.body)
    parts = body['messages'][0]['content']
    assert parts[0]['type'] == 'text'
    assert sum(1 for p in parts if p['type'] == 'image_url') == 4      # capped
    assert deepseek.describe_frames([], 'x') is None


@responses.activate
def test_deepseek_http_error_is_none(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-x')
    responses.add(responses.POST, deepseek.CHAT_URL, status=429, body='slow')
    assert deepseek.chat('s', 'u') is None
