"""Panel-scoped PD-L1 assay provenance and runtime release boundary."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from reportgen.rules.schema import load_rule_yaml


REPORT_GROUP_APPROVED = "approved_by_report_group"
CONTROLLED_PILOT_APPROVED = "product_owner_authorized_controlled_pilot"
CONTROLLED_PILOT_MODE = "controlled_pilot_transcription"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def load_pdl1_product_contract(panel_package: Any) -> dict[str, Any]:
    """Load an optional panel-owned PD-L1 product contract."""

    if panel_package is None:
        return {}
    try:
        path = panel_package.resolve_rule_file("pdl1_product_contract")
    except (KeyError, ValueError):
        return {}
    contract = dict(load_rule_yaml(path))
    if _clean(contract.get("rule_id")) != "pdl1_product_contract":
        raise ValueError(
            "PD-L1 product contract has an unexpected rule_id: "
            f"{contract.get('rule_id')!r}"
        )
    return contract


def _candidate_profiles(
    contract: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for row in contract.get("candidate_profiles") or []:
        if not isinstance(row, dict):
            continue
        profile_id = _clean(row.get("profile_id"))
        if not profile_id:
            continue
        if profile_id in profiles:
            raise ValueError(f"Duplicate PD-L1 assay profile: {profile_id}")
        profiles[profile_id] = row
    return profiles


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _validate_profile_scores(
    report_data: Any,
    profile: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Validate fields and display class owned by one assay profile."""

    failures: list[dict[str, Any]] = []
    profile_id = _clean(profile.get("profile_id"))
    for raw_field in profile.get("required_case_score_fields") or []:
        field = _clean(raw_field)
        if field and _is_blank(report_data.get_field(field)):
            failures.append(
                {
                    "field": field,
                    "reason": "assay_profile_score_missing",
                    "assay_profile_id": profile_id,
                }
            )

    result = _clean(report_data.get_field("pdl1_result"))
    if not result:
        return failures

    validation_mode = _clean(profile.get("validation_mode"))
    if validation_mode == "verbatim_source_record":
        allowed_values = {
            _clean(value)
            for value in profile.get("allowed_display_values") or []
            if _clean(value)
        }
        if result not in allowed_values:
            failures.append(
                {
                    "field": "pdl1_result",
                    "reason": "source_record_classification_not_allowed",
                    "value": result,
                    "assay_profile_id": profile_id,
                    "allowed_values": sorted(allowed_values),
                }
            )
        return failures

    classifications = profile.get("display_classification") or {}
    range_spec = classifications.get(result)
    if not isinstance(range_spec, Mapping):
        failures.append(
            {
                "field": "pdl1_result",
                "reason": "classification_not_allowed_for_assay_profile",
                "value": result,
                "assay_profile_id": profile_id,
                "allowed_values": sorted(
                    _clean(value) for value in classifications if _clean(value)
                ),
            }
        )
        return failures

    source_field = _clean(range_spec.get("field"))
    source_value = report_data.get_field(source_field)
    numeric = _numeric(source_value)
    if not source_field or numeric is None:
        failures.append(
            {
                "field": "pdl1_result",
                "reason": "classification_source_missing_or_not_numeric",
                "value": result,
                "source_field": source_field,
                "source_value": source_value,
                "assay_profile_id": profile_id,
            }
        )
        return failures

    minimum = range_spec.get("minimum")
    maximum = range_spec.get("maximum")
    minimum_inclusive = bool(range_spec.get("minimum_inclusive", True))
    maximum_inclusive = bool(range_spec.get("maximum_inclusive", True))
    below = minimum is not None and (
        numeric < float(minimum) if minimum_inclusive else numeric <= float(minimum)
    )
    above = maximum is not None and (
        numeric > float(maximum) if maximum_inclusive else numeric >= float(maximum)
    )
    if below or above:
        failures.append(
            {
                "field": "pdl1_result",
                "reason": "classification_inconsistent_with_assay_profile",
                "value": result,
                "source_field": source_field,
                "source_value": source_value,
                "assay_profile_id": profile_id,
            }
        )
    return failures


def _controlled_pilot_governance(
    contract: Mapping[str, Any],
) -> bool:
    governance = contract.get("governance") or {}
    return (
        _clean(contract.get("status")) == "pilot"
        and _clean(governance.get("runtime_mode")) == CONTROLLED_PILOT_MODE
        and governance.get("runtime_enabled") is True
        and governance.get("report_text_allowed") is True
        and governance.get("promotion_blocked") is True
        and governance.get("treatment_inference_allowed") is False
        and _clean(governance.get("secondary_review_status"))
        == CONTROLLED_PILOT_APPROVED
    )


def is_pdl1_profile_runtime_allowed(
    profile: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> bool:
    """Return whether a profile may be selected in this release tier."""

    profile_id = _clean(profile.get("profile_id"))
    runtime_profiles = {
        _clean(value)
        for value in contract.get("runtime_profiles") or []
        if _clean(value)
    }
    if (
        not profile_id
        or profile_id not in runtime_profiles
        or profile.get("runtime_eligible") is not True
        or profile.get("report_text_allowed") is not True
    ):
        return False

    review_status = _clean(profile.get("secondary_review_status"))
    if review_status == REPORT_GROUP_APPROVED:
        return True
    return (
        _controlled_pilot_governance(contract)
        and review_status == CONTROLLED_PILOT_APPROVED
        and _clean(profile.get("validation_mode")) == "verbatim_source_record"
        and profile.get("treatment_inference_allowed") is False
    )


def validate_pdl1_product_contract(
    report_data: Any,
    contract: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Validate per-case provenance and the reviewed assay activation state."""

    if not isinstance(contract, Mapping) or not contract:
        return []

    failures: list[dict[str, Any]] = []
    governance = contract.get("governance") or {}
    fully_approved = (
        governance.get("runtime_enabled") is True
        and governance.get("report_text_allowed") is True
        and governance.get("promotion_blocked") is False
        and governance.get("secondary_review_status") == REPORT_GROUP_APPROVED
    )
    controlled_pilot = _controlled_pilot_governance(contract)
    if not fully_approved and not controlled_pilot:
        failures.append(
            {
                "field": "pdl1_assay_profile_id",
                "reason": "product_contract_not_runtime_approved",
                "secondary_review_status": governance.get("secondary_review_status"),
            }
        )

    required_fields = (contract.get("input_provenance") or {}).get(
        "required_fields"
    ) or []
    for raw_field in required_fields:
        field = _clean(raw_field)
        value = report_data.get_field(field)
        if not _clean(value):
            failures.append(
                {
                    "field": field,
                    "reason": "per_case_provenance_missing",
                }
            )

    profile_id = _clean(report_data.get_field("pdl1_assay_profile_id"))
    profiles = _candidate_profiles(contract)
    profile = profiles.get(profile_id)
    if profile_id and profile is None:
        failures.append(
            {
                "field": "pdl1_assay_profile_id",
                "reason": "assay_profile_unknown",
                "value": profile_id,
            }
        )
    elif profile is not None:
        if not is_pdl1_profile_runtime_allowed(profile, contract):
            failures.append(
                {
                    "field": "pdl1_assay_profile_id",
                    "reason": "assay_profile_not_runtime_approved",
                    "value": profile_id,
                    "secondary_review_status": profile.get("secondary_review_status"),
                }
            )
        failures.extend(_validate_profile_scores(report_data, profile))

    image_disposition = _clean(report_data.get_field("pdl1_image_disposition"))
    image_policy = contract.get("image_policy") or {}
    allowed_images = {
        _clean(value)
        for value in image_policy.get("allowed_runtime_dispositions") or []
        if _clean(value)
    }
    if image_disposition and image_disposition not in allowed_images:
        failures.append(
            {
                "field": "pdl1_image_disposition",
                "reason": "image_disposition_not_allowed",
                "value": image_disposition,
                "allowed_values": sorted(allowed_images),
            }
        )
    if (
        image_disposition
        and "无病例专属图像" not in image_disposition
        and image_policy.get("case_specific_image_pipeline_implemented") is not True
    ):
        failures.append(
            {
                "field": "pdl1_image_disposition",
                "reason": "case_specific_image_pipeline_not_implemented",
                "value": image_disposition,
            }
        )
    image_path = _clean(report_data.get_field("pdl1_image_path"))
    if "报告展示" in image_disposition and not image_path:
        failures.append(
            {
                "field": "pdl1_image_path",
                "reason": "case_specific_image_missing",
            }
        )
    return failures


def apply_pdl1_product_display_fields(
    report_data: Any,
    contract: Mapping[str, Any] | None,
) -> None:
    """Populate neutral assay/source provenance fields from a known profile."""

    if not isinstance(contract, Mapping) or not contract:
        return
    profile_id = _clean(report_data.get_field("pdl1_assay_profile_id"))
    profile = _candidate_profiles(contract).get(profile_id)
    if profile is None:
        return

    assay_name = _clean(profile.get("assay_name"))
    clone = _clean(profile.get("antibody_clone"))
    platform = _clean(profile.get("staining_platform"))
    visualization = _clean(profile.get("visualization_system"))
    scoring = _clean(profile.get("primary_scoring_method"))
    method_notice = _clean(profile.get("report_method_notice"))
    report_data.set_field("pdl1_assay_name", assay_name)
    report_data.set_field("pdl1_antibody_clone", clone)
    report_data.set_field("pdl1_test_platform", platform)
    report_data.set_field("pdl1_visualization_system", visualization)
    report_data.set_field("pdl1_scoring_method", scoring)
    report_data.set_field(
        "pdl1_assay_provenance",
        "检测方案："
        f"{assay_name or '--'}；抗体克隆：{clone or '--'}；"
        f"染色平台：{platform or '--'}；"
        f"显色系统：{visualization or '--'}；"
        f"主要评分方法：{scoring or '--'}。"
        + (f" {method_notice}" if method_notice else ""),
    )

    source_record = _clean(report_data.get_field("pdl1_source_record_id"))
    source_date = _clean(report_data.get_field("pdl1_source_record_date"))
    specimen_id = _clean(report_data.get_field("pdl1_specimen_id"))
    report_data.set_field(
        "pdl1_source_provenance",
        "原始IHC记录："
        f"{source_record or '--'}；记录日期：{source_date or '--'}；"
        f"PD-L1标本标识：{specimen_id or '--'}。",
    )
