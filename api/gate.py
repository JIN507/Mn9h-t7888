"""The front door: one operator account guards the whole app.

Credentials come from the environment (APP_LOGIN_USER / APP_LOGIN_PASSWORD,
never committed). A successful login sets an HttpOnly, signed cookie; every
/api/* request except the gate itself, health and the public media route
must carry it. GATE_ENABLED=false turns the door off (tests, local tooling).
"""
import hmac
import logging
import os

from flask import Blueprint, jsonify, request, current_app, make_response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)
bp = Blueprint('gate', __name__)

COOKIE = 'tq_gate'
MAX_AGE_S = 30 * 24 * 3600
OPEN_PREFIXES = ('/api/gate/', '/api/health', '/api/media/')


def enabled():
    return os.environ.get('GATE_ENABLED', 'true').lower() != 'false'


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='tq-gate')


def _expected():
    return os.environ.get('APP_LOGIN_USER', 'admin'), os.environ.get('APP_LOGIN_PASSWORD', '')


def current_operator():
    """Username from a valid gate cookie, else None."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        return _serializer().loads(token, max_age=MAX_AGE_S)
    except (BadSignature, SignatureExpired):
        return None


@bp.before_app_request
def _guard():
    if not enabled():
        return None
    path = request.path or ''
    if not path.startswith('/api/') or any(path.startswith(p) for p in OPEN_PREFIXES):
        return None
    if request.method == 'OPTIONS':
        return None
    if current_operator():
        return None
    return jsonify({'error': 'يلزم تسجيل الدخول', 'success': False, 'gate': True}), 401


@bp.route('/api/gate/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    user = str(data.get('username') or '').strip()
    password = str(data.get('password') or '')
    exp_user, exp_pass = _expected()
    if not exp_pass:
        return jsonify({'error': 'كلمة المرور غير مهيّأة على الخادم (APP_LOGIN_PASSWORD)', 'success': False}), 500
    ok = hmac.compare_digest(user, exp_user) and hmac.compare_digest(password, exp_pass)
    if not ok:
        logger.info('gate: failed login for %r', user[:40])
        return jsonify({'error': 'اسم المستخدم أو كلمة المرور غير صحيحة', 'success': False}), 401
    resp = make_response(jsonify({'success': True, 'username': user}))
    resp.set_cookie(COOKIE, _serializer().dumps(user), max_age=MAX_AGE_S, httponly=True,
                    samesite='Lax', secure=request.is_secure)
    return resp


@bp.route('/api/gate/logout', methods=['POST'])
def logout():
    resp = make_response(jsonify({'success': True}))
    resp.delete_cookie(COOKIE)
    return resp


@bp.route('/api/gate/me', methods=['GET'])
def me():
    if not enabled():
        return jsonify({'success': True, 'username': 'open', 'gate': False})
    who = current_operator()
    if not who:
        return jsonify({'success': False, 'gate': True}), 401
    return jsonify({'success': True, 'username': who, 'gate': True})
