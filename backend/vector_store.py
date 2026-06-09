import os
import threading
from typing import List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

try:
    import faiss
    HAS_FAISS = True
except ImportError:
    faiss = None
    HAS_FAISS = False

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    genai = None
    HAS_GENAI = False

import models

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMBED_DIM = 768
EMBED_BATCH_SIZE = 100
if HAS_GENAI and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

_index_lock = threading.RLock()
_faiss_index = None
_id_map: List[int] = []


def _mock_embedding(text: str) -> np.ndarray:
    state = np.random.RandomState(abs(hash(text)) % (2**32))
    vec = state.randn(EMBED_DIM)
    norm = np.linalg.norm(vec)
    return (vec / norm if norm > 0 else vec).astype(np.float32)


def _chunk_to_vec(embedding) -> np.ndarray:
    if isinstance(embedding, (bytes, bytearray)):
        return np.frombuffer(embedding, dtype=np.float32)
    return np.array(embedding, dtype=np.float32)


def get_embedding(text: str) -> np.ndarray:
  embeddings = get_embeddings_batch([text])
  return embeddings[0] if embeddings else _mock_embedding(text)


def get_embeddings_batch(texts: List[str]) -> List[np.ndarray]:
    if not texts:
        return []

    if not HAS_GENAI or not GEMINI_API_KEY:
        return [_mock_embedding(t) for t in texts]

    results: List[np.ndarray] = []
    try:
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            response = genai.embed_content(
                model="models/text-embedding-004",
                content=batch,
                task_type="retrieval_document",
            )
            embs = response["embedding"]
            if batch and isinstance(embs[0], (int, float)):
                results.append(np.array(embs, dtype=np.float32))
            else:
                for e in embs:
                    results.append(np.array(e, dtype=np.float32))
        return results
    except Exception as e:
        print(f"Gemini batch embedding error: {e}. Falling back to per-chunk mock.")
        return [_mock_embedding(t) for t in texts]


def _ensure_faiss_index():
    global _faiss_index, _id_map
    if _faiss_index is None and HAS_FAISS:
        _faiss_index = faiss.IndexFlatIP(EMBED_DIM)
        _id_map = []


def _add_to_faiss_index(chunk_ids: List[int], vectors: List[np.ndarray]):
    if not HAS_FAISS or not chunk_ids:
        return
    mat = np.array(vectors, dtype=np.float32)
    faiss.normalize_L2(mat)
    with _index_lock:
        _ensure_faiss_index()
        _faiss_index.add(mat)
        _id_map.extend(chunk_ids)


def warm_faiss_index(db: Session):
    """Build FAISS index from existing chunks on startup."""
    if not HAS_FAISS:
        return
    global _faiss_index, _id_map
    with _index_lock:
        if _faiss_index is not None and len(_id_map) > 0:
            return
        chunks = db.query(models.DocumentChunk).all()
        _faiss_index = faiss.IndexFlatIP(EMBED_DIM)
        _id_map = []
        if not chunks:
            return
        vectors = []
        for chunk in chunks:
            vectors.append(_chunk_to_vec(chunk.embedding))
            _id_map.append(chunk.id)
        mat = np.array(vectors, dtype=np.float32)
        faiss.normalize_L2(mat)
        _faiss_index.add(mat)


def store_chunk(db: Session, document_id: int, chunk_text: str):
    store_chunks_batch(db, document_id, [chunk_text])


def store_chunks_batch(db: Session, document_id: int, chunk_texts: List[str]):
    texts = [t for t in chunk_texts if t.strip()]
    if not texts:
        return

    embeddings = get_embeddings_batch(texts)
    is_sqlite = db.bind.dialect.name == "sqlite"
    new_chunks = []

    for text, emb_vec in zip(texts, embeddings):
        emb_value = emb_vec.tobytes() if is_sqlite else emb_vec.tolist()
        db_chunk = models.DocumentChunk(
            document_id=document_id,
            chunk_text=text,
            embedding=emb_value,
        )
        db.add(db_chunk)
        new_chunks.append((db_chunk, emb_vec))

    db.flush()
    chunk_ids = [c.id for c, _ in new_chunks]
    vectors = [v for _, v in new_chunks]
    db.commit()
    _add_to_faiss_index(chunk_ids, vectors)


def _search_faiss(
    db: Session, query_vec: np.ndarray, limit: int, document_id: Optional[int]
) -> List[Tuple[models.DocumentChunk, float]]:
    with _index_lock:
        if _faiss_index is None or len(_id_map) == 0:
            warm_faiss_index(db)
        if _faiss_index is None or _faiss_index.ntotal == 0:
            return []

        k = min(limit * 5, _faiss_index.ntotal)
        q = query_vec.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(q)
        scores, indices = _faiss_index.search(q, k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        chunk_id = _id_map[idx]
        chunk = db.query(models.DocumentChunk).filter(models.DocumentChunk.id == chunk_id).first()
        if not chunk:
            continue
        if document_id is not None and chunk.document_id != document_id:
            continue
        results.append((chunk, float(score)))
        if len(results) >= limit:
            break
    return results


def _search_bruteforce(
    db: Session, query_vec: np.ndarray, limit: int, document_id: Optional[int]
) -> List[Tuple[models.DocumentChunk, float]]:
    q = db.query(models.DocumentChunk)
    if document_id is not None:
        q = q.filter(models.DocumentChunk.document_id == document_id)
    chunks = q.all()
    if not chunks:
        return []

    results = []
    norm_q = np.linalg.norm(query_vec)
    for chunk in chunks:
        chunk_vec = _chunk_to_vec(chunk.embedding)
        norm_c = np.linalg.norm(chunk_vec)
        similarity = 0.0
        if norm_q > 0 and norm_c > 0:
            similarity = float(np.dot(query_vec, chunk_vec) / (norm_q * norm_c))
        results.append((chunk, similarity))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:limit]


def search_semantic(
    db: Session, query: str, limit: int = 5, document_id: int = None
) -> List[Tuple[models.DocumentChunk, float]]:
    query_vec = get_embedding(query)

    if db.bind.dialect.name == "postgresql":
        q = db.query(models.DocumentChunk)
        if document_id is not None:
            q = q.filter(models.DocumentChunk.document_id == document_id)
        chunks = (
            q.order_by(models.DocumentChunk.embedding.cosine_distance(query_vec.tolist()))
            .limit(limit)
            .all()
        )
        results = []
        norm_q = np.linalg.norm(query_vec)
        for chunk in chunks:
            chunk_vec = np.array(chunk.embedding, dtype=np.float32)
            norm_c = np.linalg.norm(chunk_vec)
            sim = float(np.dot(query_vec, chunk_vec) / (norm_q * norm_c)) if norm_q and norm_c else 0.0
            results.append((chunk, sim))
        return results

    if HAS_FAISS:
        return _search_faiss(db, query_vec, limit, document_id)

    return _search_bruteforce(db, query_vec, limit, document_id)
