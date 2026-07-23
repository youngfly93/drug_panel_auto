# 步骤: 23_profile_lung588_medical_knowledge
# 上游: lung588 knowledge_coverage/context_contracts/medical_candidates + panel-scoped runtime knowledge provider
# 输出: .work/lung588_medical_knowledge/knowledge_depth_inventory.json + knowledge_review_queue.tsv
# 种子: 无（固定哨兵变异、确定性优先级与字典序）
"""Build a de-identified, row-level lung588 medical-knowledge review queue."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reportgen.knowledge.quality import (  # noqa: E402
    BLOCKING_CITATION_REVIEW_STATUSES,
    SENTINEL_C_HGVS,
    SENTINEL_P_HGVS,
    build_panel_gene_provider,
    extract_reference_identifiers,
    is_generic_mutation_analysis,
    load_panel_citation_source_reviews,
)
from reportgen.panels.loader import PanelPackageLoader  # noqa: E402


PANEL_ID = "lung_588_pdl1"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _reportable_genes(package: Any) -> list[str]:
    raw = yaml.safe_load(
        package.resolve_rule_file("knowledge_coverage").read_text(encoding="utf-8")
    ) or {}
    genes = [
        _clean(gene).upper()
        for gene in (raw.get("reportable_genes") or [])
        if _clean(gene)
    ]
    if len(genes) != len(set(genes)):
        raise ValueError("lung588 knowledge denominator contains duplicate genes")
    return genes


def _observed_events(package: Any) -> dict[str, list[dict[str, str]]]:
    events: dict[str, list[dict[str, str]]] = defaultdict(list)
    contracts = (package.raw or {}).get("context_contracts") or {}
    for contract_id, raw_path in sorted(contracts.items()):
        path = package._resolve_path(raw_path)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = (
            ((data.get("tables") or {}).get("all_variants") or {}).get("rows")
            or []
        )
        for row in rows:
            if not isinstance(row, dict):
                continue
            match = row.get("match") or {}
            expect = row.get("expect") or {}
            gene = _clean(((match.get("gene") or {}).get("equals"))).upper()
            transcript = _clean(
                ((expect.get("transcript") or {}).get("equals"))
            )
            chromosome = _clean(
                ((expect.get("chromosome") or {}).get("equals"))
            )
            exon = _clean(((expect.get("exon") or {}).get("equals")))
            c_hgvs = _clean(((match.get("cHGVS") or {}).get("equals")))
            p_hgvs = _clean(((expect.get("pHGVS") or {}).get("equals")))
            gene_class = _clean(
                ((expect.get("gene_class") or {}).get("equals"))
            )
            frequency = _clean(
                ((expect.get("frequency") or {}).get("equals"))
            )
            if not gene:
                continue
            events[gene].append(
                {
                    "case_alias": str(contract_id).upper().replace("_", "-"),
                    "transcript": transcript,
                    "chromosome": chromosome,
                    "exon": exon,
                    "c_hgvs": c_hgvs,
                    "p_hgvs": p_hgvs,
                    "gene_class": gene_class,
                    "frequency": frequency,
                }
            )
    return events


def _candidate_events(package: Any) -> dict[str, list[dict[str, str]]]:
    raw = yaml.safe_load(
        package.resolve_rule_file("medical_candidates").read_text(encoding="utf-8")
    ) or {}
    events: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in raw.get("candidate_rules") or []:
        if not isinstance(row, dict):
            continue
        gene = _clean(row.get("gene")).upper()
        selector = row.get("selector") or {}
        therapy = row.get("therapy") or {}
        if not gene:
            continue
        events[gene].append(
            {
                "candidate_id": _clean(row.get("candidate_id")),
                "transcript": _clean(selector.get("transcript")),
                "c_hgvs": _clean(selector.get("c_hgvs")),
                "p_hgvs": _clean(selector.get("p_hgvs")),
                "therapy": _clean(therapy.get("generic_name_zh")),
                "review_status": _clean(row.get("review_status")),
                "secondary_review_status": _clean(
                    row.get("secondary_review_status")
                ),
            }
        )
    return events


def _priority(
    gene: str,
    *,
    observed: set[str],
    candidates: set[str],
    missing_analysis: bool,
    generic_analysis: bool,
    missing_domain: bool,
    citation_source_mismatch: bool,
) -> tuple[str, str]:
    if citation_source_mismatch:
        return "P0", "运行候选文本存在已确认的文献—声明错配，必须阻断并重审"
    if gene in observed or gene in candidates:
        return (
            "P0",
            "真实脱敏病例已检出或存在精确药物候选，须先完成逐事件医学审核",
        )
    if missing_analysis:
        return "P1", "此前未见变异无法形成变异解析"
    if generic_analysis:
        return "P2", "当前仅有跨癌种通用fallback，尚非肺癌特异解释"
    if missing_domain:
        return "P3", "缺固定蛋白/结构域内容"
    return "P4", "当前基础内容完整，仍待抽样医学复核"


def _action(
    *,
    missing_analysis: bool,
    generic_analysis: bool,
    missing_domain: bool,
    has_candidate: bool,
    citation_source_mismatch: bool,
) -> str:
    actions: list[str] = []
    if citation_source_mismatch:
        actions.append("移除或替换不支持当前声明的文献并完成逐声明二审")
    if missing_analysis:
        actions.append("补肺癌边界清楚的基因级变异解析")
    if generic_analysis:
        actions.append("用可追溯肺癌/基因功能证据替换通用套话")
    if missing_domain:
        actions.append("从官方蛋白资源补固定结构域并校验转录本")
    if has_candidate:
        actions.append("按精确位点、适应证上下文、药物和当前标签逐条二审")
    return "；".join(actions) or "抽样复核现有文案与来源"


def build_inventory(root: Path, as_of: str) -> dict[str, Any]:
    package = PanelPackageLoader(project_root=root).load(PANEL_ID)
    genes = _reportable_genes(package)
    observed_events = _observed_events(package)
    candidate_events = _candidate_events(package)
    observed_genes = set(observed_events)
    candidate_genes = set(candidate_events)
    provider = build_panel_gene_provider(root, package)
    reference_lookup = provider.build_reference_lookup()
    known_pmids = set(reference_lookup.get("pmid") or {})
    known_trials = set(reference_lookup.get("trial") or {})
    citation_reviews: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in load_panel_citation_source_reviews(package):
        if finding["status"] in BLOCKING_CITATION_REVIEW_STATUSES:
            citation_reviews[finding["gene"]].append(finding)

    rows: list[dict[str, Any]] = []
    for index, gene in enumerate(genes, start=1):
        section = provider.build_gene_knowledge_section(
            gene=gene,
            c_hgvs=SENTINEL_C_HGVS,
            p_hgvs=SENTINEL_P_HGVS,
            frequency=10.0,
            mutation_type="Missense",
            has_drug=False,
        )
        intro = _clean(section.get("intro"))
        analysis = _clean(section.get("mutation_analysis"))
        fixed_domain = _clean(section.get("fixed_domain_text"))
        missing_intro = not intro
        missing_analysis = not analysis
        missing_domain = not fixed_domain
        generic_analysis = bool(
            analysis and is_generic_mutation_analysis(gene, analysis)
        )
        identifiers = extract_reference_identifiers(
            (intro, analysis, fixed_domain)
        )
        unresolved_pmids = sorted(identifiers["pmid"] - known_pmids)
        unresolved_trials = sorted(identifiers["trial"] - known_trials)
        source_mismatches = []
        runtime_text = "\n".join((intro, analysis, fixed_domain))
        for finding in citation_reviews.get(gene, []):
            identifier_match = re.search(
                r"(?i)PMID\s*[:：]?\s*0*(\d{5,9})",
                finding["identifier"],
            )
            if not identifier_match:
                continue
            pmid = str(int(identifier_match.group(1)))
            if pmid not in identifiers["pmid"]:
                continue
            source_mismatches.append(
                {
                    **finding,
                    "claim_fragment_present": bool(
                        finding["claim_contains"]
                        and finding["claim_contains"] in runtime_text
                    ),
                }
            )
        priority, reason = _priority(
            gene,
            observed=observed_genes,
            candidates=candidate_genes,
            missing_analysis=missing_analysis,
            generic_analysis=generic_analysis,
            missing_domain=missing_domain,
            citation_source_mismatch=bool(source_mismatches),
        )
        rows.append(
            {
                "index": index,
                "gene": gene,
                "priority": priority,
                "priority_reason": reason,
                "observed_case_event_count": len(observed_events.get(gene, [])),
                "candidate_drug_rule_count": len(candidate_events.get(gene, [])),
                "intro_present": not missing_intro,
                "mutation_analysis_present": not missing_analysis,
                "specific_mutation_analysis": bool(
                    analysis and not generic_analysis
                ),
                "fixed_domain_present": not missing_domain,
                "cited_pmid_count": len(identifiers["pmid"]),
                "cited_trial_count": len(identifiers["trial"]),
                "unresolved_pmids": unresolved_pmids,
                "unresolved_trials": unresolved_trials,
                "citation_source_mismatches": source_mismatches,
                "recommended_action": _action(
                    missing_analysis=missing_analysis,
                    generic_analysis=generic_analysis,
                    missing_domain=missing_domain,
                    has_candidate=gene in candidate_genes,
                    citation_source_mismatch=bool(source_mismatches),
                ),
                "medical_review_status": "pending_report_group_review",
                "secondary_review_decision": "",
                "secondary_reviewer": "",
                "secondary_reviewed_at": "",
                "observed_events": observed_events.get(gene, []),
                "candidate_events": candidate_events.get(gene, []),
            }
        )

    priority_counts = Counter(row["priority"] for row in rows)
    return {
        "schema_version": "1.0",
        "panel_id": PANEL_ID,
        "as_of": as_of,
        "git_head": _git_head(root),
        "purpose": "lung588_medical_knowledge_depth_and_review_queue",
        "privacy": {
            "contains_phi": False,
            "case_identity": "CASE aliases and source hashes only",
        },
        "denominator": {
            "total_genes": len(genes),
            "ordered_gene_list_sha256": (
                yaml.safe_load(
                    package.resolve_rule_file("knowledge_coverage").read_text(
                        encoding="utf-8"
                    )
                )
                or {}
            )
            .get("contract", {})
            .get("ordered_gene_list_sha256", ""),
        },
        "summary": {
            "complete_intro_count": sum(row["intro_present"] for row in rows),
            "complete_mutation_analysis_count": sum(
                row["mutation_analysis_present"] for row in rows
            ),
            "specific_mutation_analysis_count": sum(
                row["specific_mutation_analysis"] for row in rows
            ),
            "fixed_domain_count": sum(row["fixed_domain_present"] for row in rows),
            "observed_case_gene_count": len(observed_genes),
            "candidate_rule_gene_count": len(candidate_genes),
            "priority_counts": dict(sorted(priority_counts.items())),
            "unresolved_pmid_count": len(
                {
                    pmid
                    for row in rows
                    for pmid in row["unresolved_pmids"]
                }
            ),
            "citation_source_mismatch_count": sum(
                len(row["citation_source_mismatches"]) for row in rows
            ),
        },
        "priority_contract": {
            "P0": "observed de-identified case event or exact drug candidate",
            "P1": "missing mutation analysis",
            "P2": "generic mutation-analysis fallback",
            "P3": "missing fixed protein/domain content",
            "P4": "structurally complete baseline pending sampled medical review",
        },
        "rows": rows,
    }


def write_outputs(payload: dict[str, Any], json_path: Path, tsv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    fields = [
        "index",
        "gene",
        "priority",
        "priority_reason",
        "observed_case_event_count",
        "candidate_drug_rule_count",
        "intro_present",
        "mutation_analysis_present",
        "specific_mutation_analysis",
        "fixed_domain_present",
        "cited_pmid_count",
        "cited_trial_count",
        "unresolved_pmids",
        "unresolved_trials",
        "citation_source_mismatches",
        "recommended_action",
        "medical_review_status",
        "secondary_review_decision",
        "secondary_reviewer",
        "secondary_reviewed_at",
        "observed_events",
        "candidate_events",
    ]
    with tsv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in payload["rows"]:
            writer.writerow(
                {
                    key: (
                        json.dumps(row[key], ensure_ascii=False, sort_keys=True)
                        if isinstance(row[key], (list, dict))
                        else row[key]
                    )
                    for key in fields
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".work/lung588_medical_knowledge"),
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    output_dir = (
        args.output_dir
        if args.output_dir.is_absolute()
        else root / args.output_dir
    )
    payload = build_inventory(root, args.as_of)
    json_path = output_dir / "knowledge_depth_inventory.json"
    tsv_path = output_dir / "knowledge_review_queue.tsv"
    write_outputs(payload, json_path, tsv_path)
    summary = payload["summary"]
    print(
        f"panel={PANEL_ID} genes={payload['denominator']['total_genes']} "
        f"specific={summary['specific_mutation_analysis_count']} "
        f"domain={summary['fixed_domain_count']} "
        f"priority={summary['priority_counts']}"
    )
    print(f"json={json_path}")
    print(f"tsv={tsv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
