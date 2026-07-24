"""Batch report generation endpoints."""

import asyncio
import hashlib
import json
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from reportgen.core.enhancer_registry import get_panel_registry
from reportgen.panels.release_scope import PanelReleaseDisabledError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.dependencies import (
    TASK_PRIVILEGED_ROLES,
    get_bridge,
    require_user,
    user_can_access_task,
    user_can_access_upload,
)
from app.models.batch_submission import BatchSubmission
from app.models.task import Task, TaskResult
from app.models.upload import Upload
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services import clinical_info_service as clinical_svc
from app.services import reference_report_service as diff_svc
from app.services.audit_log import record_audit_event
from app.services.batch_lifecycle import (
    BATCH_ACTIVE_STATUSES,
    BATCH_ITEM_ACTIVE_STATUSES,
    BATCH_ITEM_TERMINAL_STATUSES,
    BATCH_QUEUED_STATUSES,
    empty_batch_status_counts,
)
from app.services.file_manager import (
    UploadLimitExceeded,
    ensure_report_dir,
    max_batch_upload_bytes,
    safe_client_filename,
    save_upload_with_digest,
)
from app.services.generation_preflight import (
    required_dates_error_message,
    validate_required_dates,
)
from app.services.generation_process import run_generate_report_with_timeout
from app.services.generation_queue import submit_generation_job
from app.services.reportgen_bridge import ReportGenBridge
from app.services.task_manager import submit_batch_task
from app.time_utils import utc_now_naive

router = APIRouter(prefix="/reports", tags=["reports-batch"])

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def _batch_generation_policy_error(project_type: Optional[str]) -> Optional[str]:
    """Return a safe reason when the selected Panel disallows shared batches."""
    if not str(project_type or "").strip():
        return None
    try:
        registration = get_panel_registry().get(project_type)
    except Exception:
        return None
    package = registration.package if registration else None
    policy = (package.raw.get("batch_generation") or {}) if package else {}
    if not isinstance(policy, dict) or policy.get("enabled", True):
        return None
    if policy.get("clinical_info_mode") == "per_case_required":
        return (
            "该项目的临床指标必须逐病例录入，当前批量表单仅支持整批共享字段，"
            "为避免患者间结果串用，暂不开放批量生成。"
        )
    return str(policy.get("reason") or "该项目当前未开放批量生成。").strip()


def _validated_reference_gate_mode(value: str | None, user: User) -> str:
    try:
        mode = diff_svc.normalize_reference_gate_mode(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if diff_svc.reference_is_required(mode) and user.role not in TASK_PRIVILEGED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="仅复核人或管理员可启用金标准验收模式",
        )
    return mode


def _json_list(value: Optional[str]) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return [str(value)]
    return parsed if isinstance(parsed, list) else [parsed]


def _json_dict(value: Optional[str]) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _infer_project_type_from_name(
    bridge: ReportGenBridge,
    project_type: Optional[str],
    project_name: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    if project_type or not project_name:
        return project_type, project_name
    inferred = bridge.infer_project_type_from_text(project_name)
    if inferred.get("detected"):
        return inferred.get("project_type"), project_name or inferred.get("project_name")
    return project_type, project_name


def _raise_if_project_type_disabled(
    bridge: ReportGenBridge,
    project_type: Optional[str],
) -> None:
    try:
        bridge.ensure_project_type_enabled(project_type)
    except PanelReleaseDisabledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _enrich_clinical_payload(
    clinical_info: Optional[dict],
    project_type: Optional[str],
    *,
    lookup_sample_id: Optional[str] = None,
) -> dict:
    payload = dict(clinical_info or {})
    sample_id = str(payload.get("sample_id") or payload.get("样本编号") or "").strip()
    lookup_id = str(lookup_sample_id or "").strip() or sample_id
    if not lookup_id:
        return clinical_svc.fill_missing_report_date(payload)
    if not sample_id and lookup_id:
        payload["sample_id"] = lookup_id
    enrichment = clinical_svc.enrich_patient_with_hard_timeout(
        lookup_id,
        project_type=project_type,
    )
    payload = clinical_svc.merge_enrichment_into_values(payload, enrichment)
    return clinical_svc.fill_missing_report_date(payload)


def _batch_report_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / "batch_report.json"


def _batch_inputs_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / "batch_inputs.private.json"


def _batch_status_counts(results: list[TaskResult]) -> dict[str, int]:
    counts = empty_batch_status_counts()
    for result in results:
        status = result.status or "pending"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _normalized_idempotency_key(value: Optional[str]) -> str:
    key = str(value or "").strip() or str(uuid.uuid4())
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key 格式无效，请使用 8-128 位字母、数字或 ._:-。",
        )
    return key


def _batch_request_digest(
    *,
    items: list[dict],
    shared_clinical_info: dict,
    project_type: Optional[str],
    project_name: Optional[str],
    template_name: Optional[str],
    template_contract_mode: str,
    reference_gate_mode: str = "available",
) -> str:
    canonical = {
        "files": [
            {
                "index": int(item["index"]),
                "filename": str(item.get("filename") or ""),
                "size": int(item.get("file_size") or 0),
                "sha256": str(item.get("sha256") or ""),
            }
            for item in items
        ],
        "clinical_info": shared_clinical_info,
        "project_type": project_type,
        "project_name": project_name,
        "template_name": template_name,
        "template_contract_mode": template_contract_mode,
        "reference_gate_mode": reference_gate_mode,
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cleanup_uncommitted_batch(items: list[dict], output_dir: Path | None = None) -> None:
    """Remove only per-request artifacts created before an idempotency replay."""
    storage_root = settings.storage_root.resolve()
    for item in items:
        stored_path = Path(str(item.get("stored_path") or ""))
        try:
            parent = stored_path.resolve().parent
            parent.relative_to(storage_root)
        except (OSError, ValueError):
            continue
        shutil.rmtree(parent, ignore_errors=True)
    if output_dir is not None:
        try:
            resolved = output_dir.resolve()
            resolved.relative_to(settings.report_dir.resolve())
        except (OSError, ValueError):
            return
        shutil.rmtree(resolved, ignore_errors=True)


def _idempotent_response_data(
    db: Session,
    submission: BatchSubmission,
    *,
    accept_started: float,
) -> dict:
    task = db.query(Task).filter(Task.id == submission.task_id).first()
    if task is None:
        raise HTTPException(
            status_code=409,
            detail="幂等记录对应的任务不存在，请更换 Idempotency-Key 后重试。",
        )
    return {
        "task_id": task.id,
        "status": task.status,
        "total_files": task.total_files,
        "idempotency_key": submission.idempotency_key,
        "idempotent_replay": True,
        "accept_duration_ms": round((time.perf_counter() - accept_started) * 1000, 3),
    }


def _resolve_batch_status(*, completed: int, failed: int, total: int) -> str:
    if total and completed >= total and failed == 0:
        return "completed"
    if completed and failed:
        return "partial_failed"
    if failed and not completed:
        return "failed"
    return "completed" if completed else "failed"


def _write_batch_inputs(
    *,
    output_dir: str | Path,
    task_id: str,
    items: list[dict],
    shared_clinical_info: dict,
    project_type: Optional[str],
    project_name: Optional[str],
    template_name: Optional[str],
    template_contract_mode: str,
    reference_gate_mode: str = "available",
) -> dict:
    payload = {
        "schema_version": "1.0",
        "created_at": utc_now_naive().isoformat(),
        "task_id": task_id,
        "project_type": project_type,
        "project_name": project_name,
        "template_name": template_name,
        "template_contract_mode": template_contract_mode,
        "reference_gate_mode": reference_gate_mode,
        "shared_clinical_info": shared_clinical_info,
        "items": items,
    }
    path = _batch_inputs_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _load_batch_inputs(output_dir: str | Path) -> dict:
    path = _batch_inputs_path(output_dir)
    if not path.exists():
        raise HTTPException(
            status_code=409,
            detail="该批量任务缺少源文件索引，无法重试；请重新上传失败文件。",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"批量源文件索引读取失败: {exc}",
        ) from exc
    return payload if isinstance(payload, dict) else {}


def _task_result_to_row(result: TaskResult, output_root: Path) -> dict:
    output_path = Path(result.output_path) if result.output_path else None
    output_docx = None
    if output_path and output_path.exists():
        try:
            output_docx = str(output_path.resolve().relative_to(output_root.resolve()))
        except Exception:
            output_docx = output_path.name
    return {
        "index": result.file_index,
        "ok": result.status == "completed",
        "status": result.status,
        "excel_filename": result.excel_filename,
        "output_docx": output_docx,
        "duration_seconds": result.duration_seconds,
        "errors": _json_list(result.errors),
        "warnings": _json_list(result.warnings),
        "validation": _json_dict(result.validation_summary),
    }


def _write_batch_report(db: Session, task: Task) -> dict:
    output_root = Path(task.output_path or ensure_report_dir(task.id))
    results = (
        db.query(TaskResult)
        .filter(TaskResult.task_id == task.id)
        .order_by(TaskResult.file_index.asc())
        .all()
    )
    rows = [_task_result_to_row(result, output_root) for result in results]
    counts = _batch_status_counts(results)
    payload = {
        "generated_at": utc_now_naive().isoformat(),
        "task_id": task.id,
        "status": task.status,
        "inputs_count": task.total_files,
        "successes": task.completed_files,
        "failures": task.failed_files,
        "counts": counts,
        "output_root": str(output_root),
        "results": rows,
    }
    path = _batch_report_path(output_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _prepare_item_clinical_payload(
    *,
    stored_path: str,
    original_filename: str,
    bridge: ReportGenBridge,
    shared_clinical_info: dict,
    project_type: Optional[str],
    project_name: Optional[str],
) -> tuple[dict, Optional[str], Optional[str], object]:
    excel_data = bridge.read_excel(stored_path)
    detected_project_type = project_type
    detected_project_name = project_name
    if not detected_project_type:
        detect = bridge.detect_project_type(
            str(Path(stored_path).parent / (original_filename or "upload.xlsx")),
            excel_data=excel_data,
        )
        detected_project_type = detect.get("project_type")
        detected_project_name = detected_project_name or detect.get("project_name")
    detected_project_type, detected_project_name = _infer_project_type_from_name(
        bridge,
        detected_project_type,
        detected_project_name or shared_clinical_info.get("project_name"),
    )
    _raise_if_project_type_disabled(bridge, detected_project_type)
    batch_policy_error = _batch_generation_policy_error(detected_project_type)
    if batch_policy_error:
        raise ValueError(batch_policy_error)

    clinical_payload = bridge.get_mapped_clinical_fields(excel_data)
    clinical_payload.update(
        {
            key: value
            for key, value in shared_clinical_info.items()
            if value not in (None, "")
        }
    )
    clinical_payload = _enrich_clinical_payload(
        clinical_payload,
        detected_project_type,
        lookup_sample_id=clinical_svc.project_code_from_filename(original_filename),
    )
    return clinical_payload, detected_project_type, detected_project_name, excel_data


def _preflight_item_payload(
    *,
    stored_path: str,
    original_filename: str,
    bridge: ReportGenBridge,
    shared_clinical_info: dict,
    project_type: Optional[str],
    project_name: Optional[str],
) -> dict:
    (
        clinical_payload,
        detected_project_type,
        detected_project_name,
        excel_data,
    ) = (
        _prepare_item_clinical_payload(
            stored_path=stored_path,
            original_filename=original_filename,
            bridge=bridge,
            shared_clinical_info=shared_clinical_info,
            project_type=project_type,
            project_name=project_name,
        )
    )

    preflight = validate_required_dates(
        bridge,
        excel_path=stored_path,
        clinical_info=clinical_payload,
        project_type=detected_project_type,
        project_name=detected_project_name,
        excel_data=excel_data,
    )
    missing = list(preflight.get("missing") or [])
    if missing:
        raise ValueError(required_dates_error_message(missing))
    return {
        "clinical_payload": clinical_payload,
        "project_type": detected_project_type,
        "project_name": detected_project_name,
        "preflight": preflight,
    }


def _batch_terminal_counts(db: Session, task_id: str) -> tuple[int, int]:
    completed_files = (
        db.query(TaskResult)
        .filter(TaskResult.task_id == task_id, TaskResult.status == "completed")
        .count()
    )
    failed_files = (
        db.query(TaskResult)
        .filter(TaskResult.task_id == task_id, TaskResult.status == "failed")
        .count()
    )
    return completed_files, failed_files


def _refresh_batch_counts(db: Session, task: Task, *, started_at: datetime) -> None:
    task.completed_files, task.failed_files = _batch_terminal_counts(db, task.id)
    task.duration_seconds = (utc_now_naive() - started_at).total_seconds()


def _load_batch_task_fresh(db: Session, task_id: str) -> Task | None:
    """Reload task state so cancellation from another session is observable."""
    return (
        db.query(Task)
        .populate_existing()
        .filter(Task.id == task_id)
        .first()
    )


def _build_item_payload(
    *,
    stored_path: str,
    bridge: ReportGenBridge,
    prepared: dict,
    template_name: Optional[str],
    output_dir: str,
    template_contract_mode: str,
    reference_gate_mode: str = "available",
) -> tuple[dict, dict, Optional[str], Optional[str]]:
    clinical_payload = prepared["clinical_payload"]
    detected_project_type = prepared.get("project_type")
    detected_project_name = prepared.get("project_name")

    result = run_generate_report_with_timeout(
        bridge,
        excel_path=stored_path,
        output_dir=output_dir,
        template_name=template_name,
        clinical_info=clinical_payload,
        project_type=detected_project_type,
        project_name=detected_project_name,
        strict_mode=False,
        template_contract_mode=template_contract_mode,
        qa_visual_render=(
            "all" if diff_svc.reference_is_required(reference_gate_mode) else None
        ),
        qa_visual_render_required=(
            True if diff_svc.reference_is_required(reference_gate_mode) else None
        ),
    )
    summary = {
        "project_type": detected_project_type,
        "project_name": detected_project_name,
        "clinical_info": {
            key: clinical_payload.get(key)
            for key in (
                "patient_name",
                "sample_id",
                "clinical_diagnosis",
                "cancer_type",
                "sample_type",
            )
            if clinical_payload.get(key) not in (None, "")
        },
        "report_summary_file": result.get("report_summary_file"),
        "qa_status": result.get("qa_status"),
        "qa_report_file": result.get("qa_report_file"),
        "field_provenance_file": result.get("field_provenance_file"),
        "stage_results_file": result.get("stage_results_file"),
    }
    return result, summary, detected_project_type, detected_project_name


def _complete_batch_files_task(
    *,
    task_id: str,
    items: list[dict],
    output_dir: str,
    shared_clinical_info: dict,
    project_type: Optional[str],
    project_name: Optional[str],
    template_name: Optional[str],
    template_contract_mode: str,
    reference_gate_mode: str = "available",
    bridge: ReportGenBridge,
) -> None:
    db = SessionLocal()
    worker_started = utc_now_naive()
    try:
        task = _load_batch_task_fresh(db, task_id)
        if not task:
            return
        if task.status == "cancelled":
            return
        started_at = task.started_at or worker_started
        transitioned = (
            db.query(Task)
            .filter(
                Task.id == task_id,
                Task.status.in_(list(BATCH_QUEUED_STATUSES)),
            )
            .update(
                {
                    Task.status: "preflight",
                    Task.started_at: started_at,
                    Task.output_path: output_dir,
                },
                synchronize_session=False,
            )
        )
        if transitioned != 1:
            db.rollback()
            return
        db.commit()
        task = _load_batch_task_fresh(db, task_id)
        if not task:
            return
        _write_batch_report(db, task)

        prepared_items: list[tuple[dict, dict]] = []
        for item in items:
            task = _load_batch_task_fresh(db, task_id)
            if not task or task.status == "cancelled":
                break
            row = (
                db.query(TaskResult)
                .filter(
                    TaskResult.task_id == task_id,
                    TaskResult.file_index == item["index"],
                )
                .first()
            )
            if not row:
                continue
            if row.status in BATCH_ITEM_TERMINAL_STATUSES:
                continue
            row.status = "preflight"
            row.validation_summary = json.dumps(
                {"stage": "preflight"},
                ensure_ascii=False,
            )
            db.commit()

            started = utc_now_naive()
            try:
                prepared = _preflight_item_payload(
                    stored_path=item["stored_path"],
                    original_filename=item["filename"],
                    bridge=bridge,
                    shared_clinical_info=shared_clinical_info,
                    project_type=project_type,
                    project_name=project_name,
                )
                task = _load_batch_task_fresh(db, task_id)
                row = (
                    db.query(TaskResult)
                    .filter(
                        TaskResult.task_id == task_id,
                        TaskResult.file_index == item["index"],
                    )
                    .first()
                )
                if not task or task.status == "cancelled" or not row:
                    break
                row.validation_summary = json.dumps(
                    {
                        "stage": "preflight",
                        "preflight": prepared.get("preflight") or {},
                        "project_type": prepared.get("project_type"),
                        "project_name": prepared.get("project_name"),
                    },
                    ensure_ascii=False,
                )
                prepared_items.append((item, prepared))
            except Exception as exc:
                row.status = "failed"
                row.duration_seconds = (utc_now_naive() - started).total_seconds()
                row.errors = json.dumps([str(exc)], ensure_ascii=False)
                row.warnings = json.dumps([], ensure_ascii=False)
                row.validation_summary = json.dumps(
                    {"stage": "preflight", "preflight": {"ok": False}},
                    ensure_ascii=False,
                )

            task = _load_batch_task_fresh(db, task_id)
            if not task:
                return
            _refresh_batch_counts(db, task, started_at=started_at)
            db.commit()
            _write_batch_report(db, task)

        task = _load_batch_task_fresh(db, task_id)
        if not task or task.status == "cancelled":
            return
        completed_files, failed_files = _batch_terminal_counts(db, task_id)
        transitioned = (
            db.query(Task)
            .filter(Task.id == task_id, Task.status == "preflight")
            .update(
                {
                    Task.status: "generating",
                    Task.completed_files: completed_files,
                    Task.failed_files: failed_files,
                    Task.duration_seconds: (
                        utc_now_naive() - started_at
                    ).total_seconds(),
                },
                synchronize_session=False,
            )
        )
        if transitioned != 1:
            db.rollback()
            return
        db.commit()
        task = _load_batch_task_fresh(db, task_id)
        if not task:
            return
        _write_batch_report(db, task)

        for item, prepared in prepared_items:
            task = _load_batch_task_fresh(db, task_id)
            if not task or task.status == "cancelled":
                break
            row = (
                db.query(TaskResult)
                .filter(
                    TaskResult.task_id == task_id,
                    TaskResult.file_index == item["index"],
                )
                .first()
            )
            if not row or row.status in BATCH_ITEM_TERMINAL_STATUSES:
                continue
            row.status = "generating"
            db.commit()
            started = utc_now_naive()
            try:
                result, validation_summary, _ptype, _pname = _build_item_payload(
                    stored_path=item["stored_path"],
                    bridge=bridge,
                    prepared=prepared,
                    template_name=template_name,
                    output_dir=output_dir,
                    template_contract_mode=template_contract_mode,
                    reference_gate_mode=reference_gate_mode,
                )
                row.status = "qa"
                db.commit()
                success = bool(result.get("success"))
                row.status = "completed" if success else "failed"
                row.output_path = result.get("output_file")
                row.duration_seconds = result.get("duration")
                row.errors = json.dumps(result.get("errors") or [], ensure_ascii=False)
                row.warnings = json.dumps(
                    result.get("warnings") or [],
                    ensure_ascii=False,
                )
                validation_summary["stage"] = "qa"
                validation_summary["preflight"] = prepared.get("preflight") or {}
                row.validation_summary = json.dumps(
                    validation_summary,
                    ensure_ascii=False,
                )
            except Exception as exc:
                row.status = "failed"
                row.duration_seconds = (utc_now_naive() - started).total_seconds()
                row.errors = json.dumps([str(exc)], ensure_ascii=False)
                row.warnings = json.dumps([], ensure_ascii=False)
                row.validation_summary = json.dumps(
                    {"stage": "generating", "preflight": prepared.get("preflight") or {}},
                    ensure_ascii=False,
                )

            task = _load_batch_task_fresh(db, task_id)
            if not task:
                return
            _refresh_batch_counts(db, task, started_at=started_at)
            db.commit()
            _write_batch_report(db, task)

        task = _load_batch_task_fresh(db, task_id)
        if not task or task.status == "cancelled":
            return
        completed_files, failed_files = _batch_terminal_counts(db, task_id)
        transitioned = (
            db.query(Task)
            .filter(Task.id == task_id, Task.status == "generating")
            .update(
                {
                    Task.status: "qa",
                    Task.completed_files: completed_files,
                    Task.failed_files: failed_files,
                    Task.duration_seconds: (
                        utc_now_naive() - started_at
                    ).total_seconds(),
                },
                synchronize_session=False,
            )
        )
        if transitioned != 1:
            db.rollback()
            return
        db.commit()
        task = _load_batch_task_fresh(db, task_id)
        if not task:
            return
        batch_report = _write_batch_report(db, task)

        warnings = []
        if task.completed_files:
            try:
                diff_payload = diff_svc.run_batch_reference_diff(
                    db,
                    task,
                    batch_report,
                    fail_on="fail",
                    max_samples=50,
                    require_reference=diff_svc.reference_is_required(
                        reference_gate_mode
                    ),
                )
                summary = diff_payload.get("summary") or {}
                warnings.append(
                    "批量Diff: "
                    f"{diff_payload.get('status')} "
                    f"命中{summary.get('matched_references', 0)}/"
                    f"{summary.get('total_reports', 0)}，"
                    f"阻断{summary.get('blocked', 0)}"
                )
            except Exception as exc:
                if diff_svc.reference_is_required(reference_gate_mode):
                    diff_svc.write_batch_reference_gate_failure(
                        task,
                        batch_report,
                        message=f"金标准批量对比执行失败: {exc}",
                    )
                warnings.append(f"批量自动基准对比失败: {exc}")

        completed_files, failed_files = _batch_terminal_counts(db, task_id)
        completed_at = utc_now_naive()
        final_status = _resolve_batch_status(
            completed=completed_files,
            failed=failed_files,
            total=task.total_files,
        )
        updated = (
            db.query(Task)
            .filter(Task.id == task_id, Task.status == "qa")
            .update(
                {
                    Task.status: final_status,
                    Task.completed_files: completed_files,
                    Task.failed_files: failed_files,
                    Task.completed_at: completed_at,
                    Task.duration_seconds: (completed_at - started_at).total_seconds(),
                    Task.warnings: json.dumps(warnings, ensure_ascii=False),
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            db.rollback()
            return
        db.commit()
        task = _load_batch_task_fresh(db, task_id)
        if task:
            _write_batch_report(db, task)
    except Exception as exc:
        task = _load_batch_task_fresh(db, task_id)
        if task and task.status != "cancelled":
            effective_started = task.started_at or worker_started
            completed_at = utc_now_naive()
            failed_transition = (
                db.query(Task)
                .filter(
                    Task.id == task_id,
                    Task.status.in_(list(BATCH_ACTIVE_STATUSES)),
                )
                .update(
                    {
                        Task.status: "failed",
                        Task.errors: json.dumps([str(exc)], ensure_ascii=False),
                        Task.completed_at: completed_at,
                        Task.duration_seconds: (
                            completed_at - effective_started
                        ).total_seconds(),
                    },
                    synchronize_session=False,
                )
            )
            if failed_transition != 1:
                db.rollback()
                return
            (
                db.query(TaskResult)
                .filter(
                    TaskResult.task_id == task_id,
                    TaskResult.status.in_(list(BATCH_ITEM_ACTIVE_STATUSES)),
                )
                .update(
                    {
                        TaskResult.status: "failed",
                        TaskResult.errors: json.dumps(
                            ["批量后台任务异常终止，请在任务详情中重试失败文件。"],
                            ensure_ascii=False,
                        ),
                    },
                    synchronize_session=False,
                )
            )
            completed_files, failed_files = _batch_terminal_counts(db, task_id)
            (
                db.query(Task)
                .filter(Task.id == task_id, Task.status == "failed")
                .update(
                    {
                        Task.completed_files: completed_files,
                        Task.failed_files: failed_files,
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
            task = _load_batch_task_fresh(db, task_id)
            if task:
                _write_batch_report(db, task)
    finally:
        db.close()


async def _on_batch_complete(task_id: str, result: dict):
    """Callback when batch task completes — update DB."""
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return

        if result.get("success"):
            report = result.get("report", {})
            task.status = "completed"
            task.completed_files = report.get("successes", 0)
            task.failed_files = report.get("failures", 0)
            task.output_path = result.get("output_root")
            warnings = []
            try:
                diff_payload = diff_svc.run_batch_reference_diff(
                    db,
                    task,
                    report,
                    fail_on="fail",
                    max_samples=50,
                )
                summary = diff_payload.get("summary") or {}
                warnings.append(
                    "批量Diff: "
                    f"{diff_payload.get('status')} "
                    f"命中{summary.get('matched_references', 0)}/"
                    f"{summary.get('total_reports', 0)}，"
                    f"阻断{summary.get('blocked', 0)}"
                )
            except Exception as exc:
                warnings.append(f"批量自动基准对比失败: {exc}")
            task.warnings = json.dumps(warnings, ensure_ascii=False)
        else:
            task.status = "failed"
            task.errors = json.dumps([result.get("error", "Unknown error")], ensure_ascii=False)

        task.completed_at = utc_now_naive()
        if task.started_at:
            task.duration_seconds = (task.completed_at - task.started_at).total_seconds()
        db.commit()
    finally:
        db.close()


@router.post("/batch", response_model=ApiResponse)
async def batch_generate(
    upload_ids: list[str] = [],
    input_dir: Optional[str] = None,
    project_type: Optional[str] = None,
    highlight: bool = False,
    template_contract: str = "warn",
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
    current_user: User = Depends(require_user),
):
    """
    Submit a batch generation task.

    Provide either upload_ids (list of previously uploaded files)
    or input_dir (directory path containing Excel files).
    """
    _raise_if_project_type_disabled(bridge, project_type)
    batch_policy_error = _batch_generation_policy_error(project_type)
    if batch_policy_error:
        raise HTTPException(status_code=409, detail=batch_policy_error)
    task_id = str(uuid.uuid4())
    output_dir = ensure_report_dir(task_id)

    # Resolve input paths
    input_paths: list[str] = []
    if upload_ids:
        for uid in upload_ids:
            upload = db.query(Upload).filter(Upload.id == uid).first()
            if not upload or not user_can_access_upload(current_user, upload):
                raise HTTPException(status_code=404, detail="上传记录不存在")
            input_paths.append(upload.stored_path)
    elif input_dir:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="仅管理员可从服务器目录创建批量任务")
        input_paths.append(input_dir)
    else:
        raise HTTPException(status_code=400, detail="请提供 upload_ids 或 input_dir")

    total_files = len(input_paths) if upload_ids else 0  # unknown for dir

    # Create task record
    task = Task(
        id=task_id,
        task_type="batch",
        status="running",
        user_id=current_user.id,
        project_type=project_type,
        total_files=total_files,
        started_at=utc_now_naive(),
    )
    db.add(task)
    db.commit()

    # Submit to background
    asyncio.create_task(
        submit_batch_task(
            task_id=task_id,
            inputs=input_paths,
            output_root=str(output_dir),
            config_dir=settings.upstream_config_dir,
            template=None,
            template_contract=template_contract,
            highlight=highlight,
            on_complete=_on_batch_complete,
        )
    )

    return ApiResponse(data={
        "task_id": task_id,
        "status": "running",
        "total_files": total_files,
    })


@router.post("/batch-files", response_model=ApiResponse)
def batch_generate_from_files(
    request: Request,
    files: list[UploadFile] = File(...),
    clinical_info: str = Form("{}"),
    project_type: Optional[str] = Form(None),
    project_name: Optional[str] = Form(None),
    template_name: Optional[str] = Form(None),
    template_contract_mode: str = Form("warn"),
    reference_gate_mode: str = Form("available"),
    idempotency_key_header: Optional[str] = Header(
        None,
        alias="Idempotency-Key",
    ),
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
    current_user: User = Depends(require_user),
):
    """Persist a production batch and return before preflight/enrichment."""
    _raise_if_project_type_disabled(bridge, project_type)
    batch_policy_error = _batch_generation_policy_error(project_type)
    if batch_policy_error:
        raise HTTPException(status_code=409, detail=batch_policy_error)
    accept_started = time.perf_counter()
    reference_gate_mode = _validated_reference_gate_mode(
        reference_gate_mode,
        current_user,
    )
    idempotency_key = _normalized_idempotency_key(idempotency_key_header)
    user_scope = f"user:{current_user.id}"
    excel_files = [file for file in files if file.filename]
    if not excel_files:
        raise HTTPException(status_code=400, detail="请至少上传 1 个 Excel 文件")
    if len(excel_files) > settings.max_batch_files:
        raise HTTPException(
            status_code=413,
            detail=f"批量文件数超过上限（最多 {settings.max_batch_files} 个）",
        )
    for file in excel_files:
        safe_name = safe_client_filename(file.filename, "upload.xlsx")
        if not safe_name.lower().endswith(".xlsx"):
            raise HTTPException(status_code=400, detail=f"仅支持 .xlsx 文件: {safe_name}")
        if safe_name.startswith("._") or safe_name.startswith("~$"):
            raise HTTPException(status_code=400, detail=f"请移除临时文件: {safe_name}")

    try:
        shared_clinical_info = json.loads(clinical_info or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"临床信息不是合法 JSON: {exc}",
        ) from exc
    if not isinstance(shared_clinical_info, dict):
        raise HTTPException(status_code=400, detail="临床信息必须是 JSON 对象")

    items: list[dict] = []
    batch_size = 0
    batch_limit = max_batch_upload_bytes()
    try:
        for index, file in enumerate(excel_files, start=1):
            upload_id, stored_path, file_size, file_digest = save_upload_with_digest(file)
            safe_name = safe_client_filename(file.filename, "upload.xlsx")
            items.append(
                {
                    "index": index,
                    "upload_id": upload_id,
                    "filename": safe_name,
                    "stored_path": str(stored_path),
                    "file_size": file_size,
                    "sha256": file_digest,
                }
            )
            batch_size += file_size
            if batch_size > batch_limit:
                raise UploadLimitExceeded(
                    max_bytes=batch_limit,
                    scope="批量文件总大小",
                )
    except Exception:
        _cleanup_uncommitted_batch(items)
        raise

    request_digest = _batch_request_digest(
        items=items,
        shared_clinical_info=shared_clinical_info,
        project_type=project_type,
        project_name=project_name,
        template_name=template_name,
        template_contract_mode=template_contract_mode,
        reference_gate_mode=reference_gate_mode,
    )
    existing = (
        db.query(BatchSubmission)
        .filter(
            BatchSubmission.user_scope == user_scope,
            BatchSubmission.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        _cleanup_uncommitted_batch(items)
        if existing.request_digest != request_digest:
            raise HTTPException(
                status_code=409,
                detail="该 Idempotency-Key 已用于不同的文件或参数，请更换后重试。",
            )
        return ApiResponse(
            data=_idempotent_response_data(
                db,
                existing,
                accept_started=accept_started,
            )
        )

    task_id = str(uuid.uuid4())
    output_dir = ensure_report_dir(task_id)
    task = Task(
        id=task_id,
        task_type="batch",
        status="queued",
        user_id=current_user.id,
        project_type=project_type,
        output_path=str(output_dir),
        total_files=len(items),
        completed_files=0,
        failed_files=0,
        clinical_info_snapshot=(
            json.dumps(shared_clinical_info, ensure_ascii=False)
            if shared_clinical_info
            else None
        ),
    )
    submission = BatchSubmission(
        user_scope=user_scope,
        idempotency_key=idempotency_key,
        request_digest=request_digest,
        task_id=task_id,
    )
    try:
        db.add(task)
        db.add(submission)
        for item in items:
            db.add(
                TaskResult(
                    task_id=task_id,
                    file_index=item["index"],
                    excel_filename=item["filename"],
                    status="queued",
                )
            )
        _write_batch_inputs(
            output_dir=output_dir,
            task_id=task_id,
            items=items,
            shared_clinical_info=shared_clinical_info,
            project_type=project_type,
            project_name=project_name,
            template_name=template_name,
            template_contract_mode=template_contract_mode,
            reference_gate_mode=reference_gate_mode,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = (
            db.query(BatchSubmission)
            .filter(
                BatchSubmission.user_scope == user_scope,
                BatchSubmission.idempotency_key == idempotency_key,
            )
            .first()
        )
        _cleanup_uncommitted_batch(items, output_dir)
        if winner and winner.request_digest == request_digest:
            return ApiResponse(
                data=_idempotent_response_data(
                    db,
                    winner,
                    accept_started=accept_started,
                )
            )
        if winner:
            raise HTTPException(
                status_code=409,
                detail="该 Idempotency-Key 已用于不同的文件或参数，请更换后重试。",
            )
        raise
    except Exception:
        db.rollback()
        _cleanup_uncommitted_batch(items, output_dir)
        raise

    record_audit_event(
        db,
        action="report.batch_queued",
        resource_type="task",
        resource_id=task_id,
        request=request,
        details={
            "source": "batch-files",
            "task_type": "batch",
            "project_type": project_type,
            "template_name": template_name,
            "template_contract_mode": template_contract_mode,
            "reference_gate_mode": reference_gate_mode,
            "status": "queued",
            "total_files": len(items),
        },
    )
    _write_batch_report(db, task)

    submit_generation_job(
        _complete_batch_files_task,
        task_id=task_id,
        items=items,
        output_dir=str(output_dir),
        shared_clinical_info=shared_clinical_info,
        project_type=project_type,
        project_name=project_name,
        template_name=template_name,
        template_contract_mode=template_contract_mode,
        reference_gate_mode=reference_gate_mode,
        bridge=bridge,
    )

    return ApiResponse(
        data={
            "task_id": task_id,
            "status": "queued",
            "total_files": len(items),
            "idempotency_key": idempotency_key,
            "idempotent_replay": False,
            "accept_duration_ms": round(
                (time.perf_counter() - accept_started) * 1000,
                3,
            ),
        }
    )


@router.post("/{task_id}/batch/retry-failed", response_model=ApiResponse)
def retry_failed_batch_files(
    task_id: str,
    request: Request,
    include_cancelled: bool = False,
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
    current_user: User = Depends(require_user),
):
    """Retry failed rows in a file-based batch task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or not user_can_access_task(current_user, task):
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.task_type != "batch":
        raise HTTPException(status_code=400, detail="仅批量任务支持失败重试")
    if task.status in BATCH_ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="批量任务仍在运行，不能重试")
    if not task.output_path:
        raise HTTPException(status_code=404, detail="批量任务输出目录不存在")

    retry_statuses = ["failed"]
    if include_cancelled:
        retry_statuses.append("cancelled")
    rows = (
        db.query(TaskResult)
        .filter(TaskResult.task_id == task_id, TaskResult.status.in_(retry_statuses))
        .order_by(TaskResult.file_index.asc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=400, detail="没有可重试的失败文件")

    inputs = _load_batch_inputs(task.output_path)
    input_by_index = {
        int(item.get("index")): item
        for item in inputs.get("items") or []
        if item.get("index") is not None
    }
    retry_items = []
    missing = []
    for row in rows:
        item = input_by_index.get(row.file_index)
        stored_path = Path(item.get("stored_path")) if item else None
        if not item or not stored_path or not stored_path.exists():
            missing.append(row.excel_filename)
            continue
        retry_items.append(item)
        row.status = "queued"
        row.output_path = None
        row.duration_seconds = None
        row.errors = None
        row.warnings = None
        row.validation_summary = None

    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"以下源 Excel 不存在，无法重试: {'，'.join(missing)}",
        )
    if not retry_items:
        raise HTTPException(status_code=400, detail="没有可重试的失败文件")

    task.status = "queued"
    task.failed_files = (
        db.query(TaskResult)
        .filter(TaskResult.task_id == task_id, TaskResult.status == "failed")
        .count()
    )
    task.completed_files = (
        db.query(TaskResult)
        .filter(TaskResult.task_id == task_id, TaskResult.status == "completed")
        .count()
    )
    task.completed_at = None
    warnings = _json_list(task.warnings)
    warnings.append(f"已重试失败文件 {len(retry_items)} 个")
    task.warnings = json.dumps(warnings, ensure_ascii=False)
    db.commit()
    record_audit_event(
        db,
        action="report.batch_retry_queued",
        resource_type="task",
        resource_id=task_id,
        request=request,
        details={
            "source": "batch-retry",
            "task_type": "batch",
            "project_type": task.project_type,
            "include_cancelled": include_cancelled,
            "retry_files": len(retry_items),
            "status": "queued",
            "total_files": task.total_files,
        },
    )
    _write_batch_report(db, task)

    submit_generation_job(
        _complete_batch_files_task,
        task_id=task_id,
        items=retry_items,
        output_dir=str(task.output_path),
        shared_clinical_info=inputs.get("shared_clinical_info") or {},
        project_type=inputs.get("project_type"),
        project_name=inputs.get("project_name"),
        template_name=inputs.get("template_name"),
        template_contract_mode=inputs.get("template_contract_mode") or "warn",
        reference_gate_mode=inputs.get("reference_gate_mode") or "available",
        bridge=bridge,
    )

    return ApiResponse(
        data={
            "task_id": task_id,
            "status": "queued",
            "retry_files": len(retry_items),
            "total_files": task.total_files,
        }
    )
