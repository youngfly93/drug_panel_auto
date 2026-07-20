# ruff: noqa: E402, I001
"""Regression contracts for the 2026-07-20 report-group feedback."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.core.report_generator import ReportGenerator
from reportgen.core.template_bridge_358 import PanelConfig, _build_nccn_and_immune_fields
from reportgen.core.template_renderer import TemplateRenderer
from reportgen.knowledge.gene_knowledge import GeneKnowledgeProvider
from reportgen.knowledge.governance import load_and_validate_overlay
from reportgen.models.excel_data import ExcelDataSource
from reportgen.models.report_data import ReportData
from reportgen.panels.loader import load_panel_package


def _crc358_provider() -> GeneKnowledgeProvider:
    settings = yaml.safe_load((ROOT / "config/settings.yaml").read_text(encoding="utf-8"))
    gene_config = copy.deepcopy(settings["knowledge_bases"]["gene_knowledge_db"])
    package = load_panel_package("crc_358_msi", project_root=ROOT)
    gene_config["panel_id"] = "crc_358_msi"
    gene_config["reviewed_part3_overlay_paths"] = (
        ReportGenerator._resolve_panel_reviewed_part3_overlays(package)
    )
    provider = GeneKnowledgeProvider(
        {"enabled": True, "panel_id": "crc_358_msi", "gene_knowledge_db": gene_config}
    )
    assert provider.load(base_path=str(ROOT))
    return provider


def _section(provider: GeneKnowledgeProvider, gene: str, c_hgvs: str, p_hgvs: str):
    return provider.build_gene_knowledge_section(
        gene=gene,
        c_hgvs=c_hgvs,
        p_hgvs=p_hgvs,
        frequency=12.34,
        mutation_type="Missense",
        has_drug=False,
    )


def test_fixed_domain_survives_erbb2_variant_overlay():
    section = _section(_crc358_provider(), "ERBB2", "c.2521C>A", "p.L841I")
    combined = f"{section['intro']}\n{section['mutation_analysis']}"

    assert "蛋白全长为1255个氨基酸" in combined
    assert "Protein kinase" in combined
    assert "ERBB2基因编码的蛋白全长" in combined
    assert combined.count("蛋白全长为1255个氨基酸") == 1


def test_complementary_kras_domains_are_preserved_once():
    section = _section(_crc358_provider(), "KRAS", "c.35G>A", "p.G12D")
    combined = f"{section['intro']}\n{section['mutation_analysis']}"

    assert combined.count("RAS结构域") == 1
    assert combined.count("Hypervariable region") == 1
    assert combined.count("蛋白全长为189个氨基酸") == 1


def test_missing_gene_domains_ship_as_governed_first_review_overlay():
    overlay_path = ROOT / "panels/crc_358_msi/rules/reviewed_part3_domain_overlay_20260720.yaml"
    package = load_panel_package("crc_358_msi", project_root=ROOT)
    assert overlay_path in {
        Path(path) for path in ReportGenerator._resolve_panel_reviewed_part3_overlays(package)
    }

    validation = load_and_validate_overlay(overlay_path, "crc_358_msi")
    assert validation["status"] == "PASS", validation["issues"]
    assert validation["gene"]["status_counts"] == {"provisional_runtime": 4}
    assert validation["gene"]["secondary_review_complete_rows"] == 0

    provider = _crc358_provider()
    expected = {
        "FANCA": ("1455个氨基酸", "ArcN结构域"),
        "PALB2": ("1186个氨基酸", "WD40重复结构域"),
        "DNMT3A": ("912个氨基酸", "ADD结构域"),
        "RAD51D": ("328个氨基酸", "RecA样ATP酶家族"),
    }
    for gene, markers in expected.items():
        section = _section(provider, gene, "c.999A>G", "p.X333Y")
        combined = f"{section['intro']}\n{section['mutation_analysis']}"
        assert all(marker in combined for marker in markers), (gene, combined)


def test_drug_consistency_gate_detects_missing_and_duplicate_items():
    provider = GeneKnowledgeProvider({"enabled": False})
    variant = {
        "gene": "DEMO",
        "cHGVS": "c.1A>G",
        "pHGVS": "p.M1V",
        "benefit_drugs": "甲药（C）\n乙药（C）",
        "caution_drugs": "--",
    }
    sections = [
        {
            "gene": "DEMO",
            "c_hgvs": "c.1A>G",
            "p_hgvs": "p.M1V",
            "drug_type": "benefit",
            "drug_name": "甲药（Drug A）",
        },
        {
            "gene": "DEMO",
            "c_hgvs": "c.1A>G",
            "p_hgvs": "p.M1V",
            "drug_type": "benefit",
            "drug_name": "甲药",
        },
    ]

    result = provider.build_drug_analysis_consistency([variant], sections)

    assert result["status"] == "FAIL"
    assert result["missing"][0]["drugs"] == ["乙药（C）"]
    assert result["duplicates"][0]["drugs"] == ["甲药（Drug A）"]


def test_feedback_drug_rows_match_part3_without_overlapping_blocks():
    provider = _crc358_provider()
    variants = [
        {
            "gene": "KRAS",
            "cHGVS": "c.35G>A",
            "pHGVS": "p.G12D",
            "benefit_drugs": "\n".join(
                [
                    "Avutometinib+Defactinib（C）",
                    "司美替尼（C）",
                    "曲美替尼+Navitoclax（C）",
                    "帕尼单抗+曲美替尼（C）",
                    "贝美替尼+哌柏西利（C）",
                    "BI 1701963（C）",
                    "BI 1701963+曲美替尼（C）",
                    "PD0325901+哌柏西利（C）",
                    "奈拉替尼+曲美替尼（C）",
                    "福巴替尼+贝美替尼（C）",
                    "依维莫司+Avutometinib（C）",
                    "GH35（C）",
                    "RMC-6236（C）",
                    "HRS-4642（C）",
                    "ASP3082（C）",
                    "ASP4396（C）",
                    "RMC-9805（C）",
                    "RMC-9805+RMC-6236（C）",
                    "PD0325901（D）",
                ]
            ),
            "caution_drugs": "西妥昔单抗（A）\n帕尼单抗（A）\n依维莫司（C）",
        },
        {
            "gene": "PALB2",
            "cHGVS": "c.47del",
            "pHGVS": "p.K16Sfs*2",
            "benefit_drugs": "\n".join(
                [
                    "奥拉帕利（C）",
                    "芦卡帕利（C）",
                    "尼拉帕利（C）",
                    "他拉唑帕利（C）",
                    "氟唑帕利（C）",
                    "LY2606368（C）",
                    "奥拉帕利+帕博利珠单抗（C）",
                    "帕米帕利+替雷利珠单抗（C）",
                    "芦卡帕利+阿替利珠单抗（C）",
                    "他拉唑帕利+阿替利珠单抗（C）",
                ]
            ),
            "caution_drugs": "--",
        },
        {
            "gene": "RAD51D",
            "cHGVS": "c.685C>T",
            "pHGVS": "p.Q229*",
            "benefit_drugs": "\n".join(
                [
                    "芦卡帕利（C）",
                    "LY2606368（C）",
                    "帕米帕利+替雷利珠单抗（C）",
                    "芦卡帕利+阿替利珠单抗（C）",
                ]
            ),
            "caution_drugs": "--",
        },
    ]

    sections = provider.build_drug_analysis_sections(variants)
    result = provider.build_drug_analysis_consistency(variants, sections)

    assert result["status"] == "PASS", result
    kras_benefit = [
        row for row in sections if row.get("gene") == "KRAS" and row.get("drug_type") == "benefit"
    ]
    assert len(kras_benefit) == 3


def test_consistency_gate_is_limited_to_governed_drug_contracts():
    provider = _crc358_provider()

    assert provider.has_reviewed_drug_analysis_contract(
        {
            "gene": "KRAS",
            "cHGVS": "c.35G>A",
            "pHGVS": "p.G12D",
        }
    )
    assert provider.has_reviewed_drug_analysis_contract(
        {
            "gene": "PALB2",
            "cHGVS": "c.47del",
            "pHGVS": "p.K16Sfs*2",
        }
    )
    assert not provider.has_reviewed_drug_analysis_contract(
        {
            "gene": "ERBB2",
            "cHGVS": "c.1979G>A",
            "pHGVS": "p.G660D",
        }
    )


def test_kras_everolimus_rules_use_primary_source_and_conservative_scope():
    overlay = yaml.safe_load(
        (ROOT / "panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml").read_text(
            encoding="utf-8"
        )
    )
    rows = [
        row
        for row in overlay["drug_sections"]
        if row.get("gene") == "KRAS"
        and row.get("p_hgvs") in {"p.G12S", "p.G12D"}
        and row.get("type") == "caution"
        and "依维莫司" in str(row.get("drug_name") or "")
    ]

    assert {row["p_hgvs"] for row in rows} == {"p.G12S", "p.G12D"}
    for row in rows:
        combined = f"{row['relation']}\n{row['clinical']}"
        assert "20664172" in combined
        assert "29285035" not in combined
        assert "28544747" not in combined
        assert "并非" in combined and "位点专属" in combined
        assert row["review_status"] == "provisional_runtime"
        assert row["secondary_review_status"] == "pending_report_group_review"
        assert row["review_metadata"]["references"] == [
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC2912177/"
        ]


def test_kras_g12c_correction_supersedes_misattributed_historical_entry():
    correction_path = ROOT / "panels/crc_358_msi/rules/reviewed_part3_corrections_20260720.yaml"
    package = load_panel_package("crc_358_msi", project_root=ROOT)
    overlays = [
        Path(path) for path in ReportGenerator._resolve_panel_reviewed_part3_overlays(package)
    ]
    historical_path = ROOT / "panels/crc_358_msi/rules/reviewed_part3_crc358_reviewed_case_a.yaml"
    assert correction_path in overlays
    assert overlays.index(correction_path) > overlays.index(historical_path)

    validation = load_and_validate_overlay(correction_path, "crc_358_msi")
    assert validation["status"] == "PASS", validation["issues"]
    assert validation["drug"]["status_counts"] == {"provisional_runtime": 2}
    assert validation["drug"]["secondary_review_complete_rows"] == 0

    provider = _crc358_provider()
    variant = {
        "gene": "KRAS",
        "cHGVS": "c.34G>T",
        "pHGVS": "p.G12C",
        "benefit_drugs": "--",
        "caution_drugs": "依维莫司（C）",
    }
    rows = [
        row
        for row in provider.build_drug_analysis_sections([variant])
        if row.get("gene") == "KRAS" and "依维莫司" in row.get("drug_name", "")
    ]
    assert len(rows) == 1
    combined = f"{rows[0]['relation']}\n{rows[0]['clinical']}"
    assert combined.count("20664172") == 2
    assert "29285035" not in combined
    assert "28544747" not in combined
    assert "并非p.G12C位点专属临床证据" in combined


def test_kras_g12c_correction_does_not_leak_to_adjacent_variant():
    provider = _crc358_provider()
    rows = provider.build_drug_analysis_sections(
        [
            {
                "gene": "KRAS",
                "cHGVS": "c.34G>C",
                "pHGVS": "p.G12R",
                "benefit_drugs": "--",
                "caution_drugs": "依维莫司（C）",
            }
        ]
    )
    assert len(rows) == 1
    combined = f"{rows[0]['relation']}\n{rows[0]['clinical']}"
    assert "p.G12C" not in combined
    assert "20664172" in combined
    assert "29285035" not in combined
    assert "28544747" not in combined
    assert "不是任一具体位点的专属临床证据" in combined


def test_nccn_results_annotate_only_class_iii_variants(tmp_path):
    source = tmp_path / "empty.xlsx"
    source.touch()
    excel_data = ExcelDataSource(file_path=str(source))
    report_data = ReportData()
    panel_config = PanelConfig(
        nccn_result_rows=[
            {"key": "ERBB2_MUT", "genes": ["ERBB2"], "match": "突变"},
            {"key": "KRAS_MUT", "genes": ["KRAS"], "match": "突变"},
        ],
        immune_positive_rows=[],
        immune_negative_rows=[],
        immune_hyperprogression_rows=[],
    )

    _build_nccn_and_immune_fields(
        report_data,
        [
            {
                "gene": "ERBB2",
                "cHGVS": "c.2521C>A",
                "pHGVS": "p.L841I",
                "gene_class": "Ⅲ类",
            },
            {
                "gene": "KRAS",
                "cHGVS": "c.35G>A",
                "pHGVS": "p.G12D",
                "gene_class": "Ⅱ类",
            },
        ],
        excel_data,
        panel_config=panel_config,
    )

    assert report_data.get_field("nccn_ERBB2_MUT") == ("c.2521C>A，p.L841I（意义未明变异）")
    assert report_data.get_field("nccn_KRAS_MUT") == "c.35G>A，p.G12D"


def _set_table_widths(table, width_twips: int) -> None:
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.insert(0, tbl_w)
    tbl_w.set(qn("w:type"), "dxa")
    tbl_w.set(qn("w:w"), str(width_twips))

    grid_cols = table._tbl.tblGrid.findall(qn("w:gridCol"))
    per_column = width_twips // len(grid_cols)
    for grid_col in grid_cols:
        grid_col.set(qn("w:w"), str(per_column))
    for tc_w in table._tbl.findall(".//w:tcPr/w:tcW", table._tbl.nsmap):
        tc_w.set(qn("w:type"), "dxa")
        tc_w.set(qn("w:w"), str(per_column))


def test_crc_variant_detail_table_expands_to_content_width(tmp_path):
    docx_path = tmp_path / "variant_detail_width.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=9)
    table.rows[0].cells[0].text = "基因名称"
    table.rows[0].cells[1].text = "基因突变信息"
    table.rows[0].cells[6].text = "靶向药物信息"
    table.rows[1].cells[1].text = "转录本号"
    table.rows[1].cells[6].text = "潜在获益靶向药物"
    _set_table_widths(table, 4500)
    expected_width = int(
        doc.sections[0].page_width.twips
        - doc.sections[0].left_margin.twips
        - doc.sections[0].right_margin.twips
    )
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._fit_tables_to_page_width(
        str(docx_path),
        {
            "panel_style": {
                "variant_detail_table": {
                    "fit_to_content_width": True,
                    "minimum_content_width_ratio": 0.98,
                }
            }
        },
    )

    rendered = Document(docx_path)
    grid_cols = rendered.tables[0]._tbl.tblGrid.findall(qn("w:gridCol"))
    assert sum(int(col.get(qn("w:w"))) for col in grid_cols) == expected_width
    layout = rendered.tables[0]._tbl.tblPr.find(qn("w:tblLayout"))
    assert layout is not None
    assert layout.get(qn("w:type")) == "fixed"


def test_part3_drug_names_and_narrative_have_ten_point_space_after(tmp_path):
    docx_path = tmp_path / "part3_drug_spacing.docx"
    doc = Document()
    for text in [
        "第三部分：基因变异及相应靶向/免疫药物解析",
        "靶向药物/免疫用药提示解析",
        "潜在获益靶向/免疫药物解析",
        "KRAS：c.35G>A，p.G12D突变相应潜在获益药物",
        "依维莫司",
        "药物疗效临床解析：",
        "这是药物解析正文。",
        "3. 阅读说明",
    ]:
        doc.add_paragraph(text)
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._restore_part3_dynamic_styles(
        str(docx_path),
        {"drug_benefit_sections": [{"drug_name": "依维莫司"}]},
    )

    rendered = Document(docx_path)
    by_text = {
        paragraph.text.strip(): paragraph
        for paragraph in rendered.paragraphs
        if paragraph.text.strip()
    }
    assert by_text["依维莫司"].paragraph_format.space_after.pt == 10.0
    assert by_text["这是药物解析正文。"].paragraph_format.space_after.pt == 10.0


def test_targeted_results_heading_is_configured_for_idempotent_new_page():
    settings = yaml.safe_load((ROOT / "config/settings.yaml").read_text(encoding="utf-8"))
    assert (
        "2. 靶向药物相关检测结果" in settings["report_content"]["force_page_break_before_headings"]
    )


def test_immune_brand_note_uses_compact_reviewed_style():
    doc = Document()
    paragraph = doc.add_paragraph(
        "3. 上表涉及的已上市的药物名称及对应的商品名称："
        "帕博利珠单抗[可瑞达]、纳武利尤单抗[欧狄沃]。"
    )

    changed = TemplateRenderer(log_level="ERROR")._apply_immune_table_notes_to_doc(
        doc,
        {
            "panel_style": {
                "biomarker_table": {
                    "note_font_size": 8,
                    "note_line_spacing": 1.0,
                }
            }
        },
    )

    assert changed is True
    assert paragraph.paragraph_format.line_spacing == 1.0
    assert paragraph.paragraph_format.space_before.pt == 0.0
    assert paragraph.paragraph_format.space_after.pt == 0.0
    assert all(run.font.size.pt == 8.0 for run in paragraph.runs if run.text)


def test_report_generator_reuses_the_validated_context_for_rendering(tmp_path, monkeypatch):
    generator = ReportGenerator(config_dir=str(ROOT / "config"), log_level="ERROR")
    validated_context = {
        "project_type": "crc_358_msi",
        "_require_deterministic_layout": True,
    }
    captured = {}

    def fake_render(*_args, **kwargs):
        captured.update(kwargs)
        generator.template_renderer.last_processor_report = []
        return str(tmp_path / "report.docx")

    monkeypatch.setattr(generator.template_renderer, "render", fake_render)
    monkeypatch.setattr(
        generator,
        "_get_template_processor_names",
        lambda *_args, **_kwargs: [],
    )
    state = SimpleNamespace(
        report_data=ReportData(),
        output_path=str(tmp_path / "report.docx"),
        template_file=str(tmp_path / "template.docx"),
        panel_package=None,
        canonical_project_type="crc_358_msi",
        template_context=validated_context,
        final_output=None,
        processor_report=[],
        template_processor_names=None,
    )
    stage = SimpleNamespace(artifacts={}, metrics={})

    generator._stage_template_render(stage, state)

    assert captured["template_context"] is validated_context
    assert captured["template_context"]["_require_deterministic_layout"] is True


def test_legal_notice_normalizer_writes_east_asian_font_and_is_idempotent(
    tmp_path,
):
    docx_path = tmp_path / "legal_notice.docx"
    doc = Document()
    notice = doc.add_paragraph()
    notice_run = notice.add_run("检测结果仅对本次送检样本负责，电子版仅供参考。")
    notice_run.font.name = "微软雅黑"
    consultation = doc.add_paragraph()
    consultation_run = consultation.add_run("咨询电话：00000000。")
    consultation_run.font.name = "微软雅黑"
    doc.save(docx_path)

    renderer = TemplateRenderer(log_level="ERROR")
    context = {
        "consultation_line": "咨询电话：00000000。",
        "report_content": {
            "legal_notice_style": {
                "marker": "检测结果仅对本次送检样本负责",
                "font_name": "宋体",
            }
        },
    }
    renderer._normalize_legal_notice_style(str(docx_path), context)

    rendered = Document(docx_path)
    for paragraph in rendered.paragraphs:
        for run in paragraph.runs:
            r_fonts = run._r.get_or_add_rPr().rFonts
            assert r_fonts is not None
            for attr in ("ascii", "hAnsi", "eastAsia"):
                assert r_fonts.get(qn(f"w:{attr}")) == "宋体"

    once = docx_path.read_bytes()
    renderer._normalize_legal_notice_style(str(docx_path), context)
    assert docx_path.read_bytes() == once
