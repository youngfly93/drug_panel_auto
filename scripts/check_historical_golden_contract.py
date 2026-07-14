#!/usr/bin/env python3
"""Check a DOCX against a committed de-identified historical contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.core.historical_golden_contract import (  # noqa: E402
    load_historical_golden_contract,
    validate_historical_golden_docx,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--docx", required=True)
    parser.add_argument("--require-reference-sha", action="store_true")
    parser.add_argument("--reference-docx")
    parser.add_argument("--output-json")
    args = parser.parse_args()

    contract = load_historical_golden_contract(args.contract)
    result = validate_historical_golden_docx(
        contract=contract,
        docx_path=args.docx,
        require_reference_sha=args.require_reference_sha,
        reference_docx_path=args.reference_docx,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
