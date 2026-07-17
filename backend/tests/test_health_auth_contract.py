from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.config import settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.dependencies import require_admin, require_user  # noqa: E402
from app.main import create_app  # noqa: E402


def _reject_auth() -> None:
    raise HTTPException(status_code=401, detail="Not authenticated")


def test_healthz_is_anonymous_storage_free_and_business_routes_stay_protected() -> None:
    app = create_app()

    def fail_if_database_is_touched():
        raise AssertionError("anonymous health probe must not resolve a database")

    app.dependency_overrides[get_db] = fail_if_database_is_touched
    app.dependency_overrides[require_user] = _reject_auth
    app.dependency_overrides[require_admin] = _reject_auth

    client = TestClient(app)
    try:
        response = client.get("/api/v1/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert client.get("/api/v1/tasks/stats").status_code == 401
        assert client.get("/api/v1/admin/ops/status").status_code == 401
        assert "/api/v1/healthz" not in app.openapi()["paths"]
    finally:
        client.close()


def test_authenticated_user_can_read_task_stats(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'health-auth.sqlite'}",
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

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(
        id=1,
        role="user",
        is_active=True,
    )

    client = TestClient(app)
    try:
        response = client.get("/api/v1/tasks/stats")
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 0
    finally:
        client.close()


def test_production_can_disable_api_documentation(monkeypatch) -> None:
    monkeypatch.setattr(settings, "docs_enabled", False)
    app = create_app()
    route_paths = {route.path for route in app.routes}

    assert "/docs" not in route_paths
    assert "/redoc" not in route_paths
    assert "/openapi.json" not in route_paths


def test_health_router_matches_production_runtime_contract() -> None:
    """Keep the source-controlled probe identical to iyun129's safe contract."""
    app = create_app()
    health_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/healthz"
    ]

    assert len(health_routes) == 1
    assert health_routes[0].methods == {"GET"}
    assert health_routes[0].include_in_schema is False
