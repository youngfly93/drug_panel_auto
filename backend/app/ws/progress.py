"""WebSocket endpoint for batch task progress streaming."""

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import authenticate_access_token, user_can_access_task
from app.models.task import Task

router = APIRouter()

# Active WebSocket connections per task_id
_connections: dict[str, list[WebSocket]] = defaultdict(list)


async def broadcast_progress(task_id: str, message: dict[str, Any]) -> None:
    """Broadcast a progress message to all connected clients for a task."""
    import json

    dead = []
    for ws in _connections.get(task_id, []):
        try:
            await ws.send_text(json.dumps(message, ensure_ascii=False))
        except Exception:
            dead.append(ws)
    # Cleanup dead connections
    for ws in dead:
        _connections[task_id].remove(ws)


@router.websocket("/ws/tasks/{task_id}/progress")
async def task_progress_ws(
    websocket: WebSocket,
    task_id: str,
    db: Session = Depends(get_db),
):
    await websocket.accept()
    try:
        raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        auth_message = json.loads(raw_auth)
        if auth_message.get("type") != "authenticate":
            raise ValueError("authentication message required")
        token = auth_message.get("token")
        if not isinstance(token, str) or not token:
            raise ValueError("bearer token required")
        user = authenticate_access_token(token, db)
    except (asyncio.TimeoutError, HTTPException, ValueError, json.JSONDecodeError):
        await websocket.close(code=4401, reason="Not authenticated")
        return
    except WebSocketDisconnect:
        return

    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        await websocket.close(code=4404, reason="Task not found")
        return
    if not user_can_access_task(user, task):
        await websocket.close(code=4403, reason="Forbidden")
        return

    _connections[task_id].append(websocket)
    await websocket.send_json({"type": "authenticated", "task_id": task_id})
    try:
        while True:
            # Keep connection alive; client may send ping/cancel
            data = await websocket.receive_text()
            if data == "cancel":
                # TODO: implement task cancellation
                pass
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _connections[task_id]:
            _connections[task_id].remove(websocket)
        if not _connections[task_id]:
            del _connections[task_id]
