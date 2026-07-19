"""Reference report storage and automatic report diff helpers."""

import hashlib
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.reference import ReferenceReport
from app.models.task import Task
from app.models.upload import Upload
from app.services.file_manager import write_upload_stream

_upstream = Path(str(settings.upstream_root))
if str(_upstream) not in sys.path:
    sys.path.insert(0, str(_upstream))

from reportgen.core.historical_golden_contract import (  # noqa: E402
    load_historical_golden_contract,
)
from reportgen.core.report_diff import (  # noqa: E402
    ReportDiffOptions,
    compare_reports,
    write_report_diff_outputs,
)

ALLOWED_DIFF_ARTIFACTS = {"report_diff.json", "report_diff.md"}
BATCH_DIFF_JSON = "batch_report_diff.json"
BATCH_DIFF_MD = "batch_report_diff.md"
REFERENCE_GATE_AVAILABLE = "available"
REFERENCE_GATE_REQUIRED = "required"
REFERENCE_GATE_MODES = {REFERENCE_GATE_AVAILABLE, REFERENCE_GATE_REQUIRED}
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


def normalize_reference_gate_mode(value: str | None) -> str:
    mode = str(value or REFERENCE_GATE_AVAILABLE).strip().lower()
    if mode not in REFERENCE_GATE_MODES:
        raise ValueError("reference_gate_mode must be 'available' or 'required'")
    return mode


def reference_is_required(value: str | None) -> bool:
    return normalize_reference_gate_mode(value) == REFERENCE_GATE_REQUIRED


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


def formal_golden_attestation_path(reference: ReferenceReport) -> Path:
    return Path(reference.stored_path).with_suffix(".golden.json")


def validate_formal_golden_registration(
    *,
    panel_id: str,
    case_id: str,
    reference_docx: str | Path,
    contract_path: str | Path,
) -> dict:
    """Validate an external real case against a committed de-identified contract."""
    source = Path(reference_docx).resolve()
    contract_file = Path(contract_path).resolve()
    registry_root = (settings.upstream_root / "panels").resolve()
    try:
        contract_file.relative_to(registry_root)
    except ValueError as exc:
        raise ValueError("金标准契约必须位于受版本控制的 panels/ 目录") from exc
    if "golden_cases" not in contract_file.parts:
        raise ValueError("金标准契约必须位于 panel 的 golden_cases/ 目录")
    if not source.is_file() or source.suffix.lower() != ".docx":
        raise ValueError("金标准报告必须是现存的 .docx 文件")

    contract = load_historical_golden_contract(contract_file)
    contract_panel = str(contract.get("panel_id") or "").strip()
    case_alias = str(contract.get("case_alias") or "").strip()
    if normalize_lookup(contract_panel) != normalize_lookup(panel_id):
        raise ValueError("panel_id 与金标准契约不一致")
    if normalize_lookup(case_id) == normalize_lookup(case_alias):
        raise ValueError("case_id 必须使用外部真实病例编号，不能使用脱敏 case_alias")
    expected_sha = str(
        (contract.get("source") or {}).get("reference_docx_sha256") or ""
    ).strip()
    actual_sha = sha256_file(source)
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ValueError("金标准契约缺少有效 reference_docx_sha256")
    if actual_sha != expected_sha:
        raise ValueError("金标准报告 SHA256 与脱敏契约不一致")
    return {
        "contract": contract,
        "contract_path": contract_file,
        "contract_sha256": sha256_file(contract_file),
        "reference_sha256": actual_sha,
    }


def create_formal_golden_attestation(
    reference: ReferenceReport,
    *,
    contract_path: str | Path,
) -> dict:
    validated = validate_formal_golden_registration(
        panel_id=reference.panel_id,
        case_id=reference.case_id,
        reference_docx=reference.stored_path,
        contract_path=contract_path,
    )
    contract = validated["contract"]
    contract_file = validated["contract_path"]
    relative_contract = contract_file.relative_to(settings.upstream_root.resolve())
    payload = {
        "schema_version": "1.0",
        "reference_id": reference.id,
        "panel_id": reference.panel_id,
        "case_id": reference.case_id,
        "case_alias": contract.get("case_alias"),
        "contract": relative_contract.as_posix(),
        "contract_sha256": validated["contract_sha256"],
        "reference_sha256": validated["reference_sha256"],
        "created_at": datetime.now().isoformat(),
    }
    path = formal_golden_attestation_path(reference)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
    return payload


def load_verified_formal_golden_attestation(
    reference: ReferenceReport,
) -> dict | None:
    path = formal_golden_attestation_path(reference)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        contract_relative = Path(str(payload.get("contract") or ""))
        if contract_relative.is_absolute():
            return None
        contract_path = (settings.upstream_root / contract_relative).resolve()
        contract_path.relative_to((settings.upstream_root / "panels").resolve())
        contract = load_historical_golden_contract(contract_path)
        stored_path = Path(reference.stored_path)
        checks = (
            payload.get("schema_version") == "1.0",
            payload.get("reference_id") == reference.id,
            normalize_lookup(payload.get("panel_id"))
            == normalize_lookup(reference.panel_id),
            normalize_lookup(payload.get("case_id")) == normalize_lookup(reference.case_id),
            payload.get("case_alias") == contract.get("case_alias"),
            normalize_lookup(contract.get("panel_id"))
            == normalize_lookup(reference.panel_id),
            payload.get("contract_sha256") == sha256_file(contract_path),
            payload.get("reference_sha256") == reference.checksum_sha256,
            reference.checksum_sha256 == sha256_file(stored_path),
            (contract.get("source") or {}).get("reference_docx_sha256")
            == reference.checksum_sha256,
        )
    except Exception:
        return None
    return payload if all(checks) else None


def report_diff_dir(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    path = Path(output_path)
    if path.suffix.lower() == ".docx":
        return path.parent / "report_diff"
    return path / "report_diff"


def report_diff_artifact_path(output_path: Optional[str], filename: str) -> Optional[Path]:
    diff_dir = report_diff_dir(output_path)
    if not diff_dir:
        return None
    if filename in {BATCH_DIFF_JSON, BATCH_DIFF_MD}:
        candidate = (diff_dir / filename).resolve()
    elif filename in ALLOWED_DIFF_ARTIFACTS:
        candidate = (diff_dir / filename).resolve()
    elif filename.endswith("/report_diff.json") or filename.endswith("/report_diff.md"):
        candidate = (diff_dir / filename).resolve()
    else:
        return None
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


def batch_report_diff_artifact_path(output_root: Optional[str], filename: str) -> Optional[Path]:
    if filename not in {BATCH_DIFF_JSON, BATCH_DIFF_MD}:
        return None
    diff_dir = report_diff_dir(output_root)
    if not diff_dir:
        return None
    candidate = (diff_dir / filename).resolve()
    try:
        candidate.relative_to(diff_dir.resolve())
    except ValueError:
        return None
    return candidate


def load_batch_report_diff(output_root: Optional[str]) -> Optional[dict]:
    path = batch_report_diff_artifact_path(output_root, BATCH_DIFF_JSON)
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def report_diff_summary(output_path: Optional[str]) -> dict:
    batch_payload = load_batch_report_diff(output_path)
    if batch_payload:
        summary = batch_payload.get("summary") or {}
        gate = batch_payload.get("gate") or {}
        return {
            "diff_report_file": str(
                batch_report_diff_artifact_path(output_path, BATCH_DIFF_JSON)
            ),
            "diff_markdown_file": str(
                batch_report_diff_artifact_path(output_path, BATCH_DIFF_MD)
            ),
            "diff_status": batch_payload.get("status"),
            "diff_gate_passed": gate.get("passed"),
            "diff_require_reference": bool(gate.get("require_reference")),
            "diff_reference_id": None,
            "diff_reference_name": (
                f"基准命中 {summary.get('matched_references', 0)}/"
                f"{summary.get('total_reports', 0)}"
            ),
        }

    payload = load_report_diff(output_path)
    diff_path = report_diff_artifact_path(output_path, "report_diff.json")
    md_path = report_diff_artifact_path(output_path, "report_diff.md")
    if not payload:
        return {
            "diff_report_file": str(diff_path) if diff_path and diff_path.exists() else None,
            "diff_markdown_file": str(md_path) if md_path and md_path.exists() else None,
            "diff_status": None,
            "diff_gate_passed": None,
            "diff_require_reference": False,
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
        "diff_require_reference": bool(gate.get("require_reference")),
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


def find_active_reference(
    db: Session,
    *,
    panel_id: str | None,
    case_id: str | None,
    require_formal_golden: bool = False,
) -> ReferenceReport | None:
    if not panel_id or not case_id:
        return None
    reference = (
        db.query(ReferenceReport)
        .filter(
            func.lower(ReferenceReport.panel_id) == normalize_lookup(panel_id),
            func.lower(ReferenceReport.case_id) == normalize_lookup(case_id),
            ReferenceReport.active == True,  # noqa: E712
        )
        .order_by(ReferenceReport.created_at.desc())
        .first()
    )
    if reference and require_formal_golden:
        return reference if load_verified_formal_golden_attestation(reference) else None
    return reference


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
    try:
        _size, checksum = write_upload_stream(
            fileobj,
            stored_path,
            scope="金标准文件",
        )
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise

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
        checksum_sha256=checksum,
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
    attestation_path = formal_golden_attestation_path(reference)
    db.delete(reference)
    db.commit()
    try:
        path.unlink(missing_ok=True)
        attestation_path.unlink(missing_ok=True)
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


def derive_reference_case_id_from_payload(
    payload: dict | None,
    *,
    fallback_filename: str | None = None,
) -> str | None:
    payload = payload or {}
    for key in CASE_ID_KEYS:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value).strip()
    if fallback_filename:
        stem = Path(fallback_filename).stem
        token_match = re.search(r"(?i)([a-z]{1,8}\d{4,})", stem)
        return token_match.group(1) if token_match else stem
    return None


def find_active_reference_for_task(
    db: Session,
    task: Task,
    *,
    require_formal_golden: bool = False,
) -> ReferenceReport | None:
    if not task.project_type:
        return None
    upload = (
        db.query(Upload).filter(Upload.id == task.upload_id).first()
        if task.upload_id
        else None
    )
    case_id = derive_reference_case_id(task, upload)
    if not case_id:
        return None
    return find_active_reference(
        db,
        panel_id=task.project_type,
        case_id=case_id,
        require_formal_golden=require_formal_golden,
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
    output_dir: str | Path | None = None,
) -> dict:
    if fail_on not in {"fail", "warn"}:
        raise ValueError("fail_on must be 'fail' or 'warn'")
    if not task.output_path:
        raise ValueError("报告文件不存在")

    diff_dir = Path(output_dir) if output_dir else report_diff_dir(task.output_path)
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
    require_reference: bool = False,
) -> dict | None:
    reference = find_active_reference_for_task(
        db,
        task,
        require_formal_golden=require_reference,
    )
    if not reference:
        if require_reference:
            return write_reference_gate_failure(
                task,
                code="REFERENCE_REQUIRED_NOT_FOUND",
                message="金标准验收模式未找到与 Panel/病例编号匹配的启用基准报告",
                fail_on=fail_on,
                task_id=task.id,
            )
        return None
    try:
        result = compare_task_with_reference_path(
            task,
            reference_docx=reference.stored_path,
            task_id=task.id,
            fail_on=fail_on,
            max_samples=max_samples,
            reference_report=reference,
        )
    except Exception as exc:
        if not require_reference:
            raise
        return write_reference_gate_failure(
            task,
            code="REFERENCE_DIFF_EXECUTION_FAILED",
            message=f"金标准报告对比执行失败: {exc}",
            fail_on=fail_on,
            task_id=task.id,
            reference_report=reference,
        )
    result.setdefault("gate", {})["require_reference"] = require_reference
    diff_dir = report_diff_dir(task.output_path)
    if diff_dir:
        write_report_diff_outputs(result, diff_dir)
    return result


def write_reference_gate_failure(
    task: Task,
    *,
    code: str,
    message: str,
    fail_on: str = "fail",
    task_id: str | None = None,
    reference_report: ReferenceReport | None = None,
) -> dict:
    """Persist a fail-closed artifact when required reference validation cannot run."""
    diff_dir = report_diff_dir(task.output_path)
    if not diff_dir:
        raise ValueError("报告对比目录不可用")
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "status": "FAIL",
        "reference_docx": (
            reference_report.stored_path if reference_report is not None else ""
        ),
        "candidate_docx": str(task.output_path or ""),
        "summary": {"failures": 1, "warnings": 0, "text_similarity": None},
        "sections": {},
        "issues": [{"level": "error", "code": code, "message": message}],
        "gate": {
            "fail_on": fail_on,
            "passed": False,
            "require_reference": True,
        },
    }
    if reference_report is not None:
        payload["reference_report"] = reference_to_dict(reference_report)
    if task_id:
        payload["download_urls"] = {
            "json": f"/api/v1/reports/{task_id}/diff/download/report_diff.json",
            "markdown": f"/api/v1/reports/{task_id}/diff/download/report_diff.md",
        }
    write_report_diff_outputs(payload, diff_dir)
    return payload


def _resolve_batch_output_docx(output_root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = output_root / path
    path = path.resolve()
    if not path.exists() or path.suffix.lower() != ".docx":
        return None
    return path


def _batch_row_snapshot(row: dict) -> dict:
    snapshot = row.get("patient_snapshot")
    if isinstance(snapshot, dict) and snapshot:
        return snapshot
    validation = row.get("validation") or {}
    if isinstance(validation, dict):
        clinical_info = validation.get("clinical_info") or {}
        if isinstance(clinical_info, dict):
            return clinical_info
    return {}


def _panel_id_for_batch_row(task: Task, row: dict) -> str | None:
    validation = row.get("validation") or {}
    validation_panel = (
        validation.get("project_type") if isinstance(validation, dict) else None
    )
    snapshot = _batch_row_snapshot(row)
    return (
        str(snapshot.get("project_type")).strip()
        if snapshot.get("project_type")
        else str(validation_panel).strip() if validation_panel else task.project_type
    )


def _batch_status_from_counts(fail: int, warn: int, skipped: int) -> str:
    if fail:
        return "FAIL"
    if warn or skipped:
        return "WARN"
    return "PASS"


def _write_batch_diff_markdown(payload: dict, output_dir: Path) -> Path:
    summary = payload.get("summary") or {}
    lines = [
        "# Batch Report Diff",
        "",
        f"- Status: {payload.get('status')}",
        f"- Gate passed: {(payload.get('gate') or {}).get('passed')}",
        f"- Total reports: {summary.get('total_reports', 0)}",
        f"- Matched references: {summary.get('matched_references', 0)}",
        f"- PASS/WARN/FAIL/SKIP: {summary.get('pass', 0)}/"
        f"{summary.get('warn', 0)}/{summary.get('fail', 0)}/"
        f"{summary.get('skip', 0)}",
        "",
        "| # | Case | Panel | Status | Gate | Reference | Report |",
        "|---|------|-------|--------|------|-----------|--------|",
    ]
    for row in payload.get("items") or []:
        gate = row.get("gate_passed")
        lines.append(
            (
                "| {index} | {case_id} | {panel_id} | {status} | {gate} | "
                "{reference} | {report} |"
            ).format(
                index=row.get("index", ""),
                case_id=row.get("case_id") or "-",
                panel_id=row.get("panel_id") or "-",
                status=row.get("status") or "-",
                gate="-" if gate is None else ("PASS" if gate else "BLOCK"),
                reference=row.get("reference_name") or "-",
                report=row.get("output_docx") or "-",
            )
        )
    path = output_dir / BATCH_DIFF_MD
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_batch_reference_gate_failure(
    task: Task,
    batch_report: dict,
    *,
    message: str,
    fail_on: str = "fail",
) -> dict:
    """Persist a fail-closed batch artifact when required validation aborts."""
    output_root = Path(str(task.output_path or batch_report.get("output_root"))).resolve()
    diff_root = report_diff_dir(str(output_root))
    if not diff_root:
        raise ValueError("批量报告对比目录不可用")
    diff_root.mkdir(parents=True, exist_ok=True)
    total = len(batch_report.get("results") or [])
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "task_id": task.id,
        "status": "FAIL",
        "gate": {
            "fail_on": fail_on,
            "passed": False,
            "require_reference": True,
        },
        "summary": {
            "total_reports": total,
            "matched_references": 0,
            "pass": 0,
            "warn": 0,
            "fail": total or 1,
            "skip": 0,
            "blocked": total or 1,
        },
        "issues": [
            {
                "level": "error",
                "code": "BATCH_REFERENCE_GATE_EXECUTION_FAILED",
                "message": message,
            }
        ],
        "items": [],
        "download_urls": {
            "json": f"/api/v1/reports/{task.id}/diff/batch/download/{BATCH_DIFF_JSON}",
            "markdown": f"/api/v1/reports/{task.id}/diff/batch/download/{BATCH_DIFF_MD}",
        },
    }
    json_path = diff_root / BATCH_DIFF_JSON
    md_path = _write_batch_diff_markdown(payload, diff_root)
    payload["json_file"] = str(json_path)
    payload["markdown_file"] = str(md_path)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def run_batch_reference_diff(
    db: Session,
    task: Task,
    batch_report: dict,
    *,
    fail_on: str = "fail",
    max_samples: int = 50,
    require_reference: bool = False,
) -> dict:
    output_root = Path(str(task.output_path or batch_report.get("output_root"))).resolve()
    diff_root = report_diff_dir(str(output_root))
    if not diff_root:
        raise ValueError("批量报告对比目录不可用")
    diff_root.mkdir(parents=True, exist_ok=True)

    items = []
    matched = 0
    pass_count = warn_count = fail_count = skip_count = 0
    blocked_count = 0

    for row in batch_report.get("results") or []:
        output_docx = _resolve_batch_output_docx(output_root, row.get("output_docx"))
        snapshot = _batch_row_snapshot(row)
        panel_id = _panel_id_for_batch_row(task, row)
        case_id = derive_reference_case_id_from_payload(
            snapshot,
            fallback_filename=row.get("excel_filename"),
        )
        item = {
            "index": row.get("index"),
            "excel_filename": row.get("excel_filename"),
            "output_docx": str(output_docx) if output_docx else row.get("output_docx"),
            "diff_key": sanitize_path_segment(output_docx.stem) if output_docx else None,
            "panel_id": panel_id,
            "case_id": case_id,
            "status": "SKIP",
            "gate_passed": None,
            "reference_id": None,
            "reference_name": None,
            "diff_json": None,
            "diff_markdown": None,
            "message": None,
        }
        if not output_docx:
            item["status"] = "FAIL"
            item["gate_passed"] = False
            item["message"] = "生成报告不存在，无法执行对比"
            fail_count += 1
            blocked_count += 1
            items.append(item)
            continue
        reference = find_active_reference(
            db,
            panel_id=panel_id,
            case_id=case_id,
            require_formal_golden=require_reference,
        )
        if not reference:
            if require_reference:
                item["status"] = "FAIL"
                item["gate_passed"] = False
                item["message"] = "金标准验收模式未找到匹配的启用基准报告"
                fail_count += 1
                blocked_count += 1
            else:
                item["message"] = "未找到匹配的启用基准报告"
                skip_count += 1
            items.append(item)
            continue

        matched += 1
        pseudo_task = Task(
            id=f"{task.id}:{row.get('index')}",
            task_type="single",
            status="completed",
            project_type=panel_id,
            output_path=str(output_docx),
        )
        item_dir = diff_root / item["diff_key"]
        try:
            result = compare_task_with_reference_path(
                pseudo_task,
                reference_docx=reference.stored_path,
                fail_on=fail_on,
                max_samples=max_samples,
                reference_report=reference,
                output_dir=item_dir,
            )
            status = result.get("status") or "WARN"
            gate_passed = bool((result.get("gate") or {}).get("passed"))
            item.update(
                {
                    "status": status,
                    "gate_passed": gate_passed,
                    "reference_id": reference.id,
                    "reference_name": reference.name,
                    "diff_json": str(item_dir / "report_diff.json"),
                    "diff_markdown": str(item_dir / "report_diff.md"),
                    "download_urls": {
                        "json": (
                            f"/api/v1/reports/{task.id}/diff/batch/items/"
                            f"{item['diff_key']}/download/report_diff.json"
                        ),
                        "markdown": (
                            f"/api/v1/reports/{task.id}/diff/batch/items/"
                            f"{item['diff_key']}/download/report_diff.md"
                        ),
                    },
                    "message": result.get("summary"),
                }
            )
            if status == "PASS":
                pass_count += 1
            elif status == "FAIL":
                fail_count += 1
            else:
                warn_count += 1
            if not gate_passed:
                blocked_count += 1
        except Exception as exc:
            item["status"] = "FAIL"
            item["gate_passed"] = False
            item["reference_id"] = reference.id
            item["reference_name"] = reference.name
            item["message"] = f"报告对比失败: {exc}"
            fail_count += 1
            blocked_count += 1
        items.append(item)

    status = _batch_status_from_counts(fail_count, warn_count, skip_count)
    gate_passed = blocked_count == 0
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "task_id": task.id,
        "status": status,
        "gate": {
            "fail_on": fail_on,
            "passed": gate_passed,
            "require_reference": require_reference,
        },
        "summary": {
            "total_reports": len(batch_report.get("results") or []),
            "matched_references": matched,
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "skip": skip_count,
            "blocked": blocked_count,
        },
        "download_urls": {
            "json": f"/api/v1/reports/{task.id}/diff/batch/download/{BATCH_DIFF_JSON}",
            "markdown": f"/api/v1/reports/{task.id}/diff/batch/download/{BATCH_DIFF_MD}",
        },
        "items": items,
    }
    json_path = diff_root / BATCH_DIFF_JSON
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = _write_batch_diff_markdown(payload, diff_root)
    payload["json_file"] = str(json_path)
    payload["markdown_file"] = str(md_path)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
