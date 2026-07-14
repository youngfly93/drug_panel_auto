#!/usr/bin/env python3
# 步骤: 知识库发布门禁
# 上游: 生产 Panel overlay、药物规则、基础库 manifest 与知识 Excel
# 输出: JSON 发布门禁与多维覆盖率报告
# 种子: NA
"""Validate production knowledge governance without ignored review artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reportgen.knowledge.release_gate import run_knowledge_release_gate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--panel", action="append", dest="panels")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".work/knowledge_release/knowledge_release_gate.json"),
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = run_knowledge_release_gate(
        args.project_root,
        panel_ids=tuple(args.panels) if args.panels else None,
        output_path=args.output,
    )
    print(f"status={result['status']}")
    for panel in result["panels"]:
        coverage = panel["multidimensional_coverage"]
        print(
            f"{panel['panel_id']} status={panel['status']} "
            f"gene={coverage['gene_explanation']['percent']}% "
            f"review={coverage['review_governance']['standardized_percent']}% "
            f"sources={coverage['source_provenance']['structured_source_percent']}%"
        )
    print(f"issues={result['summary']['issues']}")
    print(f"output={result.get('report_file', args.output)}")
    if args.strict and result["status"] != "PASS":
        print(json.dumps(result["issues"][:20], ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
