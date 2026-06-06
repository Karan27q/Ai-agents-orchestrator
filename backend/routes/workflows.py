from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import datetime
import json

from database import get_db
import models
import auth
from workflow_engine import start_workflow_run

router = APIRouter(prefix="/workflows", tags=["workflows"])

class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    workflow_json: str
    status: Optional[str] = "draft"

class WorkflowResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    workflow_json: str
    status: str
    organization_id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True

class WorkflowRunResponse(BaseModel):
    id: int
    workflow_id: int
    status: str
    started_at: datetime.datetime
    completed_at: Optional[datetime.datetime]
    logs: str
    results: Optional[str]

    class Config:
        from_attributes = True

@router.post("", response_model=WorkflowResponse)
def create_workflow(
    workflow_in: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_developer)
):
    workflow = models.Workflow(
        name=workflow_in.name,
        description=workflow_in.description,
        workflow_json=workflow_in.workflow_json,
        status=workflow_in.status,
        organization_id=current_user.organization_id,
        created_by=current_user.id
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow

@router.get("", response_model=List[WorkflowResponse])
def list_workflows(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500)
):
    """List workflows with pagination for better throughput."""
    query = db.query(models.Workflow).filter(
        models.Workflow.organization_id == current_user.organization_id
    )
    
    # Count total for header (optional, can be cached)
    total = query.count()
    
    # Apply pagination
    workflows = query.order_by(models.Workflow.created_at.desc()).offset(skip).limit(limit).all()
    
    return workflows

@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    workflow = db.query(models.Workflow).filter(
        models.Workflow.id == workflow_id,
        models.Workflow.organization_id == current_user.organization_id
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return workflow

@router.put("/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(
    workflow_id: int,
    workflow_in: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_developer)
):
    workflow = db.query(models.Workflow).filter(
        models.Workflow.id == workflow_id,
        models.Workflow.organization_id == current_user.organization_id
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
        
    workflow.name = workflow_in.name
    workflow.description = workflow_in.description
    workflow.workflow_json = workflow_in.workflow_json
    workflow.status = workflow_in.status
    workflow.updated_at = datetime.datetime.utcnow()
    
    db.commit()
    db.refresh(workflow)
    return workflow

@router.delete("/{workflow_id}")
def delete_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_admin)
):
    workflow = db.query(models.Workflow).filter(
        models.Workflow.id == workflow_id,
        models.Workflow.organization_id == current_user.organization_id
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
        
    db.delete(workflow)
    db.commit()
    return {"message": "Workflow deleted successfully."}

@router.post("/{workflow_id}/run", response_model=WorkflowRunResponse)
async def run_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_developer)
):
    workflow = db.query(models.Workflow).filter(
        models.Workflow.id == workflow_id,
        models.Workflow.organization_id == current_user.organization_id
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
        
    # Create workflow run
    run = models.WorkflowRun(
        workflow_id=workflow.id,
        status="pending",
        logs="Initialising workflow run...",
        started_at=datetime.datetime.utcnow()
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    
    # Start execution in the background using the workflow engine helper
    start_workflow_run(run.id)
    
    return run

@router.get("/{workflow_id}/runs", response_model=List[WorkflowRunResponse])
def list_workflow_runs(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Verify workflow ownership
    workflow = db.query(models.Workflow).filter(
        models.Workflow.id == workflow_id,
        models.Workflow.organization_id == current_user.organization_id
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
        
    return db.query(models.WorkflowRun).filter(
        models.WorkflowRun.workflow_id == workflow_id
    ).order_by(models.WorkflowRun.started_at.desc()).all()

@router.get("/runs/{run_id}", response_model=WorkflowRunResponse)
def get_run_details(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    run = db.query(models.WorkflowRun).filter(models.WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found.")
        
    # Verify organization access
    if run.workflow.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this run.")
        
    return run
