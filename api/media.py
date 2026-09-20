"""Media endpoints: frame extraction."""
import logging
import os
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from services.media_service import extract_frames_from_video

logger = logging.getLogger(__name__)
bp = Blueprint('media', __name__)


@bp.route('/api/extract-frames', methods=['POST'])
def extract_frames_api():
    """API endpoint to extract frames from uploaded video"""
    # Check if a file was uploaded
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    # Check if the file is empty
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Get frame interval parameter with default value of 2 seconds
    frame_interval = request.form.get('frameInterval', '2')
    
    # Create a unique filename
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    unique_filename = f"{timestamp}_{filename}"
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
    
    # Save the uploaded file
    file.save(file_path)
    
    try:
        # Extract frames from the video
        frames = extract_frames_from_video(file_path, frame_interval)
        
        # Delete the uploaded file after processing
        os.remove(file_path)
        
        # Distinct, usable frames for a video-origin search
        keyframes = []
        try:
            import base64
            from services.keyframes import select_keyframes
            blobs = [base64.b64decode(f['data'].split(',', 1)[1]) for f in frames]
            keyframes = select_keyframes(blobs, k=4)
        except Exception as e:
            logger.warning('keyframe selection failed: %s', e)

        return jsonify({
            'success': True,
            'frames': frames,
            'frameCount': len(frames),
            'keyframe_indices': keyframes,
        })
    except Exception as e:
        # Delete the uploaded file if an error occurs
        if os.path.exists(file_path):
            os.remove(file_path)
        
        return jsonify({
            'error': str(e)
        }), 500
