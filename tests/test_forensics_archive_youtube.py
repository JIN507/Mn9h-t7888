"""Items 2/4/YouTube: file forensics + AI verdict, archive + own index,
YouTube provider and agent tool."""
import io

import responses

from services import file_forensics as ff


def _jpeg_with(exif=None, xmp=None):
    from PIL import Image
    img = Image.new('RGB', (16, 16), 'blue')
    buf = io.BytesIO()
    kwargs = {}
    if exif is not None:
        kwargs['exif'] = exif
    img.save(buf, format='JPEG', **kwargs)
    data = buf.getvalue()
    if xmp:
        # APP1 XMP segment is just bytes for our scanner; append raw for the test
        data = data[:2] + b'\xff\xe1' + (len(xmp) + 31).to_bytes(2, 'big') + b'http://ns.adobe.com/xap/1.0/\x00' + xmp + data[2:]
    return data


def test_forensics_reads_exif_xmp_and_flags_ai_software(monkeypatch):
    from PIL import Image
    img = Image.new('RGB', (16, 16), 'blue')
    exif = img.getexif()
    exif[271] = 'Canon'; exif[272] = 'EOS R5'; exif[305] = 'Adobe Photoshop 25.0'; exif[315] = 'Jane Doe'
    xmp = (b'<x:xmpmeta><rdf:RDF><rdf:Description xmp:CreatorTool="Midjourney v6" '
           b'photoshop:Credit="Reuters"/></rdf:RDF></x:xmpmeta>')
    monkeypatch.setattr(ff, 'ai_detection', lambda data: {'verdict': 'human', 'ai_confidence': 0.05, 'generator': None, 'provider': 'aiornot'})
    out = ff.analyze(_jpeg_with(exif=exif.tobytes(), xmp=xmp))
    assert out['exif']['make'] == 'Canon' and out['exif']['model'] == 'EOS R5'
    assert out['exif']['artist'] == 'Jane Doe'
    assert out['xmp']['credit'] == 'Reuters' and out['xmp']['creator_tool'] == 'Midjourney v6'
    assert any('credit line in file: Reuters' in h for h in out['hints'])
    assert out['likely_ai'] is True                       # software names a generator
    assert out['ai_detection']['verdict'] == 'human'


def test_forensics_ai_detector_verdict_and_c2pa(monkeypatch):
    monkeypatch.setattr(ff, 'ai_detection', lambda data: {'verdict': 'ai', 'ai_confidence': 0.93, 'generator': 'dalle', 'provider': 'aiornot'})
    data = _jpeg_with() + b'jumb....c2pa....claim_generator\x00\x10Adobe Firefly 2.0\x00'
    out = ff.analyze(data)
    assert out['likely_ai'] is True
    assert out['c2pa']['present'] is True and 'Adobe Firefly' in out['c2pa']['claim_generator']
    assert any('AI-generated per detector (93%)' in h for h in out['hints'])
    assert ff.analyze(b'') == {'exif': {}, 'iptc': {}, 'xmp': {}, 'c2pa': {'present': False},
                               'ai_detection': None, 'hints': []}


def test_ai_detection_skipped_without_key(monkeypatch):
    monkeypatch.delenv('AIORNOT_API_KEY', raising=False)
    assert ff.ai_detection(b'x') is None
    monkeypatch.setenv('AIORNOT_API_KEY', 'k')
    monkeypatch.setenv('ORIGIN_AI_CHECK', 'false')
    assert ff.ai_detection(b'x') is None


@responses.activate
def test_archive_url_prefers_existing_capture_then_saves():
    from providers import wayback
    wayback._cache.clear()
    responses.add(responses.GET, wayback.CDX_URL, json=[['timestamp', 'statuscode'], ['20240720120000', '200']], status=200)
    got = wayback.archive_url('https://news.example/a')
    assert got == {'url': 'https://web.archive.org/web/20240720120000/https://news.example/a', 'status': 'existing'}

    responses.add(responses.GET, wayback.CDX_URL, json=[], status=200)
    responses.add(responses.GET, 'https://web.archive.org/save/https://news.example/b', status=302,
                  headers={'Location': '/web/20260921000000/https://news.example/b'})
    got = wayback.archive_url('https://news.example/b')
    assert got['status'] == 'saved' and got['url'].startswith('https://web.archive.org/web/2026')

    responses.add(responses.GET, wayback.CDX_URL, json=[], status=200)
    responses.add(responses.GET, 'https://web.archive.org/save/https://news.example/c', status=500)
    got = wayback.archive_url('https://news.example/c')
    assert got['status'] == 'failed' and got['url'].endswith('/*/https://news.example/c')


@responses.activate
def test_youtube_search_returns_dated_leads(monkeypatch):
    from providers import youtube
    monkeypatch.setenv('YOUTUBE_API_KEY', 'yt')
    responses.add(responses.GET, youtube.SEARCH_URL, json={'items': [
        {'id': {'videoId': 'IZ0ldhWOR1A'},
         'snippet': {'title': 'ابراج الكويت تحترق', 'channelTitle': 'News', 'publishedAt': '2026-03-07T18:33:42Z',
                     'thumbnails': {'high': {'url': 'https://i.ytimg.com/vi/IZ0ldhWOR1A/hqdefault.jpg'}}}},
        {'id': {'kind': 'youtube#channel'}, 'snippet': {}},
    ]}, status=200)
    got = youtube.search_videos('ابراج الكويت تحترق', published_before='2026-03-09', lang='ar')
    assert len(got) == 1
    v = got[0]
    assert v['link'] == 'https://www.youtube.com/watch?v=IZ0ldhWOR1A'
    assert v['api_date'] == '2026-03-07T18:33:42Z' and v['api_date_source'] == 'platform:youtube_api'
    assert v['image_url'].endswith('hqdefault.jpg') and v['provider'] == 'youtube_api'
    url = responses.calls[0].request.url
    assert 'publishedBefore=2026-03-09T00%3A00%3A00Z' in url and 'relevanceLanguage=ar' in url
    monkeypatch.delenv('YOUTUBE_API_KEY')
    assert youtube.configured() is False and youtube.search_videos('x') == []
