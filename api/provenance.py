"""Provenance endpoint: origin & first-seen analysis."""
import logging

from flask import Blueprint, current_app, jsonify, request

from services.provenance_service import analyze_provenance

logger = logging.getLogger(__name__)
bp = Blueprint('provenance', __name__)


@bp.route('/api/provenance', methods=['POST'])
def api_provenance():
    """API endpoint for provenance analysis (origin & first seen)"""
    try:
        data = request.get_json(silent=True) or {}
        if not data.get('image_url'):
            return jsonify({'error': 'image_url required'}), 200
        return jsonify(analyze_provenance(data['image_url'])), 200
    except Exception as e:
        current_app.logger.exception('provenance API error')
        return jsonify({
            'first_seen': None,
            'timeline': [],
            'related_images': [],
            'stats': {'checked': 0, 'with_dates': 0},
            'note': f'Server error: {str(e)}'
        }), 200
