"""Pre-generation checks that prevent predictable production QA failures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reportgen.core.enhancer_registry import normalize_project_type
from reportgen.panels.input_contract import (
    input_contract_failures_as_missing,
    validate_excel_input_contract,
)
from reportgen.panels.loader import PanelPackageLoader

from app.config import settings
from app.services import clinical_info_service as clinical_svc
from app.services.reportgen_bridge import ReportGenBridge

MISSING_MARKERS = {"", "-", "--", "未知", "未填写", "unknown", "none", "null", "nan", "n/a", "na"}
FALLBACK_FIELD_LABELS = {
    "patient_name": "患者姓名",
    "sample_id": "样本编号",
    "report_number": "报告编号",
    "project_name": "项目名称",
    "report_date": "报告日期",
    "pdl1_tps": "PD-L1 TPS",
    "pdl1_cps": "PD-L1 CPS",
    "pdl1_result": "PD-L1结果",
    "pdl1_assay_profile_id": "PD-L1检测方案",
    "pdl1_source_record_id": "PD-L1原始记录编号",
    "pdl1_source_record_date": "PD-L1原始记录日期",
    "pdl1_specimen_id": "PD-L1检测标本标识",
    "pdl1_image_disposition": "PD-L1图像处置",
    "pdl1_image_path": "PD-L1病例图片",
    "lung_histology": "肺癌组织学类型",
    "disease_extent": "疾病范围/分期",
    "prior_systemic_therapy": "既往系统治疗情况",
    "companion_diagnostic_status": "伴随诊断符合状态",
    "tmb_value": "TMB",
    "msi_status": "MSI",
}


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


def required_input_fields(project_type: str | None) -> list[str]:
    """Return Panel-declared required scalar/biomarker fields."""
    if not project_type:
        return [field for field, _label in required_date_fields(project_type)]
    try:
        canonical = normalize_project_type(project_type) or project_type
        package = PanelPackageLoader(project_root=settings.upstream_root).load(canonical)
    except Exception:
        return [field for field, _label in required_date_fields(project_type)]

    contract = package.input_contract or {}
    required = [
        str(field).strip()
        for field in contract.get("required_single_fields") or []
        if str(field or "").strip()
    ]
    required.extend(field for field, _label in required_date_fields(project_type))
    biomarkers = contract.get("biomarkers") or {}
    if isinstance(biomarkers, dict):
        required.extend(
            str(field).strip()
            for field, field_contract in biomarkers.items()
            if isinstance(field_contract, dict)
            and field_contract.get("required") is True
            and str(field or "").strip()
        )

    ordered: list[str] = []
    seen: set[str] = set()
    for field in required:
        if field not in seen:
            seen.add(field)
            ordered.append(field)
    return ordered


def _input_contract(project_type: str | None) -> dict[str, Any]:
    if not project_type:
        return {}
    try:
        canonical = normalize_project_type(project_type) or project_type
        package = PanelPackageLoader(project_root=settings.upstream_root).load(canonical)
    except Exception:
        return {}
    return dict(package.input_contract or {})


def _field_labels(project_type: str | None) -> dict[str, str]:
    labels = dict(FALLBACK_FIELD_LABELS)
    try:
        schema = clinical_svc.get_clinical_form_schema(project_type)
    except Exception:
        return labels
    for group in schema.groups:
        for field in group.fields:
            labels[field.key] = field.label
    return labels


def _resolve_mapped_fields(
    bridge: ReportGenBridge,
    *,
    excel_path: str | Path,
    clinical_info: dict[str, Any] | None,
    project_type: str | None,
    project_name: str | None,
    excel_data: Any | None,
) -> tuple[dict[str, Any], str | None, str | None]:
    if excel_data is None:
        excel_data = bridge.read_excel(str(excel_path))

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
            {key: value for key, value in clinical_info.items() if value not in (None, "")}
        )
    if effective_project_name:
        mapped_fields["project_name"] = effective_project_name
    return mapped_fields, effective_project_type, effective_project_name


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
    mapped_fields, effective_project_type, effective_project_name = _resolve_mapped_fields(
        bridge,
        excel_path=excel_path,
        clinical_info=clinical_info,
        project_type=project_type,
        project_name=project_name,
        excel_data=excel_data,
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


def validate_required_inputs(
    bridge: ReportGenBridge,
    *,
    excel_path: str | Path,
    clinical_info: dict[str, Any] | None,
    project_type: str | None,
    project_name: str | None = None,
    excel_data: Any | None = None,
) -> dict[str, Any]:
    """Validate all Panel-required scalar inputs before a task is created."""
    mapped_fields, effective_project_type, effective_project_name = _resolve_mapped_fields(
        bridge,
        excel_path=excel_path,
        clinical_info=clinical_info,
        project_type=project_type,
        project_name=project_name,
        excel_data=excel_data,
    )
    labels = _field_labels(effective_project_type)
    missing = [
        {"field": field, "label": labels.get(field, field)}
        for field in required_input_fields(effective_project_type)
        if is_missing_value(mapped_fields.get(field))
    ]
    structural_failures = validate_excel_input_contract(
        excel_data,
        _input_contract(effective_project_type),
    )
    missing.extend(input_contract_failures_as_missing(structural_failures))
    return {
        "ok": not missing,
        "project_type": effective_project_type,
        "project_name": effective_project_name,
        "missing": missing,
        "input_contract_failures": structural_failures,
    }


def required_dates_error_message(missing: list[dict[str, str]]) -> str:
    labels = "、".join(item["label"] for item in missing)
    return f"生成前缺少必填日期：{labels}。请在临床信息表单或 Excel 中补齐后再生成。"


def required_inputs_error_message(missing: list[dict[str, str]]) -> str:
    labels = "、".join(item["label"] for item in missing)
    return f"生成前缺少必填信息：{labels}。请在临床信息表单或 Excel 中补齐后再生成。"
