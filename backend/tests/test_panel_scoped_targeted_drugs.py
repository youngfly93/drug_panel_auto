# ruff: noqa: E402, I001
"""Targeted-drug rules must stay request-scoped to the selected panel."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.services import knowledge_service
from reportgen.core.field_mapper import FieldMapper
from reportgen.core.report_generator import ReportGenerator
from reportgen.core.template_bridge_358 import load_panel_config
from reportgen.knowledge.gene_knowledge import GeneKnowledgeProvider
from reportgen.panels.loader import load_panel_package
from reportgen.rules.targeted_drugs import load_targeted_drug_rule_context

def _package(panel_id: str):
    return load_panel_package(panel_id, project_root=ROOT)


def _context(panel_id: str) -> dict:
    context = load_targeted_drug_rule_context(_package(panel_id))
    assert context is not None
    return context


def test_targeted_drug_rule_context_matrix():
    crc358 = _context("crc_358_msi")
    crc301 = _context("crc_301_msi")
    lung = _context("lung_329_pdl1")
    endometrial = _context("endometrial_29")

    assert crc358["enabled"] is True
    assert crc358["base_db_enabled"] is True
    assert set(crc358["allowed_source_dbs"]) == {"INTERNAL", "CGI", "CIVIC"}
    assert crc358["allow_internal_rows"] is True
    assert crc358["approved_drug_rows_enabled"] is True
    assert crc358["summary_display_scope"] == "drug_matched_variants"
    assert crc358["summary_display_variant_levels"] == ["Ⅰ类", "Ⅱ类"]
    assert crc358["source_panel_id"] == "crc_358_msi"
    assert len(crc358["reviewed_variant_overrides"]) == 15
    assert len(crc358["applicability_rules"]) == 1
    assert set(crc358["overrides"]) == {"ATM", "SETD2"}

    assert crc301["enabled"] is True
    assert crc301["source_panel_id"] == "crc_358_msi"
    assert crc301["shared"] is True
    assert len(crc301["reviewed_variant_overrides"]) == 7
    assert not any(
        row.get("c_hgvs") in {"c.499C>T", "c.1291delA", "c.34G>T"}
        for row in crc301["reviewed_variant_overrides"]
    )

    for context in (lung, endometrial):
        assert context["enabled"] is False
        assert context["base_db_enabled"] is False
        assert context["allowed_source_dbs"] == []
        assert context["allow_internal_rows"] is False
        assert context["approved_drug_rows_enabled"] is False
        assert context["summary_display_scope"] == "drug_matched_variants"
        assert context["summary_display_variant_levels"] == ["Ⅰ类", "Ⅱ类"]
        assert context["reviewed_variant_overrides"] == []
        assert context["applicability_rules"] == []
        assert context["overrides"] == {}


def test_shared_part3_overlay_honors_exact_row_panel_scope():
    variant = {
        "gene": "FANCD2",
        "cHGVS": "c.1630C>T",
        "pHGVS": "p.Q544*",
        "benefit_drugs": "奥拉帕利（C）",
        "caution_drugs": "--",
    }

    def sections(panel_id: str):
        package = _package(panel_id)
        provider = GeneKnowledgeProvider(
            {
                "enabled": True,
                "panel_id": panel_id,
                "gene_knowledge_db": {
                    "enabled": True,
                    "path": "missing.xlsx",
                    "reviewed_part3_overlay_paths": (
                        ReportGenerator._resolve_panel_reviewed_part3_overlays(
                            package
                        )
                    ),
                },
            }
        )
        provider.load(base_path=str(ROOT))
        return provider.build_drug_analysis_sections([variant])

    assert [row["gene"] for row in sections("crc_358_msi")] == ["FANCD2"]
    assert sections("crc_301_msi") == []

    # The read-only Web catalog must expose the same scope as Word runtime.
    assert knowledge_service.get_catalog_entries(
        panel_id="crc_301_msi",
        kind="drug",
        layer="reviewed_overlay",
        gene="FANCD2",
        search="c.1630C>T",
        page=1,
        page_size=10,
    )["total"] == 0


def test_same_mapper_does_not_leak_reviewed_override_between_panels():
    mapper = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR")
    contexts = {
        panel: _context(panel)
        for panel in (
            "crc_358_msi",
            "lung_329_pdl1",
            "crc_301_msi",
            "endometrial_29",
        )
    }

    def lookup(panel: str):
        return mapper._lookup_reviewed_variant_override_drugs(
            "TP53",
            "c.821T>A",
            "p.V274D",
            variant_level="Ⅱ类",
            targeted_drug_rules=contexts[panel],
        )

    assert lookup("crc_358_msi") is not None
    assert lookup("lung_329_pdl1") is None
    assert lookup("crc_301_msi") is not None
    assert lookup("endometrial_29") is None
    assert lookup("crc_358_msi") is not None


def test_panel_rule_lookup_is_safe_when_shared_mapper_is_used_concurrently():
    mapper = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR")
    crc = _context("crc_358_msi")
    lung = _context("lung_329_pdl1")

    def lookup(context: dict) -> bool:
        result = mapper._lookup_reviewed_variant_override_drugs(
            "TP53",
            "c.821T>A",
            "p.V274D",
            variant_level="Ⅱ类",
            targeted_drug_rules=context,
        )
        return result is not None

    contexts = [crc, lung] * 20
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lookup, contexts))

    assert results == [True, False] * 20


def test_enhancer_panel_config_uses_same_request_scoped_drug_policy():
    crc301 = _package("crc_301_msi")
    lung = _package("lung_329_pdl1")

    crc301_config = load_panel_config(
        base_path=str(ROOT),
        panel_id="crc_301_msi",
        config_path=str(crc301.resolve_rule_file("panel_rules")),
        panel_package=crc301,
    )
    lung_config = load_panel_config(
        base_path=str(ROOT),
        panel_id="lung_329_pdl1",
        config_path=str(lung.resolve_rule_file("panel_rules")),
        panel_package=lung,
    )

    assert len(crc301_config.reviewed_variant_overrides) == 7
    assert lung_config.reviewed_variant_overrides == []
    assert len(crc301_config.approved_drug_rows) == 7
    assert lung_config.approved_drug_rows == []


def test_real_targeted_db_and_fixed_table_are_disabled_for_non_crc_panels():
    mapper = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR")
    observed = {}
    for panel_id, cancer_type in (
        ("crc_358_msi", "结直肠癌"),
        ("lung_329_pdl1", "肺癌"),
        ("crc_301_msi", "结直肠癌"),
        ("endometrial_29", "子宫内膜癌"),
        ("crc_358_msi", "结直肠癌"),
    ):
        package = _package(panel_id)
        context = load_targeted_drug_rule_context(package)
        lookup = mapper._lookup_targeted_drugs_for_variant(
            "BRAF",
            c_point="c.1799T>A",
            p_point="p.V600E",
            variant_level="Ⅱ类",
            cancer_type=cancer_type,
            targeted_drug_rules=context,
        )
        panel_config = load_panel_config(
            base_path=str(ROOT),
            panel_id=panel_id,
            config_path=str(package.resolve_rule_file("panel_rules")),
            panel_package=package,
        )
        observed.setdefault(panel_id, []).append(
            (lookup, len(panel_config.approved_drug_rows))
        )

    expected_approved_counts = {"crc_358_msi": 7, "crc_301_msi": 7}
    for panel_id in ("crc_358_msi", "crc_301_msi"):
        for (benefit, caution, score), approved_count in observed[panel_id]:
            assert score > 0
            assert "康奈非尼" in benefit
            assert "西妥昔单抗" in caution
            assert approved_count == expected_approved_counts[panel_id]

    for panel_id in ("lung_329_pdl1", "endometrial_29"):
        for lookup, approved_count in observed[panel_id]:
            assert lookup == ("--", "--", 0.0)
            assert approved_count == 0
