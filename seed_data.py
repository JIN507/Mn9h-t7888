#!/usr/bin/env python3
"""
Seed Data Script

Idempotent seeder for shared catalog (countries and sources).
Safe to run multiple times - uses upsert logic.

Usage:
    python seed_data.py

Environment:
    DATABASE_URL - Database connection string (optional, defaults to SQLite)
"""
import os
import sys
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# =============================================================================
# SEED DATA
# =============================================================================

COUNTRIES = [
    # Gulf States
    {'code': 'SA', 'name_ar': 'المملكة العربية السعودية', 'name_en': 'Saudi Arabia'},
    {'code': 'AE', 'name_ar': 'الإمارات العربية المتحدة', 'name_en': 'United Arab Emirates'},
    {'code': 'KW', 'name_ar': 'الكويت', 'name_en': 'Kuwait'},
    {'code': 'QA', 'name_ar': 'قطر', 'name_en': 'Qatar'},
    {'code': 'BH', 'name_ar': 'البحرين', 'name_en': 'Bahrain'},
    {'code': 'OM', 'name_ar': 'عُمان', 'name_en': 'Oman'},
    # Levant
    {'code': 'JO', 'name_ar': 'الأردن', 'name_en': 'Jordan'},
    {'code': 'LB', 'name_ar': 'لبنان', 'name_en': 'Lebanon'},
    {'code': 'SY', 'name_ar': 'سوريا', 'name_en': 'Syria'},
    {'code': 'PS', 'name_ar': 'فلسطين', 'name_en': 'Palestine'},
    {'code': 'IQ', 'name_ar': 'العراق', 'name_en': 'Iraq'},
    # North Africa
    {'code': 'EG', 'name_ar': 'مصر', 'name_en': 'Egypt'},
    {'code': 'LY', 'name_ar': 'ليبيا', 'name_en': 'Libya'},
    {'code': 'TN', 'name_ar': 'تونس', 'name_en': 'Tunisia'},
    {'code': 'DZ', 'name_ar': 'الجزائر', 'name_en': 'Algeria'},
    {'code': 'MA', 'name_ar': 'المغرب', 'name_en': 'Morocco'},
    {'code': 'SD', 'name_ar': 'السودان', 'name_en': 'Sudan'},
    # Other Arab
    {'code': 'YE', 'name_ar': 'اليمن', 'name_en': 'Yemen'},
]

SOURCES = [
    # =========================================================================
    # Saudi Arabia (SA)
    # =========================================================================
    {'country_code': 'SA', 'name': 'العربية', 'domain': 'alarabiya.net', 'category': 'news', 'is_verified': True},
    {'country_code': 'SA', 'name': 'عكاظ', 'domain': 'okaz.com.sa', 'category': 'news', 'is_verified': True},
    {'country_code': 'SA', 'name': 'سبق', 'domain': 'sabq.org', 'category': 'news', 'is_verified': True},
    {'country_code': 'SA', 'name': 'واس (وكالة الأنباء السعودية)', 'domain': 'spa.gov.sa', 'category': 'gov', 'is_verified': True},
    {'country_code': 'SA', 'name': 'الرياض', 'domain': 'alriyadh.com', 'category': 'news', 'is_verified': True},
    {'country_code': 'SA', 'name': 'الوطن', 'domain': 'alwatan.com.sa', 'category': 'news', 'is_verified': True},
    
    # =========================================================================
    # United Arab Emirates (AE)
    # =========================================================================
    {'country_code': 'AE', 'name': 'الإمارات اليوم', 'domain': 'emaratalyoum.com', 'category': 'news', 'is_verified': True},
    {'country_code': 'AE', 'name': 'البيان', 'domain': 'albayan.ae', 'category': 'news', 'is_verified': True},
    {'country_code': 'AE', 'name': 'الاتحاد', 'domain': 'alittihad.ae', 'category': 'news', 'is_verified': True},
    {'country_code': 'AE', 'name': 'وام (وكالة أنباء الإمارات)', 'domain': 'wam.ae', 'category': 'gov', 'is_verified': True},
    
    # =========================================================================
    # Egypt (EG)
    # =========================================================================
    {'country_code': 'EG', 'name': 'الأهرام', 'domain': 'ahram.org.eg', 'category': 'news', 'is_verified': True},
    {'country_code': 'EG', 'name': 'اليوم السابع', 'domain': 'youm7.com', 'category': 'news', 'is_verified': True},
    {'country_code': 'EG', 'name': 'المصري اليوم', 'domain': 'almasryalyoum.com', 'category': 'news', 'is_verified': True},
    {'country_code': 'EG', 'name': 'الوفد', 'domain': 'alwafd.news', 'category': 'news', 'is_verified': True},
    
    # =========================================================================
    # Jordan (JO)
    # =========================================================================
    {'country_code': 'JO', 'name': 'الرأي', 'domain': 'alrai.com', 'category': 'news', 'is_verified': True},
    {'country_code': 'JO', 'name': 'بترا (وكالة الأنباء الأردنية)', 'domain': 'petra.gov.jo', 'category': 'gov', 'is_verified': True},
    {'country_code': 'JO', 'name': 'الغد', 'domain': 'alghad.com', 'category': 'news', 'is_verified': True},
    
    # =========================================================================
    # Kuwait (KW)
    # =========================================================================
    {'country_code': 'KW', 'name': 'القبس', 'domain': 'alqabas.com', 'category': 'news', 'is_verified': True},
    {'country_code': 'KW', 'name': 'كونا (وكالة الأنباء الكويتية)', 'domain': 'kuna.net.kw', 'category': 'gov', 'is_verified': True},
    
    # =========================================================================
    # International Arabic News
    # =========================================================================
    {'country_code': None, 'name': 'الجزيرة', 'domain': 'aljazeera.net', 'category': 'news', 'is_verified': True},
    {'country_code': None, 'name': 'بي بي سي عربي', 'domain': 'bbc.com/arabic', 'category': 'news', 'is_verified': True},
    {'country_code': None, 'name': 'سكاي نيوز عربية', 'domain': 'skynewsarabia.com', 'category': 'news', 'is_verified': True},
    {'country_code': None, 'name': 'فرانس 24 عربي', 'domain': 'france24.com/ar', 'category': 'news', 'is_verified': True},
    {'country_code': None, 'name': 'RT عربي', 'domain': 'arabic.rt.com', 'category': 'news', 'is_verified': True},
    {'country_code': None, 'name': 'CNN عربي', 'domain': 'arabic.cnn.com', 'category': 'news', 'is_verified': True},
    {'country_code': None, 'name': 'DW عربي', 'domain': 'dw.com/ar', 'category': 'news', 'is_verified': True},
    
    # =========================================================================
    # Social Media Platforms (Not verified - user content)
    # =========================================================================
    {'country_code': None, 'name': 'تويتر / إكس', 'domain': 'twitter.com', 'category': 'social', 'is_verified': False},
    {'country_code': None, 'name': 'إكس', 'domain': 'x.com', 'category': 'social', 'is_verified': False},
    {'country_code': None, 'name': 'فيسبوك', 'domain': 'facebook.com', 'category': 'social', 'is_verified': False},
    {'country_code': None, 'name': 'يوتيوب', 'domain': 'youtube.com', 'category': 'social', 'is_verified': False},
    {'country_code': None, 'name': 'تيك توك', 'domain': 'tiktok.com', 'category': 'social', 'is_verified': False},
    {'country_code': None, 'name': 'إنستغرام', 'domain': 'instagram.com', 'category': 'social', 'is_verified': False},
    {'country_code': None, 'name': 'تليغرام', 'domain': 'telegram.org', 'category': 'social', 'is_verified': False},
    {'country_code': None, 'name': 'واتساب', 'domain': 'whatsapp.com', 'category': 'social', 'is_verified': False},
]


# =============================================================================
# SEEDER FUNCTIONS
# =============================================================================

def seed_countries(db, Country):
    """
    Upsert countries - idempotent (safe to run multiple times).
    
    Returns:
        tuple: (added_count, updated_count)
    """
    added, updated = 0, 0
    
    for data in COUNTRIES:
        existing = Country.query.filter_by(code=data['code']).first()
        
        if existing:
            # Update if any field changed
            changed = False
            for key, value in data.items():
                if getattr(existing, key) != value:
                    setattr(existing, key, value)
                    changed = True
            if changed:
                updated += 1
                logger.debug(f"Updated country: {data['code']}")
        else:
            # Create new
            country = Country(**data)
            db.session.add(country)
            added += 1
            logger.debug(f"Added country: {data['code']}")
    
    db.session.commit()
    logger.info(f"Countries: {added} added, {updated} updated (total in DB: {Country.query.count()})")
    return added, updated


def seed_sources(db, Country, Source):
    """
    Upsert sources - idempotent (safe to run multiple times).
    
    Returns:
        tuple: (added_count, updated_count)
    """
    added, updated = 0, 0
    
    # Build country code -> id lookup
    countries = {c.code: c.id for c in Country.query.all()}
    
    for data in SOURCES:
        # Extract and resolve country
        country_code = data.pop('country_code', None)
        country_id = countries.get(country_code) if country_code else None
        
        # Check if source exists by domain
        existing = Source.query.filter_by(domain=data['domain']).first()
        
        if existing:
            # Update if any field changed
            changed = False
            for key, value in data.items():
                if getattr(existing, key) != value:
                    setattr(existing, key, value)
                    changed = True
            if existing.country_id != country_id:
                existing.country_id = country_id
                changed = True
            if changed:
                updated += 1
                logger.debug(f"Updated source: {data['domain']}")
        else:
            # Create new
            source = Source(country_id=country_id, **data)
            db.session.add(source)
            added += 1
            logger.debug(f"Added source: {data['domain']}")
        
        # Re-add country_code for next iteration (since we popped it)
        data['country_code'] = country_code
    
    db.session.commit()
    logger.info(f"Sources: {added} added, {updated} updated (total in DB: {Source.query.count()})")
    return added, updated


def run_seed():
    """Main seed runner"""
    # Import Flask app and models
    from app import app
    from models import db, Country, Source
    
    with app.app_context():
        logger.info("=" * 60)
        logger.info("Starting seed_data.py")
        logger.info("=" * 60)
        
        # Ensure tables exist
        db.create_all()
        logger.info("Database tables verified")
        
        # Seed countries first (sources depend on them)
        c_added, c_updated = seed_countries(db, Country)
        
        # Seed sources
        s_added, s_updated = seed_sources(db, Country, Source)
        
        # Summary
        total_changes = c_added + c_updated + s_added + s_updated
        logger.info("=" * 60)
        logger.info(f"Seed complete!")
        logger.info(f"  Countries: {c_added} new, {c_updated} updated")
        logger.info(f"  Sources: {s_added} new, {s_updated} updated")
        logger.info(f"  Total changes: {total_changes}")
        logger.info("=" * 60)
        
        return {
            'countries': {'added': c_added, 'updated': c_updated},
            'sources': {'added': s_added, 'updated': s_updated}
        }


if __name__ == '__main__':
    run_seed()
