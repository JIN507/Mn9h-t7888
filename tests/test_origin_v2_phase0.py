"""Phase 0 of Origin v2: budgets, URL identity, benchmark verdicts, the
ORIGIN_V2 job flag (falls back to v1 while v2 is unbuilt)."""
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
    assert Budget(kind='video').credits == 20 and Budget().credits == 12


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


def test_job_flag_routes_to_v2_and_falls_back_while_unbuilt(monkeypatch):
    from tasks import jobs
    calls = []
    monkeypatch.setenv('ORIGIN_V2', 'true')
    monkeypatch.setenv('ORIGIN_AGENT', 'false')
    import services.origin_engine as oe
    monkeypatch.setattr(oe, 'investigate_origin',
                        lambda url, progress=None, extra_frame_urls=None: calls.append('v1') or
                        {'success': True, 'timeline': [], 'engines': {}, 'first_seen': None})
    out = jobs._run_origin_engine('https://img.example/q.jpg')
    assert calls == ['v1'] and out is not None and out['engine'] == 'origin_engine'
