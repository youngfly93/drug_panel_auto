#!/usr/bin/env python3
# 步骤: 75 肺癌历史终版配套资料索要清单校验
# 上游: 肺癌逐报告版式台账 TSV、技术老师资料索要清单 TSV
# 输出: 标准输出中的脱敏校验结果（不写患者文件）
# 种子: 无（确定性校验）
"""Validate the local lung-panel Excel request ledger before it is shared.

The source ledgers stay under ``.work/`` and are intentionally not committed.
This versioned validator checks their schema and cross-file consistency without
selecting or emitting patient names or original report filenames.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


REQUEST_CORE_COLUMNS = (
    "优先级",
    "目标模板",
    "版式族",
    "规格",
    "PD-L1",
    "样本号",
    "理由",
)
REQUEST_MATERIAL_COLUMN = "需索要材料"
REQUEST_LEGACY_EXCEL_COLUMN = "已有Excel"
INVENTORY_COLUMNS = (
    "sample_id",
    "family",
    "prefix",
    "spec",
    "pdl1",
    "has_excel",
    "filename",
)
YES_NO = {"Y", "N"}


def _read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        headers = list(reader.fieldnames or [])
        rows = [
            {str(key): str(value or "").strip() for key, value in row.items()}
            for row in reader
        ]
    return headers, rows


def _missing_columns(headers: list[str], required: tuple[str, ...]) -> list[str]:
    present = {str(value).strip() for value in headers}
    return [column for column in required if column not in present]


def _sample_id(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _spec(value: str) -> str:
    normalized = re.sub(r"\s+", "", str(value or "")).lower()
    return re.sub(r"^肺癌", "", normalized)


def _yn(value: str) -> str:
    return str(value or "").strip().upper()


def _issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def validate_request_list(
    request_path: Path,
    *,
    inventory_path: Path | None = None,
    expected_count: int | None = None,
) -> dict[str, Any]:
    """Return a machine-readable, PHI-minimized validation result."""

    request_headers, request_rows = _read_tsv(request_path)
    issues: list[dict[str, Any]] = []
    missing = _missing_columns(request_headers, REQUEST_CORE_COLUMNS)
    if missing:
        issues.append(
            _issue(
                "request_schema_missing_columns",
                "资料索要清单缺少必需列",
                columns=missing,
            )
        )

    has_material_column = REQUEST_MATERIAL_COLUMN in request_headers
    has_legacy_excel_column = REQUEST_LEGACY_EXCEL_COLUMN in request_headers
    if not has_material_column and not has_legacy_excel_column:
        issues.append(
            _issue(
                "request_schema_missing_request_detail",
                "资料索要清单必须包含需索要材料列；旧版清单可暂用已有Excel列",
                accepted_columns=[
                    REQUEST_MATERIAL_COLUMN,
                    REQUEST_LEGACY_EXCEL_COLUMN,
                ],
            )
        )

    if expected_count is not None and len(request_rows) != expected_count:
        issues.append(
            _issue(
                "request_row_count_mismatch",
                "资料索要清单行数与冻结目标不一致",
                expected=expected_count,
                actual=len(request_rows),
            )
        )

    seen: dict[str, int] = {}
    normalized_rows: list[dict[str, Any]] = []
    for row_number, row in enumerate(request_rows, start=2):
        sample_id = _sample_id(row.get("样本号", ""))
        pdl1 = _yn(row.get("PD-L1", ""))
        material = str(row.get(REQUEST_MATERIAL_COLUMN, "") or "").strip()
        has_excel = _yn(row.get(REQUEST_LEGACY_EXCEL_COLUMN, "N"))
        spec = _spec(row.get("规格", ""))

        if not sample_id:
            issues.append(
                _issue(
                    "request_empty_sample_id",
                    "资料索要清单存在空样本号",
                    row=row_number,
                )
            )
        elif sample_id in seen:
            issues.append(
                _issue(
                    "request_duplicate_sample_id",
                    "资料索要清单存在重复样本号",
                    sample_id=sample_id,
                    first_row=seen[sample_id],
                    duplicate_row=row_number,
                )
            )
        else:
            seen[sample_id] = row_number

        if pdl1 not in YES_NO:
            issues.append(
                _issue(
                    "request_invalid_pdl1_flag",
                    "PD-L1列只能填写Y或N",
                    row=row_number,
                    value=pdl1,
                )
            )
        if has_material_column and not material:
            issues.append(
                _issue(
                    "request_empty_material",
                    "需索要材料列不得为空",
                    row=row_number,
                )
            )
        if has_legacy_excel_column and has_excel not in YES_NO:
            issues.append(
                _issue(
                    "request_invalid_excel_flag",
                    "已有Excel列只能填写Y或N",
                    row=row_number,
                    value=has_excel,
                )
            )
        normalized_rows.append(
            {
                "row": row_number,
                "sample_id": sample_id,
                "spec": spec,
                "pdl1": pdl1,
                "has_excel": has_excel,
                "material": material,
            }
        )

    inventory_count: int | None = None
    if inventory_path is not None:
        inventory_headers, inventory_rows = _read_tsv(inventory_path)
        inventory_count = len(inventory_rows)
        inventory_missing = _missing_columns(inventory_headers, INVENTORY_COLUMNS)
        if inventory_missing:
            issues.append(
                _issue(
                    "inventory_schema_missing_columns",
                    "肺癌逐报告台账缺少必需列",
                    columns=inventory_missing,
                )
            )
        else:
            inventory_index: dict[tuple[str, str, str], list[dict[str, str]]] = {}
            for row in inventory_rows:
                key = (
                    _sample_id(row.get("sample_id", "")),
                    _spec(row.get("spec", "")),
                    _yn(row.get("pdl1", "")),
                )
                inventory_index.setdefault(key, []).append(row)

            for row in normalized_rows:
                if not row["sample_id"] or row["pdl1"] not in YES_NO:
                    continue
                key = (row["sample_id"], row["spec"], row["pdl1"])
                matches = inventory_index.get(key, [])
                if not matches:
                    issues.append(
                        _issue(
                            "request_not_in_inventory",
                            "索要项未在肺癌逐报告台账中找到同规格记录",
                            row=row["row"],
                            sample_id=row["sample_id"],
                            spec=row["spec"],
                            pdl1=row["pdl1"],
                        )
                    )
                    continue
                if any(_yn(match.get("has_excel", "")) == "Y" for match in matches):
                    issues.append(
                        _issue(
                            "request_already_has_excel",
                            "索要项在逐报告台账中已登记配套Excel",
                            row=row["row"],
                            sample_id=row["sample_id"],
                        )
                    )

    pdl1_count = sum(row["pdl1"] == "Y" for row in normalized_rows)
    result = {
        "status": "PASS" if not issues else "FAIL",
        "request_file": request_path.name,
        "inventory_file": inventory_path.name if inventory_path else None,
        "request_row_count": len(request_rows),
        "unique_sample_count": len(seen),
        "pdl1_case_count": pdl1_count,
        "non_pdl1_case_count": len(request_rows) - pdl1_count,
        "inventory_row_count": inventory_count,
        "issue_count": len(issues),
        "issues": issues,
        "privacy": {
            "patient_names_emitted": False,
            "source_filenames_emitted": False,
            "sample_ids_emitted_only_on_error": True,
        },
    }
    return result


def _render_text(result: dict[str, Any]) -> str:
    lines = [
        f"status={result['status']}",
        f"request_rows={result['request_row_count']}",
        f"unique_samples={result['unique_sample_count']}",
        f"pdl1_cases={result['pdl1_case_count']}",
        f"non_pdl1_cases={result['non_pdl1_case_count']}",
        f"issues={result['issue_count']}",
    ]
    for issue in result["issues"]:
        details = " ".join(
            f"{key}={value}"
            for key, value in issue.items()
            if key not in {"code", "message"}
        )
        lines.append(
            f"- {issue['code']}: {issue['message']}"
            + (f" ({details})" if details else "")
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_list", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    result = validate_request_list(
        args.request_list.resolve(),
        inventory_path=args.inventory.resolve() if args.inventory else None,
        expected_count=args.expected_count,
    )
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_render_text(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
