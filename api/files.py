"""User files (My Files) + admin file download endpoints."""
import logging
import os
import uuid

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from auth import login_required, admin_required
from models import db, UserFile
from services.media_service import USER_FILES_FOLDER

logger = logging.getLogger(__name__)
bp = Blueprint('files', __name__)




@bp.route('/api/user/files', methods=['GET'])
@login_required
def get_user_files():
    """Get current user's files only (isolated)"""
    from flask import g
    
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    file_type = request.args.get('file_type')
    
    query = UserFile.query.filter_by(user_id=g.current_user.id)
    
    if file_type:
        query = query.filter_by(file_type=file_type)
    
    total = query.count()
    files = query.order_by(UserFile.created_at.desc()).offset(offset).limit(limit).all()
    
    return jsonify({
        'success': True,
        'total': total,
        'files': [f.to_dict() for f in files]
    })


@bp.route('/api/user/files', methods=['POST'])
@login_required
def upload_user_file():
    """Upload a file for current user"""
    from flask import g
    import mimetypes
    
    if 'file' not in request.files:
        return jsonify({'error': 'لم يتم إرسال ملف'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400
    
    # Get metadata from form
    description = request.form.get('description', '').strip()
    source_feature = request.form.get('source_feature', '').strip()
    file_type = request.form.get('file_type', '').strip()
    
    # Generate unique stored filename
    original_filename = secure_filename(file.filename)
    file_ext = os.path.splitext(original_filename)[1]
    stored_filename = f"{uuid.uuid4()}{file_ext}"
    
    # Create user subfolder
    user_folder = os.path.join(USER_FILES_FOLDER, g.current_user.id)
    os.makedirs(user_folder, exist_ok=True)
    
    # Save file
    file_path = os.path.join(user_folder, stored_filename)
    file.save(file_path)
    
    # Get file info
    file_size = os.path.getsize(file_path)
    mime_type = mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'
    
    # Auto-detect file type if not provided
    if not file_type:
        if mime_type.startswith('image/'):
            file_type = 'image'
        elif mime_type.startswith('video/'):
            file_type = 'video'
        elif mime_type.startswith('audio/'):
            file_type = 'audio'
        elif mime_type in ['application/pdf', 'application/json', 'text/csv']:
            file_type = 'report'
        else:
            file_type = 'export'
    
    # Create database record
    user_file = UserFile(
        user_id=g.current_user.id,
        filename=original_filename,
        stored_filename=stored_filename,
        file_type=file_type,
        mime_type=mime_type,
        file_size=file_size,
        file_path=os.path.join(g.current_user.id, stored_filename),
        description=description or None,
        source_feature=source_feature or None
    )
    
    db.session.add(user_file)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'file': user_file.to_dict()
    }), 201


@bp.route('/api/user/files/<file_id>', methods=['GET'])
@login_required
def get_user_file(file_id):
    """Get details of a specific user file"""
    from flask import g
    
    user_file = UserFile.query.filter_by(id=file_id, user_id=g.current_user.id).first()
    
    if not user_file:
        return jsonify({'error': 'الملف غير موجود'}), 404
    
    return jsonify({
        'success': True,
        'file': user_file.to_dict()
    })


@bp.route('/api/user/files/<file_id>/download', methods=['GET'])
@login_required
def download_user_file(file_id):
    """Download a user's file"""
    from flask import g, send_file
    
    user_file = UserFile.query.filter_by(id=file_id, user_id=g.current_user.id).first()
    
    if not user_file:
        return jsonify({'error': 'الملف غير موجود'}), 404
    
    file_path = os.path.join(USER_FILES_FOLDER, user_file.file_path)
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'الملف غير موجود على الخادم'}), 404
    
    # Increment download count
    user_file.download_count += 1
    db.session.commit()
    
    return send_file(
        file_path,
        download_name=user_file.filename,
        as_attachment=True
    )


@bp.route('/api/user/files/<file_id>', methods=['DELETE'])
@login_required
def delete_user_file(file_id):
    """Delete a user's file"""
    from flask import g
    
    user_file = UserFile.query.filter_by(id=file_id, user_id=g.current_user.id).first()
    
    if not user_file:
        return jsonify({'error': 'الملف غير موجود'}), 404
    
    # Delete physical file
    file_path = os.path.join(USER_FILES_FOLDER, user_file.file_path)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            logger.info(f'[!] Error deleting file: {e}')
    
    # Delete database record
    db.session.delete(user_file)
    db.session.commit()
    
    return jsonify({'success': True})


@bp.route('/api/admin/files/<file_id>/download', methods=['GET'])
@admin_required
def admin_download_file(file_id):
    """Admin: Download any user's file"""
    from flask import send_file
    
    user_file = UserFile.query.get(file_id)
    
    if not user_file:
        return jsonify({'error': 'الملف غير موجود'}), 404
    
    file_path = os.path.join(USER_FILES_FOLDER, user_file.file_path)
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'الملف غير موجود على الخادم'}), 404
    
    return send_file(
        file_path,
        download_name=user_file.filename,
        as_attachment=True
    )
