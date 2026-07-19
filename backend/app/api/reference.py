"""Reference report management endpoints."""

from pathlib import Path
from typing import Optional

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
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_knowledge_manager
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.reference import ReferenceReportList, ReferenceReportOut
from app.services import reference_report_service as svc
from app.services.audit_log import record_audit_event
from app.services.file_manager import safe_client_filename

router = APIRouter(prefix="/reference-reports", tags=["reference-reports"])


def _reference_out(reference) -> ReferenceReportOut:
    return ReferenceReportOut.model_validate(reference).model_copy(
        update={
            "formal_golden_verified": bool(
                svc.load_verified_formal_golden_attestation(reference)
            )
        }
    )


@router.get("", response_model=ApiResponse[ReferenceReportList])
def list_reference_reports(
    panel_id: Optional[str] = Query(None),
    case_id: Optional[str] = Query(None),
    active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    references = svc.list_reference_reports(
        db,
        panel_id=panel_id,
        case_id=case_id,
        active=active,
    )
    return ApiResponse(
        data=ReferenceReportList(
            items=[_reference_out(item) for item in references],
            total=len(references),
        )
    )


@router.post("", response_model=ApiResponse[ReferenceReportOut])
def upload_reference_report(
    request: Request,
    panel_id: str = Form(...),
    case_id: str = Form(...),
    name: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    active: bool = Form(True),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _manager: User = Depends(require_knowledge_manager),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少金标准文件名")
    original_filename = safe_client_filename(file.filename, "reference.docx")
    try:
        reference = svc.create_reference_report(
            db,
            panel_id=panel_id,
            case_id=case_id,
            name=name,
            notes=notes,
            active=active,
            original_filename=original_filename,
            fileobj=file.file,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        try:
            file.file.close()
        except Exception:
            pass
    record_audit_event(
        db,
        action="reference.created",
        resource_type="reference_report",
        resource_id=reference.id,
        request=request,
        details={
            "source": "reference-library",
            "project_type": reference.panel_id,
            "status": "active" if reference.active else "inactive",
        },
    )
    return ApiResponse(data=_reference_out(reference))


@router.post("/{reference_id}/activate", response_model=ApiResponse[ReferenceReportOut])
def activate_reference_report(
    reference_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_knowledge_manager),
):
    reference = svc.get_reference_report(db, reference_id)
    if not reference:
        raise HTTPException(status_code=404, detail="基准报告不存在")
    reference = svc.activate_reference_report(db, reference)
    record_audit_event(
        db,
        action="reference.activated",
        resource_type="reference_report",
        resource_id=reference.id,
        request=request,
        details={
            "source": "reference-library",
            "project_type": reference.panel_id,
            "status": "active",
        },
    )
    return ApiResponse(data=_reference_out(reference))


@router.delete("/{reference_id}", response_model=ApiResponse)
def delete_reference_report(
    reference_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_knowledge_manager),
):
    reference = svc.get_reference_report(db, reference_id)
    if not reference:
        raise HTTPException(status_code=404, detail="基准报告不存在")
    panel_id = reference.panel_id
    svc.delete_reference_report(db, reference)
    record_audit_event(
        db,
        action="reference.deleted",
        resource_type="reference_report",
        resource_id=reference_id,
        request=request,
        details={
            "source": "reference-library",
            "project_type": panel_id,
            "status": "deleted",
        },
    )
    return ApiResponse(data={"id": reference_id})


@router.get("/{reference_id}/download")
def download_reference_report(reference_id: str, db: Session = Depends(get_db)):
    reference = svc.get_reference_report(db, reference_id)
    if not reference:
        raise HTTPException(status_code=404, detail="基准报告不存在")
    path = Path(reference.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="基准报告文件已被删除")
    return FileResponse(
        path=str(path),
        filename=reference.original_filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
