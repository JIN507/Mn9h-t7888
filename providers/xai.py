"""xAI (Grok) provider — contextual image investigation via web search.

WARNING: the investigate call can take up to 180 s and currently blocks a
gunicorn worker. Scheduled to move into a queued job (plan Phase 2).
"""
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
        'Authorization': f"Bearer {os.environ.get('XAI_API_KEY', '')}",
    }
    logger.info('xAI investigation started for %s', image_url)
    return _provider.request('POST', RESPONSES_URL, json=payload,
                             headers=headers, timeout=180)


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
