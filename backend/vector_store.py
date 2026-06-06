import os
import numpy as np
from sqlalchemy.orm import Session

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    genai = None
    HAS_GENAI = False

import models

# Configure Gemini API if key is available
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if HAS_GENAI and GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def get_embedding(text: str) -> np.ndarray:
    """
    Generate embedding for a string using Google Gemini API.
    Falls back to a random vector if API key is not configured.
    """
    if not HAS_GENAI or not GEMINI_API_KEY:
        # Mock embedding (dimension 768)
        # Seed it with hash of text to make it slightly deterministic
        state = np.random.RandomState(abs(hash(text)) % (2**32))
        vec = state.randn(768)
        norm = np.linalg.norm(vec)
        return (vec / norm if norm > 0 else vec).astype(np.float32)
        
    try:
        response = genai.embed_content(
            model="models/text-embedding-004",
            contents=text,
            task_type="retrieval_document"
        )
        embedding_list = response["embedding"]
        return np.array(embedding_list, dtype=np.float32)
    except Exception as e:
        print(f"Gemini Embedding Error: {e}. Falling back to mock vector.")
        # Fallback
        state = np.random.RandomState(abs(hash(text)) % (2**32))
        vec = state.randn(768)
        norm = np.linalg.norm(vec)
        return (vec / norm if norm > 0 else vec).astype(np.float32)

def store_chunk(db: Session, document_id: int, chunk_text: str):
    """
    Generate embedding for the chunk and save it to the DB.
    """
    emb_vec = get_embedding(chunk_text)
    if db.bind.dialect.name == "sqlite":
        emb_value = emb_vec.tobytes()
    else:
        emb_value = emb_vec.tolist()
    
    db_chunk = models.DocumentChunk(
        document_id=document_id,
        chunk_text=chunk_text,
        embedding=emb_value
    )
    db.add(db_chunk)
    db.commit()

def search_semantic(db: Session, query: str, limit: int = 5, document_id: int = None):
    """
    Perform a vector search using local SQLite fallback or Postgres/pgvector.
    """
    query_vec = get_embedding(query)
    
    # Query chunks
    q = db.query(models.DocumentChunk)
    if document_id is not None:
        q = q.filter(models.DocumentChunk.document_id == document_id)

    if db.bind.dialect.name == "postgresql":
        chunks = q.order_by(models.DocumentChunk.embedding.cosine_distance(query_vec.tolist())).limit(limit).all()
    else:
        chunks = q.all()

    if not chunks:
        return []
        
    results = []
    for chunk in chunks:
        if isinstance(chunk.embedding, (bytes, bytearray)):
            chunk_vec = np.frombuffer(chunk.embedding, dtype=np.float32)
        else:
            chunk_vec = np.array(chunk.embedding, dtype=np.float32)
        
        dot_product = np.dot(query_vec, chunk_vec)
        norm_q = np.linalg.norm(query_vec)
        norm_c = np.linalg.norm(chunk_vec)
        
        similarity = 0.0
        if norm_q > 0 and norm_c > 0:
            similarity = float(dot_product / (norm_q * norm_c))
            
        results.append((chunk, similarity))
        
    # Sort by similarity descending for any fallback case
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:limit]
