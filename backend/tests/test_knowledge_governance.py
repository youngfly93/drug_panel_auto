"""Regression contracts for structured knowledge governance and release gates."""

import hashlib
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.knowledge.gene_knowledge import GeneKnowledgeProvider  # noqa: E402
from reportgen.knowledge.governance import (  # noqa: E402
    effective_governance,
    validate_knowledge_rows,
)
from reportgen.knowledge.release_gate import (  # noqa: E402
    _secondary_review_receipt,
    _validate_drug_rules,
    run_knowledge_release_gate,
)


def test_production_knowledge_release_gate_is_self_contained_and_passes(tmp_path):
    result = run_knowledge_release_gate(
        ROOT,
        output_path=tmp_path / "knowledge_release_gate.json",
    )

    assert result["status"] == "PASS"
    assert result["summary"] == {
        "panels_checked": 2,
        "panels_passed": 2,
        "issues": 0,
    }
    assert result["base_manifest"]["status"] == "PASS"
    assert all(
        artifact["sha256_matches"]
        for artifact in result["base_manifest"]["artifacts"]
    )
    for panel in result["panels"]:
        coverage = panel["multidimensional_coverage"]
        assert coverage["gene_explanation"]["percent"] == 100.0
        assert coverage["review_governance"]["standardized_percent"] == 100.0
        assert coverage["source_provenance"]["structured_source_percent"] == 100.0
        runtime_quality = panel["runtime_content_quality"]
        assert runtime_quality["complete_percent"] == 100.0
        assert runtime_quality["missing_intro_genes"] == []
        assert runtime_quality["missing_analysis_genes"] == []
        assert runtime_quality["missing_fixed_domain_genes"] == []
        assert runtime_quality["duplicate_fixed_domain_genes"] == []
        assert runtime_quality["citation_integrity"]["unresolved_pmids"] == []
        assert panel["clinical_release_readiness"]["status"] == "BLOCKED"
        secondary = panel["clinical_release_readiness"]["secondary_review"]
        assert secondary["status"] == "completed"
        # The prior report-group receipt remains immutable and therefore must
        # fail once this candidate changes its reviewed artifacts. CRC301 has
        # no new scoped rows; CRC358 has 14 Part-2 rules plus 9 research-only
        # Part-3 rows pending a new secondary review.
        assert secondary["receipt"]["status"] == "FAIL"
        if panel["panel_id"] == "crc_301_msi":
            assert secondary["pending_runtime_rows"] == 0
            assert coverage["review_governance"][
                "secondary_review_complete_percent"
            ] == 100.0
            assert panel["clinical_release_readiness"]["blocking_reasons"] == [
                "secondary_review_receipt_invalid",
                "insufficient_uat_reports",
                "uat_pass_rate_below_threshold_or_unknown",
            ]
        else:
            assert secondary["pending_runtime_rows"] == 23
            assert coverage["review_governance"][
                "secondary_review_complete_percent"
            ] == 99.11
            assert panel["clinical_release_readiness"]["blocking_reasons"] == [
                "secondary_review_receipt_invalid",
                "pending_report_group_secondary_review",
                "insufficient_uat_reports",
                "uat_pass_rate_below_threshold_or_unknown",
            ]
    contract_inventory = {
        panel["panel_id"]: panel["drug_analysis_contracts"]
        for panel in result["panels"]
    }
    assert contract_inventory["crc_301_msi"] == {
        "status": "PASS",
        "rules_checked": 9,
        "selector_cases_checked": 10,
        "expected_item_count": 35,
        "rendered_item_count": 35,
        "issues": [],
    }
    assert contract_inventory["crc_358_msi"] == {
        "status": "PASS",
        "rules_checked": 31,
        "selector_cases_checked": 32,
        "expected_item_count": 108,
        "rendered_item_count": 108,
        "issues": [],
    }
    assert {row["panel_id"] for row in result["non_blocking_panel_readiness"]} == {
        "endometrial_29",
        "lung_329_pdl1",
        "lung_methylation",
    }


def test_effective_governance_keeps_legacy_and_approved_states_distinct():
    overlay = yaml.safe_load(
        (
            ROOT
            / "panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml"
        ).read_text(encoding="utf-8")
    )
    tp53 = next(row for row in overlay["gene_sections"] if row["gene"] == "TP53")
    chd2 = next(row for row in overlay["gene_sections"] if row["gene"] == "CHD2")

    legacy = effective_governance(overlay, tp53, "gene")
    approved = effective_governance(overlay, chd2, "gene")

    assert legacy["status"] == "legacy_runtime"
    assert legacy["runtime_eligible"] is True
    assert legacy["source_refs"]
    assert approved["status"] == "approved_for_runtime"
    assert approved["runtime_eligible"] is True
    assert approved["reviewer"] == "codex"
    assert approved["secondary_review_status"] == "report_group_approved"


def test_secondary_review_receipt_fails_closed_when_reviewed_content_changes(
    tmp_path,
):
    artifact = tmp_path / "reviewed.yaml"
    artifact.write_text("gene: DEMO\nintro: approved\n", encoding="utf-8")
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    bundle = hashlib.sha256(
        f"reviewed.yaml\0{artifact_sha}\n".encode("utf-8")
    ).hexdigest()
    receipt = tmp_path / "receipt.yaml"
    receipt.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "receipt_id": "receipt-1",
                "status": "approved",
                "decision": "approved_for_runtime",
                "reviewed_at": "2026-07-22",
                "reviewer": {"group": "report_group"},
                "candidate_identity": {
                    "kind": "content_bundle_sha256",
                    "value": bundle,
                },
                "scope": {"panels": ["demo_panel"]},
                "artifacts": [
                    {"path": "reviewed.yaml", "sha256": artifact_sha}
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    registry = {
        "panels": {
            "demo_panel": {
                "secondary_review_receipt": "receipt.yaml",
                "secondary_review_receipt_id": "receipt-1",
            }
        }
    }

    approved = _secondary_review_receipt(tmp_path, registry, "demo_panel")
    assert approved["status"] == "PASS"
    assert approved["expected_bundle_sha256"] == bundle

    artifact.write_text("gene: DEMO\nintro: changed after review\n", encoding="utf-8")
    stale = _secondary_review_receipt(tmp_path, registry, "demo_panel")
    assert stale["status"] == "FAIL"
    assert {
        issue["code"] for issue in stale["issues"]
    } >= {
        "SECONDARY_REVIEW_ARTIFACT_MISMATCH",
        "SECONDARY_REVIEW_BUNDLE_MISMATCH",
    }


def test_release_validation_rejects_unrecorded_or_unsourced_runtime_rows():
    data = {"governance": {"schema_version": "1.0", "defaults": {}}}
    result = validate_knowledge_rows(
        data,
        [{"gene": "DEMO", "intro": "demo"}],
        panel_id="demo_panel",
        kind="gene",
    )

    codes = {issue["code"] for issue in result["issues"]}
    assert result["status"] == "FAIL"
    assert "INVALID_REVIEW_STATUS" in codes
    assert "MISSING_STRUCTURED_SOURCE" in codes


def test_drug_suppression_requires_scope_and_superseded_record():
    data = {
        "governance": {
            "schema_version": "1.0",
            "defaults": {
                "drug": {
                    "review_status": "provisional_runtime",
                    "runtime_eligible": True,
                    "review_basis": "medical_correction",
                    "evidence_level": "reviewed",
                    "evidence_as_of": "2026-07-22",
                    "cancer_scope": "test_scope",
                    "secondary_review_status": "pending_report_group_review",
                    "review_metadata": {
                        "reviewer": "test-reviewer",
                        "reviewer_type": "unit_test",
                        "reviewed_at": "2026-07-22",
                        "risk_level": "high",
                        "secondary_review_status": "pending_report_group_review",
                    },
                    "source_refs": [{"type": "test", "id": "source-1"}],
                }
            },
        }
    }
    invalid = validate_knowledge_rows(
        data,
        [{"gene": "DEMO", "type": "benefit", "suppress": True}],
        panel_id="demo_panel",
        kind="drug",
    )
    codes = {issue["code"] for issue in invalid["issues"]}
    assert {"INCOMPLETE_DRUG_SUPPRESSION", "UNSCOPED_DRUG_SUPPRESSION"} <= codes

    valid = validate_knowledge_rows(
        data,
        [
            {
                "gene": "DEMO",
                "p_hgvs": "p.Q1*",
                "type": "benefit",
                "suppress": True,
                "supersedes": "historical:DEMO_p.Q1*_benefit",
            }
        ],
        panel_id="demo_panel",
        kind="drug",
    )
    assert valid["status"] == "PASS", valid["issues"]


def test_release_gate_rejects_gene_level_targeted_drug_override(tmp_path):
    rules_path = tmp_path / "drugs.yaml"
    rules_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "version": "1.0.0",
                "updated": "2026-07-22",
                "governance": {
                    "schema_version": "1.0",
                    "defaults": {
                        "targeted_drug": {
                            "review_status": "provisional_runtime",
                            "runtime_eligible": True,
                            "review_basis": "test",
                            "evidence_level": "test",
                            "evidence_as_of": "2026-07-22",
                            "cancer_scope": "test",
                            "secondary_review_status": "pending_report_group_review",
                            "source_refs": [{"type": "test", "id": "source-1"}],
                        }
                    },
                },
                "targeted_drug_rules": {
                    "overrides": {
                        "ATM": {
                            "benefit_drugs": ["示例药物（D）"],
                            "caution_drugs": ["--"],
                        }
                    }
                },
                "approved_drug_rows": [],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    class Package:
        panel_id = "demo_panel"

        @staticmethod
        def resolve_rule_file(_name):
            return rules_path

    result = _validate_drug_rules(Package())
    assert result["status"] == "FAIL"
    assert "UNSCOPED_GENE_LEVEL_TARGETED_DRUG_OVERRIDE" in {
        issue["code"] for issue in result["issues"]
    }


def test_provider_honors_file_level_runtime_governance(tmp_path):
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        yaml.safe_dump(
            {
                "governance": {
                    "schema_version": "1.0",
                    "defaults": {
                        "gene": {
                            "review_status": "needs_review",
                            "runtime_eligible": False,
                            "source_refs": [
                                {"type": "test", "id": "blocked-source"}
                            ],
                        }
                    },
                },
                "gene_sections": [
                    {
                        "gene": "BLOCKED",
                        "intro": "blocked intro",
                        "mutation_analysis": "blocked analysis",
                    },
                    {
                        "gene": "PROVISIONAL",
                        "intro": "provisional intro",
                        "mutation_analysis": "provisional analysis",
                        "review_status": "provisional_runtime",
                        "runtime_eligible": True,
                    },
                ],
                "drug_sections": [],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    provider = GeneKnowledgeProvider(
        {
            "enabled": True,
            "gene_knowledge_db": {
                "enabled": True,
                "path": "missing.xlsx",
                "reviewed_part3_overlay_path": str(overlay),
            },
        }
    )
    provider.load(base_path=str(tmp_path))

    blocked = provider.build_gene_knowledge_section(
        gene="BLOCKED", c_hgvs="c.1A>T", p_hgvs="p.X1Y", frequency=1.0
    )
    provisional = provider.build_gene_knowledge_section(
        gene="PROVISIONAL", c_hgvs="c.1A>T", p_hgvs="p.X1Y", frequency=1.0
    )
    assert blocked["intro"] != "blocked intro"
    assert blocked["mutation_analysis"] != "blocked analysis"
    assert provisional["intro"] == "provisional intro"
