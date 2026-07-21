"""Regression contracts for structured knowledge governance and release gates."""

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
from reportgen.knowledge.release_gate import run_knowledge_release_gate  # noqa: E402


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
    contract_inventory = {
        panel["panel_id"]: panel["drug_analysis_contracts"]
        for panel in result["panels"]
    }
    assert contract_inventory["crc_301_msi"] == {
        "status": "PASS",
        "rules_checked": 9,
        "selector_cases_checked": 10,
        "expected_item_count": 83,
        "rendered_item_count": 83,
        "issues": [],
    }
    assert contract_inventory["crc_358_msi"] == {
        "status": "PASS",
        "rules_checked": 17,
        "selector_cases_checked": 18,
        "expected_item_count": 178,
        "rendered_item_count": 178,
        "issues": [],
    }
    assert {row["panel_id"] for row in result["non_blocking_panel_readiness"]} == {
        "endometrial_29",
        "lung_329_pdl1",
        "lung_methylation",
    }


def test_effective_governance_keeps_legacy_and_provisional_states_distinct():
    overlay = yaml.safe_load(
        (
            ROOT
            / "panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml"
        ).read_text(encoding="utf-8")
    )
    tp53 = next(row for row in overlay["gene_sections"] if row["gene"] == "TP53")
    chd2 = next(row for row in overlay["gene_sections"] if row["gene"] == "CHD2")

    legacy = effective_governance(overlay, tp53, "gene")
    provisional = effective_governance(overlay, chd2, "gene")

    assert legacy["status"] == "legacy_runtime"
    assert legacy["runtime_eligible"] is True
    assert legacy["source_refs"]
    assert provisional["status"] == "provisional_runtime"
    assert provisional["runtime_eligible"] is True
    assert provisional["reviewer"] == "codex"
    assert provisional["secondary_review_status"] == "pending_report_group_review"


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
