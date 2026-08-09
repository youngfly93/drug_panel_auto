"""Runtime validation for Panel-declared Excel table and column contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _value(source: Any, name: str, default: Any) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _normalized(value: Any) -> str:
    return str(value or "").strip().casefold()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _table_index(excel_data: Any) -> dict[str, str]:
    names: list[Any] = list(_value(excel_data, "sheet_names", []) or [])
    table_data = _value(excel_data, "table_data", {}) or {}
    if isinstance(table_data, Mapping):
        names.extend(table_data)
    metadata = _value(excel_data, "metadata", {}) or {}
    table_columns = (
        metadata.get("table_columns", {}) if isinstance(metadata, Mapping) else {}
    )
    if isinstance(table_columns, Mapping):
        names.extend(table_columns)

    result: dict[str, str] = {}
    for name in names:
        text = str(name or "").strip()
        if text:
            result.setdefault(_normalized(text), text)
    return result


def _table_rows(excel_data: Any, table_name: str) -> list[Any]:
    table_data = _value(excel_data, "table_data", {}) or {}
    if not isinstance(table_data, Mapping):
        return []
    wanted = _normalized(table_name)
    for name, rows in table_data.items():
        if _normalized(name) == wanted and isinstance(rows, list):
            return rows
    return []


def _table_columns(excel_data: Any, table_name: str) -> set[str]:
    columns: set[str] = set()
    metadata = _value(excel_data, "metadata", {}) or {}
    table_columns = (
        metadata.get("table_columns", {}) if isinstance(metadata, Mapping) else {}
    )
    if isinstance(table_columns, Mapping):
        wanted = _normalized(table_name)
        for name, values in table_columns.items():
            if _normalized(name) == wanted:
                columns.update(_normalized(value) for value in _string_list(values))

    for row in _table_rows(excel_data, table_name):
        if isinstance(row, Mapping):
            columns.update(_normalized(key) for key in row if _normalized(key))
    return columns


def validate_excel_input_contract(
    excel_data: Any,
    input_contract: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return safe, structural failures for required sheets and columns.

    Only configured table/column names are returned. Patient values, filenames,
    and row contents are never included in the validation payload.
    """

    if not isinstance(input_contract, Mapping) or not input_contract:
        return []

    failures: list[dict[str, Any]] = []
    table_index = _table_index(excel_data)
    required_tables = _string_list(input_contract.get("required_tables"))

    for table in required_tables:
        if _normalized(table) not in table_index:
            failures.append(
                {
                    "code": "REQUIRED_TABLE_MISSING",
                    "table": table,
                    "columns": [],
                }
            )

    required_columns = input_contract.get("required_columns") or {}
    if isinstance(required_columns, Mapping):
        for table, raw_columns in required_columns.items():
            table_name = str(table or "").strip()
            if not table_name or _normalized(table_name) not in table_index:
                continue
            observed = _table_columns(excel_data, table_name)
            for column in _string_list(raw_columns):
                if _normalized(column) not in observed:
                    failures.append(
                        {
                            "code": "REQUIRED_COLUMN_MISSING",
                            "table": table_name,
                            "columns": [column],
                        }
                    )

    required_any_columns = input_contract.get("required_any_columns") or {}
    if isinstance(required_any_columns, Mapping):
        for table, raw_columns in required_any_columns.items():
            table_name = str(table or "").strip()
            columns = _string_list(raw_columns)
            if (
                not table_name
                or not columns
                or _normalized(table_name) not in table_index
            ):
                continue
            observed = _table_columns(excel_data, table_name)
            if not any(_normalized(column) in observed for column in columns):
                failures.append(
                    {
                        "code": "REQUIRED_ANY_COLUMN_MISSING",
                        "table": table_name,
                        "columns": columns,
                    }
                )

    return failures


def describe_input_contract_failure(failure: Mapping[str, Any]) -> str:
    """Format one safe structural failure for logs or API errors."""

    code = str(failure.get("code") or "")
    table = str(failure.get("table") or "").strip()
    columns = _string_list(failure.get("columns"))
    if code == "REQUIRED_TABLE_MISSING":
        return f"缺少工作表 {table}"
    if code == "REQUIRED_ANY_COLUMN_MISSING":
        return f"工作表 {table} 至少需要一列：{' / '.join(columns)}"
    if code == "REQUIRED_COLUMN_MISSING":
        return f"工作表 {table} 缺少列 {columns[0] if columns else ''}"
    return f"工作表 {table} 不满足输入契约"


def input_contract_failures_as_missing(
    failures: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Adapt structural failures to the Web preflight's missing-field shape."""

    missing: list[dict[str, str]] = []
    for index, failure in enumerate(failures, start=1):
        table = str(failure.get("table") or "").strip()
        columns = _string_list(failure.get("columns"))
        code = str(failure.get("code") or "INPUT_CONTRACT_FAILURE")
        identity = ":".join([code, table, *columns]) or f"failure:{index}"
        missing.append(
            {
                "field": identity,
                "label": describe_input_contract_failure(failure),
            }
        )
    return missing
