# ruff: noqa: E402
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_lung_excel_request_list import validate_request_list  # noqa: E402, I001


REQUEST_HEADERS = [
    "优先级",
    "目标模板",
    "版式族",
    "规格",
    "PD-L1",
    "样本号",
    "需索要材料",
    "理由",
]
LEGACY_REQUEST_HEADERS = [
    "优先级",
    "目标模板",
    "版式族",
    "规格",
    "PD-L1",
    "样本号",
    "已有Excel",
    "理由",
]
INVENTORY_HEADERS = [
    "sample_id",
    "family",
    "prefix",
    "spec",
    "pdl1",
    "has_excel",
    "filename",
]


def _write_tsv(path: Path, headers: list[str], rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(headers)
        writer.writerows(rows)
    return path


def _request(sample_id: str, *, spec: str = "肺癌13基因", pdl1: str = "N"):
    return [
        "P1",
        "小Panel基础版",
        "A",
        spec,
        pdl1,
        sample_id,
        "NGS Excel",
        "合成测试",
    ]


def _inventory(sample_id: str, *, spec: str = "13基因", pdl1: str = "N", has_excel: str = "N"):
    return [sample_id, "A", "肺癌", spec, pdl1, has_excel, "<synthetic>.docx"]


def _codes(result: dict) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


def test_valid_request_list_matches_inventory(tmp_path):
    request_path = _write_tsv(
        tmp_path / "request.tsv",
        REQUEST_HEADERS,
        [
            _request("LZ900001"),
            _request("LZ900002", spec="肺癌62基因", pdl1="Y"),
        ],
    )
    inventory_path = _write_tsv(
        tmp_path / "inventory.tsv",
        INVENTORY_HEADERS,
        [
            _inventory("lz900001"),
            _inventory("lz900002", spec="62基因", pdl1="Y"),
        ],
    )

    result = validate_request_list(
        request_path,
        inventory_path=inventory_path,
        expected_count=2,
    )

    assert result["status"] == "PASS"
    assert result["unique_sample_count"] == 2
    assert result["pdl1_case_count"] == 1
    assert result["privacy"]["patient_names_emitted"] is False
    assert result["privacy"]["sample_ids_emitted_only_on_error"] is True


def test_duplicate_sample_and_wrong_frozen_count_fail(tmp_path):
    request_path = _write_tsv(
        tmp_path / "request.tsv",
        REQUEST_HEADERS,
        [_request("LW900001"), _request("lw900001")],
    )

    result = validate_request_list(request_path, expected_count=3)

    assert result["status"] == "FAIL"
    assert result["unique_sample_count"] == 1
    assert {
        "request_duplicate_sample_id",
        "request_row_count_mismatch",
    } <= _codes(result)


def test_legacy_request_header_remains_accepted(tmp_path):
    request_path = _write_tsv(
        tmp_path / "request.tsv",
        LEGACY_REQUEST_HEADERS,
        [["P1", "小Panel基础版", "A", "肺癌13基因", "N", "LW900003", "N", "测试"]],
    )

    result = validate_request_list(request_path, expected_count=1)

    assert result["status"] == "PASS"


def test_inventory_mismatch_and_existing_excel_fail(tmp_path):
    request_path = _write_tsv(
        tmp_path / "request.tsv",
        REQUEST_HEADERS,
        [_request("LZ900010"), _request("LZ900011", spec="肺癌62基因")],
    )
    inventory_path = _write_tsv(
        tmp_path / "inventory.tsv",
        INVENTORY_HEADERS,
        [_inventory("LZ900010", has_excel="Y")],
    )

    result = validate_request_list(
        request_path,
        inventory_path=inventory_path,
    )

    assert result["status"] == "FAIL"
    assert {
        "request_already_has_excel",
        "request_not_in_inventory",
    } <= _codes(result)


def test_invalid_flags_and_empty_sample_fail(tmp_path):
    request_path = _write_tsv(
        tmp_path / "request.tsv",
        LEGACY_REQUEST_HEADERS,
        [["P1", "模板", "A", "肺癌13基因", "maybe", "", "unknown", "测试"]],
    )

    result = validate_request_list(request_path)

    assert result["status"] == "FAIL"
    assert {
        "request_empty_sample_id",
        "request_invalid_pdl1_flag",
        "request_invalid_excel_flag",
    } <= _codes(result)


def test_empty_material_fails_for_current_schema(tmp_path):
    request_path = _write_tsv(
        tmp_path / "request.tsv",
        REQUEST_HEADERS,
        [["P1", "模板", "A", "肺癌13基因", "N", "LW900020", "", "测试"]],
    )

    result = validate_request_list(request_path)

    assert result["status"] == "FAIL"
    assert "request_empty_material" in _codes(result)
