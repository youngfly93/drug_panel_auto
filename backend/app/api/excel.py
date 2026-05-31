"""Excel upload and preview endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_bridge
from app.models.upload import Upload
from app.schemas.common import ApiResponse
from app.schemas.excel import (
    DetectResult,
    InspectResponse,
    SheetData,
    SheetInfo,
    SingleValuesResponse,
    UploadResponse,
)
from app.services.file_manager import save_upload
from app.services import clinical_info_service as clinical_svc
from app.services.reportgen_bridge import ReportGenBridge

router = APIRouter(prefix="/excel", tags=["excel"])

# In-memory cache for parsed Excel data (upload_id -> ExcelDataSource)
_excel_cache: dict = {}


def _get_excel_data(upload: Upload, bridge: ReportGenBridge):
    """Get or parse Excel data, with caching."""
    if upload.id not in _excel_cache:
        _excel_cache[upload.id] = bridge.read_excel(upload.stored_path)
    return _excel_cache[upload.id]


@router.post("/upload", response_model=ApiResponse[UploadResponse])
def upload_excel(
    file: UploadFile,
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
):
    # Validate extension
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式文件")

    # Save to disk
    upload_id, stored_path, file_size = save_upload(file)

    # Parse Excel
    try:
        excel_data = bridge.read_excel(str(stored_path))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel解析失败: {e}")

    sheet_names = bridge.get_sheet_names(excel_data)
    _excel_cache[upload_id] = excel_data

    # Detect project type using ORIGINAL filename (not UUID stored path)
    # This is critical: upstream ProjectDetector matches keywords in filename
    detect = bridge.detect_project_type(
        str(Path(stored_path).parent / (file.filename or "upload.xlsx")),
        excel_data=excel_data,
    )

    # Run data validation (Issue 1/2/3 checks)
    validation_warnings = bridge.validate_excel_data(excel_data)

    # Persist upload record
    record = Upload(
        id=upload_id,
        original_filename=file.filename,
        stored_path=str(stored_path),
        file_size_bytes=file_size,
        sheet_names=json.dumps(sheet_names, ensure_ascii=False),
        detected_project_type=detect.get("project_type"),
        detected_project_name=detect.get("project_name"),
        detection_confidence=detect.get("confidence"),
        status="completed",
    )
    db.add(record)
    db.commit()

    return ApiResponse(
        data=UploadResponse(
            upload_id=upload_id,
            original_filename=file.filename,
            file_size_bytes=file_size,
            sheet_names=sheet_names,
            detected_project_type=detect.get("project_type"),
            detected_project_name=detect.get("project_name"),
            detection_confidence=detect.get("confidence"),
            validation_warnings=validation_warnings,
        )
    )


@router.post("/inspect", response_model=ApiResponse[InspectResponse])
def inspect_excel(
    file: UploadFile,
    bridge: ReportGenBridge = Depends(get_bridge),
):
    """Inspect Excel content in one request for stateless preview deployments."""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式文件")

    upload_id, stored_path, file_size = save_upload(file)
    try:
        excel_data = bridge.read_excel(str(stored_path))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel解析失败: {e}") from e

    sheet_names = bridge.get_sheet_names(excel_data)
    sheets = [
        SheetInfo(
            name=name,
            **bridge.get_sheet_info(excel_data, name, excel_path=str(stored_path)),
        )
        for name in sheet_names
    ]
    detect = bridge.detect_project_type(
        str(Path(stored_path).parent / (file.filename or "upload.xlsx")),
        excel_data=excel_data,
    )
    validation_warnings = bridge.validate_excel_data(excel_data)

    single_values = bridge.get_mapped_clinical_fields(excel_data)
    sample_id = single_values.get("sample_id")
    enrichment = None
    if sample_id:
        enrichment = clinical_svc.enrich_patient(
            str(sample_id),
            project_type=detect.get("project_type"),
        )
        single_values = clinical_svc.merge_enrichment_into_values(
            single_values,
            enrichment,
        )

    preview_summary = None
    try:
        preview_summary = bridge.build_preview_summary(
            excel_data=excel_data,
            clinical_info=single_values,
            project_type=detect.get("project_type"),
            project_name=detect.get("project_name"),
        )
    except Exception as exc:
        validation_warnings.append(
            {
                "level": "warning",
                "field": "preview_summary",
                "message": f"上传后结果预览生成失败: {exc}",
            }
        )

    upload = UploadResponse(
        upload_id=upload_id,
        original_filename=file.filename,
        file_size_bytes=file_size,
        sheet_names=sheet_names,
        detected_project_type=detect.get("project_type"),
        detected_project_name=detect.get("project_name"),
        detection_confidence=detect.get("confidence"),
        validation_warnings=validation_warnings,
    )

    return ApiResponse(
        data=InspectResponse(
            upload=upload,
            sheets=sheets,
            single_values=single_values,
            patient_enrichment=(
                enrichment.model_dump() if enrichment is not None else None
            ),
            preview_summary=preview_summary,
        )
    )


@router.get("/{upload_id}/sheets", response_model=ApiResponse[list[SheetInfo]])
def list_sheets(
    upload_id: str,
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
):
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="上传记录不存在")

    excel_data = _get_excel_data(upload, bridge)
    sheets = []
    for name in bridge.get_sheet_names(excel_data):
        info = bridge.get_sheet_info(excel_data, name, excel_path=upload.stored_path)
        sheets.append(SheetInfo(name=name, rows=info["rows"], columns=info["columns"]))

    return ApiResponse(data=sheets)


@router.get("/{upload_id}/sheets/{sheet_name}", response_model=ApiResponse[SheetData])
def get_sheet_data(
    upload_id: str,
    sheet_name: str,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
):
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="上传记录不存在")

    excel_data = _get_excel_data(upload, bridge)
    result = bridge.get_table_data(
        excel_data,
        sheet_name,
        page=page,
        page_size=page_size,
        excel_path=upload.stored_path,
    )

    return ApiResponse(
        data=SheetData(
            name=sheet_name,
            columns=result["columns"],
            rows=result["rows"],
            total_rows=result["total_rows"],
            page=result["page"],
            page_size=result["page_size"],
        )
    )


@router.get(
    "/{upload_id}/single-values", response_model=ApiResponse[SingleValuesResponse]
)
def get_single_values(
    upload_id: str,
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
):
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="上传记录不存在")

    excel_data = _get_excel_data(upload, bridge)
    values = bridge.get_mapped_clinical_fields(excel_data)
    return ApiResponse(data=SingleValuesResponse(fields=values))


@router.get("/{upload_id}/detect", response_model=ApiResponse[DetectResult])
def detect_project_type(
    upload_id: str,
    db: Session = Depends(get_db),
    bridge: ReportGenBridge = Depends(get_bridge),
):
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="上传记录不存在")

    excel_data = _get_excel_data(upload, bridge)
    result = bridge.detect_project_type(upload.stored_path, excel_data=excel_data)
    return ApiResponse(
        data=DetectResult(
            project_type=result.get("project_type"),
            project_name=result.get("project_name"),
            confidence=result.get("confidence"),
        )
    )
