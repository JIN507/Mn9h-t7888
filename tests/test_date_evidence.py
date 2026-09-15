"""Origin engine Tier 3: publication-date evidence and resolution."""
from services import date_evidence as de


# ------------------------------------------------------------- parse_date

def test_parse_date_iso_and_epoch():
    assert de.to_iso(de.parse_date('2021-03-04T10:00:00Z')) == '2021-03-04T10:00:00Z'
    assert de.to_iso(de.parse_date('2021-03-04T12:00:00+02:00')) == '2021-03-04T10:00:00Z'
    assert de.to_iso(de.parse_date('1614852000')) == '2021-03-04T10:00:00Z'
    assert de.to_iso(de.parse_date('1614852000000')) == '2021-03-04T10:00:00Z'


def test_parse_date_rejects_future_and_garbage():
    assert de.parse_date('2999-01-01') is None
    assert de.parse_date('not a date') is None
    assert de.parse_date('') is None
    assert de.parse_date(None) is None


def test_parse_date_human_formats():
    assert de.to_iso(de.parse_date('4 March 2021')).startswith('2021-03-04')
    assert de.to_iso(de.parse_date('March 4, 2021')).startswith('2021-03-04')


# ------------------------------------------------------------ extractors

def test_platform_date_twitter_snowflake_is_exact():
    # id 1700000000000000000 -> 2023-09-08T04:15:59Z
    ev = de.platform_date('https://x.com/user/status/1700000000000000000')
    assert ev == [{'date': '2023-09-08T04:15:59Z', 'confidence': 0.98,
                   'source': 'platform:twitter_snowflake'}]
    assert de.platform_date('https://example.com/status/1700000000000000000') == []


def test_url_path_date():
    ev = de.url_path_date('https://news.example/2023/05/14/story-title')
    assert ev[0]['date'] == '2023-05-14T00:00:00Z'
    assert ev[0]['confidence'] == 0.65
    month = de.url_path_date('https://news.example/2023/05/story')
    assert month[0]['date'] == '2023-05-01T00:00:00Z'
    assert month[0]['confidence'] < ev[0]['confidence']
    assert de.url_path_date('https://news.example/story') == []


def test_html_date_evidence_meta_and_jsonld():
    html = """<html><head>
      <meta property="article:published_time" content="2020-06-01T08:30:00Z">
      <script type="application/ld+json">
        {"@type": "NewsArticle", "datePublished": "2020-06-01T08:30:00+00:00"}
      </script></head><body>old</body></html>"""
    ev = de.html_date_evidence(html, 'https://news.example/a')
    sources = {e['source'] for e in ev}
    assert 'meta:article:published_time' in sources
    assert 'jsonld:datePublished' in sources
    assert all(e['date'].startswith('2020-06-01') for e in ev)


def test_html_date_evidence_text_fallback_is_weak():
    html = '<html><body><p>Posted on 2019-11-20 by staff</p></body></html>'
    ev = de.html_date_evidence(html, 'https://blog.example/p')
    assert ev, 'text pattern fallback should fire when nothing else exists'
    weakest = min(ev, key=lambda e: e['confidence'])
    assert weakest['confidence'] <= 0.45


def test_header_date_evidence():
    ev = de.header_date_evidence({'Last-Modified': 'Wed, 21 Oct 2015 07:28:00 GMT'})
    assert ev[0]['date'].startswith('2015-10-21')
    assert ev[0]['confidence'] == 0.35
    assert de.header_date_evidence({}) == []


def test_exif_capture_date(tmp_path):
    from PIL import Image
    img = Image.new('RGB', (8, 8), 'red')
    exif = img.getexif()
    exif[36867] = '2018:07:04 12:00:00'
    path = tmp_path / 'x.jpg'
    img.save(path, exif=exif.tobytes())
    assert de.exif_capture_date(path.read_bytes()) == '2018-07-04T12:00:00Z'
    assert de.exif_capture_date(b'not an image') is None


# --------------------------------------------------------------- resolve

def test_resolve_prefers_highest_confidence_and_corroborates():
    ev = [
        {'date': '2020-06-01T08:30:00Z', 'confidence': 0.95, 'source': 'meta:article:published_time'},
        {'date': '2020-06-01T00:00:00Z', 'confidence': 0.65, 'source': 'url:path_date'},
        {'date': '2021-01-01T00:00:00Z', 'confidence': 0.45, 'source': 'text:pattern_match'},
    ]
    r = de.resolve_published_at(ev)
    assert r['published_at'] == '2020-06-01T08:30:00Z'
    assert r['confidence'] == 0.99  # 0.95 + corroboration bonus, capped
    assert r['is_upper_bound'] is False


def test_resolve_bound_overrides_weak_later_page_claim_only():
    """Weak page date (htmldate 0.8) after an archive capture -> the bound
    wins. A first-class publish tag (>=0.9) is NOT overridden: archive
    captures of dynamic pages predate the content shown on them (live
    finding: a 2016 capture of a /topic/ page vs a 2024 photo)."""
    bounds = [{'date': '2019-05-05T00:00:00Z', 'confidence': 0.6,
               'source': 'wayback:first_capture'}]
    weak = [{'date': '2022-03-01T00:00:00Z', 'confidence': 0.8,
             'source': 'htmldate:original'}]
    r = de.resolve_published_at(weak, bounds)
    assert r['published_at'] == '2019-05-05T00:00:00Z'
    assert r['is_upper_bound'] is True
    assert r['bound']['source'] == 'wayback:first_capture'

    strong = [{'date': '2022-03-01T00:00:00Z', 'confidence': 0.95,
               'source': 'meta:article:published_time'}]
    r = de.resolve_published_at(strong, bounds)
    assert r['published_at'] == '2022-03-01T00:00:00Z'
    assert r['is_upper_bound'] is False


def test_fresh_dates_are_capped():
    """A live listing page 'published' within the last 36 h is not evidence."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    html = f'<html><head><meta property="article:published_time" content="{today}"></head></html>'
    ev = de.html_date_evidence(html, 'https://news.example/topic/x')
    assert ev and all(e['confidence'] <= 0.3 for e in ev)
    assert ev[0]['source'].endswith('?fresh')


def test_resolve_bound_only_and_nothing():
    bounds = [{'date': '2019-05-05T00:00:00Z', 'confidence': 0.6,
               'source': 'wayback:first_capture'}]
    r = de.resolve_published_at([], bounds)
    assert r['published_at'] == '2019-05-05T00:00:00Z'
    assert r['is_upper_bound'] is True
    empty = de.resolve_published_at([], [])
    assert empty['published_at'] is None and empty['confidence'] == 0.0
