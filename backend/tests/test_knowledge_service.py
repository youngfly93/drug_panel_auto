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
        "review_status": "needs_review",
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
        "review_status": "approved_for_runtime",
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
        "gene_rows": 923,
        "unique_genes": 375,
        "gene_level_rows": 806,
        "variant_level_rows": 117,
        # Includes nine held UAT correction rows. They remain visible to
        # governance while being blocked from runtime report content.
        "drug_rows": 90,
        "drug_unique_genes": 24,
        "targeted_drug_rule_rows": 31,
        "targeted_drug_runtime_rule_rows": 17,
        "targeted_drug_blocked_rule_rows": 14,
        "targeted_drug_rule_unique_genes": 26,
        "targeted_drug_applicability_rule_rows": 1,
        "extra_reference_rows": 12,
        "review_status_counts": {
            "legacy_runtime": 336,
            "approved_for_runtime": 667,
            "needs_review": 9,
            "superseded": 1,
        },
    }
    if panel_id == "crc_301_msi":
        overlay_expected.update(
            gene_rows=801,
            unique_genes=342,
            gene_level_rows=711,
            variant_level_rows=90,
            drug_rows=49,
            drug_unique_genes=11,
            targeted_drug_rule_rows=9,
            targeted_drug_runtime_rule_rows=9,
            targeted_drug_blocked_rule_rows=0,
            targeted_drug_rule_unique_genes=9,
            review_status_counts={
                "legacy_runtime": 308,
                "approved_for_runtime": 542,
            },
        )
    assert payload["reviewed_overlay"] == overlay_expected
    assert payload["overlap"] == {
        "genes_in_both": 286 if panel_id == "crc_301_msi" else 355,
        "overlay_only_genes": 56 if panel_id == "crc_301_msi" else 20,
    }
    expected = {
        "crc_358_msi": (358, 350, 358, 358, 100.0),
        "crc_301_msi": (301, 256, 301, 301, 100.0),
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
    assert disposition["runtime_eligible_database_genes"] == 4
    assert disposition["database_only_filtered_genes"] == (
        111 if panel_id == "crc_301_msi" else 112
    )
    assert contract["gene_explanation_complete"] is True
    assert contract["gene_explanation_missing_count"] == 0
    assert contract["explicit_panel_rule_genes"] == (
        15 if panel_id == "crc_358_msi" else 9
    )
    assert contract["declared_panel_rule_genes"] == (
        26 if panel_id == "crc_358_msi" else 9
    )
    assert contract["explicitly_approved_drug_genes"] == (
        11 if panel_id == "crc_358_msi" else 7
    )
    assert contract["panel_rule_status_counts"] == (
        {
            "legacy_runtime": 6,
            "approved_for_runtime": 11,
            "needs_review": 14,
        }
        if panel_id == "crc_358_msi"
        else {
            "legacy_runtime": 2,
            "approved_for_runtime": 7,
        }
    )
    runtime_quality = contract["runtime_content_quality"]
    assert runtime_quality["complete_percent"] == 100.0
    assert runtime_quality["missing_intro_genes"] == []
    assert runtime_quality["missing_analysis_genes"] == []
    assert runtime_quality["citation_integrity"]["unresolved_pmids"] == []
    if panel_id == "crc_358_msi":
        assert runtime_quality["specific_explanation_genes"] == 358
        assert runtime_quality["specific_explanation_percent"] == 100.0
        assert runtime_quality["generic_fallback_genes"] == []
    else:
        assert runtime_quality["specific_explanation_genes"] == 301
        assert runtime_quality["generic_fallback_genes"] == []
    assert contract["clinical_release_readiness"]["status"] == "BLOCKED"
    generic_reason = "generic_gene_fallback_requires_content_review"
    blocking_reasons = contract["clinical_release_readiness"]["blocking_reasons"]
    assert generic_reason not in blocking_reasons
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

    assert crc301["total"] == 2
    assert {
        row["provenance"]["origin_panel_id"] for row in crc301["rows"]
    } == {"crc_301_msi"}
    assert all(
        row["provenance"]["shared_overlay"] is False for row in crc301["rows"]
    )
    assert {
        row["provenance"]["source_type"] for row in crc301["rows"]
    } == {
        "ncbi_refseq_curated_paraphrase",
        "official_reviewed_protein_annotation",
    }
    assert crc358["total"] == 0

    crc358_only = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="gene",
        layer="reviewed_overlay",
        gene="ABL2",
        page=1,
        page_size=10,
    )
    crc301_leak = service.get_catalog_entries(
        panel_id="crc_301_msi",
        kind="gene",
        layer="reviewed_overlay",
        gene="ABL2",
        page=1,
        page_size=10,
    )
    assert crc358_only["total"] == 2
    assert {
        row["provenance"]["source_type"] for row in crc358_only["rows"]
    } == {
        "official_gene_identity_plus_conservative_signaling_event_boundary",
        "official_reviewed_protein_annotation",
    }
    assert crc301_leak["total"] == 0


def test_drug_candidate_disposition_is_complete_and_not_a_migration_backlog():
    contract = service.get_catalog_coverage("crc_358_msi")[
        "knowledge_coverage_contract"
    ]
    disposition = contract["drug_candidate_disposition"]

    assert disposition["database_candidate_genes"] == 116
    assert disposition["runtime_eligible_database_genes"] == 4
    assert disposition["database_only_filtered_genes"] == 112
    assert disposition["pending_medical_review_rows"] == 0
    assert disposition["historical_review"]["approved_rows"] == 95
    assert disposition["historical_review"]["rejected_rows"] == 6
    assert disposition["filter_reason_row_counts"]["filtered_internal_generic"] == 54
    assert disposition["filter_reason_row_counts"]["filtered_missing_position"] > 0


def test_catalog_entry_counts_and_match_scopes_are_explicit():
    genes = service.get_catalog_entries(
        panel_id="crc_358_msi", kind="gene", page=1, page_size=1
    )
    assert genes["total"] == 1300
    assert genes["facets"] == {
        "layers": {"reviewed_overlay": 923, "base": 377},
        "review_statuses": {
            "legacy_runtime": 680,
            "approved_for_runtime": 620,
        },
        "match_scopes": {"gene": 1183, "variant": 117},
    }

    drugs = service.get_catalog_entries(
        panel_id="crc_358_msi", kind="drug", page=1, page_size=1
    )
    assert drugs["total"] == 171
    assert drugs["facets"] == {
        "layers": {"base": 81, "reviewed_overlay": 90},
        "review_statuses": {
            "legacy_runtime": 114,
            "approved_for_runtime": 47,
            "needs_review": 9,
            "superseded": 1,
        },
        "match_scopes": {"gene": 49, "variant": 106, "event": 16},
    }

    targeted = service.get_catalog_entries(
        panel_id="crc_358_msi", kind="targeted_drug", page=1, page_size=1
    )
    assert targeted["total"] == 842
    assert targeted["facets"] == {
        "layers": {"base": 811, "reviewed_overlay": 31},
        "review_statuses": {
            "legacy_runtime": 817,
            "approved_for_runtime": 11,
            "needs_review": 14,
        },
        "match_scopes": {"event": 622, "variant": 161, "gene": 59},
    }

    variant_rows = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="gene",
        layer="reviewed_overlay",
        match_scope="variant",
        page=1,
        page_size=100,
    )
    assert variant_rows["total"] == 117
    assert len(variant_rows["rows"]) == 100
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


def test_review_status_filters_distinguish_approved_and_legacy_runtime():
    approved = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="gene",
        layer="reviewed_overlay",
        review_status="approved_for_runtime",
        page=1,
        page_size=100,
    )
    approved_rows = list(approved["rows"])
    for page in range(2, (approved["total"] + 99) // 100 + 1):
        approved_rows.extend(
            service.get_catalog_entries(
                panel_id="crc_358_msi",
                kind="gene",
                layer="reviewed_overlay",
                review_status="approved_for_runtime",
                page=page,
                page_size=100,
            )["rows"]
        )
    assert approved["total"] == 620
    assert len(approved_rows) == 620
    domain_rows = [
        row
        for row in approved_rows
        if row["provenance"]["source_type"]
        == "official_reviewed_protein_annotation"
    ]
    assert len(domain_rows) == 273
    non_catalog_rows = [row for row in approved_rows if row not in domain_rows]
    assert {row["gene"] for row in non_catalog_rows} == {
        "ABL1",
        "AKT3",
        "AR",
        "ARAF",
        "ASXL1",
        "ATRX",
        "B2M",
        "BCL2",
        "BCOR",
        "BLM",
        "BMPR1A",
        "BRD4",
        "BTK",
        "CBL",
        "CCND1",
        "CCND2",
        "CDH1",
        "CDK12",
        "CDK4",
        "CDK6",
        "CDKN2A",
        "CD274",
        "CHD2",
        "CHEK1",
        "CHEK2",
        "CIC",
        "CREBBP",
        "CSF1R",
        "CSF3R",
        "DDR2",
        "DEK",
        "DNMT3A",
        "AKT1",
        "ALK",
        "ACVR2A",
        "AMER1",
        "EGFR",
        "EPHA2",
        "ERBB3",
        "ERCC2",
        "ERBB2",
        "ERBB4",
        "ESR2",
        "EP300",
        "EP400",
        "EZH2",
        "FAM175A",
        "FANCA",
        "FANCC",
        "FANCE",
        "FANCF",
        "FANCG",
        "FANCI",
        "FANCL",
        "FAT1",
        "FAT4",
        "FGF3",
        "FGF4",
        "FGFR1",
        "FGFR3",
        "FH",
        "FLCN",
        "FLT3",
        "FLT1",
        "GNA11",
        "GNAQ",
        "GALNT12",
        "GNAS",
        "H3F3A",
        "HIST1H1B",
        "HIST1H1C",
        "HIST1H1D",
        "HIST1H1E",
        "HIST1H2AL",
        "HIST1H2AM",
        "HIST1H2BC",
        "HIST1H2BD",
        "HIST1H2BG",
        "HIST1H2BJ",
        "HIST1H2BK",
        "HIST1H2BO",
        "HIST1H3A",
        "HIST1H3B",
        "HIST1H3C",
        "HIST1H3D",
        "HIST1H3E",
        "HIST1H3F",
        "HIST1H3G",
        "HIST1H3H",
        "HIST1H3I",
        "HIST1H3J",
        "HIST1H4I",
        "HIST3H3",
        "HLA-A",
        "HLA-B",
        "HLA-C",
        "HLA-DPA1",
        "HLA-DPB1",
        "HLA-DQA1",
        "HLA-DQB1",
        "HLA-DRB1",
        "HLA-DRB5",
        "HLA-G",
        "HIF1A",
        "HNF1A",
        "HOXB13",
        "IGF1R",
        "IFNGR1",
        "IFNGR2",
        "JUN",
        "KAT6A",
        "KDM6A",
        "KIT",
        "KMT2A",
        "LRP1B",
        "MDM2",
        "MET",
        "MED12",
        "MRE11A",
        "MSH3",
        "MTOR",
        "MUTYH",
        "MYC",
        "MYD88",
        "NBN",
        "NF2",
        "NOTCH2",
        "NPM1",
        "NRG1",
        "PALB2",
        "PDCD1LG2",
        "PDGFB",
        "PDGFRA",
        "PIK3CA",
        "PIK3C2G",
        "PMS1",
        "POLD1",
        "RAD51",
        "RAD51D",
        "RAD51B",
        "RAD52",
        "RAD54B",
        "RAD54L",
        "RAF1",
        "RARA",
        "RB1",
        "RBM10",
        "RECQL4",
        "RET",
        "ROS1",
        "RUNX1",
        "PTPRT",
        "SETD2",
        "SDHC",
        "SF3B1",
        "SLCO1B1",
        "SMAD4",
        "SMARCA1",
        "SMARCA2",
        "SMO",
        "STAG1",
        "STAG2",
        "TERC",
        "TERT",
        "TET1",
        "TMEM127",
        "TOP2A",
        "TP53BP1",
        "U2AF1",
        "VEGFA",
        "WDR90",
        "WHSC1",
        "WHSC1L1",
        "XPC",
        "XRCC2",
        "ZFHX3",
        "ZNF703",
        "ZRSR2",
        "AXIN1",
        "BCL2L11",
        "CARD11",
        "CCNE1",
        "CD79B",
        "CDH11",
        "CRKL",
        "EPAS1",
        "ERRFI1",
        "FGF19",
        "FOXL2",
        "GATA3",
        "IRS1",
        "JAK3",
        "KDR",
        "KEAP1",
        "KEL",
        "LBP1B",
        "MAP2K2",
        "MAPK1",
        "MAPK3",
        "MDM4",
        "MPL",
        "MYCN",
        "PDGFRB",
        "PIK3R1",
        "PIM1",
        "PPP2R2A",
        "PTCH2",
        "PTPN11",
        "RAD21",
        "SERPINB3",
        "SERPINB4",
        "SHH",
        "SLIT2",
        "SRC",
        "SYK",
        "TEK",
        "TGFBR1",
        "TNFAIP3",
        "TP63",
        "TSHR",
        "YAP1",
        "YES1",
        "ZNF217",
        "ZNF278",
        "ZNF521",
        "ABL2",
        "ACVR1B",
        "AXL",
        "DDR1",
        "EPHA3",
        "EPHB1",
        "FLT4",
        "INPP4A",
        "INPPL1",
        "INSR",
        "LATS1",
        "LATS2",
        "MAP2K7",
        "MAP3K13",
        "MAP3K4",
        "MAP3K6",
        "PASK",
        "PIK3CD",
        "PIK3CG",
        "PREX2",
        "PTPRB",
        "PTPRC",
        "PTPRD",
        "PTPRK",
        "PTPRS",
        "RICTOR",
        "RPTOR",
        "SMAD3",
        "SOS1",
        "VAV1",
        "VAV2",
        "ARID1B",
        "ARID2",
        "ARID4A",
        "ASXL2",
        "BACH2",
        "BCL11A",
        "BCORL1",
        "CHD4",
        "DNMT1",
        "DNMT3B",
        "HDAC4",
        "HDAC7",
        "HDAC9",
        "HIRA",
        "KDM2B",
        "KDM4C",
        "KDM5A",
        "KMT2B",
        "NCOR1",
        "NCOR2",
        "NSD1",
        "SETD5",
        "TET2",
        "TRRAP",
        "CUX1",
        "ETV1",
        "FLI1",
        "FOXP1",
        "FUBP1",
        "MAX",
        "MGA",
        "MYB",
        "PAX5",
        "RUNX1T1",
        "RUNX2",
        "SOX9",
        "TCF12",
        "TCF3",
        "TCF4",
        "TLE3",
        "TLE4",
        "NCOA4",
        "ATXN2",
        "CLTCL1",
        "DNM2",
        "FAT3",
        "MAGI2",
        "MGAM",
        "MUC1",
        "MYH11",
        "PCLO",
        "PDE4DIP",
        "PRSS1",
    }
    assert all(
        row["review"]["status"] == "approved_for_runtime"
        and row["review"]["scope"] == "entry_governance"
        and row["review"]["runtime_eligible"] is True
        and row["review"]["reviewer"] == "codex"
        and row["review"]["secondary_review_status"]
        == "report_group_approved"
        for row in approved_rows
    )
    assert all(
        row["runtime_behavior"] == "override_base_on_match"
        and row["content"]["secondary_review_status"]
        == "report_group_approved"
        and row["content"]["runtime_eligible"] is True
        and row["provenance"]["source_refs"]
        for row in approved_rows
    )

    legacy_drug_narratives = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="drug",
        layer="reviewed_overlay",
        review_status="legacy_runtime",
        page=1,
        page_size=100,
    )
    assert legacy_drug_narratives["total"] == 33
    assert all(
        row["review"]["basis"] == "historical_final_report_migration"
        for row in legacy_drug_narratives["rows"]
    )

    approved_targeted_rules = service.get_catalog_entries(
        panel_id="crc_358_msi",
        kind="targeted_drug",
        layer="reviewed_overlay",
        review_status="approved_for_runtime",
        page=1,
        page_size=100,
    )
    assert approved_targeted_rules["total"] == 11
    assert {row["gene"] for row in approved_targeted_rules["rows"]} == {
        "EGFR",
        "ERBB2",
        "ATM",
        "FANCA",
        "FANCD2",
        "FLT3",
        "PALB2",
        "RAD50",
        "RAD51D",
        "SETD2",
        "TP53",
    }
    assert all(
        row["provenance"]["source_refs"]
        for row in approved_targeted_rules["rows"]
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
