"""Flask extension initialization (db, bcrypt, CORS, rate limiter, migrations).

db and bcrypt objects are defined in models.py (kept there to avoid churn in
model imports); this module owns wiring them — and everything else — to the
app instance.
"""
import os

from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate

cors = CORS()
migrate = Migrate()


def _rate_limit_key():
    """Rate-limit per authenticated user, falling back to client IP."""
    try:
        from auth import get_current_user
        user = get_current_user()
        if user is not None:
            return f'user:{user.id}'
    except Exception:
        pass
    return get_remote_address()


limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=['200 per minute'],
    storage_uri=os.environ.get('RATELIMIT_STORAGE_URI', 'memory://'),
)

# Strict limit shared by every endpoint that spends paid API credits
SPEND_LIMIT = '10 per minute; 200 per day'


def init_extensions(app):
    from models import db, bcrypt
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)

    app.config.setdefault(
        'RATELIMIT_ENABLED',
        os.environ.get('RATELIMIT_ENABLED', 'true').lower() != 'false')
    limiter.init_app(app)

    # CORS: comma-separated allowlist via CORS_ORIGINS; defaults cover local dev
    origins = [o.strip() for o in os.environ.get(
        'CORS_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173,'
        'http://localhost:5000,http://127.0.0.1:5000'
    ).split(',') if o.strip()]
    cors.init_app(app, origins=origins)
