"""Pre-render context contract checks.

These checks validate the structured template context before DOCX rendering.
They are intentionally independent from any one template, so a panel can catch
wrong counts, biomarker summaries, or table rows before the Word layout layer
turns bad data into a polished report.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import yaml

from reportgen.utils.artifacts import write_json


MISSING = object()
PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"


def load_context_contract(path: str | Path) -> Dict[str, Any]:
    """Load a context contract from YAML or JSON."""
    contract_path = Path(path)
    with contract_path.open("r", encoding="utf-8") as handle:
        if contract_path.suffix.lower() == ".json":
            raw = json.load(handle)
        else:
            raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, Mapping):
        raise ValueError(f"context contract must be a dict: {contract_path}")
    return dict(raw)


def write_context_contract_report(report: Mapping[str, Any], path: str | Path) -> str:
    """Write a context contract report as JSON and return the path."""
    output_path = Path(path)
    write_json(output_path, dict(report))
    return str(output_path)


def check_context_contract(
    context: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    contract_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Evaluate a context dict against a declarative contract."""
    if not isinstance(context, Mapping):
        raise TypeError("context must be a mapping")
    if not isinstance(contract, Mapping):
        raise TypeError("contract must be a mapping")

    checks: List[Dict[str, Any]] = []
    severity_default = _normalize_severity(contract.get("severity_default"), FAIL)

    def add_check(
        check_id: str,
        passed: bool,
        message: str,
        *,
        severity: Optional[str] = None,
        expected: Any = None,
        actual: Any = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        level = _normalize_severity(severity, severity_default)
        status = PASS if passed else (WARN if level == WARN else FAIL)
        if level == SKIP:
            status = SKIP
        row: Dict[str, Any] = {
            "id": check_id,
            "status": status,
            "severity": level,
            "message": message,
        }
        if expected is not None:
            row["expected"] = expected
        if actual is not None:
            row["actual"] = _jsonable(actual)
        if details:
            row["details"] = _jsonable(dict(details))
        checks.append(row)

    _check_fields(context, contract.get("fields"), add_check)
    _check_tables(context, contract.get("tables"), add_check)

    summary = {
        "checks": len(checks),
        "pass": sum(1 for item in checks if item["status"] == PASS),
        "warn": sum(1 for item in checks if item["status"] == WARN),
        "fail": sum(1 for item in checks if item["status"] == FAIL),
        "skip": sum(1 for item in checks if item["status"] == SKIP),
    }
    status = FAIL if summary["fail"] else (WARN if summary["warn"] else PASS)
    return {
        "schema_version": "1.0",
        "status": status,
        "contract_id": contract.get("contract_id"),
        "panel_id": contract.get("panel_id"),
        "contract_path": str(contract_path) if contract_path else None,
        "summary": summary,
        "checks": checks,
    }


def assert_context_contract(
    context: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    contract_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Run the contract and raise AssertionError when it fails."""
    report = check_context_contract(
        context,
        contract,
        contract_path=contract_path,
    )
    if report["status"] == FAIL:
        failed = [item for item in report["checks"] if item["status"] == FAIL]
        excerpt = "; ".join(f"{item['id']}: {item['message']}" for item in failed[:5])
        raise AssertionError(f"context contract failed: {excerpt}")
    return report


def _check_fields(context: Mapping[str, Any], fields: Any, add_check) -> None:
    if fields is None:
        return
    if not isinstance(fields, Mapping):
        add_check(
            "fields",
            False,
            "fields must be a mapping",
            expected="mapping",
            actual=type(fields).__name__,
        )
        return

    for path, spec in fields.items():
        field_path = str(path)
        value = _resolve_path(context, field_path)
        passed, message = _evaluate_value(value, spec)
        add_check(
            f"field:{field_path}",
            passed,
            message,
            severity=_spec_severity(spec),
            expected=_spec_expected(spec),
            actual=None if value is MISSING else value,
        )


def _check_tables(context: Mapping[str, Any], tables: Any, add_check) -> None:
    if tables is None:
        return
    if not isinstance(tables, Mapping):
        add_check(
            "tables",
            False,
            "tables must be a mapping",
            expected="mapping",
            actual=type(tables).__name__,
        )
        return

    for table_name, spec in tables.items():
        name = str(table_name)
        table = _resolve_path(context, name)
        if table is MISSING:
            table = _resolve_path(context, f"tables.{name}")
        if not isinstance(spec, Mapping):
            spec = {"row_count": spec}
        if not isinstance(table, list):
            add_check(
                f"table:{name}:present",
                False,
                f"table {name!r} is missing or not a list",
                severity=_spec_severity(spec),
                expected="list",
                actual=None if table is MISSING else type(table).__name__,
            )
            continue
        add_check(
            f"table:{name}:present",
            True,
            f"table {name!r} is present",
            severity=_spec_severity(spec),
            actual=len(table),
        )
        _check_table_counts(name, table, spec, add_check)
        _check_required_rows(name, table, spec.get("rows"), add_check)
        _check_forbidden_rows(name, table, spec.get("forbid_rows"), add_check)


def _check_table_counts(
    table_name: str,
    table: Sequence[Any],
    spec: Mapping[str, Any],
    add_check,
) -> None:
    severity = _spec_severity(spec)
    count = len(table)
    if "row_count" in spec:
        expected = spec.get("row_count")
        passed = _equal(count, expected)
        add_check(
            f"table:{table_name}:row_count",
            passed,
            f"table {table_name!r} row count is {count}",
            severity=severity,
            expected=expected,
            actual=count,
        )
    if "min_row_count" in spec:
        expected = spec.get("min_row_count")
        passed = _compare_number(count, expected, ">=")
        add_check(
            f"table:{table_name}:min_row_count",
            passed,
            f"table {table_name!r} row count is at least {expected}",
            severity=severity,
            expected=expected,
            actual=count,
        )
    if "max_row_count" in spec:
        expected = spec.get("max_row_count")
        passed = _compare_number(count, expected, "<=")
        add_check(
            f"table:{table_name}:max_row_count",
            passed,
            f"table {table_name!r} row count is at most {expected}",
            severity=severity,
            expected=expected,
            actual=count,
        )


def _check_required_rows(
    table_name: str,
    table: Sequence[Any],
    rows: Any,
    add_check,
) -> None:
    if rows is None:
        return
    if not isinstance(rows, list):
        add_check(
            f"table:{table_name}:rows",
            False,
            "rows must be a list",
            expected="list",
            actual=type(rows).__name__,
        )
        return

    for idx, row_spec in enumerate(rows, start=1):
        if not isinstance(row_spec, Mapping):
            add_check(
                f"table:{table_name}:row:{idx}",
                False,
                "row expectation must be a mapping",
                expected="mapping",
                actual=type(row_spec).__name__,
            )
            continue
        check_id = str(row_spec.get("id") or idx)
        match_spec = row_spec.get("match") or {}
        candidates = [
            item
            for item in table
            if isinstance(item, Mapping) and _row_matches(item, match_spec)
        ]
        if not candidates:
            add_check(
                f"table:{table_name}:row:{check_id}",
                False,
                f"required row {check_id!r} was not found",
                severity=_spec_severity(row_spec),
                expected={"match": match_spec},
                actual=[],
            )
            continue
        if _row_expectations_empty(row_spec):
            add_check(
                f"table:{table_name}:row:{check_id}",
                True,
                f"required row {check_id!r} was found",
                severity=_spec_severity(row_spec),
                expected={"match": match_spec},
                actual=candidates[0],
            )
            continue
        matched = [item for item in candidates if _row_expectations_pass(item, row_spec)]
        add_check(
            f"table:{table_name}:row:{check_id}",
            bool(matched),
            f"required row {check_id!r} matches expected values",
            severity=_spec_severity(row_spec),
            expected=_row_expected(row_spec),
            actual=matched[0] if matched else candidates[:3],
        )


def _check_forbidden_rows(
    table_name: str,
    table: Sequence[Any],
    rows: Any,
    add_check,
) -> None:
    if rows is None:
        return
    if not isinstance(rows, list):
        add_check(
            f"table:{table_name}:forbid_rows",
            False,
            "forbid_rows must be a list",
            expected="list",
            actual=type(rows).__name__,
        )
        return

    for idx, row_spec in enumerate(rows, start=1):
        if not isinstance(row_spec, Mapping):
            add_check(
                f"table:{table_name}:forbid_row:{idx}",
                False,
                "forbidden row expectation must be a mapping",
                expected="mapping",
                actual=type(row_spec).__name__,
            )
            continue
        check_id = str(row_spec.get("id") or idx)
        match_spec = row_spec.get("match")
        if match_spec is None:
            match_spec = {
                key: value
                for key, value in row_spec.items()
                if key not in {"id", "severity", "message"}
            }
        matches = [
            item
            for item in table
            if isinstance(item, Mapping) and _row_matches(item, match_spec)
        ]
        add_check(
            f"table:{table_name}:forbid_row:{check_id}",
            not matches,
            f"forbidden row {check_id!r} is absent",
            severity=_spec_severity(row_spec),
            expected={"absent": match_spec},
            actual=matches[:3],
        )


def _row_matches(row: Mapping[str, Any], match_spec: Any) -> bool:
    if not match_spec:
        return True
    if not isinstance(match_spec, Mapping):
        return False
    for path, expected in match_spec.items():
        value = _resolve_path(row, str(path))
        passed, _ = _evaluate_value(value, expected)
        if not passed:
            return False
    return True


def _row_expectations_empty(row_spec: Mapping[str, Any]) -> bool:
    return not any(key in row_spec for key in ("expect", "contains", "not_contains"))


def _row_expectations_pass(row: Mapping[str, Any], row_spec: Mapping[str, Any]) -> bool:
    for path, spec in (row_spec.get("expect") or {}).items():
        passed, _ = _evaluate_value(_resolve_path(row, str(path)), spec)
        if not passed:
            return False
    for path, spec in (row_spec.get("contains") or {}).items():
        passed, _ = _evaluate_value(_resolve_path(row, str(path)), {"contains": spec})
        if not passed:
            return False
    for path, spec in (row_spec.get("not_contains") or {}).items():
        passed, _ = _evaluate_value(
            _resolve_path(row, str(path)),
            {"not_contains": spec},
        )
        if not passed:
            return False
    return True


def _row_expected(row_spec: Mapping[str, Any]) -> Dict[str, Any]:
    expected: Dict[str, Any] = {}
    for key in ("match", "expect", "contains", "not_contains"):
        if key in row_spec:
            expected[key] = row_spec[key]
    return expected


def _evaluate_value(value: Any, spec: Any) -> tuple[bool, str]:
    if not isinstance(spec, Mapping):
        if value is MISSING:
            return False, "value is missing"
        return _equal(value, spec), "value equals expected"

    required = bool(spec.get("required", True))
    if value is MISSING:
        if not required:
            return True, "optional value is missing"
        return False, "value is missing"

    checks: List[tuple[bool, str]] = []
    if "equals" in spec:
        checks.append((_equal(value, spec["equals"]), "value equals expected"))
    if "not_equals" in spec:
        checks.append((not _equal(value, spec["not_equals"]), "value differs from blocked value"))
    if "in" in spec:
        allowed = spec.get("in") or []
        checks.append((any(_equal(value, item) for item in allowed), "value is in allowed set"))
    if "contains" in spec:
        checks.append((_contains_all(value, spec["contains"]), "value contains required text"))
    if "not_contains" in spec:
        checks.append(
            (
                _contains_none(value, spec["not_contains"]),
                "value does not contain blocked text",
            )
        )
    if "regex" in spec:
        checks.append((_matches_regex(value, spec["regex"]), "value matches regex"))
    if "min" in spec:
        checks.append((_compare_number(value, spec["min"], ">="), "value is above minimum"))
    if "max" in spec:
        checks.append((_compare_number(value, spec["max"], "<="), "value is below maximum"))
    if not checks:
        return True, "value is present"
    failed = [message for passed, message in checks if not passed]
    return not failed, "; ".join(failed) if failed else "; ".join(m for _, m in checks)


def _resolve_path(root: Any, path: str) -> Any:
    if isinstance(root, Mapping) and path in root:
        return root[path]
    current = root
    for part in path.split("."):
        if isinstance(current, Mapping):
            if part in current:
                current = current[part]
                continue
            return MISSING
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if 0 <= index < len(current):
                current = current[index]
                continue
        return MISSING
    return current


def _spec_severity(spec: Any) -> Optional[str]:
    if isinstance(spec, Mapping) and spec.get("severity"):
        return str(spec.get("severity"))
    return None


def _spec_expected(spec: Any) -> Any:
    if not isinstance(spec, Mapping):
        return spec
    for key in (
        "equals",
        "not_equals",
        "in",
        "contains",
        "not_contains",
        "regex",
        "min",
        "max",
    ):
        if key in spec:
            return {key: spec[key]}
    return {"required": spec.get("required", True)}


def _normalize_severity(value: Any, default: str = FAIL) -> str:
    text = str(value or default).strip().lower()
    if text in {"warn", "warning"}:
        return WARN
    if text in {"skip", "off", "disabled"}:
        return SKIP
    return FAIL


def _equal(actual: Any, expected: Any) -> bool:
    if actual == expected:
        return True
    return str(actual).strip() == str(expected).strip()


def _contains_all(actual: Any, expected: Any) -> bool:
    text = _stringify(actual)
    return all(str(item) in text for item in _as_list(expected))


def _contains_none(actual: Any, expected: Any) -> bool:
    text = _stringify(actual)
    return all(str(item) not in text for item in _as_list(expected))


def _matches_regex(actual: Any, pattern: Any) -> bool:
    try:
        return re.search(str(pattern), _stringify(actual)) is not None
    except re.error:
        return False


def _compare_number(actual: Any, expected: Any, op: str) -> bool:
    try:
        actual_num = float(actual)
        expected_num = float(expected)
    except (TypeError, ValueError):
        return False
    if op == ">=":
        return actual_num >= expected_num
    if op == "<=":
        return actual_num <= expected_num
    raise ValueError(f"unsupported numeric comparison: {op}")


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _stringify(value: Any) -> str:
    if value is MISSING or value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return "\n".join(_stringify(item) for item in value)
    return str(value)


def _jsonable(value: Any) -> Any:
    if value is MISSING:
        return None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
