# ruff: noqa: E402, I001

import sys
from datetime import date
from pathlib import Path

import pytest
import yaml
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.config.loader import ConfigLoader
from reportgen.core.batch_runner import (
    BatchValidateOptions,
    _expected_tables_from_excel,
)
from reportgen.core.excel_reader import ExcelReader
from reportgen.core.field_provenance import (
    build_field_provenance_report,
    write_field_provenance_report,
)
from reportgen.core.field_mapper import FieldMapper
from reportgen.core.golden_case import (
    CRC_358_MSI_EXPECTATIONS,
    assert_golden_case_output,
    build_crc_358_msi_golden_excel,
)
from reportgen.core.project_detector import ProjectDetector
from reportgen.core.processors import ProcessorContext, run_processors
from reportgen.core.qa_report import build_docx_qa_report, write_docx_qa_report
from reportgen.core.report_generator import ReportGenerator
from reportgen.core.template_bridge_358 import (
    build_targeted_drug_brand_summary,
    build_tmb_summary,
    build_variants_for_template,
    enhance_report_data,
    load_panel_config,
)
from reportgen.core.template_renderer import TemplateRenderer
from reportgen.core.validation import validate_excel_data_common
from reportgen.models.excel_data import ExcelDataSource
from reportgen.models.report_data import ReportData
from reportgen.knowledge.gene_knowledge import GeneKnowledgeProvider


def _excel(
    tmp_path: Path,
    *,
    single_values=None,
    variations=None,
    tables=None,
) -> ExcelDataSource:
    path = tmp_path / "unknown.xlsx"
    path.write_bytes(b"placeholder")
    table_data = dict(tables or {})
    if variations is not None:
        table_data["Variations"] = variations
    return ExcelDataSource(
        file_path=str(path),
        single_values=single_values or {},
        table_data=table_data,
        sheet_names=list(table_data),
        metadata={},
    )


class _FakeDrugLookup:
    def _lookup_targeted_drugs_for_variant(
        self,
        gene,
        *,
        c_point,
        p_point,
        variant_level="",
        cancer_type="",
    ):
        if gene == "KRAS":
            return "Avutometinib+Defactinib（C）\n司美替尼（C）", "西妥昔单抗（A）", 100.0
        if gene == "ATM":
            return "奥拉帕利+帕博利珠单抗（C）", "--", 100.0
        return f"{gene}获益药（C）", "--", 100.0


class _FakeGeneKnowledgeProvider:
    def load(self, base_path=None):
        return None

    def build_all_gene_knowledge_sections(self, variants, cancer_type=""):
        return [
            {
                "header": f"{row.get('gene')}：{row.get('cHGVS')}",
                "has_drug": row.get("benefit_drugs") not in ("", "--", None),
                "intro": "基因简介",
                "mutation_desc": "位点说明",
                "mutation_analysis": "解析内容",
            }
            for row in variants
        ]

    def build_drug_analysis_sections(self, variants):
        return []

    def build_all_references_flat(self, variants, max_per_gene=5):
        return [f"{row.get('gene')} reference" for row in variants]

    def build_references(self, variants, max_per_gene=5):
        return {row.get("gene"): [f"{row.get('gene')} reference"] for row in variants}


def test_reviewed_override_does_not_create_absent_erbb2_tip(tmp_path):
    excel_data = _excel(tmp_path, variations=[])
    report_data = enhance_report_data(
        ReportData(),
        excel_data,
        base_path=str(ROOT),
    )

    tips = report_data.get_table("targeted_drug_tips")
    assert all(row.get("gene") != "ERBB2" for row in tips)
    assert report_data.get_field("msi_status") == "未检测"
    assert report_data.get_field("tmb_status") == "未检测"


def test_reviewed_override_applies_when_erbb2_variant_is_detected(tmp_path):
    excel_data = _excel(
        tmp_path,
        variations=[
            {
                "Gene_Symbol": "ERBB2",
                "Transcript": "NM_004448.4",
                "Chr": "17",
                "ExIn_ID": "EX17",
                "cHGVS": "c.1979G>A",
                "pHGVS_S": "p.G660D",
                "Freq(%)": 12.3,
                "ExistInsmall358": 1,
                "ExistIn552": 1,
                "CLNSIG": "Pathogenic",
            }
        ],
    )
    report_data = enhance_report_data(
        ReportData(),
        excel_data,
        base_path=str(ROOT),
    )

    tips = report_data.get_table("targeted_drug_tips")
    erbb2 = [row for row in tips if row.get("gene") == "ERBB2"]
    assert erbb2
    assert "曲妥珠单抗" in erbb2[0].get("benefit_drugs", "")


def test_nccn_mutation_rows_do_not_include_cnv_or_fusion(tmp_path):
    excel_data = _excel(
        tmp_path,
        variations=[
            {
                "Gene_Symbol": "ERBB2",
                "Transcript": "NM_004448.4",
                "Chr": "17",
                "ExIn_ID": "EX20",
                "cHGVS": "c.2324_2325ins12",
                "pHGVS_S": "p.Y772_A775dup",
                "Freq(%)": 12.3,
                "ExistInsmall358": 1,
                "ExistIn552": "Ⅱ类",
                "CLNSIG": "Pathogenic",
            }
        ],
        tables={
            "Cnv": [
                {"Gene": "ERBB2", "Status": "扩增"},
                {"Gene": "EGFR", "Status": "扩增"},
            ],
            "Fusion": [
                {"Gene1": "BICC1", "Gene2": "FGFR2"},
            ],
        },
    )
    report_data = enhance_report_data(
        ReportData(),
        excel_data,
        base_path=str(ROOT),
    )

    assert report_data.get_field("nccn_ERBB2_MUT") == (
        "c.2324_2325ins12，p.Y772_A775dup"
    )
    assert report_data.get_field("nccn_ERBB2_AMP") == "CNV:扩增"
    assert report_data.get_field("nccn_FGFR123_MUT") == "未检出"
    assert report_data.get_field("nccn_FGFR123_FUSION") == "融合:BICC1-FGFR2"
    assert report_data.get_field("imm_hyper_EGFR_AMP") == "CNV:扩增"


def test_field_mapper_adds_legacy_fusion_aliases(tmp_path):
    excel_data = _excel(
        tmp_path,
        tables={
            "Fusion": [
                {
                    "Gene1": "EML4",
                    "Chr1": "chr2",
                    "Pos1": 42491832,
                    "Gene2": "ALK",
                    "Chr2": "chr2",
                    "Pos2": 29446394,
                    "Sv_type": "fusion",
                }
            ]
        },
    )

    report_data = FieldMapper(
        config_dir=str(ROOT / "config"), log_level="ERROR"
    ).map(excel_data)

    rows = report_data.get_table("fusion")
    assert rows
    assert "#Est_Type" in rows[0]
    assert rows[0]["#Est_Type"] == "fusion"
    assert "Freq1" in rows[0]


def test_missing_clnsig_is_not_defaulted_to_pathogenic(tmp_path):
    excel_data = _excel(
        tmp_path,
        variations=[
            {
                "Gene_Symbol": "TP53",
                "Transcript": "NM_000546.6",
                "Chr": "17",
                "ExIn_ID": "EX8",
                "cHGVS": "c.817C>T",
                "pHGVS_S": "p.R273C",
                "Freq(%)": 33.0,
                "ExistInsmall358": 1,
                "ExistIn552": 1,
                "CLNSIG": "*",
            }
        ],
    )
    variants = build_variants_for_template(
        excel_data,
        filter_class_i_ii_only=False,
        important_genes_only=False,
        panel_config=load_panel_config(base_path=str(ROOT)),
    )

    assert variants
    assert variants[0]["clinical_significance"] == "临床意义未明"


def test_tmb_missing_is_explicit_not_low(tmp_path):
    summary = build_tmb_summary(_excel(tmp_path))
    assert summary["tmb_value"] == "未检测"
    assert summary["tmb_status"] == "未检测"
    assert summary["tmb_level_cn"] == "未检测"


def test_tmb_invalid_is_explicit_format_error(tmp_path):
    summary = build_tmb_summary(_excel(tmp_path, single_values={"TMB": "abc"}))
    assert summary["tmb_value"] == "未检测（格式错误）"
    assert summary["tmb_status"] == "未检测"
    assert summary["tmb_summary"] == "未检测（格式错误）"


def test_field_mapper_invalid_tmb_uses_same_format_error(tmp_path):
    report_data = FieldMapper(
        config_dir=str(ROOT / "config"), log_level="ERROR"
    ).map(_excel(tmp_path, single_values={"TMB": "abc"}))

    assert report_data.get_field("tmb_value") == "未检测（格式错误）"
    assert report_data.get_field("tmb_status") == "未检测"
    assert report_data.get_field("tmb_summary") == "未检测（格式错误）"


def test_field_mapper_valid_tmb_overrides_default_status(tmp_path):
    report_data = FieldMapper(
        config_dir=str(ROOT / "config"), log_level="ERROR"
    ).map(_excel(tmp_path, single_values={"TMB": 7.10499382716049, "MSI状态": "MSI-H"}))

    assert report_data.get_field("tmb_value") == "7.1"
    assert report_data.get_field("tmb") == "7.1 mutations/Mb"
    assert report_data.get_field("tmb_status") == "L"
    assert report_data.get_field("tmb_level_cn") == "低"
    assert "TMB-L" in report_data.get_field("tmb_summary")
    assert report_data.get_field("msi_status") == "MSI-H"
    assert "TMB-H的肿瘤" in report_data.get_field("immuno_tips")
    assert "#帕博利珠单抗" in report_data.get_field("immuno_tips")
    assert "TMB水平较低" in report_data.get_field("tmb_detail_sentence")
    assert "MSI-H" in report_data.get_field("msi_detail_sentence")
    assert "MSI-H" in report_data.get_field("msi_tips")


def test_field_mapper_dynamic_tmb_msi_narratives_match_mss_low_tmb(tmp_path):
    report_data = FieldMapper(
        config_dir=str(ROOT / "config"), log_level="ERROR"
    ).map(_excel(tmp_path, single_values={"TMB": 7.74681481481482, "MSI状态": "MSS"}))

    assert report_data.get_field("tmb_value") == "7.7"
    assert report_data.get_field("tmb_status") == "L"
    assert "7.7mutations/Mb" in report_data.get_field("tmb_detail_sentence")
    assert "TMB水平较低" in report_data.get_field("tmb_detail_sentence")
    assert "2020年6月，FDA批准帕博利珠单抗" in report_data.get_field(
        "tmb_detail_interpretation"
    )
    assert "帕博利珠单抗、纳武利尤单抗" in report_data.get_field("tmb_drug_note")
    assert "微卫星稳定（MSS）型" in report_data.get_field("msi_detail_sentence")
    assert "林奇综合征" in report_data.get_field("msi_detail_interpretation")
    assert "MSI-H的实体瘤通常具有免疫原性" in report_data.get_field("msi_tips")


def test_mixed_reviewed_class_labels_control_counts_and_drug_rows(tmp_path):
    variations = [
        {
            "ExistIn552": "Ⅱ类",
            "ExistInsmall358": 1,
            "Gene_Symbol": "TP53",
            "Transcript": "NM_000546.6",
            "Chr": "chr17",
            "ExIn_ID": "EX8",
            "cHGVS": "c.844C>T",
            "pHGVS_S": "p.R282W",
            "Function": "Missense",
            "Freq(%)": 67.29,
            "CLNSIG": "Pathogenic/Likely_pathogenic",
        },
        {
            "ExistIn552": "Ⅱ类",
            "ExistInsmall358": 1,
            "Gene_Symbol": "KRAS",
            "Transcript": "NM_004985.5",
            "Chr": "chr12",
            "ExIn_ID": "EX2",
            "cHGVS": "c.34G>A",
            "pHGVS_S": "p.G12S",
            "Function": "Missense",
            "Freq(%)": 46.29,
            "CLNSIG": "Pathogenic",
        },
        {
            "ExistIn552": "Ⅲ类",
            "ExistInsmall358": 1,
            "Gene_Symbol": "APC",
            "Transcript": "NM_000038.6",
            "Chr": "chr5",
            "ExIn_ID": "EX16E",
            "cHGVS": "c.4348C>T",
            "pHGVS_S": "p.R1450*",
            "Function": "Nonsense",
            "Freq(%)": 41.12,
            "CLNSIG": "Pathogenic",
        },
        {
            "ExistIn552": "Ⅲ类",
            "ExistInsmall358": 1,
            "Gene_Symbol": "APC",
            "Transcript": "NM_000038.6",
            "Chr": "chr5",
            "ExIn_ID": "EX16E",
            "cHGVS": "c.2387_2388del",
            "pHGVS_S": "p.Y796Wfs*2",
            "Function": "Frameshift",
            "Freq(%)": 37.52,
            "CLNSIG": "Pathogenic",
        },
        {
            "ExistIn552": "Ⅱ类",
            "ExistInsmall358": 1,
            "Gene_Symbol": "SETD2",
            "Transcript": "NM_014159.7",
            "Chr": "chr3",
            "ExIn_ID": "EX8",
            "cHGVS": "c.4930G>T",
            "pHGVS_S": "p.G1644*",
            "Function": "Nonsense",
            "Freq(%)": 22.15,
            "CLNSIG": "*",
        },
        {
            "ExistIn552": "Ⅲ类",
            "ExistInsmall358": 1,
            "Gene_Symbol": "EPHA2",
            "Transcript": "NM_004431.5",
            "Chr": "chr1",
            "ExIn_ID": "EX2",
            "cHGVS": "c.153+2T>C",
            "pHGVS_S": "*",
            "Function": "Splice-5",
            "Freq(%)": 3.33,
            "CLNSIG": "*",
        },
        {
            "ExistIn552": "Ⅲ类",
            "ExistInsmall358": 1,
            "Gene_Symbol": "FANCI",
            "Transcript": "NM_001113378.2",
            "Chr": "chr15",
            "ExIn_ID": "EX26",
            "cHGVS": "c.2879G>A",
            "pHGVS_S": "p.R960Q",
            "Function": "Missense",
            "Freq(%)": 2.18,
            "CLNSIG": "Uncertain_significance",
        },
        {
            "ExistIn552": "Ⅱ类",
            "ExistInsmall358": 1,
            "Gene_Symbol": "ATM",
            "Transcript": "NM_000051.4",
            "Chr": "chr11",
            "ExIn_ID": "EX47",
            "cHGVS": "c.6874C>T",
            "pHGVS_S": "p.Q2292*",
            "Function": "Nonsense",
            "Freq(%)": 0.53,
            "CLNSIG": "Pathogenic",
        },
        {
            "ExistIn552": 1,
            "ExistInsmall358": 1,
            "Gene_Symbol": "FBXW7",
            "Transcript": "NM_001349798.2",
            "Chr": "chr4",
            "ExIn_ID": "EX4",
            "cHGVS": "c.349_351del",
            "pHGVS_S": "p.E117del",
            "Function": "CDS-indel",
            "Freq(%)": 1.31,
            "CLNSIG": "Uncertain_significance",
        },
    ]

    report_data = enhance_report_data(
        ReportData(),
        _excel(
            tmp_path,
            single_values={"TMB": 6.463, "MSI状态": "MSS", "样本类型": "组织"},
            variations=variations,
        ),
        field_mapper=_FakeDrugLookup(),
        base_path=str(ROOT),
    )

    assert report_data.get_field("total_variants_count") == 8
    assert report_data.get_field("drug_related_count") == 4
    assert [row["gene"] for row in report_data.get_table("variants")] == [
        "TP53",
        "KRAS",
        "SETD2",
        "ATM",
    ]
    assert "FBXW7" not in {
        row.get("gene") for row in report_data.get_table("targeted_drug_tips")
    }
    assert report_data.get_field("immune_positive_count") == 3
    assert "KRAS：c.34G>A，p.G12S" in report_data.get_field(
        "immune_positive_result"
    )
    assert report_data.get_field("immune_negative_result") == "未检出"
    assert report_data.get_field("imm_neg_KRAS_STK11") == "未检出有害变异"
    assert "TP53：c.844C>T，p.R282W" in report_data.get_field("imm_pos_KRAS_TP53")
    assert "ATM：c.6874C>T，p.Q2292*" in report_data.get_field("imm_pos_DDR")
    assert "西妥昔单抗[爱必妥]" in report_data.get_field(
        "targeted_drug_brand_summary"
    )
    assert "FBXW7" not in report_data.get_field("targeted_drug_brand_summary")


def test_part3_variant_scope_can_follow_summary_variants(tmp_path):
    report_data = ReportData()
    report_data.set_field(
        "report_content",
        {
            "part3_variant_scope": "summary_variants",
            "part3_reference_variant_scope": "summary_variants",
        },
    )
    report_data = enhance_report_data(
        report_data,
        _excel(
            tmp_path,
            variations=[
                {
                    "ExistIn552": "Ⅱ类",
                    "ExistInsmall358": 1,
                    "Gene_Symbol": "TP53",
                    "Transcript": "NM_000546.6",
                    "Chr": "chr17",
                    "ExIn_ID": "EX8",
                    "cHGVS": "c.844C>T",
                    "pHGVS_S": "p.R282W",
                    "Function": "Missense",
                    "Freq(%)": 67.29,
                    "CLNSIG": "Pathogenic",
                },
                {
                    "ExistIn552": "Ⅲ类",
                    "ExistInsmall358": 1,
                    "Gene_Symbol": "APC",
                    "Transcript": "NM_000038.6",
                    "Chr": "chr5",
                    "ExIn_ID": "EX16E",
                    "cHGVS": "c.4348C>T",
                    "pHGVS_S": "p.R1450*",
                    "Function": "Nonsense",
                    "Freq(%)": 41.12,
                    "CLNSIG": "Pathogenic",
                },
            ],
        ),
        field_mapper=_FakeDrugLookup(),
        gene_knowledge_provider=_FakeGeneKnowledgeProvider(),
        base_path=str(ROOT),
    )

    headers = [row["header"] for row in report_data.get_table("gene_knowledge_sections")]
    assert headers == ["TP53：c.844C>T", "APC：c.4348C>T"]
    assert report_data.get_table("gene_references") == [
        "TP53 reference",
        "APC reference",
    ]


def test_targeted_drug_brand_summary_uses_final_drug_columns_only():
    summary = build_targeted_drug_brand_summary(
        [
            {
                "gene": "KRAS",
                "benefit_drugs": "Avutometinib+Defactinib（C）\n司美替尼（C）",
                "caution_drugs": "西妥昔单抗（A）\n帕尼单抗（A）",
            },
            {
                "gene": "ATM",
                "benefit_drugs": "奥拉帕利+帕博利珠单抗（C）",
                "caution_drugs": "--",
            },
        ],
        base_path=str(ROOT),
    )

    assert summary == (
        "Avutometinib[AVMAPKI]、Defactinib[FAKZYNJA]、奥拉帕利[利普卓]、"
        "帕博利珠单抗[可瑞达]、帕尼单抗[维克替比]、司美替尼[科赛优]、"
        "西妥昔单抗[爱必妥]。"
    )


def test_case2_fixture_tmb_msi_mapping_if_available():
    fixture = ROOT / "output/xlsx_for_win/case2_highTMB_MSIH_MLB0002.result.xlsx"
    if not fixture.exists():
        pytest.skip("case2 fixture is not available in this checkout")

    excel_data = ExcelReader(config_dir=str(ROOT / "config"), log_level="ERROR").read(
        str(fixture), include_tables=True
    )
    report_data = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR").map(
        excel_data
    )

    assert excel_data.single_values["TMB"] == pytest.approx(7.10499382716049)
    assert excel_data.single_values["MSI状态"] == "MSI-H"
    assert report_data.get_field("tmb_value") == "7.1"
    assert report_data.get_field("tmb_status") == "L"
    assert report_data.get_field("msi_status") == "MSI-H"


def test_field_mapper_updates_msi_status_cn_from_mss(tmp_path):
    report_data = FieldMapper(
        config_dir=str(ROOT / "config"), log_level="ERROR"
    ).map(_excel(tmp_path, single_values={"MSI状态": "MSS"}))

    assert report_data.get_field("msi_status") == "MSS"
    assert report_data.get_field("msi_status_cn") == "微卫星稳定型，MSS"


def test_missing_report_date_is_not_backfilled_to_today():
    report_data = ReportData()
    generator = ReportGenerator(config_dir=str(ROOT / "config"), log_level="ERROR")

    generator._mark_missing_report_date(report_data)

    assert report_data.get_field("report_date") == "未填写"
    assert "缺失必填字段: report_date" in report_data.validation_errors


def test_common_validation_warns_without_today_backfill(tmp_path):
    warnings = validate_excel_data_common(_excel(tmp_path), today=date(2026, 4, 19))

    report_date_warnings = [w for w in warnings if w.get("field") == "report_date"]
    assert report_date_warnings
    assert "不会自动回填今天" in report_date_warnings[0]["message"]


def test_detector_does_not_use_panel_column_numbers_as_crc_signal(tmp_path):
    excel_data = _excel(
        tmp_path,
        single_values={"TMB": 3.58},
        variations=[{"ExistInsmall358": 1, "Gene_Symbol": "TP53", "cHGVS": "c.1A>T"}],
    )
    detector = ProjectDetector(config_dir=str(ROOT / "config"), log_level="ERROR")
    result = detector.detect(str(Path(excel_data.file_path)), excel_data=excel_data)

    assert result["project_type"] != "crc_358_msi"


def test_detector_uses_trusted_filename_project_tokens(tmp_path):
    detector = ProjectDetector(config_dir=str(ROOT / "config"), log_level="ERROR")
    excel_data = _excel(tmp_path)

    path_301 = tmp_path / "_MLS2600000001_结直肠癌301基因+MSI_终版.xlsx"
    path_358 = tmp_path / "_MLS2600000002_结直肠癌358基因+MSI_终版.xlsx"
    path_301.write_bytes(b"placeholder")
    path_358.write_bytes(b"placeholder")

    assert detector.detect(str(path_301), excel_data=excel_data)["project_type"] == "crc_301_msi"
    assert detector.detect(str(path_358), excel_data=excel_data)["project_type"] == "crc_358_msi"


def test_crc_panel_enhancer_accepts_legacy_aliases():
    from reportgen.core.enhancer_registry import CRC358Enhancer, get_enhancer

    assert isinstance(get_enhancer("crc_301"), CRC358Enhancer)
    assert isinstance(get_enhancer("crc_358"), CRC358Enhancer)


def test_msi_percentage_label_conflict_is_warned(tmp_path):
    from app.services.reportgen_bridge import ReportGenBridge

    excel_data = _excel(
        tmp_path,
        single_values={"MSI状态": "MSS", "MSI百分比": 40.0},
    )
    bridge = ReportGenBridge(
        config_dir=str(ROOT / "config"),
        template_dir=str(ROOT / "templates"),
    )

    warnings = bridge.validate_excel_data(excel_data)
    assert any(w.get("field") == "msi_status" and w.get("level") == "warning" for w in warnings)


def test_batch_options_accept_forced_project_type():
    opts = BatchValidateOptions(
        inputs=["dummy.xlsx"],
        project_type="crc_358_msi",
        project_name="结直肠癌358基因+MSI",
    )
    assert opts.project_type == "crc_358_msi"


def test_hla_expected_table_matches_default_hidden_policy(tmp_path):
    excel_data = _excel(tmp_path, tables={"HLA": [{"Locus": "HLA-A", "Type1": "01:01"}]})

    assert _expected_tables_from_excel(excel_data, show_hla_table=False)["hla"] is False
    assert _expected_tables_from_excel(excel_data, show_hla_table=True)["hla"] is True


def test_consultation_phone_is_enabled_in_config():
    settings = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    report_content = settings.get("report_content") or {}
    assert report_content.get("consultation_phone") == "022-87190699"
    assert report_content.get("patient_letter", {}).get("after_greeting")
    assert report_content.get("part3_reading_blocks")
    assert report_content.get("tail_content", {}).get("paragraphs")


def test_configured_letter_and_tail_content_are_inserted(tmp_path):
    docx_path = tmp_path / "configured_content.docx"
    doc = Document()
    doc.add_paragraph("您好！")
    doc.add_paragraph("现代医学已经证明，肿瘤发生与基因异常有关。")
    doc.add_paragraph("致您的一封信")
    doc.add_paragraph("部分基因与药物对应关系，目前仅限于临床试验科学研究阶段。")
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._apply_report_content_fixes(
        str(docx_path),
        {
            "project_name": "结直肠癌358基因+MSI",
            "report_content": {
                "patient_letter": {
                    "after_greeting": ["项目：{project_name}"],
                    "after_modern_medicine": ["固定结尾段"],
                },
                "tail_content": {
                    "anchor_text": "部分基因与药物对应关系，目前仅限于临床试验科学研究阶段",
                    "marker_text": "尾页标题",
                    "paragraphs": [
                        {"text": "尾页标题", "bold": True, "page_break_before": True},
                        {
                            "text": "尾页正文",
                            "first_line_indent_cm": 0.7,
                            "line_spacing_multiple": 1.3,
                            "space_after_pt": 5,
                        },
                    ],
                },
            },
        },
    )

    doc = Document(docx_path)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "项目：结直肠癌358基因+MSI" in text
    assert "固定结尾段" in text
    assert "尾页标题" in text
    assert "尾页正文" in text
    tail_paragraph = next(p for p in doc.paragraphs if p.text == "尾页正文")
    ppr = tail_paragraph._p.get_or_add_pPr()
    assert ppr.find(qn("w:ind")).get(qn("w:firstLine")) == "396"
    spacing = ppr.find(qn("w:spacing"))
    assert spacing.get(qn("w:line")) == "312"
    assert spacing.get(qn("w:after")) == "100"


def test_configured_letter_content_is_inserted_inside_table_cells(tmp_path):
    docx_path = tmp_path / "configured_table_letter.docx"
    doc = Document()
    doc.add_paragraph("致您的一封信")
    table = doc.add_table(rows=2, cols=1)
    table.rows[0].cells[0].text = "您好！"
    table.rows[1].cells[0].text = "现代医学已经证明，肿瘤发生与基因异常有关。"
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._apply_report_content_fixes(
        str(docx_path),
        {
            "project_name": "结直肠癌358基因+MSI",
            "report_content": {
                "patient_letter": {
                    "after_greeting": ["项目：{project_name}"],
                    "after_modern_medicine": ["固定补充段一", "固定补充段二"],
                },
            },
        },
    )

    doc = Document(docx_path)
    text = "\n".join(
        [p.text for p in doc.paragraphs]
        + [cell.text for table in doc.tables for row in table.rows for cell in row.cells]
    )
    assert "项目：结直肠癌358基因+MSI" in text
    assert "固定补充段一" in text
    assert "固定补充段二" in text


def test_configured_tail_contact_block_uses_template_qr(tmp_path):
    from zipfile import ZipFile

    docx_path = tmp_path / "tail_contact.docx"
    doc = Document()
    doc.add_paragraph("部分基因与药物对应关系，目前仅限于临床试验科学研究阶段。")
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._apply_report_content_fixes(
        str(docx_path),
        {
            "report_content": {
                "tail_content": {
                    "anchor_text": "部分基因与药物对应关系，目前仅限于临床试验科学研究阶段",
                    "marker_text": "脉络医学检验简介",
                    "paragraphs": [
                        {"text": "脉络医学检验简介", "page_break_before": True},
                        {"text": "简介正文"},
                    ],
                    "contact_block": {
                        "enabled": True,
                        "lines": ["地址：测试地址", "电话：022-87190699"],
                        "qr_template_media": "word/media/image37.png",
                        "space_before_pt": 12,
                    },
                },
            },
        },
        str(ROOT / "templates/aligned_template_with_cnv_fusion_hla_FIXED.docx"),
    )

    doc = Document(docx_path)
    text = "\n".join(
        [p.text for p in doc.paragraphs]
        + [cell.text for table in doc.tables for row in table.rows for cell in row.cells]
    )
    assert "脉络医学检验简介" in text
    assert "地址：测试地址" in text
    assert "电话：022-87190699" in text
    assert len(doc.inline_shapes) == 1
    with ZipFile(docx_path) as zf:
        assert any(name.startswith("word/media/") for name in zf.namelist())


def test_excel_reader_extracts_lowercase_lz_sample_id_from_filename(tmp_path):
    path = tmp_path / "上传使用Excel表：lz000001.xlsx"
    path.write_bytes(b"placeholder")

    sample_id = ExcelReader(
        config_dir=str(ROOT / "config"),
        log_level="ERROR",
    )._extract_sample_id_from_filename(str(path))

    assert sample_id == "LZ000001"


def test_patient_info_can_be_loaded_from_external_runtime_path(monkeypatch, tmp_path):
    patient_info = tmp_path / "patient_info.yaml"
    patient_info.write_text(
        yaml.safe_dump(
            {
                "defaults": {"issuer": "签发人"},
                "project_info": {"project_name": "结直肠癌358基因+MSI"},
                "patients": {
                    "LZ000001": {
                        "patient_name": "测试患者",
                        "report_date": "2026-01-01",
                    }
                },
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("REPORTGEN_PATIENT_INFO_PATH", str(patient_info))

    info = ConfigLoader(config_dir=str(ROOT / "config"), log_level="ERROR").load_patient_info(
        "LZ000001"
    )

    assert info["patient_name"] == "测试患者"
    assert info["report_date"] == "2026-01-01"
    assert info["issuer"] == "签发人"
    assert info["project_name"] == "结直肠癌358基因+MSI"


def test_reviewed_atm_drug_override_matches_final_report_scope():
    mapper = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR")

    benefit, caution, score = mapper._lookup_targeted_drugs_for_variant(
        "ATM",
        c_point="c.6874C>T",
        p_point="p.Q2292*",
        variant_level="Ⅱ类",
        cancer_type="乙状结肠癌",
    )

    assert score == 100.0
    assert "奥拉帕利+帕博利珠单抗（C）" in benefit
    assert "Tuvusertib" not in benefit
    assert "Peposertib" not in benefit
    assert caution == "--"


def test_drug_analysis_is_limited_to_final_displayed_drugs():
    provider = GeneKnowledgeProvider({"enabled": False})
    provider._loaded = True
    provider._drug_full_cache = {
        "ATM": [
            {
                "type": "benefit",
                "drug": (
                    "奥拉帕利（Olaparib）、芦卡帕利（Rucaparib）、"
                    "Tuvusertib+Peposertib"
                ),
                "relation": "奥拉帕利相关说明。Tuvusertib联合治疗说明。",
                "clinical": "芦卡帕利相关说明。Peposertib与Tuvusertib研究说明。",
            }
        ]
    }

    sections = provider.build_drug_analysis_sections(
        [
            {
                "gene": "ATM",
                "cHGVS": "c.6874C>T",
                "pHGVS": "p.Q2292*",
                "benefit_drugs": "奥拉帕利（C）\n芦卡帕利（C）",
                "caution_drugs": "--",
            }
        ]
    )

    assert len(sections) == 1
    section = sections[0]
    assert "奥拉帕利" in section["drug_name"]
    assert "芦卡帕利" in section["drug_name"]
    assert "Tuvusertib" not in section["drug_name"]
    assert "Peposertib" not in section["clinical"]


def test_signature_placeholder_is_removed_without_image(tmp_path):
    docx_path = tmp_path / "signature.docx"
    doc = Document()
    doc.add_paragraph("签名：__SIG_IMG__")
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._render_signature_placeholder(str(docx_path), {})

    assert "__SIG_IMG__" not in "\n".join(p.text for p in Document(docx_path).paragraphs)


def test_signature_layout_moves_report_date_to_separate_line(tmp_path):
    from shutil import copyfile

    source = ROOT / "templates/aligned_template_with_cnv_fusion_hla_FIXED.docx"
    docx_path = tmp_path / "signature_layout.docx"
    copyfile(source, docx_path)

    renderer = TemplateRenderer(log_level="ERROR")
    renderer._render_signature_placeholder(str(docx_path), {})
    renderer._apply_report_content_fixes(str(docx_path), {"report_date": "2026-04-26"})
    renderer._normalize_signature_layout(str(docx_path), {"report_date": "2026-04-26"})

    paragraphs = [p.text.strip() for p in Document(docx_path).paragraphs if p.text.strip()]
    signature_lines = [p for p in paragraphs if p.startswith("检测者：")]
    assert signature_lines
    assert all("报告日期" not in p for p in signature_lines)
    assert "报告日期：2026.04.26" in paragraphs


def test_template_renderer_removes_explicit_underlines(tmp_path):
    from zipfile import ZipFile

    docx_path = tmp_path / "underlines.docx"
    doc = Document()
    doc.add_paragraph().add_run("姓名").font.underline = True
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).paragraphs[0].add_run("TP53").font.underline = True
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._remove_template_underlines(str(docx_path))

    rendered = Document(docx_path)
    assert rendered.paragraphs[0].runs[0].font.underline is None
    assert rendered.tables[0].cell(0, 0).paragraphs[0].runs[0].font.underline is None
    with ZipFile(docx_path) as zf:
        assert b"<w:u" not in zf.read("word/document.xml")


def test_detection_content_fill_underline_is_restored(tmp_path):
    docx_path = tmp_path / "detection_content.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("对委托人").font.underline = True
    paragraph.add_run("    组织    ").font.underline = True
    paragraph.add_run("的 DNA 样本微卫星不稳定性（MSI）以及与肿瘤密切相关的358个基因进行检测：").font.underline = True
    doc.save(docx_path)

    renderer = TemplateRenderer(log_level="ERROR")
    renderer._remove_template_underlines(str(docx_path))
    renderer._restore_detection_content_underlines(str(docx_path))

    runs = Document(docx_path).paragraphs[0].runs
    assert runs[0].font.underline is None
    assert runs[1].font.underline is True
    assert runs[2].font.underline is None


def test_variant_summary_table_restores_reviewed_link_style(tmp_path):
    docx_path = tmp_path / "variant_summary.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=4)
    headers = ["基因", "突变位点", "潜在获益靶向药物\n（证据等级）", "可能耐药或慎重药物\n（证据等级）"]
    values = ["KRAS", "c.34G>A,\np.G12S", "司美替尼（C）", "西妥昔单抗（A）"]
    for idx, value in enumerate(headers):
        table.rows[0].cells[idx].text = value
    for idx, value in enumerate(values):
        table.rows[1].cells[idx].text = value
    doc.save(docx_path)

    renderer = TemplateRenderer(log_level="ERROR")
    renderer._remove_template_underlines(str(docx_path))
    renderer._restore_variant_summary_table_style(str(docx_path))

    doc = Document(docx_path)
    table = doc.tables[0]
    gene_run = table.rows[1].cells[0].paragraphs[0].runs[0]
    site_run = table.rows[1].cells[1].paragraphs[0].runs[0]
    drug_run = table.rows[1].cells[2].paragraphs[0].runs[0]
    resist_run = table.rows[1].cells[3].paragraphs[0].runs[0]

    assert gene_run.font.underline is True
    assert str(gene_run.font.color.rgb) == "0000FF"
    assert site_run.font.underline is False
    assert str(site_run.font.color.rgb) == "000000"
    assert drug_run.font.underline is True
    assert str(drug_run.font.color.rgb) == "0000FF"
    assert resist_run.font.underline is True
    assert str(resist_run.font.color.rgb) == "0000FF"


def test_variant_detail_table_restores_reviewed_template_style(tmp_path):
    docx_path = tmp_path / "variant_detail.docx"
    doc = Document()
    table = doc.add_table(rows=3, cols=9)
    row0 = [
        "基因名称",
        "基因突变信息",
        "基因突变信息",
        "基因突变信息",
        "基因突变信息",
        "基因突变信息",
        "基因突变信息",
        "靶向药物信息",
        "靶向药物信息",
    ]
    row1 = [
        "基因名称",
        "转录本号",
        "染色体",
        "外显子",
        "位点",
        "突变\n类型",
        "频率\n(%)",
        "潜在获益靶向药物\n（证据等级）",
        "可能耐药或\n慎重药物\n（证据等级）",
    ]
    row2 = [
        "KRAS",
        "NM_004985.5",
        "12",
        "2",
        "c.34G>A,\np.G12S",
        "点突变",
        "46.29",
        "司美替尼（C）",
        "西妥昔单抗（A）",
    ]
    for row, values in zip(table.rows, [row0, row1, row2]):
        for idx, value in enumerate(values):
            row.cells[idx].text = value
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._restore_variant_detail_table_style(str(docx_path))

    doc = Document(docx_path)
    table = doc.tables[0]
    header_run = table.rows[0].cells[0].paragraphs[0].runs[0]
    gene_run = table.rows[2].cells[0].paragraphs[0].runs[0]
    site_run = table.rows[2].cells[4].paragraphs[0].runs[0]
    drug_run = table.rows[2].cells[7].paragraphs[0].runs[0]

    assert header_run.font.name == "微软雅黑"
    assert header_run.font.size.pt == 9
    assert header_run.font.bold is True
    assert str(header_run.font.color.rgb) == "F9FBFA"
    assert gene_run.font.underline is True
    assert str(gene_run.font.color.rgb) == "0000FF"
    assert site_run.font.underline is False
    assert str(site_run.font.color.rgb) == "000000"
    assert drug_run.font.underline is True
    assert str(drug_run.font.color.rgb) == "0000FF"
    assert table.rows[2].cells[7].paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.CENTER


def test_biomarker_table_restores_template_typography(tmp_path):
    docx_path = tmp_path / "biomarker.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=3)
    table.rows[0].cells[0].text = "TMB/MSI/其它生物标志物检测结果"
    table.rows[0].cells[1].text = "TMB/MSI/其它生物标志物检测结果"
    table.rows[0].cells[2].text = "用药提示"
    table.rows[1].cells[0].text = "肿瘤突变负荷（TMB）"
    table.rows[1].cells[1].text = "6.5 mutations/Mb，TMB-L"
    table.rows[1].cells[2].text = "多项临床研究表明，TMB-H的肿瘤对免疫检查点抑制剂有更强的免疫应答效果"
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._restore_biomarker_table_style(str(docx_path))

    doc = Document(docx_path)
    table = doc.tables[0]
    header_run = table.rows[0].cells[2].paragraphs[0].runs[0]
    body_run = table.rows[1].cells[2].paragraphs[0].runs[0]

    assert header_run.font.name == "微软雅黑"
    assert header_run.font.size.pt == 10
    assert header_run.font.bold is True
    assert str(header_run.font.color.rgb) == "F9FBFA"
    assert body_run.font.name == "微软雅黑"
    assert body_run.font.size.pt == 9
    assert body_run.font.bold is False
    assert body_run.font.underline is False
    assert str(body_run.font.color.rgb) == "000000"
    assert table.rows[1].cells[2].paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.CENTER


def test_report_content_fixes_remove_tmb_h_only_notes_when_tmb_low(tmp_path):
    docx_path = tmp_path / "immune_notes.docx"
    doc = Document()
    doc.add_paragraph("2.上表涉及的已上市的药物名称及对应的商品名称：旧商品名。")
    doc.add_paragraph(
        "#帕博利珠单抗均已获FDA和/或NMPA批准用于治疗结直肠癌。"
        "并且，FDA 已批准帕博利珠单抗用于治疗 TMB-H 的不可切除或转移性的成人和儿童实体瘤。"
    )
    doc.add_paragraph(
        "目前已知的免疫治疗生物标志物包括TMB、MSI、PD-L1表达、"
        "免疫疗效正相关/负相关/超进展基因等。值得注意的是，"
        "TMB、MSI、PD-L1表达预测生物标志物是相对独立的预测指标。"
    )
    doc.add_paragraph("4. 上表涉及的已上市的药物名称及对应的商品名称：免疫药品清单。")
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._apply_report_content_fixes(
        str(docx_path),
        {
            "tmb_status": "L",
            "msi_status": "MSS",
            "targeted_drug_brand_summary": "西妥昔单抗[爱必妥]。",
        },
    )

    text = "\n".join(p.text for p in Document(docx_path).paragraphs)
    assert "TMB-H 的不可切除或转移性的成人和儿童实体瘤" not in text
    assert "相对独立" not in text
    assert "FDA和/或NMPA批准用于治疗结直肠癌" in text
    assert "西妥昔单抗[爱必妥]" in text


def test_report_content_fixes_keep_conflict_note_for_tmb_high_mss(tmp_path):
    docx_path = tmp_path / "immune_notes_high.docx"
    doc = Document()
    doc.add_paragraph("2.上表涉及的已上市的药物名称及对应的商品名称：旧商品名。")
    doc.add_paragraph(
        "并且，FDA 已批准帕博利珠单抗用于治疗 TMB-H 的不可切除或转移性的成人和儿童实体瘤。"
    )
    doc.add_paragraph(
        "目前已知的免疫治疗生物标志物包括TMB、MSI、PD-L1表达。"
        "值得注意的是，TMB、MSI、PD-L1表达预测生物标志物是相对独立的预测指标。"
    )
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._apply_report_content_fixes(
        str(docx_path),
        {
            "tmb_status": "H",
            "msi_status": "MSS",
            "targeted_drug_brand_summary": "帕博利珠单抗[可瑞达]。",
        },
    )

    text = "\n".join(p.text for p in Document(docx_path).paragraphs)
    assert "TMB-H 的不可切除或转移性的成人和儿童实体瘤" in text
    assert "相对独立" in text


def test_multiline_bullet_placeholder_splits_into_real_bullets(tmp_path):
    docx_path = tmp_path / "multiline_bullets.docx"
    doc = Document()

    def add_bullet(text: str = ""):
        paragraph = doc.add_paragraph(text)
        ppr = paragraph._p.get_or_add_pPr()
        num_pr = OxmlElement("w:numPr")
        ilvl = OxmlElement("w:ilvl")
        ilvl.set(qn("w:val"), "0")
        num_id = OxmlElement("w:numId")
        num_id.set(qn("w:val"), "1")
        num_pr.append(ilvl)
        num_pr.append(num_id)
        ppr.append(num_pr)
        return paragraph

    add_bullet("第一条\n第二条\n第三条")
    add_bullet()
    add_bullet()
    add_bullet()
    doc.add_paragraph("注：")
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._normalize_multiline_bullet_paragraphs(
        str(docx_path)
    )

    rendered = Document(docx_path)
    bullets = [
        p.text
        for p in rendered.paragraphs
        if p._p.pPr is not None and p._p.pPr.numPr is not None
    ]
    assert bullets == ["第一条", "第二条", "第三条"]


def test_empty_numbered_paragraphs_are_removed(tmp_path):
    docx_path = tmp_path / "empty_numbered.docx"
    doc = Document()

    def add_bullet(text: str = ""):
        paragraph = doc.add_paragraph(text)
        ppr = paragraph._p.get_or_add_pPr()
        num_pr = OxmlElement("w:numPr")
        ilvl = OxmlElement("w:ilvl")
        ilvl.set(qn("w:val"), "0")
        num_id = OxmlElement("w:numId")
        num_id.set(qn("w:val"), "1")
        num_pr.append(ilvl)
        num_pr.append(num_id)
        ppr.append(num_pr)
        return paragraph

    add_bullet("保留")
    add_bullet("")
    doc.add_paragraph("")
    add_bullet("也保留")
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._remove_empty_numbered_paragraphs(str(docx_path))

    rendered = Document(docx_path)
    bullets = [
        p.text
        for p in rendered.paragraphs
        if p._p.pPr is not None and p._p.pPr.numPr is not None
    ]
    assert bullets == ["保留", "也保留"]
    assert any(not p.text for p in rendered.paragraphs)


def test_template_tmb_msi_patient_narratives_are_dynamic():
    template = ROOT / "templates/aligned_template_with_cnv_fusion_hla_FIXED.docx"
    doc = Document(template)
    texts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                texts.append(cell.text)
    text = "\n".join(texts)

    assert "13.5mutations/Mb" not in text
    assert "该肿瘤样本为 微卫星稳定（MSS）型" not in text
    assert "MSI-H的实体瘤通常具有免疫原性" not in text
    for token in [
        "{{ tmb_detail_sentence }}",
        "{{ tmb_detail_interpretation }}",
        "{{ tmb_drug_note }}",
        "{{ msi_detail_sentence }}",
        "{{ msi_detail_interpretation }}",
        "{{ msi_tips }}",
    ]:
        assert token in text


def test_patient_letter_is_native_docx_text_not_legacy_textbox():
    from zipfile import ZipFile
    import xml.etree.ElementTree as ET

    template = ROOT / "templates/aligned_template_with_cnv_fusion_hla_FIXED.docx"
    doc = Document(template)
    text_parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text_parts.append(cell.text)
    text = "\n".join(text_parts)

    assert "致您的一封信" in text
    assert "尊敬的 {{ patient_name }} {{ patient_salutation }}：" in text
    assert "现代医学已经证明" in text

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(template) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    textbox_text = "\n".join(
        "".join(t.text or "" for t in textbox.findall(".//w:t", ns))
        for textbox in root.findall(".//w:txbxContent", ns)
    )

    assert "现代医学已经证明" not in textbox_text
    assert "尊敬的" not in textbox_text


def test_patient_letter_body_block_is_not_pushed_to_right():
    from zipfile import ZipFile
    import xml.etree.ElementTree as ET

    template = ROOT / "templates/aligned_template_with_cnv_fusion_hla_FIXED.docx"
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(template) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))

    matching_tables = []
    for table in root.findall(".//w:tbl", ns):
        text = "".join(t.text or "" for t in table.findall(".//w:t", ns))
        if "现代医学已经证明" in text:
            matching_tables.append(table)

    assert len(matching_tables) == 1
    widths = [
        int(tc_w.get(f"{{{ns['w']}}}w") or "0")
        for tc_w in matching_tables[0].findall(".//w:tcPr/w:tcW", ns)[:2]
    ]
    grid_widths = [
        int(grid_col.get(f"{{{ns['w']}}}w") or "0")
        for grid_col in matching_tables[0].findall("./w:tblGrid/w:gridCol", ns)[:2]
    ]
    assert widths[0] <= 800
    assert widths[1] >= 8000
    assert grid_widths[0] <= 800
    assert grid_widths[1] >= 8000


def test_patient_letter_salutation_follows_gender():
    generator = ReportGenerator(config_dir=str(ROOT / "config"), log_level="ERROR")
    report_data = ReportData()

    report_data.set_field("gender", "女")
    generator._set_patient_salutation(report_data)
    assert report_data.get_field("patient_salutation") == "女士"

    report_data.set_field("gender", "男")
    generator._set_patient_salutation(report_data)
    assert report_data.get_field("patient_salutation") == "先生"


def test_clinical_diagnosis_populates_basic_info_display_only():
    generator = ReportGenerator(config_dir=str(ROOT / "config"), log_level="ERROR")
    report_data = ReportData()
    report_data.set_field("cancer_type", "-")
    report_data.set_field("clinical_diagnosis", "乙状结肠癌")

    generator._apply_clinical_diagnosis_for_display(report_data)

    assert report_data.get_field("cancer_type") == "乙状结肠癌"


def test_toc_decoration_line_is_moved_left_and_up(tmp_path):
    from shutil import copyfile
    from zipfile import ZipFile
    import xml.etree.ElementTree as ET

    source = ROOT / "templates/aligned_template_with_cnv_fusion_hla_FIXED.docx"
    docx_path = tmp_path / "toc_layout.docx"
    copyfile(source, docx_path)

    TemplateRenderer(log_level="ERROR")._normalize_toc_decoration_layout(str(docx_path))

    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ns_wp = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
    w_p = f"{{{ns_w}}}p"
    w_t = f"{{{ns_w}}}t"
    wp_anchor = f"{{{ns_wp}}}anchor"
    wp_doc_pr = f"{{{ns_wp}}}docPr"
    wp_extent = f"{{{ns_wp}}}extent"
    wp_position_h = f"{{{ns_wp}}}positionH"
    wp_position_v = f"{{{ns_wp}}}positionV"
    wp_pos_offset = f"{{{ns_wp}}}posOffset"

    with ZipFile(docx_path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))

    line_offsets = []
    circle_offsets = []
    for para in root.iter(w_p):
        text = "".join(t.text or "" for t in para.iter(w_t)).replace(" ", "")
        if "目录" not in text:
            continue
        for anchor in para.iter(wp_anchor):
            doc_pr = anchor.find(wp_doc_pr)
            extent = anchor.find(wp_extent)
            if doc_pr is None or extent is None:
                continue
            name = doc_pr.get("name", "")
            cx = int(extent.get("cx") or "0")
            cy = int(extent.get("cy") or "0")
            pos_h = anchor.find(wp_position_h)
            pos_v = anchor.find(wp_position_v)
            if pos_h is None or pos_v is None:
                continue
            x = int((pos_h.find(wp_pos_offset).text or "0"))
            y = int((pos_v.find(wp_pos_offset).text or "0"))
            if "直接连接符" in name and cx <= 100000 and cy >= 2000000:
                line_offsets.append((x, y))
            elif "椭圆" in name and cx <= 200000 and cy <= 200000:
                circle_offsets.append((x, y))

    assert line_offsets
    assert circle_offsets
    assert all(x == 127000 and y == 533400 for x, y in line_offsets)
    assert all(x == 92710 and y == 457200 for x, y in circle_offsets)


def test_section_layouts_are_normalized(tmp_path):
    docx_path = tmp_path / "sections.docx"
    doc = Document()
    doc.add_paragraph("第三部分：基因变异及相应靶向/免疫药物解析")
    doc.sections[0].right_margin = Cm(2.0)
    second = doc.add_section(WD_SECTION.NEW_PAGE)
    second.right_margin = Cm(3.5)
    doc.add_paragraph("第四部分：附录")
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._normalize_final_section_layout(str(docx_path))

    margins = {round(section.right_margin.cm, 2) for section in Document(docx_path).sections}
    assert margins == {2.0}


def test_appendix_sections_reuse_reviewed_body_header(tmp_path):
    docx_path = tmp_path / "headers.docx"
    doc = Document()
    doc.add_paragraph("致您的一封信")
    body_section = doc.add_section(WD_SECTION.NEW_PAGE)
    body_section.header.is_linked_to_previous = False
    body_section.header.paragraphs[0].text = "姓名：测试患者              科技服务人类健康"
    doc.add_paragraph("第三部分：基因变异及相应靶向/免疫药物解析")
    appendix_section = doc.add_section(WD_SECTION.NEW_PAGE)
    appendix_section.header.is_linked_to_previous = False
    appendix_section.header.paragraphs[0].text = ""
    appendix_section.different_first_page_header_footer = True
    doc.add_paragraph("Gene List for MLseq (n=358)")
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._restore_reviewed_body_headers(str(docx_path))

    doc = Document(docx_path)
    appendix = doc.sections[-1]
    assert not appendix.different_first_page_header_footer
    assert "科技服务人类健康" in "\n".join(
        p.text for p in appendix.header.paragraphs
    )
    p_bdr = appendix.footer.paragraphs[0]._p.get_or_add_pPr().find(qn("w:pBdr"))
    assert p_bdr is not None
    assert p_bdr.find(qn("w:top")).get(qn("w:val")) == "single"


def test_gene_list_table_matches_reviewed_layout(tmp_path):
    docx_path = tmp_path / "gene_list.docx"
    doc = Document()
    table = doc.add_table(rows=3, cols=2)
    table.rows[0].cells[0].text = "Gene List for MLseq (n=358)"
    table.rows[1].cells[0].text = "ABL1"
    table.rows[1].cells[1].text = "ABL2"
    table.rows[2].cells[0].text = "ZRSR2"
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._compact_gene_list_tables(str(docx_path))

    doc = Document(docx_path)
    body_run = doc.tables[0].rows[1].cells[0].paragraphs[0].runs[0]
    assert body_run.font.size.pt == 10.5
    assert body_run.font.underline is False


def test_quality_control_table_disables_inherited_underlines(tmp_path):
    docx_path = tmp_path / "qc.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "质控项"
    table.rows[0].cells[1].text = "质控结果"
    table.rows[1].cells[0].text = "核酸提取与质量控制"
    table.rows[1].cells[1].text = "合格"
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._normalize_quality_control_tables(str(docx_path))

    doc = Document(docx_path)
    body_run = doc.tables[0].rows[1].cells[0].paragraphs[0].runs[0]
    assert body_run.font.underline is False


def test_macos_field_refresh_does_not_use_word_by_default(monkeypatch, tmp_path):
    renderer = TemplateRenderer(log_level="ERROR")
    docx_path = tmp_path / "refresh.docx"
    docx_path.write_bytes(b"placeholder")
    calls = []

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv("REPORTGEN_REFRESH_WITH_WORD", raising=False)
    monkeypatch.setattr(renderer, "_document_contains_toc", lambda path: True)
    monkeypatch.setattr(renderer, "_refresh_fields_with_word_macos", lambda path: calls.append("word"))
    monkeypatch.setattr(renderer, "_refresh_fields_with_libreoffice", lambda path: calls.append("libreoffice"))

    renderer._refresh_fields_with_native_engine(str(docx_path))

    assert calls == ["libreoffice"]


def test_macos_field_refresh_can_opt_into_word(monkeypatch, tmp_path):
    renderer = TemplateRenderer(log_level="ERROR")
    docx_path = tmp_path / "refresh.docx"
    docx_path.write_bytes(b"placeholder")
    calls = []

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("REPORTGEN_REFRESH_WITH_WORD", "1")
    monkeypatch.setattr(renderer, "_document_contains_toc", lambda path: True)
    monkeypatch.setattr(renderer, "_refresh_fields_with_word_macos", lambda path: calls.append("word"))
    monkeypatch.setattr(renderer, "_refresh_fields_with_libreoffice", lambda path: calls.append("libreoffice"))

    renderer._refresh_fields_with_native_engine(str(docx_path))

    assert calls == ["word"]


def test_variant_table_layout_optimizer_keeps_reviewed_nine_column_template(tmp_path):
    docx_path = tmp_path / "variant_table.docx"
    doc = Document()
    table = doc.add_table(rows=3, cols=9)
    headers = [
        "基因名称", "基因突变信息", "基因突变信息", "基因突变信息",
        "基因突变信息", "基因突变信息", "基因突变信息",
        "靶向药物信息", "靶向药物信息",
    ]
    for idx, text in enumerate(headers):
        table.rows[0].cells[idx].text = text
    for idx in range(9):
        table.rows[1].cells[idx].text = "测试内容"
    values = [
        "TP53", "NM_000546.6", "17", "8", "c.817C>T,\np.R273C",
        "点突变", "76.12", "AZD1775（C）\nAlisertib（C）", "--",
    ]
    for idx, text in enumerate(values):
        table.rows[2].cells[idx].text = text
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._optimize_variant_table_layout(str(docx_path))

    doc = Document(docx_path)
    table = doc.tables[0]
    assert len(table.columns) == 9
    assert table.rows[0].cells[0].text == "基因名称"
    assert table.rows[2].cells[1].text == "NM_000546.6"
    assert table.rows[2].cells[6].text == "76.12"


def test_real_no_variants_sample_regression_if_available():
    sample = (
        ROOT
        / "storage/uploads/2026-03-27/0ae95efb-606b-42f0-80d7-e21283c6415c"
        / "case3_no_variants_MLB0003.result.xlsx"
    )
    if not sample.exists():
        pytest.skip("real no-variants sample is not available in this checkout")

    excel_data = ExcelReader(
        config_dir=str(ROOT / "config"), log_level="ERROR"
    ).read(str(sample), include_tables=True)
    report_data = enhance_report_data(
        ReportData(),
        excel_data,
        base_path=str(ROOT),
    )

    assert report_data.get_field("total_variants_count") == 0
    assert report_data.get_table("variants") == []
    assert not any(
        (row.get("gene") or "").upper() == "ERBB2"
        for row in report_data.get_table("targeted_drug_tips")
    )


def test_qa_report_passes_basic_clean_docx(tmp_path):
    docx_path = tmp_path / "clean.docx"
    doc = Document()
    doc.add_paragraph("已生成报告")
    doc.save(docx_path)

    qa = build_docx_qa_report(output_file=str(docx_path))

    assert qa["status"] == "PASS"
    assert qa["checks"]["docx_openable"]["status"] == "PASS"
    assert qa["checks"]["unrendered_placeholders"]["count"] == 0


def test_field_provenance_masks_sensitive_values_and_records_sources(tmp_path):
    docx_path = tmp_path / "report.docx"
    doc = Document()
    doc.add_paragraph("报告")
    doc.save(docx_path)
    excel_data = _excel(
        tmp_path,
        single_values={
            "患者姓名": "表单姓名",
            "TMB": "6.5",
            "MSI状态": "MSS",
        },
    )
    excel_data.metadata["sample_id_from_filename"] = "ZZ999999"
    excel_data.metadata["field_source_overrides"] = {
        "patient_name": {
            "source": "form",
            "source_key": "患者姓名",
            "source_detail": "web_clinical_form",
        }
    }
    report_data = ReportData()
    report_data.set_field("patient_name", "表单姓名")
    report_data.set_field("sample_id", "ZZ999999")
    report_data.set_field("tmb_value", "6.5")
    report_data.set_field("tmb_status", "L")
    report_data.set_field("msi_status", "MSS")

    provenance = build_field_provenance_report(
        output_file=str(docx_path),
        report_data=report_data,
        excel_data=excel_data,
        config_loader=ConfigLoader(config_dir=str(ROOT / "config"), log_level="ERROR"),
        project_type="crc_358_msi",
        project_name="结直肠癌358基因+MSI",
    )

    fields = provenance["fields"]
    assert fields["patient_name"]["source"] == "form"
    assert fields["patient_name"]["value"] != "表单姓名"
    assert fields["sample_id"]["source"] == "filename"
    assert fields["sample_id"]["value"] != "ZZ999999"
    assert fields["tmb_value"]["source"] == "excel"
    assert fields["tmb_status"]["source"] == "rule"
    assert fields["msi_status"]["source"] == "excel"


def test_write_field_provenance_report_creates_sidecar_json(tmp_path):
    docx_path = tmp_path / "report.docx"
    doc = Document()
    doc.add_paragraph("报告")
    doc.save(docx_path)
    payload = {"schema_version": "1.0", "fields": {}}

    out_path = Path(write_field_provenance_report(payload, str(docx_path)))

    assert out_path.name == "report.field_provenance.json"
    assert out_path.exists()


def test_qa_report_references_field_provenance(tmp_path):
    docx_path = tmp_path / "clean.docx"
    doc = Document()
    doc.add_paragraph("已生成报告")
    doc.save(docx_path)
    provenance = {
        "fields": {
            "sample_id": {"source": "filename"},
            "patient_name": {"source": "form"},
        }
    }

    qa = build_docx_qa_report(
        output_file=str(docx_path),
        field_provenance=provenance,
        field_provenance_file=str(docx_path.with_suffix(".field_provenance.json")),
    )

    assert qa["status"] == "PASS"
    assert qa["field_provenance_file"].endswith(".field_provenance.json")
    assert qa["checks"]["field_provenance"]["key_field_sources"] == {
        "sample_id": "filename",
        "patient_name": "form",
    }


def test_processor_runner_records_skip_success_and_error():
    class _Logger:
        def __init__(self):
            self.warnings = []

        def warning(self, message, **kwargs):
            self.warnings.append((message, kwargs))

    class _Processor:
        def __init__(self, name, status):
            self.name = name
            self.status = status
            self.warning_message = f"{name} failed"

        def enabled(self, _ctx):
            return self.status != "skip"

        def run(self, _ctx):
            if self.status == "error":
                raise RuntimeError("boom")

    logger = _Logger()
    ctx = ProcessorContext(
        renderer=object(),
        output_path="out.docx",
        template_path="template.docx",
        template_context={},
        logger=logger,
    )

    results = run_processors(
        [
            _Processor("ok_processor", "ok"),
            _Processor("skip_processor", "skip"),
            _Processor("bad_processor", "error"),
        ],
        ctx,
    )

    assert [r.status for r in results] == ["OK", "SKIPPED", "ERROR"]
    assert results[2].error == "boom"
    assert logger.warnings[0][0] == "bad_processor failed"


def test_template_renderer_default_processors_include_key_m1_processors():
    renderer = TemplateRenderer(log_level="ERROR")
    names = [processor.name for processor in renderer.build_post_render_processors()]

    assert "bullet_lists" in names
    assert "variant_tables" in names
    assert "toc_refresh" in names
    assert "blank_page_cleanup" in names
    assert "underlines_and_styles" in names


def test_qa_report_records_post_processor_errors(tmp_path):
    docx_path = tmp_path / "clean.docx"
    doc = Document()
    doc.add_paragraph("已生成报告")
    doc.save(docx_path)

    qa = build_docx_qa_report(
        output_file=str(docx_path),
        processor_report=[
            {"name": "bullet_lists", "status": "OK"},
            {"name": "toc_refresh", "status": "ERROR", "error": "refresh failed"},
        ],
    )

    assert qa["status"] == "WARN"
    assert qa["checks"]["post_processors"]["error_count"] == 1
    assert any(i["code"] == "POST_PROCESSOR_ERRORS" for i in qa["issues"])


def test_qa_report_detects_placeholder_residue(tmp_path):
    docx_path = tmp_path / "placeholder.docx"
    doc = Document()
    doc.add_paragraph("患者：{{ patient_name }}")
    doc.save(docx_path)

    qa = build_docx_qa_report(output_file=str(docx_path))

    assert qa["status"] == "FAIL"
    assert any(i["code"] == "UNRENDERED_PLACEHOLDER" for i in qa["issues"])


def test_qa_report_detects_empty_numbered_paragraph(tmp_path):
    docx_path = tmp_path / "empty_numbered.docx"
    doc = Document()
    p = doc.add_paragraph("")
    ppr = p._p.get_or_add_pPr()
    num_pr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), "0")
    num_id = OxmlElement("w:numId")
    num_id.set(qn("w:val"), "1")
    num_pr.append(ilvl)
    num_pr.append(num_id)
    ppr.append(num_pr)
    doc.save(docx_path)

    qa = build_docx_qa_report(output_file=str(docx_path))

    assert qa["status"] == "FAIL"
    assert qa["checks"]["empty_numbered_paragraphs"]["count"] == 1
    assert any(i["code"] == "EMPTY_NUMBERED_PARAGRAPH" for i in qa["issues"])


def test_renderer_clears_empty_numbered_paragraphs_inside_tables(tmp_path):
    docx_path = tmp_path / "table_empty_numbered.docx"
    doc = Document()
    table = doc.add_table(rows=1, cols=1)
    p = table.rows[0].cells[0].paragraphs[0]
    ppr = p._p.get_or_add_pPr()
    num_pr = OxmlElement("w:numPr")
    num_id = OxmlElement("w:numId")
    num_id.set(qn("w:val"), "1")
    num_pr.append(num_id)
    ppr.append(num_pr)
    doc.save(docx_path)

    TemplateRenderer(log_level="ERROR")._remove_empty_numbered_paragraphs(str(docx_path))

    rendered = Document(docx_path)
    cleaned = rendered.tables[0].rows[0].cells[0].paragraphs[0]
    assert cleaned._p.pPr is None or cleaned._p.pPr.numPr is None
    qa = build_docx_qa_report(output_file=str(docx_path))
    assert qa["checks"]["empty_numbered_paragraphs"]["count"] == 0


def test_qa_report_checks_crc_tables_and_counts(tmp_path):
    docx_path = tmp_path / "crc.docx"
    doc = Document()
    doc.add_paragraph("本次共检出体细胞变异：8 个")
    doc.add_paragraph("与靶向药物用药相关的变异有：4 个")
    doc.add_paragraph("6.5 mutations/Mb，TMB-L；微卫星稳定型，MSS")

    tips = doc.add_table(rows=2, cols=4)
    for idx, text in enumerate(["基因", "突变位点", "潜在获益靶向药物", "可能耐药"]):
        tips.rows[0].cells[idx].text = text

    summary = doc.add_table(rows=2, cols=4)
    for idx, text in enumerate(["基因", "基因突变信息", "潜在获益靶向药物", "可能耐药"]):
        summary.rows[0].cells[idx].text = text

    detail = doc.add_table(rows=2, cols=9)
    headers = [
        "基因名称",
        "转录本号",
        "染色体",
        "外显子",
        "核苷酸变化",
        "氨基酸变化",
        "突变频率",
        "潜在获益",
        "可能耐药",
    ]
    for idx, text in enumerate(headers):
        detail.rows[0].cells[idx].text = text

    biomarker = doc.add_table(rows=2, cols=3)
    biomarker.rows[0].cells[0].text = "TMB/MSI/其它生物标志物检测结果"
    biomarker.rows[0].cells[2].text = "用药提示"
    biomarker.rows[1].cells[0].text = "MSI"
    doc.save(docx_path)

    report_data = ReportData()
    report_data.set_field("total_variants_count", 8)
    report_data.set_field("drug_related_count", 4)
    report_data.set_field("tmb_status", "TMB-L")
    report_data.set_field("msi_status", "MSS")
    report_data.set_table("variants", [{"gene": "TP53"}])

    qa = build_docx_qa_report(
        output_file=str(docx_path),
        report_data=report_data,
        project_type="crc_358_msi",
    )

    assert qa["status"] == "PASS"
    assert qa["checks"]["variant_detail_table_shape"]["status"] == "PASS"
    assert qa["checks"]["total_variant_count_text"]["status"] == "PASS"
    assert qa["checks"]["drug_related_count_text"]["status"] == "PASS"


def test_qa_report_flags_crc_missing_required_tables(tmp_path):
    docx_path = tmp_path / "crc_missing_tables.docx"
    doc = Document()
    doc.add_paragraph("本次共检出体细胞变异：1 个")
    doc.add_paragraph("与靶向药物用药相关的变异有：1 个")
    doc.add_paragraph("TMB-L；MSS")
    doc.save(docx_path)

    report_data = ReportData()
    report_data.set_field("total_variants_count", 1)
    report_data.set_field("drug_related_count", 1)
    report_data.set_field("tmb_status", "TMB-L")
    report_data.set_field("msi_status", "MSS")
    report_data.set_table("variants", [{"gene": "TP53"}])

    qa = build_docx_qa_report(
        output_file=str(docx_path),
        report_data=report_data,
        project_type="crc_358_msi",
    )

    assert qa["status"] == "FAIL"
    issue_codes = {i["code"] for i in qa["issues"]}
    assert "VARIANT_DETAIL_TABLE_SHAPE" in issue_codes
    assert "BIOMARKER_TABLE_PRESENT" in issue_codes


def test_write_qa_report_creates_sidecar_json(tmp_path):
    docx_path = tmp_path / "clean.docx"
    doc = Document()
    doc.add_paragraph("已生成报告")
    doc.save(docx_path)

    qa = build_docx_qa_report(output_file=str(docx_path))
    qa_path = Path(write_docx_qa_report(qa, str(docx_path)))

    assert qa_path.name == "clean.qa.json"
    assert qa_path.exists()
    assert "PASS" in qa_path.read_text(encoding="utf-8")


def test_crc358_golden_excel_fixture_is_synthetic_and_parseable(tmp_path):
    xlsx_path = build_crc_358_msi_golden_excel(
        tmp_path / "LZ999001_crc_358_msi_golden.xlsx"
    )

    excel_data = ExcelReader(
        config_dir=str(ROOT / "config"), log_level="ERROR"
    ).read(str(xlsx_path), include_tables=True)

    assert excel_data.metadata["sample_id_from_filename"] == "LZ999001"
    assert excel_data.single_values["患者姓名"] == "黄金测试患者"
    assert excel_data.single_values["TMB"] == 6.5
    assert excel_data.single_values["MSI状态"] == "MSS"
    assert len(excel_data.get_table_data("Variations")) == 2
    assert {r["Gene_Symbol"] for r in excel_data.get_table_data("Variations")} == {
        "ERBB2",
        "FBXW7",
    }


def test_golden_case_assertions_pass_on_expected_report_shape(tmp_path):
    docx_path = tmp_path / "golden_like.docx"
    doc = Document()
    doc.add_paragraph("本次共检出体细胞变异：2 个")
    doc.add_paragraph("与靶向药物用药相关的变异有：1 个")
    doc.add_paragraph("6.5 mutations/Mb，TMB-L；微卫星稳定型，MSS")
    doc.add_paragraph("多项临床研究表明，TMB-H的肿瘤对免疫检查点抑制剂有更强的免疫应答效果")
    doc.add_paragraph("研究表明，MSI-H的实体瘤通常具有免疫原性和广泛的T细胞浸润性")
    doc.add_paragraph("ERBB2：c.1979G>A，p.G660D")

    tips = doc.add_table(rows=2, cols=4)
    for idx, text in enumerate(["基因", "突变位点", "潜在获益靶向药物", "可能耐药"]):
        tips.rows[0].cells[idx].text = text
    tips.rows[1].cells[0].text = "ERBB2"
    tips.rows[1].cells[1].text = "c.1979G>A，p.G660D"

    summary = doc.add_table(rows=2, cols=4)
    for idx, text in enumerate(["基因", "基因突变信息", "潜在获益靶向药物", "可能耐药"]):
        summary.rows[0].cells[idx].text = text
    summary.rows[1].cells[0].text = "ERBB2"

    detail = doc.add_table(rows=2, cols=9)
    headers = [
        "基因名称",
        "转录本号",
        "染色体",
        "外显子",
        "核苷酸变化",
        "氨基酸变化",
        "突变频率",
        "潜在获益",
        "可能耐药",
    ]
    for idx, text in enumerate(headers):
        detail.rows[0].cells[idx].text = text
    detail.rows[1].cells[0].text = "ERBB2"
    detail.rows[1].cells[4].text = "c.1979G>A"
    detail.rows[1].cells[5].text = "p.G660D"

    biomarker = doc.add_table(rows=2, cols=3)
    biomarker.rows[0].cells[0].text = "TMB/MSI/其它生物标志物检测结果"
    biomarker.rows[0].cells[2].text = "用药提示"
    biomarker.rows[1].cells[0].text = "MSI"
    doc.save(docx_path)

    report_data = ReportData()
    report_data.set_field("total_variants_count", 2)
    report_data.set_field("drug_related_count", 1)
    report_data.set_field("tmb_status", "L")
    report_data.set_field("msi_status", "MSS")
    report_data.set_table("variants", [{"gene": "ERBB2"}])
    processor_report = [{"name": "underlines_and_styles", "status": "OK"}]
    qa = build_docx_qa_report(
        output_file=str(docx_path),
        report_data=report_data,
        project_type="crc_358_msi",
        field_provenance={"fields": {"patient_name": {"source": "excel"}}},
        field_provenance_file=str(docx_path.with_suffix(".field_provenance.json")),
        processor_report=processor_report,
    )

    result = {
        "success": True,
        "output_file": str(docx_path),
        "context": report_data.context,
        "qa_report": qa,
        "field_provenance_file": str(docx_path.with_suffix(".field_provenance.json")),
        "post_processors": processor_report,
        "errors": [],
    }
    assertion = assert_golden_case_output(
        result, expectations=CRC_358_MSI_EXPECTATIONS
    )

    assert assertion["ok"]
