"""Provenance endpoint: origin & first-seen analysis."""
import logging

from flask import Blueprint, current_app, jsonify, request

from services.provenance_service import analyze_provenance

from extensions import limiter, SPEND_LIMIT

logger = logging.getLogger(__name__)
bp = Blueprint('provenance', __name__)


@bp.route('/api/provenance', methods=['POST'])
@limiter.limit(SPEND_LIMIT)
def api_provenance():
    """Queue provenance analysis - returns 202 + job id (SSE streamable)."""
    data = request.get_json(silent=True) or {}
    if not data.get('image_url'):
        return jsonify({'error': 'image_url required', 'success': False}), 400

    from auth import get_current_user
    from tasks.jobs import run_provenance
    from tasks.queue import enqueue
    user = get_current_user()
    job = enqueue(run_provenance, data['image_url'],
                  user_id=user.id if user else None,
                  image_hash=data.get('image_hash'),
                  image_phash=data.get('image_phash'))
    return jsonify({
        'success': True,
        'job_id': job.id,
        'status_url': f'/api/jobs/{job.id}',
        'events_url': f'/api/jobs/{job.id}/events',
    }), 202
