"""Payload for the UI and the persistence layer (same item shape as v1's
to_search_payload so the existing results components keep working, plus
the v2 fields: evidence levels, copies, budget, leads)."""
from origin import dates, urls

ELIGIBLE_IMAGE = ('platform', 'page')
ELIGIBLE_DATE = ('platform_id', 'structured')
SIMILAR_MAX = 120


def eligible(s):
    """The one rule: image seen on the page or via the platform, and a
    platform or structured date; listing pages never."""
    return (s['image'].level in ELIGIBLE_IMAGE and s['date'].level in ELIGIBLE_DATE
            and bool(s['date'].when) and not urls.is_listing(s['url']))


def sort_key(s):
    when = s['date'].when or '9999'
    return (when[:10], -dates.LEVEL_RANK.get(s['date'].level, 0), when)


def public_item(s, is_first=False):
    img, dt = s['image'], s['date']
    verdict = {'platform': 'confirmed', 'page': 'confirmed', 'engine_claim': 'ambiguous',
               'none': 'unverified'}[img.level]
    when = dt.when
    date_text = when[:10] if when else ('على الأقل منذ ' + dt.upper_bound[:10] if dt.upper_bound else 'بدون تاريخ')
    return {
        'title': s.get('title') or urls.domain_of(s['url']),
        'link': s['url'], 'url': s['url'],
        'snippet': (s.get('caption') or '')[:300] or None,
        'thumbnail': img.matched_url or (s.get('thumbs') or [None])[0],
        'date_text': date_text, 'date_found': date_text,
        'timestamp': when, 'published_at': when,
        'source': urls.domain_of(s['url']), 'domain': urls.domain_of(s['url']),
        'platform': urls.platform_of(s['url']),
        'type': s.get('match') or 'similar', 'match_type': s.get('match') or 'similar',
        'confidence': dates.confidence_of(dt.level),
        'is_upper_bound': bool(dt.upper_bound and not when),
        'evidence': dt.sources,
        'image_level': img.level, 'date_level': dt.level,
        'visual': {'verdict': verdict, 'match_kind': img.kind, 'similarity': None,
                   'phash_distance': img.phash, 'matched_image_url': img.matched_url,
                   'matched_from': 'engine' if img.level == 'engine_claim' else 'page',
                   'geometry': ({'inliers': img.inliers, 'same_scene': True} if img.kind == 'variant' else None),
                   'note': img.note},
        'providers': s.get('engines') or [],
        'copy_ids': sorted(s.get('copy_ids') or []),
        'origin_round': s.get('round', 0),
        'frames': ([img.frame + 1] if img.frame is not None else []),
        'is_listing': urls.is_listing(s['url']),
    }


def similar_items(candidates, sightings):
    """What the engines returned and the app did not confirm, for the reader
    to judge by eye: the engine's picture, the platform and a date when the
    link or the engine gives one. Never feeds the first-appearance decision."""
    from origin.engines import date_hint
    state = {s['canonical']: s['image'].level for s in sightings}
    order = {'exact': 0, 'page': 1, 'similar': 2, 'text': 3}
    rows, seen = [], set()
    for c in candidates or []:
        canon = c.get('canonical') or urls.canonical(c.get('url'))
        if not canon or canon in seen or state.get(canon, 'none') != 'none':
            continue                      # confirmed pages and engine claims are in the timeline
        thumb = c.get('thumb') or next(iter(c.get('thumbs') or []), None)
        if not thumb:
            continue                      # text results carry no picture to judge
        seen.add(canon)
        when = date_hint(c) or None
        verdict = (c.get('thumb_check') or {}).get('verdict')
        rows.append({
            'link': c['url'], 'url': c['url'],
            'thumbnail': thumb, 'image_url': c.get('image_url'),
            'title': c.get('title') or urls.domain_of(c['url']),
            'published_at': when, 'timestamp': when,
            'date_text': when[:10] if when else 'بدون تاريخ',
            'source': urls.domain_of(c['url']), 'domain': urls.domain_of(c['url']),
            'platform': urls.platform_of(c['url']),
            'match_type': c.get('match') or 'similar',
            'providers': c.get('engines') or [],
            'checked': canon in state,
            'thumb_verdict': verdict,
            'is_listing': urls.is_listing(c['url']),
        })
    rows.sort(key=lambda r: (order.get(r['match_type'], 9),
                             {'match': 0, None: 1, 'unknown': 1, 'differs': 2}.get(r['thumb_verdict'], 1),
                             r['published_at'] or '9999'))
    return rows[:SIMILAR_MAX]


def build(sightings, *, copies, engines, budget, extras, upload_phash=None, note=None, candidates=None):
    cands = sorted([s for s in sightings if eligible(s)], key=sort_key)
    origin = cands[0] if cands else None
    exact_first = None
    version_note = None
    if origin:
        exact = [s for s in cands if s['image'].kind == 'exact' and s['image'].level in ELIGIBLE_IMAGE]
        if origin['image'].kind == 'variant':
            version_note = ('الصورة المرفوعة نسخة معدّلة من الصورة الأصلية (اقتصاص أو تحسين/توسيع أو إعادة تلوين)؛ '
                            'أول الظهور أعلاه هو أصل الصورة نفسها.')
            if exact and exact[0] is not origin:
                exact_first = exact[0]
    scenes = []
    if extras.get('frames'):
        by_frame = {}
        for s in cands:
            f = s['image'].frame
            if f is not None and f not in by_frame:
                by_frame[f] = s
        scenes = [{'frame': f + 1, 'first_seen': public_item(s)} for f, s in sorted(by_frame.items())]
    dated = sorted([s for s in sightings if s['date'].when and s['image'].level != 'none'], key=sort_key)
    undated = [s for s in sightings if not s['date'].when and s['image'].level != 'none']
    leads = [s for s in dated + undated if not eligible(s)]
    timeline = [public_item(s, s is origin) for s in dated + undated]
    similar = similar_items(candidates, sightings)
    stats = {
        'checked': len(sightings),
        'with_dates': len(dated),
        'visually_confirmed': sum(1 for s in sightings if s['image'].level in ELIGIBLE_IMAGE),
        'engine_claims': sum(1 for s in sightings if s['image'].level == 'engine_claim'),
        'visually_rejected': sum(1 for s in sightings if s['image'].level == 'none'),
        'candidates': len({c.get('canonical') for c in candidates or []}),
        'similar': len(similar),
        'elapsed_s': budget.snapshot()['seconds'],
        'visual_verification': True,
        'frames': 1 + len(extras.get('frames') or []),
        'version': 2,
    }
    return {
        'success': True,
        'engine': 'origin_engine',
        'version': 2,
        'first_seen': public_item(origin, True) if origin else None,
        'first_seen_exact': public_item(exact_first) if exact_first else None,
        'version_note': version_note,
        'timeline': timeline,
        'total': len(timeline),
        'leads': [public_item(s) for s in leads][:20],
        'similar': similar,
        'copies': copies,
        'engines': engines,
        'budget': budget.snapshot(),
        'stats': stats,
        'rounds': extras.get('rounds') or [],
        'note': note,
        'narrative': None,
        'identity': extras.get('identity'),
        'agent': None,
        'earlier_hints': [],
        'scenes': scenes,
        'video_summary': None,
        'forensics': None,
        'internal_sightings': [],
        'screenshot': extras.get('screenshot') or False,
        'debug': extras.get('debug'),
        'raw': {},
    }
