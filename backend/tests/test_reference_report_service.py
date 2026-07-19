# ruff: noqa: E402

import io
import json
import sys
from pathlib import Path

import pytest
from docx import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.database import Base
from app.models.reference import ReferenceReport
from app.models.task import Task
from app.services import reference_report_service as svc
from app.services.file_manager import UploadLimitExceeded


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


def _write_golden_contract(
    root: Path,
    *,
    panel_id: str,
    case_alias: str,
    reference_docx: Path,
) -> Path:
    path = root / "panels" / panel_id / "golden_cases" / f"{case_alias}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "case_alias": case_alias,
                "panel_id": panel_id,
                "privacy": {"contains_phi": False},
                "source": {
                    "reference_docx_sha256": svc.sha256_file(reference_docx),
                },
            }
        ),
        encoding="utf-8",
    )
    return path


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


def test_reference_upload_rejects_oversize_without_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)
    db = _session()

    with pytest.raises(UploadLimitExceeded) as exc_info:
        svc.create_reference_report(
            db,
            panel_id="crc_358_msi",
            case_id="LIMIT_CASE",
            name="oversize",
            original_filename="oversize.docx",
            fileobj=io.BytesIO(_docx_bytes("must not be persisted")),
            active=True,
        )

    assert exc_info.value.status_code == 413
    assert db.query(ReferenceReport).count() == 0
    assert not any(path.is_file() for path in settings.reference_report_dir.rglob("*"))


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


def test_required_auto_reference_diff_fails_closed_when_reference_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    db = _session()
    candidate = tmp_path / "candidate.docx"
    candidate.write_bytes(_docx_bytes("generated report"))
    task = Task(
        id="task-required-missing",
        task_type="single",
        status="completed",
        project_type="crc_358_msi",
        output_path=str(candidate),
        clinical_info_snapshot=json.dumps({"sample_id": "LZ-NOT-REGISTERED"}),
    )
    db.add(task)
    db.commit()

    result = svc.run_auto_reference_diff(db, task, require_reference=True)

    assert result is not None
    assert result["status"] == "FAIL"
    assert result["gate"] == {
        "fail_on": "fail",
        "passed": False,
        "require_reference": True,
    }
    assert result["issues"][0]["code"] == "REFERENCE_REQUIRED_NOT_FOUND"
    persisted = svc.load_report_diff(str(candidate))
    assert persisted is not None
    assert persisted["gate"]["passed"] is False


def test_required_reference_gate_rejects_unattested_active_reference(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    db = _session()
    candidate = tmp_path / "candidate-unattested.docx"
    candidate.write_bytes(_docx_bytes("same report"))
    svc.create_reference_report(
        db,
        panel_id="crc_358_msi",
        case_id="LZ258685",
        name="ordinary baseline",
        original_filename="ordinary.docx",
        fileobj=io.BytesIO(_docx_bytes("same report")),
        active=True,
    )
    task = Task(
        id="task-unattested",
        task_type="single",
        status="completed",
        project_type="crc_358_msi",
        output_path=str(candidate),
        clinical_info_snapshot=json.dumps({"sample_id": "LZ258685"}),
    )
    db.add(task)
    db.commit()

    ordinary = svc.run_auto_reference_diff(db, task)
    required = svc.run_auto_reference_diff(db, task, require_reference=True)

    assert ordinary is not None
    assert ordinary["status"] == "PASS"
    assert required is not None
    assert required["status"] == "FAIL"
    assert required["issues"][0]["code"] == "REFERENCE_REQUIRED_NOT_FOUND"


def test_formal_golden_registration_rejects_case_alias_and_wrong_sha(
    tmp_path, monkeypatch
):
    upstream_root = tmp_path / "source"
    monkeypatch.setattr(settings, "upstream_root", upstream_root)
    reference_docx = tmp_path / "golden.docx"
    reference_docx.write_bytes(_docx_bytes("reviewed"))
    contract_path = _write_golden_contract(
        upstream_root,
        panel_id="crc_358_msi",
        case_alias="deidentified_case_a",
        reference_docx=reference_docx,
    )

    with pytest.raises(ValueError, match="不能使用脱敏 case_alias"):
        svc.validate_formal_golden_registration(
            panel_id="crc_358_msi",
            case_id="deidentified_case_a",
            reference_docx=reference_docx,
            contract_path=contract_path,
        )

    reference_docx.write_bytes(_docx_bytes("tampered"))
    with pytest.raises(ValueError, match="SHA256"):
        svc.validate_formal_golden_registration(
            panel_id="crc_358_msi",
            case_id="LZ258685",
            reference_docx=reference_docx,
            contract_path=contract_path,
        )


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


def test_required_batch_reference_diff_blocks_unmatched_case_and_uses_validation_snapshot(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    upstream_root = tmp_path / "source"
    monkeypatch.setattr(settings, "upstream_root", upstream_root)
    db = _session()
    output_root = tmp_path / "batch-required"
    output_root.mkdir()
    matched_docx = output_root / "matched.docx"
    missing_docx = output_root / "missing.docx"
    matched_docx.write_bytes(_docx_bytes("same report"))
    missing_docx.write_bytes(_docx_bytes("other report"))
    golden_source = tmp_path / "reviewed-golden.docx"
    golden_source.write_bytes(_docx_bytes("same report"))
    contract_path = _write_golden_contract(
        upstream_root,
        panel_id="crc_358_msi",
        case_alias="deidentified_case_a",
        reference_docx=golden_source,
    )
    reference = svc.create_reference_report(
        db,
        panel_id="crc_358_msi",
        case_id="LZ258685",
        name="reviewed golden",
        original_filename="golden.docx",
        fileobj=io.BytesIO(golden_source.read_bytes()),
        active=True,
    )
    svc.create_formal_golden_attestation(reference, contract_path=contract_path)
    task = Task(
        id="batch-required",
        task_type="batch",
        status="completed",
        project_type=None,
        output_path=str(output_root),
    )
    db.add(task)
    db.commit()
    report = {
        "results": [
            {
                "index": 1,
                "output_docx": "matched.docx",
                "excel_filename": "opaque.xlsx",
                "validation": {
                    "project_type": "crc_358_msi",
                    "clinical_info": {"sample_id": "LZ258685"},
                },
            },
            {
                "index": 2,
                "output_docx": "missing.docx",
                "excel_filename": "LZ000000.xlsx",
                "validation": {
                    "project_type": "crc_358_msi",
                    "clinical_info": {"sample_id": "LZ000000"},
                },
            },
        ]
    }

    result = svc.run_batch_reference_diff(
        db,
        task,
        report,
        require_reference=True,
    )

    assert result["status"] == "FAIL"
    assert result["gate"]["passed"] is False
    assert result["gate"]["require_reference"] is True
    assert result["summary"] == {
        "total_reports": 2,
        "matched_references": 1,
        "pass": 1,
        "warn": 0,
        "fail": 1,
        "skip": 0,
        "blocked": 1,
    }
    assert result["items"][0]["reference_id"] == reference.id
    assert result["items"][1]["message"].startswith("金标准验收模式")
