from typing import Dict, List
from fastapi import WebSocket, WebSocketDisconnect
import json

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int):
        connections = self.active_connections.get(user_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.active_connections.pop(user_id, None)

    async def send_personal_message(self, message: dict, user_id: int):
        connections = self.active_connections.get(user_id, [])
        data = json.dumps(message)
        for connection in connections[:]:
            try:
                await connection.send_text(data)
            except WebSocketDisconnect:
                self.disconnect(connection, user_id)
            except Exception:
                self.disconnect(connection, user_id)

    async def broadcast(self, message: dict):
        data = json.dumps(message)
        for user_id, connections in list(self.active_connections.items()):
            for connection in connections[:]:
                try:
                    await connection.send_text(data)
                except WebSocketDisconnect:
                    self.disconnect(connection, user_id)
                except Exception:
                    self.disconnect(connection, user_id)

manager = ConnectionManager()
