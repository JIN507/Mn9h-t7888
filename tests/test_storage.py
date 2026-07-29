"""R2 storage provider + host_image backend selection."""
import base64
from unittest.mock import MagicMock, patch

import responses

R2_ENV = {
    'R2_ACCOUNT_ID': 'acct123',
    'R2_ACCESS_KEY_ID': 'key123',
    'R2_SECRET_ACCESS_KEY': 'secret123',
    'R2_BUCKET': 'tahaqqaq-media',
}

PRESIGNED = 'https://acct123.r2.cloudflarestorage.com/tahaqqaq-media/uploads/x.png?X-Amz-Signature=abc'


def _r2(monkeypatch):
    for k, v in R2_ENV.items():
        monkeypatch.setenv(k, v)


def _fake_client():
    client = MagicMock()
    client.generate_presigned_url.return_value = PRESIGNED
    return client


def test_storage_unconfigured_without_env(app):
    from providers import storage
    assert storage.is_configured() is False


def test_upload_image_puts_private_object_and_presigns(app, monkeypatch, png_bytes):
    _r2(monkeypatch)
    from providers import storage
    assert storage.is_configured() is True

    client = _fake_client()
    with patch.object(storage, '_get_client', return_value=client):
        url = storage.upload_image(png_bytes)

    assert url == PRESIGNED
    put = client.put_object.call_args.kwargs
    assert put['Bucket'] == 'tahaqqaq-media'
    assert put['Key'].startswith('uploads/') and put['Key'].endswith('.png')
    assert put['ContentType'] == 'image/png'  # sniffed from magic bytes
    presign = client.generate_presigned_url.call_args
    assert presign.args[0] == 'get_object'
    assert presign.kwargs['ExpiresIn'] == 900  # 15 minutes


def test_upload_image_accepts_base64_and_data_urls(app, monkeypatch, png_bytes):
    _r2(monkeypatch)
    from providers import storage
    client = _fake_client()
    b64 = base64.b64encode(png_bytes).decode()

    with patch.object(storage, '_get_client', return_value=client):
        assert storage.upload_image(b64) == PRESIGNED
        assert storage.upload_image(f'data:image/png;base64,{b64}') == PRESIGNED

    for call in client.put_object.call_args_list:
        assert call.kwargs['Body'] == png_bytes  # decoded to raw bytes


def test_host_image_prefers_r2(app, monkeypatch, png_bytes):
    _r2(monkeypatch)
    from providers import storage
    from services.storage_service import host_image
    with patch.object(storage, '_get_client', return_value=_fake_client()):
        assert host_image(png_bytes) == PRESIGNED


@responses.activate
def test_host_image_falls_back_to_imgbb_without_r2(app, png_bytes):
    from services.storage_service import host_image
    responses.add(responses.POST, 'https://api.imgbb.com/1/upload',
                  json={'success': True,
                        'data': {'url': 'https://i.ibb.co/fallback.png'}},
                  status=200)
    assert host_image(png_bytes) == 'https://i.ibb.co/fallback.png'


@responses.activate
def test_host_image_rollback_switch(app, monkeypatch, png_bytes):
    _r2(monkeypatch)
    monkeypatch.setenv('STORAGE_BACKEND', 'imgbb')
    from services.storage_service import host_image
    responses.add(responses.POST, 'https://api.imgbb.com/1/upload',
                  json={'success': True,
                        'data': {'url': 'https://i.ibb.co/rollback.png'}},
                  status=200)
    # R2 fully configured, but the rollback switch wins
    assert host_image(png_bytes) == 'https://i.ibb.co/rollback.png'


def test_host_image_r2_failure_no_fallback(app, monkeypatch, png_bytes):
    _r2(monkeypatch)
    monkeypatch.setenv('IMGBB_FALLBACK', 'false')
    from providers import storage
    from services.storage_service import host_image

    broken = MagicMock()
    broken.put_object.side_effect = RuntimeError('bucket gone')
    with patch.object(storage, '_get_client', return_value=broken):
        assert host_image(png_bytes) is None
