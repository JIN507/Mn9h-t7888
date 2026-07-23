"""Auth + user-scoped data + public catalog endpoints."""
import logging

from flask import Blueprint, g, jsonify, request

from auth import login_required, admin_required, generate_token
from models import db, User, Country, Source, Keyword, Search, Analysis

logger = logging.getLogger(__name__)
bp = Blueprint('auth', __name__)


@bp.route('/api/auth/register', methods=['POST'])
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
        logger.info(f'[!] Register error: {e}')
        return jsonify({'error': 'حدث خطأ في التسجيل', 'code': 'REGISTER_ERROR'}), 500


@bp.route('/api/auth/login', methods=['POST'])
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
        logger.info(f'[!] Login error: {e}')
        return jsonify({'error': 'حدث خطأ في تسجيل الدخول', 'code': 'LOGIN_ERROR'}), 500


@bp.route('/api/auth/me', methods=['GET'])
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

@bp.route('/api/user/searches', methods=['GET'])
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


@bp.route('/api/user/analyses', methods=['GET'])
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


@bp.route('/api/user/keywords', methods=['GET'])
@login_required
def get_user_keywords():
    """Get current user's saved keywords"""
    from flask import g
    
    keywords = Keyword.query.filter_by(user_id=g.current_user.id, is_active=True).all()
    
    return jsonify({
        'success': True,
        'keywords': [k.to_dict() for k in keywords]
    })


@bp.route('/api/user/keywords', methods=['POST'])
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


@bp.route('/api/user/keywords/<keyword_id>', methods=['DELETE'])
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

@bp.route('/api/countries', methods=['GET'])
def get_countries():
    """Get all active countries (public - no auth required)"""
    countries = Country.query.filter_by(is_active=True).order_by(Country.name_ar).all()
    return jsonify({
        'success': True,
        'countries': [c.to_dict() for c in countries]
    })


@bp.route('/api/sources', methods=['GET'])
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
