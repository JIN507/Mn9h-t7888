import os
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
import os
from flask import Flask, render_template, request, url_for, redirect, flash, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from datetime import datetime
import uuid
import urllib.request
import asyncio
import hashlib
import time

# Import requests for direct API calls
import traceback

# AI Detection imports
from playwright.sync_api import sync_playwright

# Initialize Flask
app = Flask(__name__)
CORS(app)

# Load environment variables
load_dotenv()

# Config
UPLOAD_FOLDER = 'uploads'
# Create uploads directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# Hard-coded IMGBB API key (you should move this to .env file in production)
IMGBB_API_KEY = '0a85906528efe824b2563d2ae563b68f'
# AI or Not API Key for audio verification (updated from user input)
AIORNOT_API_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjVjNDEyZDIxLTQ2MWUtNDc2My05ODVmLWQzZjI2NmY5Y2JlMCIsInVzZXJfaWQiOiI1YzQxMmQyMS00NjFlLTQ3NjMtOTg1Zi1kM2YyNjZmOWNiZTAiLCJhdWQiOiJhY2Nlc3MiLCJleHAiOjAuMH0.w-D35bZii8-wpZZig397pzfHUReAFnBTuKSQBjOI7cA'
# Setting environment variable as in the example
os.environ['AIORNOT_API_KEY'] = AIORNOT_API_KEY
# The exact endpoints from the API docs
VOICE_ENDPOINT = "https://api.aiornot.com/v1/reports/voice"
IMAGE_ENDPOINT = "https://api.aiornot.com/v1/reports/image"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024 * 1024  # 256MB max upload
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Create audio upload folder if it doesn't exist - inside static for web access
AUDIO_UPLOAD_FOLDER = os.path.join('static', 'uploads', 'audio')
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
                _, buffer = cv2.imencode('.jpg', frame)
                img_str = base64.b64encode(buffer).decode('utf-8')
                frames.append({
                    'data': f'data:image/jpeg;base64,{img_str}',
                    'timestamp': frame_count / fps if fps > 0 else 0
                })
            
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

ZENSERP_API_KEY = "54f49710-57fb-11f0-b038-cf26fb8f0bad"

def scrape_reverse_search(image_url):
    try:
        print(f'[*] Starting reverse image search for: {image_url}')
        
        # Generate search links for different engines
        search_links = search_images(image_url)
        
        # Use ZenSerp API for direct search results
        zenserp_key = os.getenv('ZENSERP_API_KEY') or ZENSERP_API_KEY
        headers = {'apikey': zenserp_key}
        params = {'image_url': image_url}
        
        try:
            print('[*] Querying ZenSerp API for reverse image search')
            response = requests.get(
                'https://app.zenserp.com/api/v2/search',
                headers=headers,
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                organic = data.get('reverse_image_results', {}).get('organic', [])
                links = [r['url'] for r in organic if r.get('url')]
                
                print(f'[*] Found {len(links)} results from ZenSerp API')
                return {
                    'links': links,
                    'search_urls': search_links,
                    'source': 'ZenSerp API',
                    'success': True
                }
            else:
                print(f'[!] ZenSerp API error: {response.status_code}')
                return {
                    'links': [],
                    'search_urls': search_links,
                    'source': 'Search Engine Links',
                    'error': f'ZenSerp API error: {response.status_code}',
                    'success': True
                }
        
        except Exception as e:
            print(f'[!] Error with ZenSerp API: {e}')
            traceback.print_exc()
            return {
                'links': [],
                'search_urls': search_links,
                'source': 'Search Engine Links (API Failed)',
                'error': str(e),
                'success': True
            }

    except Exception as e:
        print(f'[!] Error in image source search: {e}')
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video')
def video_page():
    """Render the video frame extraction page"""
    return render_template('video.html')

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

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/ai_detection')
@app.route('/ai-detection')
def ai_detection():
    return render_template('ai_detection.html')

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

@app.route('/image-source-search')
def image_source_search():
    return render_template('image_source_search.html')

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

@app.route('/audio-verification')
def audio_verification():
    return render_template('audio_verification.html')

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
        API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjVjNDEyZDIxLTQ2MWUtNDc2My05ODVmLWQzZjI2NmY5Y2JlMCIsInVzZXJfaWQiOiI1YzQxMmQyMS00NjFlLTQ3NjMtOTg1Zi1kM2YyNjZmOWNiZTAiLCJhdWQiOiJhY2Nlc3MiLCJleHAiOjAuMH0.w-D35bZii8-wpZZig397pzfHUReAFnBTuKSQBjOI7cA"
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
@app.route('/ai_detection')
@app.route('/ai-detection')
def ai_detection_page():
    """Render the AI detection page"""
    return render_template('ai_detection.html')

# Function to upload images to ImgBB for public URL
def upload_to_imgbb(image_data):
    """Upload an image to ImgBB and return the URL"""
    # Use the API key that works in the standalone example
    imgbb_api_key = os.environ.get('IMGBB_API_KEY', '0a85906528efe824b2563d2ae563b68f')
    
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
def scrape_faceonlive(image_path):
    """Detect if an image is AI-generated using FaceOnLive's API"""
    print(f"[*] Starting FaceOnLive scraper with image: {image_path}")
    try:
        with sync_playwright() as playwright:
            # Use more forceful browser launch options
            print('[*] Launching browser with visible UI...')
            browser = playwright.chromium.launch(
                headless=False,  # Ensure we're not in headless mode
                args=['--start-maximized', '--disable-extensions', '--no-sandbox']
            )
            context = browser.new_context(viewport={'width': 1280, 'height': 800})
            print('[DEBUG] Browser launched successfully!')
            page = context.new_page()

            print("[*] Opening FaceOnLive website...")
            page.goto("https://faceonlive.com/projects/deepfake-detection-sdk/")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)  # Extra wait to ensure the page is fully loaded

            print("[*] Getting iframe...")
            frame_element = page.query_selector("iframe")
            if not frame_element:
                print("[!] Failed to find iframe")
                return {
                    'error': 'لم يتم العثور على الإطار في موقع FaceOnLive',
                    'success': False
                }
            
            frame = frame_element.content_frame()

            print("[*] Uploading image...")
            file_input = frame.locator('input[type="file"]')
            file_input.set_input_files(image_path)

            print("[*] Giving Gradio some time to attach event handlers...")
            time.sleep(2)

            print("[*] Clicking Detect button...")
            detect_button = frame.locator('button#component-9')
            if not detect_button.count():
                print("[!] Failed to find detect button")
                return {
                    'error': 'لم يتم العثور على زر الكشف',
                    'success': False
                }
            detect_button.click()

            print("[*] Waiting for result...")
            frame.wait_for_selector('h2[data-testid="label-output-value"]', timeout=120000)

            # Extract results
            print("[*] Extracting main results...")
            headers = frame.locator('h2[data-testid="label-output-value"]')
            main_results = []
            for i in range(headers.count()):
                text = headers.nth(i).inner_text()
                main_results.append(text)
                print(f"- {text}")

            print("[*] Extracting confidence scores...")
            confidence_data = {}
            # Give time for all confidence scores to fully render
            page.wait_for_timeout(2000)
            
            # Improved JavaScript extraction of confidence scores for reliability
            print("[*] Using JavaScript to extract confidence scores...")
            js_extracted_scores = frame.evaluate('''() => {
                let scores = {};
                // Look for confidence scores in various formats
                document.querySelectorAll('.confidence-set, .score-item, dt, .score-label').forEach(item => {
                    let label = '';
                    let score = '';
                    
                    // Check if this is a containing element with both label and score
                    if (item.querySelector('dt,dd')) {
                        label = item.querySelector('dt')?.innerText || '';
                        score = item.querySelector('dd')?.innerText || '';
                    }
                    // Or if it's just a label element with a next sibling as score
                    else if (item.nextElementSibling && 
                            (item.nextElementSibling.tagName === 'DD' || 
                             item.nextElementSibling.classList.contains('score-value'))) {
                        label = item.innerText || '';
                        score = item.nextElementSibling.innerText || '';
                    }
                    
                    if (label && score) {
                        scores[label.trim()] = score.trim();
                    }
                });
                
                return scores;
            }''')
            
            # Use the extracted scores or fall back to the regular method
            if js_extracted_scores and len(js_extracted_scores) > 0:
                confidence_data = js_extracted_scores
                print(f"[*] Extracted {len(confidence_data)} scores via JavaScript: {confidence_data}")
            else:
                # Fallback to traditional method
                print("[*] Falling back to traditional score extraction...")
                buttons = frame.locator('button.confidence-set, .score-item')
                for i in range(buttons.count()):
                    try:
                        model = buttons.nth(i).locator('dt').inner_text()
                        confidence = buttons.nth(i).locator('dd').inner_text()
                        confidence_data[model] = confidence
                        print(f"{model}: {confidence}")
                    except Exception as item_error:
                        print(f"[!] Error extracting score item {i}: {str(item_error)}")

            # Also take a screenshot for debugging
            screenshot_path = os.path.join(UPLOAD_FOLDER, f"faceonlive_result_{uuid.uuid4().hex}.png")
            page.screenshot(path=screenshot_path)
            print(f"[*] Screenshot saved to {screenshot_path}")
            
            # Process verdict and confidence
            verdict = main_results[0] if main_results else "Unknown"
            is_fake = "fake" in verdict.lower() or "deepfake" in verdict.lower() or "ai" in verdict.lower()
            
            # Enhanced results with more context for frontend
            results = {
                'success': True,
                'verdict': verdict,
                'is_fake': is_fake,
                'confidence_scores': confidence_data,
                'main_results': main_results,
                'source': 'FaceOnLive',
                'rawText': f"Verdict: {verdict}\n" + "\n".join([f"{k}: {v}" for k, v in confidence_data.items()]),
                'imageUrl': image_path  # Return the path to the uploaded image
            }
            
            print(f"[*] Final results: {results}")
            
            # Make sure we actually got results - if not, return an error
            if not confidence_data and (not main_results or main_results[0] == "No clear verdict found"):
                print("[!] No valid results extracted after detection completed")
                error_screenshot = os.path.join(UPLOAD_FOLDER, f"faceonlive_no_results_{uuid.uuid4().hex}.png")
                page.screenshot(path=error_screenshot)
                
                return {
                    'rawText': 'خطأ: لم يتم العثور على نتائج صالحة',
                    'source': 'Error',
                    'error': 'No valid results found',
                    'success': False,
                    'imageUrl': image_path,
                    'screenshot': error_screenshot
                }
            
            # Cleanup with error handling
            try:
                context.close()
                browser.close()
                print("[*] Browser closed successfully")
            except Exception as close_error:
                print(f"[!] Error closing browser: {str(close_error)}")
            
            # Take a final screenshot before closing everything
            try:
                final_screenshot = os.path.join(UPLOAD_FOLDER, f"faceonlive_final_{uuid.uuid4().hex}.png")
                page.screenshot(path=final_screenshot)
                print(f"[*] Final screenshot: {final_screenshot}")
            except Exception as screenshot_error:
                print(f"[!] Failed to take final screenshot: {str(screenshot_error)}")
                
            # Keep the image for debugging in case of issues
            # If you want to remove it later, uncomment the code below:
            # try:
            #     if os.path.exists(image_path):
            #         os.remove(image_path)
            #         print(f"[*] Removed temporary file: {image_path}")
            # except Exception as e:
            #     print(f"[!] Failed to remove temp file: {str(e)}")
                
            return results
    except Exception as e:
        print(f"[!] Error in FaceOnLive scraper: {str(e)}")
        traceback.print_exc()
        
        # Attempt to take an error screenshot
        error_screenshot = None
        try:
            error_screenshot = os.path.join(UPLOAD_FOLDER, f"faceonlive_error_{uuid.uuid4().hex}.png")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                page = browser.new_page()
                page.goto("https://faceonlive.com/projects/deepfake-detection-sdk/")
                page.screenshot(path=error_screenshot)
                browser.close()
                print(f"[*] Error screenshot saved: {error_screenshot}")
        except Exception as screenshot_error:
            print(f"[!] Could not take error screenshot: {str(screenshot_error)}")
        
        return {
            'error': f'خطأ أثناء التحليل: {str(e)}',
            'rawText': f'خطأ أثناء التحليل: {str(e)}',
            'source': 'Error',
            'success': False,
            'imageUrl': image_path,
            'screenshot': error_screenshot if error_screenshot else None
        }

# Original functions restored with proper route decorators
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

if __name__ == '__main__':
    # تشغيل التطبيق على جميع الواجهات (0.0.0.0) بدلاً من localhost فقط
    # هذا يتيح الوصول إلى التطبيق من أجهزة أخرى على نفس الشبكة
    app.run(host='0.0.0.0', port=5000, debug=True)