"""Task queue management endpoints."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.task import Task
from app.schemas.common import ApiResponse
from app.services import reference_report_service as diff_svc

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _qa_sidecar_path(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    return Path(output_path).with_suffix(".qa.json")


def _stage_results_sidecar_path(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    return Path(output_path).with_suffix(".stage_results.json")


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
) -> tuple[str | None, str | None]:
    stage_path = _stage_results_sidecar_path(output_path)
    if not stage_path or not stage_path.exists():
        return None, None
    try:
        payload = json.loads(stage_path.read_text(encoding="utf-8"))
    except Exception:
        return str(stage_path), None
    return str(stage_path), payload.get("generation_id")


@router.get("", response_model=ApiResponse)
def list_tasks(
    status: str = Query(None, description="Filter by status"),
    task_type: str = Query(None, description="Filter by type: single|batch"),
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    query = db.query(Task).order_by(Task.created_at.desc())
    if status:
        query = query.filter(Task.status == status)
    if task_type:
        query = query.filter(Task.task_type == task_type)

    total = query.count()
    tasks = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for t in tasks:
        qa_report_file, qa_status = _load_qa_summary(t.output_path)
        stage_results_file, generation_id = _load_stage_results_summary(t.output_path)
        diff_summary = diff_svc.report_diff_summary(t.output_path)
        items.append({
            "id": t.id,
            "task_type": t.task_type,
            "status": t.status,
            "project_type": t.project_type,
            "qa_status": qa_status,
            "qa_report_file": qa_report_file,
            "generation_id": generation_id,
            "stage_results_file": stage_results_file,
            "diff_status": diff_summary.get("diff_status"),
            "diff_gate_passed": diff_summary.get("diff_gate_passed"),
            "diff_reference_id": diff_summary.get("diff_reference_id"),
            "diff_reference_name": diff_summary.get("diff_reference_name"),
            "total_files": t.total_files,
            "completed_files": t.completed_files,
            "failed_files": t.failed_files,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "duration_seconds": t.duration_seconds,
            "errors": json.loads(t.errors) if t.errors else [],
        })

    return ApiResponse(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/stats", response_model=ApiResponse)
def task_stats(db: Session = Depends(get_db)):
    total = db.query(Task).count()
    completed = db.query(Task).filter(Task.status == "completed").count()
    failed = db.query(Task).filter(Task.status == "failed").count()
    running = db.query(Task).filter(Task.status == "running").count()
    pending = db.query(Task).filter(Task.status == "pending").count()

    return ApiResponse(data={
        "total": total,
        "completed": completed,
        "failed": failed,
        "running": running,
        "pending": pending,
    })


@router.get("/{task_id}", response_model=ApiResponse)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    qa_report_file, qa_status = _load_qa_summary(task.output_path)
    stage_results_file, generation_id = _load_stage_results_summary(task.output_path)
    diff_summary = diff_svc.report_diff_summary(task.output_path)

    return ApiResponse(data={
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "project_type": task.project_type,
        "total_files": task.total_files,
        "completed_files": task.completed_files,
        "failed_files": task.failed_files,
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

    task.status = "cancelled"
    db.commit()
    return ApiResponse(data={"id": task_id, "status": "cancelled"})
