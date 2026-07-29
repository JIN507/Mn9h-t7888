"""AI-detection orchestration: legacy response shaping per model.

Providers return normalized DetectionResults; this service maps them onto the
exact legacy JSON dicts the frontend expects (Arabic verdicts included).
"""
import json
import logging
import os
import uuid

from providers.aiornot import post_image_file, parse_image_report
from providers.base import ProviderNotConfigured
from providers.sightengine import check_genai_file, parse_genai
from services.media_service import UPLOAD_FOLDER, download_image

logger = logging.getLogger(__name__)


def persist_analysis(user_id, analysis_type, service, result, *,
                     media_hash=None, media_phash=None, media_url=None):
    """Persist a detection result as an Analysis row. Never raises."""
    from models import db, Analysis
    try:
        analysis = Analysis(
            user_id=user_id,
            analysis_type=analysis_type,
            service=service,
            media_url=media_url,
            media_hash=media_hash,
            media_phash=media_phash,
            is_ai_generated=result.get('is_ai',
                                       result.get('is_ai_generated')),
            confidence_ai=result.get('confidence_ai',
                                     result.get('confidence')),
            confidence_human=result.get('confidence_human'),
            verdict=(result.get('verdict') or '')[:100] or None,
            generator=(result.get('generator') or '')[:100] or None,
            detailed_results=result,
        )
        db.session.add(analysis)
        db.session.commit()
        return analysis.id
    except Exception as e:
        logger.error('Failed to persist analysis: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def find_cached_analysis(analysis_type, service, media_hash):
    """Most recent successful Analysis for the same media hash, or None."""
    if not media_hash:
        return None
    from models import db, Analysis
    try:
        return (db.session.query(Analysis)
                .filter_by(analysis_type=analysis_type, service=service,
                           media_hash=media_hash)
                .order_by(Analysis.created_at.desc())
                .first())
    except Exception as e:
        logger.error('Cache lookup failed: %s', e)
        return None


def scrape_faceonlive(image_path):
    """FaceOnLive scraper was removed with the Playwright stack; the route is
    kept for API compatibility and reports the feature as unavailable."""
    raise RuntimeError('FaceOnLive detection is not available')


def scrape_aiornot(image_url):
    """Detect AI-generated images using AI-or-Not API
    Following the exact structure from AI or Not official documentation
    """
    logger.info(f'[*] Starting AI-or-Not detection for image: {image_url}')
    
    try:
        # Download the image to a temporary file
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        temp_image_path = os.path.join(UPLOAD_FOLDER, f"aiornot_{uuid.uuid4().hex}.jpg")
        
        logger.info(f'[*] Downloading image to {temp_image_path}')
        download_success = download_image(image_url, temp_image_path)
        
        if not download_success or not os.path.exists(temp_image_path):
            return {
                'error': 'Failed to download image from specified URL',
                'success': False,
                'imageUrl': image_url
            }
        
        resp = post_image_file(temp_image_path)
        if resp.status_code >= 400:
            error_msg = f"Failed to analyze image: {resp.status_code} {resp.text}"
            return {
                'error': error_msg,
                'success': False,
                'imageUrl': image_url
            }

        result = resp.json()
        dr = parse_image_report(result)

        if dr.verdict == 'unknown':
            verdict_arabic = "لا يمكن تحديد مصدر الصورة"
        elif dr.is_ai:
            verdict_arabic = "منشأة بواسطة الذكاء الاصطناعي"
        else:
            verdict_arabic = "الصورة حقيقية (غير منشأة بالذكاء الاصطناعي)"

        # Return the simplified result format
        return {
            "verdict": verdict_arabic,
            "confidence_ai": dr.ai_confidence,
            "confidence_human": dr.human_confidence,
            "generator": dr.generator,
            "generator_confidence": dr.generator_confidence,
            "rawText": json.dumps(result, indent=2),
            "imageUrl": image_url,
            "is_ai": dr.is_ai,
            "success": True,
            "source": 'AI-or-Not'
        }
        
    except Exception as e:
        logger.info(f'[!] Error in AI-or-Not API call: {str(e)}')
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
                logger.info(f'[*] Removed temporary file: {temp_image_path}')
        except Exception as e:
            logger.info(f'[!] Error removing temp file: {str(e)}')
        logger.info('[*] AI-or-Not detection (Model 2) completed')

def scrape_thehive(image_url):
    """Detect AI-generated images using Sightengine API (Model 1)"""
    logger.info(f'[*] Starting Sightengine detection (Model 1) for image: {image_url}')
    
    # Download the image to a temporary file
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    temp_image_path = os.path.join(UPLOAD_FOLDER, f"sightengine_{uuid.uuid4().hex}.jpg")
    
    logger.info(f'[*] Downloading image to {temp_image_path}')
    download_success = download_image(image_url, temp_image_path)
    
    if not download_success or not os.path.exists(temp_image_path):
        return {
            'rawText': f'\u062e\u0637\u0623: \u0641\u0634\u0644 \u062a\u062d\u0645\u064a\u0644 \u0627\u0644\u0635\u0648\u0631\u0629 \u0645\u0646 \u0627\u0644\u0631\u0627\u0628\u0637 \u0627\u0644\u0645\u062d\u062f\u062f',
            'source': 'Error',
            'error': 'Failed to download image',
            'imageUrl': image_url
        }
    
    logger.info(f'[*] Image downloaded successfully to {temp_image_path}')
    
    try:
        try:
            status_code, result = check_genai_file(temp_image_path)
        except ProviderNotConfigured as e:
            return {
                'rawText': 'Sightengine credentials not configured',
                'source': 'Model-1',
                'error': str(e),
                'imageUrl': image_url
            }

        if status_code != 200 or result.get("status") != "success":
            return {
              'rawText': f"Error {status_code}: {result}",
              'source': 'Model-1',
              'error': result,
              'imageUrl': image_url
            }

        dr = parse_genai(result)
        verdict_text = "منشأة بواسطة الذكاء الاصطناعي" if dr.is_ai else "الصورة حقيقية (غير منشأة بالذكاء الاصطناعي)"

        # Format result to match the other model's structure for frontend compatibility
        return {
            "verdict": verdict_text,
            "confidence_ai": dr.ai_confidence,
            "confidence_human": dr.human_confidence,
            "generator": dr.generator,
            "quality_ok": True,     # No quality info, assume OK
            "nsfw": False,          # No NSFW info
            'source': 'Model-1',
            'rawText': json.dumps(result, indent=2),
            'imageUrl': image_url,
            'is_ai': dr.is_ai,
            'success': True
        }
            
    except Exception as e:
        logger.info(f'[!] Error in Sightengine API call: {str(e)}')
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
                logger.info(f'[*] Removed temporary file: {temp_image_path}')
        except Exception as e:
            logger.info(f'[!] Error removing temp file: {str(e)}')
        logger.info('[*] Sightengine detection (Model 1) completed')
