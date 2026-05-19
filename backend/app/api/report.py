"""Report generation and download endpoints."""

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from reportgen.utils.docx_render import render_docx_to_pngs
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_bridge
from app.models.task import Task
from app.models.upload import Upload
from app.schemas.common import ApiResponse
from app.schemas.report import GenerateRequest, GenerateResponse, TaskStatus
from app.services import reference_report_service as diff_svc
from app.services.file_manager import ensure_report_dir
from app.services.reportgen_bridge import ReportGenBridge

router = APIRouter(prefix="/reports", tags=["reports"])


def _qa_sidecar_path(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    return Path(output_path).with_suffix(".qa.json")


def _field_provenance_sidecar_path(output_path: Optional[str]) -> Optional[Path]:
    if not output_path:
        return None
    return Path(output_path).with_suffix(".field_provenance.json")


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
        clinical_info_snapshot=(
            json.dumps(req.clinical_info, ensure_ascii=False)
            if req.clinical_info
            else None
        ),
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
            project_name=req.project_name or upload.detected_project_name,
            strict_mode=req.strict_mode,
            template_contract_mode=req.template_contract_mode,
        )

        success = result.get("success", False)
        task.status = "completed" if success else "failed"
        task.output_path = result.get("output_file")
        task.duration_seconds = result.get("duration")
        warnings = list(result.get("warnings", []) or [])
        auto_diff_result = None
        if success and task.output_path:
            try:
                auto_diff_result = diff_svc.run_auto_reference_diff(
                    db,
                    task,
                    fail_on="fail",
                    max_samples=50,
                )
            except Exception as exc:
                warnings.append(f"自动基准对比失败: {exc}")
        task.errors = json.dumps(result.get("errors", []), ensure_ascii=False)
        task.warnings = json.dumps(warnings, ensure_ascii=False)
        task.completed_at = datetime.utcnow()
        db.commit()
        diff_summary = diff_svc.report_diff_summary(task.output_path)

        return ApiResponse(
            data=GenerateResponse(
                task_id=task_id,
                success=success,
                output_file=result.get("output_file"),
                field_provenance_file=result.get("field_provenance_file"),
                qa_report_file=result.get("qa_report_file"),
                qa_status=result.get("qa_status"),
                qa_issues=(result.get("qa_report") or {}).get("issues") or [],
                panel_package_validation=result.get("panel_package_validation"),
                diff_status=diff_summary.get("diff_status"),
                diff_gate_passed=diff_summary.get("diff_gate_passed"),
                diff_reference_id=diff_summary.get("diff_reference_id"),
                diff_reference_name=diff_summary.get("diff_reference_name"),
                diff_auto_ran=auto_diff_result is not None,
                duration_seconds=result.get("duration"),
                errors=result.get("errors", []),
                warnings=warnings,
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
    field_provenance_path = _field_provenance_sidecar_path(task.output_path)
    qa_report_file, qa_status, _qa_issues = _load_qa_summary(task.output_path)
    diff_summary = diff_svc.report_diff_summary(task.output_path)

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
            field_provenance_file=str(field_provenance_path)
            if field_provenance_path and field_provenance_path.exists()
            else None,
            qa_report_file=qa_report_file,
            qa_status=qa_status,
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
        with reference_path.open("wb") as fh:
            shutil.copyfileobj(reference.file, fh)
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
            "name": reference.filename,
            "active": False,
        },
    )
    return ApiResponse(data=result)


@router.post("/{task_id}/diff/auto", response_model=ApiResponse[dict])
def diff_report_against_registered_reference(
    task_id: str,
    fail_on: str = Query("fail", pattern="^(fail|warn)$"),
    max_samples: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Compare a generated report against the active panel/case reference report."""
    task = _get_single_report_task(task_id, db)
    result = diff_svc.run_auto_reference_diff(
        db,
        task,
        fail_on=fail_on,
        max_samples=max_samples,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="未找到匹配的启用基准报告")
    return ApiResponse(data=result)


@router.post("/{task_id}/diff/batch/auto", response_model=ApiResponse[dict])
def diff_batch_report_against_registered_references(
    task_id: str,
    fail_on: str = Query("fail", pattern="^(fail|warn)$"),
    max_samples: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Run reference diff for every generated report in a batch task."""
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
    return FileResponse(path=str(artifact_path), filename=filename, media_type=media_type)


@router.get("/{task_id}/diff/batch/items/{item_key}/download/{filename}")
def download_batch_report_diff_item_artifact(
    task_id: str,
    item_key: str,
    filename: str,
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
    return FileResponse(path=str(artifact_path), filename=filename, media_type=media_type)


@router.get("/{task_id}/diff/download/{filename}")
def download_report_diff_artifact(
    task_id: str,
    filename: str,
    db: Session = Depends(get_db),
):
    """Download report diff JSON or Markdown for a task."""
    task = _get_single_report_task(task_id, db)
    artifact_path = _report_diff_artifact_path(task.output_path, filename)
    if not artifact_path or not artifact_path.exists():
        raise HTTPException(status_code=404, detail="报告对比产物不存在")
    media_type = "application/json" if filename.endswith(".json") else "text/markdown"
    return FileResponse(
        path=str(artifact_path),
        filename=filename,
        media_type=media_type,
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
