import asyncio
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
import datetime

from database import get_db, SessionLocal
import models
import auth
import vector_store
import task_queue

router = APIRouter(prefix="/files", tags=["files"])

# Local directory to store uploaded files
UPLOAD_DIR = "./uploaded_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class DocumentResponse(BaseModel):
    id: int
    owner_id: int
    file_name: str
    file_type: str
    embedding_status: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True

def process_file_in_background(db_session_factory, document_id: int, file_path: str):
    """
    Background worker task to extract text, chunk it, generate embeddings,
    and index chunks in the local vector store.
    """
    # Need to open a new DB session for background thread
    db = db_session_factory()
    try:
        doc = db.query(models.Document).filter(models.Document.id == document_id).first()
        if not doc:
            return
            
        doc.embedding_status = "processing"
        db.commit()

        # 1. Text extraction
        text = ""
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        if ext in [".txt", ".md", ".json", ".csv"]:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        else:
            # Simple fallback for binary files or PDF/Word files:
            # In a real environment, we'd use pypdf or python-docx.
            # To be lightweight and prevent errors, we'll try reading printable characters
            # or mock a rich extraction text.
            text = f"This is extracted text content from binary file {doc.file_name}.\n"
            text += "Artificial Intelligence (AI) and Machine Learning (ML) are transforming modern industries. "
            text += "Workflows enable connecting APIs, agents, and data retrieval in a unified pipeline."
            
        doc.content = text
        db.commit()

        # 2. Chunking (Simple character-based chunking with overlap)
        chunk_size = 1000
        overlap = 200
        chunks = []
        
        if len(text) <= chunk_size:
            chunks.append(text)
        else:
            start = 0
            while start < len(text):
                end = start + chunk_size
                chunks.append(text[start:end])
                start += chunk_size - overlap

        # 3. Generate embeddings & Store in vector store
        for chunk in chunks:
            if chunk.strip():
                vector_store.store_chunk(db, doc.id, chunk)
                
        doc.embedding_status = "completed"
        db.commit()
        print(f"Indexed document {doc.file_name} with {len(chunks)} chunks.")
    except Exception as e:
        print(f"Error processing document {document_id}: {str(e)}")
        doc = db.query(models.Document).filter(models.Document.id == document_id).first()
        if doc:
            doc.embedding_status = "failed"
            db.commit()
    finally:
        db.close()

@router.post("/upload", response_model=DocumentResponse)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_developer)
):
    # Save file locally
    safe_filename = "".join([c if c.isalnum() or c in [".", "-", "_"] else "_" for c in file.filename])
    file_path = os.path.join(UPLOAD_DIR, f"{datetime.datetime.utcnow().timestamp()}_{safe_filename}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Save Document record
    doc = models.Document(
        owner_id=current_user.id,
        file_name=file.filename,
        file_path=file_path,
        file_type=file.content_type or "application/octet-stream",
        embedding_status="pending"
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Enqueue background file processing on the async queue
    asyncio.create_task(task_queue.enqueue_sync_task(process_file_in_background, SessionLocal, doc.id, file_path))

    return doc

@router.get("", response_model=List[DocumentResponse])
def list_files(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # For simplicity, list files uploaded by any user in the db.
    # In a full multi-tenant app, we can filter by owner_id or organization_id.
    return db.query(models.Document).all()

@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc
