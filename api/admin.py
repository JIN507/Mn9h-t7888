"""Admin-only catalog & user management endpoints."""
import logging
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import case, func

from auth import admin_required
from models import db, User, Country, Source, UserFile, ProviderCall

logger = logging.getLogger(__name__)
bp = Blueprint('admin', __name__)


@bp.route('/api/admin/provider-usage', methods=['GET'])
@admin_required
def admin_provider_usage():
    """API spend dashboard: per-provider call counts, errors, latency."""
    days = min(request.args.get('days', 30, type=int), 365)
    since = datetime.utcnow() - timedelta(days=days)

    provider_rows = (
        db.session.query(
            ProviderCall.provider,
            func.count(ProviderCall.id).label('calls'),
            func.sum(case((ProviderCall.ok.is_(False), 1), else_=0)).label('errors'),
            func.avg(ProviderCall.latency_ms).label('avg_latency_ms'),
            func.max(ProviderCall.created_at).label('last_call'),
        )
        .filter(ProviderCall.created_at >= since)
        .group_by(ProviderCall.provider)
        .order_by(func.count(ProviderCall.id).desc())
        .all())

    daily_rows = (
        db.session.query(
            func.date(ProviderCall.created_at).label('day'),
            func.count(ProviderCall.id).label('calls'),
        )
        .filter(ProviderCall.created_at >= since)
        .group_by(func.date(ProviderCall.created_at))
        .order_by(func.date(ProviderCall.created_at))
        .all())

    return jsonify({
        'success': True,
        'days': days,
        'providers': [{
            'provider': r.provider,
            'calls': int(r.calls or 0),
            'errors': int(r.errors or 0),
            'avg_latency_ms': round(float(r.avg_latency_ms), 1) if r.avg_latency_ms else None,
            'last_call': r.last_call.isoformat() if r.last_call else None,
        } for r in provider_rows],
        'daily': [{'day': str(r.day), 'calls': int(r.calls or 0)}
                  for r in daily_rows],
    })


@bp.route('/api/admin/countries', methods=['GET'])
@admin_required
def admin_get_countries():
    """Admin: Get all countries including inactive"""
    countries = Country.query.order_by(Country.code).all()
    return jsonify({
        'success': True,
        'countries': [c.to_dict() for c in countries]
    })


@bp.route('/api/admin/countries', methods=['POST'])
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


@bp.route('/api/admin/countries/<country_id>', methods=['PUT'])
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


@bp.route('/api/admin/sources', methods=['GET'])
@admin_required
def admin_get_sources():
    """Admin: Get all sources including inactive"""
    sources = Source.query.order_by(Source.domain).all()
    return jsonify({
        'success': True,
        'sources': [s.to_dict(include_country=True) for s in sources]
    })


@bp.route('/api/admin/sources', methods=['POST'])
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


@bp.route('/api/admin/sources/<source_id>', methods=['PUT'])
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


@bp.route('/api/admin/sources/<source_id>', methods=['DELETE'])
@admin_required
def admin_delete_source(source_id):
    """Admin: Soft delete a source (set inactive)"""
    source = Source.query.get(source_id)
    if not source:
        return jsonify({'error': 'المصدر غير موجود'}), 404
    
    source.is_active = False
    db.session.commit()
    
    return jsonify({'success': True})


@bp.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    """Admin: Get all users"""
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({
        'success': True,
        'users': [u.to_dict() for u in users]
    })


@bp.route('/api/admin/users/<user_id>/toggle-active', methods=['POST'])
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


@bp.route('/api/admin/users/<user_id>/reset-password', methods=['POST'])
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


@bp.route('/api/admin/files', methods=['GET'])
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
