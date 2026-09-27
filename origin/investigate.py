"""Origin v2 orchestrator (ORIGIN_V2_PLAN.md §5).

0. prepare copies (upload / screenshot crop / small re-encode), signature
1. round 1: Lens exact (en, ar) + Lens visual + Yandex + TinEye on copy #1,
   all in parallel; if Google refused the file, the same Lens calls on the
   small copy
2. verify candidate pages in parallel (platform media -> page images ->
   engine thumbnails); page/platform matches contribute new copies
3. round 2 (and 3): Lens exact on the largest new copies, Yandex on the
   first; verify what is new
4. identification + text search (phase 2)
5. decide with the one eligibility rule; build the payload
"""
import concurrent.futures
import logging
import os
import time

import requests

from origin import copies as copies_mod, dates, engines, report, urls, verify
from origin.budget import Budget

logger = logging.getLogger(__name__)

VERIFY_WORKERS = 10
ROUND1_PAGES = 40
ROUND2_PAGES = 20
MAX_ROUNDS = 3
NEW_COPIES_PER_ROUND = 2
PER_DOMAIN = 3


def _noop(_msg):
    pass


def _download(url, timeout=(5, 20)):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception as e:
        logger.warning('cannot download query image: %s', e)
        return None


class Investigation:
    def __init__(self, image_url, progress, budget):
        self.image_url = image_url
        self.progress = progress or _noop
        self.budget = budget
        self.copyset = None
        self.sigs = []
        self.seen = set()            # canonical URLs already verified/queued
        self.sightings = []
        self.engines = {}            # label -> brief
        self.rounds = []
        self.extras = {}

    # -- engines
    def run(self, tasks, timeout_s=60):
        answers = engines.run_parallel(tasks, self.budget, timeout_s=timeout_s, progress=self.progress)
        for label, ans in answers.items():
            self.engines[label] = ans.brief()
        return answers

    # -- verification
    def verify_many(self, cands, round_no):
        allowed = self.budget.take_pages(len(cands))
        cands = cands[:allowed]
        if not cands:
            return []
        self.progress(f'فحص {len(cands)} صفحة...')
        results = []
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(VERIFY_WORKERS, len(cands)))
        futures = {ex.submit(self._verify_one, c, round_no): c for c in cands}
        done = 0
        try:
            for fut in concurrent.futures.as_completed(futures, timeout=max(20, min(70, self.budget.time_left()))):
                done += 1
                try:
                    s = fut.result()
                    if s:
                        results.append(s)
                except Exception as e:
                    logger.info('verify crashed: %s', e)
                if done % 5 == 0:
                    self.progress(f'تم فحص {done}/{len(cands)} صفحة')
        except concurrent.futures.TimeoutError:
            self.budget.skip(f'verify round {round_no}', 'time')
        finally:
            ex.shutdown(wait=False)
        self.sightings.extend(results)
        return results

    def _verify_one(self, cand, round_no):
        url = cand['url']
        v = verify.verify_page(url, self.sigs, engine_thumbs=cand.get('thumbs') or [])
        d = dates.for_page(url, v.get('html'), v.get('headers'), tweet=v.get('tweet'),
                           extra=v.get('extra_dates'), crawl_date=cand.get('crawl_date'))
        s = {'url': url, 'canonical': cand.get('canonical') or urls.canonical(url),
             'title': v.get('title'), 'caption': v.get('caption'),
             'image': v['image'], 'date': d, 'match': cand.get('match'),
             'engines': cand.get('engines') or [], 'thumbs': cand.get('thumbs') or [],
             'copy_ids': set(cand.get('copy_ids') or []), 'round': round_no}
        pil = v.get('matched_pil')
        if pil is not None and v['image'].level in ('platform', 'page') and min(pil.size) >= copies_mod.MIN_COPY_PX:
            c = self.copyset.add(v['image'].matched_url, pil, 'platform' if v['image'].level == 'platform' else 'page',
                                 found_on=url)
            if c is not None:
                s['copy_ids'].add(c.id)
        return s

    def new_candidates(self, answers):
        merged = engines.merge_candidates(answers.values(), self.seen)
        for c in merged:
            self.seen.add(c['canonical'])
        return merged


def investigate(image_url, *, progress=None, extra_frame_urls=None):
    """Image investigation. Returns the UI payload (see report.build).
    Never raises."""
    progress = progress or _noop
    budget = Budget(kind='video' if extra_frame_urls else 'image')
    inv = Investigation(image_url, progress, budget)
    if not os.environ.get('SERPAPI_API_KEY'):
        return _unavailable('SerpAPI key not configured', budget)

    # 0. prepare
    progress('تجهيز الصورة ونسخ البحث...')
    data = _download(image_url)
    if not data:
        return _unavailable('cannot download the query image', budget)
    from services.visual_verify import build_query_signature
    cs, primary_pil, extras = copies_mod.prepare(data, image_url)
    inv.copyset = cs
    inv.extras.update(extras)
    sig = build_query_signature(primary_pil) if primary_pil is not None else None
    if sig is None:
        return _unavailable('cannot decode the query image', budget)
    inv.sigs = [sig]
    if extras.get('screenshot'):
        shot = build_query_signature(data)
        if shot:
            inv.sigs.append(shot)
    primary = next((c for c in cs.copies if c.source == 'upload'), cs.copies[0] if cs.copies else None)
    if primary is None:
        return _unavailable('no searchable copy', budget)
    small = next((c for c in cs.copies if c.source == 'small'), None)

    # 1. round 1
    progress('البحث في المحركات (Lens, Yandex, TinEye)...')
    tasks = [
        ('lens_exact_en', lambda: engines.lens_exact(primary.url, 'en', 'us', primary.id), engines.LENS_CREDITS),
        ('lens_exact_ar', lambda: engines.lens_exact(primary.url, 'ar', 'sa', primary.id), engines.LENS_CREDITS),
        ('lens_visual', lambda: engines.lens_visual(primary.url, copy_id=primary.id), engines.LENS_CREDITS),
        ('yandex', lambda: engines.yandex(primary.url, primary.id), engines.YANDEX_CREDITS),
        ('tineye', lambda: engines.tineye(primary.url, primary.id), 0),
    ]
    for name in ('lens_exact_en', 'lens_exact_ar', 'lens_visual', 'yandex', 'tineye'):
        cs.mark(primary, name)
    answers = inv.run(tasks, timeout_s=70)
    refused = (answers.get('lens_visual') and answers['lens_visual'].status == 'refused')
    if refused and small is not None and budget.time_left() > 60:
        progress('لم يقبل Google الملف — إعادة البحث بنسخة مصغّرة...')
        tasks = [
            ('lens_exact_en@small', lambda: engines.lens_exact(small.url, 'en', 'us', small.id, no_cache=True), engines.LENS_CREDITS),
            ('lens_exact_ar@small', lambda: engines.lens_exact(small.url, 'ar', 'sa', small.id, no_cache=True), engines.LENS_CREDITS),
            ('lens_visual@small', lambda: engines.lens_visual(small.url, copy_id=small.id, no_cache=True), engines.LENS_CREDITS),
        ]
        for name in ('lens_exact_en', 'lens_exact_ar', 'lens_visual'):
            cs.mark(small, name)
        answers.update(inv.run(tasks, timeout_s=60))
    # exact "refused" next to a visual that answered = genuinely no exact matches
    for k, a in answers.items():
        if k.startswith('lens_exact') and a.status == 'refused':
            twin = answers.get('lens_visual@small' if k.endswith('@small') else 'lens_visual')
            if twin and twin.status in ('results', 'empty'):
                a.status = 'empty'
                inv.engines[k] = a.brief()

    # 2. verify round 1
    cands = engines.rank_candidates(inv.new_candidates(answers), PER_DOMAIN, ROUND1_PAGES)
    inv.rounds.append({'round': 1, 'candidates': len(cands)})
    inv.verify_many(cands, 1)

    # 3. rounds 2..3 on new copies
    for rnd in range(2, MAX_ROUNDS + 1):
        if budget.time_left() < 45:
            budget.skip(f'round {rnd}', 'time')
            break
        new_copies = cs.unsearched('lens_exact_en', limit=NEW_COPIES_PER_ROUND)
        new_copies = [c for c in new_copies if c.source in ('page', 'platform')]
        if not new_copies:
            break
        progress('عُثر على نسخة أصلية — إعادة البحث بها...')
        tasks = []
        for i, c in enumerate(new_copies):
            cs.mark(c, 'lens_exact_en')
            tasks.append((f'lens_exact_en@copy{c.id}', (lambda c=c: engines.lens_exact(c.url, 'en', 'us', c.id)), engines.LENS_CREDITS))
            if i == 0:
                cs.mark(c, 'lens_exact_ar')
                cs.mark(c, 'yandex')
                tasks.append((f'lens_exact_ar@copy{c.id}', (lambda c=c: engines.lens_exact(c.url, 'ar', 'sa', c.id)), engines.LENS_CREDITS))
                tasks.append((f'yandex@copy{c.id}', (lambda c=c: engines.yandex(c.url, c.id)), engines.YANDEX_CREDITS))
        answers = inv.run(tasks, timeout_s=50)
        cands = engines.rank_candidates(inv.new_candidates(answers), PER_DOMAIN, ROUND2_PAGES)
        inv.rounds.append({'round': rnd, 'copies': [c.id for c in new_copies], 'candidates': len(cands)})
        if cands:
            inv.verify_many(cands, rnd)

    # 4. identification + text search: phase 2

    # 5. decide
    progress('تحديد أول ظهور...')
    payload = report.build(inv.sightings, copies=cs.briefs(), engines=inv.engines, budget=budget,
                           extras={**inv.extras, 'rounds': inv.rounds})
    progress('اكتمل تحليل المصدر')
    return payload


def _unavailable(note, budget):
    return {'success': False, 'engine': 'origin_engine', 'version': 2, 'note': note,
            'first_seen': None, 'timeline': [], 'engines': {}, 'budget': budget.snapshot()}
