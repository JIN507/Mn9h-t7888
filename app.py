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
IMGBB_API_KEY = '8a0183d939bb1db66e0e505b80c758e6'
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

def scrape_thehive(image_url):
    print(f'[*] Starting AI detection for image: {image_url}')
    
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    temp_image_path = os.path.join(UPLOAD_FOLDER, "temp_upload.jpg")
    
    download_success = download_image(image_url, temp_image_path)
    
    if not download_success or not os.path.exists(temp_image_path):
        return {
            'rawText': f'خطأ: فشل تحميل الصورة من الرابط المحدد',
            'source': 'Error',
            'error': 'Failed to download image',
            'imageUrl': image_url
        }
        
    with sync_playwright() as playwright:
        try:
            print('[*] Launching browser...')

            try:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=True,
                    args=[
                        f"--disable-extensions-except={EXTENSION_PATH}",
                        f"--load-extension={EXTENSION_PATH}",
                        "--no-sandbox",
                        "--disable-setuid-sandbox"
                    ]
                )
                print('[✓] Browser launched with extension')
            except Exception as browser_error:
                print(f'[!] Extension failed, using browser without extension')
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=False,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox"
                    ]
                )

            page = context.new_page()

            print('[*] Opening TheHive.ai...')
            page.goto("https://thehive.ai/demos/ai-generated-content-detection", wait_until='load' )

            print('[*] Waiting for the page to fully load...')
            page.wait_for_load_state('networkidle')  # انتظار اكتمال تحميل الصفحة
            page.wait_for_timeout(1000)  # انتظار أقل لتسريع العملية
            
            # النقر على زر "Upload an image" أولاً - تحسين وتبسيط
            print('[*] Looking for Upload button...')
            try:
                # أولاً نفحص إذا كان الزر موجوداً بالنص
                upload_button_visible = False
                if page.locator('button:text("/upload/i")').count() > 0:
                    print('[*] Found Upload button by text regex')
                    page.locator('button:text("/upload/i")').first.click(force=True)
                    upload_button_visible = True
                # إذا لم نجد بالطريقة الأولى نستخدم JavaScript
                if not upload_button_visible:
                    print('[*] Using JavaScript to find and click Upload button')
                    clicked = page.evaluate('''() => {
                        // نبحث عن أي زر يحتوي على كلمة upload بأي حالة
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const uploadBtn = buttons.find(btn => 
                            btn.textContent && 
                            (btn.textContent.toLowerCase().includes('upload') || 
                             btn.innerText.toLowerCase().includes('upload')));
                        if (uploadBtn) {
                            console.log('Found upload button with text: ' + uploadBtn.textContent);
                            uploadBtn.click();
                            return true;
                        }
                        // لم نجد زراً بالنص، نبحث عن زر به رمز رفع
                        const iconButtons = Array.from(document.querySelectorAll('button'));
                        for (const btn of iconButtons) {
                            if (btn.querySelector('svg') || btn.querySelector('i')) {
                                console.log('Found button with icon');
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }''')
                    if clicked:
                        print('[✓] Successfully clicked upload button with JavaScript')
                        upload_button_visible = True
                    else:
                        print('[!] Could not find upload button with JavaScript')
                

                # النقر على زر "Upload an image" أولاً
                if page.locator('button:has-text("Upload an image")').count() > 0:
                    print('[*] Found Upload button by text - clicking it')
                    page.locator('button:has-text("Upload an image")').click(force=True)
                    page.wait_for_timeout(1500)  # انتظار أقل لظهور حقل إدخال الملف
                
                # رفع الملف بالطريقة القديمة مع تحسينات للسرعة
                print('[*] Uploading file...')
                try:
                    # محاولة العثور على حقل إدخال الملف وتعيين الملف
                    file_input = page.locator('input[type="file"]').first
                    file_input.set_input_files(temp_image_path)
                    print('[✓] File uploaded successfully')
                    page.wait_for_timeout(2500)  # انتظار لمعالجة الملف - مخفض من 5000ms الأصلية
                except Exception as upload_error:
                    print(f'[!] Error uploading file: {str(upload_error)}')
                
                # انتظار أقصر بعد الرفع لتسريع العملية
                print('[*] Waiting for file processing...')
                page.wait_for_timeout(3000)  # تقليل وقت الانتظار لتسريع العملية

                # التحقق من ظهور النتائج أولاً
                print('[*] Checking for results before CAPTCHA...')
                try:
                    # فحص سريع للتحقق من وجود النتائج بالفعل
                    has_results = page.evaluate('''() => {
                        // التحقق من وجود النتائج في الصفحة
                        const content = document.body.innerText;
                        return content.includes('AI Generated') && content.includes('Not AI Generated') && 
                               (content.includes('0.') || content.includes('1.'));
                    }''')
                    
                    if has_results:
                        print('[✓] Results already visible, skipping CAPTCHA check')
                    else:
                        # الانتظار لحل الكابتشا ثم النقر على زر Continue
                        print('[*] Results not found, waiting for CAPTCHA to be solved...')
                        try:
                            page.wait_for_timeout(2000)  # تقليل وقت الانتظار للكابتشا
                            if page.locator('button:has-text("Continue")').count() > 0:
                                print('[*] Found CAPTCHA Continue button, clicking it...')
                                page.locator('button:has-text("Continue")').click(force=True)
                                print('[✓] Successfully clicked CAPTCHA Continue button')
                                page.wait_for_timeout(1000)  # تقليل وقت الانتظار بعد النقر
                        except Exception as captcha_error:
                            print(f'[!] Error handling CAPTCHA: {str(captcha_error)}')
                except Exception as results_check_error:
                    print(f'[!] Error checking for results: {str(results_check_error)}')

            except Exception as upload_error:
                print(f'[!] Error uploading file: {str(upload_error)}')

            print('[*] Waiting for results...')
            try:
                # انتظار أقل للنتائج مع فحص الصفحة بشكل دوري
                # انتظار مع فحص كل ثانيتين للتحقق من وجود النتائج
                max_wait_time = 30  # الحد الأقصى للانتظار 30 ثانية
                check_interval = 2  # التحقق كل ثانيتين
                wait_time = 0
                
                while wait_time < max_wait_time:
                    # فحص وجود النتائج - تحديث للتحقق من الشكل الجديد للنتائج
                    has_results = page.evaluate('''() => {
                        const content = document.body.innerText;
                        // Check for traditional format
                        const hasOldFormat = content.includes('AI Generated') && content.includes('Not AI Generated') && 
                               (content.includes('0.') || content.includes('1.'));
                        
                        // Check for new JSON format
                        const hasJsonFormat = content.includes('not_ai_generated') && content.includes('ai_generated') && 
                               content.includes('Confidence Score');
                               
                        return hasOldFormat || hasJsonFormat;
                    }''')
                    
                    if has_results:
                        print(f'[✓] Results found after {wait_time} seconds!')
                        break
                    
                    page.wait_for_timeout(check_interval * 1000)
                    wait_time += check_interval
                    print(f'[*] Waiting for results... ({wait_time}s/{max_wait_time}s)')
                
                print('[*] Extracting results text...')
                # Get the page content
                raw_text = page.content()
                print('[*] Raw content length:', len(raw_text))

                # Default scores
                ai_generated_score = "0.00"
                not_ai_generated_score = "0.00"
                none_score = "0.00"
                
                # Initialize detailed_results here to avoid access error
                detailed_results = {
                    'ai_generated': 0.0,
                    'not_ai_generated': 0.0,
                    'none': 0.0
                }
                
                # Extract scores using both methods for redundancy
                
                # Extract results based on the new table format from TheHive.ai
                try:
                    print('[*] Extracting results from new table format...')
                    js_extracted_scores = page.evaluate('''() => {
                        // Try to extract data directly from the Class/Confidence Score table
                        try {
                            // Get all table rows
                            const tableRows = Array.from(document.querySelectorAll('.MuiTypography-root-110'));
                            if (tableRows.length > 0) {
                                const results = {};
                                // Look for the class names and scores
                                for (let i = 0; i < tableRows.length; i++) {
                                    const text = tableRows[i].textContent.trim();
                                    if (text === 'not_ai_generated' || text === 'ai_generated' || text === 'none') {
                                        const className = text;
                                        // The next element should be the score
                                        if (i + 1 < tableRows.length) {
                                            const scoreText = tableRows[i + 1].textContent.trim();
                                            const score = parseFloat(scoreText) || 0;
                                            results[className] = score.toFixed(2);
                                        }
                                    }
                                }
                                
                                if (Object.keys(results).length > 0) {
                                    console.log('Found results in table:', results);
                                    return { ...results, format: 'new_table' };
                                }
                            }
                        } catch (e) {
                            console.error('Error extracting from table:', e);
                        }
                        
                        // If we reach here, try older formats
                        try {
                            // Try to find the table with results (fallback method)
                            const rows = Array.from(document.querySelectorAll('tr'));
                            if (rows.length > 0) {
                                const results = {};
                                for (const row of rows) {
                                    const cells = Array.from(row.querySelectorAll('td'));
                                    if (cells.length >= 2) {
                                        const className = cells[0].textContent.trim();
                                        const score = cells[1].textContent.trim();
                                        if (className && score) {
                                            results[className] = score;
                                        }
                                    }
                                }
                                if (Object.keys(results).length > 0) {
                                    return { ...results, format: 'new' };
                                }
                            }
                        } catch (e) {
                            console.error('Error extracting from tr/td:', e);
                        }
                        
                        // If still nothing, fall back to the oldest format
                        const aiScoreElement = document.querySelector('*:contains("AI Generated")');
                        const notAiScoreElement = document.querySelector('*:contains("Not AI Generated")');
                        
                        let aiScore = '0.00';
                        let notAiScore = '0.00';
                        
                        if (aiScoreElement) {
                            const aiText = aiScoreElement.textContent;
                            const aiMatch = aiText.match(/([0-9]+\.[0-9]+)/);
                            if (aiMatch) aiScore = aiMatch[0];
                        }
                        
                        if (notAiScoreElement) {
                            const notAiText = notAiScoreElement.textContent;
                            const notAiMatch = notAiText.match(/([0-9]+\.[0-9]+)/);
                            if (notAiMatch) notAiScore = notAiMatch[0];
                        }
                        
                        return { ai_generated: aiScore, not_ai_generated: notAiScore, format: 'old' };
                    }''')
                    
                    print('[*] Extracted scores:', js_extracted_scores)
                    
                    # Handle all formats - both old and new
                    print('[*] Processing extracted scores from format:', js_extracted_scores.get('format', 'unknown'))
                    
                    # Initialize scores with defaults
                    ai_generated_score = '0.00'
                    not_ai_generated_score = '0.00'
                    none_score = '0.00'
                    
                    # Extract scores based on their keys
                    for key, value in js_extracted_scores.items():
                        if key == 'format':
                            continue
                            
                        # Try to convert the value to a string if it's not already
                        if not isinstance(value, str):
                            try:
                                value = str(value)
                            except:
                                value = '0.00'
                                
                        key_lower = key.lower()
                        
                        # Handle exact key matches first
                        if key_lower == 'ai_generated':
                            ai_generated_score = value
                        elif key_lower == 'not_ai_generated':
                            not_ai_generated_score = value
                        elif key_lower == 'none':
                            none_score = value
                        # Handle approximate matches
                        elif 'ai' in key_lower and 'not' not in key_lower and 'generated' in key_lower:
                            ai_generated_score = value
                        elif 'not' in key_lower and 'ai' in key_lower:
                            not_ai_generated_score = value
                    
                    print(f'[*] Extracted scores - AI: {ai_generated_score}, Not AI: {not_ai_generated_score}, None: {none_score}')
                except Exception as js_error:
                    print(f'[!] Error extracting scores with JS: {str(js_error)}')
                
                # Fallback to regex method if JS method fails
                if ai_generated_score == '0.00' and not_ai_generated_score == '0.00':
                    print('[*] Falling back to regex method...')
                    ai_pattern = r'AI Generated\s*<[^>]+>\s*([0-9.]+)'
                    not_ai_pattern = r'Not AI Generated\s*<[^>]+>\s*([0-9.]+)'
                    
                    # New patterns for the table format
                    table_ai_pattern = r'ai_generated[\s\S]*?([0-9]\.[0-9]+)'
                    table_not_ai_pattern = r'not_ai_generated[\s\S]*?([0-9]\.[0-9]+)'
                    
                    ai_matches = re.findall(ai_pattern, raw_text) or re.findall(table_ai_pattern, raw_text)
                    not_ai_matches = re.findall(not_ai_pattern, raw_text) or re.findall(table_not_ai_pattern, raw_text)
                    
                    if ai_matches:
                        ai_generated_score = ai_matches[0]
                    
                    if not_ai_matches:
                        not_ai_generated_score = not_ai_matches[0]
                
                print(f'[✓] AI Generated score: {ai_generated_score}')
                print(f'[✓] Not AI Generated score: {not_ai_generated_score}')

                # Convert scores to float
                ai_generated_float = float(ai_generated_score)
                not_ai_generated_float = float(not_ai_generated_score)

                # Determine verdict
                verdict = "uncertain"
                confidence = 0.0

                if not_ai_generated_float >= 0.49:
                    verdict = "real"
                    confidence = not_ai_generated_float
                elif ai_generated_float >= 0.49:
                    verdict = "ai_generated"
                    confidence = ai_generated_float
                
                # Format results to match what the frontend expects (line by line format)
                # The frontend expects a format like: ai_generated\n0.XX\nnot_ai_generated\n0.XX
                
                # Start with the essential scores - ensure we're using actual numbers, not HTML or JS
                try:
                    # Clean the scores to ensure they're just numbers
                    ai_score_clean = float(ai_generated_score.strip().replace('%', ''))
                    not_ai_score_clean = float(not_ai_generated_score.strip().replace('%', ''))
                    
                    # Format with exactly 2 decimal places
                    ai_generated_score = f"{ai_score_clean:.2f}"
                    not_ai_generated_score = f"{not_ai_score_clean:.2f}"
                except (ValueError, TypeError):
                    # If conversion fails, use defaults
                    ai_generated_score = "0.00"
                    not_ai_generated_score = "0.00"
                    
                # Create the properly formatted result text
                result_text = f"ai_generated\n{ai_generated_score}\nnot_ai_generated\n{not_ai_generated_score}"
                
                # Add 'none' score if available (common in new format)
                if none_score != '0.00':
                    result_text += f"\nnone\n{none_score}"
                
                # Add any additional classes from the extracted scores
                for key, value in js_extracted_scores.items():
                    if key not in ['format', 'ai_generated', 'not_ai_generated', 'none']:
                        # Only add if it's a valid class with a numeric score
                        try:
                            # Make sure the value is numeric
                            float_value = float(value)
                            # Format with 2 decimal places
                            formatted_value = f"{float_value:.2f}"
                            result_text += f"\n{key}\n{formatted_value}"
                        except (ValueError, TypeError):
                            # Skip if the value isn't a valid number
                            pass
                            
                print(f'[*] Formatted result text for frontend parsing:\n{result_text}')
                
                # Create a clean formatted output for detailed results
                detailed_results = {
                    'ai_generated': float(ai_generated_score),
                    'not_ai_generated': float(not_ai_generated_score)
                }
                
                # Add any additional classes found
                for key, value in js_extracted_scores.items():
                    if key not in ['format', 'ai_generated', 'not_ai_generated']:
                        try:
                            detailed_results[key] = float(value)
                        except (ValueError, TypeError):
                            pass
            except Exception as results_error:
                print(f'[!] Error processing results: {str(results_error)}')
                verdict = "error"
                confidence = 0.0

            # التقاط لقطة شاشة للنتائج قبل إغلاق المتصفح
            screenshot_path = os.path.join(UPLOAD_FOLDER, 'hive_result.png')
            page.screenshot(path=screenshot_path)
            print(f'[✓] Screenshot saved: {screenshot_path}')
            
            # هام: تأكيد الحصول على النتائج بشكل صحيح قبل إغلاق المتصفح
            print('[*] Finalizing results and preparing return data...')
            
            # التأكد من وجود بيانات نتائج بشكل مناسب للعرض في واجهة المستخدم
            # Convert detailed results to nicely formatted text for display
            detailed_text = json.dumps(detailed_results, indent=2, ensure_ascii=False)
            
            # Format the rawText to be the properly formatted JSON instead of JS code
            if raw_text and '</style>' in raw_text:
                # Cut off the HTML/JS part and just show the classification results
                raw_text = detailed_text
            
            results = {
                'rawText': raw_text,
                'source': 'TheHive.ai',
                'verdict': verdict,
                'confidence': confidence,
                'ai_generated_score': ai_generated_score,
                'not_ai_generated_score': not_ai_generated_score,
                'imageUrl': image_url,
                'screenshot_path': screenshot_path, # إضافة مسار لقطة الشاشة للعرض في حالة الضرورة
                'result_text': result_text  # إضافة النص المنسق للتحليل
            }
            
            print('[✓] Results data prepared successfully:')
            print(f'   - Verdict: {verdict}')
            print(f'   - Confidence: {confidence:.2f}')
            print(f'   - AI Generated Score: {ai_generated_score}')
            print(f'   - Not AI Generated Score: {not_ai_generated_score}')
            
            # إغلاق المتصفح بعد التأكد من الحصول على النتائج
            context.close()
            print('[✓] Browser closed successfully')
            
            # تنظيف الملفات المؤقتة
            try:
                if os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
                    print('[✓] Temporary files cleaned up')
            except Exception as cleanup_error:
                print(f'[!] Warning: Could not clean up temporary files: {str(cleanup_error)}')
            
            print('[✓] DONE: Returning final results to application')
            return results

        except Exception as e:
            print(f'[!] Error: {str(e)}')
            return {
                'rawText': f'خطأ أثناء التحليل: {str(e)}',
                'source': 'Error',
                'error': str(e),
                'imageUrl': image_url
            }
        finally:
            print('[*] Playwright session finished')




def scrape_faceonlive(image_path):
    """Detect deepfake using faceonlive.com API"""
    print(f'[*] Starting deepfake detection for image: {image_path}')
    
    if not os.path.exists(image_path):
        return {
            'rawText': f'خطأ: ملف الصورة غير موجود',
            'source': 'Error',
            'error': 'Image file not found',
            'imageUrl': None
        }
        
    with sync_playwright() as playwright:
        try:
            # Launch browser with headless=False to see what's happening
            print('[*] Launching browser for FaceOnLive scraping...')
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(viewport={'width': 1280, 'height': 800})
            page = context.new_page()

            print("[*] Opening website...")
            page.goto("https://faceonlive.com/projects/deepfake-detection-sdk/")
            page.wait_for_load_state("networkidle")

            print("[*] Getting iframe...")
            frame_element = page.query_selector("iframe")
            frame = frame_element.content_frame()

            print("[*] Uploading image...")
            file_input = frame.locator('input[type="file"]')
            file_input.set_input_files(image_path)

            print("[*] Giving Gradio some time to attach event handlers...")
            time.sleep(2)

            print("[*] Clicking Detect button...")
            frame.locator('button#component-9').click()

            print("[*] Waiting for result...")
            frame.wait_for_selector('h2[data-testid="label-output-value"]', timeout=120000)

            # Collect results
            results = []
            print("\n[MAIN RESULTS]:")
            headers = frame.locator('h2[data-testid="label-output-value"]')
            for i in range(headers.count()):
                text = headers.nth(i).inner_text()
                print(f"- {text}")
                results.append(f"- {text}")

            confidence_scores = []
            print("\n[DETAILED CONFIDENCE SCORES]:")
            buttons = frame.locator('button.confidence-set')
            for i in range(buttons.count()):
                model = buttons.nth(i).locator('dt').inner_text()
                confidence = buttons.nth(i).locator('dd').inner_text()
                print(f"{model}: {confidence}")
                confidence_scores.append(f"{model}: {confidence}")
                
            # Format the results
            main_result = "\n".join(results)
            detailed_scores = "\n".join(confidence_scores)
            full_result = f"[MAIN RESULTS]:\n{main_result}\n\n[DETAILED CONFIDENCE SCORES]:\n{detailed_scores}"
            
            # Take screenshot for result visualization
            result_screenshot = os.path.join(UPLOAD_FOLDER, "faceonlive_result.png")
            page.screenshot(path=result_screenshot)
            
            # Get the first result as the primary classification
            primary_result = "Unknown"
            if len(results) > 0:
                primary_result = results[0].replace('- ', '')
                
            # Upload the image to ImgBB for later reference
            image_url = None
            try:
                with open(image_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
                image_url = upload_to_imgbb(image_data)
            except Exception as img_err:
                print(f"[!] Error uploading result image: {str(img_err)}")
                
            return {
                'rawText': full_result,
                'source': 'FaceOnLive',
                'result': primary_result,
                'imageUrl': image_url,
                'confidence_scores': confidence_scores
            }
            
        except Exception as e:
            print(f'[!] Error during deepfake detection: {str(e)}')
            traceback.print_exc()
            return {
                'rawText': f'خطأ أثناء تحليل الصورة: {str(e)}',
                'source': 'Error',
                'error': str(e),
                'imageUrl': None
            }
        finally:
            # إضافة تأخير قبل إغلاق المتصفح للسماح برؤية النتائج
            print('[*] Keeping browser open for 5 seconds to view results...')
            try:
                time.sleep(5)  # انتظر 5 ثواني قبل الإغلاق
            except Exception:
                pass
            print('[*] Playwright session finished')


def search_images(image_url):
    """Generate search URLs for reverse image search engines"""
    return {
        'google': f"https://lens.google.com/uploadbyurl?url={image_url}",
        'bing': f"https://www.bing.com/images/search?q=imgurl:{image_url}&view=detailv2&iss=sbi",
        'yandex': f"https://yandex.com/images/search?rpt=imageview&url={image_url}",
        'tineye': f"https://tineye.com/search?url={image_url}"
    }

def scrape_reverse_search(image_url):
    """Scrape TheHive.ai reverse image search results"""
    print(f"[*] Starting reverse image search for: {image_url}")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    temp_image_path = os.path.join(UPLOAD_FOLDER, "temp_upload.jpg")

    if not download_image(image_url, temp_image_path):
        return {'error': 'Failed to download image'}

    with sync_playwright() as p:
        try:
            # Determine whether to use YesCaptcha extension based on environment variable
            use_extension = os.environ.get('USE_CAPTCHA_EXTENSION', 'True').lower() == 'true'
            extension_args = []
            if use_extension and EXTENSION_PATH:
                extension_args = [
                    f"--disable-extensions-except={EXTENSION_PATH}",
                    f"--load-extension={EXTENSION_PATH}"
                ]
            
            context = p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=True,
                args=[
                    *extension_args,
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--start-maximized"
                ]
            )
            page = context.new_page()
            print("[*] Navigating to reverse image search...")
            page.goto("https://thehive.ai/demos/reverse-image-search", wait_until="load")
            page.wait_for_timeout(4000)

            # Handle captcha continue button if exists
            if page.locator('button:has-text("Continue")').count() > 0:
                print("[*] CAPTCHA continue button found, clicking...")
                page.locator('button:has-text("Continue")').click()
                page.wait_for_timeout(2000)

            # Click Upload button
            print("[*] Clicking Upload button...")
            upload_btn = page.locator('button:has-text("Upload")')
            if upload_btn.count() > 0:
                upload_btn.click()
                page.wait_for_timeout(1000)
            else:
                raise Exception("Upload button not found")

            # Set file input
            file_input = page.locator('input[type="file"]')
            file_input.set_input_files(temp_image_path)
            print("[*] File uploaded")

            page.wait_for_timeout(8000)  # Wait for result to appear
            try:
                    # فحص سريع للتحقق من وجود النتائج بالفعل
                    has_results = page.evaluate(r'''() => {
                        // التحقق من وجود النتائج في الصفحة
                        const content = document.body.innerText;
                        return content.includes('AI Generated') && content.includes('Not AI Generated') && 
                               (content.includes('0.') || content.includes('1.'));
                    }''')
                    
                    if has_results:
                        print('[✓] Results already visible, skipping CAPTCHA check')
                    else:
                        # الانتظار لحل الكابتشا ثم النقر على زر Continue
                        print('[*] Results not found, waiting for CAPTCHA to be solved...')
                        try:
                            page.wait_for_timeout(2000)  # تقليل وقت الانتظار للكابتشا
                            if page.locator('button:has-text("Continue")').count() > 0:
                                print('[*] Found CAPTCHA Continue button, clicking it...')
                                page.locator('button:has-text("Continue")').click(force=True)
                                print('[✓] Successfully clicked CAPTCHA Continue button')
                                page.wait_for_timeout(1000)  # تقليل وقت الانتظار بعد النقر
                        except Exception as captcha_error:
                            print(f'[!] Error handling CAPTCHA: {str(captcha_error)}')
            except Exception as results_check_error:
                    print(f'[!] Error checking for results: {str(results_check_error)}')

            except Exception as upload_error:
                print(f'[!] Error uploading file: {str(upload_error)}')

            page.wait_for_timeout(8000)
            # Extract result box contents using a more flexible approach
            print("[*] Extracting result links...")
            
            # استخراج جميع الروابط من الصفحة
            print("[*] Trying to extract links using JavaScript...")
            try:
                hrefs = page.evaluate("""
                () => {
                    // استخراج جميع الروابط من القسم الرئيسي
                    const mainContainer = document.querySelector("[class*='jss'][class*='MuiBox'][class*='jss']")
                        || document.querySelector("[class*='MuiBox']")
                        || document.body;
                        
                    // البحث عن جميع الروابط داخل العنصر الرئيسي
                    const links = Array.from(mainContainer.querySelectorAll('a[href]'));
                    
                    // تصفية الروابط وإعادة الـ href فقط
                    return links
                        .map(link => link.href)
                        .filter(href => {
                            // استبعاد روابط TheHive نفسه والروابط الداخلية
                            return !href.includes('thehive.ai') && 
                                   !href.startsWith('#') &&
                                   !href.includes('javascript:');
                        });
                }
                """)
                
                print(f"[*] Found {len(hrefs)} links using JavaScript")
            except Exception as js_error:
                print(f"[!] JavaScript extraction failed: {js_error}")
                # خطة بديلة: استخدام طريقة playwright المباشرة
                try:
                    # تجربة مجموعة من المحددات للعثور على الروابط
                    selectors = [
                        "div[class*='jss'] a[href]",
                        "div[class*='MuiBox'] a[href]",
                        "#root div a[href]",
                        "a[href]"
                    ]
                    
                    for selector in selectors:
                        links = page.locator(selector)
                        if links.count() > 0:
                            hrefs = [link.get_attribute('href') for link in links.all() if link.get_attribute('href')]
                            hrefs = [href for href in hrefs if 'thehive.ai' not in href and not href.startswith('#')]
                            print(f"[*] Found {len(hrefs)} links using selector {selector}")
                            break
                    else:
                        print("[!] Could not find any links using any selectors")
                        hrefs = []
                except Exception as selector_error:
                    print(f"[!] Selector-based extraction failed: {selector_error}")
                    hrefs = []
            
            # طباعة الروابط التي تم العثور عليها
            for i, href in enumerate(hrefs):
                print(f"[{i+1}] {href}")
                
            # التقاط لقطة شاشة للتشخيص إذا لم نجد أي روابط
            if not hrefs:
                print("[!] No links found, taking screenshot for diagnosis")
                screenshot_path = os.path.join(UPLOAD_FOLDER, "debug_screenshot.png")
                page.screenshot(path=screenshot_path)
                print(f"[*] Screenshot saved to {screenshot_path}")
                
                # تجربة تحليل HTML مباشرة للتشخيص
                html_content = page.content()
                print(f"[*] Page HTML content length: {len(html_content)}")
                print(f"[*] HTML preview: {html_content[:500]}...")
                
                # محاولة استخراج أي شيء يبدو كرابط من HTML
                import re
                urls = re.findall(r'href=[\"\']?([^\"\'> ]+)', html_content)
                print(f"[*] URLs found in HTML: {urls[:10]}")
                
                # اختيار الروابط الخارجية فقط
                external_urls = [url for url in urls if not url.startswith('#') and 'thehive.ai' not in url and not url.startswith('javascript:')]
                if external_urls:
                    print(f"[*] Found {len(external_urls)} potential external links in HTML")
                    hrefs = external_urls

            context.close()
            
            # Clean up temporary files
            try:
                if os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
                    print("[✓] Temporary files cleaned up")
            except Exception as cleanup_error:
                print(f"[!] Warning: Could not clean up temporary files: {str(cleanup_error)}")

            return {'links': hrefs, 'source': 'TheHive Reverse Image Search'}

        except Exception as e:
            print(f"[!] Error: {str(e)}")
            # Clean up temporary files in case of error
            try:
                if os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
            except:
                pass
            return {'error': str(e)}

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
def video():
    return render_template('video.html')

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
    
    # Get the service type from the form data - thehive (default) or faceonlive
    service_type = request.form.get('service_type', 'thehive')
    print(f'[*] Service type requested: {service_type}')
    
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
        # Print the service type being requested
        print(f'[DEBUG] Service type requested: {service_type}')
        result = None
        
        # Process based on selected service
        if service_type.lower() == 'thehive':
            # For TheHive, we need to upload to ImgBB first to get a public URL
            print('[*] Processing with TheHive.ai service')
            
            # Upload file to imgbb to get URL
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
            
            # Add a print statement to verify we're calling the scraper
            print('[DEBUG] About to call TheHive.ai scraper with URL:', image_url)
            
            # Force browser visibility
            os.environ['PLAYWRIGHT_FORCE_VISIBLE'] = '1'
            
            # Explicitly wait to give time to debug
            print('[DEBUG] Waiting 2 seconds before starting scraper...')
            time.sleep(2)
            
            # Call the TheHive.ai scraper with the image URL
            print('[*] Starting TheHive.ai scraper...')
            result = scrape_thehive(image_url)
            print('[DEBUG] TheHive.ai scraper returned:', result)
            
        elif service_type.lower() == 'faceonlive':
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
            print(f'[!] Unknown service type: {service_type}')
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
            
        print(f'[✓] Successfully obtained results from {service_type}')
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
    imgbb_api_key = os.environ.get('IMGBB_API_KEY', '8a0183d939bb1db66e0e505b80c758e6')
    
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

def scrape_thehive(image_url):
    """Detect AI-generated images using TheHive.ai API"""
    print(f'[*] Starting AI detection for image: {image_url}')
    
    # Download the image to a temporary file
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    temp_image_path = os.path.join(UPLOAD_FOLDER, f"thehive_{uuid.uuid4().hex}.jpg")
    
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
        # Use Sightengine API instead of Playwright
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
              'source': 'Sightengine',
              'error': result,
              'imageUrl': image_url
            }

        score = result['type']['ai_generated']
        return {
          'rawText': f"AI-generated confidence: {score:.2%}",
          'source': 'Sightengine',
          'confidence': score,
          'is_ai': score > 0.5,
          'imageUrl': image_url,
          'success': True
        }
            
    except Exception as e:
        print(f'[!] Error in Sightengine API call: {str(e)}')
        traceback.print_exc()
        return {
            'error': f'\u062e\u0637\u0623 \u0623\u062b\u0646\u0627\u0621 \u0627\u0644\u062a\u062d\u0644\u064a\u0644: {str(e)}',
            'rawText': f'\u062e\u0637\u0623 \u0623\u062b\u0646\u0627\u0621 \u0627\u0644\u062a\u062d\u0644\u064a\u0644: {str(e)}',
            'source': 'Sightengine',
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
        print('[*] Sightengine detection completed')

# FaceOnLive implementation using the new scraper code
def scrape_faceonlive(image_path):
    """Automated scraper for FaceOnLive deepfake detection"""
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