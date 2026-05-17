"""
Field provenance sidecar for generated reports.

The goal is not to rebuild the whole mapper. It records enough source evidence
for high-risk fields so operators can explain why a rendered value appeared in
the final report.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from reportgen.config.loader import ConfigLoader
from reportgen.models.excel_data import ExcelDataSource
from reportgen.models.report_data import ReportData
from reportgen.utils.artifacts import write_json


SOURCE_PRECEDENCE = ["form", "excel", "patient_info", "filename", "rule", "default"]
KEY_FIELDS = [
    "patient_name",
    "sample_id",
    "report_number",
    "pathology_id",
    "project_type",
    "project_name",
    "report_date",
    "gender",
    "age",
    "cancer_type",
    "sample_type",
    "tmb_value",
    "tmb_status",
    "msi_status",
]
SENSITIVE_FIELDS = {
    "patient_name",
    "sample_id",
    "report_number",
    "pathology_id",
}
DERIVED_FIELDS = {
    "project_type",
    "project_name",
    "tmb_status",
    "tmb_level_cn",
    "tmb_reference",
    "tmb_summary",
    "msi_status_cn",
    "msi_summary",
    "total_variants_count",
    "drug_related_count",
}


def build_field_provenance_report(
    *,
    output_file: str,
    report_data: ReportData,
    excel_data: ExcelDataSource,
    config_loader: ConfigLoader,
    project_type: Optional[str] = None,
    project_name: Optional[str] = None,
    template_file: Optional[str] = None,
    generation_id: Optional[str] = None,
    key_fields: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Build a field provenance report for one generation."""
    fields = key_fields or KEY_FIELDS
    mapping_config = config_loader.load_mapping_config()
    single_values_cfg = mapping_config.get("single_values", {}) or {}
    patient_info = _load_patient_info(config_loader, excel_data)

    provenance: Dict[str, Any] = {}
    for field_name in fields:
        value = _final_value(field_name, report_data, project_type, project_name)
        source = _resolve_source(
            field_name=field_name,
            value=value,
            report_data=report_data,
            excel_data=excel_data,
            single_values_cfg=single_values_cfg,
            patient_info=patient_info,
            project_type=project_type,
            project_name=project_name,
        )
        sensitive = field_name in SENSITIVE_FIELDS
        provenance[field_name] = {
            "value": _mask_value(value, field_name) if sensitive else _jsonable(value),
            "raw_value_present": not _is_missing(value),
            "sensitive": sensitive,
            "source": source["source"],
            "source_key": source.get("source_key"),
            "source_detail": source.get("source_detail"),
            "precedence": SOURCE_PRECEDENCE,
        }

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "generation_id": generation_id,
        "output_file": str(output_file),
        "template_file": str(template_file) if template_file else None,
        "project_type": project_type,
        "project_name": project_name,
        "privacy": {
            "sensitive_fields_masked": True,
            "sensitive_fields": sorted(SENSITIVE_FIELDS),
        },
        "source_precedence": SOURCE_PRECEDENCE,
        "fields": provenance,
    }


def write_field_provenance_report(
    report: Mapping[str, Any],
    output_file: str,
    provenance_file: Optional[str] = None,
) -> str:
    """Write provenance JSON next to the generated DOCX."""
    path = (
        Path(provenance_file)
        if provenance_file
        else Path(output_file).with_suffix(".field_provenance.json")
    )
    write_json(path, dict(report))
    return str(path)


def summarize_key_field_sources(
    provenance_report: Optional[Mapping[str, Any]],
) -> Dict[str, str]:
    """Return a compact field->source summary for QA reports and UIs."""
    if not provenance_report:
        return {}
    fields = provenance_report.get("fields") or {}
    if not isinstance(fields, Mapping):
        return {}
    return {
        str(field): str(info.get("source") or "unknown")
        for field, info in fields.items()
        if isinstance(info, Mapping)
    }


def _final_value(
    field_name: str,
    report_data: ReportData,
    project_type: Optional[str],
    project_name: Optional[str],
) -> Any:
    if field_name == "project_type" and project_type:
        return project_type
    if field_name == "project_name" and project_name:
        return project_name
    return report_data.get_field(field_name)


def _resolve_source(
    *,
    field_name: str,
    value: Any,
    report_data: ReportData,
    excel_data: ExcelDataSource,
    single_values_cfg: Mapping[str, Any],
    patient_info: Mapping[str, Any],
    project_type: Optional[str],
    project_name: Optional[str],
) -> Dict[str, Any]:
    overrides = excel_data.metadata.get("field_source_overrides") or {}
    if isinstance(overrides, Mapping) and field_name in overrides:
        override = overrides[field_name] or {}
        if isinstance(override, Mapping):
            return {
                "source": str(override.get("source") or "form"),
                "source_key": override.get("source_key"),
                "source_detail": override.get("source_detail") or "web_clinical_form",
            }

    excel_match = _find_excel_value(field_name, excel_data, single_values_cfg)
    if excel_match is not None:
        source_key, _source_value = excel_match
        return {
            "source": "excel",
            "source_key": source_key,
            "source_detail": "excel_single_values",
        }

    if field_name in patient_info and not _is_missing(patient_info.get(field_name)):
        if _values_match(value, patient_info.get(field_name)):
            return {
                "source": "patient_info",
                "source_key": field_name,
                "source_detail": "patient_info.yaml",
            }

    sample_id = excel_data.metadata.get("sample_id_from_filename")
    if field_name == "sample_id" and sample_id and _values_match(value, sample_id):
        return {
            "source": "filename",
            "source_key": "sample_id_from_filename",
            "source_detail": "excel_filename",
        }

    if field_name == "project_type" and project_type:
        return {
            "source": "rule",
            "source_key": "project_type",
            "source_detail": "generation_argument_or_project_detector",
        }
    if field_name == "project_name" and project_name:
        return {
            "source": "rule",
            "source_key": "project_name",
            "source_detail": "generation_argument_or_project_detector",
        }
    if field_name in DERIVED_FIELDS:
        return {
            "source": "rule",
            "source_key": field_name,
            "source_detail": "computed_from_report_context",
        }

    default_value = _mapping_default(field_name, single_values_cfg)
    if not _is_missing(default_value) and _values_match(value, default_value):
        return {
            "source": "default",
            "source_key": field_name,
            "source_detail": "mapping.default_value",
        }

    if _is_missing(value):
        return {
            "source": "missing",
            "source_key": field_name,
            "source_detail": "no_value_in_final_context",
        }

    if field_name in report_data.context:
        return {
            "source": "unknown",
            "source_key": field_name,
            "source_detail": "present_in_report_context_without_source_marker",
        }

    return {
        "source": "missing",
        "source_key": field_name,
        "source_detail": "field_not_in_report_context",
    }


def _find_excel_value(
    field_name: str,
    excel_data: ExcelDataSource,
    single_values_cfg: Mapping[str, Any],
) -> Optional[tuple[str, Any]]:
    cfg = single_values_cfg.get(field_name) or {}
    synonyms = cfg.get("synonyms") if isinstance(cfg, Mapping) else []
    candidates = [field_name, *(synonyms or [])]
    for candidate in candidates:
        if candidate in excel_data.single_values and not _is_missing(
            excel_data.single_values.get(candidate)
        ):
            return str(candidate), excel_data.single_values.get(candidate)
    return None


def _mapping_default(field_name: str, single_values_cfg: Mapping[str, Any]) -> Any:
    cfg = single_values_cfg.get(field_name) or {}
    if isinstance(cfg, Mapping):
        return cfg.get("default_value")
    return None


def _load_patient_info(
    config_loader: ConfigLoader, excel_data: ExcelDataSource
) -> Dict[str, Any]:
    sample_id = excel_data.metadata.get("sample_id_from_filename")
    try:
        return config_loader.load_patient_info(sample_id) or {}
    except Exception:
        return {}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in {"", "--", "未填写", "未检测", "None", "nan"}
    return False


def _values_match(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return str(left).strip() == str(right).strip()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _mask_value(value: Any, field_name: str) -> Any:
    if _is_missing(value):
        return _jsonable(value)
    text = str(value)
    if field_name == "patient_name":
        if len(text) <= 1:
            return "*"
        if len(text) == 2:
            return text[0] + "*"
        return text[0] + "*" * (len(text) - 2) + text[-1]

    if len(text) <= 4:
        return "*" * len(text)
    if len(text) <= 8:
        return text[:1] + "*" * (len(text) - 2) + text[-1:]
    return text[:2] + "*" * (len(text) - 4) + text[-2:]
