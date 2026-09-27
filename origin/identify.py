"""Identification track: who / where / what, then text and X search.

The engines' result titles and the captions of pages that were verified to
show the photo already name the people, place and event far more reliably
than a vision model guessing from pixels. One DeepSeek call turns that text
pool into an identity block and 2–3 queries (Arabic + English, each pairing
the names with one distinctive visible detail). Google text search and, if
configured, one Grok X-search question with the names produce leads that
go through the same page-level verification as everything else.

The identity is labeled an inference ("استنتاج") and never decides the
origin; it only chooses which pages get fetched.
"""
import logging
import os

from origin import engines, urls

logger = logging.getLogger(__name__)

MAX_TITLES = 40
MAX_CAPTIONS = 12
MAX_QUERIES = 3

_SYSTEM = (
    'You are an OSINT analyst identifying a photograph from text collected about it. '
    'You receive: a short visual description, page titles returned by reverse-image engines, '
    'and captions of pages verified to show the photo. Return strict JSON: '
    '{"people": [names of identifiable people, most frequent first], '
    '"place": "<place or null>", "place_ar": "<Arabic place or null>", '
    '"event": "<event in English or null>", "event_ar": "<Arabic event or null>", '
    '"detail": "<one distinctive visible detail: brand, sign, object, caption word>", '
    '"queries_ar": ["<=2 Arabic web queries: names/event + detail + كلمة مثل صورة>"], '
    '"queries_en": ["<=2 English web queries: names/event + detail + photo"], '
    '"x_question": "<one question for an X/Twitter search: earliest post of this exact photo of <names/event>, with the detail>", '
    '"confidence": "high|medium|low"}. Use only what the text supports; never invent names.'
)

_VISION_PROMPT = (
    'Describe this image in 2 sentences for a provenance search: what is shown, visible text, '
    'logos, uniforms, landmarks. Do not guess names or events you are not sure of.'
)


def text_pool(candidates, sightings):
    """Titles from engine rows (Lens visual/exact) + captions/titles of pages
    verified to show the photo."""
    titles, seen = [], set()
    for c in candidates:
        t = (c.get('title') or '').strip()
        if t and t.lower() not in seen and not urls.is_junk(c.get('url', '')):
            seen.add(t.lower())
            titles.append(t[:120])
        if len(titles) >= MAX_TITLES:
            break
    captions = []
    for s in sightings:
        if s['image'].level in ('page', 'platform'):
            for txt in (s.get('caption'), s.get('title')):
                txt = (txt or '').strip()
                if txt and txt.lower() not in seen:
                    seen.add(txt.lower())
                    captions.append(txt[:240])
            if len(captions) >= MAX_CAPTIONS:
                break
    return titles, captions


def describe(image_bytes):
    """One vision call, optional. Returns a short description or ''."""
    try:
        from providers import deepseek
        if not deepseek.configured() or not image_bytes:
            return ''
        d = deepseek.describe_image(image_bytes, _VISION_PROMPT, max_tokens=180)
        if isinstance(d, dict):
            d = d.get('description') or d.get('text') or ''
        return (d or '')[:500] if isinstance(d, str) else ''
    except Exception as e:
        logger.info('vision description skipped: %s', e)
        return ''


def identify(description, titles, captions):
    """The identity block or None (DeepSeek missing / nothing to work with)."""
    try:
        from providers import deepseek
        if not deepseek.configured() or not (titles or captions or description):
            return None
        user = ('VISUAL DESCRIPTION: ' + (description or '(none)') + '\n\nENGINE TITLES:\n- '
                + '\n- '.join(titles or ['(none)']) + '\n\nVERIFIED CAPTIONS:\n- '
                + '\n- '.join(captions or ['(none)']))
        out = deepseek.chat_json(_SYSTEM, user, max_tokens=600, temperature=0.1)
        if not isinstance(out, dict):
            return None
        out['people'] = [p for p in (out.get('people') or []) if isinstance(p, str)][:5]
        out['queries_ar'] = [q for q in (out.get('queries_ar') or []) if isinstance(q, str) and q.strip()][:2]
        out['queries_en'] = [q for q in (out.get('queries_en') or []) if isinstance(q, str) and q.strip()][:2]
        out['label'] = 'استنتاج'
        return out
    except Exception as e:
        logger.info('identification failed: %s', e)
        return None


def x_query(identity):
    """An X-scoped Google query: the original post usually lives on X and
    Lens rarely lists it; `site:x.com` with the event/names finds it."""
    if not identity:
        return None
    core = ' '.join([p for p in (identity.get('people') or [])[:3]] or
                    [identity.get('event') or '']).strip()
    if not core:
        return None
    detail = (identity.get('detail') or '').strip()
    if detail and detail.lower() not in core.lower():
        core = f'{core} {detail}'
    return f'{core} site:x.com'


def queries_of(identity):
    """Up to MAX_QUERIES: best Arabic query, best English query, X-scoped."""
    if not identity:
        return []
    qs = []
    for q in (identity.get('queries_ar') or [])[:1] + (identity.get('queries_en') or [])[:1]:
        if q and q not in qs:
            qs.append(q)
    xq = x_query(identity)
    if xq and xq not in qs:
        qs.append(xq)
    for q in (identity.get('queries_ar') or [])[1:2]:
        if q and q not in qs:
            qs.append(q)
    return qs[:MAX_QUERIES]


def text_search(identity, budget, progress=None):
    """Google text search for the identity's queries. Returns {label: EngineAnswer}."""
    qs = queries_of(identity)
    if not qs:
        return {}
    tasks = []
    for i, q in enumerate(qs):
        ar = any('؀' <= ch <= 'ۿ' for ch in q)
        hl, gl = ('ar', 'sa') if ar else ('en', 'us')
        tasks.append((f'text{i + 1}', (lambda q=q, hl=hl, gl=gl: engines.google_text(q, hl=hl, gl=gl)), engines.TEXT_CREDITS))
    if progress:
        progress('بحث نصي بالأسماء المستخلصة...')
    return engines.run_parallel(tasks, budget, timeout_s=40, progress=progress)


def grok_search(identity, image_bytes, progress=None):
    """One Grok X-search question with the names. Returns an EngineAnswer of leads."""
    name = 'grok'
    if os.environ.get('GROK_SEARCH', 'true').lower() == 'false':
        return engines.EngineAnswer(name, 'skipped', note='disabled')
    try:
        from providers import xai
        if not xai.configured():
            return engines.EngineAnswer(name, 'skipped', note='not configured')
        people = ', '.join((identity or {}).get('people') or [])
        event = (identity or {}).get('event') or ''
        detail = (identity or {}).get('detail') or ''
        if not (people or event):
            return engines.EngineAnswer(name, 'skipped', note='nothing identified')
        q = ((identity or {}).get('x_question') or
             f'Find the earliest X (Twitter) post of this exact photo: {people} {event}.')
        q += (f' Visible detail: {detail}.' if detail else '')
        q += (' Search X first: look for the ORIGINAL poster — the official account, agency, '
              'outlet or eyewitness that published it first — then reposts. Return only URLs you '
              'actually retrieved, as full x.com/<user>/status/<id> links or article links, each with its date.')
        if progress:
            progress('سؤال Grok عن أول منشور على X...')
        res = xai.search_origin(image_bytes or '', q)
        if res.get('error'):
            return engines.EngineAnswer(name, 'error', note=str(res['error'])[:120])
        cands = []
        for u in res.get('urls') or []:
            c = engines._cand(u, engine=name, copy_id=None, match='text')
            if c:
                cands.append(c)
        return engines.EngineAnswer(name, 'results' if cands else 'empty', cands, 0, note=q[:80])
    except Exception as e:
        return engines.EngineAnswer(name, 'error', note=str(e)[:120])
