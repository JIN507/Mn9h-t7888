"""RQ worker entrypoint (Render worker service).

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
    worker = Worker([Queue(name, connection=connection) for name in QUEUES],
                    connection=connection)
    worker.work(with_scheduler=False)


if __name__ == '__main__':
    main()
