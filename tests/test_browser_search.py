"""Browser-driven engines: pure-Python parsers pinned to real markup
captured from tineye.com and bing.com (the Playwright fetch itself is not
exercised here — it needs Chromium and the live sites)."""
from providers import browser_search as bs

TINEYE_HTML = """
<main>
 <p>22 results — TinEye searched 85.7 billion images for: x.jpeg</p>
 <p>First indexed by TinEye on July 24, 2024</p>
 <div class="flex flex-col gap-8">
  <div class="w-full">
   <h4><a class="font-bold" href="https://www.wionews.com/indian-coast-guard"
          data-test="match-link">wionews.com</a></h4>
   <p><span> Filename: <a href="https://www.wionews.com/img/444618-icggoa.png">444618-icggoa.png</a></span>
      <span class="block">1200 x 675, 20.7 kB</span></p>
   <p><a href="https://www.wionews.com/indian-coast-guard">indian-coast-guard</a>
      <span data-test="crawl-date">Jul 24, 2024</span></p>
  </div>
  <div class="w-full">
   <h4><a class="font-bold" href="https://gcaptain.com/major-fire/" data-test="match-link">gcaptain.com</a></h4>
   <p><span> Filename: <a href="https://gcaptain.com/wp-content/uploads/2024/07/Maersk-Frankfurt-Fire.jpeg">Maersk-Frankfurt-Fire.jpeg</a></span>
      <span class="block">1600 x 1200, 153.4 kB</span></p>
   <p><a href="https://gcaptain.com/major-fire/">major-fire/</a>
      <span data-test="crawl-date">Jun 19, 2026</span></p>
  </div>
  <div class="similar-match"><a href="https://www.shutterstock.com/pic-1">stock (ignored)</a></div>
 </div>
</main>
"""


def test_parse_tineye_html_matches_dates_and_first_indexed():
    got = bs.parse_tineye_html(TINEYE_HTML)
    assert [m['link'] for m in got] == ['https://www.wionews.com/indian-coast-guard',
                                        'https://gcaptain.com/major-fire/']
    first = got[0]
    assert first['provider'] == 'tineye_web' and first['match_type'] == 'exact'
    assert first['crawl_date'] == '2024-07-24T00:00:00Z'
    assert first['first_indexed'] == '2024-07-24T00:00:00Z'
    assert first['image_url'] == 'https://www.wionews.com/img/444618-icggoa.png'
    assert first['image_size'] == [1200, 675]
    assert got[1]['crawl_date'] == '2026-06-19T00:00:00Z'
    assert got[1]['image_size'] == [1600, 1200]
    assert bs.parse_tineye_html('') == []


def test_unwrap_bing_redirect():
    import base64
    real = 'https://gcaptain.com/major-fire/'
    token = 'a1' + base64.urlsafe_b64encode(real.encode()).decode().rstrip('=')
    wrapped = f'https://www.bing.com/ck/a?!&&p=abc&u={token}&ntb=1'
    assert bs.unwrap_bing_redirect(wrapped) == real
    assert bs.unwrap_bing_redirect(real) == real
    assert bs.unwrap_bing_redirect('https://www.bing.com/ck/a?u=a1!!!') is None
    assert bs.unwrap_bing_redirect(None) is None


def test_parse_bing_html_caption_and_leads():
    import base64
    real = 'https://www.worldcargonews.com/2024/07/fire/'
    token = 'a1' + base64.urlsafe_b64encode(real.encode()).decode().rstrip('=')
    html = f"""
    <ol id="b_results">
      <li class="b_algo"><h2><a href="https://www.bing.com/ck/a?p=x&u={token}">Fire breaks out</a></h2>
        <div class="b_caption"><p>One crew member dead.</p></div></li>
      <li class="b_algo"><h2><a href="https://www.microsoft.com/x">MS (ignored)</a></h2></li>
      <li class="b_algo"><h2><a href="https://mykn.kuehne-nagel.com/news/x">Container vessel</a></h2></li>
    </ol>"""
    caption, leads = bs.parse_bing_html(
        html, 'https://www.bing.com/search?q=Maersk+Frankfurt+Fire+Incident&FORM=SBIVSP')
    assert caption == 'Maersk Frankfurt Fire Incident'
    assert [l['link'] for l in leads] == [real, 'https://mykn.kuehne-nagel.com/news/x']
    assert leads[0]['match_type'] == 'organic' and leads[0]['provider'] == 'bing_web'
    assert leads[0]['snippet'] == 'One crew member dead.'
    assert leads[0]['caption'] == caption
    # the raw image-URL query is not a caption
    caption, _ = bs.parse_bing_html('', 'https://www.bing.com/images/search?q=imgurl:https://x/y.jpg')
    assert caption is None


def test_configured_respects_opt_out(monkeypatch):
    monkeypatch.setenv('BROWSER_SEARCH', 'false')
    assert bs.configured() is False
