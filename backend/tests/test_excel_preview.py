import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

import pandas as pd  # noqa: E402
from reportgen.models.excel_data import ExcelDataSource  # noqa: E402

from app.services.reportgen_bridge import ReportGenBridge  # noqa: E402


def _bridge_with_reader(reader=None):
    bridge = ReportGenBridge.__new__(ReportGenBridge)
    bridge._excel_reader = reader
    return bridge


def test_sheet_info_counts_list_backed_table_data(tmp_path):
    excel_path = tmp_path / "synthetic.xlsx"
    excel_path.write_bytes(b"placeholder")
    bridge = _bridge_with_reader()
    excel_data = ExcelDataSource(
        file_path=str(excel_path),
        table_data={
            "Variations": [
                {"Gene": "ERBB2", "cHGVS": "c.1979G>A"},
                {"Gene": "FBXW7", "pHGVS": "p.R465H"},
            ]
        },
        sheet_names=["Variations"],
    )

    assert bridge.get_sheet_info(excel_data, "Variations") == {
        "rows": 2,
        "columns": 3,
    }
    page = bridge.get_table_data(excel_data, "Variations", page=1, page_size=50)
    assert page["total_rows"] == 2
    assert page["columns"] == ["Gene", "cHGVS", "pHGVS"]


def test_sheet_preview_falls_back_to_raw_excel_sheet(tmp_path):
    excel_path = tmp_path / "synthetic.xlsx"
    excel_path.write_bytes(b"placeholder")
    reader = SimpleNamespace(
        read_sheet=lambda _path, _sheet: pd.DataFrame(
            [{"患者姓名": "黄金测试患者", "样本编号": "LZ999001"}]
        )
    )
    bridge = _bridge_with_reader(reader)
    excel_data = ExcelDataSource(
        file_path=str(excel_path),
        table_data={},
        sheet_names=["Meta"],
    )

    assert bridge.get_sheet_info(excel_data, "Meta", excel_path=str(excel_path)) == {
        "rows": 1,
        "columns": 2,
    }
    page = bridge.get_table_data(
        excel_data,
        "Meta",
        page=1,
        page_size=50,
        excel_path=str(excel_path),
    )
    assert page["total_rows"] == 1
    assert page["columns"] == ["患者姓名", "样本编号"]
    assert page["rows"][0]["样本编号"] == "LZ999001"
