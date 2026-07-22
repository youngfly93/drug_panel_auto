"""Runtime-facing quality checks for panel knowledge content.

The release gate historically treated a gene name present in either the base
workbook or an overlay as complete coverage.  That is useful for migration
accounting, but it does not prove that the final provider can render both a
gene introduction and a mutation-analysis paragraph.  This module evaluates
the same provider configuration used by report generation and keeps structural
coverage separate from content depth.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from reportgen.knowledge.gene_knowledge import GeneKnowledgeProvider
from reportgen.rules.targeted_drugs import load_targeted_drug_rule_context


GENERIC_ANALYSIS_FRAGMENT = (
    "基因突变在多种肿瘤中被报道，其突变可能影响蛋白功能和下游信号通路"
)
GENERIC_ANALYSIS_ENDING = "临床意义是当前研究的热点领域"
SENTINEL_C_HGVS = "c.999999A>G"
SENTINEL_P_HGVS = "p.X999999Y"
SENTINEL_LOF_C_HGVS = "c.1del"
SENTINEL_LOF_P_HGVS = "p.M1Rfs*2"


def _overlay_paths(package: Any) -> list[str]:
    raw = getattr(package, "raw", None) or {}
    values: list[str] = []
    primary = raw.get("reviewed_part3_overlay")
    if primary:
        values.append(str(primary))
    additions = raw.get("reviewed_part3_overlay_additions") or []
    if isinstance(additions, str):
        additions = [additions]
    values.extend(str(value) for value in additions if str(value).strip())
    return [str(package._resolve_path(value).resolve()) for value in values]


def build_panel_gene_provider(project_root: str | Path, package: Any) -> GeneKnowledgeProvider:
    """Build the exact panel-scoped gene provider used by report generation."""
    root = Path(project_root).resolve()
    settings = yaml.safe_load(
        (root / "config/settings.yaml").read_text(encoding="utf-8")
    ) or {}
    knowledge = settings.get("knowledge_bases") or {}
    gene_config = dict(knowledge.get("gene_knowledge_db") or {})
    gene_config["reviewed_part3_overlay_path"] = ""
    gene_config["reviewed_part3_overlay_paths"] = _overlay_paths(package)
    provider = GeneKnowledgeProvider(
        {
            "enabled": True,
            "panel_id": package.panel_id,
            "gene_symbol_aliases": (
                (getattr(package, "raw", None) or {}).get(
                    "gene_symbol_aliases"
                )
                or {}
            ),
            "gene_knowledge_db": gene_config,
            "gene_transcript_db": knowledge.get("gene_transcript_db") or {},
        }
    )
    provider.load(str(root))
    return provider


def is_generic_mutation_analysis(gene: str, text: str) -> bool:
    normalized = re.sub(r"\s+", "", str(text or ""))
    gene_key = re.sub(r"\s+", "", str(gene or "").upper())
    return (
        f"{gene_key}{GENERIC_ANALYSIS_FRAGMENT}" in normalized.upper()
        and GENERIC_ANALYSIS_ENDING in normalized
    )


def extract_reference_identifiers(texts: Iterable[str]) -> dict[str, set[str]]:
    """Extract bracketed PMID and trial identifiers without treating years as PMIDs."""
    pmids: set[str] = set()
    trials: set[str] = set()
    for raw in texts:
        text = str(raw or "")
        for trial in re.findall(r"(?i)\b(?:NCT|CTR|ChiCTR)\d+\b", text):
            trials.add(trial.upper())
        for explicit in re.findall(r"(?i)PMID\s*[:：]?\s*0*(\d{5,9})", text):
            pmids.add(str(int(explicit)))
        for group in re.findall(r"\[([^\]]+)]", text):
            without_trials = re.sub(
                r"(?i)\b(?:NCT|CTR|ChiCTR)\d+\b", "", group
            )
            for token in re.split(r"[，,;；、]+", without_trials):
                token = token.strip()
                if re.fullmatch(r"0*\d{5,9}", token):
                    pmids.add(str(int(token)))
    return {"pmid": pmids, "trial": trials}


def profile_panel_runtime_content(
    project_root: str | Path,
    package: Any,
    genes: Iterable[str],
) -> dict[str, Any]:
    """Profile final provider output for a representative previously unseen SNV."""
    normalized_genes = sorted(
        {str(gene or "").strip().upper() for gene in genes if str(gene or "").strip()}
    )
    provider = build_panel_gene_provider(project_root, package)
    missing_intro: list[str] = []
    missing_analysis: list[str] = []
    missing_fixed_domain: list[str] = []
    duplicate_fixed_domain: list[str] = []
    generic_analysis: list[str] = []
    texts: list[str] = []
    for gene in normalized_genes:
        section = provider.build_gene_knowledge_section(
            gene=gene,
            c_hgvs=SENTINEL_C_HGVS,
            p_hgvs=SENTINEL_P_HGVS,
            frequency=10.0,
            mutation_type="Missense",
            has_drug=False,
        )
        intro = str(section.get("intro") or "").strip()
        analysis = str(section.get("mutation_analysis") or "").strip()
        fixed_domain = str(section.get("fixed_domain_text") or "").strip()
        texts.extend((intro, analysis))
        if not intro:
            missing_intro.append(gene)
        if not analysis:
            missing_analysis.append(gene)
        elif is_generic_mutation_analysis(gene, analysis):
            generic_analysis.append(gene)
        if not fixed_domain:
            missing_fixed_domain.append(gene)
        elif len(re.findall(r"编码的蛋白全长", fixed_domain)) > 1:
            duplicate_fixed_domain.append(gene)

    complete = len(normalized_genes) - len(set(missing_intro) | set(missing_analysis))
    specific = complete - len(generic_analysis)
    identifiers = extract_reference_identifiers(texts)
    lookup = provider.build_reference_lookup()
    unresolved_pmids = sorted(identifiers["pmid"] - set(lookup.get("pmid") or {}))
    unresolved_trials = sorted(
        identifiers["trial"] - set(lookup.get("trial") or {})
    )
    total = len(normalized_genes)
    return {
        "representative_variant": {
            "c_hgvs": SENTINEL_C_HGVS,
            "p_hgvs": SENTINEL_P_HGVS,
            "purpose": "previously_unseen_variant_fallback_contract",
        },
        "total_genes": total,
        "complete_genes": complete,
        "complete_percent": round(100.0 * complete / total, 2) if total else 100.0,
        "missing_intro_genes": missing_intro,
        "missing_analysis_genes": missing_analysis,
        "fixed_domain_covered_genes": total - len(missing_fixed_domain),
        "fixed_domain_coverage_percent": (
            round(100.0 * (total - len(missing_fixed_domain)) / total, 2)
            if total
            else 100.0
        ),
        "missing_fixed_domain_genes": missing_fixed_domain,
        "duplicate_fixed_domain_genes": duplicate_fixed_domain,
        "generic_fallback_genes": generic_analysis,
        "generic_fallback_count": len(generic_analysis),
        "generic_fallback_percent": (
            round(100.0 * len(generic_analysis) / total, 2) if total else 0.0
        ),
        "specific_explanation_genes": specific,
        "specific_explanation_percent": (
            round(100.0 * specific / total, 2) if total else 100.0
        ),
        "citation_integrity": {
            "cited_pmids": len(identifiers["pmid"]),
            "unresolved_pmids": unresolved_pmids,
            "cited_trials": len(identifiers["trial"]),
            "unresolved_trials": unresolved_trials,
        },
    }


def _drug_rule_text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _selector_values(value: Any, fallback: str) -> list[str]:
    if isinstance(value, (list, tuple)):
        values = [str(item).strip() for item in value if str(item).strip()]
        return values or [fallback]
    text = str(value or "").strip()
    return [text or fallback]


def _representative_targeted_drug_cases(
    context: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Expand every runtime rule selector into a deterministic synthetic case."""
    cases: list[dict[str, Any]] = []
    for gene, raw_rule in sorted((context.get("overrides") or {}).items()):
        rule = dict(raw_rule) if isinstance(raw_rule, Mapping) else {}
        cases.append(
            {
                "rule_id": f"gene_override:{str(gene).upper()}",
                "selector_kind": "gene_override",
                "gene": str(gene).upper(),
                "cHGVS": SENTINEL_C_HGVS,
                "pHGVS": SENTINEL_P_HGVS,
                "gene_class": "Ⅱ类",
                "benefit_drugs": _drug_rule_text(rule.get("benefit_drugs"))
                or "--",
                "caution_drugs": _drug_rule_text(rule.get("caution_drugs"))
                or "--",
            }
        )

    for index, raw_rule in enumerate(
        context.get("reviewed_variant_overrides") or [], start=1
    ):
        if not isinstance(raw_rule, Mapping):
            continue
        rule = dict(raw_rule)
        gene = str(rule.get("gene") or "").strip().upper()
        applicability = str(rule.get("applicability") or "").strip().lower()
        is_lof = applicability in {"loss_of_function", "lof", "truncating"}
        fallback_c = SENTINEL_LOF_C_HGVS if is_lof else SENTINEL_C_HGVS
        fallback_p = SENTINEL_LOF_P_HGVS if is_lof else SENTINEL_P_HGVS
        c_values = _selector_values(rule.get("c_hgvs"), fallback_c)
        p_values = _selector_values(rule.get("p_hgvs"), fallback_p)
        for c_hgvs in c_values:
            for p_hgvs in p_values:
                cases.append(
                    {
                        "rule_id": f"reviewed_rule:{index}:{gene}:{c_hgvs}:{p_hgvs}",
                        "selector_kind": "reviewed_variant_or_event",
                        "gene": gene,
                        "cHGVS": c_hgvs,
                        "pHGVS": p_hgvs,
                        "gene_class": "Ⅱ类",
                        "benefit_drugs": _drug_rule_text(
                            rule.get("benefit_drugs")
                        )
                        or "--",
                        "caution_drugs": _drug_rule_text(
                            rule.get("caution_drugs")
                        )
                        or "--",
                        "research_drugs": _drug_rule_text(
                            rule.get("research_drugs")
                        )
                        or "--",
                    }
                )
    return cases


def profile_panel_targeted_drug_contracts(
    project_root: str | Path,
    package: Any,
) -> dict[str, Any]:
    """Prove every configured Part-2 rule has an exact Part-3 contract.

    This is an inventory gate rather than a sampled-report check: every active
    gene, event and HGVS selector is synthesized, rendered through the real
    provider, and compared item-for-item in the same variant and direction.
    """
    context = load_targeted_drug_rule_context(package)
    if not context or not context.get("enabled"):
        return {
            "status": "NOT_APPLICABLE",
            "rules_checked": 0,
            "selector_cases_checked": 0,
            "expected_item_count": 0,
            "rendered_item_count": 0,
            "issues": [],
        }

    provider = build_panel_gene_provider(project_root, package)
    cases = _representative_targeted_drug_cases(context)
    issues: list[dict[str, Any]] = []
    expected_items = 0
    rendered_items = 0
    for case in cases:
        variant = {
            key: value
            for key, value in case.items()
            if key not in {"rule_id", "selector_kind"}
        }
        sections = provider.build_drug_analysis_sections([variant])
        consistency = provider.build_drug_analysis_consistency([variant], sections)
        coverage = provider.build_drug_analysis_contract_coverage([variant])
        expected_items += int(consistency.get("expected_item_count") or 0)
        rendered_items += int(consistency.get("rendered_item_count") or 0)
        if consistency.get("status") != "PASS":
            issues.append(
                {
                    "code": "TARGETED_DRUG_ANALYSIS_GAP",
                    "message": (
                        f"{package.panel_id} {case['rule_id']} does not render "
                        "the complete Part-3 drug analysis"
                    ),
                    "rule_id": case["rule_id"],
                    "gene": case["gene"],
                    "c_hgvs": case["cHGVS"],
                    "p_hgvs": case["pHGVS"],
                    "consistency": consistency,
                }
            )
        if coverage.get("status") != "PASS":
            issues.append(
                {
                    "code": "TARGETED_DRUG_CONTRACT_GAP",
                    "message": (
                        f"{package.panel_id} {case['rule_id']} still depends on "
                        "an ungoverned legacy Part-3 fallback"
                    ),
                    "rule_id": case["rule_id"],
                    "gene": case["gene"],
                    "c_hgvs": case["cHGVS"],
                    "p_hgvs": case["pHGVS"],
                    "coverage": coverage,
                }
            )

    rule_count = len(context.get("overrides") or {}) + len(
        context.get("reviewed_variant_overrides") or []
    )
    return {
        "status": "PASS" if not issues else "FAIL",
        "rules_checked": rule_count,
        "selector_cases_checked": len(cases),
        "expected_item_count": expected_items,
        "rendered_item_count": rendered_items,
        "issues": issues,
    }
