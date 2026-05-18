"""Reference report storage and automatic report diff helpers."""

import hashlib
import json
import re
import shutil
import sys
import uuid
from pathlib import Path
from typing import BinaryIO, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.reference import ReferenceReport
from app.models.task import Task
from app.models.upload import Upload

_upstream = Path(str(settings.upstream_root))
if str(_upstream) not in sys.path:
    sys.path.insert(0, str(_upstream))

from reportgen.core.report_diff import (
    ReportDiffOptions,
    compare_reports,
    write_report_diff_outputs,
)

ALLOWED_DIFF_ARTIFACTS = {"report_diff.json", "report_diff.md"}
CASE_ID_KEYS = (
    "case_id",
    "sample_id",
    "sample_no",
    "sample_number",
    "barcode",
    "report_number",
    "patient_id",
    "样本编号",
    "送检编号",
    "条码号",
    "报告编号",
)


def normalize_lookup(value: str | None) -> str:
    return str(value or "").strip().lower()


def sanitize_path_segment(value: str) -> str:
    segment = re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip())
    return segment.strip("._") or "unknown"


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    stem = sanitize_path_segment(Path(name).stem)
    suffix = Path(name).suffix.lower() or ".docx"
    return f"{stem}{suffix}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def report_diff_dir(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    return Path(output_path).parent / "report_diff"


def report_diff_artifact_path(output_path: Optional[str], filename: str) -> Optional[Path]:
    if filename not in ALLOWED_DIFF_ARTIFACTS:
        return None
    diff_dir = report_diff_dir(output_path)
    if not diff_dir:
        return None
    candidate = (diff_dir / filename).resolve()
    try:
        candidate.relative_to(diff_dir.resolve())
    except ValueError:
        return None
    return candidate


def load_report_diff(output_path: Optional[str]) -> Optional[dict]:
    diff_path = report_diff_artifact_path(output_path, "report_diff.json")
    if not diff_path or not diff_path.exists():
        return None
    try:
        return json.loads(diff_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def report_diff_summary(output_path: Optional[str]) -> dict:
    payload = load_report_diff(output_path)
    diff_path = report_diff_artifact_path(output_path, "report_diff.json")
    md_path = report_diff_artifact_path(output_path, "report_diff.md")
    if not payload:
        return {
            "diff_report_file": str(diff_path) if diff_path and diff_path.exists() else None,
            "diff_markdown_file": str(md_path) if md_path and md_path.exists() else None,
            "diff_status": None,
            "diff_gate_passed": None,
            "diff_reference_id": None,
            "diff_reference_name": None,
        }
    reference = payload.get("reference_report") or {}
    gate = payload.get("gate") or {}
    return {
        "diff_report_file": str(diff_path) if diff_path and diff_path.exists() else None,
        "diff_markdown_file": str(md_path) if md_path and md_path.exists() else None,
        "diff_status": payload.get("status"),
        "diff_gate_passed": gate.get("passed"),
        "diff_reference_id": reference.get("id"),
        "diff_reference_name": reference.get("name"),
    }


def reference_to_dict(reference: ReferenceReport) -> dict:
    return {
        "id": reference.id,
        "panel_id": reference.panel_id,
        "case_id": reference.case_id,
        "name": reference.name,
        "original_filename": reference.original_filename,
        "active": reference.active,
    }


def list_reference_reports(
    db: Session,
    *,
    panel_id: str | None = None,
    case_id: str | None = None,
    active: bool | None = None,
) -> list[ReferenceReport]:
    query = db.query(ReferenceReport).order_by(ReferenceReport.created_at.desc())
    if panel_id:
        query = query.filter(func.lower(ReferenceReport.panel_id) == normalize_lookup(panel_id))
    if case_id:
        query = query.filter(func.lower(ReferenceReport.case_id) == normalize_lookup(case_id))
    if active is not None:
        query = query.filter(ReferenceReport.active == active)
    return query.all()


def get_reference_report(db: Session, reference_id: str) -> ReferenceReport | None:
    return db.query(ReferenceReport).filter(ReferenceReport.id == reference_id).first()


def create_reference_report(
    db: Session,
    *,
    panel_id: str,
    case_id: str,
    name: str | None,
    original_filename: str,
    fileobj: BinaryIO,
    active: bool = True,
    notes: str | None = None,
) -> ReferenceReport:
    if not original_filename.lower().endswith(".docx"):
        raise ValueError("仅支持上传 .docx 基准报告")
    panel_id = panel_id.strip()
    case_id = case_id.strip()
    if not panel_id or not case_id:
        raise ValueError("panel_id 和 case_id 不能为空")

    reference_id = str(uuid.uuid4())
    filename = f"{reference_id}_{sanitize_filename(original_filename)}"
    target_dir = (
        settings.reference_report_dir
        / sanitize_path_segment(panel_id)
        / sanitize_path_segment(case_id)
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_path = target_dir / filename
    with stored_path.open("wb") as fh:
        shutil.copyfileobj(fileobj, fh)

    if active:
        db.query(ReferenceReport).filter(
            func.lower(ReferenceReport.panel_id) == normalize_lookup(panel_id),
            func.lower(ReferenceReport.case_id) == normalize_lookup(case_id),
            ReferenceReport.active == True,  # noqa: E712
        ).update({"active": False})

    reference = ReferenceReport(
        id=reference_id,
        panel_id=panel_id,
        case_id=case_id,
        name=(name or Path(original_filename).stem).strip() or Path(original_filename).stem,
        original_filename=Path(original_filename).name,
        stored_path=str(stored_path),
        checksum_sha256=sha256_file(stored_path),
        active=active,
        notes=notes,
    )
    db.add(reference)
    db.commit()
    db.refresh(reference)
    return reference


def activate_reference_report(db: Session, reference: ReferenceReport) -> ReferenceReport:
    db.query(ReferenceReport).filter(
        func.lower(ReferenceReport.panel_id) == normalize_lookup(reference.panel_id),
        func.lower(ReferenceReport.case_id) == normalize_lookup(reference.case_id),
        ReferenceReport.id != reference.id,
    ).update({"active": False})
    reference.active = True
    db.commit()
    db.refresh(reference)
    return reference


def delete_reference_report(db: Session, reference: ReferenceReport) -> None:
    path = Path(reference.stored_path)
    db.delete(reference)
    db.commit()
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def derive_reference_case_id(task: Task, upload: Upload | None = None) -> str | None:
    payload = {}
    if task.clinical_info_snapshot:
        try:
            payload = json.loads(task.clinical_info_snapshot) or {}
        except Exception:
            payload = {}
    for key in CASE_ID_KEYS:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value).strip()

    filename = upload.original_filename if upload else None
    if filename:
        stem = Path(filename).stem
        token_match = re.search(r"(?i)([a-z]{1,8}\d{4,})", stem)
        return token_match.group(1) if token_match else stem
    return None


def find_active_reference_for_task(db: Session, task: Task) -> ReferenceReport | None:
    if not task.project_type:
        return None
    upload = db.query(Upload).filter(Upload.id == task.upload_id).first() if task.upload_id else None
    case_id = derive_reference_case_id(task, upload)
    if not case_id:
        return None
    return (
        db.query(ReferenceReport)
        .filter(
            func.lower(ReferenceReport.panel_id) == normalize_lookup(task.project_type),
            func.lower(ReferenceReport.case_id) == normalize_lookup(case_id),
            ReferenceReport.active == True,  # noqa: E712
        )
        .order_by(ReferenceReport.created_at.desc())
        .first()
    )


def compare_task_with_reference_path(
    task: Task,
    *,
    reference_docx: str,
    task_id: str | None = None,
    fail_on: str = "fail",
    max_samples: int = 30,
    reference_report: ReferenceReport | None = None,
    reference_metadata: dict | None = None,
) -> dict:
    if fail_on not in {"fail", "warn"}:
        raise ValueError("fail_on must be 'fail' or 'warn'")
    if not task.output_path:
        raise ValueError("报告文件不存在")

    diff_dir = report_diff_dir(task.output_path)
    if not diff_dir:
        raise ValueError("报告对比目录不可用")
    diff_dir.mkdir(parents=True, exist_ok=True)

    result = compare_reports(
        ReportDiffOptions(
            reference_docx=reference_docx,
            candidate_docx=str(task.output_path),
            output_dir=str(diff_dir),
            max_samples=max_samples,
        )
    )
    status = result.get("status")
    gate_passed = status == "PASS" or (status == "WARN" and fail_on == "fail")
    result["gate"] = {
        "fail_on": fail_on,
        "passed": bool(gate_passed),
    }
    if reference_report is not None:
        result["reference_report"] = reference_to_dict(reference_report)
    elif reference_metadata:
        result["reference_report"] = reference_metadata
    if task_id:
        result["download_urls"] = {
            "json": f"/api/v1/reports/{task_id}/diff/download/report_diff.json",
            "markdown": f"/api/v1/reports/{task_id}/diff/download/report_diff.md",
        }
    write_report_diff_outputs(result, diff_dir)
    return result


def run_auto_reference_diff(
    db: Session,
    task: Task,
    *,
    fail_on: str = "fail",
    max_samples: int = 50,
) -> dict | None:
    reference = find_active_reference_for_task(db, task)
    if not reference:
        return None
    return compare_task_with_reference_path(
        task,
        reference_docx=reference.stored_path,
        task_id=task.id,
        fail_on=fail_on,
        max_samples=max_samples,
        reference_report=reference,
    )
