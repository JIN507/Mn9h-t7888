"""Search endpoints: upload+engine links, direct (Zenserp) search,
reverse image search, xAI context investigation, export."""
import base64
import logging
import os
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from providers.imgbb import upload_to_imgbb
from services.media_service import UPLOAD_FOLDER, allowed_file
from services.search_service import (search_images, scrape_reverse_search,
                                     build_direct_search_timeline)

logger = logging.getLogger(__name__)
bp = Blueprint('search', __name__)


@bp.route('/api/upload', methods=['POST'])
def upload_image():
    """API endpoint to upload an image"""
    if 'file' not in request.files and 'image' not in request.form:
        return jsonify({'error': 'No image provided'}), 400

    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            with open(filepath, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            os.remove(filepath)
    else:
        image_data = request.form['image']

    image_url = upload_to_imgbb(image_data)
    if not image_url:
        return jsonify({'error': 'Failed to upload image'}), 500

    search_results = search_images(image_url)

    return jsonify({
        'imageUrl': image_url,
        'searchResults': search_results,
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
def xai_context_api():
    try:
        data = request.get_json(silent=True) or {}
        image_url = data.get('image_url')

        if not image_url:
            return jsonify({'error': 'No image_url provided', 'success': False}), 400

        if not os.environ.get('XAI_API_KEY'):
            return jsonify({'error': 'XAI_API_KEY is not configured', 'success': False}), 500

        from providers.xai import investigate_image, extract_summary

        resp = investigate_image(image_url)

        if resp.status_code != 200:
            return jsonify({'error': f'xAI API Error: {resp.status_code}', 'details': resp.text, 'success': False}), 502

        xai_data = resp.json()
        message_content = extract_summary(xai_data)

        return jsonify({
            'success': True,
            'summary': message_content,
            'raw': xai_data
        })

    except Exception as e:
        current_app.logger.exception(f"xAI context error: {e}")
        return jsonify({'error': str(e), 'success': False}), 500

@bp.route('/api/direct-search', methods=['POST'])
def direct_search_api():
    """API endpoint for Direct Search using Zenserp"""
    try:
        data = request.get_json(silent=True) or {}
        query = data.get('query')
        image_url = data.get('image_url')
        
        if not query and not image_url:
            # Check form data if json is empty
            query = request.form.get('query')
            image_url = request.form.get('image_url')
        
        if not query and not image_url:
             # Handle file upload for reverse image search
            if 'file' in request.files:
                file = request.files['file']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    
                    # Upload to ImgBB
                    with open(filepath, 'rb') as f:
                        image_data = base64.b64encode(f.read()).decode('utf-8')
                    image_url = upload_to_imgbb(image_data)
                    os.remove(filepath) # clean up
            
        if not query and not image_url:
            return jsonify({'error': 'No query or image provided', 'success': False}), 400

        logger.info(f"[*] Starting Zenserp search. Query: {query}, Image: {image_url}")
        
        # Zenserp Search Logic
        from providers.zenserp import reverse_image_search, text_search

        if image_url:
            # Keep US/English for broader search + better source data; we translate after
            resp = reverse_image_search(image_url, gl='us', hl='en')
        else:
            resp = text_search(query, num=40, gl='sa', hl='ar')
        
        if resp.status_code != 200:
            logger.info(f"[!] Zenserp API Error: {resp.text}")
            return jsonify({'error': f'Zenserp API Error: {resp.status_code}', 'details': resp.text, 'success': False}), 502

        zenserp_data = resp.json()
        logger.info(f"[*] Zenserp response keys: {zenserp_data.keys()}")
        
        timeline = build_direct_search_timeline(zenserp_data, bool(image_url))

        return jsonify({
            'success': True,
            'timeline': timeline,
            'total': len(timeline),
            'raw': {} # Don't send raw data to save bandwidth
        })

    except Exception as e:
        logger.info(f"[!] Error in Direct Search: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e), 'success': False}), 500

@bp.route('/api/image-source-search', methods=['POST'])
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
        
        try:
            # Upload image to imgbb first to get a URL
            with open(filepath, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Get image URL from ImgBB
            image_url = upload_to_imgbb(image_data)
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
                
            return jsonify({
                'success': True,
                'imageUrl': image_url,
                'links': result.get('links', []),
                'source': result.get('source', 'TheHive Reverse Image Search')
            })
            
        except Exception as e:
            # Clean up the temporary file in case of error
            if os.path.exists(filepath):
                os.remove(filepath)
                
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
            
    return jsonify({'error': 'نوع الملف غير مدعوم'}), 400
