"""Search endpoints: upload+engine links, direct (Zenserp) search,
reverse image search, xAI context investigation, export."""
import base64
import logging
import os
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from services.storage_service import host_image
from services.media_service import UPLOAD_FOLDER, allowed_file, compute_hashes
from services.search_service import (search_images, scrape_reverse_search,
                                     persist_search, find_cached_search,
                                     parse_iso_datetime)

from extensions import limiter, SPEND_LIMIT

logger = logging.getLogger(__name__)
bp = Blueprint('search', __name__)


def _is_decodable_image(path):
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


@bp.route('/api/upload', methods=['POST'])
@limiter.limit(SPEND_LIMIT)
def upload_image():
    """API endpoint to upload an image"""
    if 'file' not in request.files and 'image' not in request.form:
        return jsonify({'error': 'No image provided'}), 400

    image_hash, image_phash = None, None
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # The bytes must be a decodable image: a mislabeled file (HTML,
            # empty blob) would otherwise be hosted and burn a paid search.
            if not _is_decodable_image(filepath):
                os.remove(filepath)
                return jsonify({'error': 'الملف ليس صورة صالحة (JPG/PNG/WEBP)',
                                'success': False}), 400

            with open(filepath, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            # SHA-256 + pHash on every upload
            image_hash, image_phash = compute_hashes(filepath)

            os.remove(filepath)
    else:
        image_data = request.form['image']

    image_url = host_image(image_data)
    if not image_url:
        return jsonify({'error': 'Failed to upload image'}), 500

    search_results = search_images(image_url)

    # Feed the internal provenance index in the background — the WORKER owns
    # the embedding model; the web process never loads torch
    from services.embedding_service import visual_verify_enabled
    if image_hash and visual_verify_enabled():
        from tasks.jobs import run_index_image
        from tasks.queue import enqueue
        enqueue(run_index_image, image_url, image_hash)

    return jsonify({
        'imageUrl': image_url,
        'searchResults': search_results,
        'image_hash': image_hash,
        'image_phash': image_phash,
        'timestamp': datetime.now().isoformat()
    })

@bp.route('/api/export', methods=['POST'])
def export_results():
    """Export search results as JSON"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    response = jsonify(data)
    response.headers.set('Content-Disposition', 'attachment', filename='bahith-al-suwar-results.json')
    return response

@bp.route('/image-source-search', methods=['POST'])
@limiter.limit(SPEND_LIMIT)
def image_source_search():

    try:
        data = request.get_json(silent=True) or {}
        image_url = data.get('image_url') or request.form.get('image_url')
        if not image_url:
            return jsonify({'links': [], 'search_urls': {}, 'error': 'image_url is required', 'success': False}), 200
        result = scrape_reverse_search(image_url)
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.exception(e)  # use current_app.logger instead of current_app
        return jsonify({'links': [], 'search_urls': {}, 'error': f'Unhandled: {e}', 'success': False}), 200

# Endpoint for x.ai Contextual Image Investigation
@bp.route('/api/xai-context', methods=['POST'])
@limiter.limit(SPEND_LIMIT)
def xai_context_api():
    """Queue the Grok contextual investigation - returns 202 + job id."""
    data = request.get_json(silent=True) or {}
    image_url = data.get('image_url')

    if not image_url:
        return jsonify({'error': 'No image_url provided', 'success': False}), 400
    if not os.environ.get('XAI_API_KEY'):
        return jsonify({'error': 'XAI_API_KEY is not configured', 'success': False}), 500

    from auth import get_current_user
    from tasks.jobs import run_xai_investigation
    from tasks.queue import enqueue
    user = get_current_user()
    job = enqueue(run_xai_investigation, image_url,
                  user_id=user.id if user else None)
    return jsonify({
        'success': True,
        'job_id': job.id,
        'status_url': f'/api/jobs/{job.id}',
        'events_url': f'/api/jobs/{job.id}/events',
    }), 202


# Endpoint for Zenserp Direct Search
@bp.route('/api/direct-search', methods=['POST'])
@limiter.limit(SPEND_LIMIT)
def direct_search_api():
    """Queue a timeline search — 202 + SSE. Cache hits return 200 instantly."""
    try:
        data = request.get_json(silent=True) or {}
        query = data.get('query') or request.form.get('query')
        image_url = data.get('image_url') or request.form.get('image_url')
        # Video mode: several frames of one clip; the first is the primary
        image_urls = data.get('image_urls') if isinstance(data.get('image_urls'), list) else []
        image_urls = [u for u in image_urls if isinstance(u, str) and u.startswith('http')]
        if image_urls and not image_url:
            image_url = image_urls[0]
        extra_image_urls = [u for u in image_urls if u != image_url][:11]
        image_hash = data.get('image_hash') or request.form.get('image_hash')
        image_phash = data.get('image_phash') or request.form.get('image_phash')
        rerun = bool(data.get('rerun') or request.form.get('rerun'))
        mode = 'quick' if (data.get('mode') or request.form.get('mode')) == 'quick' else 'deep'

        # Legacy path: direct file upload to this endpoint
        if not query and not image_url and 'file' in request.files:
            file = request.files['file']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                with open(filepath, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
                image_hash, image_phash = compute_hashes(filepath)
                image_url = host_image(image_data)
                os.remove(filepath)

        if not query and not image_url:
            return jsonify({'error': 'No query or image provided', 'success': False}), 400

        # Repeat-search cache: same image hash -> instant answer, zero spend
        if image_url and image_hash and not rerun:
            cached = find_cached_search('direct', image_hash)
            # a quick result never stands in for a requested deep search
            if cached and cached.raw_response and mode == 'deep' and \
                    (cached.raw_response.get('mode') or 'deep') != 'deep':
                cached = None
            if cached and cached.raw_response:
                logger.info('Direct-search cache hit: hash=%s', image_hash)
                payload = {k: v for k, v in cached.raw_response.items()
                           if k in ('timeline', 'engine', 'first_seen',
                                    'narrative', 'engines', 'stats',
                                    'rounds', 'note', 'agent',
                                    'earlier_hints', 'scenes', 'video_summary',
                                    'forensics', 'internal_sightings',
                                    # origin v2
                                    'version', 'first_seen_exact', 'version_note',
                                    'leads', 'copies', 'budget', 'identity', 'screenshot',
                                    'prior_sightings', 'mode', 'similar')}
                payload.update({
                    'success': True,
                    'timeline': payload.get('timeline') or [],
                    'total': cached.result_count,
                    'cached': True,
                    'search_id': cached.id,
                    'raw': {},
                })
                return jsonify(payload)

        from auth import get_current_user
        from tasks.jobs import run_direct_search
        from tasks.queue import enqueue
        user = get_current_user()
        job = enqueue(run_direct_search, query=query, image_url=image_url,
                      user_id=user.id if user else None,
                      image_hash=image_hash, image_phash=image_phash,
                      extra_image_urls=extra_image_urls or None, mode=mode)
        return jsonify({
            'success': True,
            'job_id': job.id,
            'status_url': f'/api/jobs/{job.id}',
            'events_url': f'/api/jobs/{job.id}/events',
        }), 202

    except Exception as e:
        logger.exception('direct-search error')
        return jsonify({'error': str(e), 'success': False}), 500

@bp.route('/api/image-source-search', methods=['POST'])
@limiter.limit(SPEND_LIMIT)
def api_image_source_search():
    """API endpoint to find image sources using TheHive.ai"""
    if 'file' not in request.files:
        return jsonify({'error': 'لم يتم تقديم صورة'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Repeat-search cache keyed on SHA-256; rerun=true forces fresh spend
        media_hash, media_phash = compute_hashes(filepath)
        rerun = str(request.form.get('rerun', '')).lower() in ('1', 'true', 'yes')
        if not rerun:
            cached = find_cached_search('reverse', media_hash)
            if cached and cached.raw_response:
                logger.info('Reverse-search cache hit: hash=%s', media_hash)
                if os.path.exists(filepath):
                    os.remove(filepath)
                payload = dict(cached.raw_response)
                payload['cached'] = True
                payload['search_id'] = cached.id
                return jsonify(payload)

        try:
            # Upload image to imgbb first to get a URL
            with open(filepath, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Get image URL from ImgBB
            image_url = host_image(image_data)
            if not image_url:
                raise Exception('فشل في رفع الصورة')
                
            # Use the URL to search for image sources
            result = scrape_reverse_search(image_url)
            
            # Clean up the temporary file
            if os.path.exists(filepath):
                os.remove(filepath)
                
            if 'error' in result:
                return jsonify({
                    'success': False,
                    'error': result['error'],
                    'imageUrl': image_url
                }), 500
                
            payload = {
                'success': True,
                'imageUrl': image_url,
                'links': result.get('links', []),
                'matches': result.get('matches', []),
                'source': result.get('source', 'TheHive Reverse Image Search')
            }

            # Persist every search -> Search + SearchResult rows
            from auth import get_current_user
            user = get_current_user()
            results = [{
                'url': m.get('link'),
                'title': m.get('title'),
                'thumbnail': m.get('thumbnail'),
            } for m in result.get('matches', [])]
            search_id = persist_search(
                user.id if user else None, 'reverse',
                image_url=image_url, image_hash=media_hash,
                image_phash=media_phash, results=results,
                raw_response=payload)
            payload['search_id'] = search_id
            return jsonify(payload)
            
        except Exception as e:
            # Clean up the temporary file in case of error
            if os.path.exists(filepath):
                os.remove(filepath)
                
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
            
    return jsonify({'error': 'نوع الملف غير مدعوم'}), 400
