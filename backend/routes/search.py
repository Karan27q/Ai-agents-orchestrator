from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Any

from database import get_db
import models
import auth
import vector_store
from rate_limiter import limiter

router = APIRouter(prefix="/search", tags=["search"])

class SemanticSearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 5

class SearchResultChunk(BaseModel):
    document_id: int
    file_name: str
    chunk_text: str
    similarity: float

class GlobalSearchResponse(BaseModel):
    workflows: List[Any]
    documents: List[Any]
    semantic_chunks: List[SearchResultChunk]

@router.post("/semantic", response_model=List[SearchResultChunk])
@limiter.limit("30/minute")
def search_semantic(
    req: SemanticSearchRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    results = vector_store.search_semantic(db, req.query, limit=req.limit)
    
    response_data = []
    for chunk, similarity in results:
        response_data.append({
            "document_id": chunk.document_id,
            "file_name": chunk.document.file_name,
            "chunk_text": chunk.chunk_text,
            "similarity": similarity
        })
    return response_data

@router.get("", response_model=GlobalSearchResponse)
def global_search(
    q: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Performs a hybrid global search across workflows, documents (metadata),
    and semantic vector chunks.
    """
    if not q or len(q) < 2:
        return {"workflows": [], "documents": [], "semantic_chunks": []}

    # 1. Search Workflows in Org
    workflows = db.query(models.Workflow).filter(
        models.Workflow.organization_id == current_user.organization_id,
        models.Workflow.name.like(f"%{q}%")
    ).limit(5).all()

    # 2. Search Documents
    documents = db.query(models.Document).filter(
        models.Document.file_name.like(f"%{q}%")
    ).limit(5).all()

    # 3. Search Semantic Chunks
    semantic_results = vector_store.search_semantic(db, q, limit=5)
    chunks_response = []
    for chunk, similarity in semantic_results:
        chunks_response.append({
            "document_id": chunk.document_id,
            "file_name": chunk.document.file_name,
            "chunk_text": chunk.chunk_text,
            "similarity": similarity
        })

    # Prepare serialized lists
    workflows_list = [
        {"id": w.id, "name": w.name, "description": w.description, "status": w.status}
        for w in workflows
    ]
    documents_list = [
        {"id": d.id, "file_name": d.file_name, "file_type": d.file_type, "status": d.embedding_status}
        for d in documents
    ]

    return {
        "workflows": workflows_list,
        "documents": documents_list,
        "semantic_chunks": chunks_response
    }
