"""Batch report generation endpoints."""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models.task import Task
from app.models.upload import Upload
from app.schemas.common import ApiResponse
from app.services.file_manager import ensure_report_dir
from app.services.task_manager import submit_batch_task

router = APIRouter(prefix="/reports", tags=["reports-batch"])


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
        else:
            task.status = "failed"
            task.errors = json.dumps([result.get("error", "Unknown error")], ensure_ascii=False)

        task.completed_at = datetime.utcnow()
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
):
    """
    Submit a batch generation task.

    Provide either upload_ids (list of previously uploaded files)
    or input_dir (directory path containing Excel files).
    """
    task_id = str(uuid.uuid4())
    output_dir = ensure_report_dir(task_id)

    # Resolve input paths
    input_paths: list[str] = []
    if upload_ids:
        for uid in upload_ids:
            upload = db.query(Upload).filter(Upload.id == uid).first()
            if upload:
                input_paths.append(upload.stored_path)
    elif input_dir:
        input_paths.append(input_dir)
    else:
        raise HTTPException(status_code=400, detail="请提供 upload_ids 或 input_dir")

    total_files = len(input_paths) if upload_ids else 0  # unknown for dir

    # Create task record
    task = Task(
        id=task_id,
        task_type="batch",
        status="running",
        project_type=project_type,
        total_files=total_files,
        started_at=datetime.utcnow(),
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
