# ruff: noqa: E402, I001
"""Behavior contract for the read-only Panel Knowledge Catalog service."""

import json
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.services import knowledge_service as service  # noqa: E402


CRC_PANELS = ("crc_358_msi", "crc_301_msi")


@pytest.fixture(scope="module", autouse=True)
def _fresh_knowledge_cache():
    service.reload_all()
    yield
    service.reload_all()


def _walk_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _entry_ids(payload: dict[str, Any]) -> list[str]:
    return [str(row["entry_id"]) for row in payload["rows"]]


def test_crc_panel_summaries_declare_overlay_origin_and_sharing():
    payload = service.get_catalog_panels()
    panels = payload["panels"]
    by_id = {row["panel_id"]: row for row in panels}

    assert [row["panel_id"] for row in panels] == sorted(by_id)
    assert payload["total"] == len(panels)

    crc358 = by_id["crc_358_msi"]
    assert crc358 == {
        "panel_id": "crc_358_msi",
        "display_name": "结直肠癌358基因+MSI",
        "status": "active",
        "overlay_available": True,
        "overlay_origin_panel_id": "crc_358_msi",
        "shared_overlay": False,
        "review_status": "provisional_runtime",
        "warning": None,
    }

    crc301 = by_id["crc_301_msi"]
    assert crc301 == {
        "panel_id": "crc_301_msi",
        "display_name": "结直肠癌301基因+MSI",
        "status": "active",
        "overlay_available": True,
        "overlay_origin_panel_id": "crc_358_msi",
        "shared_overlay": True,
        "review_status": "provisional_runtime",
        "warning": None,
    }

    crc358_entry = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="gene",
        layer="reviewed_overlay",
        gene="KRAS",
        search="c.34G>A",
        page_size=1,
    )["rows"][0]
    crc301_entry = service.get_catalog_entries(
        panel_id="crc_301_msi",
        kind="gene",
        layer="reviewed_overlay",
        gene="KRAS",
        search="c.34G>A",
        page_size=1,
    )["rows"][0]

    assert crc358_entry["entry_id"] == crc301_entry["entry_id"]
    assert crc358_entry["provenance"]["origin_panel_id"] == "crc_358_msi"
    assert crc358_entry["provenance"]["shared_overlay"] is False
    assert crc301_entry["provenance"]["origin_panel_id"] == "crc_358_msi"
    assert crc301_entry["provenance"]["shared_overlay"] is True


@pytest.mark.parametrize("panel_id", CRC_PANELS)
def test_crc_coverage_reports_exact_base_and_reviewed_layer_counts(panel_id: str):
    payload = service.get_catalog_coverage(panel_id)

    assert payload["panel"]["panel_id"] == panel_id
    assert payload["base"] == {
        "gene_source_rows": 378,
        "gene_entries": 377,
        "unique_genes": 377,
        "drug_rows": 81,
        "drug_unique_genes": 26,
        "targeted_drug_rows": 811,
        "targeted_drug_unique_genes": 151,
    }
    overlay_expected = {
        "available": True,
        "gene_rows": 315,
        "unique_genes": 235,
        "gene_level_rows": 233,
        "variant_level_rows": 82,
        "drug_rows": 40,
        "drug_unique_genes": 16,
        "targeted_drug_rule_rows": 17,
        "targeted_drug_rule_unique_genes": 15,
        "targeted_drug_applicability_rule_rows": 1,
        "extra_reference_rows": 12,
        "review_status_counts": {
            "legacy_runtime": 338,
            "provisional_runtime": 17,
        },
    }
    if panel_id == "crc_301_msi":
        overlay_expected.update(
            gene_rows=340,
            unique_genes=271,
            gene_level_rows=269,
            variant_level_rows=71,
            drug_rows=18,
            drug_unique_genes=8,
            targeted_drug_rule_rows=9,
            targeted_drug_rule_unique_genes=9,
            review_status_counts={
                "legacy_runtime": 309,
                "provisional_runtime": 49,
            },
        )
    assert payload["reviewed_overlay"] == overlay_expected
    assert payload["overlap"] == {
        "genes_in_both": 215,
        "overlay_only_genes": 56 if panel_id == "crc_301_msi" else 20,
    }
    expected = {
        "crc_358_msi": (358, 350, 218, 358, 100.0),
        "crc_301_msi": (301, 256, 230, 301, 100.0),
    }[panel_id]
    total, base_covered, overlay_covered, either_covered, percent = expected
    assert payload["declared_gene_coverage"] == {
        "denominator_name": "reportable_genes",
        "total": total,
        "base_covered": base_covered,
        "overlay_covered": overlay_covered,
        "either_covered": either_covered,
        "percent": percent,
        "label": "reportable_genes 覆盖率",
    }
    contract = payload["knowledge_coverage_contract"]
    assert contract["total_genes"] == total
    disposition = contract["drug_candidate_disposition"]
    assert disposition["pending_medical_review_rows"] == 0
    assert disposition["database_candidate_genes"] in {115, 116}
    assert contract["gene_explanation_complete"] is True
    assert contract["gene_explanation_missing_count"] == 0
    assert contract["explicit_panel_rule_genes"] == (
        15 if panel_id == "crc_358_msi" else 9
    )
    assert contract["explicitly_approved_drug_genes"] == 0
    assert contract["panel_rule_status_counts"] == {
        "legacy_runtime": 12 if panel_id == "crc_358_msi" else 8,
        "provisional_runtime": 5 if panel_id == "crc_358_msi" else 1,
    }
    runtime_quality = contract["runtime_content_quality"]
    assert runtime_quality["complete_percent"] == 100.0
    assert runtime_quality["missing_intro_genes"] == []
    assert runtime_quality["missing_analysis_genes"] == []
    assert runtime_quality["citation_integrity"]["unresolved_pmids"] == []
    assert contract["clinical_release_readiness"]["status"] == "BLOCKED"
    assert "generic_gene_fallback_requires_content_review" in contract[
        "clinical_release_readiness"
    ]["blocking_reasons"]
    multidimensional = contract["multidimensional_coverage"]
    assert multidimensional["gene_explanation"]["percent"] == 100.0
    assert multidimensional["review_governance"]["standardized_percent"] == 100.0
    assert multidimensional["source_provenance"]["structured_source_percent"] == 100.0
    assert multidimensional["source_provenance"]["evidence_level_percent"] == 100.0
    assert payload["warnings"] == []


def test_non_crc_pilot_does_not_inherit_crc_coverage_denominator():
    payload = service.get_catalog_coverage("lung_329_pdl1")

    assert payload["declared_gene_coverage"] == {
        "denominator_name": "",
        "total": 0,
        "base_covered": 0,
        "overlay_covered": 0,
        "either_covered": 0,
        "percent": None,
        "label": "未声明覆盖分母",
    }
    assert payload["knowledge_coverage_contract"]["total_genes"] == 0


def test_crc301_specific_overlay_closes_gene_gap_without_leaking_to_crc358():
    crc301 = service.get_catalog_entries(
        panel_id="crc_301_msi",
        kind="gene",
        layer="reviewed_overlay",
        gene="ABCB1",
        page=1,
        page_size=10,
    )
    crc358 = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="gene",
        layer="reviewed_overlay",
        gene="ABCB1",
        page=1,
        page_size=10,
    )

    assert crc301["total"] == 1
    assert crc301["rows"][0]["provenance"]["origin_panel_id"] == "crc_301_msi"
    assert crc301["rows"][0]["provenance"]["shared_overlay"] is False
    assert crc301["rows"][0]["provenance"]["source_type"] == "ncbi_refseq_curated_paraphrase"
    assert crc358["total"] == 0


def test_drug_candidate_disposition_is_complete_and_not_a_migration_backlog():
    contract = service.get_catalog_coverage("crc_358_msi")[
        "knowledge_coverage_contract"
    ]
    disposition = contract["drug_candidate_disposition"]

    assert disposition["database_candidate_genes"] == 116
    assert disposition["runtime_eligible_database_genes"] == 26
    assert disposition["database_only_filtered_genes"] == 90
    assert disposition["pending_medical_review_rows"] == 0
    assert disposition["historical_review"]["approved_rows"] == 95
    assert disposition["historical_review"]["rejected_rows"] == 6
    assert disposition["filter_reason_row_counts"]["filtered_missing_position"] > 0


def test_catalog_entry_counts_and_match_scopes_are_explicit():
    genes = service.get_catalog_entries(
        panel_id="crc_358_msi", kind="gene", page=1, page_size=1
    )
    assert genes["total"] == 692
    assert genes["facets"] == {
        "layers": {"reviewed_overlay": 315, "base": 377},
        "review_statuses": {
            "legacy_runtime": 680,
            "provisional_runtime": 12,
        },
        "match_scopes": {"gene": 610, "variant": 82},
    }

    drugs = service.get_catalog_entries(
        panel_id="crc_358_msi", kind="drug", page=1, page_size=1
    )
    assert drugs["total"] == 121
    assert drugs["facets"] == {
        "layers": {"base": 81, "reviewed_overlay": 40},
        "review_statuses": {
            "legacy_runtime": 116,
            "provisional_runtime": 5,
        },
        "match_scopes": {"gene": 48, "variant": 71, "event": 2},
    }

    targeted = service.get_catalog_entries(
        panel_id="crc_358_msi", kind="targeted_drug", page=1, page_size=1
    )
    assert targeted["total"] == 828
    assert targeted["facets"] == {
        "layers": {"base": 811, "reviewed_overlay": 17},
        "review_statuses": {
            "legacy_runtime": 823,
            "provisional_runtime": 5,
        },
        "match_scopes": {"event": 612, "variant": 155, "gene": 61},
    }

    variant_rows = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="gene",
        layer="reviewed_overlay",
        match_scope="variant",
        page=1,
        page_size=100,
    )
    assert variant_rows["total"] == 82
    assert len(variant_rows["rows"]) == 82
    assert all(row["match_scope"] == "variant" for row in variant_rows["rows"])


def test_base_catalog_shows_runtime_normalized_content_not_raw_instruction_cells():
    smad4 = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="gene",
        layer="base",
        gene="SMAD4",
        page=1,
        page_size=10,
    )["rows"][0]
    kmt2c = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="gene",
        layer="base",
        gene="KMT2C",
        page=1,
        page_size=10,
    )["rows"][0]

    assert smad4["content"]["content_profile"] == "此前未见位点的基础回退预览"
    assert "3056个氨基酸" not in smad4["content"]["intro"]
    assert "552个氨基酸" in smad4["content"]["mutation_analysis"]
    assert "239919。" not in kmt2c["content"]["mutation_analysis"]
    assert "4911个氨基酸" in kmt2c["content"]["mutation_analysis"]


def test_catalog_search_treats_regex_metacharacters_as_literal_text():
    for literal in ("[", "\\"):
        payload = service.get_catalog_entries(
            panel_id="crc_358_msi",
            kind="gene",
            search=literal,
            page=1,
            page_size=3,
        )
        assert isinstance(payload["total"], int)

    for regex_like in (".*", "(ATM)+"):
        payload = service.get_catalog_entries(
            panel_id="crc_358_msi",
            kind="gene",
            search=regex_like,
            page=1,
            page_size=3,
        )
        assert payload["total"] == 0
        assert payload["rows"] == []

    literal_hgvs = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="gene",
        layer="reviewed_overlay",
        search="c.34G>A",
        page=1,
        page_size=10,
    )
    assert literal_hgvs["total"] == 1
    assert literal_hgvs["rows"][0]["gene"] == "KRAS"
    assert literal_hgvs["rows"][0]["match_scope"] == "variant"


def test_catalog_pagination_is_stable_and_out_of_range_pages_are_empty():
    query = {
        "panel_id": "crc_358_msi",
        "kind": "gene",
        "layer": "base",
        "page_size": 17,
    }
    first = service.get_catalog_entries(**query, page=1)
    repeated_first = service.get_catalog_entries(**query, page=1)
    second = service.get_catalog_entries(**query, page=2)
    beyond = service.get_catalog_entries(**query, page=10_000)

    assert first["total"] == repeated_first["total"] == second["total"] == 377
    assert _entry_ids(first) == _entry_ids(repeated_first)
    assert set(_entry_ids(first)).isdisjoint(_entry_ids(second))
    assert len(first["rows"]) == len(second["rows"]) == 17
    assert beyond["rows"] == []
    assert beyond["total"] == 377
    assert beyond["page"] == 10_000
    assert beyond["facets"]["layers"] == {"base": 377}

    with pytest.raises(ValueError, match="page must be"):
        service.get_catalog_entries(**query, page=0)
    with pytest.raises(ValueError, match="page_size"):
        service.get_catalog_entries(
            panel_id="crc_358_msi",
            kind="gene",
            page=1,
            page_size=101,
        )


def test_review_status_filters_distinguish_provisional_and_legacy_runtime():
    provisional = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="gene",
        layer="reviewed_overlay",
        review_status="provisional_runtime",
        page=1,
        page_size=100,
    )
    assert provisional["total"] == 12
    assert {row["gene"] for row in provisional["rows"]} == {
        "CD274",
        "CHD2",
        "ERCC2",
        "ESR2",
        "HIST1H3B",
        "HLA-C",
        "HLA-DPA1",
        "PIK3C2G",
        "SLCO1B1",
        "WDR90",
        "XPC",
        "ZNF703",
    }
    assert all(
        row["review"]["status"] == "provisional_runtime"
        and row["review"]["scope"] == "entry_governance"
        and row["review"]["runtime_eligible"] is True
        and row["review"]["reviewer"] == "codex"
        and row["review"]["secondary_review_status"]
        == "pending_report_group_review"
        for row in provisional["rows"]
    )
    assert all(
        row["runtime_behavior"] == "override_base_on_match"
        and row["content"]["first_pass_status"] == "completed"
        and row["content"]["first_pass_reviewer_type"]
        == "ai_assisted_evidence_review"
        and row["content"]["secondary_review_status"]
        == "pending_report_group_review"
        and row["content"]["runtime_eligible"] is True
        and row["provenance"]["source_refs"]
        for row in provisional["rows"]
    )

    legacy_drug_narratives = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="drug",
        layer="reviewed_overlay",
        review_status="legacy_runtime",
        page=1,
        page_size=100,
    )
    assert legacy_drug_narratives["total"] == 35
    assert all(
        row["review"]["basis"] == "historical_final_report_migration"
        for row in legacy_drug_narratives["rows"]
    )

    provisional_targeted_rules = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="targeted_drug",
        layer="reviewed_overlay",
        review_status="provisional_runtime",
        page=1,
        page_size=100,
    )
    assert provisional_targeted_rules["total"] == 5
    assert {row["gene"] for row in provisional_targeted_rules["rows"]} == {
        "FANCA",
        "FANCD2",
        "PALB2",
        "RAD50",
        "RAD51D",
    }
    assert all(
        row["provenance"]["source_refs"]
        for row in provisional_targeted_rules["rows"]
    )


def test_public_catalog_payload_does_not_expose_internal_paths_or_phi_fields():
    internal_drugs = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="targeted_drug",
        layer="base",
        search="internal",
        page=1,
        page_size=100,
    )
    assert internal_drugs["total"] == 66
    assert len(internal_drugs["rows"]) == 66
    assert all(
        row["provenance"]["source_db"].lower() == "internal"
        and row["provenance"]["source_ref"] == "internal_curated_source"
        for row in internal_drugs["rows"]
    )

    public_payload = {
        "panels": service.get_catalog_panels(),
        "coverage": service.get_catalog_coverage("crc_301_msi"),
        "shared_overlay": service.get_catalog_entries(
            panel_id="crc_301_msi",
            kind="gene",
            layer="reviewed_overlay",
            page=1,
            page_size=100,
        ),
        "internal_drugs": internal_drugs,
    }
    forbidden_keys = {
        "patient_name",
        "sample_id",
        "report_number",
        "hospital",
        "file_path",
        "source_path",
        "original_filename",
    }
    assert forbidden_keys.isdisjoint(set(_walk_keys(public_payload)))

    serialized = json.dumps(public_payload, ensure_ascii=False)
    for forbidden_text in (
        str(ROOT),
        "/Volumes/",
        "/Users/",
        "/storage/",
        ".xlsx",
        ".xls",
        ".docx",
    ):
        assert forbidden_text.casefold() not in serialized.casefold()


@pytest.mark.parametrize("panel_id", ["unknown_panel", "../crc_358_msi", ""])
def test_unknown_panel_is_rejected_by_entries_and_coverage(panel_id: str):
    with pytest.raises(KeyError, match="Unknown panel"):
        service.get_catalog_entries(panel_id=panel_id, kind="gene")
    with pytest.raises(KeyError, match="Unknown panel"):
        service.get_catalog_coverage(panel_id)
