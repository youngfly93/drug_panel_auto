"""Report generation schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class GenerateRequest(BaseModel):
    upload_id: str
    clinical_info: dict[str, Any] = {}
    project_type: Optional[str] = None
    project_name: Optional[str] = None
    template_name: Optional[str] = None
    strict_mode: bool = False
    template_contract_mode: str = "warn"


class GenerateResponse(BaseModel):
    task_id: str
    success: bool
    output_file: Optional[str] = None
    duration_seconds: Optional[float] = None
    errors: list[str] = []
    warnings: list[str] = []


class TaskStatus(BaseModel):
    id: str
    task_type: str
    status: str
    project_type: Optional[str] = None
    total_files: int = 1
    completed_files: int = 0
    failed_files: int = 0
    output_path: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    errors: list[str] = []
    warnings: list[str] = []
