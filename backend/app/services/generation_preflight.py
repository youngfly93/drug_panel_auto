"""Pre-generation checks that prevent predictable production QA failures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.reportgen_bridge import ReportGenBridge

MISSING_MARKERS = {"", "-", "--", "未知", "未填写", "unknown", "none", "null", "nan", "n/a", "na"}


def required_date_fields(project_type: str | None) -> list[tuple[str, str]]:
    """Return date fields that must exist before generation for this panel."""
    required = [("report_date", "报告日期")]
    return required


def is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in MISSING_MARKERS
    return False


def validate_required_dates(
    bridge: ReportGenBridge,
    *,
    excel_path: str | Path,
    clinical_info: dict[str, Any] | None,
    project_type: str | None,
    project_name: str | None = None,
    excel_data: Any | None = None,
) -> dict[str, Any]:
    """Validate report/receive dates after merging clinical form fields.

    The returned payload is safe for API responses: it contains only field names
    and labels, not patient values or filenames.
    """
    if excel_data is None:
        excel_data = bridge.read_excel(str(excel_path))
    if clinical_info:
        inject_clinical_info = getattr(bridge, "_inject_clinical_info_into_excel", None)
        if callable(inject_clinical_info):
            inject_clinical_info(excel_data, clinical_info)

    effective_project_type = project_type
    effective_project_name = project_name
    if not effective_project_type:
        try:
            detected = bridge.detect_project_type(str(excel_path), excel_data=excel_data)
        except Exception:
            detected = {}
        effective_project_type = detected.get("project_type")
        effective_project_name = effective_project_name or detected.get("project_name")

    if not effective_project_type and effective_project_name:
        inferred = bridge.infer_project_type_from_text(effective_project_name)
        if inferred.get("detected"):
            effective_project_type = inferred.get("project_type")
            effective_project_name = effective_project_name or inferred.get("project_name")

    mapped_fields = bridge.get_mapped_clinical_fields(excel_data)
    if clinical_info:
        mapped_fields.update(
            {
                key: value
                for key, value in clinical_info.items()
                if value not in (None, "")
            }
        )
    missing = [
        {"field": field, "label": label}
        for field, label in required_date_fields(effective_project_type)
        if is_missing_value(mapped_fields.get(field))
    ]
    return {
        "ok": not missing,
        "project_type": effective_project_type,
        "project_name": effective_project_name,
        "missing": missing,
    }


def required_dates_error_message(missing: list[dict[str, str]]) -> str:
    labels = "、".join(item["label"] for item in missing)
    return f"生成前缺少必填日期：{labels}。请在临床信息表单或 Excel 中补齐后再生成。"
