"""Media/file handling: storage folders, allowed types, frame extraction,
image downloads."""
import base64
import logging
import os

import cv2
import requests

logger = logging.getLogger(__name__)

# Project root (services/ is one level below it)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
AUDIO_UPLOAD_FOLDER = os.path.join('uploads', 'audio')
USER_FILES_FOLDER = os.path.join(BASE_DIR, 'user_files')
for _d in (UPLOAD_FOLDER, AUDIO_UPLOAD_FOLDER, USER_FILES_FOLDER):
    os.makedirs(_d, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac', 'wma'}


def compute_hashes(file_path):
    """SHA-256 (exact identity) + perceptual hash (images) for a file.

    Returns (sha256_hex, phash_hex_or_None). Never raises.
    """
    sha256 = None
    phash = None
    try:
        import hashlib
        h = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        sha256 = h.hexdigest()
    except Exception as e:
        logger.error('sha256 failed for %s: %s', file_path, e)

    try:
        import imagehash
        from PIL import Image
        with Image.open(file_path) as img:
            phash = str(imagehash.phash(img))
    except Exception:
        phash = None  # not an image / unreadable — fine

    return sha256, phash


def compute_text_hash(text):
    """SHA-256 of normalized text content."""
    import hashlib
    return hashlib.sha256(text.strip().encode('utf-8')).hexdigest()


def allowed_file(filename):
    return ('.' in filename
            and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS)


def allowed_audio_file(filename):
    return ('.' in filename
            and filename.rsplit('.', 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS)


def extract_frames_from_video(video_path, frame_interval):
    """Extract frames from video file at specified intervals."""
    try:
        video = cv2.VideoCapture(video_path)

        if not video.isOpened():
            logger.error('Could not open video file %s', video_path)
            return []

        fps = video.get(cv2.CAP_PROP_FPS)

        frame_interval_sec = int(frame_interval)
        frame_interval_frames = int(fps * frame_interval_sec)

        # Ensure we extract at least one frame
        if frame_interval_frames <= 0:
            frame_interval_frames = 1

        frames = []
        frame_count = 0

        while True:
            success, frame = video.read()
            if not success:
                break

            if frame_count % frame_interval_frames == 0:
                try:
                    _, buffer = cv2.imencode('.jpg', frame)
                    img_str = base64.b64encode(buffer).decode('utf-8')
                    frames.append({
                        'data': f'data:image/jpeg;base64,{img_str}',
                        'timestamp': frame_count / fps if fps > 0 else 0
                    })
                except Exception as e:
                    logger.warning('Error encoding frame %d: %s', frame_count, e)

            frame_count += 1

        video.release()
        return frames
    except Exception as e:
        logger.error('Error extracting frames: %s', e)
        return []


def download_image(url, save_path):
    """Download an image from URL to specified path."""
    try:
        response = requests.get(url, stream=True, timeout=15)
        response.raise_for_status()

        with open(save_path, 'wb') as img_file:
            for chunk in response.iter_content(chunk_size=8192):
                img_file.write(chunk)

        # Verify file was actually created and contains data
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            logger.info('Downloaded image to %s', save_path)
            return True
        logger.warning('Downloaded file is empty or missing: %s', save_path)
        return False
    except Exception as e:
        logger.error('Error downloading image: %s', e)
        return False
