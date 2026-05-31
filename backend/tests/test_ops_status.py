import json
import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api import ops as ops_api
from app.config import settings
from app.database import Base, get_db
from app.models.task import Task


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
    runtime_dir = tmp_path / "runtime"
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("RG_WEB_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.setenv("RG_WEB_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(
        ops_api,
        "_libreoffice_listener_status",
        lambda: {"checked": True, "running": True},
    )

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(ops_api.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_db
    return TestClient(app), SessionLocal, runtime_dir, backup_dir


def test_ops_status_returns_sanitized_runtime_snapshot(tmp_path, monkeypatch):
    client, SessionLocal, runtime_dir, backup_dir = _client(tmp_path, monkeypatch)
    storage_root = settings.storage_root
    for name in ["uploads", "reports", "previews", "signatures", "reference_reports"]:
        (storage_root / name).mkdir(parents=True, exist_ok=True)

    release_dir = tmp_path / "releases" / "abcdef12"
    release_dir.mkdir(parents=True)
    (release_dir / "REVISION").write_text("abcdef1234567890", encoding="utf-8")
    (runtime_dir / "logs").mkdir(parents=True)
    (runtime_dir / "current_release").write_text(str(release_dir), encoding="utf-8")
    (runtime_dir / "logs" / "watchdog.log").write_text(
        "\n".join(
            [
                "2026-05-31 15:00:00 watchdog begin",
                "2026-05-31 15:00:01 web ok local_http=200 pid=123 release=/secret/path",
                "2026-05-31 15:00:02 tunnel ok public_http=200",
                "2026-05-31 15:00:03 libreoffice listener ok",
                "2026-05-31 15:00:04 watchdog end",
            ]
        ),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "maintenance.log").write_text(
        "\n".join(
            [
                "2026-05-31 14:00:00 backup complete archive=/private/full/path/a.tar.gz",
                "2026-05-31 14:00:01 verify complete archive=/private/full/path/a.tar.gz",
                "2026-05-31 14:00:02 cleanup complete",
            ]
        ),
        encoding="utf-8",
    )
    download_event = {
        "timestamp": "2026-05-31T15:01:00",
        "event_type": "report_download_completed",
        "task_id": "task-sensitive",
        "task_type": "single",
        "task_status": "completed",
        "project_type": "crc_358_msi",
        "download_kind": "docx",
        "file_size_bytes": 1048576,
        "file_size_mb": 1.0,
        "duration_ms": 2500.0,
        "throughput_mbps": 3.36,
        "client_host": "203.0.113.10",
        "user_agent": "secret-browser",
        "range_header": None,
        "cf_ray": "ray-secret",
    }
    (runtime_dir / "logs" / "uvicorn.log").write_text(
        json.dumps(download_event, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    backup_dir.mkdir(parents=True)
    archive = backup_dir / "reportgen-web-backup-20260531_140000.tar.gz"
    archive.write_bytes(b"backup")
    (backup_dir / "reportgen-web-backup-20260531_140000.tar.gz.sha256").write_text(
        "0123456789abcdef  reportgen-web-backup-20260531_140000.tar.gz\n",
        encoding="utf-8",
    )
    (backup_dir / "reportgen-web-backup-20260531_140000.tar.gz.manifest.json").write_text(
        json.dumps(
            {
                "created_at": "20260531_140000",
                "current_release": str(release_dir),
                "storage_root": str(storage_root),
                "revision": "abcdef1234567890",
                "included_storage_roots": ["db", "uploads", "reports"],
                "storage_stats": {"reports": {"exists": True, "files": 2, "bytes": 3}},
                "db_backup": {"exists": True, "files": 1, "bytes": 4},
            }
        ),
        encoding="utf-8",
    )

    db = SessionLocal()
    db.add(
        Task(
            id="task-sensitive",
            task_type="single",
            status="completed",
            project_type="crc_358_msi",
            output_path=str(tmp_path / "reports" / "SensitivePatient.docx"),
            errors=json.dumps(["Sensitive Patient error from case.xlsx"], ensure_ascii=False),
            warnings=json.dumps(["Sensitive Patient warning"], ensure_ascii=False),
            total_files=1,
            completed_files=1,
            failed_files=0,
            created_at=datetime(2026, 5, 31, 15, 0, 0),
            completed_at=datetime(2026, 5, 31, 15, 0, 30),
            duration_seconds=30.0,
        )
    )
    db.commit()
    db.close()

    with client:
        response = client.get("/api/v1/admin/ops/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["deployment"]["release"] == "abcdef12"
    assert data["deployment"]["revision_short"] == "abcdef12"
    assert data["tasks"]["counts"]["total"] == 1
    assert data["tasks"]["recent"][0]["id"] == "task-sensitive"
    assert data["runtime"]["generation_queue"]["max_workers"] >= 1
    assert data["runtime"]["generation_queue"]["queued"] >= 0
    assert data["runtime"]["generation_queue"]["active"] >= 0
    assert data["runtime"]["task_recovery"]["ran"] in {True, False}
    assert data["downloads"]["summary"]["completed"] == 1
    assert data["downloads"]["recent_terminal_events"][0]["task_id"] == "task-sensitive"
    assert data["downloads"]["recent_terminal_events"][0]["cf_ray_present"] is True
    assert data["backups"]["latest"]["filename"] == archive.name
    assert data["runtime"]["watchdog"]["web"]["status"] == "ok"

    response_text = response.text
    assert "SensitivePatient" not in response_text
    assert "Sensitive Patient" not in response_text
    assert "case.xlsx" not in response_text
    assert "secret-browser" not in response_text
    assert "203.0.113.10" not in response_text
    assert str(tmp_path) not in response_text
