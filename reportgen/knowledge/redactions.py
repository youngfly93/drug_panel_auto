"""Panel-scoped exact knowledge retractions.

This module intentionally supports removal only. A safety retraction can stop
an unsupported inherited statement from reaching a panel, but it cannot
promote replacement medical wording or silently broaden evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from reportgen.rules.schema import load_rule_yaml


ALLOWED_FIELDS = {
    "intro",
    "mutation_analysis",
    "fixed_domain_text",
}
ALLOWED_ACTION = "remove_exact_literal"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def load_panel_knowledge_redactions(
    panel_package: Any,
) -> list[dict[str, Any]]:
    """Load and validate removal-only redactions owned by one panel."""

    if panel_package is None:
        return []
    try:
        path = panel_package.resolve_rule_file("knowledge_redactions")
    except (KeyError, ValueError):
        return []

    raw = dict(load_rule_yaml(path))
    if _clean(raw.get("rule_id")) != "knowledge_redactions":
        raise ValueError(
            "Knowledge redaction contract has an unexpected rule_id: "
            f"{raw.get('rule_id')!r}"
        )
    panel_id = _clean(raw.get("panel_id"))
    package_panel_id = _clean(getattr(panel_package, "panel_id", ""))
    if panel_id != package_panel_id:
        raise ValueError(
            "Knowledge redaction panel mismatch: "
            f"{panel_id!r} != {package_panel_id!r}"
        )

    governance = raw.get("governance") or {}
    if (
        governance.get("exact_literal_only") is not True
        or governance.get("additions_allowed") is not False
        or governance.get("replacement_text_allowed") is not False
    ):
        raise ValueError(
            "Knowledge redaction governance must be exact, removal-only, "
            "and replacement-free"
        )

    redactions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(raw.get("redactions") or [], start=1):
        if not isinstance(row, Mapping):
            raise ValueError(
                f"Knowledge redaction row {index} must be a mapping"
            )
        redaction_id = _clean(row.get("redaction_id"))
        gene = _clean(row.get("gene")).upper()
        target_text = _clean(row.get("target_text"))
        action = _clean(row.get("action"))
        fields = row.get("fields") or []
        if isinstance(fields, str):
            fields = [fields]
        normalized_fields = {
            _clean(field)
            for field in fields
            if _clean(field)
        }
        if not redaction_id or redaction_id in seen_ids:
            raise ValueError(
                f"Knowledge redaction row {index} has a missing/duplicate id"
            )
        if not gene or not target_text:
            raise ValueError(
                f"Knowledge redaction {redaction_id} lacks gene/target_text"
            )
        if action != ALLOWED_ACTION:
            raise ValueError(
                f"Knowledge redaction {redaction_id} is not removal-only"
            )
        if (
            not normalized_fields
            or not normalized_fields <= ALLOWED_FIELDS
        ):
            raise ValueError(
                f"Knowledge redaction {redaction_id} has invalid fields"
            )
        if (
            row.get("runtime_eligible") is not True
            or row.get("adds_medical_claim") is not False
            or _clean(row.get("replacement_status"))
            != "pending_report_group_review"
        ):
            raise ValueError(
                f"Knowledge redaction {redaction_id} violates the "
                "safety-retraction release boundary"
            )
        seen_ids.add(redaction_id)
        redactions.append(
            {
                "redaction_id": redaction_id,
                "gene": gene,
                "fields": sorted(normalized_fields),
                "action": action,
                "target_text": target_text,
                "reason": _clean(row.get("reason")),
                "adds_medical_claim": False,
                "replacement_status": "pending_report_group_review",
            }
        )
    return redactions
