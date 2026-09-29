"""Queued jobs re-sign our own storage links before using them."""
from providers import storage


def test_foreign_url_is_returned_unchanged(monkeypatch):
    monkeypatch.setattr(storage, 'is_configured', lambda: True)
    assert storage.refreshed_url('https://example.com/a.jpg') == 'https://example.com/a.jpg'
    assert storage.refreshed_url(None) is None


def test_own_presigned_url_is_signed_again(monkeypatch):
    seen = []
    monkeypatch.setattr(storage, 'is_configured', lambda: True)
    monkeypatch.setattr(storage, 'presigned_get_url',
                        lambda key: seen.append(key) or 'https://fresh.example/' + key)
    old = 'https://acct.r2.cloudflarestorage.com/bucket/uploads/x.jpg?X-Amz-Expires=900'
    assert storage.refreshed_url(old) == 'https://fresh.example/uploads/x.jpg'
    assert seen == ['uploads/x.jpg']


def test_old_url_is_kept_when_signing_fails(monkeypatch):
    monkeypatch.setattr(storage, 'is_configured', lambda: True)
    monkeypatch.setattr(storage, 'presigned_get_url', lambda key: None)
    old = 'https://acct.r2.cloudflarestorage.com/bucket/uploads/x.jpg?X-Amz-Expires=900'
    assert storage.refreshed_url(old) == old
