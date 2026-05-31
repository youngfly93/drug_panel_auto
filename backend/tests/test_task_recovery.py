import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.models.task import Task, TaskResult  # noqa: E402
from app.services import task_recovery  # noqa: E402


def _session_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _capture_queue(monkeypatch):
    queued = []

    def fake_submit(func, *args, **kwargs):
        queued.append({"func": func, "args": args, "kwargs": kwargs})

    monkeypatch.setattr(task_recovery, "submit_generation_job", fake_submit)
    return queued


def test_recover_interrupted_single_task_requeues_from_private_request(
    tmp_path, monkeypatch
):
    SessionLocal = _session_factory(tmp_path, monkeypatch)
    queued = _capture_queue(monkeypatch)
    task_id = "single-recover"
    source = settings.upload_dir / "2026-05-31" / "upload-1" / "case.xlsx"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"placeholder")
    output_dir = settings.report_dir / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = task_recovery.write_single_generation_request(
        task_id=task_id,
        payload={
            "task_id": task_id,
            "stored_path": str(source),
            "output_dir": str(output_dir),
            "clinical_payload": {"sample_id": "CASE001"},
            "project_type": "crc_358_msi",
            "project_name": "结直肠癌358基因+MSI",
            "template_name": None,
            "strict_mode": False,
            "template_contract_mode": "warn",
            "qa_visual_render": None,
            "qa_visual_render_required": None,
            "qa_visual_render_dpi": None,
            "qa_visual_render_timeout_seconds": None,
        },
    )

    db = SessionLocal()
    db.add(
        Task(
            id=task_id,
            task_type="single",
            status="running",
            project_type="crc_358_msi",
            context_json_path=str(request_path),
            started_at=datetime.utcnow(),
        )
    )
    db.commit()
    db.close()

    summary = task_recovery.recover_interrupted_tasks(
        session_factory=SessionLocal,
        bridge=object(),
    )

    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    db.close()
    assert summary["scanned"] == 1
    assert summary["requeued"] == 1
    assert task.status == "pending"
    assert task.started_at is None
    assert "重新进入后台队列" in task.warnings
    assert len(queued) == 1
    assert queued[0]["func"].__name__ == "_complete_file_generation_task"
    assert queued[0]["kwargs"]["stored_path"] == str(source)
    assert queued[0]["kwargs"]["output_dir"] == str(output_dir)


def test_recover_interrupted_single_task_without_metadata_fails(
    tmp_path, monkeypatch
):
    SessionLocal = _session_factory(tmp_path, monkeypatch)
    queued = _capture_queue(monkeypatch)
    db = SessionLocal()
    db.add(
        Task(
            id="single-missing",
            task_type="single",
            status="pending",
            project_type="crc_358_msi",
        )
    )
    db.commit()
    db.close()

    summary = task_recovery.recover_interrupted_tasks(
        session_factory=SessionLocal,
        bridge=object(),
    )

    db = SessionLocal()
    task = db.query(Task).filter(Task.id == "single-missing").first()
    db.close()
    assert summary["failed"] == 1
    assert task.status == "failed"
    assert "缺少恢复清单" in task.errors
    assert queued == []


def test_recover_interrupted_batch_requeues_unfinished_rows(tmp_path, monkeypatch):
    SessionLocal = _session_factory(tmp_path, monkeypatch)
    queued = _capture_queue(monkeypatch)
    task_id = "batch-recover"
    output_dir = settings.report_dir / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = settings.upload_dir / "2026-05-31" / "batch"
    source_dir.mkdir(parents=True, exist_ok=True)
    sources = []
    for index in (1, 2, 3):
        path = source_dir / f"case{index}.xlsx"
        path.write_bytes(b"placeholder")
        sources.append(path)
    (output_dir / "batch_inputs.private.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "task_id": task_id,
                "project_type": "crc_358_msi",
                "project_name": "结直肠癌358基因+MSI",
                "template_name": None,
                "template_contract_mode": "warn",
                "shared_clinical_info": {},
                "items": [
                    {
                        "index": index,
                        "filename": f"case{index}.xlsx",
                        "stored_path": str(path),
                    }
                    for index, path in enumerate(sources, start=1)
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    db = SessionLocal()
    db.add(
        Task(
            id=task_id,
            task_type="batch",
            status="running",
            project_type="crc_358_msi",
            output_path=str(output_dir),
            total_files=3,
            completed_files=1,
            failed_files=0,
            started_at=datetime.utcnow(),
        )
    )
    db.add_all(
        [
            TaskResult(
                task_id=task_id,
                file_index=1,
                excel_filename="case1.xlsx",
                status="completed",
                output_path=str(output_dir / "case1.docx"),
            ),
            TaskResult(
                task_id=task_id,
                file_index=2,
                excel_filename="case2.xlsx",
                status="running",
            ),
            TaskResult(
                task_id=task_id,
                file_index=3,
                excel_filename="case3.xlsx",
                status="pending",
            ),
        ]
    )
    db.commit()
    db.close()

    summary = task_recovery.recover_interrupted_tasks(
        session_factory=SessionLocal,
        bridge=object(),
    )

    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    rows = (
        db.query(TaskResult)
        .filter(TaskResult.task_id == task_id)
        .order_by(TaskResult.file_index.asc())
        .all()
    )
    db.close()
    assert summary["requeued"] == 1
    assert task.status == "pending"
    assert task.completed_files == 1
    assert task.failed_files == 0
    assert [row.status for row in rows] == ["completed", "pending", "pending"]
    assert len(queued) == 1
    assert queued[0]["func"].__name__ == "_complete_batch_files_task"
    assert [item["index"] for item in queued[0]["kwargs"]["items"]] == [2, 3]
