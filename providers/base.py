"""Shared HTTP infrastructure for external API providers.

Every provider module builds on:
- one requests.Session per provider with connection-error retries
  (status codes are never retried, so HTTP error handling stays with callers)
- explicit per-call timeouts — no unbounded requests
- a lightweight circuit breaker: after N consecutive failures the provider
  fails fast for a cooldown period instead of hanging users
- usage metering: every call logs provider, endpoint, latency and outcome
- normalized result dataclasses shared by all providers
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Force IPv4 — some networks hang on IPv6 (moved from app.py)
try:
    import socket
    import urllib3.util.connection as urllib3_cn
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
except Exception:  # pragma: no cover
    pass


class ProviderError(Exception):
    """Base error for provider failures."""


class ProviderNotConfigured(ProviderError):
    """Required credentials are missing from the environment."""


class CircuitOpen(ProviderError):
    """Provider temporarily disabled after repeated failures."""


@dataclass
class DetectionResult:
    """Normalized AI-detection verdict shared by all detector providers."""
    verdict: str                      # 'ai' | 'human' | 'unknown'
    ai_confidence: float = 0.0
    human_confidence: float = 0.0
    generator: str = 'unknown'
    generator_confidence: float = 0.0
    provider: str = ''
    raw: dict = field(default_factory=dict)

    @property
    def is_ai(self) -> bool:
        return self.verdict == 'ai'


@dataclass
class Candidate:
    """Normalized reverse-search match shared by all search providers.

    match_type buckets: 'exact' | 'similar' | 'page_match' | 'organic'
    """
    link: str
    title: str = ''
    thumbnail: Optional[str] = None
    match_type: str = 'similar'
    provider: str = ''

    def to_dict(self) -> dict:
        return {'title': self.title, 'link': self.link,
                'thumbnail': self.thumbnail, 'match_type': self.match_type,
                'provider': self.provider}


class _Breaker:
    def __init__(self, threshold: int = 5, cooldown: float = 60.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self.failures = 0
        self.opened_at = 0.0
        self.lock = threading.Lock()

    def check(self, provider: str):
        with self.lock:
            if self.failures >= self.threshold:
                if time.monotonic() - self.opened_at < self.cooldown:
                    raise CircuitOpen(
                        f'{provider} disabled after repeated failures')
                self.failures = 0  # half-open: allow one retry round

    def record(self, ok: bool):
        with self.lock:
            if ok:
                self.failures = 0
            else:
                self.failures += 1
                if self.failures >= self.threshold:
                    self.opened_at = time.monotonic()


def make_session() -> requests.Session:
    """Session retrying only connection-level failures, never status codes."""
    session = requests.Session()
    retry = Retry(total=None, connect=2, read=1, status=0,
                  backoff_factor=0.5, allowed_methods=None,
                  raise_on_status=False)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


class BaseProvider:
    """Shared session + circuit breaker + metered request()."""
    name = 'provider'
    timeout: object = 30

    def __init__(self):
        self.session = make_session()
        self.breaker = _Breaker()

    def request(self, method: str, url: str, timeout=None, **kwargs) -> requests.Response:
        self.breaker.check(self.name)
        started = time.monotonic()
        try:
            resp = self.session.request(
                method, url, timeout=timeout or self.timeout, **kwargs)
        except requests.RequestException:
            self.breaker.record(ok=False)
            logger.warning('provider=%s url=%s outcome=transport_error elapsed=%.2fs',
                           self.name, url, time.monotonic() - started)
            raise
        self.breaker.record(ok=resp.status_code < 500)
        logger.info('provider=%s url=%s status=%s elapsed=%.2fs',
                    self.name, url, resp.status_code, time.monotonic() - started)
        return resp
