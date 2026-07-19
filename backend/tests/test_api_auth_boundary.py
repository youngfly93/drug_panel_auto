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
from app.models.audit import AuditLog
from app.models.task import Task
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


def _role_scoped_client(
    tmp_path: Path,
    *,
    user_id: int,
    role: str,
) -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        f"sqlite:///{tmp_path / f'role-{user_id}-{role}.sqlite'}",
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
        id=user_id,
        username=f"user-{user_id}",
        display_name=f"User {user_id}",
        role=role,
        is_active=True,
    )
    return TestClient(app), session_factory


def _seed_role_scope_tasks(session_factory: sessionmaker) -> None:
    db = session_factory()
    try:
        db.add_all(
            [
                Task(
                    id="owned-task",
                    user_id=1,
                    task_type="single",
                    status="completed",
                ),
                Task(
                    id="other-task",
                    user_id=2,
                    task_type="single",
                    status="completed",
                ),
                Task(
                    id="legacy-task",
                    user_id=None,
                    task_type="single",
                    status="completed",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_operator_only_sees_and_reads_owned_tasks(tmp_path: Path) -> None:
    client, session_factory = _role_scoped_client(
        tmp_path,
        user_id=1,
        role="operator",
    )
    _seed_role_scope_tasks(session_factory)

    with client:
        listed = client.get("/api/v1/tasks")
        own = client.get("/api/v1/tasks/owned-task")
        other = client.get("/api/v1/tasks/other-task")
        legacy = client.get("/api/v1/reports/legacy-task")

    assert {row["id"] for row in listed.json()["data"]["items"]} == {"owned-task"}
    assert own.status_code == 200
    assert other.status_code == 404
    assert legacy.status_code == 404


def test_reviewer_can_read_cross_operator_and_legacy_tasks(tmp_path: Path) -> None:
    client, session_factory = _role_scoped_client(
        tmp_path,
        user_id=9,
        role="reviewer",
    )
    _seed_role_scope_tasks(session_factory)

    with client:
        listed = client.get("/api/v1/tasks")
        other = client.get("/api/v1/tasks/other-task")
        legacy = client.get("/api/v1/reports/legacy-task")

    assert {row["id"] for row in listed.json()["data"]["items"]} == {
        "owned-task",
        "other-task",
        "legacy-task",
    }
    assert other.status_code == 200
    assert legacy.status_code == 200


def test_operator_cannot_review_or_mutate_reference_library(tmp_path: Path) -> None:
    client, session_factory = _role_scoped_client(
        tmp_path,
        user_id=1,
        role="operator",
    )
    _seed_role_scope_tasks(session_factory)
    report_path = tmp_path / "owned.docx"
    report_path.write_bytes(b"synthetic-report")
    report_path.with_suffix(".qa.json").write_text('{"status":"FAIL"}')
    db = session_factory()
    try:
        db.query(Task).filter(Task.id == "owned-task").update(
            {Task.output_path: str(report_path)}
        )
        db.commit()
    finally:
        db.close()

    with client:
        review = client.post(
            "/api/v1/reports/owned-task/review-state",
            json={"status": "reviewed", "operator": "spoofed-admin"},
        )
        reference = client.post(
            "/api/v1/reference-reports",
            data={"panel_id": "crc_358_msi", "case_id": "SYNTHETIC"},
            files={"file": ("reference.docx", b"synthetic", "application/octet-stream")},
        )
        reference_list = client.get("/api/v1/reference-reports")
        blocked_download = client.get("/api/v1/reports/owned-task/download")
        override_download = client.get(
            "/api/v1/reports/owned-task/download",
            params={"override_gate": True},
        )

    assert review.status_code == 403
    assert reference.status_code == 403
    assert reference_list.status_code == 403
    assert blocked_download.status_code == 409
    assert override_download.status_code == 403


def test_knowledge_manager_reference_write_uses_authenticated_audit_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
    client, session_factory = _role_scoped_client(
        tmp_path,
        user_id=4,
        role="knowledge_manager",
    )

    with client:
        response = client.post(
            "/api/v1/reference-reports",
            data={"panel_id": "crc_358_msi", "case_id": "SYNTHETIC"},
            files={"file": ("reference.docx", b"synthetic", "application/octet-stream")},
        )

    assert response.status_code == 200
    db = session_factory()
    try:
        event = db.query(AuditLog).filter(AuditLog.action == "reference.created").one()
        assert event.user_id == 4
        assert '"operator": "User 4"' in event.details
    finally:
        db.close()


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


def _websocket_client(
    monkeypatch,
    *,
    valid_token: bool,
    task_owner_id: int | None = 1,
    authenticated_user_id: int = 1,
    authenticated_role: str = "operator",
) -> TestClient:
    app = FastAPI()
    app.include_router(progress_ws.router)

    class FakeQuery:
        def filter(self, *_args):
            return self

        def first(self):
            if task_owner_id is None:
                return None
            return SimpleNamespace(user_id=task_owner_id)

    app.dependency_overrides[get_db] = lambda: SimpleNamespace(
        query=lambda _model: FakeQuery()
    )

    def authenticate(token, _db):
        if not valid_token or token != "synthetic-token":
            raise HTTPException(status_code=401, detail="Invalid token")
        return SimpleNamespace(
            id=authenticated_user_id,
            role=authenticated_role,
            is_active=True,
        )

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


def test_websocket_rejects_another_operators_task(monkeypatch) -> None:
    with _websocket_client(
        monkeypatch,
        valid_token=True,
        task_owner_id=1,
        authenticated_user_id=2,
    ) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/tasks/synthetic/progress") as websocket:
                websocket.send_json({"type": "authenticate", "token": "synthetic-token"})
                websocket.receive_json()
    assert exc_info.value.code == 4403


def test_websocket_reviewer_can_observe_any_task(monkeypatch) -> None:
    with _websocket_client(
        monkeypatch,
        valid_token=True,
        task_owner_id=1,
        authenticated_user_id=2,
        authenticated_role="reviewer",
    ) as client:
        with client.websocket_connect("/ws/tasks/synthetic/progress") as websocket:
            websocket.send_json({"type": "authenticate", "token": "synthetic-token"})
            assert websocket.receive_json()["type"] == "authenticated"
