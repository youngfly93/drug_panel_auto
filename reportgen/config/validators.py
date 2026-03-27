"""
Lightweight config validators.

We intentionally keep this dependency-free (no pydantic/jsonschema) to reduce
runtime footprint and make CI checks simple.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

_ALLOWED_TYPES = {"string", "int", "float", "date", "bool"}
_ALLOWED_EMPTY_BEHAVIOR = {"show_placeholder", "hide_section", "error"}


def _as_dict(obj: Any) -> Dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def validate_mapping_config(cfg: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(cfg, dict):
        return False, ["mapping.yaml must be a dict at top level"]

    schema_version = cfg.get("schema_version")
    if schema_version is None:
        errors.append("mapping.schema_version is required")
    elif not isinstance(schema_version, (str, int, float)):
        errors.append("mapping.schema_version must be a string/number")

    single_values = cfg.get("single_values")
    if not isinstance(single_values, dict):
        errors.append("mapping.single_values must be a dict")
        single_values = {}

    for key, item in single_values.items():
        if not isinstance(item, dict):
            errors.append(f"mapping.single_values.{key}: must be a dict")
            continue
        if "synonyms" not in item:
            errors.append(
                f"mapping.single_values.{key}.synonyms is required (can be empty list)"
            )
        elif not isinstance(item.get("synonyms"), list):
            errors.append(f"mapping.single_values.{key}.synonyms must be a list")

        t = item.get("type")
        if not isinstance(t, str) or not t:
            errors.append(f"mapping.single_values.{key}.type is required")
        elif t not in _ALLOWED_TYPES:
            errors.append(
                f"mapping.single_values.{key}.type must be one of {_ALLOWED_TYPES} "
                f"(got {t!r})"
            )

        required = item.get("required")
        if required is not None and not isinstance(required, bool):
            errors.append(
                f"mapping.single_values.{key}.required must be bool if present"
            )

    table_data = cfg.get("table_data")
    if not isinstance(table_data, dict):
        errors.append("mapping.table_data must be a dict")
        table_data = {}

    for table_name, table_cfg in table_data.items():
        if not isinstance(table_cfg, dict):
            errors.append(f"mapping.table_data.{table_name}: must be a dict")
            continue

        sheet_name = table_cfg.get("sheet_name")
        if not isinstance(sheet_name, str) or not sheet_name.strip():
            errors.append(f"mapping.table_data.{table_name}.sheet_name is required")

        empty_behavior = table_cfg.get("empty_behavior")
        if empty_behavior is not None:
            if (
                not isinstance(empty_behavior, str)
                or empty_behavior not in _ALLOWED_EMPTY_BEHAVIOR
            ):
                errors.append(
                    f"mapping.table_data.{table_name}.empty_behavior must be one of "
                    f"{_ALLOWED_EMPTY_BEHAVIOR} (got {empty_behavior!r})"
                )

        cols = table_cfg.get("columns")
        if not isinstance(cols, dict):
            errors.append(f"mapping.table_data.{table_name}.columns must be a dict")
            continue

        for col_key, col_cfg in cols.items():
            if not isinstance(col_cfg, dict):
                errors.append(
                    f"mapping.table_data.{table_name}.columns.{col_key}: must be a dict"
                )
                continue
            syn = col_cfg.get("synonyms")
            if not isinstance(syn, list):
                errors.append(
                    f"mapping.table_data.{table_name}.columns.{col_key}."
                    "synonyms must be a list"
                )
            t = col_cfg.get("type")
            if not isinstance(t, str) or not t:
                errors.append(
                    f"mapping.table_data.{table_name}.columns.{col_key}."
                    "type is required"
                )
            elif t not in _ALLOWED_TYPES:
                errors.append(
                    f"mapping.table_data.{table_name}.columns.{col_key}."
                    "type must be one of "
                    f"{_ALLOWED_TYPES} (got {t!r})"
                )

    return len(errors) == 0, errors


def validate_project_types_config(cfg: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(cfg, dict):
        return False, ["project_types.yaml must be a dict at top level"]

    project_types = cfg.get("project_types")
    if not isinstance(project_types, list) or not project_types:
        errors.append("project_types.project_types must be a non-empty list")
        project_types = []

    seen_ids: set[str] = set()
    for i, item in enumerate(project_types):
        if not isinstance(item, dict):
            errors.append(f"project_types.project_types[{i}] must be a dict")
            continue
        pid = item.get("id")
        name = item.get("name")
        template = item.get("template")
        if not isinstance(pid, str) or not pid.strip():
            errors.append(f"project_types.project_types[{i}].id is required")
        else:
            if pid in seen_ids:
                errors.append(f"project_types: duplicated id {pid!r}")
            seen_ids.add(pid)
        if not isinstance(name, str) or not name.strip():
            errors.append(f"project_types.project_types[{i}].name is required")
        if template is not None and not isinstance(template, str):
            errors.append(
                f"project_types.project_types[{i}].template must be string if present"
            )

    default_cfg = cfg.get("default")
    if default_cfg is not None and not isinstance(default_cfg, dict):
        errors.append("project_types.default must be a dict if present")
    else:
        d = _as_dict(default_cfg)
        thr = d.get("match_threshold")
        if thr is not None:
            try:
                v = float(thr)
                if not (0.0 <= v <= 1.0):
                    errors.append(
                        "project_types.default.match_threshold must be between 0 and 1"
                    )
            except Exception:
                errors.append(
                    "project_types.default.match_threshold must be a number between "
                    "0 and 1"
                )

    return len(errors) == 0, errors


def validate_settings_config(cfg: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(cfg, dict):
        return False, ["settings.yaml must be a dict at top level"]

    logging_cfg = _as_dict(cfg.get("logging"))
    content_cfg = _as_dict(logging_cfg.get("content"))
    sensitive_fields = content_cfg.get("sensitive_fields")
    if sensitive_fields is not None:
        if not isinstance(sensitive_fields, list) or not all(
            isinstance(x, str) and x.strip() for x in sensitive_fields
        ):
            errors.append(
                "settings.logging.content.sensitive_fields must be a list[str]"
            )

    kb_cfg = _as_dict(cfg.get("knowledge_bases"))
    for section in (
        "targeted_drug_db",
        "immune_gene_list",
        "gene_knowledge_db",
        "gene_transcript_db",
    ):
        s = kb_cfg.get(section)
        if s is None:
            continue
        if not isinstance(s, dict):
            errors.append(f"settings.knowledge_bases.{section} must be a dict")
            continue
        enabled = s.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            errors.append(
                f"settings.knowledge_bases.{section}.enabled must be bool if present"
            )

    return len(errors) == 0, errors


def validate_filtering_config(cfg: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(cfg, dict):
        return False, ["filtering.yaml must be a dict at top level"]

    variations = _as_dict(cfg.get("variations"))
    enabled = variations.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        errors.append("filtering.variations.enabled must be bool if present")

    freq = _as_dict(variations.get("frequency_filter"))
    if "min_frequency" in freq:
        try:
            float(freq.get("min_frequency"))
        except Exception:
            errors.append(
                "filtering.variations.frequency_filter.min_frequency must be a number"
            )

    return len(errors) == 0, errors
