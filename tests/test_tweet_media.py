"""X posts: photos, text and date via Twitter's syndication endpoint; the
photo is the page's own media for verification and the pivot; the caption
becomes the sighting's title/snippet."""
import responses

from providers import tweet
from services.visual_verify import platform_image_urls

TW = 'https://x.com/svs9111/status/570514380095299584'


def setup_function(_):
    tweet.clear_cache()


def test_status_id_and_token():
    assert tweet.status_id(TW) == ('svs9111', '570514380095299584')
    assert tweet.status_id('https://twitter.com/a_b/statuses/1234717126671425537?s=20') == ('a_b', '1234717126671425537')
    assert tweet.status_id('https://x.com/svs9111') is None
    tok = tweet.syndication_token('570514380095299584')
    assert tok and '0' not in tok and '.' not in tok


@responses.activate
def test_tweet_info_via_syndication_then_fxtwitter_fallback():
    responses.add(responses.GET, tweet.SYNDICATION_URL, json={
        'created_at': '2015-02-25T09:23:22.000Z', 'text': 'صورة قديمه ل عبدالمجيد عبدالله',
        'user': {'screen_name': 'svs9111'},
        'photos': [{'url': 'https://pbs.twimg.com/media/B-rfyhEUcAAZcBR.jpg'}]},
        status=200, content_type='application/json')
    info = tweet.tweet_info(TW)
    assert info['photos'] == ['https://pbs.twimg.com/media/B-rfyhEUcAAZcBR.jpg?name=orig']
    assert info['created_at'].startswith('2015-02-25') and 'عبدالمجيد' in info['text']
    assert tweet.tweet_info(TW) is info                      # cached, no second request
    assert len(responses.calls) == 1
    assert platform_image_urls(TW) == ['https://pbs.twimg.com/media/B-rfyhEUcAAZcBR.jpg?name=orig']

    tweet.clear_cache()
    responses.add(responses.GET, tweet.SYNDICATION_URL, body='', status=404)
    responses.add(responses.GET, 'https://api.fxtwitter.com/svs9111/status/570514380095299584', json={
        'tweet': {'text': 't', 'created_at': 'Wed Feb 25 09:23:22 +0000 2015',
                  'author': {'screen_name': 'svs9111'},
                  'media': {'photos': [{'url': 'https://pbs.twimg.com/media/X.jpg?name=orig'}]}}}, status=200)
    info = tweet.tweet_info(TW)
    assert info['photos'] == ['https://pbs.twimg.com/media/X.jpg?name=orig']

    tweet.clear_cache()
    responses.add(responses.GET, tweet.SYNDICATION_URL, body='', status=404)
    responses.add(responses.GET, 'https://api.fxtwitter.com/svs9111/status/570514380095299584', status=500)
    assert tweet.tweet_info(TW) is None
    assert platform_image_urls(TW) == []


@responses.activate
def test_video_tweet_gives_its_poster_frame():
    responses.add(responses.GET, tweet.SYNDICATION_URL, json={
        'created_at': '2024-11-10T23:00:37.000Z', 'text': 'video', 'user': {'screen_name': 'u'},
        'photos': [], 'mediaDetails': [{'type': 'video', 'media_url_https': 'https://pbs.twimg.com/ext_tw_video_thumb/1/pu/img/abc.jpg'}],
        'video': {'poster': 'https://pbs.twimg.com/ext_tw_video_thumb/1/pu/img/abc.jpg'}},
        status=200, content_type='application/json')
    info = tweet.tweet_info('https://x.com/u/status/1855747417544773860')
    assert info['photos'] == ['https://pbs.twimg.com/ext_tw_video_thumb/1/pu/img/abc.jpg?name=orig']
