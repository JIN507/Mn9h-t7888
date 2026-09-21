"""YouTube Data API v3 — platform-native video search with exact upload
times (origin engine, item 3).

Reverse-image engines index a video's poster, not its moments; YouTube's
own search, driven by what the vision model read in the frames, finds the
upload directly and `publishedAt` is authoritative. Free key from Google
Cloud (enable "YouTube Data API v3"); a search costs 100 of the 10,000
daily units.
"""
import logging
import os

import requests

from .base import BaseProvider, Candidate

logger = logging.getLogger(__name__)

SEARCH_URL = 'https://www.googleapis.com/youtube/v3/search'


class YouTubeProvider(BaseProvider):
    name = 'youtube'
    timeout = (5, 20)


_provider = YouTubeProvider()


def api_key():
    return os.environ.get('YOUTUBE_API_KEY') or os.environ.get('YT_API_KEY') or ''


def configured():
    return bool(api_key())


def search_videos(query, *, published_before=None, published_after=None,
                  max_results=10, order='relevance', region=None, lang=None):
    """Search videos. Returns candidate dicts (organic leads) carrying the
    exact upload time as `api_date` and the poster as `image_url`.
    Raises requests.RequestException on HTTP failure."""
    if not configured():
        return []
    params = {
        'part': 'snippet', 'type': 'video', 'q': query,
        'maxResults': max(1, min(int(max_results), 50)),
        'order': order, 'key': api_key(),
    }
    if published_before:
        params['publishedBefore'] = _rfc3339(published_before)
    if published_after:
        params['publishedAfter'] = _rfc3339(published_after)
    if region:
        params['regionCode'] = region
    if lang:
        params['relevanceLanguage'] = lang
    resp = _provider.request('GET', SEARCH_URL, params=params)
    if resp.status_code != 200:
        raise requests.RequestException(
            f'YouTube HTTP {resp.status_code}: {resp.text[:200]}')
    out = []
    for item in resp.json().get('items') or []:
        vid = (item.get('id') or {}).get('videoId')
        sn = item.get('snippet') or {}
        if not vid:
            continue
        thumbs = sn.get('thumbnails') or {}
        poster = ((thumbs.get('high') or thumbs.get('medium') or thumbs.get('default') or {})
                  .get('url')) or f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg'
        cand = Candidate(link=f'https://www.youtube.com/watch?v={vid}',
                         title=sn.get('title', '') or '', thumbnail=poster,
                         match_type='organic', provider='youtube_api').to_dict()
        cand['image_url'] = poster
        cand['api_date'] = sn.get('publishedAt')
        cand['api_date_source'] = 'platform:youtube_api'
        cand['channel'] = sn.get('channelTitle')
        cand['video_id'] = vid
        out.append(cand)
    logger.info('YouTube search %r -> %d videos', query[:50], len(out))
    return out


def _rfc3339(value):
    """'2024-07-19' | ISO datetime -> RFC 3339 with seconds and Z."""
    v = str(value).strip()
    if len(v) == 10:
        return v + 'T00:00:00Z'
    if v.endswith('Z'):
        return v
    if '+' in v[10:] or v[10:].count('-') == 1:
        return v
    return v + 'Z'
