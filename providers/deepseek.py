"""DeepSeek provider — the LLM behind the origin investigation.

OpenAI-compatible chat completions. Used for:
  - chat / chat_json      : one-shot text (planning, narrative)
  - describe_image        : vision — what/who/where is in the query image
  - chat_tools            : one turn of a tool-calling agent loop
No key => every function returns None and the engine runs deterministically.
"""
import base64
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


def _post(payload):
    """POST a chat completion. Returns the parsed JSON body or None."""
    key = api_key()
    if not key:
        return None
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
        return resp.json()
    except ValueError:
        logger.warning('deepseek: non-JSON body')
        return None


def image_part(image_bytes, mime='image/jpeg'):
    """OpenAI-style image content part from raw bytes (inline base64)."""
    b64 = base64.b64encode(image_bytes).decode('ascii')
    return {'type': 'image_url',
            'image_url': {'url': f'data:{mime};base64,{b64}'}}


def describe_image(image_bytes, prompt, *, mime='image/jpeg', max_tokens=700,
                   json_mode=True):
    """Vision call: `prompt` + the image. Returns dict (json_mode) or text."""
    payload = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': prompt}, image_part(image_bytes, mime)]}],
        'max_tokens': max_tokens,
        'temperature': 0.1,
    }
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}
    body = _post(payload)
    if not body:
        return None
    try:
        text = body['choices'][0]['message']['content'] or ''
    except (KeyError, IndexError, TypeError):
        return None
    return _loads_lenient(text) if json_mode else text


def describe_frames(frames, prompt, *, mime='image/jpeg', max_tokens=900,
                    json_mode=True, max_frames=4):
    """Vision call over several frames of one video (up to max_frames).
    Returns dict (json_mode) or text; None on failure / no frames."""
    frames = [f for f in (frames or []) if f][:max_frames]
    if not frames:
        return None
    content = [{'type': 'text', 'text': prompt}]
    content += [image_part(f, mime) for f in frames]
    payload = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': content}],
        'max_tokens': max_tokens,
        'temperature': 0.1,
    }
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}
    body = _post(payload)
    if not body:
        return None
    try:
        text = body['choices'][0]['message']['content'] or ''
    except (KeyError, IndexError, TypeError):
        return None
    return _loads_lenient(text) if json_mode else text


def chat_tools(messages, tools, *, max_tokens=900, temperature=0.1,
               tool_choice='auto'):
    """One agent turn. Returns the assistant message dict
    ({'role','content','tool_calls'?}) plus usage, or None on failure."""
    payload = {
        'model': MODEL,
        'messages': messages,
        'tools': tools,
        'tool_choice': tool_choice,
        'max_tokens': max_tokens,
        'temperature': temperature,
    }
    body = _post(payload)
    if not body:
        return None
    try:
        msg = body['choices'][0]['message']
    except (KeyError, IndexError, TypeError):
        logger.warning('deepseek: unexpected tool response shape')
        return None
    msg.setdefault('content', '')
    msg['_usage'] = body.get('usage') or {}
    return msg


def parse_tool_args(tool_call):
    """Arguments of a tool call as a dict (never raises)."""
    try:
        raw = tool_call['function'].get('arguments') or '{}'
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return {}


def _loads_lenient(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find('{'), text.rfind('}')
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    logger.warning('deepseek: non-JSON output')
    return None


def chat_json(system, user, **kwargs):
    """chat() in JSON mode, parsed. Returns dict or None."""
    text = chat(system, user, json_mode=True, **kwargs)
    if not text:
        return None
    return _loads_lenient(text)
