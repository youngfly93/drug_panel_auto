# ruff: noqa: E402
"""Independent lung588 engineering-contract regression tests."""

import hashlib
import io
import re
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile

import yaml
from docx import Document
from docx.enum.table import WD_ROW_HEIGHT_RULE
from docx.oxml.ns import qn
from docxtpl import DocxTemplate

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from reportgen.core.project_detector import ProjectDetector
from reportgen.core.report_generator import (
    apply_pdl1_display_fields,
    validate_panel_biomarker_contracts,
)
from reportgen.core.template_bridge_358 import (
    build_all_variants_for_template,
    build_variants_for_template,
    load_panel_config,
)
from reportgen.core.template_renderer import TemplateRenderer
from reportgen.models.excel_data import ExcelDataSource
from reportgen.models.report_data import ReportData
from reportgen.panels.loader import load_panel_package
from reportgen.panels.validation import validate_panel_package

from app.api.batch import _batch_generation_policy_error
from app.services.clinical_info_service import get_clinical_form_schema

PANEL_DIR = ROOT / "panels" / "lung_588_pdl1"
TEMPLATE = PANEL_DIR / "templates" / "lung_588_pdl1_golden_template_v0.docx"
SOURCE_TEMPLATE = (
    ROOT / "panels" / "lung_329_pdl1" / "templates" / "lung_329_pdl1_golden_template_v1.docx"
)
EXPECTED_GENE_SHA256 = "f9e6be05c954a4d3df97f031d453fe1f58ea0689290b11de3c173f4a0edf08f1"


def _gene_contract() -> list[str]:
    raw = yaml.safe_load(
        (PANEL_DIR / "rules" / "knowledge_coverage.yaml").read_text(encoding="utf-8")
    )
    return list(raw["reportable_genes"])


def _visible_template_text() -> str:
    document = Document(TEMPLATE)
    parts = [paragraph.text for paragraph in document.paragraphs]
    parts.extend(cell.text for table in document.tables for row in table.rows for cell in row.cells)
    return "\n".join(parts)


def _excel(tmp_path: Path, rows: list[dict]) -> ExcelDataSource:
    path = tmp_path / "synthetic-lung588.xlsx"
    path.write_bytes(b"synthetic")
    return ExcelDataSource(
        file_path=str(path),
        table_data={"Variations": rows},
        sheet_names=["Variations"],
    )


def test_lung588_package_is_independent_and_valid():
    package = load_panel_package("lung_588_pdl1", project_root=ROOT)
    report = validate_panel_package("lung_588_pdl1", project_root=ROOT)

    assert report.ok, report.to_dict()
    assert package.panel_id == "lung_588_pdl1"
    assert package.display_name == "肺癌588基因+PD-L1"
    assert package.raw["status"] == "draft"
    assert package.default_template.status == "draft"
    assert package.raw["part3_knowledge"]["enabled"] is False
    assert "cross-cancer" in package.raw["part3_knowledge"]["reason"]
    assert "肺癌专属知识当前未启用" in (package.raw["part3_knowledge"]["disabled_notice"])
    assert package.resolve_template_file() == TEMPLATE.resolve()


def test_lung588_gene_denominator_is_exact_and_ordered():
    genes = _gene_contract()

    assert len(genes) == 588
    assert len(set(genes)) == 588
    assert hashlib.sha256("\n".join(genes).encode("utf-8")).hexdigest() == EXPECTED_GENE_SHA256

    document = Document(TEMPLATE)
    tables = [
        table for table in document.tables if "Gene List for MLseq (n=588)" in table.cell(0, 0).text
    ]
    assert len(tables) == 1
    rendered = [
        cell.text.strip() for row in tables[0].rows[1:] for cell in row.cells if cell.text.strip()
    ]
    assert rendered == genes
    assert all(row.height_rule == WD_ROW_HEIGHT_RULE.EXACTLY for row in tables[0].rows[1:])
    assert max(row.height.cm for row in tables[0].rows[1:]) <= 0.72


def test_lung588_template_is_hardened_and_byte_reproducible(tmp_path):
    visible = _visible_template_text()
    assert "肺癌588基因+PD-L1检测项目" in visible
    assert "Gene List for MLseq (n=588)" in visible
    assert "肺癌329" not in visible
    assert "n=329" not in visible
    assert "__PART3_MARKER__" in visible
    assert "肺癌专属治疗知识和事件级药物规则当前未启用" in visible
    assert "本病例未提供可追溯的PD-L1免疫组化图像" in visible
    assert "4、因肿瘤存在较大的异质性" in visible
    assert "5、因肿瘤存在较大的异质性" not in visible

    template = DocxTemplate(str(TEMPLATE))
    context = {
        "patient_name": "SYNTHETIC_PATIENT",
        "sample_id": "SYNTHETIC_CASE",
        "pdl1_tps": "50",
        "pdl1_cps": "52",
        "pdl1_result": "阳性（高表达）",
        "variants_2_1": [],
        "targeted_drug_tips": [],
        "nccn_results": [],
        "immune_positive_results": [],
        "immune_negative_results": [],
        "immune_hyperprogression_results": [],
    }
    template.render(context)
    output = io.BytesIO()
    template.save(output)
    with ZipFile(output) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", "ignore")
    rendered = re.sub(r"<[^>]+>", "", xml)
    assert "SYNTHETIC_PATIENT" in rendered
    assert "阳性（高表达）" in rendered

    styled = tmp_path / "styled-lung588.docx"
    shutil.copy2(TEMPLATE, styled)
    TemplateRenderer(log_level="ERROR")._compact_gene_list_tables(
        str(styled),
        {
            "panel_style": {
                "gene_list_table": {
                    "row_height_cm": 0.72,
                    "header_row_height_cm": 0.88,
                    "row_height_rule": "exact",
                    "body_font_size": 10,
                }
            }
        },
    )
    styled_document = Document(styled)
    styled_table = next(
        table
        for table in styled_document.tables
        if "Gene List for MLseq (n=588)" in table.cell(0, 0).text
    )
    assert all(row.height_rule == WD_ROW_HEIGHT_RULE.EXACTLY for row in styled_table.rows)
    assert styled_table.rows[0].height.cm <= 0.89
    assert max(row.height.cm for row in styled_table.rows[1:]) <= 0.73


def test_lung588_template_does_not_reuse_scaffold_pdl1_image():
    def compact(value: object) -> str:
        return "".join(str(value or "").split())

    def pdl1_image_hash(document: Document) -> str:
        start = next(
            paragraph
            for paragraph in document.paragraphs
            if compact(paragraph.text) == compact("3.2 PD-L1表达检测结果")
        )
        end = next(
            paragraph
            for paragraph in document.paragraphs
            if compact(paragraph.text) == compact("3.3微卫星不稳定性（MSI）检测结果")
        )
        children = list(document.element.body.iterchildren())
        block = children[children.index(start._p) + 1 : children.index(end._p)]
        candidates = []
        for child in block:
            text = "".join(node.text or "" for node in child.iter(qn("w:t"))).strip()
            if text or not any(True for _ in child.iter(qn("w:drawing"))):
                continue
            candidates.extend(
                blip.get(qn("r:embed"))
                for blip in child.iter(qn("a:blip"))
                if blip.get(qn("r:embed"))
            )
        assert len(candidates) == 1
        return hashlib.sha256(document.part.related_parts[candidates[0]].blob).hexdigest()

    source_image_hash = pdl1_image_hash(Document(SOURCE_TEMPLATE))
    generated = Document(TEMPLATE)
    start = next(
        paragraph
        for paragraph in generated.paragraphs
        if compact(paragraph.text) == compact("3.2 PD-L1表达检测结果")
    )
    end = next(
        paragraph
        for paragraph in generated.paragraphs
        if compact(paragraph.text) == compact("3.3微卫星不稳定性（MSI）检测结果")
    )
    children = list(generated.element.body.iterchildren())
    block = children[children.index(start._p) + 1 : children.index(end._p)]
    assert not [
        child
        for child in block
        if not compact("".join(node.text or "" for node in child.iter(qn("w:t"))))
        and any(True for _ in child.iter(qn("w:drawing")))
    ]

    with ZipFile(TEMPLATE) as archive:
        generated_media_hashes = {
            hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
            if name.startswith("word/media/")
        }
    assert source_image_hash not in generated_media_hashes


def test_part3_disabled_policy_renders_notice_without_shared_knowledge(tmp_path):
    output = tmp_path / "part3-disabled.docx"
    document = Document()
    document.add_paragraph("__PART3_MARKER__")
    document.save(output)

    notice = "肺癌588第三部分尚未完成独立知识二审，当前工程草案不输出患者级解释。"
    TemplateRenderer(log_level="ERROR")._render_part3_formatted(
        str(output),
        {
            "part3_disabled_notice": notice,
            "part3_knowledge_status": "disabled",
            "total_variants_count": 8,
            "gene_knowledge_sections": [
                {"header": "SHOULD_NOT_RENDER", "intro": "SHOULD_NOT_RENDER"}
            ],
        },
    )

    rendered = "\n".join(paragraph.text for paragraph in Document(output).paragraphs)
    assert notice in rendered
    assert "SHOULD_NOT_RENDER" not in rendered
    assert "在本次检测范围内" not in rendered
    assert "__PART3_MARKER__" not in rendered


def test_lung588_project_detection_requires_trusted_product_text():
    detector = ProjectDetector(config_dir=str(ROOT / "config"), log_level="ERROR")

    detected = detector.detect("CASE-肺癌588基因+PD-L1.xlsx")
    unknown = detector.detect("CASE-LUNG-ONLY.xlsx")

    assert detected["detected"] is True
    assert detected["project_type"] == "lung_588_pdl1"
    assert unknown["detected"] is False
    assert unknown["project_type"] is None


def test_lung588_explicit_classes_drive_variant_filter(tmp_path):
    package = load_panel_package("lung_588_pdl1", project_root=ROOT)
    config = load_panel_config(
        base_path=str(ROOT),
        panel_package=package,
    )
    rows = [
        {
            "ExistIn552": "Ⅰ类",
            "Gene_Symbol": "BRAF",
            "cHGVS": "c.1799T>A",
            "pHGVS_S": "p.V600E",
            "Freq(%)": 40,
        },
        {
            "ExistIn552": "Ⅱ类",
            "Gene_Symbol": "TP53",
            "cHGVS": "c.734G>A",
            "pHGVS_S": "p.G245D",
            "Freq(%)": 30,
        },
        {
            "ExistIn552": "Ⅲ类",
            "Gene_Symbol": "ATM",
            "cHGVS": "c.1236-2A>T",
            "pHGVS_S": "*",
            "Freq(%)": 20,
        },
        {
            "ExistIn552": 1,
            "Gene_Symbol": "EGFR",
            "cHGVS": "c.2573T>G",
            "pHGVS_S": "p.L858R",
            "Freq(%)": 10,
        },
        {
            "ExistIn552": "Ⅱ类",
            "Gene_Symbol": "KRAS",
            "cHGVS": "not-a-coding-hgvs",
            "pHGVS_S": "p.G12D",
            "Freq(%)": 5,
        },
    ]
    excel = _excel(tmp_path, rows)

    main = build_variants_for_template(
        excel,
        filter_column="ExistIn552",
        panel_config=config,
    )
    all_rows = build_all_variants_for_template(
        excel,
        filter_column="ExistIn552",
        panel_config=config,
    )

    assert [row["gene"] for row in main] == ["BRAF", "TP53"]
    assert [row["gene"] for row in all_rows] == ["BRAF", "TP53", "ATM"]
    assert config.variant_filter_columns == ["ExistIn552"]
    assert config.variant_filter_values == ["Ⅰ类", "Ⅱ类", "Ⅲ类"]
    assert len(config.crc_important_genes) == 588
    assert config.nccn_result_rows == []
    assert config.immune_positive_genes == set()
    assert config.immune_negative_genes == set()
    assert config.immune_hyperprogression_genes == set()


def test_lung588_pdl1_form_is_project_scoped_and_required():
    lung = get_clinical_form_schema("lung_588_pdl1")
    crc = get_clinical_form_schema("crc_358_msi")
    lung_fields = {field.key: field for group in lung.groups for field in group.fields}
    crc_fields = {field.key for group in crc.groups for field in group.fields}

    assert {"pdl1_tps", "pdl1_cps", "pdl1_result"} <= set(lung_fields)
    assert all(lung_fields[key].required for key in ("pdl1_tps", "pdl1_cps", "pdl1_result"))
    assert lung_fields["pdl1_result"].ui.options == [
        "阳性（高表达）",
        "阳性（低表达）",
        "阴性",
    ]
    assert not {"pdl1_tps", "pdl1_cps", "pdl1_result"} & crc_fields

    treatment_context = {
        "lung_histology": [
            "非小细胞肺癌",
            "小细胞肺癌",
            "其他",
            "未明确",
        ],
        "disease_extent": [
            "可切除早期",
            "不可切除局部晚期",
            "转移性",
            "未明确",
        ],
        "prior_systemic_therapy": ["已接受", "未接受", "未明确"],
        "companion_diagnostic_status": [
            "已确认符合",
            "待确认",
            "不符合",
        ],
    }
    assert (
        next(group.label for group in lung.groups if group.id == "treatment_context")
        == "肺癌治疗适应证上下文"
    )
    for key, options in treatment_context.items():
        assert lung_fields[key].required is False
        assert lung_fields[key].ui.component == "select"
        assert lung_fields[key].ui.options == options
    assert not set(treatment_context) & crc_fields


def test_lung588_batch_is_blocked_until_per_case_pdl1_exists():
    error = _batch_generation_policy_error("lung_588_pdl1")

    assert error is not None
    assert "逐病例" in error
    assert "串用" in error
    assert _batch_generation_policy_error("crc_358_msi") is None


def test_lung588_pdl1_contract_fails_closed_on_missing_range_and_classification():
    package = load_panel_package("lung_588_pdl1", project_root=ROOT)
    contracts = package.input_contract["biomarkers"]

    missing = ReportData()
    assert {
        failure["field"] for failure in validate_panel_biomarker_contracts(missing, contracts)
    } == {"tmb_value", "msi_status", "pdl1_tps", "pdl1_cps", "pdl1_result"}

    invalid = ReportData()
    invalid.set_field("tmb_value", 7.5)
    invalid.set_field("msi_status", "MSS")
    invalid.set_field("pdl1_tps", 5)
    invalid.set_field("pdl1_cps", 101)
    invalid.set_field("pdl1_result", "阳性（高表达）")
    reasons = {
        (failure["field"], failure["reason"])
        for failure in validate_panel_biomarker_contracts(invalid, contracts)
    }
    assert ("pdl1_cps", "above_maximum") in reasons
    assert ("pdl1_result", "classification_inconsistent") in reasons

    negative = ReportData()
    negative.set_field("tmb_value", 0)
    negative.set_field("msi_status", "MSS")
    negative.set_field("pdl1_tps", 0)
    negative.set_field("pdl1_cps", 0)
    negative.set_field("pdl1_result", "阴性")
    assert validate_panel_biomarker_contracts(negative, contracts) == []

    negative.set_field("pdl1_cps", float("nan"))
    nan_failures = validate_panel_biomarker_contracts(negative, contracts)
    assert ("pdl1_cps", "not_numeric") in {
        (failure["field"], failure["reason"]) for failure in nan_failures
    }

    valid = ReportData()
    valid.set_field("tmb_value", 6.3)
    valid.set_field("msi_status", "MSS")
    valid.set_field("pdl1_tps", 5)
    valid.set_field("pdl1_cps", 6)
    valid.set_field("pdl1_result", "阳性（低表达）")
    assert validate_panel_biomarker_contracts(valid, contracts) == []
    apply_pdl1_display_fields(valid)
    interpretation = valid.get_field("pdl1_table_interpretation")
    assert "TPS 5%" in interpretation
    assert "CPS 6" in interpretation
    assert "推荐" not in interpretation
    assert "帕博利珠单抗" not in interpretation
