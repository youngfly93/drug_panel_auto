# ruff: noqa: E402
"""Synthetic contracts for derived-input drafts; never a historical same-case claim."""

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / "backend"):
    sys.path.insert(0, str(directory))

from reportgen.core.field_mapper import FieldMapper
from reportgen.core.golden_case import _golden_case_spec, _normalize_panel
from reportgen.core.project_detector import ProjectDetector
from reportgen.core.template_bridge_358 import build_undetected_genes, load_panel_config
from reportgen.core.template_contract import extract_template_contract, validate_declared_contract
from reportgen.models.excel_data import ExcelDataSource
from reportgen.panels.input_scope import scope_panel_excel
from reportgen.panels.loader import load_panel_package
from reportgen.panels.validation import validate_panel_package
from reportgen.rules.targeted_drugs import load_targeted_drug_rule_context
from scripts.scan_hardcoded_literals import scan_docx

from app.services.project_identity import ProjectIdentityConflictError, resolve_project_identity
from app.services.reportgen_bridge import ReportGenBridge


def package(panel):
    return load_panel_package(panel, project_root=ROOT)


def source(tmp_path, count=62, name="neutral.xlsx", project_name=None):
    path = tmp_path / name
    path.touch()
    column = f"ExistInsmall{count}"
    rows = [
        {
            "Gene_Symbol": "BRAF",
            "cHGVS": "c.1799T>A",
            "pHGVS_S": "p.V600E",
            "Transcript": "NM_004333.6",
            "ExistIn552": "Ⅰ类",
            column: 1,
        },
        {
            "Gene_Symbol": "ERBB2",
            "cHGVS": "c.1979G>A",
            "pHGVS_S": "p.G660D",
            "Transcript": "NM_004448.4",
            "ExistIn552": "Ⅰ类",
            column: 1,
        },
        {
            "Gene_Symbol": "TP53",
            "cHGVS": "c.734G>A",
            "pHGVS_S": "p.G245D",
            "Transcript": "NM_000546.6",
            "ExistIn552": "Ⅱ类",
            column: 1,
        },
        {
            "Gene_Symbol": "PIK3CA",
            "cHGVS": "c.3197C>T",
            "pHGVS_S": "p.A1066V",
            "Transcript": "NM_006218.4",
            "ExistIn552": "Ⅱ类",
            column: 1,
        },
        {"Gene_Symbol": "FGF3", "cHGVS": "c.469G>T", "ExistIn552": "Ⅱ类", column: None},
        {"Gene_Symbol": "EGFR", "cHGVS": "c.1A>T", "ExistIn552": 1, column: 1},
    ]
    return ExcelDataSource(
        str(path),
        single_values={"project_name": project_name} if project_name else {},
        table_data={
            "Variations": rows,
            "Hereditary_tumor": [{"Gene_Symbol": "TP53", column: 1, "ExistIn178": 1}],
            "Cnv": [
                {"Gene": "EGFR", "CopyNumber": 8, "ExistIn137": 1},
                {"Gene": "FGF3", "CopyNumber": 6, "ExistIn137": 1},
            ],
            "CtDrug": [{"Drug": "independent PGx source"}],
            "Fusion": [
                {"gene1": "EML4", "gene2": "ALK", "Est_Type": "RNA"},
                {"gene1": "ETV6", "gene2": "NTRK3", "Est_Type": "RNA"},
            ],
        },
    )


@pytest.mark.parametrize(
    "panel,count", [("lung_13", 13), ("lung_62", 62), ("lung_62_pdl1", 62), ("lung_588", 588)]
)
def test_draft_packages_are_valid_and_literal_free(panel, count):
    pkg = package(panel)
    assert pkg.raw["status"] == pkg.default_template.status == "draft"
    assert validate_panel_package(panel, project_root=ROOT).ok
    assert not scan_docx(pkg.resolve_template_file(), tokens=[]).hard
    declared = validate_declared_contract(
        str(pkg.resolve_template_file()),
        extract_template_contract(str(pkg.resolve_template_file())),
        pkg.template_contract,
    )
    assert declared.ok, declared
    lists = set(extract_template_contract(str(pkg.resolve_template_file())).required_lists)
    reference = package("lung_588_pdl1")
    reference_lists = extract_template_contract(
        str(reference.resolve_template_file())
    ).required_lists
    pgx_lists = {name for name in reference_lists if name.startswith("drug_")}
    assert pgx_lists <= lists
    assert "chemotherapy_dosage_rows" in lists
    assert "immune_hyperprogression_result" in extract_template_contract(
        str(pkg.resolve_template_file())
    ).required_paths
    config = load_panel_config(panel_package=pkg)
    assert len(config.crc_important_genes) == count
    assert len(build_undetected_genes(set(), panel_config=config)) == count
    assert all(
        set(row.get("genes") or []) <= config.crc_important_genes
        for row in config.lung_guideline_drug_rows
    )


@pytest.mark.parametrize("count", [62, 588])
def test_shared_fingerprint_defaults_to_ngs_not_ihc_even_with_filename(tmp_path, count):
    excel = source(tmp_path, count, f"肺癌{count}基因+PD-L1.xlsx")
    result = ProjectDetector(config_dir=str(ROOT / "config"), log_level="ERROR").detect(
        excel.file_path, excel
    )
    assert result["project_type"] == f"lung_{count}"
    assert result["identity_source"] == "ngs_family_default"
    assert result["identity_conflicts"] == []
    assert {item["id"] for item in result["family_choices"]} == {
        f"lung_{count}",
        f"lung_{count}_pdl1",
    }


@pytest.mark.parametrize("count", [62, 588])
def test_trusted_order_or_explicit_choice_selects_pdl1_within_family(tmp_path, count):
    bridge = ReportGenBridge(config_dir=str(ROOT / "config"), template_dir=str(ROOT / "templates"))
    excel = source(tmp_path, count)
    chosen = resolve_project_identity(
        bridge,
        excel_path=excel.file_path,
        excel_data=excel,
        requested_project_type=f"lung_{count}_pdl1",
    )
    assert chosen.project_type == f"lung_{count}_pdl1"
    excel.single_values["project_name"] = f"肺癌{count}基因+PD-L1"
    detected = bridge.detect_project_type(excel.file_path, excel)
    assert detected["project_type"] == f"lung_{count}_pdl1"
    assert detected["identity_source"] == "trusted_project_text"


@pytest.mark.parametrize("other", ["crc_358_msi", "lung_588", "lung_13"])
def test_family_disambiguation_never_overrides_a_different_ngs_product(tmp_path, other):
    bridge = ReportGenBridge(config_dir=str(ROOT / "config"), template_dir=str(ROOT / "templates"))
    excel = source(tmp_path)
    with pytest.raises(ProjectIdentityConflictError):
        resolve_project_identity(
            bridge, excel_path=excel.file_path, excel_data=excel, requested_project_type=other
        )


def test_membership_is_not_classification_and_cnv_pgx_sources_are_not_mutated(tmp_path):
    excel = source(tmp_path, 13)
    before = copy.deepcopy(excel.to_dict())
    view = scope_panel_excel(excel, package("lung_13"))
    assert {row["Gene_Symbol"] for row in view.get_table_data("Variations")} == {
        "BRAF",
        "ERBB2",
        "TP53",
        "PIK3CA",
    }
    assert view.get_table_data("Cnv") == [before["table_data"]["Cnv"][0]]
    assert view.get_table_data("Cnv")[0]["CopyNumber"] == 8
    assert view.get_table_data("Cnv")[0]["ExistIn137"] == 1
    assert view.get_table_data("CtDrug") == before["table_data"]["CtDrug"]
    assert view.get_table_data("Fusion") == [before["table_data"]["Fusion"][0]]
    assert excel.to_dict() == before


def test_missing_flag_fails_closed_and_flag_name_is_configuration_driven(tmp_path):
    excel = source(tmp_path, 13)
    pkg = package("lung_13")
    for row in excel.table_data["Variations"]:
        row.pop("ExistInsmall13")
    with pytest.raises(ValueError, match="membership column"):
        scope_panel_excel(excel, pkg)
    excel = source(tmp_path, 13)
    raw = copy.deepcopy(pkg.raw)
    raw["derived_input"]["membership_column"] = "ExistInsmall130"
    custom = SimpleNamespace(raw=raw, panel_id="test")
    for table in ("Variations", "Hereditary_tumor"):
        for row in excel.table_data[table]:
            row["ExistInsmall130"] = row.pop("ExistInsmall13")
    assert len(scope_panel_excel(excel, custom).get_table_data("Variations")) == 4


@pytest.mark.parametrize("record_header", [False, True])
def test_blank_membership_cells_are_nonmembers_not_missing_columns(tmp_path, record_header):
    excel = source(tmp_path, 13)
    excel.table_data["Variations"][4].pop("ExistInsmall13")
    if record_header:
        excel.metadata["table_columns"] = {
            "Variations": list(excel.table_data["Variations"][0])
        }
    before = copy.deepcopy(excel.to_dict())
    view = scope_panel_excel(excel, package("lung_13"))
    assert len(view.get_table_data("Variations")) == 4
    assert excel.to_dict() == before


@pytest.mark.parametrize("empty_rows", [False, True])
def test_recorded_header_allows_an_all_blank_membership_column(tmp_path, empty_rows):
    excel = source(tmp_path, 13)
    excel.metadata["table_columns"] = {
        "Variations": list(excel.table_data["Variations"][0])
    }
    for row in excel.table_data["Variations"]:
        row.pop("ExistInsmall13")
    if empty_rows:
        excel.table_data["Variations"] = []
    assert scope_panel_excel(excel, package("lung_13")).get_table_data("Variations") == []
    excel.metadata["table_columns"]["Variations"].remove("ExistInsmall13")
    with pytest.raises(ValueError, match="membership column"):
        scope_panel_excel(excel, package("lung_13"))


def test_thirteen_gene_context_keeps_four_variants_and_three_targeted_rows(tmp_path):
    pkg = package("lung_13")
    excel = source(tmp_path, 13)
    mapper = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR")
    report = mapper.map(excel, panel_package=pkg)
    assert {row["gene"] for row in report.get_table("variants_2_1")} == {
        "BRAF",
        "ERBB2",
        "TP53",
        "PIK3CA",
    }
    tips = report.get_table("targeted_drug_tips")
    assert {row["gene"] for row in tips} == {"BRAF", "ERBB2", "PIK3CA"}
    policy = load_targeted_drug_rule_context(pkg)
    assert "TP53" not in policy["gene_level_review_pending"]["allowed_genes"]
    assert "PIK3CA" in policy["gene_level_review_pending"]["allowed_genes"]


def test_optional_fields_never_infer_qc_from_read_metrics(tmp_path):
    excel = source(tmp_path, 13)
    excel.single_values.update({"Q30": 98.5, "平均深度": 1500})
    mapper = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR")
    report = mapper.map(excel, panel_package=package("lung_13"))
    for field in (
        "qc_extraction_status", "qc_library_status", "qc_sequencing_status", "qc_analysis_status"
    ):
        assert report.get_field(field) == "未提供"
        assert report.metadata["optional_source_fields"][field] == {
            "source": "default", "source_key": None, "provided": False, "inferred": False,
        }
    assert "unregistered_typo" not in report.context


def test_optional_fields_preserve_explicit_source_and_remain_panel_scoped(tmp_path):
    excel = source(tmp_path, 13)
    excel.single_values["测序质控结论"] = "人工复核未通过"
    excel.single_values["family_history"] = "合成测试病史"
    mapper = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR")
    report = mapper.map(excel, panel_package=package("lung_13"))
    assert report.get_field("qc_sequencing_status") == "人工复核未通过"
    assert report.get_field("family_history") == "合成测试病史"
    provenance = report.metadata["optional_source_fields"]["qc_sequencing_status"]
    assert provenance["source_key"] == "测序质控结论"
    legacy = mapper.map(excel, panel_package=package("lung_588_pdl1"))
    assert "qc_sequencing_status" not in legacy.context


def test_class_three_variants_keep_primary_rows_but_no_drug_tips(tmp_path):
    excel = source(tmp_path, 62)
    excel.table_data["Variations"] = [{
        "Gene_Symbol": "ESR1", "cHGVS": "c.1242G>T", "pHGVS_S": "p.Q414H",
        "ExistIn552": "Ⅲ类", "ExistInsmall62": 1,
    }]
    mapper = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR")
    report = mapper.map(excel, panel_package=package("lung_62"))
    rows = report.get_table("variants_2_1")
    assert len(rows) == 1 and rows[0]["gene"] == "ESR1"
    assert rows[0]["benefit_drugs"] == "--"
    assert report.get_table("targeted_drug_tips") == []


@pytest.mark.parametrize("panel", ["lung_13", "lung_62", "lung_62_pdl1", "lung_588"])
def test_each_draft_has_a_product_specific_synthetic_golden_runner(tmp_path, panel):
    assert _normalize_panel(panel) == panel
    spec = _golden_case_spec(panel)
    built = spec["builder"](tmp_path / spec["input_filename"])
    data = built.excel_data
    assert data.metadata["synthetic_fixture"] is True
    assert data.metadata["panel_id"] == panel
    assert "Cnv" in data.sheet_names
    assert data.table_data["Cnv"]
    assert all(row["Status"] == "neutral" for row in data.table_data["Cnv"])
    flag = f"ExistInsmall{panel.split('_')[1]}"
    assert data.table_data["Variations"][0][flag] == 1
    assert not any("pdl1" in key.lower() for key in data.table_data["Variations"][0])
    assert bool(data.single_values.get("PD-L1 TPS")) == panel.endswith("_pdl1")
    assert built.excel_file.with_suffix(".pdl1.png").exists() == panel.endswith("_pdl1")
    assert spec["expectations"]["project_type"] == panel
    assert "CtDrug" in data.sheet_names
    mapper = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR")
    mapped = mapper.map(data, panel_package=package(panel))
    pgx = mapped.get_table("drug_shunbo")
    # PGx is an independent assay source, not cropped by the NGS gene panel.
    assert len(pgx) == 1 and pgx[0]["Gene"] == "ERCC1"
    assert pgx[0]["Result"] == "SYNTHETIC-PGX-OBSERVATION"
