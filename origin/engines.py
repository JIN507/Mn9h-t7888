"""Engine adapters. Every call answers with an EngineAnswer whose status is
one of results | empty | refused | error | skipped — never a silent zero.
Paid calls (SerpAPI) reserve credits on the Budget before they run; when
the cap would be crossed the call is skipped and recorded.
"""
import concurrent.futures
import logging
import os
from dataclasses import dataclass, field

from origin import urls
from origin.budget import BudgetExceeded

logger = logging.getLogger(__name__)

LENS_CREDITS = 1
YANDEX_CREDITS = 1
TEXT_CREDITS = 1


@dataclass
class EngineAnswer:
    name: str
    status: str                      # results | empty | refused | error | skipped
    candidates: list = field(default_factory=list)
    credits: int = 0
    note: str = ''
    copy_id: int = None

    def brief(self):
        return {'status': self.status, 'count': len(self.candidates), 'credits': self.credits,
                'note': self.note or None, 'copy_id': self.copy_id}


def _cand(link, *, engine, copy_id, title='', thumb=None, image_url=None, match='similar', **extra):
    if not link or urls.is_junk(link):
        return None
    d = {'url': link, 'title': (title or '')[:200], 'thumb': thumb, 'image_url': image_url,
         'engine': engine, 'copy_id': copy_id, 'match': match}
    d.update({k: v for k, v in extra.items() if v})
    return d


def _from_serp_rows(rows, engine, copy_id, default_match):
    out = []
    for m in rows or []:
        c = _cand(m.get('link'), engine=engine, copy_id=copy_id, title=m.get('title'),
                  thumb=m.get('thumbnail'), image_url=m.get('image_url'),
                  match={'exact': 'exact', 'similar': 'similar'}.get(m.get('match_type'), default_match),
                  crawl_date=m.get('crawl_date'), first_indexed=m.get('first_indexed'),
                  engine_date=m.get('date'))
        if c:
            out.append(c)
    return out


# ------------------------------------------------------------- SerpAPI

def lens_exact(copy_url, hl='en', country='us', copy_id=None, no_cache=False):
    from providers.serpapi import lens_matches, SerpApiNoResults
    name = f'lens_exact_{hl}'
    try:
        rows = lens_matches(copy_url, 'exact_matches', hl=hl, country=country, no_cache=no_cache)
    except SerpApiNoResults as e:
        return EngineAnswer(name, 'refused', credits=LENS_CREDITS, note=str(e)[:120], copy_id=copy_id)
    except Exception as e:
        return EngineAnswer(name, 'error', credits=LENS_CREDITS, note=str(e)[:120], copy_id=copy_id)
    cands = _from_serp_rows(rows, name, copy_id, 'exact')
    return EngineAnswer(name, 'results' if cands else 'empty', cands, LENS_CREDITS, copy_id=copy_id)


def lens_visual(copy_url, hl='en', country='us', copy_id=None, no_cache=False):
    from providers.serpapi import lens_matches, SerpApiNoResults
    name = 'lens_visual'
    try:
        rows = lens_matches(copy_url, 'visual_matches', hl=hl, country=country, no_cache=no_cache)
    except SerpApiNoResults as e:
        return EngineAnswer(name, 'refused', credits=LENS_CREDITS, note=str(e)[:120], copy_id=copy_id)
    except Exception as e:
        return EngineAnswer(name, 'error', credits=LENS_CREDITS, note=str(e)[:120], copy_id=copy_id)
    cands = _from_serp_rows(rows, name, copy_id, 'similar')
    return EngineAnswer(name, 'results' if cands else 'empty', cands, LENS_CREDITS, copy_id=copy_id)


def yandex(copy_url, copy_id=None):
    from providers import yandex as yp
    name = 'yandex'
    try:
        rows = yp.reverse_image(copy_url)
    except Exception as e:
        note = str(e)[:120]
        status = 'refused' if 'not publicly accessible' in note.lower() else 'error'
        return EngineAnswer(name, status, credits=YANDEX_CREDITS, note=note, copy_id=copy_id)
    cands = _from_serp_rows(rows, name, copy_id, 'similar')
    return EngineAnswer(name, 'results' if cands else 'empty', cands, YANDEX_CREDITS, copy_id=copy_id)


def google_text(query, hl='en', gl='us', num=20):
    from providers.serpapi import web_search
    name = 'text'
    try:
        rows = web_search(query, hl=hl, gl=gl, num=num)
    except Exception as e:
        return EngineAnswer(name, 'error', credits=TEXT_CREDITS, note=str(e)[:120])
    cands = []
    for r in rows:
        c = _cand(r.get('link'), engine=name, copy_id=None, title=r.get('title'), match='text',
                  snippet=(r.get('snippet') or '')[:200], date_hint=r.get('date'))
        if c:
            cands.append(c)
    return EngineAnswer(name, 'results' if cands else 'empty', cands, TEXT_CREDITS, note=query[:80])


# ------------------------------------------------------------- free engines

def tineye(copy_url, copy_id=None):
    name = 'tineye'
    try:
        from providers import browser_search
        if not browser_search.configured():
            return EngineAnswer(name, 'skipped', note='not configured', copy_id=copy_id)
        rows = browser_search.tineye_web(copy_url)
    except Exception as e:
        return EngineAnswer(name, 'error', note=str(e)[:120], copy_id=copy_id)
    cands = _from_serp_rows(rows, name, copy_id, 'exact')
    return EngineAnswer(name, 'results' if cands else 'empty', cands, 0, copy_id=copy_id)


def vision(image_bytes, copy_id=None):
    """Google Cloud Vision Web Detection on BYTES (optional; needs credentials)."""
    name = 'vision'
    try:
        from providers import vision as vp
        if not vp.configured():
            return EngineAnswer(name, 'skipped', note='not configured', copy_id=copy_id)
        fn = getattr(vp, 'web_detection_bytes', None)
        if fn is None:
            return EngineAnswer(name, 'skipped', note='bytes upload not implemented', copy_id=copy_id)
        rows = fn(image_bytes)
    except Exception as e:
        return EngineAnswer(name, 'error', note=str(e)[:120], copy_id=copy_id)
    cands = _from_serp_rows(rows, name, copy_id, 'similar')
    return EngineAnswer(name, 'results' if cands else 'empty', cands, 0, copy_id=copy_id)


# ------------------------------------------------------------- runner

def run_parallel(tasks, budget, timeout_s=60, progress=None):
    """tasks: [(label, callable, credits)]. Reserves credits first (skipping
    what the budget cannot pay), runs the rest in parallel, returns
    {label: EngineAnswer}. A task that outruns `timeout_s` is reported as
    error 'timeout' and left to finish in the background."""
    answers = {}
    runnable = []
    for label, fn, credits in tasks:
        if credits:
            try:
                budget.charge(credits, label)
            except BudgetExceeded as e:
                answers[label] = EngineAnswer(label, 'skipped', note=f'budget: {e}')
                budget.skip(label, 'credits')
                continue
        runnable.append((label, fn))
    if not runnable:
        return answers
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=len(runnable))
    futures = {ex.submit(fn): label for label, fn in runnable}
    try:
        for fut in concurrent.futures.as_completed(futures, timeout=timeout_s):
            label = futures[fut]
            try:
                ans = fut.result()
            except Exception as e:
                ans = EngineAnswer(label, 'error', note=str(e)[:120])
            answers[label] = ans
            if progress:
                progress(f'{label}: ' + _arabic_status(ans))
    except concurrent.futures.TimeoutError:
        for fut, label in futures.items():
            if not fut.done():
                answers[label] = EngineAnswer(label, 'error', note='timeout')
    finally:
        ex.shutdown(wait=False)
    return answers


def _arabic_status(ans):
    return {'results': f'{len(ans.candidates)} نتيجة', 'empty': 'لا نتائج',
            'refused': 'لم يقبل المحرك الصورة', 'error': 'تعذّر', 'skipped': 'تخطّي'}.get(ans.status, ans.status)


def merge_candidates(answers, seen=None):
    """Unique candidates across answers by canonical URL; the strongest
    match label and every engine kept. Junk and already-seen dropped."""
    seen = seen if seen is not None else set()
    rank = {'exact': 0, 'text': 1, 'page': 2, 'similar': 3}
    merged = {}
    for ans in answers:
        for c in ans.candidates:
            canon = urls.canonical(c['url'])
            if not canon or canon in seen:
                continue
            e = merged.get(canon)
            if e is None:
                e = merged[canon] = dict(c, canonical=canon, engines=[c['engine']], thumbs=[],
                                         copy_ids={c.get('copy_id')} - {None})
            else:
                if c['engine'] not in e['engines']:
                    e['engines'].append(c['engine'])
                if rank.get(c['match'], 9) < rank.get(e['match'], 9):
                    e['match'] = c['match']
                if c.get('copy_id') is not None:
                    e['copy_ids'].add(c['copy_id'])
                for k in ('crawl_date', 'first_indexed', 'title', 'engine_date'):
                    if not e.get(k) and c.get(k):
                        e[k] = c[k]
            for t in (c.get('image_url'), c.get('thumb')):
                if t and t.startswith('http') and t not in e['thumbs']:
                    e['thumbs'].append(t)
    return list(merged.values())


SOCIAL_PER_DOMAIN = 12     # posts on one platform are distinct authors, not one site


def date_hint(cand):
    """Zero-cost publication hint: the post id in the URL (X snowflake,
    Instagram shortcode, TikTok id) or the date the engine showed."""
    if cand.get('date_hint') is not None:
        return cand['date_hint']
    from services import date_evidence as de
    hint = None
    try:
        ev = de.platform_date(cand['url']) or []
        if ev:
            hint = ev[0]['date']
    except Exception:
        hint = None
    if not hint and cand.get('engine_date'):
        try:
            dt = de.parse_date(cand['engine_date'])
            hint = de.to_iso(dt) if dt else None
        except Exception:
            hint = None
    cand['date_hint'] = hint or ''
    return cand['date_hint']


def rank_candidates(cands, per_domain=3, limit=40):
    """Who gets a page fetch: thumbnail matches and exact rows first, then
    the earliest-dated posts (ids decode for free), social before web,
    listings last; one web domain never floods, platforms get more room."""
    def score(c):
        s = {'exact': 0, 'text': 15, 'page': 20, 'similar': 30}.get(c['match'], 40)
        tv = (c.get('thumb_check') or {}).get('verdict')
        if tv == 'match':
            s -= 30
        elif tv == 'differs':
            s += 60
        s -= 5 * min(len(c.get('engines') or []), 3)
        if c.get('crawl_date'):
            s -= 6
        hint = date_hint(c)
        if urls.is_social(c['url']):
            s -= 4
            if hint:
                s -= 30                  # a post whose id dates it: cheapest possible origin check
        if urls.is_listing(c['url']):
            s += 40                      # listings are never origins: last
        return (s, hint or '9999')
    out, per = [], {}
    for c in sorted(cands, key=score):
        d = urls.domain_of(c['url'])
        cap = SOCIAL_PER_DOMAIN if urls.is_social(c['url']) else per_domain
        if per.get(d, 0) >= cap:
            continue
        per[d] = per.get(d, 0) + 1
        out.append(c)
        if len(out) >= limit:
            break
    return out
