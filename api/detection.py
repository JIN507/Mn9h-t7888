"""AI-detection endpoints: image, audio, text, video."""
import base64
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime

import requests
from flask import Blueprint, current_app, jsonify, request, url_for
from werkzeug.utils import secure_filename

from providers.imgbb import upload_to_imgbb
from services.detection_service import (scrape_aiornot, scrape_thehive,
                                        scrape_faceonlive, persist_analysis,
                                        find_cached_analysis)
from services.media_service import (UPLOAD_FOLDER, AUDIO_UPLOAD_FOLDER,
                                    allowed_file, allowed_audio_file,
                                    compute_hashes, compute_text_hash)

from extensions import limiter, SPEND_LIMIT

logger = logging.getLogger(__name__)
bp = Blueprint('detection', __name__)


@bp.route('/ai-detect-thehive', methods=['POST'])
@limiter.limit(SPEND_LIMIT)
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
        logger.info(f"Error in AI detection: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': f'حدث خطأ: {str(e)}', 'source': 'TheHive.ai'}), 500

# First implementation of ai_detect_faceonlive has been removed to prevent duplicate endpoint errors
# The updated implementation is at line ~1458

@bp.route('/api/ai-detection', methods=['POST'])
@limiter.limit(SPEND_LIMIT)
def api_ai_detection():
    """API endpoint for AI image detection using TheHive.ai or FaceOnLive"""
    logger.info('[*] Received request to /api/ai-detection endpoint')
    logger.info('[DEBUG] Starting API endpoint for AI detection')
    
    # Check if image file is provided
    if 'image' not in request.files:
        logger.info('[!] No image file in request')
        return jsonify({
            'error': 'لم يتم العثور على صورة في الطلب',
            'success': False
        }), 400
    
    # Get the service from the form data - thehive (Model 1) or aiornot (Model 2)
    service = request.form.get('service', 'thehive')
    logger.info(f'[*] Service requested: {service}')
    
    # Create upload directory if it doesn't exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # Get the image file from the request
    image_file = request.files['image']
    if image_file.filename == '':
        logger.info('[!] Empty filename')
        return jsonify({
            'error': 'اسم الملف فارغ',
            'success': False
        }), 400
    
    # Save the image to a temporary file
    filename = secure_filename(image_file.filename)
    temp_path = os.path.join(UPLOAD_FOLDER, filename)
    try:
        image_file.save(temp_path)
        logger.info(f'[✓] Image saved temporarily to {temp_path}')
    except Exception as e:
        logger.info(f'[!] Error saving file: {str(e)}')
        return jsonify({
            'error': f'خطأ في حفظ الملف: {str(e)}',
            'success': False
        }), 500
    
    try:
        result = None

        # SHA-256 + pHash on every upload; serve cache hits unless forced
        media_hash, media_phash = compute_hashes(temp_path)
        force = str(request.form.get('force', '')).lower() in ('1', 'true', 'yes')
        if not force:
            cached = find_cached_analysis('ai_image', service, media_hash)
            if cached and cached.detailed_results:
                logger.info('Detection cache hit: service=%s hash=%s',
                            service, media_hash)
                payload = dict(cached.detailed_results)
                payload['cached'] = True
                payload['analysis_id'] = cached.id
                return jsonify(payload)

        # Upload file to imgbb to get URL for both services
        logger.info('[*] Uploading image to ImgBB...')
        with open(temp_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
            
        image_url = upload_to_imgbb(image_data)
        if not image_url:
            logger.info('[!] Failed to get image URL from ImgBB')
            return jsonify({
                'error': 'فشل في رفع الصورة للتحليل',
                'success': False
            }), 500
            
        logger.info(f'[✓] Image uploaded to ImgBB: {image_url}')
        
        # Process based on selected service
        if service.lower() == 'thehive':
            # Model 1: Sightengine API (formerly TheHive.ai)
            logger.info('[*] Processing with Model 1 (Sightengine API)')
            
            # Call the Sightengine API with the image URL
            logger.info('[*] Starting Sightengine scraper...')
            result = scrape_thehive(image_url)
            logger.info('Sightengine scraper (Model 1) returned: %s', result)
            
        elif service.lower() == 'aiornot':
            # Model 2: AI-or-Not API
            logger.info('[*] Processing with Model 2 (AI-or-Not API)')
            
            # Call the AI-or-Not API with the image URL
            logger.info('[*] Starting AI-or-Not scraper...')
            result = scrape_aiornot(image_url)
            logger.info('AI-or-Not scraper (Model 2) returned: %s', result)
            
        elif service.lower() == 'faceonlive':
            # For FaceOnLive, we pass the local file path directly
            logger.info('[*] Processing with FaceOnLive service')
            
            # Add a print statement to verify we're calling the scraper
            logger.info('About to call FaceOnLive scraper with path: %s', temp_path)
            
            # Explicitly wait to give time to debug
            logger.info('[DEBUG] Waiting 2 seconds before starting scraper...')
            time.sleep(2)

            result = scrape_faceonlive(temp_path)
            logger.info('FaceOnLive scraper returned: %s', result)
            
        else:
            logger.info(f'[!] Unknown service: {service}')
            return jsonify({
                'error': 'نوع خدمة غير معروف',
                'success': False
            }), 400
        
        if 'error' in result:
            logger.info(f'[!] Error in scraper: {result["error"]}')
            return jsonify({
                'error': result['error'],
                'success': False
            }), 500
            
        logger.info(f'[✓] Successfully obtained results from {service}')

        # Persist every detection -> Analysis (cache source for repeats)
        from auth import get_current_user
        user = get_current_user()
        analysis_id = persist_analysis(
            user.id if user else None, 'ai_image', service, result,
            media_hash=media_hash, media_phash=media_phash,
            media_url=image_url)
        if analysis_id:
            result['analysis_id'] = analysis_id
        return jsonify(result)
        
    except Exception as e:
        logger.info(f'[!] Unexpected error in AI detection: {str(e)}')
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
                logger.info(f'[✓] Removed temporary file: {temp_path}')
        except Exception as e:
            logger.info(f'[!] Error removing temporary file: {str(e)}')

@bp.route('/verify-audio', methods=['POST'])
@bp.route('/api/verify-audio', methods=['POST'])
@limiter.limit(SPEND_LIMIT)
def verify_audio():
    """API endpoint to verify if audio is AI-generated using AIorNot API"""
    try:
        logger.info("[*] Starting audio verification process")
        
        # Check if audio file is present in request
        if 'audio' not in request.files:
            logger.info("[!] No audio file in request")
            return jsonify({
                'error': 'لم يتم تقديم ملف صوتي',
                'success': False
            }), 400
            
        audio_file = request.files['audio']
        logger.info(f"[*] Received file: {audio_file.filename}")
        
        # Check if the file is valid
        if audio_file.filename == '':
            logger.info("[!] Empty filename")
            return jsonify({
                'error': 'لم يتم اختيار ملف صوتي',
                'success': False
            }), 400
            
        if not allowed_audio_file(audio_file.filename):
            logger.info(f"[!] File type not allowed: {audio_file.filename}")
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
            logger.info(f'[*] Audio file saved to: {audio_path} (Size: {file_size} bytes)')
        except Exception as save_error:
            logger.info(f'[!] Error saving file: {str(save_error)}')
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
                logger.info(f'[*] MD5 hash: {md5_hash}')
        except Exception as hash_error:
            logger.info(f'[!] Error calculating hash: {str(hash_error)}')
            md5_hash = "غير متاح"
        
        # إضافة رابط الملف الصوتي للتشغيل في واجهة المستخدم
        audio_url = url_for('static', filename=f'uploads/audio/{saved_filename}')
        
        # SHA-256 on every upload; serve cache hits unless forced
        media_hash, _ = compute_hashes(audio_path)
        force = str(request.form.get('force', '')).lower() in ('1', 'true', 'yes')
        if not force:
            cached = find_cached_analysis('ai_audio', 'aiornot', media_hash)
            if cached and cached.detailed_results:
                payload = dict(cached.detailed_results)
                payload['cached'] = True
                payload['analysis_id'] = cached.id
                return jsonify(payload)

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

            from auth import get_current_user
            user = get_current_user()
            analysis_id = persist_analysis(
                user.id if user else None, 'ai_audio', 'aiornot',
                response_data, media_hash=media_hash, media_url=audio_url)
            if analysis_id:
                response_data['analysis_id'] = analysis_id
            return jsonify(response_data)

        except requests.exceptions.RequestException as req_error:
            logger.info(f'[!] Request error: {str(req_error)}')
            return jsonify({
                'error': 'فشل في الاتصال بخدمة تحليل الصوت',
                'message': str(req_error),
                'success': False
            }), 500
    
    except Exception as e:
        logger.info(f'[!] Unexpected error: {str(e)}')
        return jsonify({
            'error': 'حدث خطأ غير متوقع',
            'message': str(e),
            'success': False
        }), 500




from providers.imgbb import upload_to_imgbb

@bp.route('/api/text-detection', methods=['POST'])
@limiter.limit(SPEND_LIMIT)
def api_text_detection():
    """Detect AI-generated text using AIorNot API"""
    logger.info('[*] Received text detection request')
    
    data = request.get_json()
    if not data or not data.get('text'):
        return jsonify({'error': 'لم يتم إرسال نص للتحليل', 'success': False}), 400
    
    text_content = data['text'].strip()
    if len(text_content) < 20:
        return jsonify({'error': 'النص قصير جداً — يجب أن يكون 20 حرف على الأقل', 'success': False}), 400
    
    aiornot_key = os.environ.get('AIORNOT_API_KEY')
    if not aiornot_key:
        return jsonify({'error': 'مفتاح API غير متوفر', 'success': False}), 500

    # SHA-256 of the text; serve cache hits unless forced
    text_hash = compute_text_hash(text_content)
    force = bool(data.get('force')) if isinstance(data, dict) else False
    if not force:
        cached = find_cached_analysis('ai_text', 'aiornot', text_hash)
        if cached and cached.detailed_results:
            payload = dict(cached.detailed_results)
            payload['cached'] = True
            payload['analysis_id'] = cached.id
            return jsonify(payload)

    try:
        from providers.aiornot import post_text

        resp = post_text(text_content)

        if resp.status_code != 200:
            error_text = resp.text[:500]
            logger.info(f'[!] Text API error: {error_text}')
            return jsonify({
                'error': f'فشل التحليل: {resp.status_code}',
                'success': False
            }), 500
        
        result = resp.json()
        logger.info(f'[*] Text API response received')
        
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
            
            payload = {
                'success': True,
                'verdict': verdict_text,
                'is_ai': is_ai,
                'confidence_ai': ai_confidence,
                'confidence_human': human_confidence,
                'annotations': annotations
            }
            from auth import get_current_user
            user = get_current_user()
            analysis_id = persist_analysis(
                user.id if user else None, 'ai_text', 'aiornot',
                payload, media_hash=text_hash)
            if analysis_id:
                payload['analysis_id'] = analysis_id
            return jsonify(payload)
        else:
            # Fallback — return raw report for debugging
            report_preview = json.dumps(report_obj, ensure_ascii=False, indent=2)[:800]
            logger.info(f'[!] No ai_text in report. Keys: {list(report_obj.keys())}')
            return jsonify({
                'success': False,
                'error': f'بنية غير متوقعة: {report_preview}'
            }), 500
            
    except Exception as e:
        logger.info(f'[!] Text detection error: {str(e)}')
        traceback.print_exc()
        return jsonify({
            'error': f'خطأ أثناء التحليل: {str(e)}',
            'success': False
        }), 500

@bp.route('/api/analyze-video', methods=['POST'])
@limiter.limit(SPEND_LIMIT)
def api_analyze_video():
    """Queue AIOrNot video analysis - returns 202 + job id (SSE streamable)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded', 'success': False}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected', 'success': False}), 400

    if not os.environ.get('AIORNOT_API_KEY'):
        return jsonify({'error': 'AIorNot API Key missing', 'success': False}), 500

    temp_filename = secure_filename(f"vid_{uuid.uuid4()}_{file.filename}")
    temp_path = os.path.join(UPLOAD_FOLDER, temp_filename)
    file.save(temp_path)
    media_hash, _ = compute_hashes(temp_path)

    from auth import get_current_user
    from tasks.jobs import run_video_analysis
    from tasks.queue import enqueue
    user = get_current_user()
    job = enqueue(run_video_analysis, temp_path, file.filename,
                  user_id=user.id if user else None, media_hash=media_hash)
    return jsonify({
        'success': True,
        'job_id': job.id,
        'status_url': f'/api/jobs/{job.id}',
        'events_url': f'/api/jobs/{job.id}/events',
    }), 202


@bp.route('/api/faceonlive-detection', methods=['POST'])
@bp.route('/ai-detect-faceonlive', methods=['POST'])  # Keep old route for compatibility
@limiter.limit(SPEND_LIMIT)
def ai_detect_faceonlive():
    """Handle image upload for FaceOnLive detection"""
    logger.info('[*] Received request to FaceOnLive detection endpoint')
    
    if 'image' not in request.files:
        logger.info('[!] No image file in request')
        return jsonify({
            'error': 'لم يتم العثور على صورة في الطلب',
            'success': False
        }), 400
        
    # Create upload directory if it doesn't exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # Get the image file from the request
    image_file = request.files['image']
    if image_file.filename == '':
        logger.info('[!] Empty filename')
        return jsonify({
            'error': 'اسم الملف فارغ',
            'success': False
        }), 400
    
    # Save the image to a temporary file
    filename = secure_filename(f"faceonlive_{uuid.uuid4()}_{image_file.filename}")
    temp_path = os.path.join(UPLOAD_FOLDER, filename)
    try:
        image_file.save(temp_path)
        logger.info(f'[✓] Image saved temporarily to {temp_path}')
    except Exception as e:
        logger.info(f'[!] Error saving file: {str(e)}')
        return jsonify({
            'error': f'خطأ في حفظ الملف: {str(e)}',
            'success': False
        }), 500
    
    try:
        # Call the FaceOnLive scraper with the path to the image file
        logger.info('[*] Starting FaceOnLive scraper...')
        results = scrape_faceonlive(temp_path)
        
        if 'error' in results:
            logger.info(f'[!] Error in scraper: {results["error"]}')
            return jsonify({
                'error': results['error'],
                'success': False
            }), 500
            
        logger.info('[✓] Successfully obtained results from FaceOnLive')
        return jsonify(results)
        
    except Exception as e:
        logger.info(f'[!] Unexpected error in AI detection: {str(e)}')
        traceback.print_exc()
        return jsonify({
            'error': f'خطأ غير متوقع: {str(e)}',
            'success': False
        }), 500
    finally:
        # File cleanup is now handled inside the scrape_faceonlive function
        pass
