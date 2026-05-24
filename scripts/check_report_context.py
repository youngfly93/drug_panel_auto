#!/usr/bin/env python3
"""Check a rendered report context JSON against a context contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.core.context_contract import (  # noqa: E402
    check_context_contract,
    load_context_contract,
    write_context_contract_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("context_json", help="Path to report context JSON")
    parser.add_argument("contract", help="Path to context contract YAML/JSON")
    parser.add_argument("--output", help="Optional JSON report output path")
    parser.add_argument(
        "--allow-warn",
        action="store_true",
        help="Exit 0 for WARN status. FAIL still exits non-zero.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    context_path = Path(args.context_json)
    contract_path = Path(args.contract)
    context = json.loads(context_path.read_text(encoding="utf-8"))
    contract = load_context_contract(contract_path)
    report = check_context_contract(
        context,
        contract,
        contract_path=contract_path,
    )
    if args.output:
        write_context_contract_report(report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] == "FAIL":
        return 1
    if report["status"] == "WARN" and not args.allow_warn:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

