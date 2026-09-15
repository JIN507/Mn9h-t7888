"""DeepSeek provider — text LLM used surgically inside the origin engine.

Two jobs only (both optional — no key => the engine runs deterministically):
  1. plan_expansion: read the harvested candidates (titles, captions,
     credit lines) and propose targeted text queries + credited sources.
  2. write_narrative: Arabic summary where every claim cites evidence.

OpenAI-compatible chat completions; JSON mode is requested for planning.
"""
import json
import logging
import os

from .base import BaseProvider

logger = logging.getLogger(__name__)

CHAT_URL = 'https://api.deepseek.com/chat/completions'
MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')

_KEY_NAMES = ('DEEPSEEK_API_KEY', 'DEAPSEAK_KEY', 'Deapseak_key',
              'DEEPSEAK_KEY')


class DeepSeekProvider(BaseProvider):
    name = 'deepseek'
    timeout = (10, 90)


_provider = DeepSeekProvider()


def api_key():
    for name in _KEY_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


def configured():
    return bool(api_key())


def chat(system, user, *, json_mode=False, max_tokens=1200, temperature=0.2):
    """One chat completion. Returns the assistant text, or None on failure."""
    key = api_key()
    if not key:
        return None
    payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        'max_tokens': max_tokens,
        'temperature': temperature,
    }
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}
    headers = {'Authorization': f'Bearer {key}',
               'Content-Type': 'application/json'}
    try:
        resp = _provider.request('POST', CHAT_URL, json=payload,
                                 headers=headers)
    except Exception as e:
        logger.warning('deepseek request failed: %s', e)
        return None
    if resp.status_code != 200:
        logger.warning('deepseek HTTP %s: %s', resp.status_code,
                       resp.text[:200])
        return None
    try:
        return resp.json()['choices'][0]['message']['content']
    except Exception:
        logger.warning('deepseek: unexpected response shape')
        return None


def chat_json(system, user, **kwargs):
    """chat() in JSON mode, parsed. Returns dict or None."""
    text = chat(system, user, json_mode=True, **kwargs)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find('{'), text.rfind('}')
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    logger.warning('deepseek: non-JSON planning output')
    return None
