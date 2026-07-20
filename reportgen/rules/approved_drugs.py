"""Panel-scoped selection rules for the CRC approved-drug table."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence


FIXED_DISPLAY_MODE = "fixed"
EXCLUDE_IF_LISTED_IN_PART2 = "exclude_if_listed_in_part2"
SUPPORTED_DISPLAY_MODES = {FIXED_DISPLAY_MODE, EXCLUDE_IF_LISTED_IN_PART2}


@dataclass(frozen=True)
class ApprovedDrugSelection:
    """Selected rows plus an auditable record of rows suppressed by Part 2."""

    rows: List[Dict[str, Any]]
    suppressed_names: List[str]
    total_count: int


def normalize_display_mode(value: Any) -> str:
    """Normalize and validate a panel-declared approved-drug display mode."""
    mode = str(value or FIXED_DISPLAY_MODE).strip().lower()
    if mode not in SUPPORTED_DISPLAY_MODES:
        supported = ", ".join(sorted(SUPPORTED_DISPLAY_MODES))
        raise ValueError(
            f"unsupported approved-drug display mode {mode!r}; expected {supported}"
        )
    return mode


def _as_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _normalize_drug_text(value: Any) -> str:
    """Return a comparison key tolerant of case, width and punctuation only."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"\([a-d]\)\s*$", "", text)
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)


def _split_part2_drug_values(value: Any) -> List[str]:
    values: List[str] = []
    for text in _as_text_list(value):
        values.extend(
            item.strip()
            for item in re.split(r"[\n\r;；、]+", text)
            if item.strip()
        )
    return values


def _part2_drug_values(rows: Iterable[Mapping[str, Any]]) -> List[str]:
    """Collect the final, non-compacted Part-2 drug cells when available."""
    values: List[str] = []
    for row in rows:
        # *_full is authoritative after display compaction. Before compaction it
        # is normally absent, so fall back to the corresponding visible field.
        for full_key, visible_key in (
            ("benefit_drugs_full", "benefit_drugs"),
            ("caution_drugs_full", "caution_drugs"),
        ):
            value = row.get(full_key)
            if value in (None, ""):
                value = row.get(visible_key)
            values.extend(_split_part2_drug_values(value))

        for legacy_key in ("潜在获益药物", "潜在耐药药物"):
            values.extend(_split_part2_drug_values(row.get(legacy_key)))
    return values


def _row_aliases(row: Mapping[str, Any]) -> List[str]:
    aliases = [
        *_as_text_list(row.get("drug") or row.get("Drug")),
        *_as_text_list(row.get("match_aliases")),
    ]
    return [alias for alias in aliases if len(_normalize_drug_text(alias)) >= 2]


def _display_name(row: Mapping[str, Any]) -> str:
    values = _as_text_list(row.get("drug") or row.get("Drug"))
    return values[0] if values else ""


def select_approved_drug_rows(
    approved_rows: Sequence[Mapping[str, Any]],
    part2_rows: Sequence[Mapping[str, Any]],
    *,
    mode: str = FIXED_DISPLAY_MODE,
) -> ApprovedDrugSelection:
    """Apply the Panel display policy to the reviewed approved-drug universe.

    ``exclude_if_listed_in_part2`` implements the candidate rule stated in
    the report-group feedback:
    start from the configured approved-drug universe and suppress a row only
    when one of its explicit aliases appears in the final Part-2 benefit or
    caution drug cells. It never infers a match from genes or indications.
    """
    normalized_mode = normalize_display_mode(mode)
    active_rows = [
        dict(row)
        for row in approved_rows
        if isinstance(row, Mapping) and row.get("enabled") is not False
    ]
    if normalized_mode == FIXED_DISPLAY_MODE:
        return ApprovedDrugSelection(
            rows=active_rows,
            suppressed_names=[],
            total_count=len(active_rows),
        )

    source_values = [
        normalized
        for normalized in (
            _normalize_drug_text(value) for value in _part2_drug_values(part2_rows)
        )
        if normalized
    ]
    selected: List[Dict[str, Any]] = []
    suppressed: List[str] = []
    for row in active_rows:
        aliases = [
            normalized
            for normalized in (
                _normalize_drug_text(alias) for alias in _row_aliases(row)
            )
            if normalized
        ]
        listed_in_part2 = any(
            (alias == source_value if len(alias) <= 2 else alias in source_value)
            for alias in aliases
            for source_value in source_values
        )
        if listed_in_part2:
            suppressed.append(_display_name(row))
        else:
            selected.append(row)

    return ApprovedDrugSelection(
        rows=selected,
        suppressed_names=suppressed,
        total_count=len(active_rows),
    )
