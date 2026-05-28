#!/usr/bin/env python3
"""Template-Fit Analyzer.

Quantify how well a corpus of reports (.docx) fits an existing golden template,
so new-panel onboarding can choose the right base. See
``docs/template_fit_methodology.md`` for the algorithm and decision thresholds.

Output:
  - Per-report fit JSON (path, fit_score, section breakdown)
  - Per-family markdown brief (high/medium/low/novel sections + recommendation)

Usage:
  python -m scripts.template_fit_analyzer \\
      --golden panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx \\
      --corpus "<local corpus directory>" \\
      --family-hint Lung13 \\
      --output tmp/template_fit/lung13_fit.json \\
      --report tmp/template_fit/lung13_fit_brief.md
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Known section title patterns (CRC358-style; tolerant of "1. " / "二、" prefixes)
# ---------------------------------------------------------------------------

SECTION_PATTERNS: dict[str, re.Pattern] = {
    "报告导读": re.compile(r"^\s*(?:[\d一二三四五六七八九十]+[、.\.])?\s*报告导读"),
    "致患者信": re.compile(r"^\s*(?:致(?:您|你)的一封信|致患者信?|致(?:您|你)信)"),
    "检测结果小结": re.compile(r"^\s*(?:[\d]+[、.])?\s*检测结果小结"),
    "靶向药物相关": re.compile(r"^\s*(?:[\d.]+\s*)?靶向药物相关"),
    "免疫治疗": re.compile(r"^\s*(?:[\d.]+\s*)?(?:免疫治疗|免疫疗效)"),
    "检测结果说明": re.compile(r"^\s*(?:[\d]+[、.])?\s*检测结果说明"),
    "基因变异解析": re.compile(r"^\s*(?:[\d]+[、.])?\s*基因变异(?:及.*)?解析"),
    "阅读说明": re.compile(r"^\s*(?:[\d]+[、.])?\s*阅读说明"),
    "常见问题": re.compile(r"^\s*(?:[\d]+[、.])?\s*常见问题"),
    "诊疗知识": re.compile(r"^\s*(?:[\d]+[、.])?\s*(?:.*?诊疗知识)"),
    "信号通路": re.compile(r"^\s*(?:[\d]+[、.])?\s*(?:.*?信号通路|相关通路)"),
    "基因检测列表": re.compile(r"^\s*(?:[\d]+[、.])?\s*基因检测列表"),
    "参考文献": re.compile(r"^\s*(?:[\d]+[、.])?\s*参考文献"),
}

# Jinja/marker text — excluded from the "fixed paragraphs" set since they
# are intentionally variable.
JINJA_OR_MARKER_PATTERN = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|__[A-Z_]+__")


# ---------------------------------------------------------------------------
# Lightweight DOCX walker (raw XML; tolerates non-standard packages)
# ---------------------------------------------------------------------------

_P_OR_TBL = re.compile(r"<w:p\b[^>]*?>(.*?)</w:p>|<w:tbl\b[^>]*?>(.*?)</w:tbl>", re.DOTALL)
_TEXT = re.compile(r"<w:t[^>]*>([^<]*)</w:t>")
_TR = re.compile(r"<w:tr\b[^>]*?>(.*?)</w:tr>", re.DOTALL)
_TC = re.compile(r"<w:tc\b[^>]*?>(.*?)</w:tc>", re.DOTALL)


def _normalize(text: str) -> str:
    """Strip zero-width/nbsp chars and collapse whitespace."""
    if not text:
        return ""
    text = text.replace("​", "").replace("﻿", "").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_paragraphs_and_tables(docx_path: Path):
    """Yield ('p', text) and ('tbl', sig_dict) in document order."""
    try:
        with zipfile.ZipFile(docx_path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    except (zipfile.BadZipFile, KeyError):
        return
    for m in _P_OR_TBL.finditer(xml):
        if m.group(1) is not None:  # paragraph
            text = "".join(_TEXT.findall(m.group(1)))
            yield ("p", _normalize(text))
        else:  # table
            body = m.group(2)
            tr_m = _TR.search(body)
            if tr_m is None:
                continue
            header_cells = [
                _normalize("".join(_TEXT.findall(tc.group(1))))
                for tc in _TC.finditer(tr_m.group(1))
            ]
            yield (
                "tbl",
                {
                    "columns": len(header_cells),
                    "header_cells": header_cells,
                    "rows": len(_TR.findall(body)),
                },
            )


def match_section_title(text: str) -> str | None:
    """Return canonical section key for a paragraph that looks like a heading."""
    if not text or len(text) > 80:
        return None
    for canonical, pat in SECTION_PATTERNS.items():
        if pat.match(text):
            return canonical
    return None


# ---------------------------------------------------------------------------
# Golden template signature
# ---------------------------------------------------------------------------

@dataclass
class SectionSignature:
    title: str
    fixed_paragraphs: set[str] = field(default_factory=set)
    table_signatures: list[dict] = field(default_factory=list)


@dataclass
class TemplateSignature:
    sections: dict[str, SectionSignature]


def build_template_signature(template_path: Path) -> TemplateSignature:
    sections: dict[str, SectionSignature] = {}
    current: str | None = None
    for kind, content in extract_paragraphs_and_tables(template_path):
        if kind == "p":
            text = content
            matched = match_section_title(text)
            if matched:
                current = matched
                sections.setdefault(current, SectionSignature(title=current))
                continue
            if current and text and not JINJA_OR_MARKER_PATTERN.search(text):
                sections[current].fixed_paragraphs.add(text)
        elif kind == "tbl" and current:
            sections[current].table_signatures.append(
                {"columns": content["columns"], "header_cells": content["header_cells"]}
            )
    return TemplateSignature(sections=sections)


# ---------------------------------------------------------------------------
# Per-report fit scoring
# ---------------------------------------------------------------------------

@dataclass
class ReportFit:
    report_path: str
    fit_score: float
    section_hit_rate: float
    paragraph_jaccard_mean: float
    table_signature_match_rate: float
    matched_sections: list[str]
    missing_sections: list[str]
    novel_sections: list[str]
    section_jaccards: dict[str, float]


def analyze_report(report_path: Path, golden: TemplateSignature) -> ReportFit:
    report_secs: dict[str, dict] = {}
    current: str | None = None
    for kind, content in extract_paragraphs_and_tables(report_path):
        if kind == "p":
            text = content
            matched = match_section_title(text)
            if matched:
                current = matched
                report_secs.setdefault(current, {"paragraphs": set(), "tables": []})
                continue
            if current and text:
                report_secs[current]["paragraphs"].add(text)
        elif kind == "tbl" and current:
            report_secs.setdefault(current, {"paragraphs": set(), "tables": []})
            report_secs[current]["tables"].append(
                {"columns": content["columns"], "header_cells": content["header_cells"]}
            )

    target = set(golden.sections.keys())
    found = set(report_secs.keys())
    matched_sections = sorted(target & found)
    missing_sections = sorted(target - found)
    novel_sections = sorted(found - target)
    section_hit_rate = len(matched_sections) / max(len(target), 1)

    section_jaccards: dict[str, float] = {}
    for s in matched_sections:
        a = golden.sections[s].fixed_paragraphs
        b = report_secs[s]["paragraphs"]
        union = a | b
        section_jaccards[s] = (len(a & b) / len(union)) if union else 0.0
    paragraph_jaccard_mean = (
        statistics.mean(section_jaccards.values()) if section_jaccards else 0.0
    )

    table_matches = 0
    table_total = 0
    for s in matched_sections:
        for gt in golden.sections[s].table_signatures:
            table_total += 1
            best = 0.0
            for rt in report_secs[s]["tables"]:
                if rt["columns"] != gt["columns"]:
                    continue
                gset = {c for c in gt["header_cells"] if c}
                rset = {c for c in rt["header_cells"] if c}
                union = gset | rset
                jaccard = (len(gset & rset) / len(union)) if union else 1.0
                best = max(best, jaccard)
            if best >= 0.8:
                table_matches += 1
    table_signature_match_rate = (
        (table_matches / table_total) if table_total > 0 else 1.0
    )

    fit_score = (
        0.4 * section_hit_rate
        + 0.4 * paragraph_jaccard_mean
        + 0.2 * table_signature_match_rate
    )

    return ReportFit(
        report_path=str(report_path),
        fit_score=fit_score,
        section_hit_rate=section_hit_rate,
        paragraph_jaccard_mean=paragraph_jaccard_mean,
        table_signature_match_rate=table_signature_match_rate,
        matched_sections=matched_sections,
        missing_sections=missing_sections,
        novel_sections=novel_sections,
        section_jaccards=section_jaccards,
    )


# ---------------------------------------------------------------------------
# Family-level aggregation + markdown brief
# ---------------------------------------------------------------------------

def classify(score: float) -> str:
    if score >= 0.85:
        return "sibling"
    if score >= 0.60:
        return "cousin"
    return "stranger"


CLASSIFY_LABEL = {
    "sibling": "兄弟 panel — 直接复用,~1-2 天",
    "cousin": "表亲 panel — 复用骨架 + 改若干章节,~3-5 天",
    "stranger": "陌生 panel — 该换 base 或走无监督挖掘,~5-10 天+",
}


def aggregate_family(reports: list[ReportFit], family: str, golden: TemplateSignature) -> dict:
    if not reports:
        return {"family": family, "n_reports": 0}

    scores = sorted(r.fit_score for r in reports)
    n = len(scores)
    p25 = scores[max(0, n // 4 - 1)]
    p50 = scores[n // 2]
    p75 = scores[min(n - 1, (3 * n) // 4)]

    all_sections = set(golden.sections.keys())
    hit_freq = Counter()
    jaccard_by_sec: dict[str, list[float]] = {s: [] for s in all_sections}
    novel_freq = Counter()
    for r in reports:
        for s in r.matched_sections:
            hit_freq[s] += 1
        for s, j in r.section_jaccards.items():
            jaccard_by_sec[s].append(j)
        for s in r.novel_sections:
            novel_freq[s] += 1

    high, mid, low = [], [], []
    for s in all_sections:
        hit = hit_freq[s] / n
        mean_j = statistics.mean(jaccard_by_sec[s]) if jaccard_by_sec[s] else 0.0
        if mean_j >= 0.85 and hit >= 0.9:
            high.append((s, mean_j, hit))
        elif mean_j >= 0.5 or hit >= 0.5:
            mid.append((s, mean_j, hit))
        else:
            low.append((s, mean_j, hit))

    novel = [(s, c / n) for s, c in novel_freq.most_common(20) if c / n >= 0.5]

    return {
        "family": family,
        "n_reports": n,
        "fit_score": {"p25": p25, "median": p50, "p75": p75},
        "classification": classify(p50),
        "high_fit_sections": high,
        "medium_fit_sections": mid,
        "low_fit_sections": low,
        "novel_sections": novel,
    }


def render_brief(agg: dict, golden_path: str) -> str:
    if agg["n_reports"] == 0:
        return f"# Template-fit Analysis: family `{agg['family']}`\n\nNo reports analyzed (corpus empty or all skipped).\n"

    cls = agg["classification"]
    median = agg["fit_score"]["median"] * 100
    p25 = agg["fit_score"]["p25"] * 100
    p75 = agg["fit_score"]["p75"] * 100

    out = []
    out.append(
        f"# Template-fit Analysis: `{Path(golden_path).stem}` ↔ family `{agg['family']}`"
    )
    out.append("")
    out.append(f"- Reports analyzed: **{agg['n_reports']}**")
    out.append(
        f"- Fit score (median): **{median:.0f}/100** (P25 {p25:.0f}, P75 {p75:.0f})"
    )
    out.append(f"- Classification: **{CLASSIFY_LABEL[cls]}**")
    out.append("")

    def _sec_list(title: str, items, label_jaccard=True):
        out.append(f"## {title}")
        if items:
            for s, j, h in sorted(items, key=lambda x: (-x[1], -x[2])):
                if label_jaccard:
                    out.append(
                        f"- `{s}` — 段落 Jaccard {j*100:.0f}%, 出现率 {h*100:.0f}%"
                    )
                else:
                    out.append(f"- `{s}` — 出现率 {h*100:.0f}%")
        else:
            out.append("(无)")
        out.append("")

    _sec_list("✅ 高契合章节(直接复用)", agg["high_fit_sections"])
    _sec_list("🟡 中契合章节(可复用骨架,改内容)", agg["medium_fit_sections"])
    _sec_list("🔴 低契合章节(必须新设计或缺失)", agg["low_fit_sections"])

    out.append("## 🆕 该 Family 独有章节(CRC358 模板里没有,出现率 ≥ 50%)")
    if agg["novel_sections"]:
        for s, freq in agg["novel_sections"]:
            out.append(f"- `{s}` — 出现率 {freq*100:.0f}%")
    else:
        out.append("(无)")
    out.append("")

    out.append("## 推荐起步")
    if cls == "sibling":
        out.append("- `cp -r panels/crc_358_msi panels/<your_panel_id>`")
        out.append("- 改 panel.yaml、rules/、模板里的癌种特定文本")
        out.append("- 不需要新设计章节")
    elif cls == "cousin":
        out.append("- 以 `panels/crc_358_msi` 为 base")
        out.append("- 替换/扩展上面 🔴 低契合章节(每个 ~ 半天)")
        out.append("- 上面 🆕 独有章节需要新设计(每个 ~ 1-2 天,含变量化)")
    else:
        out.append("- ⚠️ CRC358 不是合适 base。两个选项:")
        out.append(
            "  - (a) 从这个 family 选一份 reviewed final 当 golden,独立走 onboarding;"
        )
        out.append(
            "  - (b) 走无监督模式挖掘(段落频率聚类),先识别 family 内的章节结构。"
        )
    out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--golden", required=True, type=Path)
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--family-hint", default=None)
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--max-reports", type=int, default=None)
    args = ap.parse_args()

    if not args.golden.exists():
        print(f"ERROR: golden template not found: {args.golden}", file=sys.stderr)
        return 2
    if not args.corpus.exists():
        print(f"ERROR: corpus directory not found: {args.corpus}", file=sys.stderr)
        return 2

    print(f"Building golden signature from {args.golden} ...", file=sys.stderr)
    golden = build_template_signature(args.golden)
    n_paras = sum(len(s.fixed_paragraphs) for s in golden.sections.values())
    print(
        f"  {len(golden.sections)} sections, {n_paras} fixed paragraphs.",
        file=sys.stderr,
    )

    reports = sorted(
        p
        for p in args.corpus.rglob("*.docx")
        if not p.name.startswith("~$") and not p.name.startswith("._")
    )
    if args.max_reports:
        reports = reports[: args.max_reports]
    print(f"Analyzing {len(reports)} reports ...", file=sys.stderr)

    fits: list[ReportFit] = []
    skipped = 0
    for i, p in enumerate(reports, 1):
        try:
            fits.append(analyze_report(p, golden))
        except Exception as e:
            skipped += 1
            print(f"  SKIP {p.name}: {e}", file=sys.stderr)
            continue
        if i % 100 == 0:
            print(f"  [{i}/{len(reports)}]", file=sys.stderr)
    print(
        f"Done. {len(fits)} analyzed, {skipped} skipped.", file=sys.stderr
    )

    family_name = args.family_hint or args.corpus.name
    agg = aggregate_family(fits, family_name, golden)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "golden": str(args.golden),
                    "family": family_name,
                    "aggregate": agg,
                    "reports": [
                        {
                            "path": f.report_path,
                            "fit_score": f.fit_score,
                            "section_hit_rate": f.section_hit_rate,
                            "paragraph_jaccard_mean": f.paragraph_jaccard_mean,
                            "table_signature_match_rate": f.table_signature_match_rate,
                            "matched_sections": f.matched_sections,
                            "missing_sections": f.missing_sections,
                            "novel_sections": f.novel_sections,
                        }
                        for f in fits
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"JSON: {args.output}", file=sys.stderr)

    brief = render_brief(agg, str(args.golden))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(brief, encoding="utf-8")
        print(f"Brief: {args.report}", file=sys.stderr)
    else:
        print(brief)

    return 0


if __name__ == "__main__":
    sys.exit(main())
