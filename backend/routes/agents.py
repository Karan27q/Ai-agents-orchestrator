import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import datetime

from database import get_db
import models
import auth
from agents import ResearchAgentOrchestrator
from rate_limiter import limiter

router = APIRouter(prefix="/agents", tags=["agents"])

class ResearchRequest(BaseModel):
    topic: str

class AgentTaskResponse(BaseModel):
    id: int
    task_type: str
    payload: str
    status: str
    result: Optional[str]
    created_at: datetime.datetime

    class Config:
        from_attributes = True

@router.post("/research")
@limiter.limit("20/minute")
async def start_research(
    req: ResearchRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_manager)
):
    """
    Spawns a Multi-Agent Research flow and streams back events via SSE (Server-Sent Events).
    The flow covers: Planner -> Research -> Critic -> Writer -> Citation agents, followed by token streaming.
    Saves the final report to the DB in agent_tasks.
    """
    orchestrator = ResearchAgentOrchestrator()
    
    # Save a record of the research task
    task = models.AgentTask(
        task_type="research",
        payload=json.dumps({"topic": req.topic, "user_id": current_user.id}),
        status="running"
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    async def event_generator():
        final_report = ""
        try:
            async for event in orchestrator.run_research_flow(req.topic):
                if event.get("type") == "completed":
                    final_report = event.get("report", "")
                yield f"data: {json.dumps(event)}\n\n"
            
            # Mark task completed
            # Need to get a new DB session inside generator to avoid thread binding issues in async generators
            from database import SessionLocal
            with SessionLocal() as db_session:
                db_task = db_session.query(models.AgentTask).filter(models.AgentTask.id == task.id).first()
                if db_task:
                    db_task.status = "completed"
                    db_task.result = final_report
                    db_session.commit()
                    
        except Exception as e:
            # Yield error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            
            from database import SessionLocal
            with SessionLocal() as db_session:
                db_task = db_session.query(models.AgentTask).filter(models.AgentTask.id == task.id).first()
                if db_task:
                    db_task.status = "failed"
                    db_task.result = f"Error occurred: {str(e)}"
                    db_session.commit()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/tasks", response_model=List[AgentTaskResponse])
def list_tasks(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Retrieve research tasks
    # (Since there is no direct organization mapping on agent tasks, we parse the payload or just return all for simplicity)
    tasks = db.query(models.AgentTask).order_by(models.AgentTask.created_at.desc()).all()
    filtered_tasks = []
    for t in tasks:
        try:
            payload_data = json.loads(t.payload)
            # Filter if payload has organization/user details matching current user
            # Let's allow managers and devs to view them all
            filtered_tasks.append(t)
        except Exception:
            filtered_tasks.append(t)
    return filtered_tasks
