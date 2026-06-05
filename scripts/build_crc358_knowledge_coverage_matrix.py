#!/usr/bin/env python3
"""Build a CRC358 knowledge coverage matrix.

This workbook is a planning/audit artifact. It does not change production
knowledge. It combines the template gene list, Part3 reviewed overlay, base
gene KB, targeted drug KB, immune KB, and pressure-test gap workbook.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from docx import Document
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reportgen.knowledge.gene_knowledge import GeneKnowledgeProvider


GENE_RE = re.compile(r"^[A-Z][A-Z0-9-]{1,15}$")


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def _is_gene(value: Any) -> bool:
    text = _clean(value).upper()
    return bool(GENE_RE.match(text)) and text not in {"GENE", "LIST", "MLSEQ"}


def _extract_template_gene_list(template_docx: Path) -> list[str]:
    doc = Document(template_docx)
    best: list[str] = []
    for table in doc.tables:
        first_row = " ".join(cell.text for cell in table.rows[0].cells) if table.rows else ""
        if "Gene List for MLseq" not in first_row and "n=358" not in first_row:
            continue
        genes: list[str] = []
        for row in table.rows[1:]:
            for cell in row.cells:
                gene = _clean(cell.text).upper()
                if _is_gene(gene):
                    genes.append(gene)
        # Preserve template order while removing duplicate cells caused by Word
        # merged-cell quirks.
        ordered = []
        seen = set()
        for gene in genes:
            if gene not in seen:
                seen.add(gene)
                ordered.append(gene)
        if len(ordered) > len(best):
            best = ordered
    return best


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_provider(project_root: Path) -> GeneKnowledgeProvider:
    settings = _load_yaml(project_root / "config/settings.yaml")
    gene_cfg = dict(settings["knowledge_bases"]["gene_knowledge_db"])
    gene_cfg["reviewed_part3_overlay_path"] = (
        "panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml"
    )
    provider = GeneKnowledgeProvider(
        {
            "enabled": True,
            "gene_knowledge_db": gene_cfg,
            "gene_transcript_db": {"enabled": False},
        }
    )
    provider.load(str(project_root))
    return provider


def _overlay_variant_counts(provider: GeneKnowledgeProvider) -> Counter[str]:
    counts: Counter[str] = Counter()
    for key in provider._reviewed_gene_section_overrides:
        gene = key.split("|", 1)[0]
        counts[gene] += 1
    return counts


def _load_crc_rule_sets(path: Path) -> dict[str, set[str]]:
    data = _load_yaml(path)
    return {
        "class_i": {str(x).upper() for x in data.get("class_i_genes") or []},
        "class_ii": {str(x).upper() for x in data.get("class_ii_genes") or []},
        "important": {str(x).upper() for x in data.get("crc_important_genes") or []},
        "drug_override": {
            str(row.get("gene", "")).upper()
            for row in data.get("reviewed_variant_overrides") or []
            if row.get("gene")
        },
    }


def _load_targeted_drug_counts(path: Path) -> dict[str, Counter[str]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    if not path.exists():
        return counts
    df = pd.read_excel(path, sheet_name="targeted_drug_tips")
    for _, row in df.iterrows():
        gene = _clean(row.get("基因名称")).upper()
        if not _is_gene(gene):
            continue
        benefit = _clean(row.get("潜在获益靶向药物（证据等级）"))
        caution = _clean(row.get("可能耐药或慎重药物（证据等级）"))
        source = _clean(row.get("source_db")) or "unknown"
        counts[gene]["total"] += 1
        counts[gene][f"source:{source}"] += 1
        if benefit and benefit not in {"--", "-"}:
            counts[gene]["benefit"] += 1
        if caution and caution not in {"--", "-"}:
            counts[gene]["caution"] += 1
    return counts


def _load_immune_sets(path: Path) -> dict[str, set[str]]:
    result = {"positive": set(), "negative": set(), "hyper": set()}
    if not path.exists():
        return result
    df = pd.read_excel(path, sheet_name="immune_gene_list")
    col_map = {
        "positive": "免疫治疗正相关基因",
        "negative": "免疫治疗负相关基因",
        "hyper": "免疫超进展相关基因",
    }
    for key, col in col_map.items():
        if col not in df.columns:
            continue
        for value in df[col].dropna():
            gene = _clean(value).upper()
            if _is_gene(gene):
                result[key].add(gene)
    return result


def _load_gap_counts(path: Path | None) -> dict[str, Counter[str]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    if not path or not path.exists():
        return counts
    wb = load_workbook(path)
    if "缺口明细" in wb.sheetnames:
        ws = wb["缺口明细"]
        headers = [_clean(c.value) for c in ws[1]]
        idx = {h: i for i, h in enumerate(headers)}
        for row in ws.iter_rows(min_row=2, values_only=True):
            gene = _clean(row[idx.get("基因", -1)]).upper() if "基因" in idx else ""
            if not _is_gene(gene):
                continue
            counts[gene]["pressure_variants"] += 1
            risk = _clean(row[idx.get("固定套话风险", -1)]) if "固定套话风险" in idx else ""
            priority = _clean(row[idx.get("优先级", -1)]) if "优先级" in idx else ""
            status = _clean(row[idx.get("覆盖状态", -1)]) if "覆盖状态" in idx else ""
            if risk == "高":
                counts[gene]["high_risk"] += 1
            if priority:
                counts[gene][f"priority:{priority}"] += 1
            if status:
                counts[gene][f"status:{status}"] += 1
    if "待审核候选内容" in wb.sheetnames:
        ws = wb["待审核候选内容"]
        headers = [_clean(c.value) for c in ws[1]]
        idx = {h: i for i, h in enumerate(headers)}
        for row in ws.iter_rows(min_row=2, values_only=True):
            gene = _clean(row[idx.get("基因", -1)]).upper() if "基因" in idx else ""
            if _is_gene(gene):
                counts[gene]["review_candidates"] += 1
    return counts


def _part3_level(
    *,
    gene: str,
    provider: GeneKnowledgeProvider,
    variant_count: int,
) -> str:
    gene_key = provider._hgvs_key(gene)
    if variant_count:
        return "A 位点级已审核"
    if gene_key in provider._gene_level_section_overrides:
        return "B 基因级已审核"
    if gene in provider._reviewed_gene_analysis_cache:
        return "C 基础库可自动拼接"
    if gene in provider._gene_analysis_cache or gene in provider._gene_intro_cache:
        return "D 基础库通用"
    return "E 缺失"


def _suggestion(row: dict[str, Any]) -> str:
    level = row["Part3覆盖级别"]
    high = int(row["压测高风险次数"] or 0)
    p0p1 = int(row["P0/P1次数"] or 0)
    candidates = int(row["待审核候选数"] or 0)
    drug_total = int(row["靶向药物条目数"] or 0)
    if high and p0p1:
        return "优先补位点级/基因级内容，报告组审核后入库"
    if level == "E 缺失":
        return "补基因级兜底内容"
    if level == "D 基础库通用" and candidates:
        return "已有候选，待报告组审核升级"
    if level == "D 基础库通用":
        return "后续从历史报告补充肠癌语境"
    if level.startswith("C") and high:
        return "抽查拼接效果，必要时升级为已审核"
    if drug_total and not (row["免疫正相关"] or row["免疫负相关"] or row["免疫超进展相关"]):
        return "药物已有覆盖，按压测结果抽查"
    return "维持，后续按反馈补充"


def _append_table(ws, headers: list[str], rows: list[list[Any]]) -> None:
    ws.append(headers)
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in rows:
        ws.append(row)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"
    for idx, header in enumerate(headers, start=1):
        max_len = len(str(header))
        for col in ws.iter_cols(min_col=idx, max_col=idx, min_row=2):
            for cell in col:
                max_len = max(max_len, min(len(str(cell.value or "")), 60))
        ws.column_dimensions[get_column_letter(idx)].width = min(max(max_len + 2, 10), 34)


def build_matrix(
    *,
    project_root: Path,
    template_docx: Path,
    crc_rules: Path,
    targeted_drug_db: Path,
    immune_gene_db: Path,
    gap_xlsx: Path | None,
    output: Path,
) -> dict[str, Any]:
    genes = _extract_template_gene_list(template_docx)
    provider = _load_provider(project_root)
    rule_sets = _load_crc_rule_sets(crc_rules)
    variant_overlay_counts = _overlay_variant_counts(provider)
    targeted_counts = _load_targeted_drug_counts(targeted_drug_db)
    immune_sets = _load_immune_sets(immune_gene_db)
    gap_counts = _load_gap_counts(gap_xlsx)

    matrix_rows: list[dict[str, Any]] = []
    for order, gene in enumerate(genes, start=1):
        gene_key = provider._hgvs_key(gene)
        part3_level = _part3_level(
            gene=gene,
            provider=provider,
            variant_count=variant_overlay_counts.get(gene, 0),
        )
        groups = []
        if gene in rule_sets["class_i"]:
            groups.append("I类")
        if gene in rule_sets["class_ii"]:
            groups.append("II类")
        if gene in rule_sets["important"]:
            groups.append("CRC重点")
        if gene in rule_sets["drug_override"]:
            groups.append("药物人工规则")
        drug = targeted_counts.get(gene, Counter())
        gaps = gap_counts.get(gene, Counter())
        row = {
            "序号": order,
            "基因": gene,
            "分组": "、".join(groups) or "检测基因",
            "Part3覆盖级别": part3_level,
            "基因简介": "有" if gene in provider._gene_intro_cache else "缺",
            "基础库reviewed列": "有" if gene in provider._reviewed_gene_analysis_cache else "缺",
            "基础通用解析": "有" if gene in provider._gene_analysis_cache else "缺",
            "reviewed基因级": "有" if gene_key in provider._gene_level_section_overrides else "缺",
            "reviewed位点级数量": variant_overlay_counts.get(gene, 0),
            "靶向药物条目数": drug.get("total", 0),
            "获益条目数": drug.get("benefit", 0),
            "慎用/耐药条目数": drug.get("caution", 0),
            "免疫正相关": "是" if gene in immune_sets["positive"] else "",
            "免疫负相关": "是" if gene in immune_sets["negative"] else "",
            "免疫超进展相关": "是" if gene in immune_sets["hyper"] else "",
            "压测出现次数": gaps.get("pressure_variants", 0),
            "压测高风险次数": gaps.get("high_risk", 0),
            "P0/P1次数": gaps.get("priority:P0", 0) + gaps.get("priority:P1", 0),
            "P2次数": gaps.get("priority:P2", 0),
            "待审核候选数": gaps.get("review_candidates", 0),
        }
        row["建议动作"] = _suggestion(row)
        matrix_rows.append(row)

    level_counts = Counter(row["Part3覆盖级别"] for row in matrix_rows)
    no_intro = sum(1 for row in matrix_rows if row["基因简介"] == "缺")
    no_analysis = sum(1 for row in matrix_rows if row["基础通用解析"] == "缺")
    drug_gene_count = sum(1 for row in matrix_rows if row["靶向药物条目数"])
    immune_gene_count = sum(
        1
        for row in matrix_rows
        if row["免疫正相关"] or row["免疫负相关"] or row["免疫超进展相关"]
    )
    high_risk_gene_count = sum(1 for row in matrix_rows if row["压测高风险次数"])

    wb = Workbook()
    ws = wb.active
    ws.title = "汇总"
    summary = [
        ["矩阵基因数", len(matrix_rows)],
        ["来源", "金标模板 Gene List for MLseq (n=358)"],
        ["A 位点级已审核", level_counts.get("A 位点级已审核", 0)],
        ["B 基因级已审核", level_counts.get("B 基因级已审核", 0)],
        ["C 基础库可自动拼接", level_counts.get("C 基础库可自动拼接", 0)],
        ["D 基础库通用", level_counts.get("D 基础库通用", 0)],
        ["E 缺失", level_counts.get("E 缺失", 0)],
        ["缺基因简介", no_intro],
        ["缺基础通用解析", no_analysis],
        ["有靶向药物条目的基因", drug_gene_count],
        ["有免疫相关规则的基因", immune_gene_count],
        ["压测中出现高风险的基因", high_risk_gene_count],
        ["结论", "当前适合按P0/P1/高频反馈逐步补库；不建议宣称知识库已完整。"],
    ]
    _append_table(ws, ["指标", "结果"], summary)

    headers = list(matrix_rows[0].keys()) if matrix_rows else []
    ws2 = wb.create_sheet("CRC358覆盖矩阵")
    _append_table(ws2, headers, [[row[h] for h in headers] for row in matrix_rows])
    for row_idx in range(2, ws2.max_row + 1):
        level = ws2.cell(row_idx, headers.index("Part3覆盖级别") + 1).value
        fill = None
        if str(level).startswith("A"):
            fill = PatternFill("solid", fgColor="D9EAD3")
        elif str(level).startswith("B"):
            fill = PatternFill("solid", fgColor="E2F0D9")
        elif str(level).startswith("C"):
            fill = PatternFill("solid", fgColor="FFF2CC")
        elif str(level).startswith("D"):
            fill = PatternFill("solid", fgColor="FCE4D6")
        elif str(level).startswith("E"):
            fill = PatternFill("solid", fgColor="F4CCCC")
        if fill:
            for col_idx in range(1, ws2.max_column + 1):
                ws2.cell(row_idx, col_idx).fill = fill

    ws3 = wb.create_sheet("位点级覆盖清单")
    variant_rows = []
    for key, section in sorted(provider._reviewed_gene_section_overrides.items()):
        gene, c_hgvs, p_hgvs = (key.split("|") + ["", ""])[:3]
        variant_rows.append(
            [
                gene,
                c_hgvs,
                p_hgvs,
                "有" if section.get("intro") else "缺",
                "有" if section.get("mutation_analysis") else "缺",
                (section.get("mutation_analysis") or "")[:180],
            ]
        )
    _append_table(
        ws3,
        ["基因", "cHGVS", "pHGVS", "简介", "解析", "解析预览"],
        variant_rows,
    )

    ws4 = wb.create_sheet("补库优先级")
    priority_rows = []
    for row in matrix_rows:
        if (
            row["压测高风险次数"]
            or row["Part3覆盖级别"].startswith("E")
            or row["P0/P1次数"]
            or row["待审核候选数"]
        ):
            priority_rows.append(
                [
                    row["基因"],
                    row["Part3覆盖级别"],
                    row["压测高风险次数"],
                    row["P0/P1次数"],
                    row["P2次数"],
                    row["待审核候选数"],
                    row["建议动作"],
                ]
            )
    priority_rows.sort(key=lambda x: (-int(x[3] or 0), -int(x[2] or 0), str(x[1]), str(x[0])))
    _append_table(
        ws4,
        ["基因", "Part3覆盖级别", "压测高风险次数", "P0/P1次数", "P2次数", "待审核候选数", "建议动作"],
        priority_rows,
    )

    ws5 = wb.create_sheet("口径说明")
    _append_table(
        ws5,
        ["项目", "说明"],
        [
            ["A 位点级已审核", "reviewed_part3_knowledge.yaml 中有 gene+cHGVS/pHGVS 精确覆盖；只代表这些位点已审核。"],
            ["B 基因级已审核", "reviewed_part3_knowledge.yaml 中有 gene 级覆盖；适合兜底，但高频位点仍建议补位点级。"],
            ["C 基础库可自动拼接", "gene_knowledge_db.xlsx 中有 reviewed 列，可按位点类型自动拼接；需报告组抽查措辞。"],
            ["D 基础库通用", "只有通用简介/解析，容易显得像套话。"],
            ["E 缺失", "当前缺少可用 Part3 内容，需优先补基因级兜底。"],
            ["用途", "这张表用于补库排期、报告组审核和领导汇报，不会自动修改生产知识库。"],
        ],
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return {
        "gene_count": len(matrix_rows),
        "level_counts": dict(level_counts),
        "drug_gene_count": drug_gene_count,
        "immune_gene_count": immune_gene_count,
        "high_risk_gene_count": high_risk_gene_count,
        "output": str(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--template-docx",
        type=Path,
        default=Path("panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx"),
    )
    parser.add_argument(
        "--crc-rules",
        type=Path,
        default=Path("panels/crc_358_msi/rules/crc.yaml"),
    )
    parser.add_argument(
        "--targeted-drug-db",
        type=Path,
        default=Path("data/knowledge_bases/processed/targeted_drug_db_public.xlsx"),
    )
    parser.add_argument(
        "--immune-gene-db",
        type=Path,
        default=Path("data/knowledge_bases/processed/immune_gene_list_public.xlsx"),
    )
    parser.add_argument("--gap-xlsx", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_matrix(
        project_root=args.project_root.resolve(),
        template_docx=args.template_docx,
        crc_rules=args.crc_rules,
        targeted_drug_db=args.targeted_drug_db,
        immune_gene_db=args.immune_gene_db,
        gap_xlsx=args.gap_xlsx,
        output=args.output,
    )
    print(yaml.safe_dump(result, allow_unicode=True, sort_keys=False))


if __name__ == "__main__":
    main()
