"""Google refuses some image hosts (Cloudflare R2, 2026-09-22): SerpAPI then
answers 200 + "hasn't returned any results" — the same text as for a 404
URL. That answer is a fetch failure: retry through another URL variant of
the same image, report it honestly, never as a clean zero. Text search
runs on SerpAPI Google (Zenserp quota is gone). Leads from text/Grok
search get inspected automatically."""
import responses

from providers import serpapi
from services import origin_engine as oe

SERP = 'https://serpapi.com/search.json'
NO_RESULTS = {'search_metadata': {'status': 'Success'},
              'search_information': {'images_results_state': 'Fully empty'},
              'error': "Google Lens hasn't returned any results for this query."}


@responses.activate
def test_lens_no_results_answer_raises_a_distinct_error(monkeypatch):
    monkeypatch.setenv('SERPAPI_API_KEY', 'k')
    responses.add(responses.GET, SERP, json=NO_RESULTS, status=200)
    try:
        serpapi.lens_matches('https://pub-1.r2.dev/u/a.jpg', 'visual_matches')
        assert False, 'expected SerpApiNoResults'
    except serpapi.SerpApiNoResults:
        pass
    # a genuinely empty section stays an empty list
    responses.add(responses.GET, SERP, json={'exact_matches': []}, status=200)
    assert serpapi.lens_matches('https://pbs.twimg.com/a.jpg', 'exact_matches') == []


def test_google_variant_order_direct_then_copies_then_proxy(monkeypatch):
    monkeypatch.setattr(oe, 'LENS_IMAGE_PROXY', 'wsrv')
    monkeypatch.setattr(oe, 'GOOGLE_REFUSED_HOSTS', ())
    got = oe.google_image_urls('https://pub-1.r2.dev/uploads/a.jpg',
                               ['https://pub-1.r2.dev/uploads/small.jpg', 'https://i.ibb.co/x/q.jpg'])
    assert got == ['https://pub-1.r2.dev/uploads/a.jpg', 'https://pub-1.r2.dev/uploads/small.jpg',
                   'https://i.ibb.co/x/q.jpg',
                   'https://wsrv.nl/?url=pub-1.r2.dev/uploads/a.jpg&output=jpg&filename=q.jpg']
    # a host known to be blocked goes last
    monkeypatch.setattr(oe, 'GOOGLE_REFUSED_HOSTS', ('r2.dev',))
    got = oe.google_image_urls('https://pub-1.r2.dev/uploads/a.jpg', ['https://i.ibb.co/x/q.jpg'])
    assert got[0] == 'https://i.ibb.co/x/q.jpg' and got[-1] == 'https://pub-1.r2.dev/uploads/a.jpg'
    monkeypatch.setattr(oe, 'LENS_IMAGE_PROXY', 'none')
    monkeypatch.setattr(oe, 'GOOGLE_REFUSED_HOSTS', ())
    assert oe.google_image_urls('https://pub-1.r2.dev/uploads/a.jpg') == ['https://pub-1.r2.dev/uploads/a.jpg']


def test_google_fallback_copies_small_reencoded_then_imgbb(monkeypatch):
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new('RGB', (1600, 900), (90, 120, 200)).save(buf, format='JPEG')
    big = buf.getvalue()
    small = oe.small_copy_bytes(big)
    assert small and Image.open(io.BytesIO(small)).size == (512, 288)
    assert oe.small_copy_bytes(small) is None                     # already small
    hosted = []
    import services.storage_service as ss
    import providers.imgbb as imgbb
    monkeypatch.setattr(ss, 'host_image', lambda data, filename_hint='x': hosted.append(len(data)) or
                        'https://acct.r2.cloudflarestorage.com/b/uploads/s.jpg?X-Amz-Signature=1')
    monkeypatch.setattr(imgbb, 'upload_to_imgbb', lambda data, expiration=None: 'https://i.ibb.co/x/s.jpg')
    monkeypatch.setenv('R2_PUBLIC_BASE_URL', 'https://pub-1.r2.dev')
    monkeypatch.setenv('IMGBB_API_KEY', 'k')
    monkeypatch.setenv('SEARCH_COPY', 'imgbb')
    assert oe.google_fallback_copies(big, 'https://pub-1.r2.dev/uploads/a.jpg') == (
        'https://pub-1.r2.dev/uploads/s.jpg', 'https://i.ibb.co/x/s.jpg')
    assert hosted == [len(small)]
    monkeypatch.setenv('SEARCH_COPY', 'none')
    assert oe.google_fallback_copies(big, 'https://pub-1.r2.dev/uploads/a.jpg') == ()


def test_lens_retry_switches_host_on_no_results_and_reports_fetch_failure(monkeypatch):
    monkeypatch.setattr(oe, 'LENS_RETRY_DELAY_S', 0)
    calls = []

    def lens(image_url, lens_type, hl='ar', country='sa', no_cache=False):
        calls.append((image_url, no_cache))
        if image_url == 'direct':
            raise serpapi.SerpApiNoResults('not fetched')
        return [{'link': 'https://ok.example', 'match_type': 'exact', 'provider': 'google_lens'}]
    monkeypatch.setattr(oe, 'lens_matches', lens)
    got = oe._lens_exact_with_retry('direct', 'en', 'us', alternates=('proxy',))
    assert got and calls == [('direct', False), ('proxy', True)]

    # every variant refused -> each tried ONCE -> SerpApiNoResults propagates -> fetch_failed
    calls.clear()

    def refused(image_url, lens_type, **k):
        calls.append(image_url)
        raise serpapi.SerpApiNoResults('x')
    monkeypatch.setattr(oe, 'lens_matches', refused)
    try:
        oe._lens_exact_with_retry('direct', 'en', 'us', alternates=('small', 'proxy'))
        assert False
    except serpapi.SerpApiNoResults:
        pass
    assert calls == ['direct', 'small', 'proxy']
    st = oe._failure_status(serpapi.SerpApiNoResults('x'))
    assert st['ok'] is False and st['note'] == 'fetch_failed'

    # a genuine empty + no-results mix is NOT a fetch failure
    seq = iter([[], serpapi.SerpApiNoResults('x'), []])

    def mixed(*a, **k):
        v = next(seq)
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(oe, 'lens_matches', mixed)
    assert oe._lens_exact_with_retry('direct', 'en', 'us') == []


@responses.activate
def test_text_search_prefers_serpapi_google_and_falls_back_to_zenserp(monkeypatch):
    monkeypatch.setenv('SERPAPI_API_KEY', 'k')
    monkeypatch.setenv('ZENSERP_API_KEY', 'z')
    responses.add(responses.GET, SERP, json={'organic_results': [
        {'link': 'https://x.com/svs9111/status/570514380095299584', 'title': 'صورة قديمة', 'snippet': 's', 'date': 'Feb 25, 2015'},
        {'position': 2}]}, status=200)
    got = oe.text_search_results('عبدالمجيد عبدالله نبيل شعيل', hl='ar', gl='sa')
    assert got == [{'link': 'https://x.com/svs9111/status/570514380095299584', 'title': 'صورة قديمة',
                    'snippet': 's', 'date': 'Feb 25, 2015'}]
    assert 'engine=google' in responses.calls[0].request.url and 'hl=ar' in responses.calls[0].request.url
    # SerpAPI down -> Zenserp
    responses.add(responses.GET, SERP, status=429, body='quota')
    responses.add(responses.GET, 'https://app.zenserp.com/api/v2/search',
                  json={'organic': [{'url': 'https://a.example/p', 'title': 'A', 'description': 'd'}]}, status=200)
    got = oe.text_search_results('q')
    assert got[0]['link'] == 'https://a.example/p'
    # both down -> raises (the tool reports an error, never silent)
    responses.add(responses.GET, SERP, status=429, body='quota')
    responses.add(responses.GET, 'https://app.zenserp.com/api/v2/search', status=403, json={'error': 'Not enough requests.'})
    try:
        oe.text_search_results('q')
        assert False
    except RuntimeError as e:
        assert 'serpapi' in str(e) and 'zenserp' in str(e)


def test_agent_auto_inspects_social_leads_from_text_and_grok(monkeypatch):
    from services import origin_agent as oa
    inv = oa.Investigation('https://img.example/q.jpg', {'phash': None}, lambda m: None, dict(oa.DEFAULT_BUDGET))
    inspected = []

    def fake_inspect(cands, strict=False):
        inspected.extend(c['url'] for c in cands)
        return [{'url': c['url'], 'domain': oe.domain_of(c['url']), 'title': '', 'published_at': None,
                 'confidence': 0, 'visual': {'verdict': 'unverified'}, 'evidence': [], 'match_type': 'organic',
                 'providers': ['web_search']} for c in cands]
    monkeypatch.setattr(inv, 'inspect', fake_inspect)
    leads = [{'url': 'https://ar.wikipedia.org/wiki/x', 'title': 'w'},
             {'url': 'https://x.com/svs9111/status/570514380095299584', 'title': 't'},
             {'url': 'https://news.example/2015/02/story', 'title': 'n'}]
    briefs = oa._inspect_leads(inv, leads, 'web_search')
    assert inspected[0] == 'https://x.com/svs9111/status/570514380095299584'   # social first
    assert len(briefs) == len(inspected) == 3
    assert oa._inspect_leads(inv, leads, 'grok') == []                        # already known


def test_prompt_never_lets_the_ai_detector_end_the_search():
    from services import origin_agent as oa
    assert 'no real-world origin' not in oa.SYSTEM_PROMPT
    assert 'WEAK signal' in oa.SYSTEM_PROMPT and 'fetch_failed' in oa.SYSTEM_PROMPT
