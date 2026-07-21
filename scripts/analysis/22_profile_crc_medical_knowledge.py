# 步骤: 22_profile_crc_medical_knowledge
# 上游: CRC panel coverage/rules + panel-scoped runtime knowledge provider + targeted_drug_db_public.xlsx（只读）
# 输出: .work/crc_medical_knowledge/knowledge_depth_inventory.json
# 种子: 无（固定规则、基因名归一化与字典序排序）
"""Profile residual CRC medical-knowledge debt without editing source workbooks."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reportgen.core.template_bridge_358 import load_panel_config  # noqa: E402
from reportgen.knowledge.quality import profile_panel_runtime_content  # noqa: E402
from reportgen.panels.loader import PanelPackageLoader  # noqa: E402
from reportgen.rules.targeted_drugs import (  # noqa: E402
    load_targeted_drug_rule_context,
)


DEFAULT_PANELS = ("crc_301_msi", "crc_358_msi")


def _gene_tokens(value: Any) -> set[str]:
    return {
        token.strip().upper()
        for token in re.split(r"[\s,，、;/；]+", str(value or ""))
        if token.strip()
    }


def _base_targeted_drug_genes(root: Path) -> set[str]:
    settings = yaml.safe_load(
        (root / "config/settings.yaml").read_text(encoding="utf-8")
    ) or {}
    config = (
        (settings.get("knowledge_bases") or {}).get("targeted_drug_db") or {}
    )
    path = root / str(config.get("path") or "")
    sheet = str(config.get("sheet") or "targeted_drug_tips")
    if not path.is_file():
        raise FileNotFoundError(f"targeted-drug database not found: {path}")
    frame = pd.read_excel(path, sheet_name=sheet, dtype=str).fillna("")
    gene_column = next(
        (column for column in frame.columns if str(column).strip() == "基因名称"),
        None,
    )
    if gene_column is None:
        raise ValueError(f"targeted-drug gene column missing: {path}#{sheet}")
    genes: set[str] = set()
    for value in frame[gene_column]:
        genes.update(_gene_tokens(value))
    return genes


def _target_rule_genes(context: dict[str, Any]) -> set[str]:
    genes = {
        str(gene).strip().upper()
        for gene in (context.get("overrides") or {})
        if str(gene).strip()
    }
    for row in context.get("reviewed_variant_overrides") or []:
        genes.update(_gene_tokens(row.get("gene")))
    return genes


def _git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_inventory(root: Path, panel_ids: tuple[str, ...], as_of: str) -> dict[str, Any]:
    loader = PanelPackageLoader(project_root=root)
    base_drug_genes = _base_targeted_drug_genes(root)
    panels: list[dict[str, Any]] = []

    for panel_id in panel_ids:
        package = loader.load(panel_id)
        coverage = yaml.safe_load(
            package.resolve_rule_file("knowledge_coverage").read_text(
                encoding="utf-8"
            )
        ) or {}
        reportable = {
            str(gene).strip().upper()
            for gene in (coverage.get("reportable_genes") or [])
            if str(gene).strip()
        }
        profile = profile_panel_runtime_content(root, package, reportable)
        generic = set(profile["generic_fallback_genes"])
        panel_config = load_panel_config(base_path=root, panel_id=panel_id)
        display_genes = {
            str(row.get("name") or "").strip().upper()
            for row in panel_config.panel_display_genes
            if str(row.get("name") or "").strip()
        }
        important_genes = {
            str(gene).strip().upper()
            for gene in panel_config.crc_important_genes
            if str(gene).strip()
        }
        rule_context = load_targeted_drug_rule_context(package) or {}
        target_rule_genes = _target_rule_genes(rule_context)

        p0 = generic & (display_genes | target_rule_genes)
        p1 = (generic & important_genes) - p0
        p2 = (generic & base_drug_genes) - p0 - p1
        p3 = generic - p0 - p1 - p2
        panels.append(
            {
                "panel_id": panel_id,
                "total_genes": len(reportable),
                "complete_genes": profile["complete_genes"],
                "specific_explanation_genes": profile[
                    "specific_explanation_genes"
                ],
                "specific_explanation_percent": profile[
                    "specific_explanation_percent"
                ],
                "generic_fallback_count": profile["generic_fallback_count"],
                "generic_fallback_percent": profile["generic_fallback_percent"],
                "priority_residual": {
                    "P0_report_or_exact_rule_surface": sorted(p0),
                    "P1_crc_important": sorted(p1),
                    "P2_base_drug_candidate_gene": sorted(p2),
                    "P3_other_panel_gene": sorted(p3),
                },
                "citation_integrity": profile["citation_integrity"],
            }
        )

    return {
        "schema_version": "1.0",
        "as_of": as_of,
        "git_head": _git_head(root),
        "purpose": "residual_crc_medical_knowledge_depth_inventory",
        "classification": {
            "P0": "generic fallback still exposed on a panel display gene or exact targeted-drug rule gene",
            "P1": "generic fallback on a declared CRC-important gene",
            "P2": "generic fallback on a gene represented in the base targeted-drug candidate database",
            "P3": "remaining generic fallback; no automatic drug inference is permitted",
            "precedence": ["P0", "P1", "P2", "P3"],
        },
        "base_targeted_drug_unique_gene_count": len(base_drug_genes),
        "panels": panels,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--panels", nargs="+", default=list(DEFAULT_PANELS))
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".work/crc_medical_knowledge/knowledge_depth_inventory.json"),
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    payload = build_inventory(root, tuple(args.panels), args.as_of)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for panel in payload["panels"]:
        residual = panel["priority_residual"]
        print(
            panel["panel_id"],
            f"specific={panel['specific_explanation_genes']}/{panel['total_genes']}",
            f"generic={panel['generic_fallback_count']}",
            "priority="
            + "/".join(str(len(residual[key])) for key in residual),
        )
    print(f"output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
