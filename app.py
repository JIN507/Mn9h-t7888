import os
import sys
import re
import json
import time
import uuid
import base64
import hashlib
import io
import requests
import traceback
import concurrent.futures

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
from urllib.parse import urlencode, quote_plus
import cv2
import numpy as np
from PIL import Image
from flask import Flask, render_template, request, url_for, redirect, flash, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Provenance feature imports (with fallbacks)
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

try:
    import dateparser
    DATEPARSER_AVAILABLE = True
except ImportError:
    DATEPARSER_AVAILABLE = False

# Initialize Flask
# Serve static files from 'frontend/dist/assets' available at '/assets'
# Serve templates (index.html) from 'frontend/dist'
app = Flask(__name__, static_folder='frontend/dist/assets', static_url_path='/assets', template_folder='frontend/dist')

# Load environment variables
load_dotenv()

# CORS: comma-separated allowlist via CORS_ORIGINS; defaults cover local dev only
_cors_origins = [o.strip() for o in os.environ.get(
    'CORS_ORIGINS',
    'http://localhost:5173,http://127.0.0.1:5173,http://localhost:5000,http://127.0.0.1:5000'
).split(',') if o.strip()]
CORS(app, origins=_cors_origins)

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================
from config import Config
from models import db, bcrypt, User, Country, Source, Keyword, Search, SearchResult, Analysis, AnalysisFrame, UserFile
from auth import login_required, admin_required, optional_auth, generate_token, get_current_user

# Providers (external APIs) and services (business logic)
from providers.imgbb import upload_to_imgbb
from services.provenance_service import analyze_provenance
from services.media_service import (UPLOAD_FOLDER, AUDIO_UPLOAD_FOLDER,
                                    allowed_file, allowed_audio_file,
                                    extract_frames_from_video, download_image)
from services.search_service import (search_images, scrape_reverse_search,
                                     build_direct_search_timeline)
from services.detection_service import (scrape_aiornot, scrape_thehive,
                                        scrape_faceonlive)

# Apply configuration
app.config.from_object(Config)

# Initialize database and bcrypt
db.init_app(app)
bcrypt.init_app(app)

# Create tables on first request (development convenience)
with app.app_context():
    db.create_all()
    print('[*] Database tables initialized')


# Serve React App
@app.route('/')
def index():
    return render_template('index.html')

# Catch-all route for React client-side routing
@app.route('/<path:path>')
def catch_all(path):
    # Check if path exists in static folder (e.g. for other assets)
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return render_template('index.html')

# Config — app.config keeps the legacy relative path; module-level
# UPLOAD_FOLDER (absolute) comes from services.media_service
# API Keys from Environment
IMGBB_API_KEY = os.environ.get('IMGBB_API_KEY')
AIORNOT_API_KEY = os.environ.get('AIORNOT_API_KEY')
SERPAPI_API_KEY = os.environ.get('SERPAPI_API_KEY')
ZENSERP_API_KEY = os.environ.get('ZENSERP_API_KEY')
XAI_API_KEY = os.environ.get('XAI_API_KEY')

# Setting environment variable as in the example
if AIORNOT_API_KEY:
    os.environ['AIORNOT_API_KEY'] = AIORNOT_API_KEY
# The exact endpoints from the API docs
VOICE_ENDPOINT = "https://api.aiornot.com/v1/reports/voice"
IMAGE_ENDPOINT = "https://api.aiornot.com/v1/reports/image"
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024 * 1024  # 256MB max upload
os.makedirs('uploads', exist_ok=True)

# Create audio upload folder if it doesn't exist - inside static for web access
# Note: Since we changed static_folder, we need to handle user uploads carefully.
# We'll serve uploads via a specific route or keep them in root 'static' and serve manually.
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# First implementation of upload_to_imgbb has been removed
# Using the improved version defined at line ~1404

# Video processing functions
# Absolute media folders live in services/media_service







@app.route('/api/extract-frames', methods=['POST'])
def extract_frames_api():
    """API endpoint to extract frames from uploaded video"""
    # Check if a file was uploaded
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    # Check if the file is empty
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Get frame interval parameter with default value of 2 seconds
    frame_interval = request.form.get('frameInterval', '2')
    
    # Create a unique filename
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    unique_filename = f"{timestamp}_{filename}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    
    # Save the uploaded file
    file.save(file_path)
    
    try:
        # Extract frames from the video
        frames = extract_frames_from_video(file_path, frame_interval)
        
        # Delete the uploaded file after processing
        os.remove(file_path)
        
        return jsonify({
            'success': True,
            'frames': frames,
            'frameCount': len(frames)
        })
    except Exception as e:
        # Delete the uploaded file if an error occurs
        if os.path.exists(file_path):
            os.remove(file_path)
        
        return jsonify({
            'error': str(e)
        }), 500





@app.route('/ai-detect-thehive', methods=['POST'])
def ai_detect_thehive():
    try:
        image_file = request.files.get('image')
        if not image_file or not allowed_file(image_file.filename):
            return jsonify({'error': 'يرجى تحميل ملف صورة صالح'}), 400
            
        # Save the uploaded image temporarily
        temp_path = os.path.join(UPLOAD_FOLDER, secure_filename(f"{uuid.uuid4()}-{image_file.filename}"))
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        image_file.save(temp_path)
        
        # Upload to imgbb to get URL
        with open(temp_path, 'rb') as img_file:
            image_data = base64.b64encode(img_file.read()).decode('utf-8')
        
        upload_result = upload_to_imgbb(image_data)
        if 'error' in upload_result:
            return jsonify({'error': 'فشل في رفع الصورة إلى الخادم'}), 500
            
        image_url = upload_result.get('url')
        
        # Use the TheHive.ai scraper
        results = scrape_thehive(image_url)
        
        # Add processing time and source info
        results['processing_time'] = f"{results.get('processing_time', 0):.1f}"
        
        # Clean up the temporary file
        try:
            os.remove(temp_path)
        except:
            pass
            
        return jsonify(results)
    except Exception as e:
        print(f"Error in AI detection: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': f'حدث خطأ: {str(e)}', 'source': 'TheHive.ai'}), 500

# First implementation of ai_detect_faceonlive has been removed to prevent duplicate endpoint errors
# The updated implementation is at line ~1458


@app.route('/api/upload', methods=['POST'])
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
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
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

@app.route('/api/export', methods=['POST'])
def export_results():
    """Export search results as JSON"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    response = jsonify(data)
    response.headers.set('Content-Disposition', 'attachment', filename='bahith-al-suwar-results.json')
    return response

@app.route('/api/ai-detection', methods=['POST'])
def api_ai_detection():
    """API endpoint for AI image detection using TheHive.ai or FaceOnLive"""
    print('[*] Received request to /api/ai-detection endpoint')
    print('[DEBUG] Starting API endpoint for AI detection')
    
    # Check if image file is provided
    if 'image' not in request.files:
        print('[!] No image file in request')
        return jsonify({
            'error': 'لم يتم العثور على صورة في الطلب',
            'success': False
        }), 400
    
    # Get the service from the form data - thehive (Model 1) or aiornot (Model 2)
    service = request.form.get('service', 'thehive')
    print(f'[*] Service requested: {service}')
    
    # Create upload directory if it doesn't exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # Get the image file from the request
    image_file = request.files['image']
    if image_file.filename == '':
        print('[!] Empty filename')
        return jsonify({
            'error': 'اسم الملف فارغ',
            'success': False
        }), 400
    
    # Save the image to a temporary file
    filename = secure_filename(image_file.filename)
    temp_path = os.path.join(UPLOAD_FOLDER, filename)
    try:
        image_file.save(temp_path)
        print(f'[✓] Image saved temporarily to {temp_path}')
    except Exception as e:
        print(f'[!] Error saving file: {str(e)}')
        return jsonify({
            'error': f'خطأ في حفظ الملف: {str(e)}',
            'success': False
        }), 500
    
    try:
        print('[DEBUG] Inside api_ai_detection try block')
        # Print the service being requested
        print(f'[DEBUG] Service requested: {service}')
        result = None
        
        # Upload file to imgbb to get URL for both services
        print('[*] Uploading image to ImgBB...')
        with open(temp_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
            
        image_url = upload_to_imgbb(image_data)
        if not image_url:
            print('[!] Failed to get image URL from ImgBB')
            return jsonify({
                'error': 'فشل في رفع الصورة للتحليل',
                'success': False
            }), 500
            
        print(f'[✓] Image uploaded to ImgBB: {image_url}')
        
        # Process based on selected service
        if service.lower() == 'thehive':
            # Model 1: Sightengine API (formerly TheHive.ai)
            print('[*] Processing with Model 1 (Sightengine API)')
            
            # Call the Sightengine API with the image URL
            print('[*] Starting Sightengine scraper...')
            result = scrape_thehive(image_url)
            print('[DEBUG] Sightengine scraper (Model 1) returned:', result)
            
        elif service.lower() == 'aiornot':
            # Model 2: AI-or-Not API
            print('[*] Processing with Model 2 (AI-or-Not API)')
            
            # Call the AI-or-Not API with the image URL
            print('[*] Starting AI-or-Not scraper...')
            result = scrape_aiornot(image_url)
            print('[DEBUG] AI-or-Not scraper (Model 2) returned:', result)
            
        elif service.lower() == 'faceonlive':
            # For FaceOnLive, we pass the local file path directly
            print('[*] Processing with FaceOnLive service')
            
            # Add a print statement to verify we're calling the scraper
            print('[DEBUG] About to call FaceOnLive scraper with path:', temp_path)
            
            # Explicitly wait to give time to debug
            print('[DEBUG] Waiting 2 seconds before starting scraper...')
            time.sleep(2)

            result = scrape_faceonlive(temp_path)
            print('[DEBUG] FaceOnLive scraper returned:', result)
            
        else:
            print(f'[!] Unknown service: {service}')
            return jsonify({
                'error': 'نوع خدمة غير معروف',
                'success': False
            }), 400
        
        if 'error' in result:
            print(f'[!] Error in scraper: {result["error"]}')
            return jsonify({
                'error': result['error'],
                'success': False
            }), 500
            
        print(f'[✓] Successfully obtained results from {service}')
        return jsonify(result)
        
    except Exception as e:
        print(f'[!] Unexpected error in AI detection: {str(e)}')
        traceback.print_exc()
        return jsonify({
            'error': f'خطأ غير متوقع: {str(e)}',
            'success': False
        }), 500
    finally:
        # Clean up the temporary file if it exists
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                print(f'[✓] Removed temporary file: {temp_path}')
        except Exception as e:
            print(f'[!] Error removing temporary file: {str(e)}')
@app.route('/image-source-search', methods=['POST'])
def image_source_search():

    try:
        data = request.get_json(silent=True) or {}
        image_url = data.get('image_url') or request.form.get('image_url')
        if not image_url:
            return jsonify({'links': [], 'search_urls': {}, 'error': 'image_url is required', 'success': False}), 200
        result = scrape_reverse_search(image_url)
        return jsonify(result), 200
    except Exception as e:
        app.logger.exception(e)  # use app.logger instead of current_app
        return jsonify({'links': [], 'search_urls': {}, 'error': f'Unhandled: {e}', 'success': False}), 200

# Endpoint for x.ai Contextual Image Investigation
@app.route('/api/xai-context', methods=['POST'])
def xai_context_api():
    try:
        data = request.get_json(silent=True) or {}
        image_url = data.get('image_url')

        if not image_url:
            return jsonify({'error': 'No image_url provided', 'success': False}), 400

        if not XAI_API_KEY:
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
        app.logger.exception(f"xAI context error: {e}")
        return jsonify({'error': str(e), 'success': False}), 500


# Endpoint for Zenserp Direct Search
@app.route('/api/direct-search', methods=['POST'])
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
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    
                    # Upload to ImgBB
                    with open(filepath, 'rb') as f:
                        image_data = base64.b64encode(f.read()).decode('utf-8')
                    image_url = upload_to_imgbb(image_data)
                    os.remove(filepath) # clean up
            
        if not query and not image_url:
            return jsonify({'error': 'No query or image provided', 'success': False}), 400

        print(f"[*] Starting Zenserp search. Query: {query}, Image: {image_url}")
        
        # Zenserp Search Logic
        from providers.zenserp import reverse_image_search, text_search

        if image_url:
            # Keep US/English for broader search + better source data; we translate after
            resp = reverse_image_search(image_url, gl='us', hl='en')
        else:
            resp = text_search(query, num=40, gl='sa', hl='ar')
        
        if resp.status_code != 200:
            print(f"[!] Zenserp API Error: {resp.text}")
            return jsonify({'error': f'Zenserp API Error: {resp.status_code}', 'details': resp.text, 'success': False}), 502

        zenserp_data = resp.json()
        print(f"[*] Zenserp response keys: {zenserp_data.keys()}")
        
        timeline = build_direct_search_timeline(zenserp_data, bool(image_url))

        return jsonify({
            'success': True,
            'timeline': timeline,
            'total': len(timeline),
            'raw': {} # Don't send raw data to save bandwidth
        })

    except Exception as e:
        print(f"[!] Error in Direct Search: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e), 'success': False}), 500

@app.route('/api/image-source-search', methods=['POST'])
def api_image_source_search():
    """API endpoint to find image sources using TheHive.ai"""
    if 'file' not in request.files:
        return jsonify({'error': 'لم يتم تقديم صورة'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
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



@app.route('/verify-audio', methods=['POST'])
@app.route('/api/verify-audio', methods=['POST'])
def verify_audio():
    """API endpoint to verify if audio is AI-generated using AIorNot API"""
    try:
        print("[*] Starting audio verification process")
        
        # Check if audio file is present in request
        if 'audio' not in request.files:
            print("[!] No audio file in request")
            return jsonify({
                'error': 'لم يتم تقديم ملف صوتي',
                'success': False
            }), 400
            
        audio_file = request.files['audio']
        print(f"[*] Received file: {audio_file.filename}")
        
        # Check if the file is valid
        if audio_file.filename == '':
            print("[!] Empty filename")
            return jsonify({
                'error': 'لم يتم اختيار ملف صوتي',
                'success': False
            }), 400
            
        if not allowed_audio_file(audio_file.filename):
            print(f"[!] File type not allowed: {audio_file.filename}")
            return jsonify({
                'error': 'نوع الملف غير مدعوم', 
                'message': 'الصيغ المدعومة: mp3, wav, m4a, وغيرها من الصيغ الصوتية الشائعة',
                'success': False
            }), 400
        
        # Create directory if it doesn't exist (just to be sure)
        os.makedirs(AUDIO_UPLOAD_FOLDER, exist_ok=True)
        
        # Save the file temporarily
        filename = secure_filename(audio_file.filename)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        saved_filename = f"{timestamp}-{filename}"
        audio_path = os.path.join(AUDIO_UPLOAD_FOLDER, saved_filename)
        
        try:
            audio_file.save(audio_path)
            file_size = os.path.getsize(audio_path)
            print(f'[*] Audio file saved to: {audio_path} (Size: {file_size} bytes)')
        except Exception as save_error:
            print(f'[!] Error saving file: {str(save_error)}')
            return jsonify({
                'error': 'فشل في حفظ الملف الصوتي', 
                'details': str(save_error),
                'success': False
            }), 500
        
        # Calculate MD5 hash for the file
        try:
            with open(audio_path, "rb") as f:
                file_data = f.read()
                md5_hash = hashlib.md5(file_data).hexdigest()
                print(f'[*] MD5 hash: {md5_hash}')
        except Exception as hash_error:
            print(f'[!] Error calculating hash: {str(hash_error)}')
            md5_hash = "غير متاح"
        
        # إضافة رابط الملف الصوتي للتشغيل في واجهة المستخدم
        audio_url = url_for('static', filename=f'uploads/audio/{saved_filename}')
        
        # Send file to AIorNot API
        try:
            from providers.aiornot import post_voice_file
            response = post_voice_file(audio_path)

            # Check if the request was successful
            if response.status_code != 200:
                error_msg = f"فشل في تحليل الصوت: {response.status_code}"
                try:
                    error_details = response.json()
                    error_msg += f" - {error_details}"
                except:
                    error_msg += f" - {response.text}"

                return jsonify({
                    'error': error_msg,
                    'success': False
                }), 500

            # Parse the response
            api_response = response.json()

            # Extract report data
            report = api_response.get('report', {})
            verdict = report.get('verdict', 'unknown')
            confidence = report.get('confidence', 0)
            duration = report.get('duration', 0)

            # Determine if AI generated based on verdict
            is_ai = verdict.lower() == 'ai'

            # Format the response for our frontend
            response_data = {
                'is_ai_generated': is_ai,
                'confidence': confidence,
                'id': api_response.get('id', str(uuid.uuid4())),
                'created_at': api_response.get('created_at', datetime.now().isoformat()),
                'audio_url': audio_url,
                'file_size': file_size,
                'md5': report.get('md5', md5_hash),
                'duration': duration,
                'details': {
                    'verdict': verdict,
                    'confidence': confidence,
                    'format': filename.split('.')[-1].upper()
                },
                'success': True
            }

            return jsonify(response_data)

        except requests.exceptions.RequestException as req_error:
            print(f'[!] Request error: {str(req_error)}')
            return jsonify({
                'error': 'فشل في الاتصال بخدمة تحليل الصوت',
                'message': str(req_error),
                'success': False
            }), 500
    
    except Exception as e:
        print(f'[!] Unexpected error: {str(e)}')
        return jsonify({
            'error': 'حدث خطأ غير متوقع',
            'message': str(e),
            'success': False
        }), 500




from providers.imgbb import upload_to_imgbb


# ─── Text AI Detection Endpoint ───────────────────────────────────
@app.route('/api/text-detection', methods=['POST'])
def api_text_detection():
    """Detect AI-generated text using AIorNot API"""
    print('[*] Received text detection request')
    
    data = request.get_json()
    if not data or not data.get('text'):
        return jsonify({'error': 'لم يتم إرسال نص للتحليل', 'success': False}), 400
    
    text_content = data['text'].strip()
    if len(text_content) < 20:
        return jsonify({'error': 'النص قصير جداً — يجب أن يكون 20 حرف على الأقل', 'success': False}), 400
    
    aiornot_key = os.environ.get('AIORNOT_API_KEY') or AIORNOT_API_KEY
    if not aiornot_key:
        return jsonify({'error': 'مفتاح API غير متوفر', 'success': False}), 500

    try:
        from providers.aiornot import post_text

        resp = post_text(text_content)

        if resp.status_code != 200:
            error_text = resp.text[:500]
            print(f'[!] Text API error: {error_text}')
            return jsonify({
                'error': f'فشل التحليل: {resp.status_code}',
                'success': False
            }), 500
        
        result = resp.json()
        print(f'[*] Text API response received')
        
        # Actual structure: report.ai_text { confidence, is_detected, annotations: [[text, score], ...] }
        report_obj = result.get('report', {})
        ai_text = report_obj.get('ai_text', {})
        
        if ai_text:
            is_ai = bool(ai_text.get('is_detected', False))
            ai_confidence = float(ai_text.get('confidence', 0.0))
            human_confidence = 1.0 - ai_confidence
            
            # Ensure values are between 0 and 1
            ai_confidence = max(0.0, min(ai_confidence, 1.0))
            human_confidence = max(0.0, min(human_confidence, 1.0))
            
            verdict_text = "نص مُولّد بالذكاء الاصطناعي" if is_ai else "نص بشري (غير مُولّد بالذكاء الاصطناعي)"
            
            # Parse annotations — format is [[text, score], [text, score], ...]
            annotations = []
            raw_annotations = ai_text.get('annotations', [])
            if isinstance(raw_annotations, list):
                for block in raw_annotations:
                    if isinstance(block, list) and len(block) >= 2:
                        block_text = str(block[0])
                        block_score = float(block[1]) if isinstance(block[1], (int, float)) else 0.0
                        # Score seems to be per-block — lower means more AI-like
                        annotations.append({
                            'text': block_text.strip(),
                            'is_ai': is_ai,  # Use overall verdict for block classification
                            'confidence': ai_confidence
                        })
            
            return jsonify({
                'success': True,
                'verdict': verdict_text,
                'is_ai': is_ai,
                'confidence_ai': ai_confidence,
                'confidence_human': human_confidence,
                'annotations': annotations
            })
        else:
            # Fallback — return raw report for debugging
            report_preview = json.dumps(report_obj, ensure_ascii=False, indent=2)[:800]
            print(f'[!] No ai_text in report. Keys: {list(report_obj.keys())}')
            return jsonify({
                'success': False,
                'error': f'بنية غير متوقعة: {report_preview}'
            }), 500
            
    except Exception as e:
        print(f'[!] Text detection error: {str(e)}')
        traceback.print_exc()
        return jsonify({
            'error': f'خطأ أثناء التحليل: {str(e)}',
            'success': False
        }), 500

# Video Analysis Endpoint
@app.route('/api/analyze-video', methods=['POST'])
def api_analyze_video():
    """Analyze video for AI content using AIorNot API"""
    print('[*] Received video analysis request')
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded', 'success': False}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected', 'success': False}), 400

    # Save temp file
    temp_filename = secure_filename(f"vid_{uuid.uuid4()}_{file.filename}")
    temp_path = os.path.join(UPLOAD_FOLDER, temp_filename)
    
    try:
        file.save(temp_path)
        print(f'[*] Video saved to {temp_path}')
        
        # Determine file size
        file_size = os.path.getsize(temp_path)
        print(f'[*] File size: {file_size / (1024*1024):.2f} MB')
        
        # Check API Key
        aiornot_key = os.environ.get('AIORNOT_API_KEY')
        if not aiornot_key:
             return jsonify({'error': 'AIorNot API Key missing', 'success': False}), 500

        # Call AIorNot API
        from providers.aiornot import post_video_file
        response = post_video_file(temp_path, file.filename)
        
        if response.status_code == 200:
            result = response.json()
            print('DEBUG AI Response:', json.dumps(result, indent=2))
            return jsonify({'success': True, 'data': result})
        elif response.status_code == 422:
             print(f'[!] Validation Error: {response.text}')
             return jsonify({'error': 'Validation Error (Check file format/parameters)', 'details': response.json(), 'success': False}), 422
        else:
            print(f'[!] AIorNot Error: {response.text}')
            return jsonify({'error': f'AIorNot API Error: {response.status_code}', 'details': response.text, 'success': False}), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request timed out (Video might be too long)', 'success': False}), 504
    except Exception as e:
        print(f'[!] Error in video analysis: {e}')
        traceback.print_exc()
        return jsonify({'error': str(e), 'success': False}), 500
    finally:
        # Cleanup
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                print(f'[*] Removed temp video: {temp_path}')
            except:
                pass

# FaceOnLive implementation using the new scraper code

@app.route('/api/faceonlive-detection', methods=['POST'])
@app.route('/ai-detect-faceonlive', methods=['POST'])  # Keep old route for compatibility
def ai_detect_faceonlive():
    """Handle image upload for FaceOnLive detection"""
    print('[*] Received request to FaceOnLive detection endpoint')
    
    if 'image' not in request.files:
        print('[!] No image file in request')
        return jsonify({
            'error': 'لم يتم العثور على صورة في الطلب',
            'success': False
        }), 400
        
    # Create upload directory if it doesn't exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # Get the image file from the request
    image_file = request.files['image']
    if image_file.filename == '':
        print('[!] Empty filename')
        return jsonify({
            'error': 'اسم الملف فارغ',
            'success': False
        }), 400
    
    # Save the image to a temporary file
    filename = secure_filename(f"faceonlive_{uuid.uuid4()}_{image_file.filename}")
    temp_path = os.path.join(UPLOAD_FOLDER, filename)
    try:
        image_file.save(temp_path)
        print(f'[✓] Image saved temporarily to {temp_path}')
    except Exception as e:
        print(f'[!] Error saving file: {str(e)}')
        return jsonify({
            'error': f'خطأ في حفظ الملف: {str(e)}',
            'success': False
        }), 500
    
    try:
        # Call the FaceOnLive scraper with the path to the image file
        print('[*] Starting FaceOnLive scraper...')
        results = scrape_faceonlive(temp_path)
        
        if 'error' in results:
            print(f'[!] Error in scraper: {results["error"]}')
            return jsonify({
                'error': results['error'],
                'success': False
            }), 500
            
        print('[✓] Successfully obtained results from FaceOnLive')
        return jsonify(results)
        
    except Exception as e:
        print(f'[!] Unexpected error in AI detection: {str(e)}')
        traceback.print_exc()
        return jsonify({
            'error': f'خطأ غير متوقع: {str(e)}',
            'success': False
        }), 500
    finally:
        # File cleanup is now handled inside the scrape_faceonlive function
        pass



@app.route('/api/provenance', methods=['POST'])
def api_provenance():
    """API endpoint for provenance analysis (origin & first seen)"""
    try:
        data = request.get_json(silent=True) or {}
        if not data.get('image_url'):
            return jsonify({'error': 'image_url required'}), 200
        return jsonify(analyze_provenance(data['image_url'])), 200
    except Exception as e:
        app.logger.exception('provenance API error')
        return jsonify({
            'first_seen': None,
            'timeline': [],
            'related_images': [],
            'stats': {'checked': 0, 'with_dates': 0},
            'note': f'Server error: {str(e)}'
        }), 200

# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    """Register a new user"""
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        display_name = data.get('display_name', '').strip()
        
        # Validation
        if not email or '@' not in email:
            return jsonify({'error': 'البريد الإلكتروني غير صالح', 'code': 'INVALID_EMAIL'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'code': 'WEAK_PASSWORD'}), 400
        
        # Check if email exists
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'البريد الإلكتروني مسجل مسبقاً', 'code': 'EMAIL_EXISTS'}), 409
        
        # Create user
        user = User(
            email=email,
            display_name=display_name or email.split('@')[0]
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Generate token
        token = generate_token(user)
        
        return jsonify({
            'success': True,
            'token': token,
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f'[!] Register error: {e}')
        return jsonify({'error': 'حدث خطأ في التسجيل', 'code': 'REGISTER_ERROR'}), 500


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """Login user and return JWT token"""
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'البريد الإلكتروني وكلمة المرور مطلوبان', 'code': 'MISSING_CREDENTIALS'}), 400
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            return jsonify({'error': 'بيانات الدخول غير صحيحة', 'code': 'INVALID_CREDENTIALS'}), 401
        
        if not user.is_active:
            return jsonify({'error': 'الحساب معطل', 'code': 'ACCOUNT_DISABLED'}), 403
        
        # Generate token
        token = generate_token(user)
        
        return jsonify({
            'success': True,
            'token': token,
            'user': user.to_dict()
        })
        
    except Exception as e:
        print(f'[!] Login error: {e}')
        return jsonify({'error': 'حدث خطأ في تسجيل الدخول', 'code': 'LOGIN_ERROR'}), 500


@app.route('/api/auth/me', methods=['GET'])
@login_required
def auth_me():
    """Get current user info"""
    from flask import g
    return jsonify({
        'success': True,
        'user': g.current_user.to_dict()
    })


# =============================================================================
# USER-SCOPED DATA ENDPOINTS
# =============================================================================

@app.route('/api/user/searches', methods=['GET'])
@login_required
def get_user_searches():
    """Get current user's search history (isolated)"""
    from flask import g
    
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    search_type = request.args.get('type')
    
    # NOTE: Search defines a `query` COLUMN which shadows Model.query —
    # must go through db.session.query() here.
    query = db.session.query(Search).filter_by(user_id=g.current_user.id)
    
    if search_type:
        query = query.filter_by(search_type=search_type)
    
    total = query.count()
    searches = query.order_by(Search.created_at.desc()).offset(offset).limit(limit).all()
    
    return jsonify({
        'success': True,
        'total': total,
        'searches': [s.to_dict() for s in searches]
    })


@app.route('/api/user/analyses', methods=['GET'])
@login_required
def get_user_analyses():
    """Get current user's analysis history (isolated)"""
    from flask import g
    
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    analysis_type = request.args.get('type')
    
    query = Analysis.query.filter_by(user_id=g.current_user.id)
    
    if analysis_type:
        query = query.filter_by(analysis_type=analysis_type)
    
    total = query.count()
    analyses = query.order_by(Analysis.created_at.desc()).offset(offset).limit(limit).all()
    
    return jsonify({
        'success': True,
        'total': total,
        'analyses': [a.to_dict() for a in analyses]
    })


@app.route('/api/user/keywords', methods=['GET'])
@login_required
def get_user_keywords():
    """Get current user's saved keywords"""
    from flask import g
    
    keywords = Keyword.query.filter_by(user_id=g.current_user.id, is_active=True).all()
    
    return jsonify({
        'success': True,
        'keywords': [k.to_dict() for k in keywords]
    })


@app.route('/api/user/keywords', methods=['POST'])
@login_required
def add_user_keyword():
    """Add a new keyword for current user"""
    from flask import g
    
    data = request.get_json() or {}
    keyword_text = data.get('keyword', '').strip()
    category = data.get('category', '').strip()
    
    if not keyword_text:
        return jsonify({'error': 'الكلمة المفتاحية مطلوبة'}), 400
    
    # Check for duplicate
    existing = Keyword.query.filter_by(user_id=g.current_user.id, keyword=keyword_text).first()
    if existing:
        return jsonify({'error': 'الكلمة موجودة مسبقاً', 'code': 'DUPLICATE'}), 409
    
    keyword = Keyword(
        user_id=g.current_user.id,
        keyword=keyword_text,
        category=category or None
    )
    db.session.add(keyword)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'keyword': keyword.to_dict()
    }), 201


@app.route('/api/user/keywords/<keyword_id>', methods=['DELETE'])
@login_required
def delete_user_keyword(keyword_id):
    """Delete a user's keyword"""
    from flask import g
    
    keyword = Keyword.query.filter_by(id=keyword_id, user_id=g.current_user.id).first()
    
    if not keyword:
        return jsonify({'error': 'الكلمة غير موجودة'}), 404
    
    db.session.delete(keyword)
    db.session.commit()
    
    return jsonify({'success': True})


# =============================================================================
# SHARED CATALOG ENDPOINTS (Read: All Users, Write: Admin Only)
# =============================================================================

@app.route('/api/countries', methods=['GET'])
def get_countries():
    """Get all active countries (public - no auth required)"""
    countries = Country.query.filter_by(is_active=True).order_by(Country.name_ar).all()
    return jsonify({
        'success': True,
        'countries': [c.to_dict() for c in countries]
    })


@app.route('/api/sources', methods=['GET'])
def get_sources():
    """Get all active sources (public - no auth required)"""
    country_id = request.args.get('country_id')
    category = request.args.get('category')
    verified_only = request.args.get('verified', 'false').lower() == 'true'
    
    query = Source.query.filter_by(is_active=True)
    
    if country_id:
        query = query.filter_by(country_id=country_id)
    if category:
        query = query.filter_by(category=category)
    if verified_only:
        query = query.filter_by(is_verified=True)
    
    sources = query.order_by(Source.name).all()
    
    return jsonify({
        'success': True,
        'sources': [s.to_dict(include_country=True) for s in sources]
    })


# =============================================================================
# ADMIN-ONLY CATALOG MANAGEMENT
# =============================================================================

@app.route('/api/admin/countries', methods=['GET'])
@admin_required
def admin_get_countries():
    """Admin: Get all countries including inactive"""
    countries = Country.query.order_by(Country.code).all()
    return jsonify({
        'success': True,
        'countries': [c.to_dict() for c in countries]
    })


@app.route('/api/admin/countries', methods=['POST'])
@admin_required
def admin_create_country():
    """Admin: Create a new country"""
    data = request.get_json() or {}
    
    code = data.get('code', '').strip().upper()
    name_ar = data.get('name_ar', '').strip()
    name_en = data.get('name_en', '').strip()
    
    if not code or not name_ar:
        return jsonify({'error': 'الكود والاسم العربي مطلوبان'}), 400
    
    if Country.query.filter_by(code=code).first():
        return jsonify({'error': 'كود الدولة موجود مسبقاً'}), 409
    
    country = Country(code=code, name_ar=name_ar, name_en=name_en)
    db.session.add(country)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'country': country.to_dict()
    }), 201


@app.route('/api/admin/countries/<country_id>', methods=['PUT'])
@admin_required
def admin_update_country(country_id):
    """Admin: Update a country"""
    country = Country.query.get(country_id)
    if not country:
        return jsonify({'error': 'الدولة غير موجودة'}), 404
    
    data = request.get_json() or {}
    
    if 'name_ar' in data:
        country.name_ar = data['name_ar'].strip()
    if 'name_en' in data:
        country.name_en = data['name_en'].strip()
    if 'is_active' in data:
        country.is_active = bool(data['is_active'])
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'country': country.to_dict()
    })


@app.route('/api/admin/sources', methods=['GET'])
@admin_required
def admin_get_sources():
    """Admin: Get all sources including inactive"""
    sources = Source.query.order_by(Source.domain).all()
    return jsonify({
        'success': True,
        'sources': [s.to_dict(include_country=True) for s in sources]
    })


@app.route('/api/admin/sources', methods=['POST'])
@admin_required
def admin_create_source():
    """Admin: Create a new source"""
    data = request.get_json() or {}
    
    name = data.get('name', '').strip()
    domain = data.get('domain', '').strip().lower()
    category = data.get('category', '').strip()
    country_id = data.get('country_id')
    is_verified = data.get('is_verified', False)
    
    if not name or not domain:
        return jsonify({'error': 'الاسم والدومين مطلوبان'}), 400
    
    if Source.query.filter_by(domain=domain).first():
        return jsonify({'error': 'الدومين موجود مسبقاً'}), 409
    
    source = Source(
        name=name,
        domain=domain,
        category=category or None,
        country_id=country_id or None,
        is_verified=is_verified
    )
    db.session.add(source)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'source': source.to_dict()
    }), 201


@app.route('/api/admin/sources/<source_id>', methods=['PUT'])
@admin_required
def admin_update_source(source_id):
    """Admin: Update a source"""
    source = Source.query.get(source_id)
    if not source:
        return jsonify({'error': 'المصدر غير موجود'}), 404
    
    data = request.get_json() or {}
    
    if 'name' in data:
        source.name = data['name'].strip()
    if 'category' in data:
        source.category = data['category'].strip() or None
    if 'country_id' in data:
        source.country_id = data['country_id'] or None
    if 'is_verified' in data:
        source.is_verified = bool(data['is_verified'])
    if 'is_active' in data:
        source.is_active = bool(data['is_active'])
    if 'logo_url' in data:
        source.logo_url = data['logo_url'].strip() or None
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'source': source.to_dict()
    })


@app.route('/api/admin/sources/<source_id>', methods=['DELETE'])
@admin_required
def admin_delete_source(source_id):
    """Admin: Soft delete a source (set inactive)"""
    source = Source.query.get(source_id)
    if not source:
        return jsonify({'error': 'المصدر غير موجود'}), 404
    
    source.is_active = False
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    """Admin: Get all users"""
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({
        'success': True,
        'users': [u.to_dict() for u in users]
    })


@app.route('/api/admin/users/<user_id>/toggle-active', methods=['POST'])
@admin_required
def admin_toggle_user_active(user_id):
    """Admin: Enable/disable a user"""
    from flask import g
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'المستخدم غير موجود'}), 404
    
    # Prevent disabling yourself
    if user.id == g.current_user.id:
        return jsonify({'error': 'لا يمكنك تعطيل حسابك الخاص'}), 400
    
    user.is_active = not user.is_active
    db.session.commit()
    
    return jsonify({
        'success': True,
        'user': user.to_dict()
    })


@app.route('/api/admin/users/<user_id>/reset-password', methods=['POST'])
@admin_required
def admin_reset_user_password(user_id):
    """Admin: Reset a user's password"""
    from flask import g
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'المستخدم غير موجود'}), 404
    
    data = request.get_json() or {}
    new_password = data.get('password', '').strip()
    
    if not new_password:
        return jsonify({'error': 'كلمة المرور الجديدة مطلوبة'}), 400
    
    if len(new_password) < 6:
        return jsonify({'error': 'كلمة المرور يجب أن تكون 6 أحرف على الأقل'}), 400
    
    user.set_password(new_password)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'تم تحديث كلمة المرور بنجاح'
    })


@app.route('/api/admin/files', methods=['GET'])
@admin_required
def admin_get_all_files():
    """Admin: Get all users' files"""
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    user_id = request.args.get('user_id')
    file_type = request.args.get('file_type')
    
    query = UserFile.query
    
    if user_id:
        query = query.filter_by(user_id=user_id)
    if file_type:
        query = query.filter_by(file_type=file_type)
    
    total = query.count()
    files = query.order_by(UserFile.created_at.desc()).offset(offset).limit(limit).all()
    
    return jsonify({
        'success': True,
        'total': total,
        'files': [f.to_dict(include_user=True) for f in files]
    })


# =============================================================================
# USER FILES ENDPOINTS (ملفاتي - My Files)
# =============================================================================

# Create storage folder for user files
USER_FILES_FOLDER = os.path.join(os.path.dirname(__file__), 'user_files')
os.makedirs(USER_FILES_FOLDER, exist_ok=True)


@app.route('/api/user/files', methods=['GET'])
@login_required
def get_user_files():
    """Get current user's files only (isolated)"""
    from flask import g
    
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    file_type = request.args.get('file_type')
    
    query = UserFile.query.filter_by(user_id=g.current_user.id)
    
    if file_type:
        query = query.filter_by(file_type=file_type)
    
    total = query.count()
    files = query.order_by(UserFile.created_at.desc()).offset(offset).limit(limit).all()
    
    return jsonify({
        'success': True,
        'total': total,
        'files': [f.to_dict() for f in files]
    })


@app.route('/api/user/files', methods=['POST'])
@login_required
def upload_user_file():
    """Upload a file for current user"""
    from flask import g
    import mimetypes
    
    if 'file' not in request.files:
        return jsonify({'error': 'لم يتم إرسال ملف'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400
    
    # Get metadata from form
    description = request.form.get('description', '').strip()
    source_feature = request.form.get('source_feature', '').strip()
    file_type = request.form.get('file_type', '').strip()
    
    # Generate unique stored filename
    original_filename = secure_filename(file.filename)
    file_ext = os.path.splitext(original_filename)[1]
    stored_filename = f"{uuid.uuid4()}{file_ext}"
    
    # Create user subfolder
    user_folder = os.path.join(USER_FILES_FOLDER, g.current_user.id)
    os.makedirs(user_folder, exist_ok=True)
    
    # Save file
    file_path = os.path.join(user_folder, stored_filename)
    file.save(file_path)
    
    # Get file info
    file_size = os.path.getsize(file_path)
    mime_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'
    
    # Auto-detect file type if not provided
    if not file_type:
        if mime_type.startswith('image/'):
            file_type = 'image'
        elif mime_type.startswith('video/'):
            file_type = 'video'
        elif mime_type.startswith('audio/'):
            file_type = 'audio'
        elif mime_type in ['application/pdf', 'application/json', 'text/csv']:
            file_type = 'report'
        else:
            file_type = 'export'
    
    # Create database record
    user_file = UserFile(
        user_id=g.current_user.id,
        filename=original_filename,
        stored_filename=stored_filename,
        file_type=file_type,
        mime_type=mime_type,
        file_size=file_size,
        file_path=os.path.join(g.current_user.id, stored_filename),
        description=description or None,
        source_feature=source_feature or None
    )
    
    db.session.add(user_file)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'file': user_file.to_dict()
    }), 201


@app.route('/api/user/files/<file_id>', methods=['GET'])
@login_required
def get_user_file(file_id):
    """Get details of a specific user file"""
    from flask import g
    
    user_file = UserFile.query.filter_by(id=file_id, user_id=g.current_user.id).first()
    
    if not user_file:
        return jsonify({'error': 'الملف غير موجود'}), 404
    
    return jsonify({
        'success': True,
        'file': user_file.to_dict()
    })


@app.route('/api/user/files/<file_id>/download', methods=['GET'])
@login_required
def download_user_file(file_id):
    """Download a user's file"""
    from flask import g, send_file
    
    user_file = UserFile.query.filter_by(id=file_id, user_id=g.current_user.id).first()
    
    if not user_file:
        return jsonify({'error': 'الملف غير موجود'}), 404
    
    file_path = os.path.join(USER_FILES_FOLDER, user_file.file_path)
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'الملف غير موجود على الخادم'}), 404
    
    # Increment download count
    user_file.download_count += 1
    db.session.commit()
    
    return send_file(
        file_path,
        download_name=user_file.filename,
        as_attachment=True
    )


@app.route('/api/user/files/<file_id>', methods=['DELETE'])
@login_required
def delete_user_file(file_id):
    """Delete a user's file"""
    from flask import g
    
    user_file = UserFile.query.filter_by(id=file_id, user_id=g.current_user.id).first()
    
    if not user_file:
        return jsonify({'error': 'الملف غير موجود'}), 404
    
    # Delete physical file
    file_path = os.path.join(USER_FILES_FOLDER, user_file.file_path)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f'[!] Error deleting file: {e}')
    
    # Delete database record
    db.session.delete(user_file)
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/admin/files/<file_id>/download', methods=['GET'])
@admin_required
def admin_download_file(file_id):
    """Admin: Download any user's file"""
    from flask import send_file
    
    user_file = UserFile.query.get(file_id)
    
    if not user_file:
        return jsonify({'error': 'الملف غير موجود'}), 404
    
    file_path = os.path.join(USER_FILES_FOLDER, user_file.file_path)
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'الملف غير موجود على الخادم'}), 404
    
    return send_file(
        file_path,
        download_name=user_file.filename,
        as_attachment=True
    )


if __name__ == '__main__':
    # تشغيل التطبيق على جميع الواجهات (0.0.0.0) بدلاً من localhost فقط
    # هذا يتيح الوصول إلى التطبيق من أجهزة أخرى على نفس الشبكة
    app.run(host='0.0.0.0', port=5000, debug=True)