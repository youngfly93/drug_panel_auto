"""Report generation and download endpoints."""

import base64
import json
import os
import re
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse
from reportgen.panels.release_scope import PanelReleaseDisabledError
from reportgen.utils.docx_render import render_docx_to_pngs
from reportgen.utils.file_utils import safe_filename
from reportgen.utils.logger import get_logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.dependencies import (
    TASK_PRIVILEGED_ROLES,
    get_bridge,
    require_reviewer,
    require_user,
    user_can_access_task,
    user_can_access_upload,
)
from app.models.audit import AuditLog
from app.models.task import Task, TaskResult
from app.models.upload import Upload
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.report import (
    GenerateRequest,
    GenerateResponse,
    ReviewStateUpdate,
    TaskStatus,
)
from app.services import clinical_info_service as clinical_svc
from app.services import reference_report_service as diff_svc
from app.services.audit_log import (
    audit_event_payload,
    record_audit_event,
    request_operator,
)
from app.services.batch_lifecycle import (
    BATCH_ACTIVE_STATUSES,
    empty_batch_status_counts,
    pending_file_count,
    working_file_count,
)
from app.services.file_manager import (
    UploadLimitExceeded,
    ensure_report_dir,
    safe_client_filename,
    save_feedback_upload,
    save_upload,
    write_upload_stream,
)
from app.services.generation_preflight import (
    required_inputs_error_message,
    validate_required_inputs,
)
from app.services.generation_process import run_generate_report_with_timeout
from app.services.generation_queue import submit_generation_job
from app.services.project_identity import (
    ProjectIdentityConflictError,
    resolve_project_identity,
)
from app.services.reportgen_bridge import ReportGenBridge
from app.services.task_recovery import write_single_generation_request
from app.time_utils import utc_now_naive

router = APIRouter(prefix="/reports", tags=["reports"])
download_logger = get_logger("reportgen-web.download")
feedback_logger = get_logger("reportgen-web.feedback")


@router.post("/{task_id}/feedback", response_model=ApiResponse[dict])
def upload_report_feedback(
    task_id: str,
    file: UploadFile = File(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """报告组反馈上传：按样本号归档到 storage/feedback/<sample_id>/。

    从任务的报告 summary 推导样本号；无法推导时回退用 task_id 作为目录。
    """
    filename = (file.filename or "").lower()
    if not filename.endswith((".docx", ".doc", ".pdf", ".txt", ".md")):
        raise HTTPException(status_code=400, detail="反馈文件仅支持 DOCX/DOC/PDF/TXT/MD 格式")

    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None or not user_can_access_task(current_user, task):
        raise HTTPException(status_code=404, detail="任务不存在")

    sample_id = task_id
    output_path = task.output_path
    if output_path:
        summary_path = Path(output_path).with_suffix(".summary.json")
        try:
            if summary_path.exists():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                sid = str((summary.get("patient") or {}).get("sample_id") or "").strip()
                if sid:
                    sample_id = sid
        except Exception:  # noqa: BLE001 - best-effort sample_id resolution
            pass

    try:
        stored_path, size = save_feedback_upload(file, sample_id, note=note, task_id=task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    feedback_logger.info(
        "feedback uploaded",
        task_id=task_id,
        sample_id=sample_id,
        file=stored_path.name,
        size=size,
    )
    return ApiResponse(
        success=True,
        data={
            "sample_id": sample_id,
            "filename": stored_path.name,
            "size": size,
        },
    )


DOWNLOAD_SLOW_WARN_SECONDS = float(os.environ.get("RG_WEB_DOWNLOAD_SLOW_WARN_SECONDS", "10"))


def _raise_required_inputs_if_missing(
    bridge: ReportGenBridge,
    *,
    excel_path: str | Path,
    clinical_payload: dict,
    project_type: Optional[str],
    project_name: Optional[str],
    excel_data: object | None = None,
) -> None:
    preflight = validate_required_inputs(
        bridge,
        excel_path=excel_path,
        clinical_info=clinical_payload,
        project_type=project_type,
        project_name=project_name,
        excel_data=excel_data,
    )
    missing = list(preflight.get("missing") or [])
    if missing:
        raise HTTPException(
            status_code=422,
            detail=required_inputs_error_message(missing),
        )


class ObservedFileResponse(FileResponse):
    """FileResponse that logs after Starlette finishes streaming the body."""

    def __init__(
        self,
        *args,
        log_context: dict,
        started_at: float,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._reportgen_log_context = log_context
        self._reportgen_started_at = started_at

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except Exception as exc:
            duration_seconds = time.perf_counter() - self._reportgen_started_at
            download_logger.log_event(
                "report_download_failed",
                level="ERROR",
                **self._reportgen_log_context,
                duration_ms=round(duration_seconds * 1000, 3),
                error_type=type(exc).__name__,
            )
            raise

        duration_seconds = time.perf_counter() - self._reportgen_started_at
        size_bytes = int(self._reportgen_log_context.get("file_size_bytes") or 0)
        throughput_mbps = None
        if duration_seconds > 0 and size_bytes > 0:
            throughput_mbps = round(size_bytes * 8 / duration_seconds / 1_000_000, 3)
        event_type = (
            "report_download_slow"
            if duration_seconds >= DOWNLOAD_SLOW_WARN_SECONDS
            else "report_download_completed"
        )
        level = "WARNING" if event_type == "report_download_slow" else "INFO"
        download_logger.log_event(
            event_type,
            level=level,
            **self._reportgen_log_context,
            duration_ms=round(duration_seconds * 1000, 3),
            throughput_mbps=throughput_mbps,
            slow_threshold_seconds=DOWNLOAD_SLOW_WARN_SECONDS,
        )


def _round_seconds(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except Exception:
        return None


def _download_request_context(request: Request) -> dict:
    headers = request.headers
    return {
        "method": request.method,
        "client_host": request.client.host if request.client else None,
        "range_header": headers.get("range"),
        "cf_ray": headers.get("cf-ray"),
        "user_agent": (headers.get("user-agent") or "")[:160] or None,
    }


def _task_download_context(task: Task) -> dict:
    seconds_since_completed = None
    if task.completed_at:
        completed_at = task.completed_at
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        seconds_since_completed = (datetime.now(timezone.utc) - completed_at).total_seconds()
    return {
        "task_id": task.id,
        "task_type": task.task_type,
        "task_status": task.status,
        "project_type": task.project_type,
        "task_duration_seconds": _round_seconds(task.duration_seconds),
        "seconds_since_completed": _round_seconds(seconds_since_completed),
    }


def _observed_file_response(
    *,
    path: Path,
    download_filename: str,
    media_type: str,
    download_kind: str,
    task: Task,
    request: Request,
    extra_context: Optional[dict] = None,
    db: Optional[Session] = None,
) -> FileResponse:
    started_at = time.perf_counter()
    stat_result = path.stat()
    context = {
        **_task_download_context(task),
        **_download_request_context(request),
        "download_kind": download_kind,
        "file_size_bytes": stat_result.st_size,
        "file_size_mb": round(stat_result.st_size / 1024 / 1024, 3),
    }
    if extra_context:
        context.update(extra_context)

    download_logger.log_event("report_download_started", **context)
    headers = {
        "X-ReportGen-Task-Id": task.id,
        "X-ReportGen-Download-Kind": download_kind,
        "X-ReportGen-Download-Bytes": str(stat_result.st_size),
        "X-ReportGen-Download-Retryable": "true",
        "Cache-Control": "private, no-store",
        "Accept-Ranges": "bytes",
        "X-Content-Type-Options": "nosniff",
    }
    prepare_duration_ms = context.get("prepare_duration_ms")
    if prepare_duration_ms is not None:
        headers["X-ReportGen-Prepare-Duration-Ms"] = str(prepare_duration_ms)
    if task.duration_seconds is not None:
        headers["X-ReportGen-Task-Duration-Seconds"] = str(_round_seconds(task.duration_seconds))
    if db is not None and request.method.upper() != "HEAD":
        record_audit_event(
            db,
            action="report.download_requested",
            resource_type="task",
            resource_id=task.id,
            request=request,
            details={
                "download_kind": download_kind,
                "file_index": context.get("file_index"),
                "file_size_bytes": stat_result.st_size,
                "file_size_mb": round(stat_result.st_size / 1024 / 1024, 3),
                "include_failed": context.get("include_failed"),
                "item_count": context.get("item_count"),
                "project_type": task.project_type,
                "qa_filter": context.get("qa_filter"),
                "task_status": task.status,
                "task_type": task.task_type,
            },
        )
    return ObservedFileResponse(
        path=str(path),
        filename=download_filename,
        media_type=media_type,
        stat_result=stat_result,
        headers=headers,
        log_context=context,
        started_at=started_at,
    )


def _complete_file_generation_task(
    *,
    task_id: str,
    stored_path: str,
    output_dir: str,
    clinical_payload: dict,
    project_type: Optional[str],
    project_name: Optional[str],
    template_name: Optional[str],
    strict_mode: bool,
    template_contract_mode: str,
    reference_gate_mode: str = "available",
    qa_visual_render: Optional[str],
    qa_visual_render_required: Optional[bool],
    qa_visual_render_dpi: Optional[int],
    qa_visual_render_timeout_seconds: Optional[int],
    bridge: ReportGenBridge,
) -> None:
    """Complete a file-based report task after the request has returned."""
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        db.close()
        return
    if task.status == "cancelled":
        db.close()
        return

    task.status = "running"
    task.started_at = task.started_at or utc_now_naive()
    db.commit()

    try:
        result = run_generate_report_with_timeout(
            bridge,
            excel_path=stored_path,
            output_dir=output_dir,
            template_name=template_name,
            clinical_info=clinical_payload,
            project_type=project_type,
            project_name=project_name,
            strict_mode=strict_mode,
            template_contract_mode=template_contract_mode,
            qa_visual_render=qa_visual_render,
            qa_visual_render_required=qa_visual_render_required,
            qa_visual_render_dpi=qa_visual_render_dpi,
            qa_visual_render_timeout_seconds=qa_visual_render_timeout_seconds,
        )

        success = result.get("success", False)
        task.status = "completed" if success else "failed"
        task.completed_files = 1 if success else 0
        task.failed_files = 0 if success else 1
        task.output_path = result.get("output_file")
        task.duration_seconds = result.get("duration")
        warnings = list(result.get("warnings", []) or [])
        if success and task.output_path:
            try:
                _run_auto_reference_diff_with_gate(
                    db,
                    task,
                    reference_gate_mode=reference_gate_mode,
                )
            except Exception as exc:
                warnings.append(f"自动基准对比失败: {exc}")
        task.errors = json.dumps(result.get("errors", []), ensure_ascii=False)
        task.warnings = json.dumps(warnings, ensure_ascii=False)
        task.completed_at = utc_now_naive()
        db.commit()
    except Exception as exc:
        task.status = "failed"
        task.failed_files = 1
        task.errors = json.dumps([str(exc)], ensure_ascii=False)
        task.completed_at = utc_now_naive()
        db.commit()
    finally:
        db.close()


def _qa_sidecar_path(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    return Path(output_path).with_suffix(".qa.json")


def _field_provenance_sidecar_path(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    return Path(output_path).with_suffix(".field_provenance.json")


def _stage_results_sidecar_path(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    return Path(output_path).with_suffix(".stage_results.json")


def _report_summary_sidecar_path(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    return Path(output_path).with_suffix(".summary.json")


def _batch_report_path(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    return Path(output_path) / "batch_report.json"


def _fallback_stage_results_sidecar_path(task_id: str) -> Path:
    return settings.report_dir / task_id / "generation.stage_results.json"


def _load_qa_summary(
    output_path: Optional[str],
) -> tuple[Optional[str], Optional[str], list[dict]]:
    qa_path = _qa_sidecar_path(output_path)
    if not qa_path or not qa_path.exists():
        return None, None, []
    try:
        payload = json.loads(qa_path.read_text(encoding="utf-8"))
    except Exception:
        return str(qa_path), None, []
    return str(qa_path), payload.get("status"), payload.get("issues") or []


def _load_stage_results(
    output_path: Optional[str],
    task_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], list[dict]]:
    stage_path = _stage_results_sidecar_path(output_path)
    if (not stage_path or not stage_path.exists()) and task_id:
        stage_path = _fallback_stage_results_sidecar_path(task_id)
    if not stage_path or not stage_path.exists():
        return None, None, []
    try:
        payload = json.loads(stage_path.read_text(encoding="utf-8"))
    except Exception:
        return str(stage_path), None, []
    return (
        str(stage_path),
        payload.get("generation_id"),
        payload.get("stage_results") or [],
    )


def _load_json_list(value: Optional[str]) -> list:
    if not value:
        return []
    try:
        payload = json.loads(value)
    except Exception:
        return [str(value)]
    return payload if isinstance(payload, list) else [payload]


def _load_json_dict(value: Optional[str]) -> dict:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _batch_status_counts(db: Session, task_id: str) -> dict[str, int]:
    counts = empty_batch_status_counts()
    rows = (
        db.query(TaskResult.status, func.count(TaskResult.id))
        .filter(TaskResult.task_id == task_id)
        .group_by(TaskResult.status)
        .all()
    )
    for status, count in rows:
        counts[status or "pending"] = count
    return counts


REVIEW_STATUSES = {
    "draft": "待审核",
    "reviewed": "已审核",
    "delivered": "已交付",
    "rejected": "退回修改",
}
CONTROLLED_PILOT_PROJECT_TYPES = {"lung_329_pdl1", "lung_588_pdl1"}


def _require_override_permission(override_gate: bool, user: User) -> None:
    if override_gate and user.role not in TASK_PRIVILEGED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="仅复核人或管理员可显式放行未通过门禁的报告",
        )


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


def _effective_visual_gate_options(
    reference_gate_mode: str,
    qa_visual_render: str | None,
    qa_visual_render_required: bool | None,
) -> tuple[str | None, bool | None]:
    if diff_svc.reference_is_required(reference_gate_mode):
        return "all", True
    return qa_visual_render, qa_visual_render_required


def _run_auto_reference_diff_with_gate(
    db: Session,
    task: Task,
    *,
    reference_gate_mode: str,
) -> dict | None:
    required = diff_svc.reference_is_required(reference_gate_mode)
    try:
        return diff_svc.run_auto_reference_diff(
            db,
            task,
            fail_on="fail",
            max_samples=50,
            require_reference=required,
        )
    except Exception as exc:
        if not required:
            raise
        return diff_svc.write_reference_gate_failure(
            task,
            code="REFERENCE_GATE_EXECUTION_FAILED",
            message=f"金标准验收门禁执行失败: {exc}",
            task_id=task.id,
        )


def _task_artifact_dir(task: Task) -> Path:
    if task.task_type == "batch":
        return Path(task.output_path) if task.output_path else settings.report_dir / task.id
    if task.output_path:
        return Path(task.output_path).parent
    return settings.report_dir / task.id


def _review_state_path(task: Task) -> Path:
    return _task_artifact_dir(task) / "review_state.json"


def _default_review_state(task: Task) -> dict:
    return {
        "schema_version": "1.0",
        "task_id": task.id,
        "status": "draft",
        "status_label": REVIEW_STATUSES["draft"],
        "updated_at": None,
        "updated_by": None,
        "note": "",
        "history": [],
    }


def _load_review_state(task: Task) -> dict:
    path = _review_state_path(task)
    if not path.exists():
        return _default_review_state(task)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_review_state(task)
    if not isinstance(payload, dict):
        return _default_review_state(task)
    status = payload.get("status") or "draft"
    payload["status_label"] = REVIEW_STATUSES.get(status, status)
    payload.setdefault("history", [])
    return payload


def _write_review_state(task: Task, payload: dict) -> dict:
    path = _review_state_path(task)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["status_label"] = REVIEW_STATUSES.get(payload.get("status"), payload.get("status"))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _gate_issue(level: str, code: str, message: str, scope: str = "task") -> dict:
    return {
        "level": level,
        "code": code,
        "message": message,
        "scope": scope,
    }


def _is_required_field_warning(message: object) -> bool:
    text = str(message or "")
    return "缺失必填字段" in text or "missing required" in text.lower()


def _controlled_pilot_review_required(
    project_type: object,
    review_status: object,
) -> bool:
    return str(project_type or "").strip().lower() in CONTROLLED_PILOT_PROJECT_TYPES and str(
        review_status or ""
    ).strip().lower() not in {"reviewed", "delivered"}


def _qa_has_full_visual_pass(qa_path: str | None) -> bool:
    if not qa_path:
        return False
    try:
        payload = json.loads(Path(qa_path).read_text(encoding="utf-8"))
    except Exception:
        return False
    visual = (payload.get("checks") or {}).get("visual_render") or {}
    renderer = visual.get("renderer_fingerprint") or {}
    required_renderer_fields = (
        "platform",
        "machine",
        "engine",
        "engine_version",
        "profile_mode",
        "pdf_renderer",
        "pdf_renderer_version",
        "font_substitution_profile",
        "font_substitution_profile_sha256",
    )
    fingerprint_complete = all(
        str(renderer.get(field) or "").strip() not in {"", "none", "unavailable"}
        for field in required_renderer_fields
    )
    font_profile_hash_valid = bool(
        re.fullmatch(
            r"[0-9a-f]{64}",
            str(renderer.get("font_substitution_profile_sha256") or "").lower(),
        )
    )
    return bool(
        visual.get("status") == "PASS"
        and visual.get("requested") == "all"
        and visual.get("required") is True
        and renderer.get("platform") == "Linux"
        and renderer.get("profile_mode") == "isolated"
        and fingerprint_complete
        and font_profile_hash_valid
    )


def _quality_gate_payload(task: Task, db: Session) -> dict:
    issues: list[dict] = []
    diff_summary = diff_svc.report_diff_summary(task.output_path)
    task_errors = _load_json_list(task.errors)
    task_warnings = _load_json_list(task.warnings)

    task_is_active = (
        task.status in BATCH_ACTIVE_STATUSES
        if task.task_type == "batch"
        else task.status in {"pending", "running"}
    )
    if task_is_active:
        issues.append(_gate_issue("blocker", "TASK_NOT_FINISHED", "任务仍在生成中，不能进入交付。"))
    if task.status == "cancelled":
        issues.append(_gate_issue("blocker", "TASK_CANCELLED", "任务已取消。"))
    if task_errors:
        issues.append(
            _gate_issue(
                "blocker",
                "TASK_ERRORS",
                "任务存在错误: " + "；".join(str(item) for item in task_errors[:3]),
            )
        )
    review_state = _load_review_state(task)
    if _controlled_pilot_review_required(
        task.project_type,
        review_state.get("status"),
    ):
        issues.append(
            _gate_issue(
                "blocker",
                "CONTROLLED_PILOT_REVIEW_REQUIRED",
                "肺癌588处于受控试运行，必须先由复核人标记“已审核”后才能交付。",
            )
        )

    if task.task_type == "batch":
        rows = (
            db.query(TaskResult)
            .filter(TaskResult.task_id == task.id)
            .order_by(TaskResult.file_index.asc())
            .all()
        )
        counts = empty_batch_status_counts()
        for row in rows:
            counts[row.status or "pending"] = counts.get(row.status or "pending", 0) + 1

        if not rows:
            issues.append(_gate_issue("blocker", "BATCH_EMPTY", "批量任务没有逐文件结果。"))
        pending_count = pending_file_count(counts)
        working_count = working_file_count(counts)
        if working_count or pending_count:
            issues.append(
                _gate_issue(
                    "blocker",
                    "BATCH_NOT_FINISHED",
                    f"批量任务仍有 {working_count} 个处理中、{pending_count} 个待执行。",
                )
            )
        if counts.get("failed"):
            issues.append(
                _gate_issue(
                    "blocker",
                    "BATCH_HAS_FAILURES",
                    f"批量任务有 {counts['failed']} 个失败文件。",
                )
            )
        if counts.get("cancelled"):
            issues.append(
                _gate_issue(
                    "blocker",
                    "BATCH_HAS_CANCELLED",
                    f"批量任务有 {counts['cancelled']} 个已取消文件。",
                )
            )

        for row in rows:
            scope = f"file:{row.file_index}"
            row_warnings = _load_json_list(row.warnings)
            validation = _load_json_dict(row.validation_summary)
            if row.status != "completed":
                issues.append(
                    _gate_issue(
                        "blocker",
                        "BATCH_ROW_NOT_COMPLETED",
                        f"{row.excel_filename} 状态为 {row.status}。",
                        scope,
                    )
                )
                continue
            if not row.output_path or not Path(row.output_path).exists():
                issues.append(
                    _gate_issue(
                        "blocker",
                        "OUTPUT_MISSING",
                        f"{row.excel_filename} 报告文件不存在。",
                        scope,
                    )
                )
            qa_status = validation.get("qa_status")
            if qa_status == "FAIL":
                issues.append(
                    _gate_issue(
                        "blocker",
                        "QA_FAIL",
                        f"{row.excel_filename} QA 状态为 FAIL。",
                        scope,
                    )
                )
            elif qa_status == "WARN":
                issues.append(
                    _gate_issue(
                        "warning",
                        "QA_WARN",
                        f"{row.excel_filename} QA 状态为 WARN。",
                        scope,
                    )
                )
            elif not qa_status:
                issues.append(
                    _gate_issue(
                        "warning",
                        "QA_MISSING",
                        f"{row.excel_filename} 未记录 QA 状态。",
                        scope,
                    )
                )
            for warning in row_warnings:
                if _is_required_field_warning(warning):
                    issues.append(
                        _gate_issue("blocker", "REQUIRED_FIELD_MISSING", str(warning), scope)
                    )
                else:
                    issues.append(_gate_issue("warning", "ROW_WARNING", str(warning), scope))
        metrics = {
            "total_files": task.total_files,
            "completed_files": task.completed_files,
            "failed_files": task.failed_files,
            "status_counts": counts,
        }
    else:
        if task.status != "completed":
            issues.append(
                _gate_issue("blocker", "TASK_NOT_COMPLETED", f"单份报告任务状态为 {task.status}。")
            )
        if not task.output_path or not Path(task.output_path).exists():
            issues.append(_gate_issue("blocker", "OUTPUT_MISSING", "报告文件不存在。"))
        qa_file, qa_status, qa_issues = _load_qa_summary(task.output_path)
        if qa_status == "FAIL":
            issues.append(_gate_issue("blocker", "QA_FAIL", "QA 状态为 FAIL。"))
        elif qa_status == "WARN":
            issues.append(_gate_issue("warning", "QA_WARN", "QA 状态为 WARN。"))
        elif not qa_status:
            issues.append(_gate_issue("warning", "QA_MISSING", "未找到 QA 状态。"))
        for issue in qa_issues[:20]:
            level = "blocker" if issue.get("level") == "error" else "warning"
            issues.append(
                _gate_issue(
                    level,
                    issue.get("code") or "QA_ISSUE",
                    issue.get("message") or str(issue),
                )
            )
        metrics = {
            "qa_status": qa_status,
            "qa_report_file": qa_file,
        }

    if diff_summary.get("diff_gate_passed") is False:
        issues.append(_gate_issue("blocker", "DIFF_GATE_FAILED", "基准报告 Diff 门禁未通过。"))
    elif diff_summary.get("diff_status") == "FAIL":
        issues.append(_gate_issue("blocker", "DIFF_FAIL", "基准报告 Diff 状态为 FAIL。"))
    elif diff_summary.get("diff_status") == "WARN":
        issues.append(_gate_issue("warning", "DIFF_WARN", "基准报告 Diff 状态为 WARN。"))
    elif not diff_summary.get("diff_status"):
        issues.append(_gate_issue("warning", "DIFF_NOT_RUN", "未找到基准报告 Diff 结果。"))

    if diff_summary.get("diff_require_reference"):
        if task.task_type == "batch":
            for row in rows:
                if row.status != "completed":
                    continue
                validation = _load_json_dict(row.validation_summary)
                if not _qa_has_full_visual_pass(validation.get("qa_report_file")):
                    issues.append(
                        _gate_issue(
                            "blocker",
                            "GOLDEN_VISUAL_QA_REQUIRED",
                            f"{row.excel_filename} 未完成 Linux 全页阻断式视觉 QA。",
                            f"file:{row.file_index}",
                        )
                    )
        elif not _qa_has_full_visual_pass(metrics.get("qa_report_file")):
            issues.append(
                _gate_issue(
                    "blocker",
                    "GOLDEN_VISUAL_QA_REQUIRED",
                    "金标准验收报告未完成 Linux 全页阻断式视觉 QA。",
                )
            )

    for warning in task_warnings:
        if _is_required_field_warning(warning):
            issues.append(_gate_issue("blocker", "REQUIRED_FIELD_MISSING", str(warning)))
        else:
            issues.append(_gate_issue("warning", "TASK_WARNING", str(warning)))

    blocker_count = sum(1 for issue in issues if issue["level"] == "blocker")
    warning_count = sum(1 for issue in issues if issue["level"] == "warning")
    return {
        "schema_version": "1.0",
        "task_id": task.id,
        "task_type": task.task_type,
        "status": "PASS" if blocker_count == 0 else "BLOCKED",
        "passed": blocker_count == 0,
        "generated_at": utc_now_naive().isoformat(),
        "blockers": blocker_count,
        "warnings": warning_count,
        "issues": issues,
        "metrics": metrics,
        "diff": {
            key: diff_summary.get(key)
            for key in (
                "diff_status",
                "diff_gate_passed",
                "diff_require_reference",
                "diff_reference_id",
                "diff_reference_name",
                "diff_report_file",
                "diff_markdown_file",
            )
        },
        "review": review_state,
    }


def _add_zip_file(zf: zipfile.ZipFile, path: Optional[Path], arcname: str) -> None:
    if path and path.exists() and path.is_file():
        zf.write(path, arcname)


def _artifact_sidecars(output_path: Optional[str]) -> list[tuple[Optional[Path], str]]:
    if not output_path:
        return []
    path = Path(output_path)
    return [
        (_report_summary_sidecar_path(output_path), f"summaries/{path.stem}.summary.json"),
        (_qa_sidecar_path(output_path), f"qa/{path.stem}.qa.json"),
        (
            _field_provenance_sidecar_path(output_path),
            f"field_provenance/{path.stem}.field_provenance.json",
        ),
        (_stage_results_sidecar_path(output_path), f"stage_results/{path.stem}.stage_results.json"),
    ]


def _visual_render_dir(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    path = Path(output_path)
    return path.parent / "rendered_pages" / path.stem


def _visual_render_page_path(output_path: Optional[str], filename: str) -> Optional[Path]:
    render_dir = _visual_render_dir(output_path)
    if not render_dir:
        return None
    candidate = (render_dir / filename).resolve()
    try:
        candidate.relative_to(render_dir.resolve())
    except ValueError:
        return None
    return candidate


def _report_diff_dir(output_path: Optional[str]) -> Optional[Path]:
    return diff_svc.report_diff_dir(output_path)


def _report_diff_artifact_path(output_path: Optional[str], filename: str) -> Optional[Path]:
    return diff_svc.report_diff_artifact_path(output_path, filename)


def _render_error_payload(exc: Exception) -> dict:
    payload = {
        "error": str(exc),
        "stage": getattr(exc, "stage", None),
    }
    command = getattr(exc, "command", None)
    if command:
        payload["command"] = list(command)
    stdout = getattr(exc, "stdout", None)
    stderr = getattr(exc, "stderr", None)
    if stdout:
        payload["stdout_tail"] = str(stdout)[-2000:]
    if stderr:
        payload["stderr_tail"] = str(stderr)[-2000:]
    return payload


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
    """Fill missing form values from the runtime patient registry/ops lookup."""
    payload = dict(clinical_info or {})
    sample_id = str(payload.get("sample_id") or payload.get("样本编号") or "").strip()
    lookup_id = str(lookup_sample_id or "").strip() or sample_id
    if not lookup_id:
        return clinical_svc.fill_missing_report_date(payload)
    if not sample_id and lookup_id:
        payload["sample_id"] = lookup_id
    enrichment = clinical_svc.enrich_patient(lookup_id, project_type=project_type)
    payload = clinical_svc.merge_enrichment_into_values(payload, enrichment)
    return clinical_svc.fill_missing_report_date(payload)


def _apply_pdl1_upload_receipt(
    clinical_payload: dict,
    project_type: Optional[str],
    *,
    owner_user_id: int,
) -> dict:
    """Normalize trusted PD-L1 image provenance before input preflight."""

    try:
        return clinical_svc.apply_pdl1_image_metadata(
            clinical_payload,
            project_type,
            owner_user_id=owner_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _compact_filename_part(value: object, fallback: str) -> str:
    text = "" if value is None else str(value).strip()
    text = re.sub(r"\s+", "", text)
    if text.lower() in {"", "-", "--", "未知", "unknown", "none", "null", "nan", "n/a", "na"}:
        text = ""
    return safe_filename(text or fallback, replacement="_")


def _normalize_project_filename_part(
    project_name: Optional[str], project_type: Optional[str]
) -> str:
    text = project_name or _panel_display_name(project_type) or "基因检测"
    text = str(text).strip().replace("＋", "+")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"检测项目$", "", text)
    text = re.sub(r"MSI", "msi", text, flags=re.IGNORECASE)
    text = re.sub(r"PD[-_\\s]?L1", "pd-l1", text, flags=re.IGNORECASE)
    return _compact_filename_part(text, "基因检测")


def _panel_display_name(project_type: Optional[str]) -> Optional[str]:
    if not project_type:
        return None
    panel_yaml = settings.upstream_root / "panels" / project_type / "panel.yaml"
    if not panel_yaml.exists():
        panel_yaml = Path(__file__).resolve().parents[3] / "panels" / project_type / "panel.yaml"
    if not panel_yaml.exists():
        return None
    try:
        payload = yaml.safe_load(panel_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    display_name = payload.get("display_name")
    return str(display_name).strip() if display_name else None


def _clinical_snapshot(task: Task) -> dict:
    if not task.clinical_info_snapshot:
        return {}
    try:
        payload = json.loads(task.clinical_info_snapshot)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _business_report_filename(
    *,
    clinical_info: Optional[dict],
    project_type: Optional[str],
    project_name: Optional[str],
    output_path: Optional[str] = None,
    revision_label: Optional[str] = None,
) -> str:
    info = clinical_info or {}
    patient_name = info.get("patient_name") or info.get("患者姓名") or info.get("姓名")
    sample_id = info.get("sample_id") or info.get("报告编号") or info.get("样本号")
    cancer = (
        info.get("cancer_type")
        or info.get("clinical_diagnosis")
        or info.get("diagnosis")
        or info.get("临床诊断")
        or info.get("癌种")
    )
    resolved_project_name = (
        project_name or info.get("project_name") or info.get("项目名称") or info.get("检测项目")
    )

    if not any([patient_name, sample_id, cancer, resolved_project_name, project_type]):
        return Path(output_path).name if output_path else "report.docx"

    patient_part = _compact_filename_part(patient_name, "患者未填")
    cancer_part = _compact_filename_part(cancer, "癌种未填")
    project_part = _normalize_project_filename_part(resolved_project_name, project_type)
    org_part = _compact_filename_part(settings.report_filename_org_code, "mljy")
    sample_part = _compact_filename_part(sample_id, "编号未填").lower()
    revision_part = _compact_filename_part(
        revision_label or settings.report_filename_revision_label,
        "修改版",
    )
    return (
        f"{patient_part}-{cancer_part}-{project_part}-{org_part}-{sample_part}-{revision_part}.docx"
    )


def _get_single_report_task(task_id: str, db: Session) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.task_type != "single":
        raise HTTPException(status_code=400, detail="报告对比仅支持单份任务")
    if not task.output_path:
        raise HTTPException(status_code=404, detail="报告文件不存在")
    output_path = Path(task.output_path)
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="报告文件已被删除")
    return task


def _get_report_task_with_output(task_id: str, db: Session) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.output_path:
        raise HTTPException(status_code=404, detail="报告文件不存在")
    output_path = Path(task.output_path)
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="报告文件已被删除")
    return task


def _inline_docx_payload(
    output_file: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    if not output_file:
        return None, None
    path = Path(output_file)
    if not path.exists():
        return path.name, None
    return path.name, base64.b64encode(path.read_bytes()).decode("ascii")


def _generate_response_from_result(
    *,
    task_id: str,
    result: dict,
    warnings: list[str],
    diff_summary: dict,
    auto_diff_ran: bool,
    clinical_info: Optional[dict] = None,
    project_type: Optional[str] = None,
    project_name: Optional[str] = None,
    include_inline_file: bool = False,
) -> GenerateResponse:
    output_filename = None
    output_file_base64 = None
    controlled_pilot = str(project_type or "").strip().lower() in CONTROLLED_PILOT_PROJECT_TYPES
    if include_inline_file and not controlled_pilot and result.get("success", False):
        _physical_filename, output_file_base64 = _inline_docx_payload(result.get("output_file"))
        output_filename = _business_report_filename(
            clinical_info=clinical_info,
            project_type=project_type,
            project_name=project_name,
            output_path=result.get("output_file"),
        )

    return GenerateResponse(
        task_id=task_id,
        success=result.get("success", False),
        output_file=result.get("output_file"),
        output_filename=output_filename,
        output_file_base64=output_file_base64,
        field_provenance_file=result.get("field_provenance_file"),
        qa_report_file=result.get("qa_report_file"),
        report_summary_file=result.get("report_summary_file"),
        qa_status=result.get("qa_status"),
        qa_issues=(result.get("qa_report") or {}).get("issues") or [],
        visual_render=((result.get("qa_report") or {}).get("checks") or {}).get("visual_render"),
        panel_package_validation=result.get("panel_package_validation"),
        generation_id=result.get("generation_id"),
        stage_results=result.get("stage_results") or [],
        stage_results_file=result.get("stage_results_file"),
        diff_status=diff_summary.get("diff_status"),
        diff_gate_passed=diff_summary.get("diff_gate_passed"),
        diff_reference_id=diff_summary.get("diff_reference_id"),
        diff_reference_name=diff_summary.get("diff_reference_name"),
        diff_auto_ran=auto_diff_ran,
        duration_seconds=result.get("duration"),
        errors=result.get("errors", []),
        warnings=warnings,
    )


@router.post("/generate", response_model=ApiResponse[GenerateResponse])
def generate_report(
    req: GenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
    current_user: User = Depends(require_user),
):
    """Generate a single report (synchronous, 2-5s)."""
    reference_gate_mode = _validated_reference_gate_mode(
        req.reference_gate_mode,
        current_user,
    )
    qa_visual_render, qa_visual_render_required = _effective_visual_gate_options(
        reference_gate_mode,
        req.qa_visual_render,
        req.qa_visual_render_required,
    )
    upload = db.query(Upload).filter(Upload.id == req.upload_id).first()
    if not upload or not user_can_access_upload(current_user, upload):
        raise HTTPException(status_code=404, detail="上传记录不存在")
    _raise_if_project_type_disabled(bridge, req.project_type)

    task_id = str(uuid.uuid4())
    output_dir = ensure_report_dir(task_id)
    try:
        excel_data = bridge.read_excel(upload.stored_path)
        identity = resolve_project_identity(
            bridge,
            excel_path=upload.stored_path,
            excel_data=excel_data,
            requested_project_type=req.project_type or upload.detected_project_type,
            requested_project_name=req.project_name or upload.detected_project_name,
            clinical_project_name=(
                (req.clinical_info or {}).get("project_name")
                or (req.clinical_info or {}).get("项目名称")
                or (req.clinical_info or {}).get("检测项目")
            ),
        )
    except ProjectIdentityConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    effective_project_type = identity.project_type
    effective_project_name = identity.project_name
    _raise_if_project_type_disabled(bridge, effective_project_type)
    clinical_payload = _enrich_clinical_payload(
        req.clinical_info,
        effective_project_type,
        lookup_sample_id=clinical_svc.project_code_from_filename(upload.original_filename),
    )
    clinical_payload = _apply_pdl1_upload_receipt(
        clinical_payload,
        effective_project_type,
        owner_user_id=current_user.id,
    )
    clinical_payload.pop("项目名称", None)
    clinical_payload.pop("检测项目", None)
    if effective_project_name:
        clinical_payload["project_name"] = effective_project_name
    _raise_required_inputs_if_missing(
        bridge,
        excel_path=upload.stored_path,
        clinical_payload=clinical_payload,
        project_type=effective_project_type,
        project_name=effective_project_name,
        excel_data=excel_data,
    )

    # Create task record
    task = Task(
        id=task_id,
        user_id=current_user.id,
        upload_id=req.upload_id,
        task_type="single",
        status="running",
        project_type=effective_project_type,
        clinical_info_snapshot=(
            json.dumps(clinical_payload, ensure_ascii=False) if clinical_payload else None
        ),
        started_at=utc_now_naive(),
    )
    db.add(task)
    db.commit()
    record_audit_event(
        db,
        action="report.generate_requested",
        resource_type="task",
        resource_id=task_id,
        request=request,
        details={
            "source": "generate",
            "task_type": "single",
            "project_type": effective_project_type,
            "template_name": req.template_name,
            "strict_mode": req.strict_mode,
            "template_contract_mode": req.template_contract_mode,
            "reference_gate_mode": reference_gate_mode,
            "qa_visual_render": qa_visual_render,
            "status": "running",
        },
    )

    try:
        result = run_generate_report_with_timeout(
            bridge,
            excel_path=upload.stored_path,
            output_dir=str(output_dir),
            template_name=req.template_name,
            clinical_info=clinical_payload,
            project_type=effective_project_type,
            project_name=effective_project_name,
            strict_mode=req.strict_mode,
            template_contract_mode=req.template_contract_mode,
            qa_visual_render=qa_visual_render,
            qa_visual_render_required=qa_visual_render_required,
            qa_visual_render_dpi=req.qa_visual_render_dpi,
            qa_visual_render_timeout_seconds=req.qa_visual_render_timeout_seconds,
        )

        success = result.get("success", False)
        task.status = "completed" if success else "failed"
        task.output_path = result.get("output_file")
        task.duration_seconds = result.get("duration")
        warnings = list(result.get("warnings", []) or [])
        auto_diff_result = None
        if success and task.output_path:
            try:
                auto_diff_result = _run_auto_reference_diff_with_gate(
                    db,
                    task,
                    reference_gate_mode=reference_gate_mode,
                )
            except Exception as exc:
                warnings.append(f"自动基准对比失败: {exc}")
        task.errors = json.dumps(result.get("errors", []), ensure_ascii=False)
        task.warnings = json.dumps(warnings, ensure_ascii=False)
        task.completed_at = utc_now_naive()
        db.commit()
        diff_summary = diff_svc.report_diff_summary(task.output_path)

        return ApiResponse(
            data=_generate_response_from_result(
                task_id=task_id,
                result=result,
                warnings=warnings,
                diff_summary=diff_summary,
                auto_diff_ran=auto_diff_result is not None,
                clinical_info=clinical_payload,
                project_type=effective_project_type,
                project_name=effective_project_name,
            )
        )
    except Exception as e:
        task.status = "failed"
        task.errors = json.dumps([str(e)], ensure_ascii=False)
        task.completed_at = utc_now_naive()
        db.commit()
        return ApiResponse(
            success=False,
            data=GenerateResponse(
                task_id=task_id,
                success=False,
                errors=[str(e)],
            ),
            error=str(e),
        )


@router.post("/generate-file", response_model=ApiResponse[GenerateResponse])
def generate_report_from_file(
    request: Request,
    file: UploadFile = File(...),
    clinical_info: str = Form("{}"),
    project_type: Optional[str] = Form(None),
    project_name: Optional[str] = Form(None),
    template_name: Optional[str] = Form(None),
    strict_mode: bool = Form(False),
    template_contract_mode: str = Form("warn"),
    reference_gate_mode: str = Form("available"),
    qa_visual_render: Optional[str] = Form(None),
    qa_visual_render_required: Optional[bool] = Form(None),
    qa_visual_render_dpi: Optional[int] = Form(None),
    qa_visual_render_timeout_seconds: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
    current_user: User = Depends(require_user),
):
    """Generate a report from Excel in one request for stateless previews."""
    reference_gate_mode = _validated_reference_gate_mode(
        reference_gate_mode,
        current_user,
    )
    qa_visual_render, qa_visual_render_required = _effective_visual_gate_options(
        reference_gate_mode,
        qa_visual_render,
        qa_visual_render_required,
    )
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少 Excel 文件名")
    original_filename = safe_client_filename(file.filename, "upload.xlsx")
    if not original_filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式文件")

    try:
        clinical_payload = json.loads(clinical_info or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"临床信息不是合法 JSON: {exc}") from exc
    if not isinstance(clinical_payload, dict):
        raise HTTPException(status_code=400, detail="临床信息必须是 JSON 对象")
    _raise_if_project_type_disabled(bridge, project_type)

    _upload_id, stored_path, _file_size = save_upload(file)
    excel_data = bridge.read_excel(str(stored_path))
    try:
        identity = resolve_project_identity(
            bridge,
            excel_path=str(Path(stored_path).parent / original_filename),
            excel_data=excel_data,
            requested_project_type=project_type,
            requested_project_name=project_name,
            clinical_project_name=(
                clinical_payload.get("project_name")
                or clinical_payload.get("项目名称")
                or clinical_payload.get("检测项目")
            ),
        )
    except ProjectIdentityConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    detected_project_type = identity.project_type
    detected_project_name = identity.project_name
    _raise_if_project_type_disabled(bridge, detected_project_type)
    clinical_payload = _enrich_clinical_payload(
        clinical_payload,
        detected_project_type,
        lookup_sample_id=clinical_svc.project_code_from_filename(original_filename),
    )
    clinical_payload = _apply_pdl1_upload_receipt(
        clinical_payload,
        detected_project_type,
        owner_user_id=current_user.id,
    )
    clinical_payload.pop("项目名称", None)
    clinical_payload.pop("检测项目", None)
    if detected_project_name:
        clinical_payload["project_name"] = detected_project_name
    _raise_required_inputs_if_missing(
        bridge,
        excel_path=str(stored_path),
        clinical_payload=clinical_payload,
        project_type=detected_project_type,
        project_name=detected_project_name,
        excel_data=excel_data,
    )

    task_id = str(uuid.uuid4())
    output_dir = ensure_report_dir(task_id)
    task = Task(
        id=task_id,
        user_id=current_user.id,
        task_type="single",
        status="running",
        project_type=detected_project_type,
        clinical_info_snapshot=(
            json.dumps(clinical_payload, ensure_ascii=False) if clinical_payload else None
        ),
        started_at=utc_now_naive(),
    )
    db.add(task)
    db.commit()
    record_audit_event(
        db,
        action="report.generate_file_requested",
        resource_type="task",
        resource_id=task_id,
        request=request,
        details={
            "source": "generate-file",
            "task_type": "single",
            "project_type": detected_project_type,
            "template_name": template_name,
            "strict_mode": strict_mode,
            "template_contract_mode": template_contract_mode,
            "reference_gate_mode": reference_gate_mode,
            "qa_visual_render": qa_visual_render,
            "status": "running",
        },
    )

    try:
        result = run_generate_report_with_timeout(
            bridge,
            excel_path=str(stored_path),
            output_dir=str(output_dir),
            template_name=template_name,
            clinical_info=clinical_payload,
            project_type=detected_project_type,
            project_name=detected_project_name,
            strict_mode=strict_mode,
            template_contract_mode=template_contract_mode,
            qa_visual_render=qa_visual_render,
            qa_visual_render_required=qa_visual_render_required,
            qa_visual_render_dpi=qa_visual_render_dpi,
            qa_visual_render_timeout_seconds=qa_visual_render_timeout_seconds,
        )

        success = result.get("success", False)
        task.status = "completed" if success else "failed"
        task.output_path = result.get("output_file")
        task.duration_seconds = result.get("duration")
        warnings = list(result.get("warnings", []) or [])
        auto_diff_result = None
        if success and task.output_path:
            try:
                auto_diff_result = _run_auto_reference_diff_with_gate(
                    db,
                    task,
                    reference_gate_mode=reference_gate_mode,
                )
            except Exception as exc:
                warnings.append(f"自动基准对比失败: {exc}")
        task.errors = json.dumps(result.get("errors", []), ensure_ascii=False)
        task.warnings = json.dumps(warnings, ensure_ascii=False)
        task.completed_at = utc_now_naive()
        db.commit()
        diff_summary = diff_svc.report_diff_summary(task.output_path)

        return ApiResponse(
            data=_generate_response_from_result(
                task_id=task_id,
                result=result,
                warnings=warnings,
                diff_summary=diff_summary,
                auto_diff_ran=auto_diff_result is not None,
                clinical_info=clinical_payload,
                project_type=detected_project_type,
                project_name=detected_project_name,
                include_inline_file=True,
            )
        )
    except Exception as e:
        task.status = "failed"
        task.errors = json.dumps([str(e)], ensure_ascii=False)
        task.completed_at = utc_now_naive()
        db.commit()
        return ApiResponse(
            success=False,
            data=GenerateResponse(
                task_id=task_id,
                success=False,
                errors=[str(e)],
            ),
            error=str(e),
        )


@router.post("/generate-file-async", response_model=ApiResponse[GenerateResponse])
def generate_report_from_file_async(
    request: Request,
    file: UploadFile = File(...),
    clinical_info: str = Form("{}"),
    project_type: Optional[str] = Form(None),
    project_name: Optional[str] = Form(None),
    template_name: Optional[str] = Form(None),
    strict_mode: bool = Form(False),
    template_contract_mode: str = Form("warn"),
    reference_gate_mode: str = Form("available"),
    qa_visual_render: Optional[str] = Form(None),
    qa_visual_render_required: Optional[bool] = Form(None),
    qa_visual_render_dpi: Optional[int] = Form(None),
    qa_visual_render_timeout_seconds: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
    current_user: User = Depends(require_user),
):
    """Start file-based report generation and return immediately."""
    reference_gate_mode = _validated_reference_gate_mode(
        reference_gate_mode,
        current_user,
    )
    qa_visual_render, qa_visual_render_required = _effective_visual_gate_options(
        reference_gate_mode,
        qa_visual_render,
        qa_visual_render_required,
    )
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少 Excel 文件名")
    original_filename = safe_client_filename(file.filename, "upload.xlsx")
    if not original_filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式文件")

    try:
        clinical_payload = json.loads(clinical_info or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"临床信息不是合法 JSON: {exc}") from exc
    if not isinstance(clinical_payload, dict):
        raise HTTPException(status_code=400, detail="临床信息必须是 JSON 对象")
    _raise_if_project_type_disabled(bridge, project_type)

    upload_id, stored_path, _file_size = save_upload(file)
    excel_data = bridge.read_excel(str(stored_path))
    try:
        identity = resolve_project_identity(
            bridge,
            excel_path=str(Path(stored_path).parent / original_filename),
            excel_data=excel_data,
            requested_project_type=project_type,
            requested_project_name=project_name,
            clinical_project_name=(
                clinical_payload.get("project_name")
                or clinical_payload.get("项目名称")
                or clinical_payload.get("检测项目")
            ),
        )
    except ProjectIdentityConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    detected_project_type = identity.project_type
    detected_project_name = identity.project_name
    _raise_if_project_type_disabled(bridge, detected_project_type)
    clinical_payload = _enrich_clinical_payload(
        clinical_payload,
        detected_project_type,
        lookup_sample_id=clinical_svc.project_code_from_filename(original_filename),
    )
    clinical_payload = _apply_pdl1_upload_receipt(
        clinical_payload,
        detected_project_type,
        owner_user_id=current_user.id,
    )
    clinical_payload.pop("项目名称", None)
    clinical_payload.pop("检测项目", None)
    if detected_project_name:
        clinical_payload["project_name"] = detected_project_name
    _raise_required_inputs_if_missing(
        bridge,
        excel_path=str(stored_path),
        clinical_payload=clinical_payload,
        project_type=detected_project_type,
        project_name=detected_project_name,
        excel_data=excel_data,
    )

    task_id = str(uuid.uuid4())
    output_dir = ensure_report_dir(task_id)
    task = Task(
        id=task_id,
        user_id=current_user.id,
        upload_id=upload_id,
        task_type="single",
        status="pending",
        project_type=detected_project_type,
        clinical_info_snapshot=(
            json.dumps(clinical_payload, ensure_ascii=False) if clinical_payload else None
        ),
    )
    request_path = write_single_generation_request(
        task_id=task_id,
        payload={
            "task_id": task_id,
            "stored_path": str(stored_path),
            "output_dir": str(output_dir),
            "clinical_payload": clinical_payload,
            "project_type": detected_project_type,
            "project_name": detected_project_name,
            "template_name": template_name,
            "strict_mode": strict_mode,
            "template_contract_mode": template_contract_mode,
            "reference_gate_mode": reference_gate_mode,
            "qa_visual_render": qa_visual_render,
            "qa_visual_render_required": qa_visual_render_required,
            "qa_visual_render_dpi": qa_visual_render_dpi,
            "qa_visual_render_timeout_seconds": qa_visual_render_timeout_seconds,
        },
    )
    task.context_json_path = str(request_path)
    db.add(task)
    db.commit()
    record_audit_event(
        db,
        action="report.generate_async_queued",
        resource_type="task",
        resource_id=task_id,
        request=request,
        details={
            "source": "generate-file-async",
            "task_type": "single",
            "project_type": detected_project_type,
            "template_name": template_name,
            "strict_mode": strict_mode,
            "template_contract_mode": template_contract_mode,
            "reference_gate_mode": reference_gate_mode,
            "qa_visual_render": qa_visual_render,
            "status": "pending",
        },
    )

    submit_generation_job(
        _complete_file_generation_task,
        task_id=task_id,
        stored_path=str(stored_path),
        output_dir=str(output_dir),
        clinical_payload=clinical_payload,
        project_type=detected_project_type,
        project_name=detected_project_name,
        template_name=template_name,
        strict_mode=strict_mode,
        template_contract_mode=template_contract_mode,
        reference_gate_mode=reference_gate_mode,
        qa_visual_render=qa_visual_render,
        qa_visual_render_required=qa_visual_render_required,
        qa_visual_render_dpi=qa_visual_render_dpi,
        qa_visual_render_timeout_seconds=qa_visual_render_timeout_seconds,
        bridge=bridge,
    )

    return ApiResponse(
        data=GenerateResponse(
            task_id=task_id,
            success=True,
            output_file=None,
            duration_seconds=None,
            warnings=["报告生成已进入后台队列，请稍后刷新任务状态。"],
        )
    )


@router.get("/{task_id}", response_model=ApiResponse[TaskStatus])
def get_task_status(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    field_provenance_path = _field_provenance_sidecar_path(task.output_path)
    report_summary_path = _report_summary_sidecar_path(task.output_path)
    qa_report_file, qa_status, _qa_issues = _load_qa_summary(task.output_path)
    stage_results_file, generation_id, stage_results = _load_stage_results(
        task.output_path,
        task_id=task.id,
    )
    diff_summary = diff_svc.report_diff_summary(task.output_path)
    batch_counts = _batch_status_counts(db, task.id) if task.task_type == "batch" else {}

    return ApiResponse(
        data=TaskStatus(
            id=task.id,
            task_type=task.task_type,
            status=task.status,
            project_type=task.project_type,
            total_files=task.total_files,
            completed_files=task.completed_files,
            failed_files=task.failed_files,
            cancelled_files=batch_counts.get("cancelled", 0),
            pending_files=pending_file_count(batch_counts),
            running_files=working_file_count(batch_counts),
            status_counts=batch_counts,
            output_path=task.output_path,
            field_provenance_file=(
                str(field_provenance_path)
                if field_provenance_path and field_provenance_path.exists()
                else None
            ),
            qa_report_file=qa_report_file,
            report_summary_file=(
                str(report_summary_path)
                if report_summary_path and report_summary_path.exists()
                else None
            ),
            qa_status=qa_status,
            generation_id=generation_id,
            stage_results_file=stage_results_file,
            stage_results=stage_results,
            diff_report_file=diff_summary.get("diff_report_file"),
            diff_markdown_file=diff_summary.get("diff_markdown_file"),
            diff_status=diff_summary.get("diff_status"),
            diff_gate_passed=diff_summary.get("diff_gate_passed"),
            diff_reference_id=diff_summary.get("diff_reference_id"),
            diff_reference_name=diff_summary.get("diff_reference_name"),
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            duration_seconds=task.duration_seconds,
            errors=json.loads(task.errors) if task.errors else [],
            warnings=json.loads(task.warnings) if task.warnings else [],
        )
    )


@router.get("/{task_id}/qa", response_model=ApiResponse[dict])
def get_qa_report(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    qa_path = _qa_sidecar_path(task.output_path)
    if not qa_path or not qa_path.exists():
        raise HTTPException(status_code=404, detail="QA报告不存在")
    try:
        payload = json.loads(qa_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"QA报告读取失败: {exc}") from exc
    return ApiResponse(data=payload)


@router.get("/{task_id}/summary", response_model=ApiResponse[dict])
def get_report_summary(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    summary_path = _report_summary_sidecar_path(task.output_path)
    if not summary_path or not summary_path.exists():
        raise HTTPException(status_code=404, detail="报告结果摘要不存在")
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"报告结果摘要读取失败: {exc}",
        ) from exc
    return ApiResponse(data=payload)


@router.get("/{task_id}/field-provenance", response_model=ApiResponse[dict])
def get_field_provenance(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    provenance_path = _field_provenance_sidecar_path(task.output_path)
    if not provenance_path or not provenance_path.exists():
        raise HTTPException(status_code=404, detail="字段来源报告不存在")
    try:
        payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"字段来源报告读取失败: {exc}") from exc
    return ApiResponse(data=payload)


@router.get("/{task_id}/stage-results", response_model=ApiResponse[dict])
def get_stage_results(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    stage_path = _stage_results_sidecar_path(task.output_path)
    if not stage_path or not stage_path.exists():
        stage_path = _fallback_stage_results_sidecar_path(task.id)
    if not stage_path or not stage_path.exists():
        raise HTTPException(status_code=404, detail="生成阶段报告不存在")
    try:
        payload = json.loads(stage_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"生成阶段报告读取失败: {exc}",
        ) from exc
    return ApiResponse(data=payload)


@router.get("/{task_id}/batch-results", response_model=ApiResponse[dict])
def get_batch_results(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.task_type != "batch":
        raise HTTPException(status_code=400, detail="仅批量任务支持逐文件结果")

    rows = (
        db.query(TaskResult)
        .filter(TaskResult.task_id == task_id)
        .order_by(TaskResult.file_index.asc())
        .all()
    )
    counts = empty_batch_status_counts()
    for row in rows:
        counts[row.status or "pending"] = counts.get(row.status or "pending", 0) + 1
    output_root = Path(task.output_path) if task.output_path else None
    items = []
    for row in rows:
        output_path = row.output_path
        output_filename = Path(output_path).name if output_path else None
        summary_path = _report_summary_sidecar_path(output_path)
        validation = _load_json_dict(row.validation_summary)
        items.append(
            {
                "index": row.file_index,
                "excel_filename": row.excel_filename,
                "status": row.status,
                "output_path": output_path,
                "output_filename": output_filename,
                "download_url": (
                    f"/api/v1/reports/{task_id}/batch-results/{row.file_index}/download"
                    if output_path and Path(output_path).exists()
                    else None
                ),
                "report_summary_file": (
                    str(summary_path)
                    if summary_path and summary_path.exists()
                    else validation.get("report_summary_file")
                ),
                "qa_status": validation.get("qa_status"),
                "project_type": validation.get("project_type"),
                "project_name": validation.get("project_name"),
                "clinical_info": validation.get("clinical_info") or {},
                "duration_seconds": row.duration_seconds,
                "errors": _load_json_list(row.errors),
                "warnings": _load_json_list(row.warnings),
                "validation": validation,
            }
        )
    batch_report = None
    batch_report_path = _batch_report_path(task.output_path)
    if batch_report_path and batch_report_path.exists():
        try:
            batch_report = json.loads(batch_report_path.read_text(encoding="utf-8"))
        except Exception:
            batch_report = None
    return ApiResponse(
        data={
            "task_id": task.id,
            "status": task.status,
            "total_files": task.total_files,
            "completed_files": task.completed_files,
            "failed_files": task.failed_files,
            "cancelled_files": counts.get("cancelled", 0),
            "pending_files": pending_file_count(counts),
            "running_files": working_file_count(counts),
            "status_counts": counts,
            "output_root": str(output_root) if output_root else None,
            "items": items,
            "batch_report": batch_report,
        }
    )


@router.get("/{task_id}/quality-gate", response_model=ApiResponse[dict])
def get_quality_gate(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(data=_quality_gate_payload(task, db))


@router.get("/{task_id}/review-state", response_model=ApiResponse[dict])
def get_review_state(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(data=_load_review_state(task))


@router.get("/{task_id}/audit-log", response_model=ApiResponse[dict])
def get_task_audit_log(
    task_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.resource_type == "task", AuditLog.resource_id == task_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return ApiResponse(
        data={
            "task_id": task_id,
            "items": [audit_event_payload(row) for row in rows],
        }
    )


@router.post("/{task_id}/review-state", response_model=ApiResponse[dict])
def update_review_state(
    task_id: str,
    req: ReviewStateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_reviewer),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if req.status not in REVIEW_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"审核状态仅支持: {', '.join(REVIEW_STATUSES)}",
        )

    gate = _quality_gate_payload(task, db)
    if req.status == "delivered" and not gate["passed"] and not req.override_gate:
        raise HTTPException(
            status_code=409,
            detail="质控门禁未通过，不能标记已交付；请先处理阻断项。",
        )

    state = _load_review_state(task)
    now = utc_now_naive().isoformat()
    actor = request_operator(request)
    event = {
        "status": req.status,
        "status_label": REVIEW_STATUSES[req.status],
        "updated_at": now,
        "updated_by": actor,
        "note": req.note or "",
        "override_gate": bool(req.override_gate),
        "gate_status": gate["status"],
        "gate_blockers": gate["blockers"],
    }
    history = state.get("history") or []
    history.append(event)
    state.update(event)
    state["task_id"] = task.id
    state["schema_version"] = "1.0"
    state["history"] = history
    updated_state = _write_review_state(task, state)
    record_audit_event(
        db,
        action="review_state.updated",
        resource_type="task",
        resource_id=task.id,
        request=request,
        details={
            "gate_blockers": gate["blockers"],
            "gate_status": gate["status"],
            "operator": actor,
            "override_gate": bool(req.override_gate),
            "project_type": task.project_type,
            "review_status": req.status,
            "review_status_label": REVIEW_STATUSES[req.status],
            "task_status": task.status,
            "task_type": task.task_type,
        },
    )
    return ApiResponse(data=updated_state)


@router.get("/{task_id}/batch-results/{file_index}/download")
def download_batch_item_report(
    task_id: str,
    file_index: int,
    request: Request,
    db: Session = Depends(get_db),
    override_gate: bool = Query(False, description="复核人显式放行：QA FAIL 时仍允许下载交付"),
    current_user: User = Depends(require_user),
):
    _require_override_permission(override_gate, current_user)
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.task_type != "batch":
        raise HTTPException(status_code=400, detail="仅批量任务支持逐文件下载")
    row = (
        db.query(TaskResult)
        .filter(TaskResult.task_id == task_id, TaskResult.file_index == file_index)
        .first()
    )
    if not row or not row.output_path:
        raise HTTPException(status_code=404, detail="报告文件不存在")
    path = Path(row.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="报告文件已被删除")

    # 交付门禁（第3步）：与单份下载一致——QA=FAIL 的批量逐文件报告不允许直接
    # 下载交付，需复核人显式 override。只拦 FAIL 这一硬失败，不误伤 WARN/无记录。
    if _load_json_dict(row.validation_summary).get("qa_status") == "FAIL" and not override_gate:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{row.excel_filename or '该报告'} QA 状态为 FAIL，已阻止下载交付。"
                "请先核查修复；确需交付可由复核人显式 override（加 override_gate=1）。"
            ),
        )
    return _observed_file_response(
        path=path,
        download_filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        download_kind="batch_item_docx",
        task=task,
        request=request,
        extra_context={"file_index": file_index},
        db=db,
    )


@router.get("/{task_id}/batch/download")
def download_batch_reports_zip(
    task_id: str,
    request: Request,
    qa: Optional[str] = Query(None, pattern="^(pass|all)$"),
    override_gate: bool = Query(
        False, description="配合 qa=all：复核人显式放行，打包含 QA FAIL 的报告"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    _require_override_permission(override_gate, current_user)
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.task_type != "batch":
        raise HTTPException(status_code=400, detail="仅批量任务支持打包下载")
    output_root = Path(task.output_path) if task.output_path else settings.report_dir / task_id
    output_root.mkdir(parents=True, exist_ok=True)
    qa_pass_only = qa == "pass"
    zip_path = output_root / (
        f"{task_id}_qa_pass_reports.zip" if qa_pass_only else f"{task_id}_reports.zip"
    )
    rows = (
        db.query(TaskResult)
        .filter(TaskResult.task_id == task_id, TaskResult.status == "completed")
        .order_by(TaskResult.file_index.asc())
        .all()
    )
    # 交付门禁（第3步）三态过滤：
    #   qa=pass          → 只打包 QA PASS 的报告（最严，保持原语义）
    #   默认（不传/其它）→ 排除 QA=FAIL，但保留 PASS/WARN/无记录（默认即安全，
    #                      不把坏报告混进交付包）
    #   qa=all + override_gate=1 → 复核人显式放行，打包全部含 FAIL
    force_all = qa == "all" and override_gate
    if qa_pass_only:
        rows = [
            row
            for row in rows
            if _load_json_dict(row.validation_summary).get("qa_status") == "PASS"
        ]
    elif not force_all:
        rows = [
            row
            for row in rows
            if _load_json_dict(row.validation_summary).get("qa_status") != "FAIL"
        ]
    if not rows:
        if qa_pass_only:
            detail = "没有 QA PASS 的成功报告"
        elif not force_all:
            detail = (
                "没有可打包的合格报告（QA=FAIL 的报告已被排除）。"
                "确需打包含 FAIL 可用 qa=all&override_gate=1。"
            )
        else:
            detail = "没有可打包的成功报告"
        raise HTTPException(status_code=404, detail=detail)
    prepare_started = time.perf_counter()
    temp_zip_path = output_root / f".{zip_path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with zipfile.ZipFile(
            temp_zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            batch_report = _batch_report_path(task.output_path)
            if batch_report and batch_report.exists():
                zf.write(batch_report, "batch_report.json")
            for row in rows:
                if not row.output_path:
                    continue
                docx_path = Path(row.output_path)
                if docx_path.exists():
                    zf.write(
                        docx_path,
                        f"reports/{row.file_index:03d}_{docx_path.name}",
                    )
                summary_path = _report_summary_sidecar_path(row.output_path)
                if summary_path and summary_path.exists():
                    zf.write(
                        summary_path,
                        f"summaries/{row.file_index:03d}_{summary_path.name}",
                    )
        temp_zip_path.replace(zip_path)
    finally:
        if temp_zip_path.exists():
            temp_zip_path.unlink(missing_ok=True)
    prepare_duration_ms = round((time.perf_counter() - prepare_started) * 1000, 3)
    return _observed_file_response(
        path=zip_path,
        download_filename=zip_path.name,
        media_type="application/zip",
        download_kind="batch_zip",
        task=task,
        request=request,
        extra_context={
            "qa_filter": "pass" if qa_pass_only else "all",
            "item_count": len(rows),
            "prepare_duration_ms": prepare_duration_ms,
        },
        db=db,
    )


@router.get("/{task_id}/audit-package")
def download_audit_package(
    task_id: str,
    request: Request,
    include_failed: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    output_root = _task_artifact_dir(task)
    output_root.mkdir(parents=True, exist_ok=True)
    gate = _quality_gate_payload(task, db)
    review_state = _load_review_state(task)
    if (
        _controlled_pilot_review_required(
            task.project_type,
            review_state.get("status"),
        )
        and current_user.role not in TASK_PRIVILEGED_ROLES
    ):
        raise HTTPException(
            status_code=409,
            detail=("该肺癌Panel处于受控试运行，未审核报告的审计包仅供复核人或管理员下载。"),
        )
    zip_path = output_root / (
        f"{task_id}_audit_package.zip" if include_failed else f"{task_id}_passed_audit_package.zip"
    )
    prepare_started = time.perf_counter()
    manifest = {
        "schema_version": "1.0",
        "generated_at": utc_now_naive().isoformat(),
        "task": {
            "id": task.id,
            "task_type": task.task_type,
            "status": task.status,
            "project_type": task.project_type,
            "total_files": task.total_files,
            "completed_files": task.completed_files,
            "failed_files": task.failed_files,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "duration_seconds": task.duration_seconds,
        },
        "quality_gate": {
            "status": gate["status"],
            "passed": gate["passed"],
            "blockers": gate["blockers"],
            "warnings": gate["warnings"],
        },
        "review": {
            "status": review_state.get("status"),
            "status_label": review_state.get("status_label"),
            "updated_at": review_state.get("updated_at"),
            "updated_by": review_state.get("updated_by"),
        },
        "include_failed": include_failed,
    }

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "audit_manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "quality_gate.json",
            json.dumps(gate, ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "review_state.json",
            json.dumps(review_state, ensure_ascii=False, indent=2),
        )

        if task.task_type == "batch":
            batch_report = _batch_report_path(task.output_path)
            _add_zip_file(zf, batch_report, "batch/batch_report.json")
            diff_summary = diff_svc.report_diff_summary(task.output_path)
            _add_zip_file(
                zf,
                Path(diff_summary["diff_report_file"])
                if diff_summary.get("diff_report_file")
                else None,
                "diff/batch_report_diff.json",
            )
            _add_zip_file(
                zf,
                Path(diff_summary["diff_markdown_file"])
                if diff_summary.get("diff_markdown_file")
                else None,
                "diff/batch_report_diff.md",
            )
            rows = (
                db.query(TaskResult)
                .filter(TaskResult.task_id == task_id)
                .order_by(TaskResult.file_index.asc())
                .all()
            )
            for row in rows:
                if row.status != "completed" and not include_failed:
                    continue
                prefix = f"items/{row.file_index:03d}_{safe_filename(row.excel_filename)}"
                if row.output_path:
                    docx_path = Path(row.output_path)
                    _add_zip_file(zf, docx_path, f"{prefix}/report/{docx_path.name}")
                    for sidecar, arcname in _artifact_sidecars(row.output_path):
                        _add_zip_file(zf, sidecar, f"{prefix}/{arcname}")
                zf.writestr(
                    f"{prefix}/result.json",
                    json.dumps(
                        {
                            "index": row.file_index,
                            "excel_filename": row.excel_filename,
                            "status": row.status,
                            "duration_seconds": row.duration_seconds,
                            "errors": _load_json_list(row.errors),
                            "warnings": _load_json_list(row.warnings),
                            "validation": _load_json_dict(row.validation_summary),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
        else:
            if task.output_path:
                docx_path = Path(task.output_path)
                _add_zip_file(zf, docx_path, f"report/{docx_path.name}")
                for sidecar, arcname in _artifact_sidecars(task.output_path):
                    _add_zip_file(zf, sidecar, arcname)
                diff_summary = diff_svc.report_diff_summary(task.output_path)
                _add_zip_file(
                    zf,
                    Path(diff_summary["diff_report_file"])
                    if diff_summary.get("diff_report_file")
                    else None,
                    "diff/report_diff.json",
                )
                _add_zip_file(
                    zf,
                    Path(diff_summary["diff_markdown_file"])
                    if diff_summary.get("diff_markdown_file")
                    else None,
                    "diff/report_diff.md",
                )

    prepare_duration_ms = round((time.perf_counter() - prepare_started) * 1000, 3)
    return _observed_file_response(
        path=zip_path,
        download_filename=zip_path.name,
        media_type="application/zip",
        download_kind="audit_package_zip",
        task=task,
        request=request,
        extra_context={
            "include_failed": include_failed,
            "prepare_duration_ms": prepare_duration_ms,
        },
        db=db,
    )


@router.post("/{task_id}/visual-render", response_model=ApiResponse[dict])
def render_report_pages(
    task_id: str,
    mode: str = Query("first", pattern="^(first|all)$"),
    dpi: int = Query(120, ge=72, le=240),
    timeout_seconds: int = Query(120, ge=5, le=600),
    db: Session = Depends(get_db),
):
    """Render generated DOCX pages to PNGs on demand for visual QA."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.output_path:
        raise HTTPException(status_code=404, detail="报告文件不存在")

    docx_path = Path(task.output_path)
    if not docx_path.exists():
        raise HTTPException(status_code=404, detail="报告文件已被删除")

    render_dir = _visual_render_dir(task.output_path)
    if not render_dir:
        raise HTTPException(status_code=404, detail="渲染目录不可用")
    first_page = 1 if mode == "first" else None
    last_page = 1 if mode == "first" else None

    try:
        pages = render_docx_to_pngs(
            docx_path,
            output_dir=render_dir,
            dpi=dpi,
            first_page=first_page,
            last_page=last_page,
            timeout_seconds=timeout_seconds,
            keep_pdf=False,
        )
    except Exception as exc:
        payload = {
            "requested": mode,
            "status": "WARN",
            "message": f"视觉渲染失败: {exc}",
            "rendered_pages": [],
            "output_dir": str(render_dir),
            **_render_error_payload(exc),
        }
        return ApiResponse(success=False, data=payload, error=payload["message"])

    page_names = [path.name for path in pages if path.exists()]
    return ApiResponse(
        data={
            "requested": mode,
            "status": "PASS" if page_names else "WARN",
            "message": "视觉渲染完成" if page_names else "视觉渲染未生成页面图片",
            "rendered_pages": [
                {
                    "filename": name,
                    "url": f"/api/v1/reports/{task_id}/visual-render/pages/{name}",
                }
                for name in page_names
            ],
            "output_dir": str(render_dir),
        }
    )


@router.get("/{task_id}/visual-render/pages/{filename}")
def get_rendered_page(task_id: str, filename: str, db: Session = Depends(get_db)):
    """Return one rendered PNG page for a generated report."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    page_path = _visual_render_page_path(task.output_path, filename)
    if not page_path or not page_path.exists() or page_path.suffix.lower() != ".png":
        raise HTTPException(status_code=404, detail="页面图片不存在")
    return FileResponse(path=str(page_path), media_type="image/png")


@router.post("/{task_id}/diff", response_model=ApiResponse[dict])
def diff_report_against_reference(
    task_id: str,
    reference: UploadFile = File(...),
    fail_on: str = Query("fail", pattern="^(fail|warn)$"),
    max_samples: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Compare a generated report against an uploaded reference DOCX."""
    task = _get_single_report_task(task_id, db)
    if not reference.filename or not reference.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="仅支持上传 .docx 基准报告")

    diff_dir = _report_diff_dir(task.output_path)
    if not diff_dir:
        raise HTTPException(status_code=404, detail="报告对比目录不可用")
    diff_dir.mkdir(parents=True, exist_ok=True)
    reference_path = diff_dir / "reference.docx"
    try:
        write_upload_stream(
            reference.file,
            reference_path,
            scope="临时对比基准文件",
        )
    except UploadLimitExceeded:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"基准报告保存失败: {exc}") from exc
    finally:
        try:
            reference.file.close()
        except Exception:
            pass

    result = diff_svc.compare_task_with_reference_path(
        task,
        reference_docx=str(reference_path),
        task_id=task_id,
        fail_on=fail_on,
        max_samples=max_samples,
        reference_metadata={
            "source": "uploaded",
            "name": safe_client_filename(reference.filename, "reference.docx"),
            "active": False,
        },
    )
    return ApiResponse(data=result)


@router.post("/{task_id}/diff/auto", response_model=ApiResponse[dict])
def diff_report_against_registered_reference(
    task_id: str,
    fail_on: str = Query("fail", pattern="^(fail|warn)$"),
    max_samples: int = Query(50, ge=1, le=200),
    reference_gate_mode: str = Query("available", pattern="^(available|required)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Compare a generated report against the active panel/case reference report."""
    reference_gate_mode = _validated_reference_gate_mode(
        reference_gate_mode,
        current_user,
    )
    task = _get_single_report_task(task_id, db)
    result = diff_svc.run_auto_reference_diff(
        db,
        task,
        fail_on=fail_on,
        max_samples=max_samples,
        require_reference=diff_svc.reference_is_required(reference_gate_mode),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="未找到匹配的启用基准报告")
    return ApiResponse(data=result)


@router.post("/{task_id}/diff/batch/auto", response_model=ApiResponse[dict])
def diff_batch_report_against_registered_references(
    task_id: str,
    fail_on: str = Query("fail", pattern="^(fail|warn)$"),
    max_samples: int = Query(50, ge=1, le=200),
    reference_gate_mode: str = Query("available", pattern="^(available|required)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Run reference diff for every generated report in a batch task."""
    reference_gate_mode = _validated_reference_gate_mode(
        reference_gate_mode,
        current_user,
    )
    task = _get_report_task_with_output(task_id, db)
    if task.task_type != "batch":
        raise HTTPException(status_code=400, detail="仅批量任务支持该接口")
    report_path = Path(task.output_path) / "validation_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="批量验证报告不存在")
    try:
        batch_report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"批量验证报告读取失败: {exc}") from exc
    result = diff_svc.run_batch_reference_diff(
        db,
        task,
        batch_report,
        fail_on=fail_on,
        max_samples=max_samples,
        require_reference=diff_svc.reference_is_required(reference_gate_mode),
    )
    return ApiResponse(data=result)


@router.get("/{task_id}/diff", response_model=ApiResponse[dict])
def get_report_diff(task_id: str, db: Session = Depends(get_db)):
    """Return the latest report diff JSON for a task."""
    task = _get_report_task_with_output(task_id, db)
    if task.task_type == "batch":
        payload = diff_svc.load_batch_report_diff(task.output_path)
    else:
        payload = diff_svc.load_report_diff(task.output_path)
    if not payload:
        raise HTTPException(status_code=404, detail="报告对比结果不存在")
    return ApiResponse(data=payload)


@router.get("/{task_id}/diff/batch/download/{filename}")
def download_batch_report_diff_artifact(
    task_id: str,
    filename: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Download batch report diff JSON or Markdown for a task."""
    task = _get_report_task_with_output(task_id, db)
    if task.task_type != "batch":
        raise HTTPException(status_code=400, detail="仅批量任务支持该产物")
    artifact_path = diff_svc.batch_report_diff_artifact_path(task.output_path, filename)
    if not artifact_path or not artifact_path.exists():
        raise HTTPException(status_code=404, detail="批量报告对比产物不存在")
    media_type = "application/json" if filename.endswith(".json") else "text/markdown"
    return _observed_file_response(
        path=artifact_path,
        download_filename=filename,
        media_type=media_type,
        download_kind="batch_diff_artifact",
        task=task,
        request=request,
        db=db,
    )


@router.get("/{task_id}/diff/batch/items/{item_key}/download/{filename}")
def download_batch_report_diff_item_artifact(
    task_id: str,
    item_key: str,
    filename: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Download one sample's batch report diff JSON or Markdown."""
    task = _get_report_task_with_output(task_id, db)
    if task.task_type != "batch":
        raise HTTPException(status_code=400, detail="仅批量任务支持该产物")
    if filename not in {"report_diff.json", "report_diff.md"}:
        raise HTTPException(status_code=404, detail="报告对比产物不存在")
    diff_dir = diff_svc.report_diff_dir(task.output_path)
    if not diff_dir:
        raise HTTPException(status_code=404, detail="报告对比目录不存在")
    item_dir = (diff_dir / diff_svc.sanitize_path_segment(item_key)).resolve()
    try:
        item_dir.relative_to(diff_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="报告对比产物不存在") from None
    artifact_path = (item_dir / filename).resolve()
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="报告对比产物不存在")
    media_type = "application/json" if filename.endswith(".json") else "text/markdown"
    return _observed_file_response(
        path=artifact_path,
        download_filename=filename,
        media_type=media_type,
        download_kind="batch_diff_item_artifact",
        task=task,
        request=request,
        db=db,
    )


@router.get("/{task_id}/diff/download/{filename}")
def download_report_diff_artifact(
    task_id: str,
    filename: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Download report diff JSON or Markdown for a task."""
    task = _get_single_report_task(task_id, db)
    artifact_path = _report_diff_artifact_path(task.output_path, filename)
    if not artifact_path or not artifact_path.exists():
        raise HTTPException(status_code=404, detail="报告对比产物不存在")
    media_type = "application/json" if filename.endswith(".json") else "text/markdown"
    return _observed_file_response(
        path=artifact_path,
        download_filename=filename,
        media_type=media_type,
        download_kind="diff_artifact",
        task=task,
        request=request,
        db=db,
    )


def _download_report_response(
    task_id: str,
    db: Session,
    request: Request,
    current_user: User,
    override_gate: bool = False,
) -> FileResponse:
    _require_override_permission(override_gate, current_user)
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.output_path:
        raise HTTPException(status_code=404, detail="报告文件不存在")

    file_path = Path(task.output_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="报告文件已被删除")

    # 交付门禁（B 步）：QA 明确判定 FAIL 的报告不允许直接下载交付。生成不拦
    # （方便排查），出厂才拦——坏报告可以留档诊断，但不许流到客户手里。只拦
    # qa_status == "FAIL" 这一硬失败，刻意不拦 QA_MISSING / WARN / diff 未跑
    # 等环境性问题，避免误伤无 QA 记录的历史任务。需人工显式 override_gate=1
    # 才放行（与审核交付的 override 语义一致）。
    _, qa_status, _ = _load_qa_summary(task.output_path)
    if qa_status == "FAIL" and not override_gate:
        raise HTTPException(
            status_code=409,
            detail=(
                "报告 QA 状态为 FAIL，已阻止下载交付。请先在质控门禁中核查并修复问题；"
                "确需交付可由复核人显式 override（下载时加 override_gate=1）。"
            ),
        )
    # A reviewer must be able to see the generated Word file before deciding
    # whether it passes. Review state therefore governs formal delivery/audit
    # status, not access to the authenticated draft artifact itself.

    clinical_info = _clinical_snapshot(task)
    project_type = str(task.project_type or "").strip().lower()
    revision_label = None
    if project_type in CONTROLLED_PILOT_PROJECT_TYPES:
        review_status = str(_load_review_state(task).get("status") or "").strip().lower()
        if review_status not in {"reviewed", "delivered"}:
            revision_label = "草稿"
    download_filename = _business_report_filename(
        clinical_info=clinical_info,
        project_type=task.project_type,
        project_name=clinical_info.get("project_name") or clinical_info.get("项目名称"),
        output_path=task.output_path,
        revision_label=revision_label,
    )

    return _observed_file_response(
        path=file_path,
        download_filename=download_filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        download_kind="single_docx",
        task=task,
        request=request,
        db=db,
    )


@router.head("/{task_id}/download", include_in_schema=False)
def head_download_report(
    task_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    return _download_report_response(task_id, db, request, current_user)


@router.get("/{task_id}/download")
def download_report(
    task_id: str,
    request: Request,
    db: Session = Depends(get_db),
    override_gate: bool = Query(False, description="复核人显式放行：QA FAIL 时仍允许下载交付"),
    current_user: User = Depends(require_user),
):
    return _download_report_response(
        task_id,
        db,
        request,
        current_user,
        override_gate=override_gate,
    )
