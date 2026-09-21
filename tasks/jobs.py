"""Job functions executed by the RQ worker (or inline in dev sync mode).

Every job returns {'status': <http status>, 'payload': <json body>} — the
same body the old synchronous endpoints produced, so the frontend result
handling is unchanged after the 202/SSE hop.
"""
import functools
import logging
import os

import requests
from rq import get_current_job

logger = logging.getLogger(__name__)

_app = None


def _get_app():
    """App instance for DB access inside the worker process."""
    global _app
    if _app is None:
        import app as app_module
        _app = app_module.app
    return _app


def _with_app_context(fn):
    """Jobs run in the worker process — give them an app context so DB
    persistence and provider metering work exactly as in a request."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _get_app().app_context():
            return fn(*args, **kwargs)
    return wrapper


def _progress(message):
    from tasks.queue import get_current_local_job
    job = get_current_job() or get_current_local_job()
    if job is not None:
        meta = job.get_meta(refresh=True) or {}
        meta.setdefault('progress', []).append(message)
        job.meta = meta
        job.save_meta()


@_with_app_context
def run_video_analysis(temp_path, filename, user_id=None,
                       media_hash=None):
    """AIOrNot video analysis (was the blocking /api/analyze-video body)."""
    from providers.aiornot import post_video_file
    try:
        _progress('جاري إرسال الفيديو للتحليل...')
        try:
            response = post_video_file(temp_path, filename)
        except requests.exceptions.Timeout:
            return {'status': 504, 'payload': {
                'error': 'Request timed out (Video might be too long)',
                'success': False}}

        if response.status_code == 200:
            result = response.json()
            _progress('اكتمل التحليل')
            payload = {'success': True, 'data': result}
            _persist_analysis(user_id, 'video', 'aiornot', media_hash,
                              result, payload)
            return {'status': 200, 'payload': payload}
        if response.status_code == 422:
            return {'status': 422, 'payload': {
                'error': 'Validation Error (Check file format/parameters)',
                'details': response.json(), 'success': False}}
        return {'status': response.status_code, 'payload': {
            'error': f'AIorNot API Error: {response.status_code}',
            'details': response.text, 'success': False}}
    except Exception as e:
        logger.exception('video analysis job failed')
        return {'status': 500, 'payload': {'error': str(e), 'success': False}}
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _persist_analysis(user_id, analysis_type, service, media_hash,
                      raw_result, payload):
    """Persist a video Analysis row via the shared service helper."""
    from services.detection_service import persist_analysis
    report = (raw_result or {}).get('report', {}) if isinstance(raw_result, dict) else {}
    ai_video = report.get('ai_video', {}) if isinstance(report, dict) else {}
    row = dict(payload)
    if ai_video:
        row['is_ai'] = (ai_video.get('verdict') == 'ai')
    persist_analysis(user_id, 'video', service, row, media_hash=media_hash)


@_with_app_context
def run_xai_investigation(image_url, user_id=None):
    """Grok contextual investigation (was the 180s-blocking /api/xai-context)."""
    from providers.xai import investigate_image, extract_summary
    try:
        _progress('جاري البحث في الويب عن سياق الصورة (قد يستغرق دقائق)...')
        resp = investigate_image(image_url)
        if resp.status_code != 200:
            return {'status': 502, 'payload': {
                'error': f'xAI API Error: {resp.status_code}',
                'details': resp.text, 'success': False}}

        xai_data = resp.json()
        message_content = extract_summary(xai_data)
        _progress('اكتمل التحقيق')

        payload = {'success': True, 'summary': message_content, 'raw': xai_data}
        from services.search_service import persist_search
        persist_search(user_id, 'xai_context', image_url=image_url,
                       raw_response={'summary': message_content})
        return {'status': 200, 'payload': payload}
    except Exception as e:
        logger.exception('xai investigation job failed')
        return {'status': 500, 'payload': {'error': str(e), 'success': False}}


@_with_app_context
def run_direct_search(query=None, image_url=None, user_id=None,
                      image_hash=None, image_phash=None, extra_image_urls=None):
    """Timeline search as a background job (was the blocking /api/direct-search).

    Image mode runs the Origin Engine (multi-engine harvest, dated + visually
    verified sightings, bounded expansion). If the engine cannot run at all
    it degrades to the legacy path: Zenserp with one retry, then the Google
    Lens harvest — so the search ALWAYS returns something. Text mode is
    Zenserp only.
    """
    from urllib.parse import urlparse
    from providers.zenserp import reverse_image_search, text_search
    from services.search_service import (build_direct_search_timeline,
                                         scrape_reverse_search,
                                         persist_search, parse_iso_datetime)

    image_mode = bool(image_url)
    if image_mode:
        origin = _run_origin_engine(image_url, extra_image_urls)
        if origin is not None:
            results = [{
                'url': i.get('link'),
                'title': i.get('title'),
                'snippet': None,
                'thumbnail': i.get('thumbnail'),
                'domain': i.get('source'),
                'published_at': parse_iso_datetime(i.get('published_at')),
                'confidence': i.get('confidence'),
            } for i in origin['timeline']]
            raw = {k: origin.get(k) for k in
                   ('timeline', 'engine', 'first_seen', 'narrative',
                    'engines', 'stats', 'rounds', 'note', 'agent',
                    'earlier_hints', 'scenes', 'video_summary',
                    'forensics', 'internal_sightings')}
            origin['search_id'] = persist_search(
                user_id, 'direct', query=None, image_url=image_url,
                image_hash=image_hash, image_phash=image_phash,
                results=results, raw_response=raw)
            _progress('اكتمل البحث')
            return {'status': 200, 'payload': origin}
        _progress('تعذّر تشغيل محرك المصدر — التبديل إلى البحث التقليدي...')

    engine = 'zenserp'
    zenserp_data = None
    last_error = None

    _progress('جاري البحث في محركات البحث...')
    for attempt in (1, 2):
        try:
            if image_mode:
                resp = reverse_image_search(image_url, gl='us', hl='en')
            else:
                resp = text_search(query, num=40, gl='sa', hl='ar')
            if resp.status_code == 200:
                zenserp_data = resp.json()
                break
            last_error = f'Zenserp API Error: {resp.status_code}'
            logger.warning('%s (attempt %d): %s', last_error, attempt,
                           resp.text[:200])
        except requests.RequestException as e:
            last_error = f'Zenserp request failed: {e}'
            logger.warning('%s (attempt %d)', last_error, attempt)
        if attempt == 1:
            _progress('محرك البحث بطيء الاستجابة — محاولة ثانية...')

    if zenserp_data is not None:
        _progress('جاري تحليل النتائج وترجمتها...')
        timeline = build_direct_search_timeline(zenserp_data, image_mode)
    elif image_mode:
        # Zenserp is down — the reliable Lens harvest becomes the timeline
        _progress('التبديل إلى Google Lens...')
        engine = 'google_lens_fallback'
        lens = scrape_reverse_search(image_url)
        timeline = [{
            'title': m.get('title') or None,
            'link': m.get('link'),
            'snippet': None,
            'thumbnail': m.get('thumbnail'),
            'date_text': None,
            'timestamp': None,
            'source': urlparse(m['link']).netloc if m.get('link') else 'Web',
            'type': m.get('match_type', 'similar'),
        } for m in lens.get('matches', [])]
        if not timeline and (lens.get('error') or not lens.get('success')):
            # both engines genuinely down — say so instead of an empty 200
            return {'status': 502, 'payload': {
                'error': last_error or 'Search engines unavailable',
                'success': False}}
    else:
        return {'status': 502, 'payload': {
            'error': last_error or 'Zenserp API Error', 'success': False}}

    # Tier-1 visual post-filter (feature flag)
    visual_summary = None
    from services.embedding_service import visual_verify_enabled
    if image_mode and timeline and visual_verify_enabled():
        from services.visual_verify import apply_visual_post_filter
        _progress('جاري التحقق البصري من النتائج...')
        timeline, visual_summary = apply_visual_post_filter(
            timeline, image_url, url_field='link')

    results = [{
        'url': i.get('link'),
        'title': i.get('title'),
        'snippet': i.get('snippet'),
        'thumbnail': i.get('thumbnail'),
        'domain': i.get('source'),
        'published_at': parse_iso_datetime(i.get('timestamp')),
        'confidence': None,
    } for i in timeline]
    search_id = persist_search(
        user_id, 'direct', query=query, image_url=image_url,
        image_hash=image_hash, image_phash=image_phash, results=results,
        raw_response={'timeline': timeline, 'engine': engine})

    _progress('اكتمل البحث')
    payload = {
        'success': True,
        'timeline': timeline,
        'total': len(timeline),
        'search_id': search_id,
        'engine': engine,
        'raw': {}
    }
    if visual_summary is not None:
        payload['visual_verification'] = visual_summary
    return {'status': 200, 'payload': payload}


def _run_origin_engine(image_url, extra_image_urls=None):
    """investigate_origin() -> page payload, or None when the engine could
    not run (missing key, unexpected crash). Never raises.
    extra_image_urls: more frames of the same video (video mode)."""
    from services.origin_engine import investigate_origin, to_search_payload
    from services.origin_agent import investigate as agent_investigate
    from providers import deepseek
    use_agent = (os.environ.get('ORIGIN_AGENT', 'true').lower() == 'true'
                 and deepseek.configured())
    try:
        if use_agent:
            report = agent_investigate(image_url, progress=_progress,
                                       extra_frame_urls=extra_image_urls)
        else:
            report = investigate_origin(image_url, progress=_progress,
                                        extra_frame_urls=extra_image_urls)
    except Exception:
        logger.exception('origin engine crashed; falling back')
        return None
    if not report.get('success'):
        logger.warning('origin engine unavailable: %s', report.get('note'))
        return None
    engines = report.get('engines') or {}
    broken = [n for n, e in engines.items()
              if not e.get('ok') and e.get('note') != 'not configured']
    if broken and not report.get('timeline'):
        logger.warning('origin engine found nothing and %s failed; '
                       'falling back to legacy search', broken)
        return None
    return to_search_payload(report)


@_with_app_context
def run_index_image(image_url, media_hash):
    """Index an uploaded image into the internal provenance index.

    Runs in the worker so the web process never loads the embedding model
    (torch would not fit the web dyno's memory).
    """
    from services.vector_index import index_bytes
    try:
        r = requests.get(image_url, timeout=(5, 15))
        r.raise_for_status()
        index_bytes(r.content, media_hash, source='query')
    except Exception as e:
        logger.warning('index job failed for %s: %s', media_hash, e)


@_with_app_context
def run_provenance(image_url, user_id=None, image_hash=None,
                   image_phash=None):
    """Provenance analysis (page-fetch heavy; was blocking /api/provenance)."""
    from services.provenance_service import analyze_provenance
    from services.search_service import persist_search, parse_iso_datetime
    try:
        _progress('جاري جمع المطابقات البصرية...')
        payload = analyze_provenance(image_url)

        # Tier-1 visual post-filter (feature flag): every timeline entry
        # must actually show the query image on its page
        from services.embedding_service import visual_verify_enabled
        if visual_verify_enabled() and payload.get('timeline'):
            from services.visual_verify import apply_visual_post_filter
            _progress('جاري التحقق البصري من النتائج...')
            filtered, summary = apply_visual_post_filter(
                payload['timeline'], image_url, url_field='url')
            payload['timeline'] = filtered
            payload['visual_verification'] = summary
            dated = [i for i in filtered if i.get('published_at')]
            payload['first_seen'] = dated[0] if dated else None
            payload['stats']['visually_rejected'] = summary.get('rejected', 0)

        _progress('اكتمل تحليل المصدر')

        results = [{
            'url': i.get('url'),
            'title': i.get('title'),
            'domain': i.get('domain'),
            'published_at': parse_iso_datetime(i.get('published_at')),
            'confidence': i.get('confidence'),
        } for i in payload.get('timeline', [])]
        persist_search(user_id, 'provenance', image_url=image_url,
                       image_hash=image_hash, image_phash=image_phash,
                       results=results, raw_response=payload)
        return {'status': 200, 'payload': payload}
    except Exception as e:
        logger.exception('provenance job failed')
        return {'status': 500, 'payload': {
            'first_seen': None, 'timeline': [], 'related_images': [],
            'stats': {'checked': 0, 'with_dates': 0},
            'note': f'Server error: {str(e)}'}}
