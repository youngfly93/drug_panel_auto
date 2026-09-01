# ruff: noqa: E402, I001
"""Targeted-drug rules must stay request-scoped to the selected panel."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

import pytest


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
from reportgen.models.excel_data import ExcelDataSource
from reportgen.models.report_data import ReportData
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
    assert len(crc358["reviewed_variant_overrides"]) == 19
    assert len(crc358["blocked_reviewed_variant_overrides"]) == 13
    assert len(crc358["applicability_rules"]) == 1
    assert "genes" not in crc358["applicability_rules"][0]
    assert crc358["applicability_rules"][0]["sources"] == ["internal"]
    assert crc358["applicability_rules"][0][
        "reject_when_db_position_missing"
    ] is True
    assert crc358["overrides"] == {}

    assert crc301["enabled"] is True
    assert crc301["source_panel_id"] == "crc_358_msi"
    assert crc301["shared"] is True
    assert len(crc301["reviewed_variant_overrides"]) == 9
    assert not any(
        row.get("c_hgvs") in {"c.499C>T", "c.1291delA", "c.34G>T"}
        for row in crc301["reviewed_variant_overrides"]
    )

    assert lung["enabled"] is True
    assert lung["source_panel_id"] == "lung_588_pdl1"
    assert lung["shared"] is True
    assert lung["base_db_enabled"] is False
    assert lung["allowed_source_dbs"] == []
    assert lung["allow_internal_rows"] is False
    assert lung["approved_drug_rows_enabled"] is False
    assert len(lung["reviewed_variant_overrides"]) == 2
    assert lung["blocked_reviewed_variant_overrides"] == []
    notices = {
        row["gene"]: row.get("_clinical_context_display_notice")
        for row in lung["reviewed_variant_overrides"]
    }
    assert notices == {
        "BRAF": "肺癌病理类型、疾病范围/分期、伴随诊断状态未提供",
        "ERBB2": (
            "肺癌病理类型、疾病范围/分期、既往系统治疗情况、"
            "伴随诊断状态未提供"
        ),
    }
    assert all(
        row.get("_review_status_display_notice") == "待报告组审"
        for row in lung["reviewed_variant_overrides"]
    )
    assert lung["applicability_rules"] == []
    assert lung["overrides"] == {}

    for context in (endometrial,):
        assert context["enabled"] is False
        assert context["base_db_enabled"] is False
        assert context["allowed_source_dbs"] == []
        assert context["allow_internal_rows"] is False
        assert context["approved_drug_rows_enabled"] is False
        assert context["summary_display_scope"] == "drug_matched_variants"
        assert context["summary_display_variant_levels"] == ["Ⅰ类", "Ⅱ类"]
        assert context["reviewed_variant_overrides"] == []
        assert context["blocked_reviewed_variant_overrides"] == []
        assert context["applicability_rules"] == []
        assert context["overrides"] == {}


def test_shared_part3_overlay_honors_exact_row_panel_scope():
    variant = {
        "gene": "FANCD2",
        "cHGVS": "c.1630C>T",
        "pHGVS": "p.Q544*",
        "benefit_drugs": "--",
        "caution_drugs": "--",
        "research_drugs": "芦卡帕利\n奥拉帕利+帕博利珠单抗",
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

    crc358_sections = sections("crc_358_msi")
    assert [row["gene"] for row in crc358_sections] == ["FANCD2"]
    assert crc358_sections[0]["drug_type"] == "research"
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

    assert len(crc301_config.reviewed_variant_overrides) == 9
    assert len(lung_config.reviewed_variant_overrides) == 2
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

    # The exact lung rule is transcript-bound. This lookup deliberately omits
    # transcript, so neither the exact rule nor the disabled base DB may fire.
    for lookup, approved_count in observed["lung_329_pdl1"]:
        assert lookup == ("--", "--", 0.0)
        assert approved_count == 0

    for lookup, approved_count in observed["endometrial_29"]:
        assert lookup == ("--", "--", 0.0)
        assert approved_count == 0


@pytest.mark.parametrize("panel_id", ["lung_329_pdl1", "lung_588_pdl1"])
def test_explicit_lung_policy_never_reopens_ctdrug_when_base_db_is_unavailable(
    panel_id,
    tmp_path,
    monkeypatch,
):
    source = tmp_path / f"{panel_id}.xlsx"
    source.write_bytes(b"synthetic")
    excel_data = ExcelDataSource(
        file_path=str(source),
        sheet_names=["Variations", "CtDrug"],
        table_data={
            "Variations": [
                {
                    "Gene_Symbol": "BRAF",
                    "Transcript": "NM_004333.6",
                    "cHGVS": "c.1799T>A",
                    "pHGVS_S": "p.V600E",
                    "ExistIn552": "Ⅱ类",
                },
                {
                    "Gene_Symbol": "BRAF",
                    "Transcript": "NM_004333.6",
                    "cHGVS": "c.1781A>G",
                    "pHGVS_S": "p.D594G",
                    "ExistIn552": "Ⅱ类",
                },
            ],
            "CtDrug": [
                {
                    "检测基因": "BRAF",
                    "药物": "SENTINEL-GENE-FALLBACK",
                    "证据等级": "D",
                    "用药提示（仅供参考）": "敏感",
                }
            ],
        },
    )
    rules = load_targeted_drug_rule_context(_package(panel_id))
    mapper = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR")
    mapper._targeted_drug_db = None
    monkeypatch.setattr(mapper, "_load_targeted_drug_db", lambda: None)
    report_data = ReportData()
    report_data.set_field("cancer_type", "肺癌")

    rows = mapper._build_targeted_drug_tips(
        excel_data,
        report_data,
        targeted_drug_rules=rules,
    )

    assert len(rows) == 1
    assert rows[0]["gene"] == "BRAF"
    assert "p.V600E" in rows[0]["variant_site"]
    assert "达拉非尼+曲美替尼" in rows[0]["benefit_drugs"]
    assert "肺癌病理类型、疾病范围/分期、伴随诊断状态未提供" in rows[0][
        "benefit_drugs"
    ]
    assert "待报告组审" in rows[0]["benefit_drugs"]
    assert "SENTINEL-GENE-FALLBACK" not in str(rows)
