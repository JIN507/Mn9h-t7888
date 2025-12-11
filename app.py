import os, time, traceback, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import sys
import re
import json
import uuid
import time
import base64
import hashlib
import requests
import traceback
import random

from datetime import datetime
from urllib.parse import urlencode, quote_plus
import cv2
import numpy as np
from PIL import Image
import io
from flask import Flask, render_template, request, url_for, redirect, flash, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from datetime import datetime
import uuid
import urllib.request
import asyncio
import hashlib

# Try to import Google Cloud Vision
try:
    from google.cloud import vision
    VISION_API_AVAILABLE = True
    
    # Set credentials path if not already set
    if not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        credentials_path = os.path.join(os.path.dirname(__file__), 'google-credentials.json')
        if os.path.exists(credentials_path):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
            print(f'[*] Google Cloud credentials set to: {credentials_path}')
        # else:
            # print('[!] google-credentials.json not found. Please set GOOGLE_APPLICATION_CREDENTIALS.')
except ImportError:
    VISION_API_AVAILABLE = False
    print('[!] Google Cloud Vision not available. Install with: pip install google-cloud-vision')

# Import requests for direct API calls
import traceback

# AI Detection imports
from playwright.sync_api import sync_playwright

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

import concurrent.futures

# Initialize Flask
# Initialize Flask
# Serve static files from 'frontend/dist/assets' available at '/assets'
# Serve templates (index.html) from 'frontend/dist'
app = Flask(__name__, static_folder='frontend/dist/assets', static_url_path='/assets', template_folder='frontend/dist')
CORS(app)

# Load environment variables
load_dotenv()

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

# Config
UPLOAD_FOLDER = 'uploads'
# Create uploads directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# Hard-coded IMGBB API key (you should move this to .env file in production)
# API Keys from Environment
IMGBB_API_KEY = os.environ.get('IMGBB_API_KEY')
AIORNOT_API_KEY = os.environ.get('AIORNOT_API_KEY')
SERPAPI_API_KEY = os.environ.get('SERPAPI_API_KEY')
ZENSERP_API_KEY = os.environ.get('ZENSERP_API_KEY')

# Setting environment variable as in the example
if AIORNOT_API_KEY:
    os.environ['AIORNOT_API_KEY'] = AIORNOT_API_KEY
# The exact endpoints from the API docs
VOICE_ENDPOINT = "https://api.aiornot.com/v1/reports/voice"
IMAGE_ENDPOINT = "https://api.aiornot.com/v1/reports/image"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024 * 1024  # 256MB max upload
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Create audio upload folder if it doesn't exist - inside static for web access
# Note: Since we changed static_folder, we need to handle user uploads carefully.
# We'll serve uploads via a specific route or keep them in root 'static' and serve manually.
AUDIO_UPLOAD_FOLDER = os.path.join('uploads', 'audio') # Removed 'static' prefix to avoid confusion with React static
os.makedirs(AUDIO_UPLOAD_FOLDER, exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac', 'wma'}

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_audio_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS

# First implementation of upload_to_imgbb has been removed
# Using the improved version defined at line ~1404

# Video processing functions
def extract_frames_from_video(video_path, frame_interval):
    """Extract frames from video file at specified intervals"""
    try:
        # Open the video file
        video = cv2.VideoCapture(video_path)
        
        # Check if video opened successfully
        if not video.isOpened():
            print("Error: Could not open video file")
            return []
        
        # Get video properties
        fps = video.get(cv2.CAP_PROP_FPS)
        total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        # Calculate frame interval in frames
        frame_interval_sec = int(frame_interval)  # Convert to integer seconds
        frame_interval_frames = int(fps * frame_interval_sec)
        
        # Ensure we extract at least one frame
        if frame_interval_frames <= 0:
            frame_interval_frames = 1
        
        frames = []
        frame_count = 0
        
        while True:
            # Read the next frame
            success, frame = video.read()
            
            # Break the loop if we've reached the end of the video
            if not success:
                break
            
            # Extract frame at specified interval
            if frame_count % frame_interval_frames == 0:
                # Convert frame to base64 encoded string
                try:
                    _, buffer = cv2.imencode('.jpg', frame)
                    img_str = base64.b64encode(buffer).decode('utf-8')
                    frames.append({
                        'data': f'data:image/jpeg;base64,{img_str}',
                        'timestamp': frame_count / fps if fps > 0 else 0
                    })
                except Exception as e:
                    print(f"Error encoding frame {frame_count}: {e}")
            
            frame_count += 1
        
        # Release the video file
        video.release()
        
        return frames
    except Exception as e:
        print(f"Error extracting frames: {str(e)}")
        return []

def download_image(url, path):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(response.content)
            print(f"[*] Image downloaded to: {path}")
            return True
        else:
            print(f"[!] Failed to download image: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"[!] Error downloading image: {str(e)}")
        return False

# Free transcription via Google Web Speech API


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXTENSION_PATH = os.path.join(BASE_DIR, "yescaptcha-extension")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
USER_DATA_DIR = os.path.join(BASE_DIR, "user-data")







def search_images(image_url):
    """Generate search URLs for reverse image search engines"""
    return {
        'google': f"https://lens.google.com/uploadbyurl?url={image_url}",
        'bing': f"https://www.bing.com/images/search?q=imgurl:{image_url}&view=detailv2&iss=sbi",
        'yandex': f"https://yandex.com/images/search?rpt=imageview&url={image_url}",
        'tineye': f"https://tineye.com/search?url={image_url}"
    }

from io import BytesIO

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

import os, requests, traceback

# (اختياري) إجبار IPv4 — يفيد لو الشبكة عندك تتعلّق على IPv6
try:
    import socket, urllib3.util.connection as urllib3_cn
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
except Exception:
    pass

# SERPAPI Key loaded from env above

def scrape_reverse_search(image_url):
    """
    Drop-in replacement: uses SerpAPI Google Reverse Image only.
    Keeps the same return structure your app expects.
    """
    try:
        print(f'[*] Starting reverse image search (SerpAPI) for: {image_url}')
        # keep your existing manual search links helper
        search_links = search_images(image_url)

        params = {
            'engine': 'google_reverse_image',
            'image_url': image_url,
            'api_key': SERPAPI_API_KEY,
            'device': 'desktop',
            'google_domain': 'google.com',  # change to 'google.com.sa' if you prefer
            'gl': 'sa',
            'hl': 'ar',
        }

        try:
            resp = requests.get('https://serpapi.com/search.json', params=params, timeout=(8, 20))
            print(f'[*] SerpAPI status={resp.status_code}')
            if resp.status_code != 200:
                return {
                    'links': [],
                    'search_urls': search_links,
                    'source': 'SerpAPI',
                    'error': f'SerpAPI HTTP {resp.status_code}: {resp.text[:200]}',
                    'success': True
                }

            data = resp.json()

            # collect candidate links from common fields
            buckets = []
            for key in ('image_results', 'inline_images', 'visual_matches', 'organic_results'):
                val = data.get(key)
                if isinstance(val, list):
                    buckets.extend(val)

            links = []
            for item in buckets:
                if not isinstance(item, dict):
                    continue
                url = item.get('link') or item.get('source') or item.get('original') or item.get('image')
                if url:
                    links.append(url)

            # de-duplicate while preserving order
            seen, uniq = set(), []
            for u in links:
                if u not in seen:
                    seen.add(u)
                    uniq.append(u)

            return {
                'links': uniq,
                'search_urls': search_links,
                'source': 'SerpAPI',
                'success': True
            }

        except requests.exceptions.Timeout as e:
            return {
                'links': [],
                'search_urls': search_links,
                'source': 'Search Engine Links (Timeout)',
                'error': f'SerpAPI timeout: {e}',
                'success': True
            }
        except requests.RequestException as e:
            traceback.print_exc()
            return {
                'links': [],
                'search_urls': search_links,
                'source': 'Search Engine Links (API Failed)',
                'error': str(e),
                'success': True
            }

    except Exception as e:
        traceback.print_exc()
        return {
            'links': [],
            'search_urls': {},
            'error': str(e),
            'success': False
        }
def extract_frames(video_file, frame_interval=2):
    """Extract frames from video file at specified time intervals"""
    video = cv2.VideoCapture(video_file)
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = video.get(cv2.CAP_PROP_FPS)
    duration = total_frames / fps
    
    # Convert time interval to frame interval
    frame_step = int(frame_interval * fps)
    if frame_step < 1:
        frame_step = 1  # Ensure minimum step of at least 1 frame
    
    # Calculate frame indices based on time interval
    frame_indices = []
    current_frame = 0
    while current_frame < total_frames:
        frame_indices.append(current_frame)
        current_frame += frame_step
    
    frames = []
    for idx in frame_indices:
        video.set(cv2.CAP_PROP_POS_FRAMES, idx)
        success, frame = video.read()
        if success:
            _, buffer = cv2.imencode('.jpg', frame)
            img_str = base64.b64encode(buffer).decode('utf-8')
            frames.append({
                'data': f"data:image/jpeg;base64,{img_str}",
                'timestamp': idx / fps  # Time in seconds
            })
    
    video.release()
    return frames





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

@app.route('/api/extract-frames', methods=['POST'])
def extract_video_frames():
    """API endpoint to extract frames from video using time interval"""
    if 'file' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400

    file = request.files['file']
    if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        frame_interval = float(request.form.get('frameInterval', 2))
        frames = extract_frames(filepath, frame_interval)
        os.remove(filepath)
        return jsonify({
            'frames': frames,
            'totalFrames': len(frames)
        })
    except Exception as e:
        app.logger.error(f"Frame extraction error: {str(e)}")
        if os.path.exists(filepath):
            os.remove(filepath)
            return jsonify({'error': str(e)}), 500




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
            
            # Force browser visibility
            os.environ['PLAYWRIGHT_FORCE_VISIBLE'] = '1'
            
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
        headers = {'apikey': ZENSERP_API_KEY}
        
        if image_url:
            # Reverse Image Search - use image_url parameter per Zenserp docs
            params = {
                'image_url': image_url,
                'gl': 'us',              # Keep US for broader search, we will translate
                'hl': 'en'               # Keep English for better source data
            }
            print(f"[*] Zenserp reverse image search params: {params}")
            resp = requests.get('https://app.zenserp.com/api/v2/search', headers=headers, params=params, timeout=90)
            
        else:
            # Text Search
            params = {
                'q': query,
                'num': 40, # Fetch more initially, then filter
                'gl': 'sa',
                'hl': 'ar'
            }
            resp = requests.get('https://app.zenserp.com/api/v2/search', headers=headers, params=params, timeout=60)

        print(f"[*] Zenserp response status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"[!] Zenserp API Error: {resp.text}")
            return jsonify({'error': f'Zenserp API Error: {resp.status_code}', 'details': resp.text, 'success': False}), 502

        zenserp_data = resp.json()
        print(f"[*] Zenserp response keys: {zenserp_data.keys()}")
        
        # Initialize translation
        try:
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(source='auto', target='ar')
            def translate_text(text):
                if not text: return text
                try:
                    # Don't translate if already looks Arabic (simple heuristic)
                    if any('\u0600' <= char <= '\u06FF' for char in text[:10]):
                        return text
                    return translator.translate(text)
                except:
                    return text
        except ImportError:
            print("[!] deep_translator not found, skipping translation")
            def translate_text(text): return text # Fallback if translator not available

        # Process results into a standard timeline format
        items_to_process = []
        
        # Helper to parse Zenserp results (without translation yet)
        def parse_item(item, source_type='web'):
            title = item.get('title', 'No Title')
            link = item.get('url') or item.get('link') or item.get('destination')
            snippet = item.get('description') or item.get('snippet') or item.get('title')
            thumbnail = item.get('thumbnail') or item.get('image')
            
            # Extract Date
            date_str = item.get('date') or item.get('snippet_highlighted_words', [None])[0] if isinstance(item.get('snippet_highlighted_words'), list) else None
            
            # Helper to extract date from snippet text if date_str is missing
            if not date_str and snippet:
                # Expanded Regex for English and Arabic dates
                import re
                date_candidates = []
                
                # 1. Standard Date: "Oct 25, 2023" or "2023-10-25"
                match_std = re.search(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b|\b\d{4}-\d{2}-\d{2}\b', snippet, re.IGNORECASE)
                if match_std: date_candidates.append(match_std.group(0))

                # 2. Relative English: "2 hours ago", "5 mins ago"
                match_rel_en = re.search(r'\b\d+\s+(?:sec|min|hour|day|week|month|year)s?\s+ago\b', snippet, re.IGNORECASE)
                if match_rel_en: date_candidates.append(match_rel_en.group(0))

                # 3. Relative Arabic: "منذ 3 ساعات", "منذ يومين"
                match_rel_ar = re.search(r'\bمنذ\s+(?:\d+|يومين|ساعتين)\s+(?:ثواني|ثانية|دقائق|دقيقة|ساعات|ساعة|أيام|يوم|أسابيع|أسبوع|أشهر|شهر|سنوات|سنة)\b', snippet)
                if match_rel_ar: date_candidates.append(match_rel_ar.group(0))
                
                if date_candidates:
                    date_str = date_candidates[0]

            # Try to extract domain
            domain = 'Web'
            if link:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(link).netloc
                except:
                    pass

            # Timestamp parsing with better language support
            timestamp = None
            if date_str:
                try:
                    if DATEPARSER_AVAILABLE:
                         # Explicitly hint Arabic and English
                         dt = dateparser.parse(date_str, languages=['ar', 'en'])
                         if dt: timestamp = dt.isoformat()
                except:
                    pass
            
            return {
                'title': title,
                'link': link,
                'snippet': snippet,
                'thumbnail': thumbnail,
                'date_text': date_str,
                'timestamp': timestamp,
                'source': domain,
                'type': source_type
            }

        # Harvest results from all sections
        sections_to_check = [
            ('reverse_image_results', ['organic', 'pages_with_matching_images']),
            ('organic', None),
            ('image_results', None)
        ]
        
        for section, subsections in sections_to_check:
            if section in zenserp_data:
                data_section = zenserp_data[section]
                
                # Handle nested structure (reverse_image_results)
                if subsections and isinstance(data_section, dict):
                    for sub in subsections:
                        if sub in data_section and data_section[sub]:
                            for item in data_section[sub]:
                                items_to_process.append(parse_item(item, 'organic'))
                
                # Handle list structure (organic, image_results)
                elif isinstance(data_section, list):
                     for item in data_section:
                        items_to_process.append(parse_item(item, 'organic'))

        # Remove duplicates based on link
        seen_links = set()
        unique_items = []
        for item in items_to_process:
            if item['link'] and item['link'] not in seen_links:
                seen_links.add(item['link'])
                unique_items.append(item)
        
        # Sort: Oldest first (Ascending)
        # Items with timestamp appear first, sorted ascending (oldest to newest)
        # Items without timestamp appear last
        unique_items.sort(key=lambda x: (x['timestamp'] is None, x['timestamp']))
        
        # Limit to top 20 BEFORE translation to save time
        final_items = unique_items[:20]

        print(f"[*] Translating {len(final_items)} items...")

        # Parallel translation using ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            def translate_item(item):
                if not item['title'] and not item['snippet']:
                    return item
                    
                # Translating title and snippet
                if item['title']:
                    item['title'] = translate_text(item['title'])
                if item['snippet']:
                    item['snippet'] = translate_text(item['snippet'])
                return item
            
            # Execute translation in parallel
            timeline = list(executor.map(translate_item, final_items))

        print(f"[*] Total filtered timeline items: {len(timeline)}")

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
        
        # AIorNot API Key and endpoint
        API_KEY = AIORNOT_API_KEY
        VOICE_ENDPOINT = "https://api.aiornot.com/v1/reports/voice"
        
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
            print(f'[*] Sending file to AIorNot API for analysis')
            with open(audio_path, "rb") as audio_file:
                files = {"file": audio_file}
                headers = {"Authorization": f"Bearer {API_KEY}"}
                
                # Make the API request with a 2 minute timeout as recommended
                response = requests.post(
                    VOICE_ENDPOINT,
                    headers=headers,
                    files=files,
                    timeout=120  # 2 minute timeout as recommended
                )
                
                # Check if the request was successful
                if response.status_code != 200:
                    error_msg = f"فشل في تحليل الصوت: {response.status_code}"
                    try:
                        error_details = response.json()
                        error_msg += f" - {error_details}"
                    except:
                        error_msg += f" - {response.text}"
                    
                    print(f'[!] API error: {error_msg}')
                    return jsonify({
                        'error': error_msg,
                        'success': False
                    }), 500
                
                # Parse the response
                api_response = response.json()
                print(f'[*] API response: {api_response}')
                
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
                
                print(f'[*] Final result to send to client: {response_data}')
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

# Ensure upload directory exists
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# AI Detection page route - supporting both URL formats


# Function to upload images to ImgBB for public URL
def upload_to_imgbb(image_data):
    """Upload an image to ImgBB and return the URL"""
    # Use the API key that works in the standalone example
    imgbb_api_key = os.environ.get('IMGBB_API_KEY')
    
    print(f'[*] Starting ImgBB upload with API key: {imgbb_api_key[:4]}...{imgbb_api_key[-4:]}')
    
    url = 'https://api.imgbb.com/1/upload'
    
    try:
        # For image data that comes from a form upload (bytes or file-like object)
        if isinstance(image_data, bytes) or hasattr(image_data, 'read'):
            print('[*] Handling direct file upload')
            # Use the exact structure that works in the standalone example
            files = {'image': image_data}
            data = {'key': imgbb_api_key}
            response = requests.post(url, data=data, files=files, timeout=30)
        
        # For base64-encoded string (from data URLs or already encoded images)
        elif isinstance(image_data, str):
            print('[*] Handling base64 string upload')
            # Clean data URL prefix if present
            if image_data.startswith('data:image'):
                print('[*] Cleaning data URL prefix')
                image_data = re.sub(r'^data:image/[^;]+;base64,', '', image_data)
            
            # Create temporary file from base64 data
            import io
            from PIL import Image
            print('[*] Converting base64 to image file')
            try:
                # Try to decode base64 and create a temporary image file
                img_data = base64.b64decode(image_data)
                img = Image.open(io.BytesIO(img_data))
                
                # Save to temporary file
                temp_path = os.path.join(UPLOAD_FOLDER, f'temp_img_{uuid.uuid4()}.png')
                os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                img.save(temp_path)
                
                # Upload using the file method that works
                with open(temp_path, 'rb') as img_file:
                    files = {'image': img_file}
                    data = {'key': imgbb_api_key}
                    response = requests.post(url, data=data, files=files, timeout=30)
                
                # Clean up temp file
                try:
                    os.remove(temp_path)
                except:
                    pass
                    
            except Exception as e:
                print(f'[!] Error processing image data: {str(e)}')
                # Fall back to direct string upload
                files = {'image': image_data}
                data = {'key': imgbb_api_key}
                response = requests.post(url, data=data, files=files, timeout=30)
        else:
            print(f'[!] Unsupported image data type: {type(image_data)}')
            return None
        
        print(f'[*] ImgBB API response status code: {response.status_code}')
        
        try:
            json_data = response.json()
            print(f'[*] ImgBB API response: {str(json_data)[:200]}')
            
            if response.status_code == 200 and json_data.get('success'):
                # Extract URL exactly as in working example
                return json_data['data']['url']
            else:
                error = json_data.get('error', {})
                error_message = error.get('message', 'Unknown error')
                print(f'[!] ImgBB API error: {error_message}')
                return None
                
        except ValueError as e:
            print(f'[!] Failed to parse ImgBB JSON response: {str(e)}')
            print(f'[!] Raw response: {response.text[:100]}')
            return None
        
        if json_data.get('success', False):
            return json_data['data']['url']
        else:
            print(f"[!] ImgBB upload failed: {json_data.get('error', {}).get('message', 'Unknown error')}")
            return None
    except Exception as e:
        print(f"[!] Error uploading to ImgBB: {str(e)}")
        return None

def download_image(url, save_path):
    """Download an image from URL to specified path"""
    try:
        response = requests.get(url, stream=True, timeout=15)
        response.raise_for_status()
        
        with open(save_path, 'wb') as img_file:
            for chunk in response.iter_content(chunk_size=8192):
                img_file.write(chunk)
        
        # Verify file was actually created and contains data
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            print(f"[✓] Successfully downloaded image to {save_path}")
            return True
        else:
            print(f"[!] Downloaded file is empty or does not exist: {save_path}")
            return False
    except Exception as e:
        print(f"[!] Error downloading image: {str(e)}")
        return False

def scrape_aiornot(image_url):
    """Detect AI-generated images using AI-or-Not API
    Following the exact structure from AI or Not official documentation
    """
    print(f'[*] Starting AI-or-Not detection for image: {image_url}')
    
    try:
        # Download the image to a temporary file
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        temp_image_path = os.path.join(UPLOAD_FOLDER, f"aiornot_{uuid.uuid4().hex}.jpg")
        
        print(f'[*] Downloading image to {temp_image_path}')
        download_success = download_image(image_url, temp_image_path)
        
        if not download_success or not os.path.exists(temp_image_path):
            return {
                'error': 'Failed to download image from specified URL',
                'success': False,
                'imageUrl': image_url
            }
        
        # Get API key from environment variable exactly as in the example
        API_KEY = os.environ.get('AIORNOT_API_KEY') or AIORNOT_API_KEY
        IMAGE_ENDPOINT = "https://api.aiornot.com/v2/image/sync"
        
        # Simple API call exactly as in the official documentation
        print(f'[*] Calling AI-or-Not API endpoint: {IMAGE_ENDPOINT}')
        with open(temp_image_path, "rb") as image_file:
            files = {"image": image_file}
            params = {
                "external_id": f"bahith-{uuid.uuid4().hex[:8]}"  # Optional tracking ID
            }
            
            resp = requests.post(
                IMAGE_ENDPOINT, 
                headers={"Authorization": f"Bearer {API_KEY}"},
                files=files,
                params=params
            )
            
            # Check for HTTP errors and raise them
            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                error_msg = f"Failed to analyze image: {resp.status_code} {resp.text}"
                print(f'[!] {error_msg}')
                return {
                    'error': error_msg,
                    'success': False,
                    'imageUrl': image_url
                }
        
        # Parse the response according to v2 API structure
        result = resp.json()
        print("[*] API Response received")
        print(json.dumps(result, indent=2))
        
        # Extract information from new response structure
        ai_generated_report = result.get('report', {}).get('ai_generated', {})
        
        # Check if AI verdict exists
        if ai_generated_report:
            verdict = ai_generated_report.get('verdict', '').lower()
            is_ai_generated = (verdict == 'ai')
            
            # Get confidence scores
            ai_confidence = ai_generated_report.get('ai', {}).get('confidence', 0.0)
            human_confidence = ai_generated_report.get('human', {}).get('confidence', 0.0)
            
            # Get generator information
            generators_dict = ai_generated_report.get('generator', {})
            
            # Find the generator with highest confidence
            generator = 'unknown'
            max_confidence = 0
            for gen_name, confidence in generators_dict.items():
                # Ensure the confidence value is a number, not a dictionary or other type
                if isinstance(confidence, (int, float)) and confidence > max_confidence:
                    max_confidence = confidence
                    generator = gen_name
                # If confidence is a dictionary (unexpected format), try to extract a usable value
                elif isinstance(confidence, dict) and 'confidence' in confidence:
                    conf_value = confidence.get('confidence', 0)
                    if conf_value > max_confidence:
                        max_confidence = conf_value
                        generator = gen_name
                    
            # Set Arabic verdict
            verdict_arabic = "منشأة بواسطة الذكاء الاصطناعي" if is_ai_generated else "الصورة حقيقية (غير منشأة بالذكاء الاصطناعي)"
        else:
            # Fallback to older structure or set defaults if structure is unexpected
            is_ai_generated = False
            ai_confidence = 0.0
            human_confidence = 1.0
            generator = 'unknown'
            verdict_arabic = "لا يمكن تحديد مصدر الصورة"
            print("[!] Warning: Unexpected API response structure")
        
        # Return the simplified result format
        return {
            "verdict": verdict_arabic,
            "confidence_ai": ai_confidence,
            "confidence_human": human_confidence,
            "generator": generator,
            "rawText": json.dumps(result, indent=2),
            "imageUrl": image_url,
            "is_ai": is_ai_generated,
            "success": True,
            "source": 'AI-or-Not'
        }
        
    except Exception as e:
        print(f'[!] Error in AI-or-Not API call: {str(e)}')
        traceback.print_exc()
        return {
            'error': f'Error during analysis: {str(e)}',
            'success': False,
            'imageUrl': image_url
        }
    finally:
        # Clean up temp file
        try:
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)
                print(f'[*] Removed temporary file: {temp_image_path}')
        except Exception as e:
            print(f'[!] Error removing temp file: {str(e)}')
        print('[*] AI-or-Not detection (Model 2) completed')

def scrape_thehive(image_url):
    """Detect AI-generated images using Sightengine API (Model 1)"""
    print(f'[*] Starting Sightengine detection (Model 1) for image: {image_url}')
    
    # Download the image to a temporary file
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    temp_image_path = os.path.join(UPLOAD_FOLDER, f"sightengine_{uuid.uuid4().hex}.jpg")
    
    print(f'[*] Downloading image to {temp_image_path}')
    download_success = download_image(image_url, temp_image_path)
    
    if not download_success or not os.path.exists(temp_image_path):
        return {
            'rawText': f'\u062e\u0637\u0623: \u0641\u0634\u0644 \u062a\u062d\u0645\u064a\u0644 \u0627\u0644\u0635\u0648\u0631\u0629 \u0645\u0646 \u0627\u0644\u0631\u0627\u0628\u0637 \u0627\u0644\u0645\u062d\u062f\u062f',
            'source': 'Error',
            'error': 'Failed to download image',
            'imageUrl': image_url
        }
    
    print(f'[*] Image downloaded successfully to {temp_image_path}')
    
    try:
        # Use Sightengine API
        print('[*] Calling Sightengine API...')
        import requests

        resp = requests.post(
            "https://api.sightengine.com/1.0/check.json",
            files={"media": open(temp_image_path, "rb")},
            data={
              "models":    "genai",
              "api_user":  "1797817014",
              "api_secret":"A4Y8VjQbRGgRsxwDSkMCQSh3tU4VTTcG"
            },
            timeout=30
        )

        result = resp.json()
        if resp.status_code != 200 or result.get("status") != "success":
            return {
              'rawText': f"Error {resp.status_code}: {result}",
              'source': 'Model-1',
              'error': result,
              'imageUrl': image_url
            }

        score = result['type']['ai_generated']
        
        # For consistency with the other model, calculate human score as inverse of AI score
        ai_confidence = float(score)
        human_confidence = 1.0 - ai_confidence
        
        # Ensure confidence values are between 0 and 1
        ai_confidence = max(0.0, min(ai_confidence, 1.0))
        human_confidence = max(0.0, min(human_confidence, 1.0))
        
        # Set verdict text based on AI score
        is_ai = ai_confidence > 0.5
        verdict_text = "منشأة بواسطة الذكاء الاصطناعي" if is_ai else "الصورة حقيقية (غير منشأة بالذكاء الاصطناعي)"
        
        # Format result to match the other function's structure for frontend compatibility
        return {
            "verdict": verdict_text,
            "confidence_ai": ai_confidence,
            "confidence_human": human_confidence,
            "generator": "unknown",  # Sightengine doesn't provide generator info
            "quality_ok": True,     # No quality info, assume OK
            "nsfw": False,          # No NSFW info
            'source': 'Model-1',
            'rawText': json.dumps(result, indent=2),
            'imageUrl': image_url,
            'is_ai': is_ai,
            'success': True
        }
            
    except Exception as e:
        print(f'[!] Error in Sightengine API call: {str(e)}')
        traceback.print_exc()
        return {
            'error': f'\u062e\u0637\u0623 \u0623\u062b\u0646\u0627\u0621 \u0627\u0644\u062a\u062d\u0644\u064a\u0644: {str(e)}',
            'rawText': f'\u062e\u0637\u0623 \u0623\u062b\u0646\u0627\u0621 \u0627\u0644\u062a\u062d\u0644\u064a\u0644: {str(e)}',
            'source': 'Model-1',
            'success': False,
            'imageUrl': image_url
        }
    finally:
        # Clean up temp file
        try:
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)
                print(f'[*] Removed temporary file: {temp_image_path}')
        except Exception as e:
            print(f'[!] Error removing temp file: {str(e)}')
        print('[*] Sightengine detection (Model 1) completed')

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
        data = request.get_json()
        if not data or not data.get('image_url'):
            return jsonify({'error': 'image_url required'}), 200

        image_url = data['image_url']
        print(f'[*] Provenance API called with image_url: {image_url}')

        # Check if required dependencies are available
        if not BS4_AVAILABLE:
            return jsonify({
                'first_seen': None,
                'timeline': [],
                'related_images': [],
                'stats': {'checked': 0, 'with_dates': 0},
                'note': 'BeautifulSoup4 dependency not available. Please install: pip install beautifulsoup4'
            }), 200

        # Get SerpAPI key
        serpapi_key = os.environ.get('SERPAPI_API_KEY', SERPAPI_API_KEY)
        
        if not serpapi_key:
            return jsonify({
                'first_seen': None,
                'timeline': [],
                'related_images': [],
                'stats': {'checked': 0, 'with_dates': 0},
                'note': 'SerpAPI key not configured'
            }), 200

        try:
            print(f'[*] Calling SerpAPI for reverse image search: {image_url}')
            
            # SerpAPI parameters for Google Reverse Image Search
            params = {
                'engine': 'google_reverse_image',
                'image_url': image_url,
                'api_key': serpapi_key,
                'hl': 'en',
                'gl': 'us'
            }
            
            response = requests.get('https://serpapi.com/search.json', params=params, timeout=30)
            
            if response.status_code != 200:
                print(f'[!] SerpAPI error: {response.status_code}')
                return jsonify({
                    'first_seen': None,
                    'timeline': [],
                    'related_images': [],
                    'stats': {'checked': 0, 'with_dates': 0},
                    'note': f'SerpAPI error: {response.status_code}'
                }), 200
            
            serp_data = response.json()
            print(f'[*] SerpAPI response received')
            
            # Check for errors in response
            if 'error' in serp_data:
                print(f'[!] SerpAPI error: {serp_data["error"]}')
                return jsonify({
                    'first_seen': None,
                    'timeline': [],
                    'related_images': [],
                    'stats': {'checked': 0, 'with_dates': 0},
                    'note': f'SerpAPI error: {serp_data.get("error")}'
                }), 200

            # Collect candidate links and related images from SerpAPI response
            candidate_urls = []
            related_images = []
            
            from urllib.parse import urlparse
            
            # Process image results for related images gallery
            image_results = serp_data.get('image_results', [])
            print(f'[*] Found {len(image_results)} image results')
            
            for img in image_results[:30]:  # Limit to 30 images
                if isinstance(img, dict):
                    thumbnail = img.get('thumbnail')
                    original = img.get('original')
                    source_url = img.get('source')
                    link = img.get('link')
                    position = img.get('position', '')
                    title = img.get('title', '')
                    
                    # Add link to candidate URLs for timeline
                    if link and link.startswith('http'):
                        candidate_urls.append(link)
                    
                    if thumbnail or original:
                        # Extract source domain from link (the page URL where image was found)
                        if link:
                            try:
                                parsed = urlparse(link)
                                source_domain = parsed.netloc or 'مصدر غير معروف'
                            except:
                                source_domain = 'مصدر غير معروف'
                        else:
                            source_domain = 'مصدر غير معروف'
                        
                        related_images.append({
                            'thumbnail': thumbnail or original,
                            'original': original or thumbnail,
                            'link': link or source_url or original,
                            'source': source_domain,
                            'title': title
                        })
            
            # Process inline images
            inline_images = serp_data.get('inline_images', [])
            print(f'[*] Found {len(inline_images)} inline images')
            
            for img in inline_images[:20]:  # Limit to 20
                if isinstance(img, dict):
                    thumbnail = img.get('thumbnail')
                    original = img.get('original')
                    link = img.get('link')
                    source_url = img.get('source')
                    title = img.get('title', '')
                    
                    # Add link to candidate URLs for timeline
                    if link and link.startswith('http'):
                        candidate_urls.append(link)
                    
                    if thumbnail or original:
                        # Avoid duplicates
                        if not any(ri['original'] == (original or thumbnail) for ri in related_images):
                            # Extract source domain
                            if link:
                                try:
                                    parsed = urlparse(link)
                                    source_domain = parsed.netloc or 'مصدر غير معروف'
                                except:
                                    source_domain = 'مصدر غير معروف'
                            else:
                                source_domain = 'مصدر غير معروف'
                            
                            related_images.append({
                                'thumbnail': thumbnail or original,
                                'original': original or thumbnail,
                                'link': link or source_url or original,
                                'source': source_domain,
                                'title': title
                            })
            
            # Get URLs from visual matches and organic results
            for key in ['visual_matches', 'organic_results']:
                items = serp_data.get(key, [])
                print(f'[*] Found {len(items)} {key}')
                
                for item in items:
                    if isinstance(item, dict):
                        url = item.get('link') or item.get('url')
                        if url and url.startswith('http'):
                            candidate_urls.append(url)

            # De-duplicate URLs while preserving order, limit to ~18 URLs
            seen = set()
            unique_urls = []
            for url in candidate_urls:
                if url not in seen and len(unique_urls) < 18:
                    seen.add(url)
                    unique_urls.append(url)
            
            print(f'[*] Found {len(candidate_urls)} total URLs, {len(unique_urls)} unique URLs')
            print(f'[*] Found {len(related_images)} related images')
            
            # Limit related images to 24 items
            related_images = related_images[:24]

            # Process URLs in parallel to extract dates and metadata
            print(f'[*] Processing {len(unique_urls)} URLs for provenance...')
            timeline_results = process_urls_for_provenance(unique_urls)
            print(f'[*] Processed {len(timeline_results)} timeline results')

            # Sort timeline by date (OLDEST FIRST → NEWEST LAST, then undated items)
            dated_items = [item for item in timeline_results if item.get('published_at')]
            undated_items = [item for item in timeline_results if not item.get('published_at')]

            # Sort dated items by published_at in ascending order (oldest to newest)
            dated_items.sort(key=lambda x: x['published_at'] or '9999-12-31T23:59:59Z')

            # Timeline: oldest dated items first, newest dated items last, then undated
            timeline = dated_items + undated_items

            # First seen = first dated entry
            first_seen = dated_items[0] if dated_items else None

            # Stats
            stats = {
                'checked': len(timeline_results),
                'with_dates': len(dated_items)
            }

            return jsonify({
                'first_seen': first_seen,
                'timeline': timeline,
                'related_images': related_images,
                'stats': stats,
                'note': None
            }), 200

        except requests.exceptions.Timeout:
            print(f'[!] SerpAPI request timeout')
            return jsonify({
                'first_seen': None,
                'timeline': [],
                'related_images': [],
                'stats': {'checked': 0, 'with_dates': 0},
                'note': 'Request timeout. Please try again.'
            }), 200
        except Exception as e:
            print(f'[!] SerpAPI error: {str(e)}')
            traceback.print_exc()
            return jsonify({
                'first_seen': None,
                'timeline': [],
                'related_images': [],
                'stats': {'checked': 0, 'with_dates': 0},
                'note': f'Error: {str(e)[:200]}'
            }), 200

    except Exception as e:
        print(f'[!] Error in provenance API: {str(e)}')
        traceback.print_exc()
        return jsonify({
            'first_seen': None,
            'timeline': [],
            'related_images': [],
            'stats': {'checked': 0, 'with_dates': 0},
            'note': f'Server error: {str(e)}'
        }), 200

def process_urls_for_provenance(urls):
    """Process URLs in parallel to extract dates and metadata"""
    from urllib.parse import urlparse
    import re
    from datetime import datetime

    def extract_page_info(url):
        """Extract title, date, and metadata from a single URL"""
        try:
            # Check if BeautifulSoup is available
            if not BS4_AVAILABLE:
                return {
                    'url': url,
                    'domain': urlparse(url).netloc,
                    'title': 'BeautifulSoup not available',
                    'published_at': None,
                    'confidence': 0.0,
                    'evidence': ['missing_dependency:beautifulsoup4']
                }

            # Set up session with retries
            session = requests.Session()
            retry_strategy = Retry(
                total=2,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)

            # Fetch page with timeout
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = session.get(url, headers=headers, timeout=(5, 10))
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            domain = urlparse(url).netloc

            # Extract title
            title = ''
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text().strip()

            # Try og:title as fallback
            if not title:
                og_title = soup.find('meta', property='og:title')
                if og_title:
                    title = og_title.get('content', '').strip()

            # Fallback to domain if no title
            if not title:
                title = domain

            # Extract published date with evidence tracking
            published_at = None
            confidence = 0.0
            evidence = []

            # High confidence sources
            meta_published = soup.find('meta', property='article:published_time')
            if meta_published and meta_published.get('content'):
                date_str = meta_published.get('content')
                parsed_date = parse_date_string(date_str)
                if parsed_date:
                    published_at = parsed_date
                    confidence = 0.95
                    evidence.append('meta:article:published_time')

            # Try JSON-LD structured data (very high confidence)
            if not published_at:
                json_ld_scripts = soup.find_all('script', type='application/ld+json')
                for script in json_ld_scripts:
                    try:
                        data = json.loads(script.string)
                        # Handle both single object and array
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            date_published = item.get('datePublished') or item.get('dateCreated') or item.get('uploadDate')
                            if date_published:
                                parsed_date = parse_date_string(date_published)
                                if parsed_date:
                                    published_at = parsed_date
                                    confidence = 0.90
                                    evidence.append('jsonld:datePublished')
                                    break
                        if published_at:
                            break
                    except:
                        continue

            # Medium-high confidence sources
            if not published_at:
                selectors = [
                    ('meta[property="og:published_time"]', 'meta:og:published_time', 0.85),
                    ('meta[property="article:published"]', 'meta:article:published', 0.85),
                    ('meta[name="pubdate"]', 'meta:pubdate', 0.80),
                    ('meta[name="publishdate"]', 'meta:publishdate', 0.80),
                    ('meta[name="date"]', 'meta:date', 0.75),
                    ('meta[itemprop="datePublished"]', 'meta:datePublished', 0.80),
                    ('meta[name="article.published"]', 'meta:article.published', 0.80),
                    ('time[datetime]', 'time:datetime', 0.75),
                    ('time[pubdate]', 'time:pubdate', 0.75),
                    ('[itemprop="datePublished"]', 'itemprop:datePublished', 0.70),
                ]

                for selector, evidence_name, conf in selectors:
                    element = soup.select_one(selector)
                    if element:
                        date_str = element.get('content') or element.get('datetime') or element.get_text()
                        if date_str:
                            parsed_date = parse_date_string(date_str.strip())
                            if parsed_date:
                                published_at = parsed_date
                                confidence = conf
                                evidence.append(evidence_name)
                                break
            
            # Try to extract from URL path (e.g., /2024/01/15/article)
            if not published_at:
                url_date_match = re.search(r'/(\d{4})/(\d{1,2})/(\d{1,2})/', url)
                if url_date_match:
                    try:
                        year, month, day = url_date_match.groups()
                        date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        parsed_date = parse_date_string(date_str)
                        if parsed_date:
                            published_at = parsed_date
                            confidence = 0.65
                            evidence.append('url:path_date')
                    except:
                        pass
            
            # Search for date patterns in text
            if not published_at:
                text_content = soup.get_text()[:2000]  # First 2000 chars
                # Look for ISO dates
                date_patterns = [
                    r'\b(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',
                    r'\b(\d{4}-\d{2}-\d{2})',
                    r'\b(\d{1,2}/\d{1,2}/\d{4})',
                ]
                for pattern in date_patterns:
                    match = re.search(pattern, text_content)
                    if match:
                        date_str = match.group(1)
                        parsed_date = parse_date_string(date_str)
                        if parsed_date:
                            published_at = parsed_date
                            confidence = 0.50
                            evidence.append('text:pattern_match')
                            break

            return {
                'url': url,
                'domain': domain,
                'title': title[:200],  # Limit title length
                'published_at': published_at,
                'confidence': confidence,
                'evidence': evidence
            }

        except requests.exceptions.RequestException as e:
            return {
                'url': url,
                'domain': urlparse(url).netloc,
                'title': f'Error: {str(e)[:50]}',
                'published_at': None,
                'confidence': 0.0,
                'evidence': [f'fetch_error:{str(e)[:30]}']
            }
        except Exception as e:
            return {
                'url': url,
                'domain': urlparse(url).netloc,
                'title': f'Parse error: {str(e)[:50]}',
                'published_at': None,
                'confidence': 0.0,
                'evidence': [f'parse_error:{str(e)[:30]}']
            }

    # Process URLs in parallel with ThreadPoolExecutor
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_to_url = {executor.submit(extract_page_info, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url, timeout=60):
            try:
                result = future.result(timeout=10)
                results.append(result)
            except concurrent.futures.TimeoutError:
                url = future_to_url[future]
                results.append({
                    'url': url,
                    'domain': urlparse(url).netloc,
                    'title': 'Timeout error',
                    'published_at': None,
                    'confidence': 0.0,
                    'evidence': ['fetch_error:timeout']
                })
            except Exception as e:
                url = future_to_url[future]
                results.append({
                    'url': url,
                    'domain': urlparse(url).netloc,
                    'title': f'Error: {str(e)[:50]}',
                    'published_at': None,
                    'confidence': 0.0,
                    'evidence': [f'fetch_error:{str(e)[:30]}']
                })

    return results

def parse_date_string(date_str):
    """Parse date string and return ISO 8601 UTC format"""
    try:
        if not date_str:
            return None
        
        # Clean the date string
        date_str = str(date_str).strip()

        # Try dateparser first if available
        if DATEPARSER_AVAILABLE:
            parsed = dateparser.parse(date_str)
            if parsed:
                # Convert to UTC and return ISO format
                utc_dt = parsed.replace(tzinfo=None) if parsed.tzinfo is None else parsed.astimezone().replace(tzinfo=None)
                return utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Fallback to basic datetime parsing with more formats
        from datetime import datetime
        formats = [
            # ISO formats
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            # Common formats
            '%d %B %Y',  # 15 January 2024
            '%B %d, %Y',  # January 15, 2024
            '%d %b %Y',  # 15 Jan 2024
            '%b %d, %Y',  # Jan 15, 2024
            # Slash formats
            '%m/%d/%Y',
            '%d/%m/%Y',
            '%Y/%m/%d',
            # Dash formats
            '%d-%m-%Y',
            '%m-%d-%Y',
            # Others
            '%Y%m%d',
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str[:50], fmt)  # Limit to first 50 chars
                return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            except ValueError:
                continue
        
        # Try to extract just year-month-day if format is complex
        import re
        simple_date = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
        if simple_date:
            try:
                dt = datetime.strptime(simple_date.group(0), '%Y-%m-%d')
                return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            except:
                pass

        return None
    except Exception:
        return None

if __name__ == '__main__':
    # تشغيل التطبيق على جميع الواجهات (0.0.0.0) بدلاً من localhost فقط
    # هذا يتيح الوصول إلى التطبيق من أجهزة أخرى على نفس الشبكة
    app.run(host='0.0.0.0', port=5000, debug=True)