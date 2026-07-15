from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.router import api_router
from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.main import create_app
from app.ws import progress as progress_ws


def _unauthenticated_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_current_user] = lambda: None
    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/tasks",
        "/api/v1/tasks/stats",
        "/api/v1/excel/missing/sheets",
        "/api/v1/reports/missing",
        "/api/v1/admin/ops/status",
        "/api/v1/config/mapping.yaml",
    ],
)
def test_sensitive_http_routes_reject_unauthenticated_requests(path: str) -> None:
    with _unauthenticated_client() as client:
        assert client.get(path).status_code == 401


def test_health_endpoint_is_public_and_minimal() -> None:
    with _unauthenticated_client() as client:
        response = client.get("/api/v1/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_production_can_disable_api_documentation(monkeypatch) -> None:
    monkeypatch.setattr(settings, "docs_enabled", False)
    app = create_app()

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/ops/status",
        "/api/v1/config/mapping.yaml",
    ],
)
def test_admin_routes_reject_authenticated_non_admin_users(path: str) -> None:
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2,
        role="user",
        is_active=True,
    )

    with TestClient(app) as client:
        assert client.get(path).status_code == 403


def _websocket_client(monkeypatch, *, valid_token: bool) -> TestClient:
    app = FastAPI()
    app.include_router(progress_ws.router)
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()

    def authenticate(token, _db):
        if not valid_token or token != "synthetic-token":
            raise HTTPException(status_code=401, detail="Invalid token")
        return SimpleNamespace(id=1, is_active=True)

    monkeypatch.setattr(progress_ws, "authenticate_access_token", authenticate)
    return TestClient(app)


def test_websocket_requires_authentication_message(monkeypatch) -> None:
    with _websocket_client(monkeypatch, valid_token=True) as client:
        with client.websocket_connect("/ws/tasks/synthetic/progress") as websocket:
            websocket.send_json({"type": "authenticate", "token": "synthetic-token"})
            assert websocket.receive_json() == {
                "type": "authenticated",
                "task_id": "synthetic",
            }


def test_websocket_rejects_invalid_token(monkeypatch) -> None:
    with _websocket_client(monkeypatch, valid_token=False) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/tasks/synthetic/progress") as websocket:
                websocket.send_json({"type": "authenticate", "token": "bad-token"})
                websocket.receive_json()
    assert exc_info.value.code == 4401
