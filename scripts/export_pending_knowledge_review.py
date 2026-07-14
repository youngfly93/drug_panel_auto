#!/usr/bin/env python3
# 步骤: 导出知识库二审队列
# 上游: Panel overlay 与药物规则治理字段
# 输出: TSV 二审工作队列（默认 .work/knowledge_review/）
# 种子: NA
"""Export runtime-eligible provisional knowledge for report-group review."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reportgen.knowledge.governance import effective_governance  # noqa: E402
from reportgen.panels.loader import PanelPackageLoader  # noqa: E402


def _rows(root: Path, panel_id: str) -> list[dict[str, str]]:
    package = PanelPackageLoader(project_root=root).load(panel_id)
    raw = package.raw or {}
    paths = []
    if raw.get("reviewed_part3_overlay"):
        paths.append(package._resolve_path(raw["reviewed_part3_overlay"]))
    additions = raw.get("reviewed_part3_overlay_additions") or []
    if isinstance(additions, str):
        additions = [additions]
    paths.extend(package._resolve_path(value) for value in additions)
    output: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for path in paths:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for kind, section in (("gene", "gene_sections"), ("drug", "drug_sections")):
            for index, row in enumerate(data.get(section) or [], start=1):
                if not isinstance(row, dict):
                    continue
                governance = effective_governance(data, row, kind)
                if governance["status"] not in {"provisional_runtime", "needs_review"}:
                    continue
                key = (
                    panel_id,
                    kind,
                    str(row.get("gene") or ""),
                    str(row.get("c_hgvs") or ""),
                    str(row.get("p_hgvs") or ""),
                    str(row.get("drug_name") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                output.append(
                    {
                        "panel_id": panel_id,
                        "kind": kind,
                        "gene": key[2],
                        "c_hgvs": key[3],
                        "p_hgvs": key[4],
                        "drug_name": key[5],
                        "review_status": governance["status"],
                        "risk_level": governance["risk_level"],
                        "evidence_level": governance["evidence_level"],
                        "cancer_scope": governance["cancer_scope"],
                        "secondary_review_status": governance[
                            "secondary_review_status"
                        ],
                        "source_refs": json.dumps(
                            governance["source_refs"], ensure_ascii=False
                        ),
                        "source_file": str(path.relative_to(root)),
                        "source_row": str(index),
                    }
                )
    drugs_path = package.resolve_rule_file("drugs")
    drugs_data = yaml.safe_load(drugs_path.read_text(encoding="utf-8")) or {}
    policy = drugs_data.get("targeted_drug_rules") or {}
    source_panel_id = str(policy.get("source_panel_id") or "")
    if source_panel_id:
        source_package = PanelPackageLoader(project_root=root).load(source_panel_id)
        drugs_path = source_package.resolve_rule_file("drugs")
        drugs_data = yaml.safe_load(drugs_path.read_text(encoding="utf-8")) or {}
        policy = drugs_data.get("targeted_drug_rules") or {}
    targeted_rows = [
        {"gene": gene, **dict(rule)}
        for gene, rule in (policy.get("overrides") or {}).items()
        if isinstance(rule, dict)
    ]
    targeted_rows.extend(
        dict(row)
        for row in policy.get("reviewed_variant_overrides") or []
        if isinstance(row, dict)
    )
    for index, row in enumerate(targeted_rows, start=1):
        governance = effective_governance(drugs_data, row, "targeted_drug")
        if governance["status"] not in {"provisional_runtime", "needs_review"}:
            continue
        key = (
            panel_id,
            "targeted_drug",
            str(row.get("gene") or ""),
            str(row.get("c_hgvs") or ""),
            str(row.get("p_hgvs") or ""),
            "",
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "panel_id": panel_id,
                "kind": "targeted_drug",
                "gene": key[2],
                "c_hgvs": key[3],
                "p_hgvs": key[4],
                "drug_name": "",
                "review_status": governance["status"],
                "risk_level": governance["risk_level"],
                "evidence_level": governance["evidence_level"],
                "cancer_scope": governance["cancer_scope"],
                "secondary_review_status": governance[
                    "secondary_review_status"
                ],
                "source_refs": json.dumps(
                    governance["source_refs"], ensure_ascii=False
                ),
                "source_file": str(drugs_path.relative_to(root)),
                "source_row": str(index),
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--panel", action="append", dest="panels", default=[]
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".work/knowledge_review/pending_secondary_review.tsv"),
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    panels = args.panels or ["crc_301_msi", "crc_358_msi"]
    rows = [row for panel in panels for row in _rows(root, panel)]
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["panel_id"]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print(f"rows={len(rows)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
