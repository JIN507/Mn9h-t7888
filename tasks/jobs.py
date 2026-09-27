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
    """Origin search as a background job.

    Image mode: Origin v2 (origin/investigate.py) — copies, engines, page-level
    verification, one eligibility rule. Text mode: SerpAPI Google results.
    Every search persists a Search + SearchResult rows.
    """
    from services.search_service import persist_search, parse_iso_datetime

    if image_url:
        from origin.investigate import investigate
        payload = investigate(image_url, progress=_progress,
                              extra_frame_urls=extra_image_urls)
        if not payload.get('success'):
            return {'status': 502, 'payload': {
                'error': payload.get('note') or 'origin engine unavailable', 'success': False}}
        results = [{
            'url': i.get('link'),
            'title': i.get('title'),
            'snippet': None,
            'thumbnail': i.get('thumbnail'),
            'domain': i.get('source'),
            'published_at': parse_iso_datetime(i.get('published_at')),
            'confidence': i.get('confidence'),
        } for i in payload['timeline']]
        raw = {k: payload.get(k) for k in
               ('timeline', 'engine', 'version', 'first_seen', 'first_seen_exact',
                'version_note', 'leads', 'copies', 'engines', 'budget', 'stats',
                'rounds', 'note', 'identity', 'scenes', 'screenshot')}
        payload['search_id'] = persist_search(
            user_id, 'direct', query=None, image_url=image_url,
            image_hash=image_hash, image_phash=image_phash,
            results=results, raw_response=raw)
        _progress('اكتمل البحث')
        return {'status': 200, 'payload': payload}

    # text mode
    from providers.serpapi import web_search
    from urllib.parse import urlparse
    _progress('جاري البحث...')
    try:
        rows = web_search(query or '', hl='ar', gl='sa', num=20)
    except Exception as e:
        logger.warning('text search failed: %s', e)
        return {'status': 502, 'payload': {'error': f'search failed: {e}', 'success': False}}
    timeline = [{
        'title': r.get('title') or None, 'link': r['link'], 'snippet': r.get('snippet'),
        'thumbnail': None, 'date_text': r.get('date'), 'timestamp': None,
        'source': urlparse(r['link']).netloc, 'type': 'organic',
    } for r in rows]
    results = [{'url': i['link'], 'title': i['title'], 'snippet': i['snippet'], 'thumbnail': None,
                'domain': i['source'], 'published_at': None, 'confidence': None} for i in timeline]
    search_id = persist_search(user_id, 'direct', query=query, image_url=None,
                               image_hash=image_hash, image_phash=image_phash,
                               results=results, raw_response={'timeline': timeline, 'engine': 'google_text'})
    _progress('اكتمل البحث')
    return {'status': 200, 'payload': {'success': True, 'timeline': timeline, 'total': len(timeline),
                                       'search_id': search_id, 'engine': 'google_text', 'raw': {}}}


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
