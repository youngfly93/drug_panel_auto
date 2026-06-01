import json
import sys
from datetime import datetime, timedelta, timezone
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
from app.models.task import Task, TaskResult


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
    assert data["schema_version"] == "1.1"
    assert data["deployment"]["release"] == "abcdef12"
    assert data["deployment"]["revision_short"] == "abcdef12"
    assert isinstance(data["alerts"], list)
    assert data["retention"]["upload_keep_days"] == 30
    assert data["retention"]["report_keep_days"] == 180
    assert data["retention"]["audit_log_keep_days"] == 365
    assert data["tasks"]["counts"]["total"] == 1
    assert data["tasks"]["recent"][0]["id"] == "task-sensitive"
    assert data["runtime"]["generation_queue"]["max_workers"] >= 1
    assert data["runtime"]["generation_queue"]["queued"] >= 0
    assert data["runtime"]["generation_queue"]["active"] >= 0
    assert isinstance(data["runtime"]["generation_limits"]["process_isolation"], bool)
    assert data["runtime"]["generation_limits"]["timeout_seconds"] >= 1
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


def test_ops_status_returns_threshold_alerts(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ops_api,
        "_disk_usage",
        lambda _path: {
            "available": True,
            "total_bytes": 100,
            "used_bytes": 92,
            "free_bytes": 8,
            "used_percent": 92.0,
        },
    )
    monkeypatch.setattr(
        ops_api,
        "queue_stats",
        lambda: {
            "max_workers": 2,
            "queued": 3,
            "active": 2,
            "submitted_total": 5,
            "finished_total": 0,
        },
    )
    client, _SessionLocal, runtime_dir, _backup_dir = _client(tmp_path, monkeypatch)
    (runtime_dir / "logs").mkdir(parents=True)
    (runtime_dir / "logs" / "uvicorn.log").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-05-31T15:01:00",
                        "event_type": "report_download_failed",
                        "task_id": "task-a",
                        "duration_ms": 1200,
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-05-31T15:02:00",
                        "event_type": "report_download_slow",
                        "task_id": "task-b",
                        "duration_ms": 45_000,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    with client:
        response = client.get("/api/v1/admin/ops/status")

    assert response.status_code == 200
    alert_ids = {alert["id"] for alert in response.json()["data"]["alerts"]}
    assert "disk.critical" in alert_ids
    assert "queue.backlog.high" in alert_ids
    assert "downloads.failed" in alert_ids
    assert "downloads.slow" in alert_ids
    assert "downloads.duration.high" in alert_ids
    assert "backup.missing" in alert_ids
    assert "maintenance.cleanup.missing" in alert_ids


def test_load_test_summary_returns_sanitized_release_gate_payload(tmp_path, monkeypatch):
    client, SessionLocal, runtime_dir, _backup_dir = _client(tmp_path, monkeypatch)
    (runtime_dir / "logs").mkdir(parents=True)
    now = datetime.now(timezone.utc)
    (runtime_dir / "logs" / "uvicorn.log").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": now.isoformat(),
                        "event_type": "report_download_completed",
                        "task_id": "batch-sensitive",
                        "duration_ms": 800,
                        "file_size_bytes": 1024,
                        "file_size_mb": 0.001,
                    }
                ),
                json.dumps(
                    {
                        "timestamp": (now - timedelta(days=3)).isoformat(),
                        "event_type": "report_download_failed",
                        "task_id": "old-sensitive",
                        "duration_ms": 5000,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    completed_docx = report_dir / "SensitivePatient.docx"
    completed_docx.write_bytes(b"docx")
    completed_docx.with_suffix(".qa.json").write_text(
        json.dumps({"status": "WARN"}),
        encoding="utf-8",
    )

    db = SessionLocal()
    db.add(
        Task(
            id="batch-sensitive",
            task_type="batch",
            status="partial_failed",
            project_type="crc_358_msi",
            total_files=2,
            completed_files=1,
            failed_files=1,
            errors=json.dumps(["Alice secret.xlsx Excel sheet missing"], ensure_ascii=False),
            warnings=json.dumps(["Sensitive Patient QA warning"], ensure_ascii=False),
            created_at=(now - timedelta(hours=1)).replace(tzinfo=None),
            completed_at=(now - timedelta(minutes=30)).replace(tzinfo=None),
            duration_seconds=120.0,
        )
    )
    db.add_all(
        [
            TaskResult(
                task_id="batch-sensitive",
                file_index=1,
                excel_filename="Alice-secret.xlsx",
                status="completed",
                output_path=str(completed_docx),
                duration_seconds=50.0,
                warnings=json.dumps(["Sensitive Patient QA warning"], ensure_ascii=False),
            ),
            TaskResult(
                task_id="batch-sensitive",
                file_index=2,
                excel_filename="Bob-secret.xlsx",
                status="failed",
                duration_seconds=20.0,
                errors=json.dumps(["Bob secret.xlsx template rendering failed"], ensure_ascii=False),
            ),
        ]
    )
    db.add(
        Task(
            id="old-task",
            task_type="single",
            status="failed",
            project_type="crc_358_msi",
            total_files=1,
            completed_files=0,
            failed_files=1,
            errors=json.dumps(["old sensitive failure"], ensure_ascii=False),
            created_at=(now - timedelta(days=3)).replace(tzinfo=None),
            duration_seconds=10.0,
        )
    )
    db.commit()
    db.close()

    with client:
        response = client.get("/api/v1/admin/ops/load-test-summary?window_hours=24")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["schema_version"] == "1.0"
    assert data["totals"]["tasks_total"] == 1
    assert data["totals"]["batch_tasks"] == 1
    assert data["totals"]["units_total"] == 2
    assert data["totals"]["units_completed"] == 1
    assert data["totals"]["units_failed"] == 1
    assert data["qa"]["warn"] == 1
    assert data["downloads"]["summary"]["completed"] == 1
    assert data["downloads"]["summary"]["failed"] == 0
    assert data["gate"]["status"] == "block"
    assert any(item["reason"] == "Excel 数据问题" for item in data["failure_reasons"])
    assert any(item["reason"] == "模板渲染错误" for item in data["failure_reasons"])

    response_text = response.text
    assert "SensitivePatient" not in response_text
    assert "Sensitive Patient" not in response_text
    assert "Alice" not in response_text
    assert "Bob" not in response_text
    assert "secret.xlsx" not in response_text
    assert str(tmp_path) not in response_text
