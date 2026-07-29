"""Job status + SSE endpoints for background work."""
import json
import logging
import time

from flask import Blueprint, Response, jsonify

from tasks.queue import fetch_job, job_state

logger = logging.getLogger(__name__)
bp = Blueprint('jobs', __name__)

# SSE streams are bounded so a gunicorn worker is never held indefinitely;
# EventSource reconnects automatically and picks up where it left off.
SSE_MAX_SECONDS = 25
SSE_POLL_SECONDS = 1.0


@bp.route('/api/jobs/<job_id>', methods=['GET'])
def job_status(job_id):
    job = fetch_job(job_id)
    if job is None:
        return jsonify({'error': 'job not found', 'success': False}), 404
    return jsonify(job_state(job))


def _sse(event, data):
    return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'


@bp.route('/api/jobs/<job_id>/events', methods=['GET'])
def job_events(job_id):
    job = fetch_job(job_id)
    if job is None:
        return jsonify({'error': 'job not found', 'success': False}), 404

    def stream():
        sent_progress = 0
        deadline = time.monotonic() + SSE_MAX_SECONDS
        while True:
            state = job_state(job)

            for message in state['progress'][sent_progress:]:
                yield _sse('progress', {'message': message})
            sent_progress = len(state['progress'])

            if state['status'] == 'finished':
                yield _sse('result', state.get('result') or {})
                return
            if state['status'] in ('failed', 'canceled', 'stopped'):
                yield _sse('job_error',
                           {'error': state.get('error', 'job failed')})
                return
            if time.monotonic() > deadline:
                # client reconnects; keeps workers from being pinned
                yield _sse('keepalive', {'status': state['status']})
                return
            time.sleep(SSE_POLL_SECONDS)

    return Response(stream(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Connection': 'keep-alive',
    })
