"""RQ worker entrypoint (the `worker` service).

Usage: python worker.py   (requires REDIS_URL)
"""
import logging
import os

from redis import Redis
from rq import Queue, Worker

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s')

QUEUES = ['default']


def main():
    redis_url = os.environ.get('REDIS_URL')
    if not redis_url:
        raise SystemExit('REDIS_URL is required to run the worker')
    connection = Redis.from_url(redis_url)

    # Preload the embedding model so the first visual verification job
    # doesn't pay the ~5s cold start
    if os.environ.get('VISUAL_VERIFY', '').lower() == 'true':
        from services.embedding_service import warm_up
        logging.getLogger(__name__).info(
            'warming up embedding model: %s', warm_up())
    worker = Worker([Queue(name, connection=connection) for name in QUEUES],
                    connection=connection)
    worker.work(with_scheduler=False)


if __name__ == '__main__':
    main()
