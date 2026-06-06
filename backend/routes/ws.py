from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy.orm import Session
from database import SessionLocal
import auth
import models
from ws_manager import manager

router = APIRouter(tags=["websockets"])

@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket, token: str = Query(None)):
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    db: Session = SessionLocal()
    try:
        user = auth.get_current_user(token=token, db=db)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        db.close()
        return

    await manager.connect(websocket, user.id)
    try:
        await websocket.send_text('{"type":"connected","message":"WebSocket notification channel opened."}')
        while True:
            data = await websocket.receive_text()
            if data.lower() in {"ping", "keepalive"}:
                await websocket.send_text('{"type":"pong"}')
            else:
                await websocket.send_text('{"type":"ack","message":"received"}')
    except WebSocketDisconnect:
        manager.disconnect(websocket, user.id)
    finally:
        db.close()
