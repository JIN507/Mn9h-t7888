"""Origin Agent — DeepSeek drives the investigation with tools.

    LOOK      vision: what/who/where is in the image, visible text, logos,
              event guess, suggested queries            (deepseek.describe_image)
    ROUND 0   deterministic harvest + inspection        (origin_engine)
    LOOP      the model chooses the next move:
                reverse_search(engine, image_url?)  Lens / Yandex / TinEye / Bing
                inspect_pages(urls)                 date evidence + visual verify
                web_search(query)                   text leads (Zenserp)
                read_page(url)                      page text + dates + images
                finish(first_seen_url, reasoning)
              every tool result carries the current best finding, so the
              model always reasons from evidence, never from memory.
    VERDICT   first_seen = earliest visually-confirmed, dated sighting
              (services.origin_engine.assess). The model's own pick is kept
              as `agent.pick` and only becomes first_seen if it passes the
              same evidence bar. The model can explain; it cannot assert.

Budget: max steps, max inspections, soft wall-clock. Without a DeepSeek
key the caller should use origin_engine.investigate_origin instead.
"""
import concurrent.futures
import json
import logging
import os
import re
import time

import requests

from providers import deepseek
from services import origin_engine as oe
from services.visual_verify import UA, build_query_signature

logger = logging.getLogger(__name__)

DEFAULT_BUDGET = {
    'max_steps': 10,          # LLM turns after round 0
    'max_tool_calls': 16,
    'max_inspections': 70,    # pages fetched over the whole run
    'round0_inspect': 28,
    'auto_inspect': 8,        # pages auto-inspected after a reverse_search
    'per_domain': 3,
    'soft_time_s': 240,
    'workers': 8,
}

VISION_PROMPT = (
    'You are an OSINT analyst. Describe this image for a provenance '
    'investigation. Return strict JSON with keys: '
    '"description" (2 sentences), '
    '"subjects" (list of {"type": "person|place|object|vehicle|text", '
    '"name_guess": string|null, "confidence": 0-1}), '
    '"visible_text" (list of strings exactly as written, any language), '
    '"logos_or_watermarks" (list), '
    '"event_guess" (string|null), "place_guess" (string|null), '
    '"date_guess" (string|null), "language_guess" (string|null), '
    '"is_screenshot" (bool — TV/phone/social-media screenshot?), '
    '"platform_hint" (e.g. "X/Twitter", "TV channel", "Telegram", null), '
    '"suggested_queries" (3-5 short web-search queries, mixing the image\'s '
    'language and English, that would surface the ORIGINAL post/article). '
    'Guesses must be marked as guesses via confidence; never state a fact '
    'you cannot see.'
)

SYSTEM_PROMPT = (
    'You are an expert OSINT image-provenance investigator. Goal: find the '
    'EARLIEST page that published THIS EXACT image (the origin), and the '
    'pages that re-shared it afterwards.\n'
    'Rules:\n'
    '1. Only pages that are VISUALLY CONFIRMED to show the image and have a '
    'DATED evidence chain count. Tool results tell you both.\n'
    '2. Think like an investigator: use the image description (who/what/'
    'event/visible text/logos) to reason where it was first posted — '
    'official accounts, agencies, the outlet whose watermark is visible, '
    'the person themselves. Use web_search to find that post, then '
    'inspect_pages/read_page to verify and date it.\n'
    '3. Social posts give exact timestamps (X/Twitter IDs). News sites give '
    'publish tags. Prefer inspecting those over blogs and aggregators.\n'
    '4. If a confirmed page holds a higher-resolution or uncropped copy, '
    'run reverse_search again with that image_url — originals surface '
    'more exact matches than screenshots.\n'
    '5. Try engines you have not used yet when results are thin '
    '(Yandex for faces/Russian/Arabic ecosystems, TinEye/Bing for older '
    'web).\n'
    '6. Never invent URLs or dates. Never conclude from memory of the '
    'event — conclude from tool evidence.\n'
    '7. Be economical: each tool call costs budget shown in results. Call '
    'finish as soon as no earlier sighting is plausible, or when budget '
    'is nearly spent. In finish, explain the evidence chain in 3-6 '
    'sentences (English is fine).\n'
    '8. VIDEO queries: pages show other moments of the clip, so visual '
    'verdicts are often "ambiguous" or "probable" (many sightings of the '
    'same scene within days). Treat "probable" as the clip; still prefer '
    'the earliest dated post from the account that filmed it.'
)

TOOLS = [
    {'type': 'function', 'function': {
        'name': 'reverse_search',
        'description': 'Reverse-image search on one engine. Returns new '
                       'candidate pages (auto-inspects the most promising '
                       'ones) plus the current best finding.',
        'parameters': {'type': 'object', 'properties': {
            'engine': {'type': 'string',
                       'enum': ['lens_exact', 'lens_visual', 'yandex',
                                'tineye', 'bing']},
            'image_url': {'type': 'string',
                          'description': 'Optional: search with a different '
                                         'copy of the image, e.g. a higher-'
                                         'resolution original found on a '
                                         'confirmed page.'},
        }, 'required': ['engine']}}},
    {'type': 'function', 'function': {
        'name': 'inspect_pages',
        'description': 'Fetch up to 8 URLs: extract publication-date '
                       'evidence and visually verify that the page shows '
                       'the image. Verified, dated pages enter the timeline.',
        'parameters': {'type': 'object', 'properties': {
            'urls': {'type': 'array', 'items': {'type': 'string'},
                     'maxItems': 8}}, 'required': ['urls']}}},
    {'type': 'function', 'function': {
        'name': 'web_search',
        'description': 'Text web search (Google via Zenserp). Returns leads '
                       '(url, title, snippet). Leads are NOT evidence until '
                       'inspected.',
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string'},
            'lang': {'type': 'string', 'enum': ['en', 'ar', 'auto'],
                     'description': 'default auto'}},
            'required': ['query']}}},
    {'type': 'function', 'function': {
        'name': 'read_page',
        'description': 'Read one page in more depth: title, text excerpt, '
                       'all date evidence, images found, visual verdict, '
                       'credits/handles mentioned.',
        'parameters': {'type': 'object', 'properties': {
            'url': {'type': 'string'}}, 'required': ['url']}}},
    {'type': 'function', 'function': {
        'name': 'grok_search',
        'description': 'Ask Grok (xAI) to search X/Twitter and the web for '
                       'the original post of this image. Returns its answer '
                       'and the URLs it cites as LEADS (not evidence — '
                       'inspect them). Use when the origin is likely a '
                       'social post. Unavailable if the account has no credits.',
        'parameters': {'type': 'object', 'properties': {
            'question': {'type': 'string',
                         'description': 'What to find, in English, e.g. '
                                        '"earliest X post of this photo of ..."'}},
            'required': ['question']}}},
    {'type': 'function', 'function': {
        'name': 'finish',
        'description': 'End the investigation with your conclusion.',
        'parameters': {'type': 'object', 'properties': {
            'first_seen_url': {'type': ['string', 'null'],
                               'description': 'URL of the earliest verified '
                                              'sighting, or null if none.'},
            'reasoning': {'type': 'string'},
            'confidence': {'type': 'string', 'enum': ['high', 'medium', 'low']},
        }, 'required': ['first_seen_url', 'reasoning', 'confidence']}}},
]

ENGINE_MAP = {
    'lens_exact': ('lens_exact_en', 'lens_exact_ar'),
    'lens_visual': ('lens_visual',),
    'yandex': ('yandex',),
    'tineye': ('tineye', 'tineye_web'),
    'bing': ('bing_web',),
}

_ARABIC = re.compile(r'[؀-ۿ]')


def _noop(_msg):
    pass


def _resolve_redirect(url, timeout=(5, 10)):
    """Google/Zenserp hand back click-redirects (google.com/goto?url=...);
    one non-following GET reveals the real target in Location."""
    try:
        host = oe.domain_of(url)
        if not (host.endswith('google.com') and '/goto' in url or '/url?' in url):
            return url
        r = requests.get(url, headers=UA, allow_redirects=False, timeout=timeout)
        loc = r.headers.get('Location')
        if loc and loc.startswith('http'):
            return loc
    except Exception as e:
        logger.info('redirect resolve failed for %s: %s', url[:80], e)
    return url


def resolve_redirects(urls, workers=8):
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_resolve_redirect, urls))


def _download(image_url, timeout=(5, 20)):
    r = requests.get(image_url, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.content, r.headers.get('Content-Type', 'image/jpeg').split(';')[0]


# ------------------------------------------------------------ investigation

class Investigation:
    """Mutable state shared by the tools."""

    def __init__(self, image_url, query_sig, progress, budget):
        self.image_url = image_url
        self.image_bytes = None
        self.extra_frames = []
        self.query_sig = query_sig
        self.progress = progress
        self.budget = budget
        self.started = time.monotonic()
        self.seen = set()            # canonical URLs already known
        self.pending = {}            # canonical -> candidate not yet inspected
        self.timeline = []           # inspected items (origin_engine shape)
        self.by_canonical = {}
        self.engines_status = {}
        self.steps = []
        self.inspections = 0
        self.tool_calls = 0
        self.llm_calls = 0
        self.tokens = 0

    # -- helpers
    def time_left(self):
        return self.budget['soft_time_s'] - (time.monotonic() - self.started)

    def first_seen(self):
        if self.extra_frames:
            oe.video_consensus(self.timeline)
        return oe.assess(self.timeline)

    def add_candidates(self, raw, round_no):
        cands = oe.merge_candidates(raw, self.seen)
        for c in cands:
            c['round'] = round_no
            self.seen.add(c['canonical'])
            self.pending[c['canonical']] = c
        return cands

    def inspect(self, cands, *, strict=False):
        room = self.budget['max_inspections'] - self.inspections
        cands = cands[:max(0, room)]
        if not cands:
            return []
        self.inspections += len(cands)
        items = oe.inspect_many(cands, self.query_sig, self.budget['workers'],
                                self.progress, strict=strict)
        for it in items:
            canon = oe.canonical_url(it['url']) or it['url']
            self.pending.pop(canon, None)
            if canon in self.by_canonical:
                continue
            self.by_canonical[canon] = it
            self.timeline.append(it)
        return items

    def candidate_for(self, url):
        canon = oe.canonical_url(url)
        if canon and canon in self.pending:
            return self.pending[canon]
        return {'url': url, 'canonical': canon or url,
                'domain': oe.domain_of(url), 'title': '',
                'match_type': 'organic', 'providers': ['agent'],
                'engine_images': [], 'thumbnail': None, 'crawl_date': None,
                'is_image': oe.is_image_url(url), 'round': 99}

    # -- compact views for the model
    def item_brief(self, it):
        v = it['visual'] or {}
        return {
            'url': it['url'], 'date': it.get('published_at'),
            'date_confidence': round(it.get('confidence') or 0, 2),
            'upper_bound_only': bool(it.get('is_upper_bound')),
            'date_sources': [e['source'] for e in (it.get('evidence') or [])[:2]],
            'visual': v.get('verdict'),
            'similarity': v.get('similarity'),
            'match': it.get('match_type'),
            'title': (it.get('title') or '')[:90],
        }

    def findings(self, limit=10):
        fs = self.first_seen()
        dated = sorted([i for i in self.timeline if i['published_at']
                        and i['visual']['verdict'] != 'rejected'
                        and not i.get('dropped')],
                       key=oe._first_seen_key)
        pend = sorted(self.pending.values(),
                      key=lambda c: oe.MATCH_RANK.get(c['match_type'], 9))
        social = [c for c in pend if oe.is_social(c['url'])]
        return {
            'current_first_seen': self.item_brief(fs) if fs else None,
            **({'earliest_by_scene_frame': {str(f): self.item_brief(i) for f, i in
                                             oe.earliest_by_frame(self.timeline).items()}}
               if self.extra_frames else {}),
            'earliest_verified': [self.item_brief(i) for i in dated[:limit]],
            'counts': {'inspected': len(self.timeline),
                       'visually_confirmed': sum(1 for i in self.timeline
                                                 if i['visual']['verdict'] == 'confirmed'),
                       'pending_not_inspected': len(self.pending)},
            'pending_social_posts': [{'url': c['url'], 'match': c['match_type']}
                                     for c in social[:6]],
            'pending_sample': [{'url': c['url'], 'match': c['match_type'],
                                'engines': c['providers']} for c in pend[:8]],
            'budget_left': {'tool_calls': self.budget['max_tool_calls'] - self.tool_calls,
                            'inspections': self.budget['max_inspections'] - self.inspections,
                            'seconds': int(self.time_left())},
        }


# ------------------------------------------------------------------ tools

def tool_reverse_search(inv, engine, image_url=None):
    pivot = image_url if (image_url and image_url.startswith('http')) else None
    target = pivot or inv.image_url
    names = ENGINE_MAP.get(engine, ())
    raw, statuses = [], {}
    extra = {}
    if engine == 'bing':
        try:
            from providers import browser_search
            if browser_search.configured():
                caption, leads = browser_search.bing_search(target)
                extra['bing_auto_caption'] = caption
                extra['hint'] = ('Bing identified the image as this caption; '
                                 'use web_search with it (and its Arabic '
                                 'equivalent) to find the original post.')
                raw.extend(leads)
                statuses['bing_web'] = {'ok': True, 'count': len(leads)}
                inv.engines_status['bing_web'] = dict(statuses['bing_web'],
                                                      caption=caption)
            else:
                statuses['bing_web'] = {'ok': False, 'count': 0, 'note': 'not configured'}
        except Exception as e:
            statuses['bing_web'] = {'ok': False, 'count': 0, 'note': str(e)[:120]}
        names = ()
    for name in names:
        got, st = oe.harvest_engine(name, target)
        statuses[name] = st
        key = f'{name}@pivot' if pivot else name
        inv.engines_status[key] = dict(st, **({'pivot_image': pivot} if pivot else {}))
        raw.extend(got)
    inv.progress(f'الوكيل: بحث عكسي ({engine})' + (' بنسخة أخرى من الصورة' if pivot else ''))
    new = inv.add_candidates(raw, round_no=len(inv.steps) + 1)
    chosen = oe.prioritize(new, inv.budget['auto_inspect'], inv.budget['per_domain'])
    if chosen:
        inv.progress(f'الوكيل: فحص {len(chosen)} صفحة جديدة')
    items = inv.inspect(chosen)
    return {
        **extra,
        'engine_status': statuses,
        'raw_matches': len(raw), 'new_candidates': len(new),
        'inspected': [inv.item_brief(i) for i in items],
        'not_inspected': [{'url': c['url'], 'match': c['match_type']}
                          for c in new if c not in chosen][:12],
    }


def tool_inspect_pages(inv, urls):
    urls = [u for u in (urls or []) if isinstance(u, str) and u.startswith('http')][:8]
    cands, already = [], []
    for u in urls:
        canon = oe.canonical_url(u) or u
        if canon in inv.by_canonical:
            already.append(inv.item_brief(inv.by_canonical[canon]))
        else:
            inv.seen.add(canon)
            cands.append(inv.candidate_for(u))
    inv.progress(f'الوكيل: فحص {len(cands)} صفحة')
    items = inv.inspect(cands)
    return {'inspected': [inv.item_brief(i) for i in items] + already}


def tool_web_search(inv, query, lang='auto'):
    if not os.environ.get('ZENSERP_API_KEY'):
        return {'error': 'text search not configured'}
    from providers.zenserp import text_search
    if lang == 'auto':
        lang = 'ar' if _ARABIC.search(query or '') else 'en'
    gl, hl = ('sa', 'ar') if lang == 'ar' else ('us', 'en')
    inv.progress(f'الوكيل: بحث نصي «{query[:40]}»')
    try:
        resp = text_search(query, num=10, gl=gl, hl=hl)
        if resp.status_code != 200:
            return {'error': f'search HTTP {resp.status_code}'}
        data = resp.json()
    except Exception as e:
        return {'error': f'search failed: {e}'}
    items = [i for i in (data.get('organic') or [])[:10]
             if i.get('url') or i.get('link')]
    resolved = resolve_redirects([i.get('url') or i.get('link') for i in items])
    leads = []
    for item, link in zip(items, resolved):
        if not link or oe.is_junk(link):
            continue
        canon = oe.canonical_url(link)
        leads.append({'url': link, 'title': (item.get('title') or '')[:90],
                      'snippet': (item.get('description') or '')[:160],
                      'social_post': oe.is_social(link),
                      'already_inspected': bool(canon and canon in inv.by_canonical)})
    return {'query': query, 'leads': leads,
            'note': 'Leads are not evidence. inspect_pages the promising ones.'}


def tool_grok_search(inv, question):
    from providers import xai
    if not xai.configured():
        return {'error': 'grok search not configured'}
    inv.progress('الوكيل: يسأل Grok (بحث X والويب)...')
    q = ((question or 'Find the earliest publication of this exact image.')
         + ' Search X (Twitter) and the web. List every URL you find with '
           'its date. Only include URLs you actually retrieved.')
    res = xai.search_origin(inv.image_bytes or inv.image_url, q)
    if res.get('error'):
        inv.engines_status['grok'] = {'ok': False, 'count': 0, 'note': res['error'][:120]}
        return {'error': res['error']}
    leads = []
    for u in res['urls']:
        if oe.is_junk(u):
            continue
        canon = oe.canonical_url(u)
        leads.append({'url': u, 'social_post': oe.is_social(u),
                      'already_inspected': bool(canon and canon in inv.by_canonical)})
    inv.engines_status['grok'] = {'ok': True, 'count': len(leads)}
    return {'answer': res['text'][:2500], 'leads': leads,
            'note': 'Leads are not evidence. inspect_pages the promising ones.'}


def tool_read_page(inv, url):
    if not isinstance(url, str) or not url.startswith('http'):
        return {'error': 'bad url'}
    canon = oe.canonical_url(url) or url
    inv.progress(f'الوكيل: قراءة {oe.domain_of(url)}')
    item = inv.by_canonical.get(canon)
    if item is None:
        inv.seen.add(canon)
        items = inv.inspect([inv.candidate_for(url)])
        item = items[0] if items else None
    if item is None:
        return {'error': 'could not fetch'}
    text = item.get('snippet') or ''
    handles = sorted(set(re.findall(r'@[A-Za-z0-9_]{3,30}', text)))[:8]
    credits = re.findall(r'(?:Photo|Image|Credit|Source|تصوير|المصدر)\s*[:\-–]\s*([^\.\n|]{3,60})',
                         text, re.IGNORECASE)[:5]
    out = inv.item_brief(item)
    out.update({'text_excerpt': text[:1500],
                'evidence': item.get('evidence') or [],
                'matched_image_url': (item.get('visual') or {}).get('matched_image_url'),
                'image_size': item.get('image_size'),
                'captured_at_exif': item.get('captured_at'),
                'handles_mentioned': handles, 'credits_mentioned': credits,
                'fetch_error': bool(item.get('fetch_error'))})
    return out


# ------------------------------------------------------------------ agent

def _summ(tool, args, result):
    if tool == 'reverse_search':
        return (f"{args.get('engine')}: {result.get('raw_matches', 0)} مطابقة، "
                f"{result.get('new_candidates', 0)} جديدة، فُحص {len(result.get('inspected', []))}")
    if tool == 'inspect_pages':
        return f"فُحصت {len(result.get('inspected', []))} صفحة"
    if tool == 'web_search':
        if result.get('error'):
            return f"«{args.get('query', '')[:50]}» → خطأ: {result['error']}"
        return f"«{args.get('query', '')[:50]}» → {len(result.get('leads', []))} نتيجة"
    if tool == 'read_page':
        return f"{oe.domain_of(args.get('url', ''))}: {result.get('visual')} / {result.get('date')}"
    if tool == 'grok_search':
        if result.get('error'):
            return f"Grok: {result['error'][:60]}"
        return f"Grok → {len(result.get('leads', []))} رابطاً"
    if tool == 'finish':
        return f"خلاصة ({args.get('confidence')})"
    return ''


def run_agent(inv, image_context):
    """The tool loop. Returns the model's finish args (or None)."""
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content':
            'IMAGE ANALYSIS (vision model, guesses carry confidence):\n'
            + json.dumps(image_context or {}, ensure_ascii=False)
            + '\n\nROUND 0 FINDINGS (automatic multi-engine harvest, already '
              'inspected):\n' + json.dumps(inv.findings(), ensure_ascii=False)
            + '\n\nDecide the next move. Call tools. Call finish when done.'},
    ]
    finish = None
    nudges = 0
    for step in range(inv.budget['max_steps']):
        if inv.time_left() < 25 or inv.tool_calls >= inv.budget['max_tool_calls']:
            break
        inv.progress('الوكيل يفكر في الخطوة التالية...')
        msg = deepseek.chat_tools(messages, TOOLS)
        inv.llm_calls += 1
        if msg is None:
            break
        inv.tokens += int((msg.get('_usage') or {}).get('total_tokens') or 0)
        assistant = {'role': 'assistant', 'content': msg.get('content') or ''}
        if msg.get('tool_calls'):
            assistant['tool_calls'] = msg['tool_calls']
        messages.append(assistant)

        if not msg.get('tool_calls'):
            nudges += 1
            if nudges > 1:
                break
            messages.append({'role': 'user', 'content':
                             'Use a tool, or call finish with your conclusion.'})
            continue

        for call in msg['tool_calls']:
            name = call.get('function', {}).get('name')
            args = deepseek.parse_tool_args(call)
            inv.tool_calls += 1
            t0 = time.monotonic()
            try:
                if name == 'reverse_search':
                    result = tool_reverse_search(inv, args.get('engine', 'lens_exact'),
                                                 args.get('image_url'))
                elif name == 'inspect_pages':
                    result = tool_inspect_pages(inv, args.get('urls'))
                elif name == 'web_search':
                    result = tool_web_search(inv, args.get('query', ''),
                                             args.get('lang', 'auto'))
                elif name == 'read_page':
                    result = tool_read_page(inv, args.get('url', ''))
                elif name == 'grok_search':
                    result = tool_grok_search(inv, args.get('question', ''))
                elif name == 'finish':
                    finish = args
                    result = {'ok': True}
                else:
                    result = {'error': f'unknown tool {name}'}
            except Exception as e:
                logger.exception('agent tool %s crashed', name)
                result = {'error': str(e)[:200]}
            if name != 'finish':
                result['current_findings'] = inv.findings(limit=6)
            inv.steps.append({'n': len(inv.steps) + 1, 'tool': name, 'args': args,
                              'summary': _summ(name, args, result),
                              'elapsed_s': round(time.monotonic() - t0, 1)})
            messages.append({'role': 'tool', 'tool_call_id': call.get('id'),
                             'content': json.dumps(result, ensure_ascii=False)[:7000]})
            if finish is not None:
                return finish
    return finish


def _validated_pick(inv, finish):
    if not finish or not finish.get('first_seen_url'):
        return None
    canon = oe.canonical_url(finish['first_seen_url'])
    item = inv.by_canonical.get(canon) if canon else None
    if item and oe._eligible_first(item):
        return item
    return None


_NARRATIVE_SYSTEM = (
    'أنت محلل تحقق من الصور. اكتب ملخصاً عربياً (4-7 جمل) لنتيجة التحقيق: '
    'ماذا تُظهر الصورة (باختصار)، أين ظهرت أولاً ومتى وبأي دليل، ثم كيف انتشرت. '
    'اعتمد فقط على البيانات المعطاة. إن كان التاريخ حداً أعلى فقل "على الأقل منذ". '
    'إن لم يوجد ظهور مؤكد فقل ذلك بوضوح واذكر أقرب المؤشرات. لا تخترع شيئاً.'
)


def _narrative(inv, image_context, first_seen, finish):
    if not deepseek.configured() or inv.time_left() < 8:
        return None
    lines = []
    for i in sorted([x for x in inv.timeline if x['published_at']
                     and x['visual']['verdict'] != 'rejected'], key=oe._first_seen_key)[:10]:
        ev = ', '.join(e['source'] for e in (i.get('evidence') or [])[:2])
        lines.append(f"- {i['published_at']} | {i['domain']} | {i['title'][:80]} | "
                     f"ثقة {i['confidence']:.2f} | بصري {i['visual'].get('verdict')} | {ev}")
    hints = oe.earlier_hints(inv.timeline, first_seen)
    scenes = oe.earliest_by_frame(inv.timeline) if inv.extra_frames else {}
    scene_lines = '; '.join(f"الإطار {f}: {i['published_at'][:10]} {i['domain']}" for f, i in sorted(scenes.items()))
    user = ('وصف الصورة: ' + json.dumps((image_context or {}).get('description', ''), ensure_ascii=False)
            + ('\nفيديو من عدة مشاهد — أول ظهور لكل إطار: ' + scene_lines if scenes else '')
            + '\nأول ظهور مؤكد: ' + (f"{first_seen['published_at']} على {first_seen['domain']} ({first_seen['url']})" if first_seen else 'لا يوجد')
            + '\nمؤشرات أقدم ضعيفة التأريخ (ليست مؤكدة): ' + ('; '.join(f"{h['published_at'][:10]} {h['domain']}" for h in hints) or 'لا يوجد')
            + '\nاستنتاج الوكيل: ' + ((finish or {}).get('reasoning') or 'لا يوجد')[:800]
            + '\nالخط الزمني:\n' + '\n'.join(lines))
    return deepseek.chat(_NARRATIVE_SYSTEM, user, max_tokens=550, temperature=0.3)


def investigate(image_url, *, progress=None, budget=None, extra_frame_urls=None):
    """Agent-driven origin investigation. Returns an origin_engine-shaped
    report with an extra `agent` block. Never raises.
    extra_frame_urls: other frames of the same video (video mode)."""
    progress = progress or _noop
    budget = {**DEFAULT_BUDGET, **(budget or {})}
    extra_frame_urls = [u for u in (extra_frame_urls or []) if u][:oe.MAX_SIGNATURE_FRAMES]
    if not os.environ.get('SERPAPI_API_KEY'):
        return oe._empty('SerpAPI key not configured')
    if not deepseek.configured():
        return oe.investigate_origin(image_url, progress=progress,
                                     extra_frame_urls=extra_frame_urls)

    started = time.monotonic()
    progress('جاري تحميل الصورة وتجهيز بصمتها...')
    image_bytes, mime = None, 'image/jpeg'
    query_sig = None
    try:
        image_bytes, mime = _download(image_url)
        query_sig = oe.frame_signatures(image_bytes, extra_frame_urls)
    except Exception as e:
        logger.warning('agent: cannot download query image: %s', e)

    image_context = None
    if image_bytes:
        progress('الوكيل ينظر إلى الصورة (DeepSeek Vision)...')
        try:
            image_context = deepseek.describe_image(image_bytes, VISION_PROMPT, mime=mime)
        except Exception as e:
            logger.warning('vision failed: %s', e)

    search_url = oe.search_copy_url(image_bytes, image_url)
    inv = Investigation(search_url, query_sig, progress, budget)
    inv.original_url = image_url
    inv.image_bytes = image_bytes
    inv.extra_frames = extra_frame_urls
    inv.llm_calls += 1 if image_context is not None else 0
    if extra_frame_urls and isinstance(image_context, dict):
        image_context['video_mode'] = True
        image_context['other_frames_of_same_video'] = extra_frame_urls
        image_context['note'] = ('The query is a VIDEO: these are frames of one clip. '
                                 'Pages may show a different moment of the same clip; '
                                 'you can reverse_search with any frame URL.')

    # round 0: the deterministic harvest gives the model evidence to reason from
    progress('جاري البحث في المحركات (Lens, Yandex, TinEye)...')
    raw = oe._harvest(search_url, progress, inv.engines_status,
                      extra_frame_urls=extra_frame_urls)
    cands = inv.add_candidates(raw, round_no=0)
    n_frames = 1 + len(extra_frame_urls)
    limit = min(48, budget['round0_inspect'] + 5 * (n_frames - 1))
    chosen = oe.prioritize(cands, limit, budget['per_domain'], by_frame=n_frames > 1)
    progress(f'{len(cands)} مرشحاً فريداً — فحص {len(chosen)} صفحة...')
    inv.inspect(chosen)
    round0_first = inv.first_seen()

    finish = run_agent(inv, image_context)

    first_seen = inv.first_seen()
    pick = _validated_pick(inv, finish)

    kept = [i for i in inv.timeline if i['visual']['verdict'] != 'rejected'
            and not i.get('dropped')]
    dated = sorted([i for i in kept if i['published_at']], key=oe._first_seen_key)
    undated = [i for i in kept if not i['published_at']]
    ordered = dated + undated

    progress('كتابة الملخص...')
    narrative = _narrative(inv, image_context, first_seen, finish)

    stats = {
        'checked': len(inv.timeline),
        'with_dates': len(dated),
        'visually_confirmed': sum(1 for i in inv.timeline if i['visual']['verdict'] == 'confirmed'),
        'probable': sum(1 for i in inv.timeline if i['visual']['verdict'] == 'probable'),
        'visually_rejected': sum(1 for i in inv.timeline if i['visual']['verdict'] == 'rejected'),
        'ambiguous': sum(1 for i in inv.timeline if i['visual']['verdict'] == 'ambiguous'),
        'elapsed_s': round(time.monotonic() - started, 1),
        'visual_verification': oe._has_embedding(query_sig),
        'frames': 1 + len(extra_frame_urls),
    }
    payload = {
        'success': True,
        'engine': 'origin_engine',
        'first_seen': oe._public_item(first_seen) if first_seen else None,
        'earlier_hints': [oe._public_item(i) for i in oe.earlier_hints(inv.timeline, first_seen)],
        'scenes': ([{'frame': f, 'first_seen': oe._public_item(i)}
                    for f, i in sorted(oe.earliest_by_frame(inv.timeline).items())]
                   if extra_frame_urls else []),
        'timeline': [oe._public_item(i) for i in ordered],
        'stats': stats,
        'engines': inv.engines_status,
        'rounds': [{'round': 0, 'candidates': len(cands), 'inspected': len(chosen),
                    'first_seen': round0_first['published_at'] if round0_first else None}]
                  + [{'round': s['n'], 'tool': s['tool'], 'summary': s['summary']}
                     for s in inv.steps],
        'narrative': narrative,
        'agent': {
            'model': deepseek.MODEL,
            'image_context': image_context,
            'steps': inv.steps,
            'finish': finish,
            'pick': oe._public_item(pick) if pick else None,
            'pick_matches_first_seen': bool(pick and first_seen and pick['url'] == first_seen['url']),
            'llm_calls': inv.llm_calls,
            'tokens': inv.tokens,
        },
        'note': None if ordered else (
            'لم يُعثر على أي ظهور مؤكد للصورة في المحركات المفحوصة — قد تكون '
            'أصلية، من مصدر خاص، أو مولّدة بالذكاء الاصطناعي.'),
    }
    progress('اكتمل تحليل المصدر')
    return payload
