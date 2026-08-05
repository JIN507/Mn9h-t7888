"""Queue plumbing — three modes, same 202+SSE contract everywhere:

- redis  (REDIS_URL set, production): real Redis + RQ worker process
- thread (local dev default):        jobs run in a background thread with an
                                     in-process registry — 202 returns
                                     instantly and SSE streams live progress,
                                     exactly like production, no Redis needed
- inline (QUEUE_MODE=inline, tests): job executes synchronously inside
                                     enqueue() for deterministic tests
"""
import logging
import os
import threading
import uuid

from redis import Redis
from rq import Queue
from rq.job import Job

logger = logging.getLogger(__name__)

_connection = None
_queue = None

JOB_RESULT_TTL = 3600  # keep results for an hour
JOB_TIMEOUT = 600      # hard cap per job

# ------------------------------------------------------------- local jobs

_local_jobs = {}
_local_lock = threading.Lock()
_local_current = threading.local()


class LocalJob:
    """Duck-typed stand-in for rq.job.Job used in thread/dev mode."""

    def __init__(self):
        self.id = str(uuid.uuid4())
        self.status = 'queued'
        self.meta = {}
        self.exc_info = None
        self._result = None

    def get_status(self, refresh=True):
        return self.status

    def get_meta(self, refresh=True):
        return self.meta

    def save_meta(self):
        pass

    def return_value(self):
        return self._result


def get_current_local_job():
    return getattr(_local_current, 'job', None)


def _run_local(job, func, args, kwargs):
    job.status = 'started'
    _local_current.job = job
    try:
        job._result = func(*args, **kwargs)
        job.status = 'finished'
    except Exception as e:
        logger.exception('local job %s failed', job.id)
        job.exc_info = f'{type(e).__name__}: {e}'
        job.status = 'failed'
    finally:
        _local_current.job = None


# ------------------------------------------------------------ mode + redis

def queue_mode():
    if os.environ.get('REDIS_URL'):
        return 'redis'
    return os.environ.get('QUEUE_MODE', 'thread')


def is_async():
    return queue_mode() == 'redis'


def get_connection():
    global _connection
    if _connection is None:
        redis_url = os.environ.get('REDIS_URL')
        if redis_url:
            _connection = Redis.from_url(redis_url)
        else:
            import fakeredis
            logger.info('REDIS_URL not set — fakeredis (%s mode)', queue_mode())
            _connection = fakeredis.FakeStrictRedis()
    return _connection


def get_queue():
    global _queue
    if _queue is None:
        _queue = Queue('default', connection=get_connection(),
                       is_async=is_async(),
                       default_timeout=JOB_TIMEOUT)
    return _queue


# ---------------------------------------------------------------- public

def enqueue(func, *args, **kwargs):
    """Enqueue a job; returns an rq Job or a LocalJob (same interface)."""
    mode = queue_mode()
    if mode == 'thread':
        job = LocalJob()
        with _local_lock:
            _local_jobs[job.id] = job
        threading.Thread(target=_run_local, args=(job, func, args, kwargs),
                         daemon=True).start()
        return job

    # 'redis' (async) and 'inline' (sync fakeredis, used by tests)
    return get_queue().enqueue(
        func, *args, result_ttl=JOB_RESULT_TTL,
        failure_ttl=JOB_RESULT_TTL, **kwargs)


def fetch_job(job_id):
    """Fetch a job by id, or None if unknown/expired."""
    with _local_lock:
        if job_id in _local_jobs:
            return _local_jobs[job_id]
    try:
        return Job.fetch(job_id, connection=get_connection())
    except Exception:
        return None


def job_state(job):
    """Serializable snapshot of a job for the status endpoint / SSE."""
    status = job.get_status(refresh=True)
    status = getattr(status, 'value', status)  # rq 2.x returns an enum
    state = {
        'job_id': job.id,
        'status': str(status),
        'progress': (job.get_meta(refresh=True) or {}).get('progress', []),
    }
    if status == 'finished':
        state['result'] = job.return_value()
    elif status == 'failed':
        state['error'] = (job.exc_info or 'job failed').splitlines()[-1][:300]
    return state
