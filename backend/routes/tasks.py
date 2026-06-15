"""
Task Queue Monitoring Routes
Provides endpoints for querying task status, progress, and dead-letter queue.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import task_queue

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}")
async def get_task(task_id: int):
    """
    Get detailed status and progress of a task.
    
    Returns:
        {
            "id": 123,
            "task_type": "workflow_run",
            "status": "running",  # pending, running, completed, failed, dead_letter
            "progress_percent": 75,
            "progress_message": "Processing nodes...",
            "retry_count": 0,
            "max_retries": 3,
            "created_at": "2026-06-15T10:30:00",
            "started_at": "2026-06-15T10:30:01",
            "completed_at": null,
            "error_message": null,
            "result": null
        }
    """
    status = await task_queue.get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@router.get("/")
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    List tasks with optional filtering.
    
    Query Parameters:
        status: Filter by status (pending, running, completed, failed, dead_letter)
        limit: Maximum number of results (1-500)
        offset: Pagination offset
    
    Returns:
        Array of task summaries
    """
    from database import SessionLocal
    import models
    
    db = SessionLocal()
    try:
        query = db.query(models.QueueTask)
        
        if status:
            query = query.filter(models.QueueTask.status == status)
        
        total = query.count()
        
        tasks = query.order_by(models.QueueTask.created_at.desc()).offset(offset).limit(limit).all()
        
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "tasks": [
                {
                    "id": t.id,
                    "task_type": t.task_type,
                    "status": t.status,
                    "progress_percent": t.progress_percent,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "started_at": t.started_at.isoformat() if t.started_at else None,
                    "retry_count": t.retry_count,
                }
                for t in tasks
            ],
        }
    finally:
        db.close()


@router.get("/dead-letter/queue")
async def list_dead_letter_tasks(
    limit: int = Query(50, ge=1, le=500),
):
    """
    Get tasks that have exhausted retries and moved to dead-letter queue.
    
    Use this to monitor failed tasks that need investigation or replay.
    
    Returns:
        Array of dead-letter tasks with error information
    """
    dead_letter = await task_queue.get_dead_letter_tasks(limit)
    return {
        "count": len(dead_letter),
        "limit": limit,
        "tasks": dead_letter,
    }


@router.post("/{task_id}/retry")
async def retry_dead_letter_task(task_id: int):
    """
    Manually retry a dead-letter task by resetting it to pending status.
    
    This allows recovery from transient failures.
    """
    from database import SessionLocal
    import models
    
    db = SessionLocal()
    try:
        task = db.query(models.QueueTask).filter(models.QueueTask.id == task_id).first()
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task.status != "dead_letter":
            raise HTTPException(
                status_code=400,
                detail=f"Only dead-letter tasks can be retried. Current status: {task.status}",
            )
        
        # Reset for retry
        task.status = "pending"
        task.retry_count = 0
        task.error_message = None
        task.error_traceback = None
        task.started_at = None
        task.completed_at = None
        db.commit()
        
        return {
            "task_id": task_id,
            "status": "pending",
            "message": "Task reset to pending queue for retry",
        }
    finally:
        db.close()


@router.get("/stats/queue")
async def get_queue_stats():
    """
    Get queue statistics and health metrics.
    
    Returns:
        {
            "pending": 5,
            "running": 2,
            "completed": 150,
            "failed": 3,
            "dead_letter": 1,
            "avg_completion_time_sec": 45.2
        }
    """
    from database import SessionLocal
    import models
    from sqlalchemy import func
    
    db = SessionLocal()
    try:
        # Count by status
        stats = {
            "pending": db.query(models.QueueTask).filter(models.QueueTask.status == "pending").count(),
            "running": db.query(models.QueueTask).filter(models.QueueTask.status == "running").count(),
            "completed": db.query(models.QueueTask).filter(models.QueueTask.status == "completed").count(),
            "failed": db.query(models.QueueTask).filter(models.QueueTask.status == "failed").count(),
            "dead_letter": db.query(models.QueueTask).filter(models.QueueTask.status == "dead_letter").count(),
        }
        
        # Calculate average completion time for completed tasks
        avg_completion = db.query(
            func.avg(func.strftime('%s', models.QueueTask.completed_at) - func.strftime('%s', models.QueueTask.started_at))
        ).filter(
            models.QueueTask.status == "completed",
            models.QueueTask.started_at.isnot(None),
            models.QueueTask.completed_at.isnot(None),
        ).scalar()
        
        stats["avg_completion_time_sec"] = float(avg_completion) if avg_completion else 0.0
        
        return stats
    finally:
        db.close()
