"""Flask extension initialization (db, bcrypt, CORS).

db and bcrypt objects are defined in models.py (kept there to avoid churn in
model imports); this module owns wiring them — and everything else — to the
app instance.
"""
import os

from flask_cors import CORS

cors = CORS()


def init_extensions(app):
    from models import db, bcrypt
    db.init_app(app)
    bcrypt.init_app(app)

    # CORS: comma-separated allowlist via CORS_ORIGINS; defaults cover local dev
    origins = [o.strip() for o in os.environ.get(
        'CORS_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173,'
        'http://localhost:5000,http://127.0.0.1:5000'
    ).split(',') if o.strip()]
    cors.init_app(app, origins=origins)
