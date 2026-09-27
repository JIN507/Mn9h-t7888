"""Benchmark runner for the origin feature (v1 or v2).

    python scripts/bench_origin.py --engine v2            # run all cases
    python scripts/bench_origin.py --engine v2 --case maersk_frankfurt
    python scripts/bench_origin.py --engine v2 --check    # exit 1 on regression vs baseline

A case passes when the returned origin is the expected URL, is *acceptable*
when it is one of the listed acceptable URLs, otherwise fails. A regression
is any case whose verdict is worse than the baseline's (pass > acceptable >
fail). Each case is run once; results are written to benchmark/results/.
"""
import json
import os
import time
from datetime import datetime, timezone

import yaml

from origin.urls import same

RANK = {'pass': 2, 'acceptable': 1, 'fail': 0, 'error': 0}
HERE = os.path.dirname(os.path.abspath(__file__))


def load_cases(path=None):
    with open(path or os.path.join(HERE, 'benchmark.yaml'), encoding='utf-8') as f:
        return yaml.safe_load(f)['cases']


def load_baseline(path=None):
    p = path or os.path.join(HERE, 'baseline_v1.json')
    if not os.path.exists(p):
        return {}
    with open(p, encoding='utf-8') as f:
        return json.load(f).get('results', {})


def verdict_for(case, origin_url):
    """pass | acceptable | fail for one case given the origin URL found."""
    if not origin_url:
        return 'fail'
    if same(origin_url, case['expected']):
        return 'pass'
    if any(same(origin_url, u) for u in case.get('acceptable') or []):
        return 'acceptable'
    return 'fail'


def public_url_for(key):
    """Public URL of a benchmark image stored in R2 (public base preferred)."""
    from providers import storage
    return storage.public_media_url(key) or storage.presigned_get_url(key, expires=3600) or None


def run_case(case, investigate):
    """investigate(image_url) -> report dict with first_seen{url}, budget{credits}."""
    t0 = time.time()
    try:
        url = public_url_for(case['key'])
        if not url:
            return {'verdict': 'error', 'origin': None, 'seconds': 0, 'credits': 0, 'error': 'no public url'}
        report = investigate(url)
        origin = (report.get('first_seen') or {}).get('url')
        credits = (report.get('budget') or {}).get('credits')
        if credits is None:
            credits = sum(1 for n, st in (report.get('engines') or {}).items()
                          if any(n.startswith(p) for p in ('lens', 'yandex', 'google_reverse', 'text')))
        return {'verdict': verdict_for(case, origin), 'origin': origin,
                'seconds': round(time.time() - t0, 1), 'credits': credits,
                'date': (report.get('first_seen') or {}).get('published_at')}
    except Exception as e:      # a crash is a failed case, never a crashed run
        return {'verdict': 'error', 'origin': None, 'seconds': round(time.time() - t0, 1),
                'credits': 0, 'error': str(e)[:200]}


def compare(results, baseline):
    """Cases whose verdict got worse than the baseline."""
    return [cid for cid, r in results.items()
            if cid in baseline and RANK.get(r['verdict'], 0) < RANK.get(baseline[cid]['verdict'], 0)]


def format_table(results, baseline=None):
    rows = ['case                  | verdict    | baseline   | seconds | credits | origin']
    rows.append('-' * 100)
    for cid, r in results.items():
        b = (baseline or {}).get(cid, {}).get('verdict', '-')
        rows.append(f"{cid:<21} | {r['verdict']:<10} | {b:<10} | {r['seconds']:>7} | {str(r['credits']):>7} | {(r.get('origin') or r.get('error') or '')[:60]}")
    return '\n'.join(rows)


def save_results(engine, results):
    out_dir = os.path.join(HERE, 'results')
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = os.path.join(out_dir, f'{stamp}_{engine}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'engine': engine, 'recorded': stamp, 'results': results}, f, indent=1, ensure_ascii=False)
    return path
