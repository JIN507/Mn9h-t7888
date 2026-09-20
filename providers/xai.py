"""xAI (Grok) provider — contextual image investigation via web search.

WARNING: the investigate call can take up to 180 s and currently blocks a
gunicorn worker. Scheduled to move into a queued job (plan Phase 2).
"""
import json
import logging
import os

from .base import BaseProvider

logger = logging.getLogger(__name__)

RESPONSES_URL = 'https://api.x.ai/v1/responses'


class XaiProvider(BaseProvider):
    name = 'xai'
    timeout = 180


_provider = XaiProvider()


def investigate_image(image_url):
    """Ask Grok to investigate an image's story — returns the raw Response."""
    payload = {
        'model': 'grok-4.20-reasoning',
        'input': [{
            'role': 'user',
            'content': (
                'Please act as an investigative journalist. I have provided '
                f'an image URL to investigate: {image_url} Search the web '
                'for context on this image (where it appeared, its origin, '
                'any controversies or truth behind it). You must use the '
                'web search tool to find information about this image. '
                'Provide a highly detailed summary in Arabic explaining '
                'the story behind this image.'),
        }],
        'tools': [{'type': 'web_search', 'enable_image_understanding': True}],
    }
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key()}',
    }
    logger.info('xAI investigation started for %s', image_url)
    return _provider.request('POST', RESPONSES_URL, json=payload,
                             headers=headers, timeout=180)


_KEY_NAMES = ('GROK_API_KEY', 'grok_key', 'GROK_KEY', 'XAI_API_KEY')


def api_key():
    """First non-empty xAI key; GROK_* names win over XAI_API_KEY so a fresh
    funded key can sit next to an old unfunded one."""
    for name in _KEY_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return ''


def configured():
    return bool(api_key()) and \
        os.environ.get('GROK_SEARCH', 'true').lower() != 'false'


def search_origin(image_url, question, model=None, timeout=120):
    """Grok with X search + web search + the image: returns
    {'text': str, 'urls': [..], 'error': str|None}. Never raises.
    (Grok's X search is the one tool that can surface the ORIGINAL post on
    X directly; its answer is a lead list — every URL must be inspected.)"""
    if isinstance(image_url, (bytes, bytearray)):
        # xAI's fetcher is refused by many image hosts: send the bytes inline
        import base64
        image_url = 'data:image/jpeg;base64,' + base64.b64encode(image_url).decode('ascii')
    payload = {
        'model': model or os.environ.get('GROK_MODEL', 'grok-4-fast'),
        'input': [{'role': 'user', 'content': [
            {'type': 'input_text', 'text': question},
            {'type': 'input_image', 'image_url': image_url}]}],
        'tools': [{'type': 'web_search'}, {'type': 'x_search'}],
    }
    headers = {'Content-Type': 'application/json',
               'Authorization': f'Bearer {api_key()}'}
    try:
        resp = _provider.request('POST', RESPONSES_URL, json=payload,
                                 headers=headers, timeout=timeout)
    except Exception as e:
        return {'text': '', 'urls': [], 'error': f'request failed: {e}'}
    if resp.status_code != 200:
        note = resp.text[:200]
        if resp.status_code == 403 and 'credit' in note.lower():
            note = 'xAI account has no credits'
        return {'text': '', 'urls': [], 'error': f'HTTP {resp.status_code}: {note}'}
    try:
        data = resp.json()
    except ValueError:
        return {'text': '', 'urls': [], 'error': 'non-JSON body'}
    return dict(parse_search_output(data), error=None)


def parse_search_output(data):
    """Text + cited/mentioned URLs from a Responses-API body."""
    import re
    texts, urls = [], []
    for item in data.get('output') or []:
        if not isinstance(item, dict):
            continue
        if item.get('type') == 'message':
            for c in item.get('content') or []:
                if not isinstance(c, dict):
                    continue
                if c.get('type') in ('output_text', 'text'):
                    texts.append(c.get('text') or '')
                for a in c.get('annotations') or []:
                    if isinstance(a, dict) and a.get('url'):
                        urls.append(a['url'])
        else:  # tool call / result items: harvest any URLs they carry
            urls.extend(re.findall(r'https?://[^\s"\'<>\\]+', json.dumps(item)))
    text = '\n'.join(t for t in texts if t)
    urls.extend(re.findall(r'https?://[^\s"\'<>)\]]+', text))
    seen, ordered = set(), []
    for u in urls:
        u = u.rstrip('.,;')
        if u not in seen and 'x.ai' not in u:
            seen.add(u)
            ordered.append(u)
    return {'text': text, 'urls': ordered[:20]}


def extract_summary(xai_data):
    """Pull the assistant text out of the several Responses-API shapes."""
    message_content = ''
    if 'message' in xai_data and 'content' in xai_data['message']:
        message_content = xai_data['message']['content']
    elif 'choices' in xai_data:
        message_content = (xai_data['choices'][0]
                           .get('message', {}).get('content', ''))
    elif 'output' in xai_data and isinstance(xai_data['output'], list):
        texts = []
        for item in xai_data['output']:
            if item.get('role') == 'assistant' and item.get('type') == 'message':
                contents = item.get('content', [])
                if isinstance(contents, str):
                    texts.append(contents)
                elif isinstance(contents, list):
                    for c in contents:
                        if c.get('type') == 'output_text':
                            texts.append(c.get('text', ''))
        message_content = '\n'.join(texts)

    if not message_content.strip():
        # Unknown structure — dump as string rather than losing the answer
        message_content = str(xai_data)
    return message_content
