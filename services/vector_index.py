"""Internal provenance index over image_vectors (the compounding moat).

Store the signature of every image the platform analyzes; look up repeats
by exact hash or embedding similarity BEFORE spending on external APIs.

Postgres: uses the pgvector `embedding_vec` column for ANN search when
available. SQLite/dev: Python cosine over the JSON column (fine at dev
scale). Both paths return the same shape.
"""
import logging

from services.embedding_service import MODEL_NAME, cosine_similarity

logger = logging.getLogger(__name__)


def store_signature(media_hash, *, phash=None, dhash=None, embedding=None,
                    source='query', ref_url=None):
    """Insert an ImageVector row (skip if this hash is already indexed).
    Never raises; returns the row id or None."""
    if not media_hash:
        return None
    from models import db, ImageVector
    try:
        existing = (db.session.query(ImageVector)
                    .filter_by(media_hash=media_hash).first())
        if existing:
            return existing.id

        emb_list = None
        dim = None
        if embedding is not None:
            emb_list = [round(float(x), 6) for x in embedding]
            dim = len(emb_list)

        row = ImageVector(media_hash=media_hash,
                          phash=str(phash) if phash else None,
                          dhash=str(dhash) if dhash else None,
                          embedding=emb_list, dim=dim,
                          model=MODEL_NAME if emb_list else None,
                          source=source,
                          ref_url=(ref_url or '')[:500] or None)
        db.session.add(row)
        db.session.commit()

        _sync_pgvector_column(row.id, emb_list)
        return row.id
    except Exception as e:
        logger.error('store_signature failed: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def _sync_pgvector_column(row_id, emb_list):
    """Mirror the embedding into the pgvector column on Postgres."""
    if not emb_list:
        return
    from models import db
    try:
        if db.engine.dialect.name != 'postgresql':
            return
        from sqlalchemy import text
        vec = '[' + ','.join(str(x) for x in emb_list) + ']'
        with db.engine.begin() as conn:
            conn.execute(text(
                'UPDATE image_vectors SET embedding_vec = :v WHERE id = :i'),
                {'v': vec, 'i': row_id})
    except Exception as e:
        logger.debug('pgvector sync skipped: %s', e)


def index_file(path, media_hash, source='query', ref_url=None):
    """Compute the full signature of a local image file and index it."""
    try:
        import imagehash
        from PIL import Image
        from services.embedding_service import embed_image, encoder_available
        with Image.open(path) as img:
            pil = img.convert('RGB')
            phash = imagehash.phash(pil)
            dhash = imagehash.dhash(pil)
            embedding = embed_image(pil) if encoder_available() else None
        return store_signature(media_hash, phash=phash, dhash=dhash,
                               embedding=embedding, source=source,
                               ref_url=ref_url)
    except Exception as e:
        logger.error('index_file failed: %s', e)
        return None


def find_similar(embedding, limit=5, min_similarity=0.90):
    """Nearest indexed images by cosine similarity.
    Returns [{'media_hash', 'similarity', 'source', 'ref_url'}...]."""
    if embedding is None:
        return []
    from models import db, ImageVector

    # Fast path: pgvector ANN on Postgres
    try:
        if db.engine.dialect.name == 'postgresql':
            from sqlalchemy import text
            vec = '[' + ','.join(str(float(x)) for x in embedding) + ']'
            rows = db.session.execute(text(
                'SELECT media_hash, source, ref_url, '
                '       1 - (embedding_vec <=> :v) AS sim '
                'FROM image_vectors WHERE embedding_vec IS NOT NULL '
                'ORDER BY embedding_vec <=> :v LIMIT :k'),
                {'v': vec, 'k': limit}).fetchall()
            return [{'media_hash': r.media_hash, 'similarity': float(r.sim),
                     'source': r.source, 'ref_url': r.ref_url}
                    for r in rows if float(r.sim) >= min_similarity]
    except Exception as e:
        logger.debug('pgvector query failed, falling back to python: %s', e)

    # Portable path: python cosine over the JSON column
    try:
        results = []
        query = (db.session.query(ImageVector)
                 .filter(ImageVector.embedding.isnot(None))
                 .order_by(ImageVector.created_at.desc())
                 .limit(10000))
        for row in query:
            sim = cosine_similarity(embedding, row.embedding)
            if sim is not None and sim >= min_similarity:
                results.append({'media_hash': row.media_hash,
                                'similarity': round(sim, 4),
                                'source': row.source,
                                'ref_url': row.ref_url})
        results.sort(key=lambda r: r['similarity'], reverse=True)
        return results[:limit]
    except Exception as e:
        logger.error('find_similar failed: %s', e)
        return []
