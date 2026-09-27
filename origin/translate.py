"""Arabic titles for the cards. Runs inside the background job, in parallel,
bounded in time; a missing translator or a slow service leaves the
original title in place."""
import concurrent.futures
import logging
import re

logger = logging.getLogger(__name__)

_ARABIC = re.compile(r'[\u0600-\u06FF]')
WORKERS = 8
TIME_CAP_S = 12
MAX_ITEMS = 60


def needs_translation(text):
    if not text or len(text) < 3:
        return False
    letters = sum(ch.isalpha() for ch in text)
    return letters > 0 and not _ARABIC.search(text)


def _translator():
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source='auto', target='ar')
    except Exception:
        return None


def translate_titles(items, time_cap_s=TIME_CAP_S):
    """Sets item['title_ar'] on items whose title is not Arabic. In place."""
    todo = [i for i in items[:MAX_ITEMS] if isinstance(i, dict) and needs_translation(i.get('title'))]
    if not todo:
        return 0
    tr = _translator()
    if tr is None:
        return 0
    done = 0
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(WORKERS, len(todo)))
    futures = {ex.submit(tr.translate, i['title'][:200]): i for i in todo}
    try:
        for fut in concurrent.futures.as_completed(futures, timeout=time_cap_s):
            item = futures[fut]
            try:
                out = fut.result()
                if out and isinstance(out, str) and out.strip() and out.strip() != item['title']:
                    item['title_ar'] = out.strip()[:200]
                    done += 1
            except Exception:
                pass
    except concurrent.futures.TimeoutError:
        logger.info('title translation cut short after %ss', time_cap_s)
    finally:
        ex.shutdown(wait=False)
    return done
