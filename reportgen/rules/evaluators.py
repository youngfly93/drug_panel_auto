"""Rule evaluator extension points and M7 report text application helpers."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from reportgen.core.validation import (
    TMB_TABLE_IMMUNO_TIPS,
    build_msi_fields,
    build_tmb_fields,
)


class RuleEvaluator(Protocol):
    """Protocol for future rule evaluators."""

    def evaluate(self, data: Any, rules: dict[str, Any]) -> Any:
        """Evaluate one rule set against input data."""


def collect_report_texts(report_text_rule: Mapping[str, Any] | None) -> dict[str, str]:
    """Flatten ``report_text.yaml`` entries to ``{key: text}``.

    Rule authors can use either ``key: "text"`` or ``key: {text: "..."}``.
    Metadata-only entries are ignored until they carry a concrete text/value.
    """
    if not isinstance(report_text_rule, Mapping):
        return {}
    raw_texts = report_text_rule.get("texts")
    if not isinstance(raw_texts, Mapping):
        return {}

    texts: dict[str, str] = {}
    for key, value in raw_texts.items():
        text_value = value
        if isinstance(value, Mapping):
            text_value = value.get("text") or value.get("value")
        if text_value is None:
            continue
        text = str(text_value)
        if text.strip():
            texts[str(key)] = text
    return texts


def apply_report_text_rules(
    report_data: Any,
    text_rules: Mapping[str, Any],
) -> dict[str, str]:
    """Apply configured report wording to already-normalized report fields."""
    if not text_rules:
        return {}

    applied: dict[str, str] = {}
    immuno_tips = _text_rule(text_rules, "tmb_table_immuno_tips", "")
    if immuno_tips:
        report_data.set_field("immuno_tips", immuno_tips)
        applied["immuno_tips"] = "tmb_table_immuno_tips"
    elif "immuno_tips" not in getattr(report_data, "context", {}):
        report_data.set_field("immuno_tips", TMB_TABLE_IMMUNO_TIPS)

    tmb_raw = report_data.get_field("tmb_value")
    if tmb_raw is None:
        tmb_raw = report_data.get_field("TMB")
    tmb_fields = build_tmb_fields(
        tmb_raw,
        sample_type=report_data.get_field("sample_type") or "组织",
        text_rules=text_rules,
    )
    for field in ("tmb_detail_interpretation", "tmb_drug_note"):
        report_data.set_field(field, tmb_fields[field])
        applied[field] = field

    msi_fields = build_msi_fields(
        report_data.get_field("msi_status"),
        text_rules=text_rules,
    )
    for field in ("msi_detail_interpretation", "msi_tips"):
        report_data.set_field(field, msi_fields[field])
        applied[field] = field

    return applied


def _text_rule(text_rules: Mapping[str, Any], key: str, default: str) -> str:
    value = text_rules.get(key)
    if isinstance(value, Mapping):
        value = value.get("text") or value.get("value")
    if value is None:
        return default
    text = str(value)
    return text if text.strip() else default
