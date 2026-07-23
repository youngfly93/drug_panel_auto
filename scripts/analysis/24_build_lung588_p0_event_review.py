# 步骤: 24_build_lung588_p0_event_review
# 上游: lung588 context_contracts/medical_candidates/candidate_evidence_review/knowledge_coverage + panel-scoped runtime knowledge provider
# 输出: .work/lung588_p0_event_review/p0_event_review.json + p0_event_review.tsv
# 种子: 无（精确事件去重、固定优先级和字典序）
"""Build the de-identified first-review packet for lung588 P0 events."""

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
    build_panel_gene_provider,
    extract_reference_identifiers,
    is_generic_mutation_analysis,
    load_panel_citation_source_reviews,
)
from reportgen.panels.loader import PanelPackageLoader  # noqa: E402


PANEL_ID = "lung_588_pdl1"
EVENT_NARRATIVE_CANDIDATE_RELATIVE_PATHS = (
    "rules/reviewed_part3_p0_event_narrative_candidates.yaml",
    "rules/reviewed_part3_p0_cross_cancer_narrative_candidates.yaml",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _equals(spec: Any) -> str:
    if isinstance(spec, dict):
        return _clean(spec.get("equals"))
    return ""


def _variant_kind(c_hgvs: str, p_hgvs: str) -> str:
    if "fs" in p_hgvs.lower():
        return "frameshift"
    if p_hgvs.endswith("*"):
        return "stop_gained"
    if re.search(r"[+-]\d", c_hgvs):
        return "splice_region_or_site"
    if p_hgvs.startswith("p.") and re.search(r"[A-Z*]\d+[A-Z*]", p_hgvs):
        return "missense"
    return "other_or_unresolved"


def _provider_mutation_type(kind: str) -> str:
    return {
        "frameshift": "Frameshift",
        "stop_gained": "Nonsense",
        "splice_region_or_site": "Splice",
        "missense": "Missense",
    }.get(kind, "Unknown")


def _observed_variants(package: Any) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    contracts = (package.raw or {}).get("context_contracts") or {}
    for contract_id, raw_path in sorted(contracts.items()):
        path = package._resolve_path(raw_path)
        contract = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = (
            ((contract.get("tables") or {}).get("all_variants") or {}).get(
                "rows"
            )
            or []
        )
        case_alias = str(contract_id).upper().replace("_", "-")
        for row in rows:
            if not isinstance(row, dict):
                continue
            match = row.get("match") or {}
            expect = row.get("expect") or {}
            gene = _equals(match.get("gene")).upper()
            transcript = _equals(expect.get("transcript"))
            c_hgvs = _equals(match.get("cHGVS"))
            p_hgvs = _equals(expect.get("pHGVS"))
            if not gene or not transcript or not c_hgvs:
                continue
            key = (gene, transcript, c_hgvs, p_hgvs)
            item = grouped.setdefault(
                key,
                {
                    "gene": gene,
                    "transcript": transcript,
                    "chromosome": _equals(expect.get("chromosome")),
                    "exon": _equals(expect.get("exon")),
                    "c_hgvs": c_hgvs,
                    "p_hgvs": p_hgvs,
                    "observations": [],
                },
            )
            item["observations"].append(
                {
                    "case_alias": case_alias,
                    "gene_class": _equals(expect.get("gene_class")),
                    "frequency": _equals(expect.get("frequency")),
                }
            )
    return [
        {
            **item,
            "observations": sorted(
                item["observations"],
                key=lambda row: row["case_alias"],
            ),
        }
        for _, item in sorted(grouped.items())
    ]


def _medical_rules(package: Any) -> dict[str, Any]:
    return (
        yaml.safe_load(
            package.resolve_rule_file("medical_candidates").read_text(
                encoding="utf-8"
            )
        )
        or {}
    )


def _event_narrative_candidate_contracts(
    package: Any,
) -> list[dict[str, Any]]:
    return [
        yaml.safe_load(
            package._resolve_path(relative_path).read_text(
                encoding="utf-8"
            )
        )
        or {}
        for relative_path in EVENT_NARRATIVE_CANDIDATE_RELATIVE_PATHS
    ]


def _candidate_evidence_review_contract(package: Any) -> dict[str, Any]:
    return (
        yaml.safe_load(
            package.resolve_rule_file("candidate_evidence_review").read_text(
                encoding="utf-8"
            )
        )
        or {}
    )


def _candidate_evidence_reviews(
    contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    reviews: dict[str, dict[str, Any]] = {}
    for row in contract.get("reviews") or []:
        if not isinstance(row, dict):
            continue
        candidate_id = _clean(row.get("candidate_id"))
        if not candidate_id:
            continue
        if candidate_id in reviews:
            raise ValueError(
                "Duplicate candidate evidence review: "
                f"{candidate_id}"
            )
        reviews[candidate_id] = row
    return reviews


def _selector_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    selector = row.get("selector") or {}
    return (
        _clean(row.get("gene") or selector.get("gene")).upper(),
        _clean(row.get("transcript") or selector.get("transcript")),
        _clean(row.get("c_hgvs") or selector.get("c_hgvs")),
        _clean(row.get("p_hgvs") or selector.get("p_hgvs")),
    )


def _event_narrative_candidates(
    contract: dict[str, Any],
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    source = contract.get("source") or {}
    governance = contract.get("governance") or {}
    defaults = (governance.get("defaults") or {}).get("gene") or {}
    selector_contract = governance.get("runtime_selector_contract") or {}
    required_defaults = {
        "review_status": "needs_review",
        "runtime_eligible": False,
        "report_text_allowed": False,
        "patient_visible": False,
        "secondary_review_status": "pending_report_group_review",
    }
    if source.get("activation_mode") != (
        "candidate_only_pending_secondary_review"
    ):
        raise ValueError(
            "Event narrative candidate activation mode must remain fail-closed"
        )
    for field, expected in required_defaults.items():
        if defaults.get(field) != expected:
            raise ValueError(
                "Event narrative candidate defaults are not fail-closed: "
                f"{field}={defaults.get(field)!r}"
            )
    if (
        selector_contract.get("current_overlay_matches_transcript") is not False
        or selector_contract.get("disposition")
        != "promotion_blocked_until_transcript_is_enforced"
    ):
        raise ValueError(
            "Event narrative candidates must remain blocked while the runtime "
            "overlay selector does not enforce transcript"
        )
    if contract.get("drug_sections"):
        raise ValueError(
            "Event narrative candidates must not contain drug sections"
        )

    candidates: dict[
        tuple[str, str, str, str], dict[str, Any]
    ] = {}
    candidate_ids: set[str] = set()
    for row in contract.get("gene_sections") or []:
        if not isinstance(row, dict):
            continue
        key = _selector_key(row)
        candidate_id = _clean(row.get("candidate_id"))
        if not key[0] or not key[1] or not key[2] or not candidate_id:
            raise ValueError(
                "Event narrative candidate lacks exact event identity"
            )
        if key in candidates or candidate_id in candidate_ids:
            raise ValueError(
                "Duplicate event narrative candidate: "
                f"{candidate_id}:{key!r}"
            )
        for field, expected in required_defaults.items():
            if row.get(field) != expected:
                raise ValueError(
                    "Event narrative candidate row is not fail-closed: "
                    f"{candidate_id}:{field}={row.get(field)!r}"
                )
        if (
            not _clean(row.get("intro"))
            or not _clean(row.get("mutation_analysis"))
            or not row.get("source_refs")
        ):
            raise ValueError(
                f"Event narrative candidate lacks content/source: {candidate_id}"
            )
        if any(
            not isinstance(source_ref, dict)
            or source_ref.get("type") != "ncbi_gene"
            or source_ref.get("authority") != "NCBI"
            or not _clean(source_ref.get("id")).startswith("GeneID:")
            or not _clean(source_ref.get("url")).startswith(
                "https://www.ncbi.nlm.nih.gov/gene/"
            )
            or source_ref.get("supports")
            != "gene_identity_and_function_only"
            for source_ref in row.get("source_refs") or []
        ):
            raise ValueError(
                "Event narrative candidate must use bounded official NCBI "
                f"gene sources: {candidate_id}"
            )
        boundaries = row.get("evidence_boundaries") or {}
        for field in (
            "treatment_inference_allowed",
            "immune_inference_allowed",
            "prognostic_inference_allowed",
            "hereditary_inference_allowed",
        ):
            if boundaries.get(field) is not False:
                raise ValueError(
                    "Event narrative candidate has an unsafe inference "
                    f"boundary: {candidate_id}:{field}"
                )
        candidates[key] = row
        candidate_ids.add(candidate_id)
    return candidates


def _validate_candidate_evidence_contract(
    contract: dict[str, Any],
    candidate_rules: list[dict[str, Any]],
    reviews_by_id: dict[str, dict[str, Any]],
) -> None:
    governance = contract.get("governance") or {}
    required_governance = {
        "secondary_review_status": "pending_report_group_review",
        "runtime_rule_source": False,
        "runtime_eligible": False,
        "report_text_allowed": False,
        "promotion_blocked": True,
    }
    for field, expected in required_governance.items():
        if governance.get(field) != expected:
            raise ValueError(
                "Candidate evidence governance is not fail-closed: "
                f"{field}={governance.get(field)!r}"
            )

    candidate_ids = [_clean(row.get("candidate_id")) for row in candidate_rules]
    if not all(candidate_ids) or len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Medical candidate IDs must be present and unique")
    if set(candidate_ids) != set(reviews_by_id):
        raise ValueError(
            "Candidate evidence review IDs do not match the medical candidate "
            f"queue: candidates={sorted(candidate_ids)!r}, "
            f"reviews={sorted(reviews_by_id)!r}"
        )

    for candidate in candidate_rules:
        candidate_id = _clean(candidate.get("candidate_id"))
        review = reviews_by_id[candidate_id]
        if _selector_key(review) != _selector_key(candidate):
            raise ValueError(
                "Candidate evidence selector mismatch: "
                f"{candidate_id}"
            )
        candidate_therapy = candidate.get("therapy") or {}
        review_therapy = review.get("therapy") or {}
        for field in ("generic_name_zh", "generic_name_en"):
            if _clean(review_therapy.get(field)) != _clean(
                candidate_therapy.get(field)
            ):
                raise ValueError(
                    "Candidate evidence therapy mismatch: "
                    f"{candidate_id}:{field}"
                )
        if (
            review.get("runtime_eligible") is not False
            or review.get("report_text_allowed") is not False
            or (
                (review.get("secondary_review") or {}).get("status")
                != "pending_report_group_review"
            )
        ):
            raise ValueError(
                "Candidate evidence review is not fail-closed: "
                f"{candidate_id}"
            )
        source_reviews = review.get("source_claim_reviews") or []
        if not source_reviews or any(
            not isinstance(source, dict)
            or not _clean(source.get("supports"))
            or not _clean(source.get("does_not_support"))
            for source in source_reviews
        ):
            raise ValueError(
                "Candidate evidence review lacks claim boundaries: "
                f"{candidate_id}"
            )
        direct_outcome = _clean(
            (review.get("scope_assessment") or {}).get(
                "direct_exact_drug_event_clinical_outcome"
            )
        )
        if direct_outcome not in {"identified", "not_identified"}:
            raise ValueError(
                "Candidate evidence review lacks direct-outcome disposition: "
                f"{candidate_id}"
            )


def _reference_rows(identifiers: dict[str, set[str]]) -> list[dict[str, str]]:
    rows = [
        {"type": "pubmed", "id": f"PMID:{value}"}
        for value in sorted(identifiers["pmid"], key=int)
    ]
    rows.extend(
        {"type": "clinical_trial", "id": value}
        for value in sorted(identifiers["trial"])
    )
    return rows


def _content_hash(section: dict[str, Any]) -> str:
    selected = {
        key: _clean(section.get(key))
        for key in ("intro", "mutation_analysis", "fixed_domain_text")
    }
    encoded = json.dumps(
        selected,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unit_id(kind: str, *parts: str) -> str:
    identity = "\0".join(parts).encode("utf-8")
    return f"{kind}:{hashlib.sha256(identity).hexdigest()[:16]}"


def _variant_units(
    package: Any,
    provider: Any,
    candidates_by_event: dict[
        tuple[str, str, str, str], list[dict[str, Any]]
    ],
    non_promotions: set[tuple[str, str, str, str]],
    narrative_candidates_by_event: dict[
        tuple[str, str, str, str], dict[str, Any]
    ],
    runtime_selector_contract: dict[str, Any],
    *,
    reviewed_at: str,
) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for event in _observed_variants(package):
        gene = event["gene"]
        transcript = event["transcript"]
        c_hgvs = event["c_hgvs"]
        p_hgvs = event["p_hgvs"]
        key = (gene, transcript, c_hgvs, p_hgvs)
        kind = _variant_kind(c_hgvs, p_hgvs)
        first_frequency = next(
            (
                float(row["frequency"])
                for row in event["observations"]
                if row["frequency"]
            ),
            0.0,
        )
        section = provider.build_gene_knowledge_section(
            gene=gene,
            c_hgvs=c_hgvs,
            p_hgvs=p_hgvs or "--",
            frequency=first_frequency,
            mutation_type=_provider_mutation_type(kind),
            has_drug=bool(candidates_by_event.get(key)),
        )
        intro = _clean(section.get("intro"))
        analysis = _clean(section.get("mutation_analysis"))
        fixed_domain = _clean(section.get("fixed_domain_text"))
        identifiers = extract_reference_identifiers(
            (intro, analysis, fixed_domain)
        )
        candidate_ids = [
            _clean(row.get("candidate_id"))
            for row in candidates_by_event.get(key, [])
        ]
        narrative_candidate = narrative_candidates_by_event.get(key) or {}
        candidate_narrative_review = (
            {
                "candidate_id": _clean(
                    narrative_candidate.get("candidate_id")
                ),
                "transcript": _clean(
                    narrative_candidate.get("transcript")
                ),
                "c_hgvs": _clean(narrative_candidate.get("c_hgvs")),
                "p_hgvs": _clean(narrative_candidate.get("p_hgvs")),
                "variant_kind": _clean(
                    narrative_candidate.get("variant_kind")
                ),
                "proposed_intro": _clean(narrative_candidate.get("intro")),
                "proposed_mutation_analysis": _clean(
                    narrative_candidate.get("mutation_analysis")
                ),
                "source_refs": narrative_candidate.get("source_refs") or [],
                "evidence_boundaries": (
                    narrative_candidate.get("evidence_boundaries") or {}
                ),
                "review_status": _clean(
                    narrative_candidate.get("review_status")
                ),
                "runtime_eligible": (
                    narrative_candidate.get("runtime_eligible") is True
                ),
                "report_text_allowed": (
                    narrative_candidate.get("report_text_allowed") is True
                ),
                "patient_visible": (
                    narrative_candidate.get("patient_visible") is True
                ),
                "secondary_review_status": _clean(
                    narrative_candidate.get("secondary_review_status")
                ),
                "runtime_selector_contract": runtime_selector_contract,
            }
            if narrative_candidate
            else {}
        )
        if key in non_promotions:
            decision = (
                "retain_detected_variant_and_prohibit_broader_drug_rule_inheritance"
            )
            question = "确认该精确事件仅进入检测结果，不继承同基因其他位点药物规则"
        elif candidate_ids:
            decision = (
                "retain_detected_variant_and_keep_treatment_candidates_hidden"
            )
            question = "逐条审核精确事件药物候选、适应证上下文和正式报告措辞"
        elif not analysis or is_generic_mutation_analysis(gene, analysis):
            decision = (
                "review_candidate_event_interpretation_before_promotion"
                if narrative_candidate
                else "rewrite_event_interpretation_before_promotion"
            )
            question = "补充肺癌边界明确、来源可追溯的事件/基因解释"
        else:
            decision = "source_scope_review_required_before_promotion"
            question = "核对现有解释是否支持该肺癌精确事件，禁止从基因级证据外推用药"
        units.append(
            {
                "review_unit_id": _unit_id(
                    "variant",
                    gene,
                    transcript,
                    c_hgvs,
                    p_hgvs,
                ),
                "unit_type": "variant_narrative",
                "priority": "P0",
                "gene": gene,
                "transcript": transcript,
                "chromosome": event["chromosome"],
                "exon": event["exon"],
                "c_hgvs": c_hgvs,
                "p_hgvs": p_hgvs,
                "variant_kind": kind,
                "case_observations": event["observations"],
                "input_gene_classes": sorted(
                    {
                        row["gene_class"]
                        for row in event["observations"]
                        if row["gene_class"]
                    }
                ),
                "candidate_ids": candidate_ids,
                "explicit_non_promotion": key in non_promotions,
                "current_content_status": (
                    "missing"
                    if not analysis
                    else (
                        "generic_fallback"
                        if is_generic_mutation_analysis(gene, analysis)
                        else "specific_but_not_lung_event_approved"
                    )
                ),
                "current_intro": intro,
                "current_mutation_analysis": analysis,
                "current_fixed_domain_text": fixed_domain,
                "current_content_sha256": _content_hash(section),
                "current_source_refs": _reference_rows(identifiers),
                "candidate_narrative_review": candidate_narrative_review,
                "patient_visible_part2_result_allowed": True,
                "patient_visible_part3_interpretation_allowed": False,
                "patient_visible_drug_conclusion_allowed": False,
                "runtime_eligible": False,
                "primary_review": {
                    "status": "completed_ai_assisted_triage",
                    "decision": decision,
                    "reviewer": "codex",
                    "reviewer_type": "ai_assisted_first_review",
                    "reviewed_at": reviewed_at,
                },
                "secondary_review": {
                    "status": "pending_report_group_review",
                    "decision": "",
                    "reviewer": "",
                    "reviewed_at": "",
                },
                "medical_review_question": question,
            }
        )
    return units


def _candidate_units(
    candidate_rules: list[dict[str, Any]],
    evidence_reviews_by_id: dict[str, dict[str, Any]],
    *,
    reviewed_at: str,
) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for row in candidate_rules:
        candidate_id = _clean(row.get("candidate_id"))
        selector = row.get("selector") or {}
        therapy = row.get("therapy") or {}
        source_scope_review = evidence_reviews_by_id.get(candidate_id) or {}
        scoped_primary_review = source_scope_review.get("primary_review") or {}
        units.append(
            {
                "review_unit_id": candidate_id,
                "unit_type": "targeted_drug_candidate",
                "priority": "P0",
                "gene": _clean(row.get("gene")).upper(),
                "transcript": _clean(selector.get("transcript")),
                "c_hgvs": _clean(selector.get("c_hgvs")),
                "p_hgvs": _clean(selector.get("p_hgvs")),
                "therapy": _clean(therapy.get("generic_name_zh")),
                "direction": _clean(row.get("direction")),
                "clinical_scope": row.get("clinical_scope") or {},
                "required_context_fields": row.get(
                    "required_context_fields"
                )
                or [],
                "context_requirements": row.get("context_requirements") or {},
                "evidence_class": _clean(row.get("evidence_class")),
                "evidence_summary": _clean(row.get("evidence_summary")),
                "source_refs": row.get("source_refs") or [],
                "source_scope_review": source_scope_review,
                "patient_visible_part2_result_allowed": False,
                "patient_visible_part3_interpretation_allowed": False,
                "patient_visible_drug_conclusion_allowed": False,
                "runtime_eligible": False,
                "primary_review": {
                    "status": "completed_ai_assisted_triage",
                    "decision": (
                        _clean(scoped_primary_review.get("decision"))
                        or "source_scope_review_missing"
                    ),
                    "reviewer": "codex",
                    "reviewer_type": "ai_assisted_first_review",
                    "reviewed_at": reviewed_at,
                },
                "secondary_review": {
                    "status": "pending_report_group_review",
                    "decision": "",
                    "reviewer": "",
                    "reviewed_at": "",
                },
                "medical_review_question": (
                    "确认精确位点、肺癌亚型、疾病范围、既往治疗、伴随诊断、"
                    "药物方向和当前标签后决定是否晋级"
                ),
            }
        )
    return units


def _citation_units(
    package: Any,
    *,
    reviewed_at: str,
) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for finding in load_panel_citation_source_reviews(package):
        units.append(
            {
                "review_unit_id": finding["review_id"],
                "unit_type": "citation_source_mismatch",
                "priority": "P0",
                "gene": finding["gene"],
                "identifier": finding["identifier"],
                "claim_contains": finding["claim_contains"],
                "disposition": finding["disposition"],
                "suggested_replacement_identifier": finding[
                    "suggested_replacement_identifier"
                ],
                "runtime_claim_retracted": finding[
                    "runtime_claim_retracted"
                ],
                "runtime_retraction_ids": finding[
                    "runtime_retraction_ids"
                ],
                "patient_visible_part2_result_allowed": False,
                "patient_visible_part3_interpretation_allowed": False,
                "patient_visible_drug_conclusion_allowed": False,
                "runtime_eligible": False,
                "primary_review": {
                    "status": "completed_ai_assisted_triage",
                    "decision": (
                        "reject_current_source_for_claim_and_request_replacement_review"
                    ),
                    "reviewer": "codex",
                    "reviewer_type": "ai_assisted_first_review",
                    "reviewed_at": reviewed_at,
                },
                "secondary_review": {
                    "status": "pending_report_group_review",
                    "decision": "",
                    "reviewer": "",
                    "reviewed_at": "",
                },
                "medical_review_question": (
                    "确认删除旧错引，并复核建议替代来源及收窄后的正式措辞"
                ),
            }
        )
    return units


def build_packet(root: Path, reviewed_at: str) -> dict[str, Any]:
    package = PanelPackageLoader(project_root=root).load(PANEL_ID)
    medical = _medical_rules(package)
    narrative_contracts = _event_narrative_candidate_contracts(package)
    narrative_candidates_by_event: dict[
        tuple[str, str, str, str], dict[str, Any]
    ] = {}
    runtime_selector_contract: dict[str, Any] = {}
    for narrative_contract in narrative_contracts:
        contract_candidates = _event_narrative_candidates(
            narrative_contract
        )
        duplicate_events = (
            set(narrative_candidates_by_event) & set(contract_candidates)
        )
        if duplicate_events:
            raise ValueError(
                "Event narrative candidate appears in multiple contracts: "
                f"{sorted(duplicate_events)!r}"
            )
        narrative_candidates_by_event.update(contract_candidates)
        current_selector_contract = (
            (narrative_contract.get("governance") or {}).get(
                "runtime_selector_contract"
            )
            or {}
        )
        if (
            runtime_selector_contract
            and current_selector_contract != runtime_selector_contract
        ):
            raise ValueError(
                "Event narrative candidate contracts disagree on the "
                "runtime selector boundary"
            )
        runtime_selector_contract = current_selector_contract
    observed_event_keys = {
        (
            row["gene"],
            row["transcript"],
            row["c_hgvs"],
            row["p_hgvs"],
        )
        for row in _observed_variants(package)
    }
    if set(narrative_candidates_by_event) - observed_event_keys:
        raise ValueError(
            "Event narrative candidate is not present in the de-identified "
            "P0 context contracts"
        )
    evidence_contract = _candidate_evidence_review_contract(package)
    evidence_reviews_by_id = _candidate_evidence_reviews(evidence_contract)
    candidate_rules = [
        row
        for row in medical.get("candidate_rules") or []
        if isinstance(row, dict)
    ]
    _validate_candidate_evidence_contract(
        evidence_contract,
        candidate_rules,
        evidence_reviews_by_id,
    )
    candidates_by_event: dict[
        tuple[str, str, str, str], list[dict[str, Any]]
    ] = defaultdict(list)
    for row in candidate_rules:
        candidates_by_event[_selector_key(row)].append(row)
    non_promotions = {
        _selector_key(row)
        for row in medical.get("explicit_non_promotions") or []
        if isinstance(row, dict) and row.get("selector")
    }
    provider = build_panel_gene_provider(root, package)
    units = _variant_units(
        package,
        provider,
        candidates_by_event,
        non_promotions,
        narrative_candidates_by_event,
        runtime_selector_contract,
        reviewed_at=reviewed_at,
    )
    units.extend(
        _candidate_units(
            candidate_rules,
            evidence_reviews_by_id,
            reviewed_at=reviewed_at,
        )
    )
    units.extend(_citation_units(package, reviewed_at=reviewed_at))
    order = {
        "citation_source_mismatch": 0,
        "targeted_drug_candidate": 1,
        "variant_narrative": 2,
    }
    units.sort(
        key=lambda row: (
            order.get(row["unit_type"], 99),
            _clean(row.get("gene")),
            _clean(row.get("c_hgvs")),
            _clean(row.get("p_hgvs")),
            row["review_unit_id"],
        )
    )
    unit_counts = Counter(row["unit_type"] for row in units)
    decision_counts = Counter(
        row["primary_review"]["decision"] for row in units
    )
    case_aliases = sorted(
        {
            observation["case_alias"]
            for row in units
            for observation in row.get("case_observations") or []
        }
    )
    narrative_candidate_units = [
        row
        for row in units
        if row.get("candidate_narrative_review")
    ]
    return {
        "schema_version": "1.0",
        "packet_id": "lung588_p0_event_first_review_20260723",
        "panel_id": PANEL_ID,
        "git_head": _git_head(root),
        "reviewed_at": reviewed_at,
        "status": "primary_review_complete_secondary_review_pending",
        "privacy": {
            "contains_phi": False,
            "case_identity": "CASE aliases and exact structured events only",
        },
        "scope": {
            "case_aliases": case_aliases,
            "historical_reports_are_current_medical_truth": False,
            "runtime_activation_in_scope": False,
            "event_narrative_candidates_are_runtime_content": False,
        },
        "summary": {
            "review_unit_count": len(units),
            "unit_type_counts": dict(sorted(unit_counts.items())),
            "primary_decision_counts": dict(sorted(decision_counts.items())),
            "secondary_review_completed_count": 0,
            "patient_visible_part3_allowed_count": sum(
                row["patient_visible_part3_interpretation_allowed"]
                for row in units
            ),
            "patient_visible_drug_allowed_count": sum(
                row["patient_visible_drug_conclusion_allowed"]
                for row in units
            ),
            "event_narrative_candidate_count": len(
                narrative_candidate_units
            ),
            "event_narrative_candidate_gene_count": len(
                {
                    row["gene"]
                    for row in narrative_candidate_units
                }
            ),
            "event_narrative_candidate_runtime_eligible_count": sum(
                row["candidate_narrative_review"]["runtime_eligible"]
                for row in narrative_candidate_units
            ),
        },
        "promotion_requirements": [
            "report_group_event_level_secondary_review",
            "source_supports_exact_claim",
            "lung_cancer_and_variant_scope_confirmed",
            "positive_and_negative_rule_tests",
            "case_level_uat",
        ],
        "units": units,
    }


def write_outputs(
    packet: dict[str, Any],
    json_path: Path,
    tsv_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    fields = [
        "review_unit_id",
        "unit_type",
        "priority",
        "gene",
        "transcript",
        "chromosome",
        "exon",
        "c_hgvs",
        "p_hgvs",
        "variant_kind",
        "therapy",
        "case_observations",
        "input_gene_classes",
        "candidate_ids",
        "explicit_non_promotion",
        "current_content_status",
        "current_source_refs",
        "candidate_narrative_review",
        "source_refs",
        "source_scope_review",
        "identifier",
        "suggested_replacement_identifier",
        "primary_review",
        "secondary_review",
        "medical_review_question",
        "runtime_eligible",
    ]
    with tsv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in packet["units"]:
            writer.writerow(
                {
                    field: (
                        json.dumps(
                            row.get(field),
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        if isinstance(row.get(field), (dict, list))
                        else row.get(field, "")
                    )
                    for field in fields
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--reviewed-at", default=date.today().isoformat())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".work/lung588_p0_event_review"),
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    output_dir = (
        args.output_dir
        if args.output_dir.is_absolute()
        else root / args.output_dir
    )
    packet = build_packet(root, args.reviewed_at)
    json_path = output_dir / "p0_event_review.json"
    tsv_path = output_dir / "p0_event_review.tsv"
    write_outputs(packet, json_path, tsv_path)
    print(
        json.dumps(
            {
                "status": packet["status"],
                **packet["summary"],
                "json": str(json_path),
                "tsv": str(tsv_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
