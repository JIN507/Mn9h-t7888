"""
Authentication Module

JWT-based authentication with decorators for route protection.
Supports both user and admin role verification.
"""
from functools import wraps
from flask import g, request, jsonify
from datetime import datetime, timedelta
import jwt
import logging

logger = logging.getLogger(__name__)


def get_secret_key():
    """Get secret key from config (imported here to avoid circular imports)"""
    from config import Config
    return Config.SECRET_KEY


def get_jwt_expiration():
    """Get JWT expiration days from config"""
    from config import Config
    return getattr(Config, 'JWT_EXPIRATION_DAYS', 7)


def generate_token(user):
    """
    Generate JWT token for authenticated user.
    
    Args:
        user: User model instance
        
    Returns:
        str: JWT token
    """
    payload = {
        'user_id': user.id,
        'email': user.email,
        'is_admin': user.is_admin,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(days=get_jwt_expiration())
    }
    return jwt.encode(payload, get_secret_key(), algorithm='HS256')


def decode_token(token):
    """
    Decode and validate JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        dict: Decoded payload or None if invalid
    """
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None


def get_current_user():
    """
    Get current user from request Authorization header.
    
    Looks for: Authorization: Bearer <token>
    
    Returns:
        User: User model instance or None
    """
    auth_header = request.headers.get('Authorization', '')
    
    if not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header[7:]  # Remove 'Bearer ' prefix
    payload = decode_token(token)
    
    if not payload:
        return None
    
    # Import here to avoid circular imports
    from models import User
    return User.query.get(payload.get('user_id'))


def login_required(f):
    """
    Decorator to require authenticated user.
    
    Sets g.current_user for use in route handlers.
    Returns 401 if not authenticated.
    
    Usage:
        @app.route('/api/protected')
        @login_required
        def protected_route():
            user = g.current_user
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        
        if not user:
            return jsonify({
                'error': 'يجب تسجيل الدخول',
                'error_en': 'Authentication required',
                'code': 'AUTH_REQUIRED'
            }), 401
        
        if not user.is_active:
            return jsonify({
                'error': 'الحساب معطل',
                'error_en': 'Account disabled',
                'code': 'ACCOUNT_DISABLED'
            }), 403
        
        g.current_user = user
        return f(*args, **kwargs)
    
    return decorated


def admin_required(f):
    """
    Decorator to require admin user.
    
    Sets g.current_user for use in route handlers.
    Returns 401 if not authenticated, 403 if not admin.
    
    Usage:
        @app.route('/api/admin/users')
        @admin_required
        def admin_only_route():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        
        if not user:
            return jsonify({
                'error': 'يجب تسجيل الدخول',
                'error_en': 'Authentication required',
                'code': 'AUTH_REQUIRED'
            }), 401
        
        if not user.is_active:
            return jsonify({
                'error': 'الحساب معطل',
                'error_en': 'Account disabled',
                'code': 'ACCOUNT_DISABLED'
            }), 403
        
        if not user.is_admin:
            return jsonify({
                'error': 'صلاحيات المسؤول مطلوبة',
                'error_en': 'Admin access required',
                'code': 'ADMIN_REQUIRED'
            }), 403
        
        g.current_user = user
        return f(*args, **kwargs)
    
    return decorated


def optional_auth(f):
    """
    Decorator for optional authentication.
    
    Sets g.current_user if authenticated, None otherwise.
    Does not block unauthenticated requests.
    
    Usage:
        @app.route('/api/public')
        @optional_auth
        def public_route():
            user = g.current_user  # May be None
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        g.current_user = get_current_user()
        return f(*args, **kwargs)
    
    return decorated


def user_owns_resource(model_class, resource_id, user_id_field='user_id'):
    """
    Check if current user owns a resource.
    
    Args:
        model_class: SQLAlchemy model class
        resource_id: ID of the resource to check
        user_id_field: Name of the user_id column (default 'user_id')
        
    Returns:
        Resource instance if owned by current user, None otherwise
    """
    resource = model_class.query.get(resource_id)
    
    if not resource:
        return None
    
    # Check ownership
    resource_user_id = getattr(resource, user_id_field, None)
    
    if resource_user_id and resource_user_id != g.current_user.id:
        # Admin can access any resource
        if not g.current_user.is_admin:
            return None
    
    return resource


def ensure_user_access(resource, user_id_field='user_id'):
    """
    Ensure current user can access a resource.
    
    Args:
        resource: Model instance to check
        user_id_field: Name of the user_id column
        
    Returns:
        bool: True if user can access, False otherwise
    """
    if not resource:
        return False
    
    resource_user_id = getattr(resource, user_id_field, None)
    
    # Resource has no user scope - allow access
    if resource_user_id is None:
        return True
    
    # User owns resource
    if resource_user_id == g.current_user.id:
        return True
    
    # Admin can access all
    if g.current_user.is_admin:
        return True
    
    return False
