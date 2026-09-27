"""Run the origin benchmark. See benchmark/runner.py for the rules."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--engine', choices=['v1', 'v2'], default='v2')
    ap.add_argument('--case', action='append', help='case id (repeatable)')
    ap.add_argument('--check', action='store_true', help='exit 1 on regression vs baseline_v1.json')
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv('.env')
    from app import app
    from benchmark import runner

    cases = runner.load_cases()
    if args.case:
        cases = [c for c in cases if c['id'] in set(args.case)]
    baseline = runner.load_baseline()

    if args.engine == 'v1':
        from services.origin_agent import investigate as _inv
    else:
        from origin.investigate import investigate as _inv

    results = {}
    with app.app_context():
        for case in cases:
            print(f"-- {case['id']} ({case['kind']}) ...", flush=True)
            results[case['id']] = runner.run_case(case, lambda url: _inv(url, progress=lambda m: None))
            r = results[case['id']]
            print(f"   {r['verdict']}  {r.get('origin') or r.get('error')}  ({r['seconds']}s, {r['credits']} credits)", flush=True)
    print()
    print(runner.format_table(results, baseline))
    path = runner.save_results(args.engine, results)
    print('saved', path)
    if args.check:
        worse = runner.compare(results, baseline)
        if worse:
            print('REGRESSION:', ', '.join(worse))
            sys.exit(1)
        print('no regression')


if __name__ == '__main__':
    main()
