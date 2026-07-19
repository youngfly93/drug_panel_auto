"""Recover queued report-generation tasks after process restarts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.task import Task, TaskResult
from app.services.batch_lifecycle import (
    BATCH_ACTIVE_STATUSES,
    BATCH_ITEM_ACTIVE_STATUSES,
)
from app.services.generation_queue import submit_generation_job
from app.time_utils import utc_now_naive

SINGLE_IN_FLIGHT_STATUSES = {"pending", "running"}
TERMINAL_STATUSES = {"completed", "failed", "partial_failed", "cancelled"}
RECOVERY_MESSAGE = "服务重启时任务未完成，系统已执行恢复处理。"
PRIVATE_REQUEST_FILENAME = "generation_request.private.json"

_last_recovery_summary: dict[str, Any] = {
    "ran": False,
    "checked_at": None,
    "scanned": 0,
    "requeued": 0,
    "failed": 0,
    "skipped": 0,
    "errors": [],
}


def single_generation_request_path(task_id: str) -> Path:
    return settings.report_dir / task_id / PRIVATE_REQUEST_FILENAME


def write_single_generation_request(*, task_id: str, payload: dict[str, Any]) -> Path:
    """Persist private request metadata needed to resume an async single task."""
    path = single_generation_request_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": "1.0",
        "created_at": utc_now_naive().isoformat(),
        **payload,
    }
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def last_recovery_summary() -> dict[str, Any]:
    return dict(_last_recovery_summary)


def _load_json_list(value: str | None) -> list:
    if not value:
        return []
    try:
        payload = json.loads(value)
    except Exception:
        return [str(value)]
    return payload if isinstance(payload, list) else [payload]


def _append_json_list(value: str | None, *items: str) -> str:
    payload = _load_json_list(value)
    payload.extend(item for item in items if item)
    return json.dumps(payload, ensure_ascii=False)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _fail_task(db: Session, task: Task, reason: str) -> None:
    now = utc_now_naive()
    task.status = "failed"
    task.completed_at = task.completed_at or now
    if task.started_at and task.completed_at:
        task.duration_seconds = (task.completed_at - task.started_at).total_seconds()
    task.errors = _append_json_list(task.errors, reason)
    task.warnings = _append_json_list(task.warnings, RECOVERY_MESSAGE)
    if task.task_type == "batch":
        (
            db.query(TaskResult)
            .filter(
                TaskResult.task_id == task.id,
                TaskResult.status.in_(list(BATCH_ITEM_ACTIVE_STATUSES)),
            )
            .update(
                {
                    TaskResult.status: "failed",
                    TaskResult.errors: json.dumps([reason], ensure_ascii=False),
                },
                synchronize_session=False,
            )
        )


def _single_payload_is_recoverable(payload: dict[str, Any]) -> tuple[bool, str | None]:
    stored_path = Path(str(payload.get("stored_path") or ""))
    output_dir = Path(str(payload.get("output_dir") or ""))
    if not stored_path.exists():
        return False, "异步单份任务源 Excel 不存在，无法自动恢复，请重新上传。"
    if not output_dir:
        return False, "异步单份任务缺少输出目录，无法自动恢复，请重新上传。"
    if not _is_under(stored_path, settings.storage_root):
        return False, "异步单份任务源 Excel 路径不在受控存储目录内，已阻止恢复。"
    if not _is_under(output_dir, settings.report_dir):
        return False, "异步单份任务输出目录不在报告存储目录内，已阻止恢复。"
    return True, None


def _recover_single_task(db: Session, task: Task, bridge: Any) -> str:
    from app.api.report import _complete_file_generation_task

    request_path = Path(task.context_json_path or single_generation_request_path(task.id))
    if not request_path.exists():
        _fail_task(
            db,
            task,
            "异步单份任务缺少恢复清单，无法自动恢复，请重新上传。",
        )
        return "failed"

    payload = _read_json(request_path)
    recoverable, reason = _single_payload_is_recoverable(payload)
    if not recoverable:
        _fail_task(db, task, reason or "异步单份任务恢复清单无效。")
        return "failed"

    task.status = "pending"
    task.started_at = None
    task.completed_at = None
    task.duration_seconds = None
    task.warnings = _append_json_list(
        task.warnings,
        "服务启动时恢复未完成的单份生成任务，已重新进入后台队列。",
    )
    db.commit()

    job_kwargs = {
        key: payload.get(key)
        for key in (
            "task_id",
            "stored_path",
            "output_dir",
            "clinical_payload",
            "project_type",
            "project_name",
            "template_name",
            "strict_mode",
            "template_contract_mode",
            "reference_gate_mode",
            "qa_visual_render",
            "qa_visual_render_required",
            "qa_visual_render_dpi",
            "qa_visual_render_timeout_seconds",
        )
    }
    job_kwargs["reference_gate_mode"] = (
        job_kwargs.get("reference_gate_mode") or "available"
    )
    job_kwargs["bridge"] = bridge
    submit_generation_job(_complete_file_generation_task, **job_kwargs)
    return "requeued"


def _batch_inputs_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / "batch_inputs.private.json"


def _recover_batch_task(db: Session, task: Task, bridge: Any) -> str:
    from app.api.batch import _complete_batch_files_task, _write_batch_report

    if not task.output_path:
        _fail_task(db, task, "批量任务缺少输出目录，无法自动恢复，请重新上传。")
        return "failed"
    output_dir = Path(task.output_path)
    if not _is_under(output_dir, settings.report_dir):
        _fail_task(db, task, "批量任务输出目录不在报告存储目录内，已阻止恢复。")
        return "failed"

    inputs_path = _batch_inputs_path(output_dir)
    inputs = _read_json(inputs_path)
    items = inputs.get("items") if isinstance(inputs.get("items"), list) else []
    if not items:
        _fail_task(db, task, "批量任务缺少源文件索引，无法自动恢复，请重新上传。")
        return "failed"
    item_by_index = {
        int(item["index"]): item
        for item in items
        if isinstance(item, dict) and item.get("index") is not None
    }

    retry_items: list[dict[str, Any]] = []
    source_missing = 0
    rows = (
        db.query(TaskResult)
        .filter(
            TaskResult.task_id == task.id,
            TaskResult.status.in_(list(BATCH_ITEM_ACTIVE_STATUSES)),
        )
        .order_by(TaskResult.file_index.asc())
        .all()
    )
    for row in rows:
        item = item_by_index.get(row.file_index)
        stored_path = Path(str(item.get("stored_path") or "")) if item else None
        if not item or not stored_path or not stored_path.exists():
            source_missing += 1
            row.status = "failed"
            row.errors = json.dumps(
                ["批量任务源 Excel 不存在，无法自动恢复。"],
                ensure_ascii=False,
            )
            continue
        retry_items.append(item)
        row.status = "queued"
        row.output_path = None
        row.duration_seconds = None
        row.errors = None
        row.warnings = None
        row.validation_summary = None

    task.completed_files = (
        db.query(TaskResult)
        .filter(TaskResult.task_id == task.id, TaskResult.status == "completed")
        .count()
    )
    task.failed_files = (
        db.query(TaskResult)
        .filter(TaskResult.task_id == task.id, TaskResult.status == "failed")
        .count()
    )

    if not retry_items:
        if task.completed_files and task.failed_files:
            task.status = "partial_failed"
        else:
            task.status = "failed" if task.failed_files else "completed"
        task.completed_at = utc_now_naive()
        task.warnings = _append_json_list(
            task.warnings,
            RECOVERY_MESSAGE,
            f"批量任务恢复时没有可重跑文件；源文件缺失 {source_missing} 个。",
        )
        db.commit()
        _write_batch_report(db, task)
        return (
            "failed"
            if task.status in {"failed", "partial_failed"}
            else "skipped"
        )

    task.status = "queued"
    task.started_at = None
    task.completed_at = None
    task.duration_seconds = None
    task.warnings = _append_json_list(
        task.warnings,
        f"服务启动时恢复未完成的批量任务，{len(retry_items)} 个文件已重新进入后台队列。",
    )
    db.commit()
    _write_batch_report(db, task)

    submit_generation_job(
        _complete_batch_files_task,
        task_id=task.id,
        items=retry_items,
        output_dir=str(output_dir),
        shared_clinical_info=inputs.get("shared_clinical_info") or {},
        project_type=inputs.get("project_type"),
        project_name=inputs.get("project_name"),
        template_name=inputs.get("template_name"),
        template_contract_mode=inputs.get("template_contract_mode") or "warn",
        reference_gate_mode=inputs.get("reference_gate_mode") or "available",
        bridge=bridge,
    )
    return "requeued"


def recover_interrupted_tasks(
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    bridge: Any = None,
) -> dict[str, Any]:
    """Recover or explicitly fail tasks left non-terminal by a prior process."""
    global _last_recovery_summary
    summary: dict[str, Any] = {
        "ran": True,
        "checked_at": utc_now_naive().isoformat(),
        "scanned": 0,
        "requeued": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
    }
    db = session_factory()
    try:
        tasks = (
            db.query(Task)
            .filter(
                or_(
                    and_(
                        Task.task_type == "single",
                        Task.status.in_(list(SINGLE_IN_FLIGHT_STATUSES)),
                    ),
                    and_(
                        Task.task_type == "batch",
                        Task.status.in_(list(BATCH_ACTIVE_STATUSES)),
                    ),
                )
            )
            .order_by(Task.created_at.asc())
            .all()
        )
        summary["scanned"] = len(tasks)
        for task in tasks:
            try:
                if task.status in TERMINAL_STATUSES:
                    outcome = "skipped"
                elif task.task_type == "single":
                    outcome = _recover_single_task(db, task, bridge)
                elif task.task_type == "batch":
                    outcome = _recover_batch_task(db, task, bridge)
                else:
                    _fail_task(db, task, f"未知任务类型 {task.task_type}，无法自动恢复。")
                    outcome = "failed"
                if outcome in {"requeued", "failed", "skipped"}:
                    summary[outcome] += 1
                db.commit()
            except Exception as exc:
                db.rollback()
                summary["errors"].append(
                    {
                        "task_id": task.id,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
        _last_recovery_summary = summary
        return summary
    finally:
        db.close()
