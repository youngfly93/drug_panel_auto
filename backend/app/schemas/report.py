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
    qa_visual_render: Optional[str] = None
    qa_visual_render_required: Optional[bool] = None
    qa_visual_render_dpi: Optional[int] = None
    qa_visual_render_timeout_seconds: Optional[int] = None


class GenerateResponse(BaseModel):
    task_id: str
    success: bool
    output_file: Optional[str] = None
    field_provenance_file: Optional[str] = None
    qa_report_file: Optional[str] = None
    qa_status: Optional[str] = None
    qa_issues: list[dict[str, Any]] = []
    visual_render: Optional[dict[str, Any]] = None
    panel_package_validation: Optional[dict[str, Any]] = None
    generation_id: Optional[str] = None
    stage_results: list[dict[str, Any]] = []
    stage_results_file: Optional[str] = None
    diff_status: Optional[str] = None
    diff_gate_passed: Optional[bool] = None
    diff_reference_id: Optional[str] = None
    diff_reference_name: Optional[str] = None
    diff_auto_ran: bool = False
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
    field_provenance_file: Optional[str] = None
    qa_report_file: Optional[str] = None
    qa_status: Optional[str] = None
    generation_id: Optional[str] = None
    stage_results_file: Optional[str] = None
    stage_results: list[dict[str, Any]] = []
    diff_report_file: Optional[str] = None
    diff_markdown_file: Optional[str] = None
    diff_status: Optional[str] = None
    diff_gate_passed: Optional[bool] = None
    diff_reference_id: Optional[str] = None
    diff_reference_name: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    errors: list[str] = []
    warnings: list[str] = []
