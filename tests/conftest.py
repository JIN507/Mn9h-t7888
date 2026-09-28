"""Shared test fixtures.

Environment is forced BEFORE the application is imported so the app never
touches the developer database or real API keys during tests.
"""
import os
import io
import struct
import zlib

# Must happen before `import app` anywhere in the test session
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['IMGBB_API_KEY'] = 'test-imgbb-key'
os.environ['AIORNOT_API_KEY'] = 'test-aiornot-key'
os.environ['SERPAPI_API_KEY'] = 'test-serpapi-key'
os.environ['XAI_API_KEY'] = 'test-xai-key'
os.environ['SIGHTENGINE_API_USER'] = 'test-se-user'
os.environ['SIGHTENGINE_API_SECRET'] = 'test-se-secret'
os.environ.pop('GOOGLE_APPLICATION_CREDENTIALS', None)
os.environ['RATELIMIT_ENABLED'] = 'false'
os.environ['GATE_ENABLED'] = 'false'  # the operator gate is exercised by its own tests
os.environ['QUEUE_MODE'] = 'inline'  # jobs run synchronously in tests
os.environ['BROWSER_SEARCH'] = 'false'  # never launch Chromium / hit tineye.com in tests
# Route tests exercise the ImgBB fallback path; R2 gets dedicated unit tests.
# Set to EMPTY (not pop): the app's load_dotenv() won't override existing env
# vars, so this also shields tests from real values in the developer's .env.
for _k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY',
           'R2_BUCKET', 'STORAGE_BACKEND', 'IMGBB_FALLBACK',
           'VISUAL_VERIFY', 'TINEYE_API_KEY', 'DEEPSEEK_API_KEY',
           'DEAPSEAK_KEY', 'Deapseak_key', 'DEEPSEAK_KEY'):
    os.environ[_k] = ''

import pytest  # noqa: E402


_tables_created = False


def _flask_app():
    global _tables_created
    import app as app_module
    if not _tables_created:
        from models import db
        with app_module.app.app_context():
            db.create_all()
        _tables_created = True
    return app_module.app


@pytest.fixture()
def app():
    return _flask_app()


@pytest.fixture(autouse=True)
def _reset_circuit_breakers():
    """Providers are process-wide singletons; without a reset, failures
    injected by one test open the breaker for later tests."""
    yield
    import importlib
    for mod_name in ('providers.serpapi',
                     'providers.aiornot', 'providers.sightengine',
                     'providers.imgbb', 'providers.xai', 'providers.storage',
                     'providers.yandex', 'providers.tineye',
                     'providers.wayback', 'providers.deepseek'):
        try:
            provider = getattr(importlib.import_module(mod_name), '_provider', None)
            if provider is not None:
                provider.breaker.failures = 0
        except Exception:
            pass


@pytest.fixture()
def client(app):
    return app.test_client()


def make_png_bytes():
    """Minimal valid 1x1 PNG. Pixel color is randomized so every test gets a
    unique SHA-256 — otherwise the Phase-2 result cache serves one test's
    result to the next."""
    import os as _os

    def chunk(tag, data):
        raw = tag + data
        return struct.pack('>I', len(data)) + raw + struct.pack('>I', zlib.crc32(raw) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b'\x00' + _os.urandom(3))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', idat) + chunk(b'IEND', b''))


@pytest.fixture()
def png_bytes():
    return make_png_bytes()


@pytest.fixture()
def png_file(png_bytes):
    return io.BytesIO(png_bytes)
