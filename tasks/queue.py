"""Queue plumbing.

With REDIS_URL set (Render): real Redis + a separate RQ worker process
(worker.py). Without it (local dev, tests): fakeredis + synchronous
execution — enqueue runs the job inline, so the API contract (202 + job
polling/SSE) stays identical everywhere with no Redis install needed.
"""
import logging
import os

from redis import Redis
from rq import Queue
from rq.job import Job

logger = logging.getLogger(__name__)

_connection = None
_queue = None

JOB_RESULT_TTL = 3600  # keep results for an hour
JOB_TIMEOUT = 600      # hard cap per job


def is_async():
    return bool(os.environ.get('REDIS_URL'))


def get_connection():
    global _connection
    if _connection is None:
        redis_url = os.environ.get('REDIS_URL')
        if redis_url:
            _connection = Redis.from_url(redis_url)
        else:
            import fakeredis
            logger.info('REDIS_URL not set — using fakeredis with '
                        'synchronous job execution')
            _connection = fakeredis.FakeStrictRedis()
    return _connection


def get_queue():
    global _queue
    if _queue is None:
        _queue = Queue('default', connection=get_connection(),
                       is_async=is_async(),
                       default_timeout=JOB_TIMEOUT)
    return _queue


def enqueue(func, *args, **kwargs):
    """Enqueue a job; returns the RQ Job."""
    return get_queue().enqueue(
        func, *args, result_ttl=JOB_RESULT_TTL,
        failure_ttl=JOB_RESULT_TTL, **kwargs)


def fetch_job(job_id):
    """Fetch a job by id, or None if unknown/expired."""
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
