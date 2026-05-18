import io
import json
import sys
from pathlib import Path

from docx import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.database import Base
from app.models.task import Task
from app.services import reference_report_service as svc


def _docx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    doc = Document()
    doc.add_paragraph(text)
    doc.save(buffer)
    return buffer.getvalue()


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_reference_upload_activates_only_one_per_panel_case(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    db = _session()

    first = svc.create_reference_report(
        db,
        panel_id="crc_358_msi",
        case_id="LZ258792",
        name="old",
        original_filename="old.docx",
        fileobj=io.BytesIO(_docx_bytes("old")),
        active=True,
    )
    second = svc.create_reference_report(
        db,
        panel_id="CRC_358_MSI",
        case_id="lz258792",
        name="new",
        original_filename="new.docx",
        fileobj=io.BytesIO(_docx_bytes("new")),
        active=True,
    )

    db.refresh(first)
    db.refresh(second)
    assert first.active is False
    assert second.active is True
    assert Path(second.stored_path).exists()


def test_auto_reference_diff_matches_task_sample_id(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    db = _session()
    candidate = tmp_path / "candidate.docx"
    candidate.write_bytes(_docx_bytes("same report"))

    reference = svc.create_reference_report(
        db,
        panel_id="crc_358_msi",
        case_id="LZ258792",
        name="golden",
        original_filename="golden.docx",
        fileobj=io.BytesIO(_docx_bytes("same report")),
        active=True,
    )
    task = Task(
        id="task-1",
        task_type="single",
        status="completed",
        project_type="crc_358_msi",
        output_path=str(candidate),
        clinical_info_snapshot=json.dumps({"sample_id": "lz258792"}),
    )
    db.add(task)
    db.commit()

    result = svc.run_auto_reference_diff(db, task)

    assert result is not None
    assert result["status"] == "PASS"
    assert result["gate"]["passed"] is True
    assert result["reference_report"]["id"] == reference.id
    summary = svc.report_diff_summary(str(candidate))
    assert summary["diff_status"] == "PASS"
    assert summary["diff_reference_id"] == reference.id
