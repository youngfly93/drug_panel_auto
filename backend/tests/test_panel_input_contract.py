# ruff: noqa: E402, I001
"""Panel Excel table/column contracts must fail closed at runtime."""

from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.core.pipeline import StageHandle
from reportgen.core.pipeline.result import StageResult
from reportgen.core.report_generator import ReportGenerator, _GenerationState
from reportgen.models.excel_data import ExcelDataSource
from reportgen.models.report_data import ReportData
from reportgen.panels.input_contract import validate_excel_input_contract
from reportgen.panels.loader import load_panel_package


CONTRACT = {
    "required_tables": ["Variations", "TMB", "Msisensor"],
    "required_columns": {
        "Variations": ["Gene_Symbol", "cHGVS", "ExistIn552", "Transcript"]
    },
    "required_any_columns": {"Variations": ["pHGVS_S", "pHGVS_A"]},
}


def _excel(
    tmp_path: Path,
    *,
    sheets: list[str],
    variation_columns: list[str],
) -> ExcelDataSource:
    source = tmp_path / "synthetic.xlsx"
    source.write_bytes(b"synthetic")
    return ExcelDataSource(
        file_path=str(source),
        sheet_names=sheets,
        table_data={},
        metadata={"table_columns": {"Variations": variation_columns}},
    )


def test_empty_variations_sheet_passes_when_headers_satisfy_contract(tmp_path):
    excel_data = _excel(
        tmp_path,
        sheets=["Variations", "TMB", "Msisensor"],
        variation_columns=[
            "Gene_Symbol",
            "cHGVS",
            "ExistIn552",
            "Transcript",
            "pHGVS_A",
        ],
    )

    assert validate_excel_input_contract(excel_data, CONTRACT) == []


def test_contract_reports_missing_table_required_column_and_any_column(tmp_path):
    excel_data = _excel(
        tmp_path,
        sheets=["Variations", "TMB"],
        variation_columns=["Gene_Symbol", "cHGVS", "ExistIn552"],
    )

    failures = validate_excel_input_contract(excel_data, CONTRACT)

    assert {(failure["code"], failure["table"]) for failure in failures} == {
        ("REQUIRED_TABLE_MISSING", "Msisensor"),
        ("REQUIRED_COLUMN_MISSING", "Variations"),
        ("REQUIRED_ANY_COLUMN_MISSING", "Variations"),
    }
    assert not any("synthetic.xlsx" in str(failure) for failure in failures)


def test_report_generator_stage_blocks_missing_selector_columns(tmp_path):
    package = load_panel_package("lung_588_pdl1", project_root=ROOT)
    excel_data = _excel(
        tmp_path,
        sheets=["Variations", "TMB", "Msisensor"],
        variation_columns=["Gene_Symbol", "cHGVS", "ExistIn552"],
    )
    state = _GenerationState(
        excel_file=excel_data.file_path,
        template_file=str(package.resolve_template_file()),
        output_dir=str(tmp_path / "output"),
        excel_data=excel_data,
        panel_package=package,
        report_data=ReportData(),
    )
    result = StageResult(name="InputContractValidationStage")

    failure = ReportGenerator(
        config_dir=str(ROOT / "config"),
        template_dir=str(ROOT / "templates"),
        log_level="ERROR",
    )._stage_input_contract_validation(
        StageHandle(result),
        state,
        time.time(),
    )

    assert failure is not None
    assert failure["success"] is False
    assert failure["input_contract_validation"]["status"] == "FAIL"
    assert result.status == "FAIL"
    assert result.issues[0].code == "PANEL_INPUT_CONTRACT_FAILED"
