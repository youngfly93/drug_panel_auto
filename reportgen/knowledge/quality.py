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
from typing import Any, Iterable

import yaml

from reportgen.knowledge.gene_knowledge import GeneKnowledgeProvider


GENERIC_ANALYSIS_FRAGMENT = (
    "基因突变在多种肿瘤中被报道，其突变可能影响蛋白功能和下游信号通路"
)
GENERIC_ANALYSIS_ENDING = "临床意义是当前研究的热点领域"
SENTINEL_C_HGVS = "c.999999A>G"
SENTINEL_P_HGVS = "p.X999999Y"


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
        texts.extend((intro, analysis))
        if not intro:
            missing_intro.append(gene)
        if not analysis:
            missing_analysis.append(gene)
        elif is_generic_mutation_analysis(gene, analysis):
            generic_analysis.append(gene)

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
