from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.api.router import api_router
from app.config import settings
from app.database import Base, get_db
from app.dependencies import get_current_user, require_admin, require_user
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
    app = FastAPI()
    app.include_router(api_router)

    def fail_if_database_is_touched():
        raise AssertionError("anonymous health probe must not resolve a database")

    app.dependency_overrides[get_db] = fail_if_database_is_touched
    app.dependency_overrides[get_current_user] = lambda: None

    with TestClient(app) as client:
        response = client.get("/api/v1/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    health_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/healthz"
    ]
    assert len(health_routes) == 1
    assert health_routes[0].methods == {"GET"}
    assert health_routes[0].include_in_schema is False
    assert "/api/v1/healthz" not in app.openapi()["paths"]


def _dependency_calls(route: APIRoute) -> set[object]:
    calls: set[object] = set()

    def collect(dependant) -> None:
        for child in dependant.dependencies:
            if child.call is not None:
                calls.add(child.call)
            collect(child)

    collect(route.dependant)
    return calls


def test_all_non_exempt_http_routes_declare_authentication() -> None:
    public_operations = {
        ("/api/v1/auth/login", "POST"),
        ("/api/v1/healthz", "GET"),
    }
    seen_public: set[tuple[str, str]] = set()
    unprotected: list[str] = []

    for route in api_router.routes:
        if not isinstance(route, APIRoute):
            continue
        dependency_calls = _dependency_calls(route)
        for method in sorted(route.methods):
            operation = (route.path, method)
            if operation in public_operations:
                seen_public.add(operation)
                continue
            if require_user not in dependency_calls and require_admin not in dependency_calls:
                unprotected.append(f"{method} {route.path}")

    assert seen_public == public_operations
    assert unprotected == []


def test_authenticated_user_can_read_task_stats(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api-auth.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        role="user",
        is_active=True,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tasks/stats")

    assert response.status_code == 200
    assert response.json()["data"]["total"] == 0


def test_production_can_disable_api_documentation(monkeypatch) -> None:
    monkeypatch.setattr(settings, "docs_enabled", False)
    app = create_app()

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
    route_paths = {route.path for route in app.routes}
    assert "/docs" not in route_paths
    assert "/redoc" not in route_paths
    assert "/openapi.json" not in route_paths


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
