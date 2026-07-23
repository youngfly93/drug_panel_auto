# 步骤: 23_profile_lung588_medical_knowledge
# 上游: lung588 knowledge_coverage/context_contracts/medical_candidates + panel-scoped runtime knowledge provider
# 输出: .work/lung588_medical_knowledge/knowledge_depth_inventory.json + 二审总表/分批TSV与manifest
# 种子: 无（固定哨兵变异、确定性优先级与字典序）
"""Build a de-identified, row-level lung588 medical-knowledge review queue."""

from __future__ import annotations

import argparse
import csv
import hashlib
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
from reportgen.knowledge.governance import effective_governance  # noqa: E402
from reportgen.panels.loader import PanelPackageLoader  # noqa: E402


PANEL_ID = "lung_588_pdl1"
PRIORITY_ORDER = ("P0", "P1", "P2", "P3", "P4")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _text_sha256(value: Any) -> str:
    return hashlib.sha256(_clean(value).encode("utf-8")).hexdigest()


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


def _fixed_domain_candidates(package: Any) -> dict[str, dict[str, Any]]:
    """Load sourced, non-runtime domain candidates for secondary review."""

    candidates: dict[str, dict[str, Any]] = {}
    additions = (package.raw or {}).get(
        "reviewed_part3_overlay_additions"
    ) or []
    if isinstance(additions, str):
        additions = [additions]
    for declared_path in additions:
        path = package._resolve_path(declared_path)
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if (
            (raw.get("source") or {}).get("activation_mode")
            != "candidate_only_pending_secondary_review"
        ):
            continue
        for row in raw.get("gene_sections") or []:
            if not isinstance(row, dict):
                continue
            gene = _clean(row.get("gene")).upper()
            fixed_domain_text = _clean(row.get("fixed_domain_text"))
            if not gene or not fixed_domain_text:
                continue
            if gene in candidates:
                raise ValueError(
                    f"duplicate lung588 domain candidate: {gene}"
                )
            governance = effective_governance(raw, row, "gene")
            selection = row.get("accession_selection") or {}
            candidates[gene] = {
                "fixed_domain_text": fixed_domain_text,
                "fixed_domain_text_sha256": _text_sha256(
                    fixed_domain_text
                ),
                "uniprot_accession": _clean(
                    row.get("uniprot_accession")
                ),
                "interpro_entries": [
                    _clean(value)
                    for value in row.get("interpro_entries") or []
                    if _clean(value)
                ],
                "source_refs": governance["source_refs"],
                "review_status": governance["status"],
                "runtime_eligible": governance["runtime_eligible"],
                "secondary_review_status": governance[
                    "secondary_review_status"
                ],
                "accession_selection": selection,
            }
    return candidates


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
    has_domain_candidate: bool,
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
        if has_domain_candidate:
            actions.append("复核官方蛋白结构域候选、accession及转录本/产物边界")
        else:
            actions.append("从官方蛋白资源补固定结构域并校验转录本")
    if has_candidate:
        actions.append("按精确位点、适应证上下文、药物和当前标签逐条二审")
    return "；".join(actions) or "抽样复核现有文案与来源"


def build_inventory(root: Path, as_of: str) -> dict[str, Any]:
    package = PanelPackageLoader(project_root=root).load(PANEL_ID)
    genes = _reportable_genes(package)
    observed_events = _observed_events(package)
    candidate_events = _candidate_events(package)
    domain_candidates = _fixed_domain_candidates(package)
    unexpected_domain_candidates = set(domain_candidates) - set(genes)
    if unexpected_domain_candidates:
        raise ValueError(
            "lung588 domain candidates fall outside the denominator: "
            + ", ".join(sorted(unexpected_domain_candidates))
        )
    runtime_domain_candidates = sorted(
        gene
        for gene, row in domain_candidates.items()
        if row["runtime_eligible"]
    )
    if runtime_domain_candidates:
        raise ValueError(
            "lung588 domain candidates must remain non-runtime pending "
            "secondary review: "
            + ", ".join(runtime_domain_candidates)
        )
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
        mutation_narrative = _clean(section.get("mutation_narrative"))
        fixed_domain = _clean(section.get("fixed_domain_text"))
        missing_intro = not intro
        missing_analysis = not analysis
        missing_mutation_narrative = not mutation_narrative
        missing_domain = not fixed_domain
        domain_candidate = domain_candidates.get(gene) or {}
        has_domain_candidate = bool(domain_candidate)
        generic_analysis = bool(
            mutation_narrative
            and is_generic_mutation_analysis(gene, mutation_narrative)
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
            missing_analysis=missing_mutation_narrative,
            generic_analysis=generic_analysis,
            missing_domain=missing_domain,
            citation_source_mismatch=bool(source_mismatches),
        )
        review_tracks: list[str] = []
        if gene in observed_genes:
            review_tracks.append("observed_case_event")
        if gene in candidate_genes:
            review_tracks.append("exact_drug_candidate")
        if missing_mutation_narrative:
            review_tracks.append("missing_mutation_narrative")
        elif generic_analysis:
            review_tracks.append("generic_mutation_narrative")
        else:
            review_tracks.append("specific_mutation_narrative")
        if missing_domain:
            review_tracks.append(
                "fixed_domain_candidate_pending_secondary_review"
                if has_domain_candidate
                else "missing_fixed_domain"
            )
        else:
            review_tracks.append("fixed_domain_present")
        if source_mismatches:
            source_status = "confirmed_runtime_source_mismatch"
        elif unresolved_pmids or unresolved_trials:
            source_status = "unresolved_runtime_reference_identifier"
        elif identifiers["pmid"] or identifiers["trial"]:
            source_status = "structured_runtime_reference_identifier_present"
        else:
            source_status = "no_runtime_reference_identifier"
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
                "mutation_narrative_present": (
                    not missing_mutation_narrative
                ),
                "composed_analysis_without_narrative": bool(
                    analysis and missing_mutation_narrative
                ),
                "specific_mutation_analysis": bool(
                    mutation_narrative and not generic_analysis
                ),
                "specific_mutation_narrative": bool(
                    mutation_narrative and not generic_analysis
                ),
                "generic_mutation_narrative": generic_analysis,
                "fixed_domain_present": not missing_domain,
                "fixed_domain_candidate_available": has_domain_candidate,
                "fixed_domain_candidate": domain_candidate,
                "review_tracks": review_tracks,
                "source_status": source_status,
                "runtime_text_sha256": {
                    "intro": _text_sha256(intro),
                    "mutation_analysis": _text_sha256(analysis),
                    "mutation_narrative": _text_sha256(
                        mutation_narrative
                    ),
                    "fixed_domain_text": _text_sha256(fixed_domain),
                },
                "runtime_content": {
                    "intro": intro,
                    "mutation_narrative": mutation_narrative,
                    "fixed_domain_text": fixed_domain,
                },
                "cited_pmid_count": len(identifiers["pmid"]),
                "cited_trial_count": len(identifiers["trial"]),
                "unresolved_pmids": unresolved_pmids,
                "unresolved_trials": unresolved_trials,
                "citation_source_mismatches": source_mismatches,
                "recommended_action": _action(
                    missing_analysis=missing_mutation_narrative,
                    generic_analysis=generic_analysis,
                    missing_domain=missing_domain,
                    has_domain_candidate=has_domain_candidate,
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
            "complete_mutation_narrative_count": sum(
                row["mutation_narrative_present"] for row in rows
            ),
            "composed_analysis_without_narrative_count": sum(
                row["composed_analysis_without_narrative"] for row in rows
            ),
            "specific_mutation_analysis_count": sum(
                row["specific_mutation_analysis"] for row in rows
            ),
            "specific_mutation_narrative_count": sum(
                row["specific_mutation_narrative"] for row in rows
            ),
            "generic_mutation_narrative_count": sum(
                row["generic_mutation_narrative"] for row in rows
            ),
            "fixed_domain_count": sum(row["fixed_domain_present"] for row in rows),
            "fixed_domain_candidate_count": sum(
                row["fixed_domain_candidate_available"] for row in rows
            ),
            "fixed_domain_candidate_runtime_eligible_count": sum(
                bool(
                    row["fixed_domain_candidate"]
                    and row["fixed_domain_candidate"]["runtime_eligible"]
                )
                for row in rows
            ),
            "fixed_domain_candidate_ambiguous_mapping_count": sum(
                bool(
                    row["fixed_domain_candidate"]
                    and row["fixed_domain_candidate"].get(
                        "accession_selection"
                    )
                )
                for row in rows
            ),
            "fixed_domain_candidate_transcript_product_review_count": sum(
                bool(
                    row["fixed_domain_candidate"]
                    and (
                        row["fixed_domain_candidate"].get(
                            "accession_selection"
                        )
                        or {}
                    ).get("requires_transcript_product_review")
                )
                for row in rows
            ),
            "fixed_domain_runtime_or_candidate_count": sum(
                row["fixed_domain_present"]
                or row["fixed_domain_candidate_available"]
                for row in rows
            ),
            "depth_strata": {
                "missing_narrative_and_domain": sum(
                    not row["mutation_narrative_present"]
                    and not row["fixed_domain_present"]
                    for row in rows
                ),
                "narrative_present_domain_missing": sum(
                    row["mutation_narrative_present"]
                    and not row["fixed_domain_present"]
                    for row in rows
                ),
                "domain_present_narrative_missing": sum(
                    row["fixed_domain_present"]
                    and not row["mutation_narrative_present"]
                    for row in rows
                ),
                "narrative_and_domain_present": sum(
                    row["mutation_narrative_present"]
                    and row["fixed_domain_present"]
                    for row in rows
                ),
            },
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
            "P1": "missing non-domain mutation narrative",
            "P2": "generic mutation-analysis fallback",
            "P3": "missing fixed protein/domain content",
            "P4": "structurally complete baseline pending sampled medical review",
        },
        "rows": rows,
    }


def build_review_batches(
    payload: dict[str, Any],
    *,
    batch_size: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Partition the full denominator into deterministic review-sized batches."""

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    assignments: list[dict[str, Any]] = []
    batches: list[dict[str, Any]] = []
    sequence = 0
    for priority in PRIORITY_ORDER:
        priority_rows = [
            row for row in payload["rows"] if row["priority"] == priority
        ]
        for offset in range(0, len(priority_rows), batch_size):
            chunk = priority_rows[offset : offset + batch_size]
            batch_number = offset // batch_size + 1
            batch_id = f"LUNG588-{priority}-{batch_number:02d}"
            track_counts: Counter[str] = Counter(
                track
                for row in chunk
                for track in row["review_tracks"]
            )
            source_counts = Counter(row["source_status"] for row in chunk)
            batches.append(
                {
                    "batch_id": batch_id,
                    "priority": priority,
                    "row_count": len(chunk),
                    "first_panel_index": chunk[0]["index"],
                    "last_panel_index": chunk[-1]["index"],
                    "review_track_counts": dict(sorted(track_counts.items())),
                    "source_status_counts": dict(sorted(source_counts.items())),
                    "secondary_review_completed_count": 0,
                    "patient_visible_allowed_count": 0,
                }
            )
            for batch_row, row in enumerate(chunk, start=1):
                sequence += 1
                runtime_content = row["runtime_content"]
                domain_candidate = row["fixed_domain_candidate"]
                accession_selection = (
                    domain_candidate.get("accession_selection") or {}
                    if domain_candidate
                    else {}
                )
                assignments.append(
                    {
                        "review_sequence": sequence,
                        "batch_id": batch_id,
                        "batch_row": batch_row,
                        "panel_index": row["index"],
                        "gene": row["gene"],
                        "priority": row["priority"],
                        "priority_reason": row["priority_reason"],
                        "review_tracks": row["review_tracks"],
                        "observed_case_event_count": row[
                            "observed_case_event_count"
                        ],
                        "candidate_drug_rule_count": row[
                            "candidate_drug_rule_count"
                        ],
                        "mutation_narrative_present": row[
                            "mutation_narrative_present"
                        ],
                        "generic_mutation_narrative": row[
                            "generic_mutation_narrative"
                        ],
                        "fixed_domain_present": row[
                            "fixed_domain_present"
                        ],
                        "fixed_domain_candidate_available": row[
                            "fixed_domain_candidate_available"
                        ],
                        "candidate_fixed_domain_text": (
                            domain_candidate.get("fixed_domain_text", "")
                        ),
                        "candidate_uniprot_accession": (
                            domain_candidate.get("uniprot_accession", "")
                        ),
                        "candidate_source_refs": (
                            domain_candidate.get("source_refs", [])
                        ),
                        "candidate_review_status": (
                            domain_candidate.get("review_status", "")
                        ),
                        "candidate_secondary_review_status": (
                            domain_candidate.get(
                                "secondary_review_status", ""
                            )
                        ),
                        "candidate_accession_selection": (
                            accession_selection
                        ),
                        "source_status": row["source_status"],
                        "runtime_intro": runtime_content["intro"],
                        "runtime_mutation_narrative": runtime_content[
                            "mutation_narrative"
                        ],
                        "runtime_fixed_domain_text": runtime_content[
                            "fixed_domain_text"
                        ],
                        "runtime_text_sha256": row["runtime_text_sha256"],
                        "recommended_action": row["recommended_action"],
                        "medical_review_status": (
                            "pending_report_group_review"
                        ),
                        "secondary_review_decision": "",
                        "secondary_reviewer": "",
                        "secondary_reviewed_at": "",
                        "patient_visible_allowed": False,
                    }
                )

    return (
        {
            "schema_version": "1.0",
            "panel_id": payload["panel_id"],
            "git_head": payload["git_head"],
            "as_of": payload["as_of"],
            "purpose": "deterministic_lung588_knowledge_secondary_review_batches",
            "privacy": payload["privacy"],
            "batch_size": batch_size,
            "total_rows": len(assignments),
            "batch_count": len(batches),
            "priority_order": list(PRIORITY_ORDER),
            "medical_release_boundary": (
                "Every row remains patient-ineligible until an attributed "
                "secondary-review decision is recorded."
            ),
            "batches": batches,
        },
        assignments,
    )


def _write_tsv(
    rows: list[dict[str, Any]],
    path: Path,
    fields: list[str],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in rows:
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


def write_outputs(
    payload: dict[str, Any],
    json_path: Path,
    tsv_path: Path,
    *,
    batch_size: int,
) -> dict[str, Path]:
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
        "mutation_narrative_present",
        "composed_analysis_without_narrative",
        "specific_mutation_analysis",
        "specific_mutation_narrative",
        "generic_mutation_narrative",
        "fixed_domain_present",
        "fixed_domain_candidate_available",
        "fixed_domain_candidate",
        "review_tracks",
        "source_status",
        "runtime_text_sha256",
        "runtime_content",
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
    _write_tsv(payload["rows"], tsv_path, fields)

    batch_manifest, assignments = build_review_batches(
        payload,
        batch_size=batch_size,
    )
    manifest_path = json_path.parent / "knowledge_review_batch_manifest.json"
    manifest_path.write_text(
        json.dumps(batch_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    batch_fields = [
        "review_sequence",
        "batch_id",
        "batch_row",
        "panel_index",
        "gene",
        "priority",
        "priority_reason",
        "review_tracks",
        "observed_case_event_count",
        "candidate_drug_rule_count",
        "mutation_narrative_present",
        "generic_mutation_narrative",
        "fixed_domain_present",
        "fixed_domain_candidate_available",
        "candidate_fixed_domain_text",
        "candidate_uniprot_accession",
        "candidate_source_refs",
        "candidate_review_status",
        "candidate_secondary_review_status",
        "candidate_accession_selection",
        "source_status",
        "runtime_intro",
        "runtime_mutation_narrative",
        "runtime_fixed_domain_text",
        "runtime_text_sha256",
        "recommended_action",
        "medical_review_status",
        "secondary_review_decision",
        "secondary_reviewer",
        "secondary_reviewed_at",
        "patient_visible_allowed",
    ]
    batch_tsv_path = json_path.parent / "knowledge_review_batches.tsv"
    _write_tsv(assignments, batch_tsv_path, batch_fields)
    batch_dir = json_path.parent / "review_batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    for batch in batch_manifest["batches"]:
        batch_rows = [
            row
            for row in assignments
            if row["batch_id"] == batch["batch_id"]
        ]
        _write_tsv(
            batch_rows,
            batch_dir / f"{batch['batch_id']}.tsv",
            batch_fields,
        )
    return {
        "inventory_json": json_path,
        "review_queue_tsv": tsv_path,
        "batch_manifest_json": manifest_path,
        "review_batches_tsv": batch_tsv_path,
        "review_batch_dir": batch_dir,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".work/lung588_medical_knowledge"),
    )
    parser.add_argument("--batch-size", type=int, default=25)
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
    outputs = write_outputs(
        payload,
        json_path,
        tsv_path,
        batch_size=args.batch_size,
    )
    summary = payload["summary"]
    print(
        f"panel={PANEL_ID} genes={payload['denominator']['total_genes']} "
        f"specific={summary['specific_mutation_analysis_count']} "
        f"domain={summary['fixed_domain_count']} "
        f"priority={summary['priority_counts']}"
    )
    print(f"json={json_path}")
    print(f"tsv={tsv_path}")
    print(f"batch_manifest={outputs['batch_manifest_json']}")
    print(f"batch_tsv={outputs['review_batches_tsv']}")
    print(f"batch_dir={outputs['review_batch_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
