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


def test_batch_reference_diff_writes_summary_and_per_sample_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    db = _session()
    output_root = tmp_path / "batch"
    output_root.mkdir()
    report_1 = output_root / "report_001.docx"
    report_2 = output_root / "report_002.docx"
    report_1.write_bytes(_docx_bytes("same report"))
    report_2.write_bytes(_docx_bytes("changed report"))

    reference = svc.create_reference_report(
        db,
        panel_id="crc_358_msi",
        case_id="CASE001",
        name="case-001",
        original_filename="case001.docx",
        fileobj=io.BytesIO(_docx_bytes("same report")),
        active=True,
    )
    task = Task(
        id="batch-1",
        task_type="batch",
        status="completed",
        project_type="crc_358_msi",
        output_path=str(output_root),
    )
    db.add(task)
    db.commit()
    batch_report = {
        "results": [
            {
                "index": 1,
                "ok": True,
                "output_docx": "report_001.docx",
                "excel_filename": "case001.xlsx",
                "patient_snapshot": {"sample_id": "CASE001"},
            },
            {
                "index": 2,
                "ok": True,
                "output_docx": "report_002.docx",
                "excel_filename": "case002.xlsx",
                "patient_snapshot": {"sample_id": "CASE002"},
            },
        ]
    }

    result = svc.run_batch_reference_diff(db, task, batch_report)

    assert result["status"] == "WARN"
    assert result["gate"]["passed"] is True
    assert result["summary"]["matched_references"] == 1
    assert result["summary"]["pass"] == 1
    assert result["summary"]["skip"] == 1
    assert result["items"][0]["reference_id"] == reference.id
    assert result["items"][0]["diff_key"] == "report_001"
    assert result["items"][0]["download_urls"]["markdown"].endswith(
        "/report_001/download/report_diff.md"
    )
    assert Path(result["items"][0]["diff_json"]).exists()

    summary = svc.report_diff_summary(str(output_root))
    assert summary["diff_status"] == "WARN"
    assert summary["diff_gate_passed"] is True
    assert "基准命中 1/2" in summary["diff_reference_name"]
