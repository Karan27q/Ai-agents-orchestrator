import asyncio
import threading
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
import datetime

from database import get_db
import models
import auth
from ws_manager import manager as ws_manager

router = APIRouter(prefix="/notifications", tags=["notifications"])

class NotificationResponse(BaseModel):
    id: int
    user_id: int
    message: str
    is_read: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class NotificationReadRequest(BaseModel):
    notification_ids: List[int]

@router.get("", response_model=List[NotificationResponse])
def get_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id
    ).order_by(models.Notification.created_at.desc()).all()

@router.post("/read")
def mark_as_read(
    req: NotificationReadRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    notifications = db.query(models.Notification).filter(
        models.Notification.id.in_(req.notification_ids),
        models.Notification.user_id == current_user.id
    ).all()
    
    for notification in notifications:
        notification.is_read = True
        
    db.commit()
    return {"message": f"Successfully marked {len(notifications)} notifications as read."}

# Utility function to add in-app notifications
def create_notification(db: Session, user_id: int, message: str) -> models.Notification:
    notif = models.Notification(
        user_id=user_id,
        message=message,
        is_read=False
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    payload = {
        "type": "notification",
        "notification": {
            "id": notif.id,
            "user_id": notif.user_id,
            "message": notif.message,
            "is_read": notif.is_read,
            "created_at": notif.created_at.isoformat()
        }
    }
    asyncio.create_task(ws_manager.send_personal_message(payload, user_id))
    return notif
