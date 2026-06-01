"""Batch report generation endpoints."""

import asyncio
import json
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
    HTTPException,
    Request,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.dependencies import get_bridge
from app.models.task import Task, TaskResult
from app.models.upload import Upload
from app.schemas.common import ApiResponse
from app.services import clinical_info_service as clinical_svc
from app.services.audit_log import record_audit_event
from app.services.file_manager import ensure_report_dir, save_upload
from app.services.generation_process import run_generate_report_with_timeout
from app.services.generation_queue import submit_generation_job
from app.services import reference_report_service as diff_svc
from app.services.reportgen_bridge import ReportGenBridge
from app.services.task_manager import submit_batch_task

router = APIRouter(prefix="/reports", tags=["reports-batch"])


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


def _enrich_clinical_payload(
    clinical_info: Optional[dict],
    project_type: Optional[str],
) -> dict:
    payload = dict(clinical_info or {})
    sample_id = str(payload.get("sample_id") or payload.get("样本编号") or "").strip()
    if not sample_id:
        return payload
    enrichment = clinical_svc.enrich_patient(sample_id, project_type=project_type)
    return clinical_svc.merge_enrichment_into_values(payload, enrichment)


def _batch_report_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / "batch_report.json"


def _batch_inputs_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / "batch_inputs.private.json"


def _batch_status_counts(results: list[TaskResult]) -> dict[str, int]:
    counts = {
        "pending": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
    }
    for result in results:
        status = result.status or "pending"
        counts[status] = counts.get(status, 0) + 1
    return counts


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
) -> dict:
    payload = {
        "schema_version": "1.0",
        "created_at": datetime.utcnow().isoformat(),
        "task_id": task_id,
        "project_type": project_type,
        "project_name": project_name,
        "template_name": template_name,
        "template_contract_mode": template_contract_mode,
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
        "generated_at": datetime.utcnow().isoformat(),
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


def _build_item_payload(
    *,
    stored_path: str,
    original_filename: str,
    bridge: ReportGenBridge,
    shared_clinical_info: dict,
    project_type: Optional[str],
    project_name: Optional[str],
    template_name: Optional[str],
    output_dir: str,
    template_contract_mode: str,
) -> tuple[dict, dict, Optional[str], Optional[str]]:
    excel_data = bridge.read_excel(stored_path)
    detected_project_type = project_type
    detected_project_name = project_name
    if not detected_project_type:
        detect = bridge.detect_project_type(stored_path, excel_data=excel_data)
        detected_project_type = detect.get("project_type")
        detected_project_name = detected_project_name or detect.get("project_name")
    detected_project_type, detected_project_name = _infer_project_type_from_name(
        bridge,
        detected_project_type,
        detected_project_name or shared_clinical_info.get("project_name"),
    )

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
    )

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
    bridge: ReportGenBridge,
) -> None:
    db = SessionLocal()
    start_time = datetime.utcnow()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return
        if task.status == "cancelled":
            return
        task.status = "running"
        task.started_at = task.started_at or start_time
        task.output_path = output_dir
        db.commit()

        for item in items:
            task = db.query(Task).filter(Task.id == task_id).first()
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
            row.status = "running"
            db.commit()

            started = datetime.utcnow()
            try:
                result, validation_summary, _ptype, _pname = _build_item_payload(
                    stored_path=item["stored_path"],
                    original_filename=item["filename"],
                    bridge=bridge,
                    shared_clinical_info=shared_clinical_info,
                    project_type=project_type,
                    project_name=project_name,
                    template_name=template_name,
                    output_dir=output_dir,
                    template_contract_mode=template_contract_mode,
                )
                success = bool(result.get("success"))
                row.status = "completed" if success else "failed"
                row.output_path = result.get("output_file")
                row.duration_seconds = result.get("duration")
                row.errors = json.dumps(result.get("errors") or [], ensure_ascii=False)
                row.warnings = json.dumps(
                    result.get("warnings") or [],
                    ensure_ascii=False,
                )
                row.validation_summary = json.dumps(
                    validation_summary,
                    ensure_ascii=False,
                )
            except Exception as exc:
                row.status = "failed"
                row.duration_seconds = (datetime.utcnow() - started).total_seconds()
                row.errors = json.dumps([str(exc)], ensure_ascii=False)
                row.warnings = json.dumps([], ensure_ascii=False)
                row.validation_summary = json.dumps({}, ensure_ascii=False)

            task = db.query(Task).filter(Task.id == task_id).first()
            task.completed_files = (
                db.query(TaskResult)
                .filter(TaskResult.task_id == task_id, TaskResult.status == "completed")
                .count()
            )
            task.failed_files = (
                db.query(TaskResult)
                .filter(TaskResult.task_id == task_id, TaskResult.status == "failed")
                .count()
            )
            task.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
            db.commit()
            _write_batch_report(db, task)

        task = db.query(Task).filter(Task.id == task_id).first()
        if task and task.status != "cancelled":
            task.completed_files = (
                db.query(TaskResult)
                .filter(TaskResult.task_id == task_id, TaskResult.status == "completed")
                .count()
            )
            task.failed_files = (
                db.query(TaskResult)
                .filter(TaskResult.task_id == task_id, TaskResult.status == "failed")
                .count()
            )
            task.status = _resolve_batch_status(
                completed=task.completed_files,
                failed=task.failed_files,
                total=task.total_files,
            )
            task.completed_at = datetime.utcnow()
            task.duration_seconds = (task.completed_at - start_time).total_seconds()
            warnings = []
            batch_report = _write_batch_report(db, task)
            if task.completed_files:
                try:
                    diff_payload = diff_svc.run_batch_reference_diff(
                        db,
                        task,
                        batch_report,
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
            db.commit()
            _write_batch_report(db, task)
    except Exception as exc:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = "failed"
            task.errors = json.dumps([str(exc)], ensure_ascii=False)
            task.completed_at = datetime.utcnow()
            task.duration_seconds = (task.completed_at - start_time).total_seconds()
            db.commit()
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


@router.post("/batch-files", response_model=ApiResponse)
def batch_generate_from_files(
    request: Request,
    files: list[UploadFile] = File(...),
    clinical_info: str = Form("{}"),
    project_type: Optional[str] = Form(None),
    project_name: Optional[str] = Form(None),
    template_name: Optional[str] = Form(None),
    template_contract_mode: str = Form("warn"),
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
):
    """Start a production batch task from multiple uploaded Excel files."""
    excel_files = [file for file in files if file.filename]
    if not excel_files:
        raise HTTPException(status_code=400, detail="请至少上传 1 个 Excel 文件")
    for file in excel_files:
        if not file.filename.lower().endswith(".xlsx"):
            raise HTTPException(status_code=400, detail=f"仅支持 .xlsx 文件: {file.filename}")
        if file.filename.startswith("._") or file.filename.startswith("~$"):
            raise HTTPException(status_code=400, detail=f"请移除临时文件: {file.filename}")

    try:
        shared_clinical_info = json.loads(clinical_info or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"临床信息不是合法 JSON: {exc}",
        ) from exc
    if not isinstance(shared_clinical_info, dict):
        raise HTTPException(status_code=400, detail="临床信息必须是 JSON 对象")

    task_id = str(uuid.uuid4())
    output_dir = ensure_report_dir(task_id)
    items: list[dict] = []
    for index, file in enumerate(excel_files, start=1):
        _upload_id, stored_path, _file_size = save_upload(file)
        items.append(
            {
                "index": index,
                "filename": file.filename,
                "stored_path": str(stored_path),
            }
        )

    task = Task(
        id=task_id,
        task_type="batch",
        status="pending",
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
    db.add(task)
    for item in items:
        db.add(
            TaskResult(
                task_id=task_id,
                file_index=item["index"],
                excel_filename=item["filename"],
                status="pending",
            )
        )
    db.commit()
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
            "status": "pending",
            "total_files": len(items),
        },
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
        bridge=bridge,
    )

    return ApiResponse(
        data={
            "task_id": task_id,
            "status": "pending",
            "total_files": len(items),
        }
    )


@router.post("/{task_id}/batch/retry-failed", response_model=ApiResponse)
def retry_failed_batch_files(
    task_id: str,
    request: Request,
    include_cancelled: bool = False,
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
):
    """Retry failed rows in a file-based batch task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.task_type != "batch":
        raise HTTPException(status_code=400, detail="仅批量任务支持失败重试")
    if task.status in {"running", "pending"}:
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
        row.status = "pending"
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

    task.status = "pending"
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
            "status": "pending",
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
        bridge=bridge,
    )

    return ApiResponse(
        data={
            "task_id": task_id,
            "status": "pending",
            "retry_files": len(retry_items),
            "total_files": task.total_files,
        }
    )
