"""Excel upload and preview schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ValidationWarning(BaseModel):
    level: str  # "warning" | "error" | "info"
    field: str
    message: str


class UploadResponse(BaseModel):
    upload_id: str
    original_filename: str
    file_size_bytes: int
    sheet_names: list[str]
    detected_project_type: Optional[str] = None
    detected_project_name: Optional[str] = None
    detection_confidence: Optional[float] = None
    validation_warnings: list[ValidationWarning] = []


class SheetInfo(BaseModel):
    name: str
    rows: int
    columns: int


class SheetData(BaseModel):
    name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int
    page: int
    page_size: int


class SingleValuesResponse(BaseModel):
    fields: dict[str, Any]


class DetectResult(BaseModel):
    project_type: Optional[str] = None
    project_name: Optional[str] = None
    confidence: Optional[float] = None
