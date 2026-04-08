"""
Clinical info service: dynamic form schema generation + patient_info.yaml CRUD.

Reads mapping.yaml to build the dynamic form schema,
and reads/writes patient_info.yaml for patient management.
"""

import threading
from pathlib import Path
from typing import Any, Optional

import yaml

from app.config import settings
from app.schemas.clinical_info import (
    ClinicalFormSchema,
    FieldGroup,
    FieldSchema,
    FieldUiHints,
    PatientDefaults,
    PatientInfo,
    ProjectInfo,
)

# File lock for concurrent YAML writes
_yaml_lock = threading.Lock()

# Field grouping rules - maps field keys to semantic groups
FIELD_GROUPS = {
    "demographics": {
        "label": "患者基本信息",
        "fields": ["patient_name", "gender", "age", "cancer_type"],
    },
    "identifiers": {
        "label": "标识信息",
        "fields": ["sample_id", "report_number", "pathology_id"],
    },
    "institution": {
        "label": "送检信息",
        "fields": ["hospital", "department"],
    },
    "temporal": {
        "label": "日期信息",
        "fields": ["collection_date", "receive_date", "report_date"],
    },
    "sample": {
        "label": "样本与项目",
        "fields": ["sample_type", "detection_method", "panel_name"],
    },
    "approval": {
        "label": "签发信息",
        "fields": ["issuer", "reviewer", "signature_image_path"],
    },
    "biomarkers": {
        "label": "检测指标",
        "fields": ["msi_status", "msi_score", "tmb_value", "tmb_unit", "final_conclusion"],
    },
}

# Fields hidden from web form (auto-computed or not applicable)
ALWAYS_HIDE = ["project_name"]

# Project-specific field overrides
PROJECT_FIELD_OVERRIDES: dict[str, dict] = {
    "lung_methylation": {
        "show": ["methylation_result"],
        "hide": ALWAYS_HIDE,
        "require": ["methylation_result"],
    },
    "crc_301_msi": {"hide": ALWAYS_HIDE},
    "crc_358_msi": {"hide": ALWAYS_HIDE},
    "mlf_result": {"hide": ALWAYS_HIDE},
}

# UI component mapping by field type
TYPE_TO_COMPONENT = {
    "string": "input",
    "int": "input-number",
    "float": "input-number",
    "date": "date-picker",
    "bool": "switch",
}


def _load_mapping_yaml() -> dict:
    """Load and return the mapping.yaml config."""
    path = Path(settings.upstream_config_dir) / "mapping.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _is_computed_field(field_def: dict) -> bool:
    """Check if a field is computed (empty synonyms and not required from user)."""
    synonyms = field_def.get("synonyms", [])
    return isinstance(synonyms, list) and len(synonyms) == 0


def _build_ui_hints(key: str, field_def: dict) -> FieldUiHints:
    """Build UI hints for a field."""
    if key == "signature_image_path":
        return FieldUiHints(
            component="file-upload",
            placeholder="请选择或上传签名图片",
            span=24,
            accept=".png,.jpg,.jpeg,.webp",
        )

    ftype = field_def.get("type", "string")
    component = TYPE_TO_COMPONENT.get(ftype, "input")
    desc = field_def.get("description", "")

    # Determine grid span based on type
    if ftype == "date":
        span = 8
    elif ftype in ("int", "float"):
        span = 6
    elif ftype == "bool":
        span = 4
    else:
        span = 12

    return FieldUiHints(
        component=component,
        placeholder=f"请输入{desc}" if desc else None,
        span=span,
    )


def get_clinical_form_schema(project_type: Optional[str] = None) -> ClinicalFormSchema:
    """
    Generate a dynamic form schema from mapping.yaml single_values.

    Groups fields semantically, marks computed fields as readonly,
    and applies project-type-specific overrides.
    """
    mapping = _load_mapping_yaml()
    single_values = mapping.get("single_values", {})

    # Build all field schemas
    all_fields: dict[str, FieldSchema] = {}
    for key, field_def in single_values.items():
        if not isinstance(field_def, dict):
            continue
        computed = _is_computed_field(field_def)
        # First synonym as label, fallback to key
        synonyms = field_def.get("synonyms", [])
        label = synonyms[0] if synonyms else key

        all_fields[key] = FieldSchema(
            key=key,
            label=label,
            type=field_def.get("type", "string"),
            required=field_def.get("required", False),
            default=field_def.get("default_value"),
            description=field_def.get("description"),
            format=field_def.get("format_template"),
            synonyms=synonyms,
            computed=computed,
            ui=_build_ui_hints(key, field_def),
        )

    # Apply project-type overrides
    overrides = PROJECT_FIELD_OVERRIDES.get(project_type, {}) if project_type else {}
    hide_fields = set(overrides.get("hide", []))
    show_fields = set(overrides.get("show", []))
    require_fields = set(overrides.get("require", []))
    for key in require_fields:
        if key in all_fields:
            all_fields[key].required = True

    # Assign fields to groups
    assigned = set()
    groups: list[FieldGroup] = []

    for group_id, group_def in FIELD_GROUPS.items():
        fields = []
        for fkey in group_def["fields"]:
            if fkey in all_fields and fkey not in hide_fields:
                fields.append(all_fields[fkey])
                assigned.add(fkey)
        if fields:
            groups.append(FieldGroup(id=group_id, label=group_def["label"], fields=fields))

    # Computed fields group (readonly)
    computed_fields = [
        f for k, f in all_fields.items()
        if k not in assigned and f.computed and k not in hide_fields
    ]
    if computed_fields:
        groups.append(FieldGroup(id="computed", label="计算字段(只读)", fields=computed_fields))
        assigned.update(f.key for f in computed_fields)

    # Catch-all for unassigned non-computed fields
    other_fields = [
        f for k, f in all_fields.items()
        if k not in assigned and k not in hide_fields
    ]
    if other_fields:
        groups.append(FieldGroup(id="other", label="其他", fields=other_fields))

    return ClinicalFormSchema(groups=groups, project_type=project_type)


# ---- patient_info.yaml CRUD ----

def _patient_info_path() -> Path:
    return Path(settings.upstream_config_dir) / "patient_info.yaml"


def _load_patient_info() -> dict:
    path = _patient_info_path()
    if not path.exists():
        return {"patients": {}, "defaults": {}, "project_info": {}}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"patients": {}, "defaults": {}, "project_info": {}}


def _save_patient_info(data: dict) -> None:
    with _yaml_lock:
        path = _patient_info_path()
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def list_patients() -> list[PatientInfo]:
    data = _load_patient_info()
    patients = data.get("patients", {})
    result = []
    for sample_id, info in patients.items():
        result.append(PatientInfo(sample_id=str(sample_id), **{k: str(v) if v else None for k, v in info.items()}))
    return result


def get_patient(sample_id: str) -> Optional[PatientInfo]:
    data = _load_patient_info()
    patients = data.get("patients", {})
    info = patients.get(sample_id)
    if info is None:
        return None
    return PatientInfo(sample_id=sample_id, **{k: str(v) if v else None for k, v in info.items()})


def upsert_patient(patient: PatientInfo) -> None:
    data = _load_patient_info()
    if "patients" not in data:
        data["patients"] = {}
    entry = patient.model_dump(exclude={"sample_id"}, exclude_none=True)
    data["patients"][patient.sample_id] = entry
    _save_patient_info(data)


def delete_patient(sample_id: str) -> bool:
    data = _load_patient_info()
    patients = data.get("patients", {})
    if sample_id in patients:
        del patients[sample_id]
        _save_patient_info(data)
        return True
    return False


def get_defaults() -> PatientDefaults:
    data = _load_patient_info()
    defaults = data.get("defaults", {})
    return PatientDefaults(**defaults)


def update_defaults(defaults: PatientDefaults) -> None:
    data = _load_patient_info()
    data["defaults"] = defaults.model_dump(exclude_none=True)
    _save_patient_info(data)


def get_project_info() -> ProjectInfo:
    data = _load_patient_info()
    pi = data.get("project_info", {})
    return ProjectInfo(**pi)


def update_project_info(info: ProjectInfo) -> None:
    data = _load_patient_info()
    data["project_info"] = info.model_dump(exclude_none=True)
    _save_patient_info(data)
