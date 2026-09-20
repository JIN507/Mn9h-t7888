"""Origin Agent: the DeepSeek-driven tool loop, with a scripted fake model.

The fake model returns a fixed sequence of tool calls; every tool is backed
by monkeypatched engines/pages so the loop's mechanics are exercised
deterministically: round-0 harvest, per-engine reverse search with pivot,
text leads that only enter the timeline once inspected and confirmed,
read_page credit mining, finish validation against the evidence bar,
budget enforcement, and the report shape."""
import json

import pytest

from services import origin_agent as oa
from services import origin_engine as oe

PAGES = {
    'https://agency.example/2021/03/04/report': (
        '<html><head><title>Agency report</title>'
        '<meta property="article:published_time" content="2021-03-04T09:00:00Z">'
        '<meta property="og:image" content="https://agency.example/full.jpg">'
        '</head><body>Photo: Agency/Handout via @AgencyPix</body></html>'),
    'https://x.com/AgencyPix/status/1367000000000000000': (
        '<html><head><title>AgencyPix on X</title></head><body>original</body></html>'),
    'https://blog.example/repost': (
        '<html><head><title>Repost</title>'
        '<meta property="article:published_time" content="2022-01-01T00:00:00Z">'
        '</head></html>'),
    'https://lookalike.example/other': (
        '<html><head><title>Other</title>'
        '<meta property="article:published_time" content="2000-01-01T00:00:00Z">'
        '</head></html>'),
}
VERDICTS = {
    'https://agency.example/2021/03/04/report': {
        'verdict': 'confirmed', 'match_kind': 'exact', 'similarity': 0.98,
        'phash_distance': 1, 'matched_image_url': 'https://agency.example/full.jpg',
        'matched_size': (2000, 1300), 'checked_images': 1},
    'https://x.com/AgencyPix/status/1367000000000000000': {
        'verdict': 'confirmed', 'match_kind': 'variant', 'similarity': 0.93,
        'phash_distance': 9, 'matched_image_url': 'https://pbs.example/a.jpg',
        'matched_size': (1200, 800), 'checked_images': 1},
    'https://blog.example/repost': {
        'verdict': 'confirmed', 'match_kind': 'variant', 'similarity': 0.91,
        'phash_distance': 11, 'matched_image_url': 'https://blog.example/i.jpg',
        'matched_size': (600, 400), 'checked_images': 1},
    'https://lookalike.example/other': {
        'verdict': 'rejected', 'match_kind': None, 'similarity': 0.3,
        'phash_distance': 28, 'matched_image_url': None, 'checked_images': 1},
}


class _FakePage:
    def __init__(self, text):
        self.text = text
        self.headers = {}


def _tc(name, args, i):
    return {'id': f'call_{i}', 'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(args)}}


@pytest.fixture()
def world(monkeypatch):
    log = {'lens': [], 'llm_messages': []}

    def lens(image_url, lens_type, hl='ar', country='sa', no_cache=False):
        log['lens'].append((image_url, lens_type, hl))
        if image_url == 'https://agency.example/full.jpg':   # pivot on original
            return [{'link': 'https://x.com/AgencyPix/status/1367000000000000000',
                     'title': 'AgencyPix', 'match_type': 'exact', 'provider': 'google_lens'}]
        if lens_type == 'exact_matches':
            return [{'link': 'https://blog.example/repost', 'title': 'Repost',
                     'match_type': 'exact', 'provider': 'google_lens'}]
        return [{'link': 'https://lookalike.example/other', 'title': 'Other',
                 'match_type': 'similar', 'provider': 'google_lens'}]

    monkeypatch.setattr(oe, 'lens_matches', lens)
    monkeypatch.setattr(oe, 'LENS_RETRY_DELAY_S', 0)
    monkeypatch.setattr(oe.vision_provider, 'configured', lambda: False)
    monkeypatch.setattr(oe.tineye_provider, 'configured', lambda: False)
    monkeypatch.setattr(oe, '_browser_engine', lambda name: None)
    monkeypatch.setattr(oe.yandex_provider, 'reverse_image', lambda u: [])
    monkeypatch.setattr(oe.wayback_provider, 'earliest_capture', lambda u: None)
    monkeypatch.setattr(oe, 'fetch_page',
                        lambda url, timeout=None: _FakePage(PAGES[url]) if url in PAGES else None)
    monkeypatch.setattr(oe, 'verify_html',
                        lambda html, url, sig, **kw: dict(VERDICTS.get(url, {'verdict': 'no_image'})))
    monkeypatch.setattr(oa, '_download', lambda u: (b'\x89PNGfake', 'image/png'))
    monkeypatch.setattr(oa, 'build_query_signature',
                        lambda b: {'phash': 'p', 'dhash': 'd', 'embedding': [0.1]})
    monkeypatch.setenv('SERPAPI_API_KEY', 'test')
    monkeypatch.setenv('ZENSERP_API_KEY', 'test')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test')
    monkeypatch.setenv('SEARCH_COPY', 'none')

    # text search: Zenserp organic leads
    class _Resp:
        status_code = 200

        def json(self):
            return {'organic': [
                {'url': 'https://www.google.com/goto?url=https://agency.example/2021/03/04/report',
                 'title': 'Agency report', 'description': 'Photo: Agency'},
                {'url': 'https://google.com/search?q=x', 'title': 'junk'},
            ]}
    import providers.zenserp as zen
    monkeypatch.setattr(zen, 'text_search', lambda q, **kw: _Resp())
    # Zenserp hands back google.com/goto click-redirects; resolved via Location
    monkeypatch.setattr(oa, '_resolve_redirect',
                        lambda u, timeout=None: u.replace('https://www.google.com/goto?url=', ''))
    return log


def _script_model(monkeypatch, log, script, narrative='ملخص'):
    """Fake DeepSeek: vision returns a context; chat_tools plays `script`."""
    turns = iter(script)

    def chat_tools(messages, tools, **kw):
        log['llm_messages'].append(messages[-1])
        try:
            calls = next(turns)
        except StopIteration:
            return None
        if calls is None:
            return {'role': 'assistant', 'content': 'thinking out loud', '_usage': {'total_tokens': 5}}
        return {'role': 'assistant', 'content': '',
                'tool_calls': [_tc(n, a, i) for i, (n, a) in enumerate(calls)],
                '_usage': {'total_tokens': 100}}

    monkeypatch.setattr(oa.deepseek, 'configured', lambda: True)
    monkeypatch.setattr(oa.deepseek, 'describe_image',
                        lambda b, p, **kw: {'description': 'a handout photo',
                                            'suggested_queries': ['agency handout photo 2021']})
    monkeypatch.setattr(oa.deepseek, 'chat_tools', chat_tools)
    monkeypatch.setattr(oa.deepseek, 'chat', lambda s, u, **kw: narrative)


def test_agent_finds_origin_via_text_search_and_pivot(world, monkeypatch):
    _script_model(monkeypatch, world, [
        [('web_search', {'query': 'agency handout photo 2021'})],
        [('inspect_pages', {'urls': ['https://agency.example/2021/03/04/report']})],
        [('read_page', {'url': 'https://agency.example/2021/03/04/report'})],
        [('reverse_search', {'engine': 'lens_exact',
                             'image_url': 'https://agency.example/full.jpg'})],
        [('finish', {'first_seen_url': 'https://x.com/AgencyPix/status/1367000000000000000',
                     'reasoning': 'Agency credit -> AgencyPix tweet, exact ID timestamp.',
                     'confidence': 'high'})],
    ])
    progress = []
    report = oa.investigate('https://r2.example/q.jpg', progress=progress.append)
    assert report['success'] is True

    # round 0 found only the repost (2022) and rejected the look-alike
    assert report['rounds'][0]['first_seen'] == '2022-01-01T00:00:00Z'

    # text lead entered the timeline only after inspection + confirmation
    fs = report['first_seen']
    assert fs['url'] == 'https://x.com/AgencyPix/status/1367000000000000000'
    assert fs['published_at'] == '2021-03-03T06:32:52Z'   # snowflake of the tweet id
    assert fs['confidence'] >= 0.9

    links = [i['link'] for i in report['timeline']]
    assert links[:2] == ['https://x.com/AgencyPix/status/1367000000000000000',
                         'https://agency.example/2021/03/04/report']
    assert 'https://lookalike.example/other' not in links

    agent = report['agent']
    assert [s['tool'] for s in agent['steps']] == \
        ['web_search', 'inspect_pages', 'read_page', 'reverse_search', 'finish']
    assert agent['pick']['url'] == fs['url'] and agent['pick_matches_first_seen'] is True
    assert agent['finish']['confidence'] == 'high'
    assert agent['image_context']['description'] == 'a handout photo'
    assert any(call[0] == 'https://agency.example/full.jpg' for call in world['lens'])
    assert report['engines']['lens_exact_en@pivot']['pivot_image'] == 'https://agency.example/full.jpg'
    assert report['narrative'] == 'ملخص'
    assert any('DeepSeek' in m for m in progress)

    # the model always sees current findings inside tool results
    last_tool_msg = [m for m in world['llm_messages'] if m.get('role') == 'tool'][-1]
    assert 'current_findings' in last_tool_msg['content']


def test_agent_pick_must_pass_evidence_bar(world, monkeypatch):
    """The model claims a page that was never verified -> pick rejected,
    first_seen stays the evidence-based answer."""
    _script_model(monkeypatch, world, [
        [('finish', {'first_seen_url': 'https://never-inspected.example/x',
                     'reasoning': 'I remember this photo.', 'confidence': 'high'})],
    ])
    report = oa.investigate('https://r2.example/q.jpg')
    assert report['agent']['pick'] is None
    assert report['agent']['pick_matches_first_seen'] is False
    assert report['first_seen']['url'] == 'https://blog.example/repost'


def test_agent_budget_and_text_only_turns(world, monkeypatch):
    """Two consecutive text-only replies end the loop; step cap holds."""
    _script_model(monkeypatch, world, [None, None,
                                       [('web_search', {'query': 'never reached'})]])
    report = oa.investigate('https://r2.example/q.jpg', budget={'max_steps': 5})
    assert report['agent']['steps'] == []
    assert report['agent']['finish'] is None
    assert report['first_seen']['url'] == 'https://blog.example/repost'

    _script_model(monkeypatch, world, [[('web_search', {'query': f'q{i}'})] for i in range(10)])
    report = oa.investigate('https://r2.example/q.jpg', budget={'max_steps': 3})
    assert len(report['agent']['steps']) == 3


def test_agent_read_page_mines_credits_and_handles(world, monkeypatch):
    _script_model(monkeypatch, world, [
        [('read_page', {'url': 'https://agency.example/2021/03/04/report'})],
        [('finish', {'first_seen_url': None, 'reasoning': 'x', 'confidence': 'low'})],
    ])
    report = oa.investigate('https://r2.example/q.jpg')
    step = report['agent']['steps'][0]
    assert step['tool'] == 'read_page'
    tool_msgs = [m for m in world['llm_messages'] if m.get('role') == 'tool']
    body = json.loads(tool_msgs[0]['content'])
    assert '@AgencyPix' in body['handles_mentioned']
    assert any('Agency' in c for c in body['credits_mentioned'])
    assert body['matched_image_url'] == 'https://agency.example/full.jpg'


def test_agent_grok_tool_returns_leads_or_error(world, monkeypatch):
    from providers import xai
    monkeypatch.setattr(xai, 'configured', lambda: True)
    monkeypatch.setattr(xai, 'search_origin', lambda u, q, **kw: {
        'text': 'Found it', 'urls': ['https://x.com/AgencyPix/status/1367000000000000000',
                                    'https://google.com/search?q=x'], 'error': None})
    _script_model(monkeypatch, world, [
        [('grok_search', {'question': 'earliest X post of this photo'})],
        [('finish', {'first_seen_url': None, 'reasoning': 'x', 'confidence': 'low'})],
    ])
    report = oa.investigate('https://r2.example/q.jpg')
    tool_msgs = [m for m in world['llm_messages'] if m.get('role') == 'tool']
    body = json.loads(tool_msgs[0]['content'])
    assert body['answer'] == 'Found it'
    assert [l['url'] for l in body['leads']] == ['https://x.com/AgencyPix/status/1367000000000000000']
    assert body['leads'][0]['social_post'] is True
    assert report['engines']['grok'] == {'ok': True, 'count': 1}

    monkeypatch.setattr(xai, 'search_origin', lambda u, q, **kw: {'text': '', 'urls': [], 'error': 'HTTP 403: xAI account has no credits'})
    _script_model(monkeypatch, world, [[('grok_search', {'question': 'q'})]])
    report = oa.investigate('https://r2.example/q.jpg')
    assert report['engines']['grok']['ok'] is False
    assert 'Grok' in report['agent']['steps'][0]['summary']


def test_agent_falls_back_to_deterministic_engine_without_key(world, monkeypatch):
    monkeypatch.setattr(oa.deepseek, 'configured', lambda: False)
    called = {}
    def fake(u, progress=None, budget=None):
        called['u'] = u
        return {'success': True}
    monkeypatch.setattr(oe, 'investigate_origin', fake)
    assert oa.investigate('https://r2.example/q.jpg')['success'] is True
    assert called['u'] == 'https://r2.example/q.jpg'
