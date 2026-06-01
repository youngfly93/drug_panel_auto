"""Task queue management endpoints."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.task import Task, TaskResult
from app.schemas.common import ApiResponse
from app.services import reference_report_service as diff_svc

router = APIRouter(prefix="/tasks", tags=["tasks"])

REVIEW_STATUSES = {
    "draft": "待审核",
    "reviewed": "已审核",
    "delivered": "已交付",
    "rejected": "退回修改",
}


def _qa_sidecar_path(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    return Path(output_path).with_suffix(".qa.json")


def _stage_results_sidecar_path(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    return Path(output_path).with_suffix(".stage_results.json")


def _fallback_stage_results_sidecar_path(task_id: str) -> Path:
    return settings.report_dir / task_id / "generation.stage_results.json"


def _task_artifact_dir(task: Task) -> Path:
    if task.task_type == "batch":
        return Path(task.output_path) if task.output_path else settings.report_dir / task.id
    if task.output_path:
        return Path(task.output_path).parent
    return settings.report_dir / task.id


def _load_review_state(task: Task) -> dict:
    path = _task_artifact_dir(task) / "review_state.json"
    default = {
        "schema_version": "1.0",
        "task_id": task.id,
        "status": "draft",
        "status_label": REVIEW_STATUSES["draft"],
        "updated_at": None,
        "updated_by": None,
        "note": "",
        "history": [],
    }
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    if not isinstance(payload, dict):
        return default
    status = payload.get("status") or "draft"
    payload["status"] = status
    payload["status_label"] = REVIEW_STATUSES.get(status, status)
    payload.setdefault("history", [])
    return payload


def _load_qa_summary(output_path: Optional[str]) -> tuple[str | None, str | None]:
    qa_path = _qa_sidecar_path(output_path)
    if not qa_path or not qa_path.exists():
        return None, None
    try:
        payload = json.loads(qa_path.read_text(encoding="utf-8"))
    except Exception:
        return str(qa_path), None
    return str(qa_path), payload.get("status")


def _load_stage_results_summary(
    output_path: Optional[str],
    task_id: Optional[str] = None,
) -> tuple[str | None, str | None]:
    stage_path = _stage_results_sidecar_path(output_path)
    if (not stage_path or not stage_path.exists()) and task_id:
        stage_path = _fallback_stage_results_sidecar_path(task_id)
    if not stage_path or not stage_path.exists():
        return None, None
    try:
        payload = json.loads(stage_path.read_text(encoding="utf-8"))
    except Exception:
        return str(stage_path), None
    return str(stage_path), payload.get("generation_id")


def _batch_status_counts(db: Session, task_id: str) -> dict[str, int]:
    counts = {
        "pending": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
    }
    rows = (
        db.query(TaskResult.status, func.count(TaskResult.id))
        .filter(TaskResult.task_id == task_id)
        .group_by(TaskResult.status)
        .all()
    )
    for status, count in rows:
        counts[status or "pending"] = count
    return counts


def _apply_batch_counts(task: Task, counts: dict[str, int]) -> None:
    task.completed_files = counts.get("completed", 0)
    task.failed_files = counts.get("failed", 0)


def _json_list(value: Optional[str]) -> list:
    if not value:
        return []
    try:
        payload = json.loads(value)
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _task_item(task: Task, db: Session) -> dict:
    batch_counts = _batch_status_counts(db, task.id) if task.task_type == "batch" else {}
    qa_report_file, qa_status = _load_qa_summary(task.output_path)
    stage_results_file, generation_id = _load_stage_results_summary(
        task.output_path,
        task_id=task.id,
    )
    diff_summary = diff_svc.report_diff_summary(task.output_path)
    review_state = _load_review_state(task)
    return {
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "project_type": task.project_type,
        "qa_status": qa_status,
        "qa_report_file": qa_report_file,
        "generation_id": generation_id,
        "stage_results_file": stage_results_file,
        "diff_status": diff_summary.get("diff_status"),
        "diff_gate_passed": diff_summary.get("diff_gate_passed"),
        "diff_reference_id": diff_summary.get("diff_reference_id"),
        "diff_reference_name": diff_summary.get("diff_reference_name"),
        "review_status": review_state.get("status"),
        "review_status_label": review_state.get("status_label"),
        "review_updated_at": review_state.get("updated_at"),
        "total_files": task.total_files,
        "completed_files": task.completed_files,
        "failed_files": task.failed_files,
        "cancelled_files": batch_counts.get("cancelled", 0),
        "pending_files": batch_counts.get("pending", 0),
        "running_files": batch_counts.get("running", 0),
        "status_counts": batch_counts,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "duration_seconds": task.duration_seconds,
        "errors": _json_list(task.errors),
        "warnings": _json_list(task.warnings),
    }


def _needs_attention(item: dict) -> bool:
    if item.get("status") in {"failed", "partial_failed", "cancelled"}:
        return True
    if item.get("qa_status") in {"FAIL", "WARN"}:
        return True
    if item.get("diff_gate_passed") is False:
        return True
    if item.get("review_status") == "rejected":
        return True
    return False


@router.get("", response_model=ApiResponse)
def list_tasks(
    status: str = Query(None, description="Filter by status"),
    task_type: str = Query(None, description="Filter by type: single|batch"),
    project_type: str = Query(None, description="Filter by project type"),
    qa_status: str = Query(None, description="Filter by QA status"),
    review_status: str = Query(None, description="Filter by review status"),
    attention: bool = Query(False, description="Only tasks needing handling"),
    q: str = Query(None, description="Search task id, project type, errors, or warnings"),
    created_from: str = Query(None, description="Created after ISO datetime"),
    created_to: str = Query(None, description="Created before ISO datetime"),
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    query = db.query(Task).order_by(Task.created_at.desc())
    if status:
        query = query.filter(Task.status == status)
    if task_type:
        query = query.filter(Task.task_type == task_type)
    if project_type:
        query = query.filter(Task.project_type == project_type)
    if created_from:
        query = query.filter(Task.created_at >= _parse_datetime(created_from))
    if created_to:
        query = query.filter(Task.created_at <= _parse_datetime(created_to))
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Task.id.ilike(pattern),
                Task.project_type.ilike(pattern),
                Task.errors.ilike(pattern),
                Task.warnings.ilike(pattern),
                Task.clinical_info_snapshot.ilike(pattern),
            )
        )

    post_filter = bool(qa_status or review_status or attention)
    if post_filter:
        all_items = [_task_item(task, db) for task in query.all()]
        if qa_status:
            all_items = [item for item in all_items if item.get("qa_status") == qa_status]
        if review_status:
            all_items = [
                item for item in all_items if item.get("review_status") == review_status
            ]
        if attention:
            all_items = [item for item in all_items if _needs_attention(item)]
        total = len(all_items)
        start = (page - 1) * page_size
        items = all_items[start : start + page_size]
    else:
        total = query.count()
        tasks = query.offset((page - 1) * page_size).limit(page_size).all()
        items = [_task_item(task, db) for task in tasks]

    return ApiResponse(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/stats", response_model=ApiResponse)
def task_stats(db: Session = Depends(get_db)):
    total = db.query(Task).count()
    completed = db.query(Task).filter(Task.status == "completed").count()
    failed = db.query(Task).filter(Task.status.in_(["failed", "partial_failed"])).count()
    running = db.query(Task).filter(Task.status == "running").count()
    pending = db.query(Task).filter(Task.status == "pending").count()
    partial_failed = db.query(Task).filter(Task.status == "partial_failed").count()
    cancelled = db.query(Task).filter(Task.status == "cancelled").count()
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_total = db.query(Task).filter(Task.created_at >= today_start).count()
    all_items = [_task_item(task, db) for task in db.query(Task).all()]
    needs_attention = sum(1 for item in all_items if _needs_attention(item))
    awaiting_review = sum(
        1
        for item in all_items
        if item.get("status") == "completed" and item.get("review_status") == "draft"
    )
    delivered = sum(1 for item in all_items if item.get("review_status") == "delivered")

    return ApiResponse(data={
        "total": total,
        "completed": completed,
        "failed": failed,
        "running": running,
        "pending": pending,
        "partial_failed": partial_failed,
        "cancelled": cancelled,
        "today_total": today_total,
        "needs_attention": needs_attention,
        "awaiting_review": awaiting_review,
        "delivered": delivered,
    })


@router.get("/{task_id}", response_model=ApiResponse)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    qa_report_file, qa_status = _load_qa_summary(task.output_path)
    stage_results_file, generation_id = _load_stage_results_summary(
        task.output_path,
        task_id=task.id,
    )
    diff_summary = diff_svc.report_diff_summary(task.output_path)
    batch_counts = _batch_status_counts(db, task.id) if task.task_type == "batch" else {}

    return ApiResponse(data={
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "project_type": task.project_type,
        "total_files": task.total_files,
        "completed_files": task.completed_files,
        "failed_files": task.failed_files,
        "cancelled_files": batch_counts.get("cancelled", 0),
        "pending_files": batch_counts.get("pending", 0),
        "running_files": batch_counts.get("running", 0),
        "status_counts": batch_counts,
        "output_path": task.output_path,
        "qa_status": qa_status,
        "qa_report_file": qa_report_file,
        "generation_id": generation_id,
        "stage_results_file": stage_results_file,
        "diff_report_file": diff_summary.get("diff_report_file"),
        "diff_markdown_file": diff_summary.get("diff_markdown_file"),
        "diff_status": diff_summary.get("diff_status"),
        "diff_gate_passed": diff_summary.get("diff_gate_passed"),
        "diff_reference_id": diff_summary.get("diff_reference_id"),
        "diff_reference_name": diff_summary.get("diff_reference_name"),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "duration_seconds": task.duration_seconds,
        "errors": json.loads(task.errors) if task.errors else [],
        "warnings": json.loads(task.warnings) if task.warnings else [],
    })


@router.delete("/{task_id}", response_model=ApiResponse)
def cancel_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail="只能取消待执行或执行中的任务")

    if task.task_type == "batch":
        (
            db.query(TaskResult)
            .filter(TaskResult.task_id == task_id, TaskResult.status == "pending")
            .update({TaskResult.status: "cancelled"}, synchronize_session=False)
        )
        counts = _batch_status_counts(db, task_id)
        _apply_batch_counts(task, counts)
        warnings = json.loads(task.warnings) if task.warnings else []
        warnings.append("用户已取消批量任务；当前正在生成的文件会完成本轮后停止后续文件。")
        task.warnings = json.dumps(warnings, ensure_ascii=False)
    task.status = "cancelled"
    task.completed_at = task.completed_at or datetime.utcnow()
    if task.started_at and task.completed_at:
        task.duration_seconds = (task.completed_at - task.started_at).total_seconds()
    db.commit()
    return ApiResponse(data={"id": task_id, "status": "cancelled"})
