"""Public search-copy route: a token-gated plain URL for private R2
objects, used so Yandex can fetch the query image in production."""
import responses

from providers import storage


def test_media_token_and_public_url(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 's3cret')
    monkeypatch.delenv('PUBLIC_BASE_URL', raising=False)
    monkeypatch.delenv('RENDER_EXTERNAL_URL', raising=False)
    assert storage.public_media_url('uploads/a.jpg') is None            # local dev: no public base
    monkeypatch.setenv('RENDER_EXTERNAL_URL', 'https://tahaqqaq.onrender.com/')
    url = storage.public_media_url('uploads/a.jpg')
    tok = storage.media_token('uploads/a.jpg')
    assert url == f'https://tahaqqaq.onrender.com/api/media/{tok}/uploads/a.jpg'
    assert len(tok) == 32 and tok != storage.media_token('uploads/b.jpg')
    assert storage.key_from_presigned_url(
        'https://acct.r2.cloudflarestorage.com/tahaqqaq-media/uploads/a.jpg?X-Amz-Signature=x') == 'uploads/a.jpg'
    assert storage.key_from_presigned_url('https://gcaptain.com/x.jpg') is None


@responses.activate
def test_public_media_route_streams_object_and_rejects_bad_token(client, monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 's3cret')
    monkeypatch.setattr(storage, 'presigned_get_url',
                        lambda key, expires=None: f'https://r2.example/signed/{key}')
    responses.add(responses.GET, 'https://r2.example/signed/uploads/a.jpg', body=b'JPEGBYTES',
                  content_type='image/jpeg')
    tok = storage.media_token('uploads/a.jpg')
    r = client.get(f'/api/media/{tok}/uploads/a.jpg')
    assert r.status_code == 200
    assert r.data == b'JPEGBYTES' and r.headers['Content-Type'].startswith('image/jpeg')
    assert client.get('/api/media/deadbeef/uploads/a.jpg').status_code == 404
    assert client.get(f'/api/media/{storage.media_token("secret/x")}/secret/x').status_code == 404
