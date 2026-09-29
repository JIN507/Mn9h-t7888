"""Image embeddings for "same instance" retrieval (Visual Verification Tier 1).

Encoder: DINOv2 ViT-S/14 via timm (self-hosted, CPU, ~85 MB weights pulled
from the HF hub on first use). Embeddings survive crops, watermarks, meme
text, color grading — the transformations viral images undergo — which
pHash cannot.

Everything degrades gracefully: if torch/timm aren't installed or the
VISUAL_VERIFY flag is off, callers get None and fall back to pHash-only.
"""
import logging
import os
import threading

logger = logging.getLogger(__name__)

MODEL_NAME = 'vit_small_patch14_dinov2.lvd142m'
EMBEDDING_DIM = 384

_lock = threading.Lock()
_model = None
_transform = None
_load_failed = False
_test_encoder = None  # unit tests inject a deterministic encoder here


def visual_verify_enabled():
    """Feature flag for the whole Tier-1 visual verification layer."""
    return os.environ.get('VISUAL_VERIFY', 'false').lower() == 'true'


def encoder_available():
    """True if an encoder can produce embeddings right now."""
    global _load_failed
    if _test_encoder is not None:
        return True
    if _load_failed:
        return False
    try:
        import timm    # noqa: F401
        import torch   # noqa: F401
        return True
    except ImportError:
        return False
    except Exception as e:
        # a broken install (e.g. mismatched torch / torchvision builds) must
        # not take the worker down: run without embeddings
        _load_failed = True
        logger.error('Embedding runtime is installed but unusable: %s', e)
        return False


def set_encoder_for_testing(fn):
    """Inject a deterministic encoder: fn(PIL.Image) -> 1-D numpy array."""
    global _test_encoder, _load_failed
    _test_encoder = fn
    if fn is not None:
        _load_failed = False


def _load_model():
    global _model, _transform, _load_failed
    with _lock:
        if _model is not None or _load_failed:
            return
        try:
            import timm
            import torch
            logger.info('Loading %s (first call downloads ~85MB weights)...',
                        MODEL_NAME)
            model = timm.create_model(MODEL_NAME, pretrained=True,
                                      num_classes=0)
            model.eval()
            torch.set_grad_enabled(False)
            cfg = timm.data.resolve_model_data_config(model)
            _transform = timm.data.create_transform(**cfg, is_training=False)
            _model = model
            logger.info('Embedding model ready (dim=%d)', EMBEDDING_DIM)
        except Exception as e:
            _load_failed = True
            logger.error('Could not load embedding model: %s', e)


def warm_up():
    """Load the model and run one dummy embed (worker boot preload)."""
    if not encoder_available():
        return False
    try:
        from PIL import Image
        return embed_image(Image.new('RGB', (32, 32))) is not None
    except Exception as e:
        logger.warning('embedding warm-up failed: %s', e)
        return False


def embed_image(image):
    """PIL.Image | path | bytes -> L2-normalized float32 numpy vector, or None."""
    import numpy as np

    pil = _as_pil(image)
    if pil is None:
        return None

    if _test_encoder is not None:
        vec = np.asarray(_test_encoder(pil), dtype='float32')
        return _normalize(vec)

    if not encoder_available():
        return None
    _load_model()
    if _model is None:
        return None

    try:
        import torch
        tensor = _transform(pil).unsqueeze(0)
        with torch.no_grad():
            features = _model(tensor)
        vec = features[0].cpu().numpy().astype('float32')
        return _normalize(vec)
    except Exception as e:
        logger.error('Embedding failed: %s', e)
        return None


def _as_pil(image):
    from PIL import Image
    import io
    try:
        if isinstance(image, Image.Image):
            return image.convert('RGB')
        if isinstance(image, (bytes, bytearray)):
            return Image.open(io.BytesIO(image)).convert('RGB')
        return Image.open(image).convert('RGB')
    except Exception as e:
        logger.warning('Could not open image for embedding: %s', e)
        return None


def _normalize(vec):
    import numpy as np
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def cosine_similarity(a, b):
    """Cosine similarity of two (normalized or not) vectors."""
    import numpy as np
    if a is None or b is None:
        return None
    a = np.asarray(a, dtype='float32')
    b = np.asarray(b, dtype='float32')
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
