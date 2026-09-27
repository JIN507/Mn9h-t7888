"""Budgets are code: time, SerpAPI credits and page fetches are counted and
enforced by the orchestrator, and the report shows what was spent and what
was skipped. One Budget per investigation; thread-safe (rounds run in
parallel)."""
import os
import threading
import time


class BudgetExceeded(Exception):
    pass


class Budget:
    def __init__(self, *, seconds=None, credits=None, pages=None, kind='image'):
        video = kind == 'video'
        self.seconds = float(seconds if seconds is not None else os.environ.get(
            'ORIGIN_TIME_S_VIDEO' if video else 'ORIGIN_TIME_S', 200 if video else 150))
        self.credits = int(credits if credits is not None else os.environ.get(
            'ORIGIN_CREDITS_VIDEO' if video else 'ORIGIN_CREDITS', 22 if video else 15))
        self.pages = int(pages if pages is not None else os.environ.get(
            'ORIGIN_PAGES_VIDEO' if video else 'ORIGIN_PAGES', 120 if video else 90))
        self.started = time.monotonic()
        self.spent_credits = 0
        self.spent_pages = 0
        self.skipped = []          # [{'step': ..., 'reason': ...}]
        self._lock = threading.Lock()

    # -- time
    def elapsed(self):
        return time.monotonic() - self.started

    def time_left(self):
        return self.seconds - self.elapsed()

    # -- credits (SerpAPI searches)
    def can_spend(self, credits=1):
        with self._lock:
            return self.spent_credits + credits <= self.credits

    def charge(self, credits=1, what=''):
        """Reserve credits before a paid call. Raises BudgetExceeded when
        the cap would be crossed (the caller records a skip instead)."""
        with self._lock:
            if self.spent_credits + credits > self.credits:
                raise BudgetExceeded(f'{what or "call"} needs {credits}, '
                                     f'{self.credits - self.spent_credits} left')
            self.spent_credits += credits

    def refund(self, credits=1):
        with self._lock:
            self.spent_credits = max(0, self.spent_credits - credits)

    # -- pages
    def take_pages(self, wanted):
        """How many page fetches may still run (<= wanted); reserves them."""
        with self._lock:
            n = max(0, min(wanted, self.pages - self.spent_pages))
            self.spent_pages += n
            return n

    def skip(self, step, reason):
        with self._lock:
            self.skipped.append({'step': step, 'reason': reason})

    def snapshot(self):
        with self._lock:
            return {'seconds': round(self.elapsed(), 1), 'seconds_cap': self.seconds,
                    'credits': self.spent_credits, 'credits_cap': self.credits,
                    'pages': self.spent_pages, 'pages_cap': self.pages,
                    'skipped': list(self.skipped)}
