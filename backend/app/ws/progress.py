"""WebSocket endpoint for batch task progress streaming."""

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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
async def task_progress_ws(websocket: WebSocket, task_id: str):
    await websocket.accept()
    _connections[task_id].append(websocket)
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
