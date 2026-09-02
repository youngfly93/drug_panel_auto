"""Panel-scoped safety policies for patient-visible Part-3 narratives."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


GENE_ANALYSIS_FIELDS = ("mutation_analysis", "mutation_narrative", "fixed_domain_text")
DRUG_TEXT_FIELDS = ("relation", "clinical")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", _clean(value)).casefold()


def _matched_terms(value: Any, terms: list[str]) -> list[str]:
    compact = _compact(value)
    if not compact:
        return []
    return [term for term in terms if _compact(term) in compact]


def apply_part3_cross_cancer_policy(
    report_data: Any,
    part3_policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Suppress unsafe historical fields without inventing replacement medicine.

    The policy operates on structured Part-3 rows before DOCX rendering.  It
    replaces only fields containing configured cross-cancer terms with a
    neutral review-state notice.  Variant identity, measured values and exact
    Panel drug names are left unchanged.
    """

    policy = dict(part3_policy or {})
    scan = policy.get("cross_cancer_residual_scan") or {}
    if not isinstance(scan, Mapping):
        return {"enabled": False, "suppressed_field_count": 0, "rows": []}

    action = _clean(scan.get("runtime_action"))
    if action != "suppress_unsafe_fields":
        return {
            "enabled": False,
            "action": action,
            "suppressed_field_count": 0,
            "rows": [],
        }

    terms = [
        _clean(term)
        for term in scan.get("terms") or []
        if _clean(term)
    ]
    notice = _clean(scan.get("suppressed_text")) or (
        "该段历史知识尚未完成肺癌专属审核，本轮评审稿不展示原文；"
        "待报告组完成肺癌专属复核后补充。"
    )
    suppressed: list[dict[str, Any]] = []

    gene_rows = [dict(row) for row in report_data.get_table("gene_knowledge_sections")]
    for row_index, row in enumerate(gene_rows):
        gene = _clean(row.get("gene")).upper()
        intro_terms = _matched_terms(row.get("intro"), terms)
        if intro_terms:
            row["intro"] = notice
            suppressed.append(
                {
                    "table": "gene_knowledge_sections",
                    "row_index": row_index,
                    "gene": gene,
                    "field": "intro",
                    "matched_terms": intro_terms,
                }
            )

        original_fixed_domain = _clean(row.get("fixed_domain_text"))
        original_narrative = _clean(row.get("mutation_narrative"))
        analysis_hits = {
            field: matches
            for field in GENE_ANALYSIS_FIELDS
            if (matches := _matched_terms(row.get(field), terms))
        }
        fixed_domain_unsafe = "fixed_domain_text" in analysis_hits
        narrative_unsafe = "mutation_narrative" in analysis_hits
        composed_analysis_unsafe = "mutation_analysis" in analysis_hits
        if fixed_domain_unsafe:
            row["fixed_domain_text"] = ""
        if narrative_unsafe:
            row["mutation_narrative"] = notice
        if fixed_domain_unsafe or narrative_unsafe or composed_analysis_unsafe:
            if fixed_domain_unsafe or narrative_unsafe:
                safe_parts = [
                    notice if fixed_domain_unsafe else original_fixed_domain,
                    notice if narrative_unsafe else original_narrative,
                ]
                deduplicated_parts: list[str] = []
                for part in safe_parts:
                    if part and (not deduplicated_parts or part != deduplicated_parts[-1]):
                        deduplicated_parts.append(part)
                row["mutation_analysis"] = "\n".join(deduplicated_parts) or notice
            else:
                row["mutation_analysis"] = notice
            for field, matches in analysis_hits.items():
                suppressed.append(
                    {
                        "table": "gene_knowledge_sections",
                        "row_index": row_index,
                        "gene": gene,
                        "field": field,
                        "matched_terms": matches,
                    }
                )
    if gene_rows:
        report_data.set_table("gene_knowledge_sections", gene_rows)

    drug_rows = [dict(row) for row in report_data.get_table("drug_analysis_sections")]
    for row_index, row in enumerate(drug_rows):
        gene = _clean(row.get("gene")).upper()
        for field in DRUG_TEXT_FIELDS:
            matches = _matched_terms(row.get(field), terms)
            if not matches:
                continue
            row[field] = notice
            suppressed.append(
                {
                    "table": "drug_analysis_sections",
                    "row_index": row_index,
                    "gene": gene,
                    "field": field,
                    "matched_terms": matches,
                }
            )
    if drug_rows:
        report_data.set_table("drug_analysis_sections", drug_rows)
        report_data.set_table(
            "drug_benefit_sections",
            [row for row in drug_rows if row.get("drug_type") == "benefit"],
        )
        report_data.set_table(
            "drug_caution_sections",
            [row for row in drug_rows if row.get("drug_type") == "caution"],
        )
        report_data.set_table(
            "drug_research_sections",
            [row for row in drug_rows if row.get("drug_type") == "research"],
        )

    result = {
        "enabled": True,
        "action": action,
        "scope": "part3_structured_fields",
        "suppressed_field_count": len(suppressed),
        "suppressed_row_count": len(
            {(row["table"], row["row_index"]) for row in suppressed}
        ),
        "notice": notice,
        "rows": suppressed,
    }
    report_data.set_field("part3_cross_cancer_suppression", result)
    return result
