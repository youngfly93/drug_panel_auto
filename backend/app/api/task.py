"""Task queue management endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.task import Task
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])


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
        items.append({
            "id": t.id,
            "task_type": t.task_type,
            "status": t.status,
            "project_type": t.project_type,
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

    return ApiResponse(data={
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "project_type": task.project_type,
        "total_files": task.total_files,
        "completed_files": task.completed_files,
        "failed_files": task.failed_files,
        "output_path": task.output_path,
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
