"""Report generation and download endpoints."""

import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_bridge
from app.models.task import Task
from app.models.upload import Upload
from app.schemas.common import ApiResponse
from app.schemas.report import GenerateRequest, GenerateResponse, TaskStatus
from app.services.file_manager import ensure_report_dir
from app.services.reportgen_bridge import ReportGenBridge

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/generate", response_model=ApiResponse[GenerateResponse])
def generate_report(
    req: GenerateRequest,
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
):
    """Generate a single report (synchronous, 2-5s)."""
    upload = db.query(Upload).filter(Upload.id == req.upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="上传记录不存在")

    task_id = str(uuid.uuid4())
    output_dir = ensure_report_dir(task_id)

    # Create task record
    task = Task(
        id=task_id,
        upload_id=req.upload_id,
        task_type="single",
        status="running",
        project_type=req.project_type or upload.detected_project_type,
        clinical_info_snapshot=json.dumps(req.clinical_info, ensure_ascii=False) if req.clinical_info else None,
        started_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()

    try:
        result = bridge.generate_report(
            excel_path=upload.stored_path,
            output_dir=str(output_dir),
            template_name=req.template_name,
            clinical_info=req.clinical_info,
            project_type=req.project_type or upload.detected_project_type,
            strict_mode=req.strict_mode,
            template_contract_mode=req.template_contract_mode,
        )

        success = result.get("success", False)
        task.status = "completed" if success else "failed"
        task.output_path = result.get("output_file")
        task.duration_seconds = result.get("duration")
        task.errors = json.dumps(result.get("errors", []), ensure_ascii=False)
        task.warnings = json.dumps(result.get("warnings", []), ensure_ascii=False)
        task.completed_at = datetime.utcnow()
        db.commit()

        return ApiResponse(
            data=GenerateResponse(
                task_id=task_id,
                success=success,
                output_file=result.get("output_file"),
                duration_seconds=result.get("duration"),
                errors=result.get("errors", []),
                warnings=result.get("warnings", []),
            )
        )
    except Exception as e:
        task.status = "failed"
        task.errors = json.dumps([str(e)], ensure_ascii=False)
        task.completed_at = datetime.utcnow()
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


@router.get("/{task_id}", response_model=ApiResponse[TaskStatus])
def get_task_status(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return ApiResponse(
        data=TaskStatus(
            id=task.id,
            task_type=task.task_type,
            status=task.status,
            project_type=task.project_type,
            total_files=task.total_files,
            completed_files=task.completed_files,
            failed_files=task.failed_files,
            output_path=task.output_path,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            duration_seconds=task.duration_seconds,
            errors=json.loads(task.errors) if task.errors else [],
            warnings=json.loads(task.warnings) if task.warnings else [],
        )
    )


@router.get("/{task_id}/download")
def download_report(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.output_path:
        raise HTTPException(status_code=404, detail="报告文件不存在")

    file_path = Path(task.output_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="报告文件已被删除")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
