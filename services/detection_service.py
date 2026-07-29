"""AI-detection orchestration: legacy response shaping per model.

Providers return normalized DetectionResults; this service maps them onto the
exact legacy JSON dicts the frontend expects (Arabic verdicts included).
"""
import json
import logging

from providers.aiornot import post_image_file, parse_image_report
from providers.base import ProviderNotConfigured
from providers.sightengine import check_genai_file, parse_genai

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


def scrape_aiornot_file(image_path):
    """AIOrNot image detection on a LOCAL file — direct upload, the image
    never goes to a public host (plan §3.4 privacy fix)."""
    logger.info('Starting AI-or-Not detection (direct file upload)')
    try:
        resp = post_image_file(image_path)
        if resp.status_code >= 400:
            return {
                'error': f"Failed to analyze image: {resp.status_code} {resp.text}",
                'success': False,
                'imageUrl': None
            }

        result = resp.json()
        dr = parse_image_report(result)

        if dr.verdict == 'unknown':
            verdict_arabic = "لا يمكن تحديد مصدر الصورة"
        elif dr.is_ai:
            verdict_arabic = "منشأة بواسطة الذكاء الاصطناعي"
        else:
            verdict_arabic = "الصورة حقيقية (غير منشأة بالذكاء الاصطناعي)"

        return {
            "verdict": verdict_arabic,
            "confidence_ai": dr.ai_confidence,
            "confidence_human": dr.human_confidence,
            "generator": dr.generator,
            "generator_confidence": dr.generator_confidence,
            "rawText": json.dumps(result, indent=2),
            "imageUrl": None,
            "is_ai": dr.is_ai,
            "success": True,
            "source": 'AI-or-Not'
        }

    except Exception as e:
        logger.exception('Error in AI-or-Not API call')
        return {
            'error': f'Error during analysis: {str(e)}',
            'success': False,
            'imageUrl': None
        }


def scrape_thehive_file(image_path):
    """Sightengine genai detection on a LOCAL file — direct upload."""
    logger.info('Starting Sightengine detection (direct file upload)')
    try:
        try:
            status_code, result = check_genai_file(image_path)
        except ProviderNotConfigured as e:
            return {
                'rawText': 'Sightengine credentials not configured',
                'source': 'Model-1',
                'error': str(e),
                'imageUrl': None
            }

        if status_code != 200 or result.get("status") != "success":
            return {
              'rawText': f"Error {status_code}: {result}",
              'source': 'Model-1',
              'error': result,
              'imageUrl': None
            }

        dr = parse_genai(result)
        verdict_text = ("منشأة بواسطة الذكاء الاصطناعي"
                        if dr.is_ai else
                        "الصورة حقيقية (غير منشأة بالذكاء الاصطناعي)")

        # Same structure as the other model for frontend compatibility
        return {
            "verdict": verdict_text,
            "confidence_ai": dr.ai_confidence,
            "confidence_human": dr.human_confidence,
            "generator": dr.generator,
            "quality_ok": True,     # No quality info, assume OK
            "nsfw": False,          # No NSFW info
            'source': 'Model-1',
            'rawText': json.dumps(result, indent=2),
            'imageUrl': None,
            'is_ai': dr.is_ai,
            'success': True
        }

    except Exception as e:
        logger.exception('Error in Sightengine API call')
        return {
            'error': f'خطأ أثناء التحليل: {str(e)}',
            'rawText': f'خطأ أثناء التحليل: {str(e)}',
            'source': 'Model-1',
            'success': False,
            'imageUrl': None
        }
