"""
Enhanced async task queue with:
- Database persistence (tasks survive server restarts)
- Retry logic with exponential backoff
- Timeout handling
- Dead-letter queue for failed tasks
- Progress tracking & webhooks
"""

import asyncio
import json
import traceback
import time
from typing import Callable, Coroutine, Any, Optional, Dict
from datetime import datetime, timedelta
import os
import httpx

from sqlalchemy.orm import Session
import models
from database import SessionLocal

WORKER_COUNT = int(os.getenv("TASK_QUEUE_WORKERS", "4"))
RETRY_BASE_DELAY = 5  # seconds
MAX_RETRY_DELAY = 300  # 5 minutes max between retries


class PersistentTaskQueue:
    """Database-backed task queue with retry and timeout handling."""
    
    def __init__(self):
        self.http_client: Optional[httpx.AsyncClient] = None
    
    async def get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for webhook delivery."""
        if self.http_client is None or self.http_client.is_closed:
            self.http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                limits=httpx.Limits(max_connections=50),
            )
        return self.http_client
    
    async def enqueue_task(
        self,
        task_type: str,
        payload: Dict[str, Any],
        max_retries: int = 3,
        timeout_seconds: int = 300,
        webhook_url: Optional[str] = None,
        workflow_run_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> int:
        """
        Enqueue a new task with persistence.
        
        Returns: task_id (for monitoring)
        """
        db = SessionLocal()
        try:
            task = models.QueueTask(
                task_type=task_type,
                payload=json.dumps(payload),
                status="pending",
                max_retries=max_retries,
                timeout_seconds=timeout_seconds,
                webhook_url=webhook_url,
                workflow_run_id=workflow_run_id,
                document_id=document_id,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            task_id = task.id
            print(f"[QUEUE] Task {task_id} ({task_type}) enqueued")
            return task_id
        finally:
            db.close()
    
    async def _send_webhook(
        self,
        webhook_url: str,
        event_type: str,
        task_id: int,
        data: Dict[str, Any],
    ) -> bool:
        """Send webhook notification for task progress/completion."""
        try:
            client = await self.get_http_client()
            payload = {
                "event": event_type,
                "task_id": task_id,
                "timestamp": datetime.utcnow().isoformat(),
                **data,
            }
            response = await client.post(webhook_url, json=payload, timeout=10.0)
            return response.status_code < 400
        except Exception as e:
            print(f"[WEBHOOK ERROR] Failed to send webhook to {webhook_url}: {e}")
            return False
    
    async def _update_task_progress(
        self,
        task_id: int,
        progress_percent: int,
        progress_message: str,
    ):
        """Update task progress in database and send webhook if configured."""
        db = SessionLocal()
        try:
            task = db.query(models.QueueTask).filter(models.QueueTask.id == task_id).first()
            if task:
                task.progress_percent = progress_percent
                task.progress_message = progress_message
                db.commit()
                
                if task.webhook_url:
                    await self._send_webhook(
                        task.webhook_url,
                        "progress",
                        task_id,
                        {"progress": progress_percent, "message": progress_message},
                    )
        finally:
            db.close()
    
    async def _handle_task_completion(
        self,
        task_id: int,
        result: Any,
    ):
        """Mark task as completed and send webhook."""
        db = SessionLocal()
        try:
            task = db.query(models.QueueTask).filter(models.QueueTask.id == task_id).first()
            if task:
                task.status = "completed"
                task.completed_at = datetime.utcnow()
                task.result = json.dumps(result) if result is not None else None
                task.progress_percent = 100
                db.commit()
                
                if task.webhook_url:
                    await self._send_webhook(
                        task.webhook_url,
                        "completed",
                        task_id,
                        {"result": result},
                    )
                
                print(f"[QUEUE] Task {task_id} completed successfully")
        finally:
            db.close()
    
    async def _handle_task_failure(
        self,
        task_id: int,
        error_message: str,
        error_traceback: str,
    ):
        """Handle task failure with retry logic or dead-letter routing."""
        db = SessionLocal()
        try:
            task = db.query(models.QueueTask).filter(models.QueueTask.id == task_id).first()
            if not task:
                return
            
            task.error_message = error_message
            task.error_traceback = error_traceback
            task.retry_count += 1
            
            if task.retry_count < task.max_retries:
                # Calculate exponential backoff: 5s, 25s, 125s (max 5min)
                delay = min(
                    RETRY_BASE_DELAY ** task.retry_count,
                    MAX_RETRY_DELAY,
                )
                task.status = "pending"
                task.started_at = None
                print(f"[QUEUE] Task {task_id} will retry in {delay}s (attempt {task.retry_count}/{task.max_retries})")
                
                # Schedule retry
                db.commit()
                await asyncio.sleep(delay)
            else:
                # Max retries exhausted -> dead-letter queue
                task.status = "dead_letter"
                task.completed_at = datetime.utcnow()
                print(f"[QUEUE] Task {task_id} moved to dead-letter queue after {task.retry_count} retries")
                
                if task.webhook_url:
                    await self._send_webhook(
                        task.webhook_url,
                        "dead_letter",
                        task_id,
                        {"error": error_message, "retries": task.retry_count},
                    )
            
            db.commit()
        finally:
            db.close()
    
    async def _execute_task(self, task_id: int, task_func: Callable, *args, **kwargs):
        """Execute a task with timeout handling."""
        db = SessionLocal()
        try:
            task = db.query(models.QueueTask).filter(models.QueueTask.id == task_id).first()
            if not task:
                print(f"[QUEUE] Task {task_id} not found")
                return
            
            # Mark as running
            task.status = "running"
            task.started_at = datetime.utcnow()
            db.commit()
            db.close()
            
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    task_func(*args, **kwargs),
                    timeout=task.timeout_seconds,
                )
                await self._handle_task_completion(task_id, result)
            
            except asyncio.TimeoutError:
                error_msg = f"Task exceeded timeout of {task.timeout_seconds}s"
                print(f"[QUEUE] {error_msg}")
                await self._handle_task_failure(task_id, error_msg, "TimeoutError")
            
            except Exception as e:
                error_msg = str(e)
                error_tb = traceback.format_exc()
                print(f"[QUEUE] Task {task_id} error: {error_msg}")
                await self._handle_task_failure(task_id, error_msg, error_tb)
        
        except Exception as e:
            print(f"[QUEUE] Fatal error in task execution: {e}")
        finally:
            if db:
                db.close()
    
    async def process_pending_tasks(self):
        """
        Worker loop: continuously process pending tasks from database.
        Handles retries by re-querying pending tasks.
        """
        print(f"[QUEUE] Worker started (processing pending tasks)")
        
        while True:
            try:
                db = SessionLocal()
                
                # Fetch next pending task
                pending_task = (
                    db.query(models.QueueTask)
                    .filter(models.QueueTask.status == "pending")
                    .order_by(models.QueueTask.created_at)
                    .first()
                )
                
                db.close()
                
                if not pending_task:
                    # No pending tasks, wait and retry
                    await asyncio.sleep(1)
                    continue
                
                task_id = pending_task.id
                task_type = pending_task.task_type
                
                print(f"[QUEUE] Processing task {task_id} (type: {task_type})")
                
                # Deserialize payload
                try:
                    payload = json.loads(pending_task.payload)
                except json.JSONDecodeError:
                    await self._handle_task_failure(
                        task_id,
                        "Invalid JSON payload",
                        "JSONDecodeError",
                    )
                    continue
                
                # Route to appropriate handler
                if task_type == "workflow_run":
                    await self._execute_task(
                        task_id,
                        self._handle_workflow_run,
                        payload,
                    )
                elif task_type == "document_embed":
                    await self._execute_task(
                        task_id,
                        self._handle_document_embed,
                        payload,
                    )
                else:
                    await self._handle_task_failure(
                        task_id,
                        f"Unknown task type: {task_type}",
                        "UnknownTaskType",
                    )
            
            except Exception as e:
                print(f"[QUEUE] Worker error: {e}")
                await asyncio.sleep(1)
    
    async def _handle_workflow_run(self, payload: Dict[str, Any]):
        """Example workflow run handler - extend as needed."""
        # This would call your actual workflow execution logic
        # For now, it's a placeholder for demonstration
        workflow_run_id = payload.get("workflow_run_id")
        print(f"[TASK] Executing workflow run {workflow_run_id}")
        # In real implementation: import workflow_engine and execute
        await asyncio.sleep(1)
        return {"workflow_run_id": workflow_run_id, "status": "completed"}
    
    async def _handle_document_embed(self, payload: Dict[str, Any]):
        """Example document embedding handler - extend as needed."""
        document_id = payload.get("document_id")
        print(f"[TASK] Embedding document {document_id}")
        # In real implementation: call embedding service
        await asyncio.sleep(1)
        return {"document_id": document_id, "embedding_status": "completed"}


# Global queue instance
_queue: Optional[PersistentTaskQueue] = None


async def get_queue() -> PersistentTaskQueue:
    """Get or create the global queue instance."""
    global _queue
    if _queue is None:
        _queue = PersistentTaskQueue()
    return _queue


async def enqueue_task(
    task_type: str,
    payload: Dict[str, Any],
    max_retries: int = 3,
    timeout_seconds: int = 300,
    webhook_url: Optional[str] = None,
    workflow_run_id: Optional[int] = None,
    document_id: Optional[int] = None,
) -> int:
    """
    Enqueue a task. Returns task_id for monitoring.
    
    Args:
        task_type: Type of task (e.g., "workflow_run", "document_embed")
        payload: Task data as dict
        max_retries: Maximum number of retries on failure
        timeout_seconds: Task timeout in seconds
        webhook_url: Optional webhook URL for progress/completion notifications
        workflow_run_id: Associated workflow run ID
        document_id: Associated document ID
    
    Returns:
        task_id: Unique task identifier
    """
    queue = await get_queue()
    return await queue.enqueue_task(
        task_type=task_type,
        payload=payload,
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
        webhook_url=webhook_url,
        workflow_run_id=workflow_run_id,
        document_id=document_id,
    )


async def start_queue_workers():
    """Start the persistent task queue worker processes."""
    print(f"[QUEUE] Starting {WORKER_COUNT} workers...")
    queue = await get_queue()
    
    # Start worker tasks
    for i in range(WORKER_COUNT):
        asyncio.create_task(queue.process_pending_tasks())
    
    print(f"[QUEUE] {WORKER_COUNT} workers started")


async def get_task_status(task_id: int) -> Optional[Dict[str, Any]]:
    """Query task status and progress."""
    db = SessionLocal()
    try:
        task = db.query(models.QueueTask).filter(models.QueueTask.id == task_id).first()
        if not task:
            return None
        
        return {
            "id": task.id,
            "task_type": task.task_type,
            "status": task.status,
            "progress_percent": task.progress_percent,
            "progress_message": task.progress_message,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "error_message": task.error_message,
            "result": json.loads(task.result) if task.result else None,
        }
    finally:
        db.close()


async def get_dead_letter_tasks(limit: int = 50) -> list:
    """Query dead-letter queue tasks."""
    db = SessionLocal()
    try:
        tasks = (
            db.query(models.QueueTask)
            .filter(models.QueueTask.status == "dead_letter")
            .order_by(models.QueueTask.completed_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": t.id,
                "task_type": t.task_type,
                "error_message": t.error_message,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "retry_count": t.retry_count,
            }
            for t in tasks
        ]
    finally:
        db.close()
