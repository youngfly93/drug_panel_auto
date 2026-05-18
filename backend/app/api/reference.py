"""Reference report management endpoints."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.reference import ReferenceReportList, ReferenceReportOut
from app.services import reference_report_service as svc

router = APIRouter(prefix="/reference-reports", tags=["reference-reports"])


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
            items=[ReferenceReportOut.model_validate(item) for item in references],
            total=len(references),
        )
    )


@router.post("", response_model=ApiResponse[ReferenceReportOut])
def upload_reference_report(
    panel_id: str = Form(...),
    case_id: str = Form(...),
    name: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    active: bool = Form(True),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        reference = svc.create_reference_report(
            db,
            panel_id=panel_id,
            case_id=case_id,
            name=name,
            notes=notes,
            active=active,
            original_filename=file.filename or "reference.docx",
            fileobj=file.file,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        try:
            file.file.close()
        except Exception:
            pass
    return ApiResponse(data=ReferenceReportOut.model_validate(reference))


@router.post("/{reference_id}/activate", response_model=ApiResponse[ReferenceReportOut])
def activate_reference_report(reference_id: str, db: Session = Depends(get_db)):
    reference = svc.get_reference_report(db, reference_id)
    if not reference:
        raise HTTPException(status_code=404, detail="基准报告不存在")
    reference = svc.activate_reference_report(db, reference)
    return ApiResponse(data=ReferenceReportOut.model_validate(reference))


@router.delete("/{reference_id}", response_model=ApiResponse)
def delete_reference_report(reference_id: str, db: Session = Depends(get_db)):
    reference = svc.get_reference_report(db, reference_id)
    if not reference:
        raise HTTPException(status_code=404, detail="基准报告不存在")
    svc.delete_reference_report(db, reference)
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
