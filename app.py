"""Tahaqqaq / Bahith Al-Suwar — application entrypoint (app factory only).

Routes live in api/ (blueprints), business logic in services/, external API
clients in providers/.
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s')

from datetime import datetime  # noqa: E402

from flask import Flask, render_template, send_from_directory  # noqa: E402

from config import Config  # noqa: E402
from extensions import init_extensions  # noqa: E402
from models import db  # noqa: E402


def create_app(config_object=Config):
    """Application factory."""
    app = Flask(
        __name__,
        static_folder='frontend/dist/assets',
        static_url_path='/assets',
        template_folder='frontend/dist',
    )
    app.config.from_object(config_object)
    app.config['UPLOAD_FOLDER'] = 'uploads'
    app.config['MAX_CONTENT_LENGTH'] = 256 * 1024 * 1024  # 256 MB
    os.makedirs('uploads', exist_ok=True)

    init_extensions(app)

    from api import register_blueprints
    register_blueprints(app)
    _register_spa(app)

    # Schema is managed by Alembic migrations: `flask db upgrade`
    # (see docs/MIGRATIONS.md — no db.create_all in production paths)
    return app


def _register_spa(app):
    """Serve the built React SPA from frontend/dist."""

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/<path:path>')
    def catch_all(path):
        if path and os.path.exists(os.path.join(app.static_folder, path)):
            return send_from_directory(app.static_folder, path)
        return render_template('index.html')

    @app.context_processor
    def inject_now():
        return {'now': datetime.now()}


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
