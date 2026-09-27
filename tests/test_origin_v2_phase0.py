"""Phase 0 of Origin v2: budgets, URL identity, benchmark verdicts, and the
direct-search route running the v2 job."""
import pytest

from origin import urls
from origin.budget import Budget, BudgetExceeded
from benchmark import runner


def test_budget_counts_and_refuses_over_cap():
    b = Budget(seconds=10, credits=3, pages=5)
    assert b.can_spend(3) and not b.can_spend(4)
    b.charge(2, 'lens')
    with pytest.raises(BudgetExceeded):
        b.charge(2, 'yandex')
    b.charge(1)
    assert b.spent_credits == 3 and not b.can_spend(1)
    b.refund(1)
    assert b.spent_credits == 2
    assert b.take_pages(3) == 3 and b.take_pages(9) == 2 and b.take_pages(1) == 0
    b.skip('round 3', 'no credits')
    snap = b.snapshot()
    assert snap['credits'] == 2 and snap['pages'] == 5 and snap['skipped'] == [{'step': 'round 3', 'reason': 'no credits'}]
    assert Budget(kind='video').credits == 22 and Budget().credits == 15


def test_canonical_urls_fold_platform_variants():
    a = 'https://twitter.com/svs9111/status/570514380095299584?lang=cs&s=20'
    b = 'https://x.com/svs9111/status/570514380095299584/'
    assert urls.canonical(a) == 'https://x.com/svs9111/status/570514380095299584' == urls.canonical(b)
    assert urls.same('https://www.pinterest.com/pin/1/?utm_medium=organic&utm_source=yandexsmartcamera',
                     'https://www.pinterest.com/pin/1/')
    assert urls.canonical('https://youtu.be/EA6bWERKe3w') == 'https://www.youtube.com/watch?v=EA6bWERKe3w'
    assert urls.canonical('https://m.youtube.com/watch?v=EA6bWERKe3w&feature=share&t=10') == 'https://www.youtube.com/watch?v=EA6bWERKe3w'
    assert urls.canonical('not a url') is None and urls.canonical('') is None
    assert not urls.same('https://x.com/a/status/1', 'https://x.com/a/status/2')


def test_benchmark_verdicts_and_regression_detection():
    case = {'id': 'c', 'expected': 'https://x.com/svs9111/status/570514380095299584',
            'acceptable': ['https://x.com/0fj/status/1234717126671425537']}
    assert runner.verdict_for(case, 'https://twitter.com/svs9111/status/570514380095299584?lang=cs') == 'pass'
    assert runner.verdict_for(case, 'https://x.com/0fj/status/1234717126671425537') == 'acceptable'
    assert runner.verdict_for(case, 'https://www.pinterest.com/pin/1/') == 'fail'
    assert runner.verdict_for(case, None) == 'fail'
    baseline = {'a': {'verdict': 'pass'}, 'b': {'verdict': 'acceptable'}, 'c': {'verdict': 'fail'}}
    results = {'a': {'verdict': 'acceptable', 'seconds': 1, 'credits': 1, 'origin': 'x'},
               'b': {'verdict': 'pass', 'seconds': 1, 'credits': 1, 'origin': 'y'},
               'c': {'verdict': 'fail', 'seconds': 1, 'credits': 1, 'origin': None}}
    assert runner.compare(results, baseline) == ['a']
    assert 'case' in runner.format_table(results, baseline)
    cases = runner.load_cases()
    assert {c['id'] for c in cases} >= {'maersk_frankfurt', 'singers_restored'}
    assert runner.load_baseline()['maersk_frankfurt']['verdict'] == 'pass'


def test_run_case_uses_investigate_and_never_raises(monkeypatch):
    monkeypatch.setattr(runner, 'public_url_for', lambda key: 'https://pub.example/' + key)
    case = {'id': 'c', 'key': 'uploads/a.jpg', 'expected': 'https://x.com/a/status/1'}
    r = runner.run_case(case, lambda url: {'first_seen': {'url': 'https://x.com/a/status/1', 'published_at': '2024'},
                                           'budget': {'credits': 7}})
    assert r['verdict'] == 'pass' and r['credits'] == 7
    r = runner.run_case(case, lambda url: (_ for _ in ()).throw(RuntimeError('boom')))
    assert r['verdict'] == 'error' and 'boom' in r['error']


def test_direct_search_route_runs_origin_v2_and_persists(client, monkeypatch):
    """/api/direct-search image mode -> job -> Origin v2 payload, persisted with its v2 fields."""
    import origin.investigate as inv_mod
    fake = {'success': True, 'engine': 'origin_engine', 'version': 2,
            'first_seen': {'url': 'https://x.com/a/status/1', 'link': 'https://x.com/a/status/1', 'title': 't',
                           'published_at': '2024-07-19T16:31:42Z', 'confidence': 0.98, 'thumbnail': None,
                           'source': 'x.com', 'image_level': 'platform', 'date_level': 'platform_id',
                           'visual': {'verdict': 'confirmed'}, 'evidence': []},
            'first_seen_exact': None, 'version_note': None,
            'timeline': [{'link': 'https://x.com/a/status/1', 'title': 't', 'thumbnail': None, 'source': 'x.com',
                          'published_at': '2024-07-19T16:31:42Z', 'confidence': 0.98, 'visual': {'verdict': 'confirmed'},
                          'type': 'exact', 'evidence': []}],
            'total': 1, 'leads': [], 'copies': [], 'engines': {'lens_exact_en': {'status': 'results', 'count': 3, 'credits': 1}},
            'budget': {'credits': 5}, 'stats': {'checked': 1, 'visually_confirmed': 1}, 'rounds': [], 'note': None,
            'identity': {'event_ar': 'حدث', 'label': 'استنتاج'}, 'scenes': [], 'screenshot': False}
    monkeypatch.setattr(inv_mod, 'investigate', lambda url, progress=None, extra_frame_urls=None: dict(fake))
    r = client.post('/api/direct-search', json={'image_url': 'https://img.example/q.jpg', 'image_hash': 'h' * 64})
    assert r.status_code == 202
    job_id = r.get_json()['job_id']
    st = client.get(f'/api/jobs/{job_id}').get_json()
    assert st['status'] == 'finished'
    payload = st['result']['payload']
    assert payload['engine'] == 'origin_engine' and payload['version'] == 2
    assert payload['first_seen']['link'] == 'https://x.com/a/status/1' and payload['search_id']
    assert payload['identity']['label'] == 'استنتاج' and payload['budget']['credits'] == 5
    # a second search of the same hash is served from the stored report with the v2 fields intact
    r2 = client.post('/api/direct-search', json={'image_url': 'https://img.example/q.jpg', 'image_hash': 'h' * 64})
    body = r2.get_json()
    assert body.get('cached') is True and body['version'] == 2 and body['identity']['label'] == 'استنتاج'
