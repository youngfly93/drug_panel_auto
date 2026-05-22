"""DOCX report diff utilities for regression review.

The diff is deliberately structural rather than visual: it compares extracted
text, table shape/content, basic run styles, and optional QA JSON reports. This
gives the pipeline a deterministic gate even when local Word/LibreOffice
rendering is unavailable.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher, unified_diff
from pathlib import Path
from typing import Any, Mapping, Optional

from docx import Document
from docx.oxml.ns import qn

from reportgen.utils.artifacts import write_json


@dataclass(frozen=True)
class ReportDiffOptions:
    reference_docx: str
    candidate_docx: str
    output_dir: Optional[str] = None
    reference_qa: Optional[str] = None
    candidate_qa: Optional[str] = None
    max_samples: int = 30


def compare_reports(options: ReportDiffOptions) -> dict[str, Any]:
    """Compare two generated DOCX reports and optional QA sidecars."""
    reference_path = Path(options.reference_docx).resolve()
    candidate_path = Path(options.candidate_docx).resolve()
    max_samples = max(1, int(options.max_samples))

    ref_snapshot = _snapshot_docx(reference_path)
    cand_snapshot = _snapshot_docx(candidate_path)

    sections = {
        "documents": _compare_document_openability(
            ref_snapshot, cand_snapshot, reference_path, candidate_path
        ),
        "text": _compare_text(ref_snapshot, cand_snapshot, max_samples=max_samples),
        "tables": _compare_tables(ref_snapshot, cand_snapshot, max_samples=max_samples),
        "styles": _compare_styles(ref_snapshot, cand_snapshot, max_samples=max_samples),
        "qa": _compare_qa(
            _load_qa(options.reference_qa, reference_path),
            _load_qa(options.candidate_qa, candidate_path),
            max_samples=max_samples,
        ),
    }
    issues = _collect_issues(sections)
    status = _overall_status(issues)
    result = {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "status": status,
        "reference_docx": str(reference_path),
        "candidate_docx": str(candidate_path),
        "summary": {
            "failures": sum(1 for item in issues if item["level"] == "error"),
            "warnings": sum(1 for item in issues if item["level"] == "warning"),
            "text_similarity": sections["text"].get("similarity"),
            "table_count": {
                "reference": ref_snapshot.get("table_count"),
                "candidate": cand_snapshot.get("table_count"),
            },
        },
        "issues": issues,
        "sections": sections,
    }

    if options.output_dir:
        output_dir = Path(options.output_dir).resolve()
        write_report_diff_outputs(result, output_dir)
        result["output_dir"] = str(output_dir)
        result["json_file"] = str(output_dir / "report_diff.json")
        result["markdown_file"] = str(output_dir / "report_diff.md")
    return result


def write_report_diff_outputs(result: Mapping[str, Any], output_dir: Path) -> None:
    """Write report_diff.json and report_diff.md."""
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "report_diff.json", dict(result))
    (output_dir / "report_diff.md").write_text(
        render_report_diff_markdown(result), encoding="utf-8"
    )


def render_report_diff_markdown(result: Mapping[str, Any]) -> str:
    """Render a compact human-readable Markdown diff summary."""
    summary = result.get("summary") or {}
    sections = result.get("sections") or {}
    lines = [
        "# Report Diff",
        "",
        f"- Status: **{result.get('status')}**",
        f"- Reference: `{Path(str(result.get('reference_docx'))).name}`",
        f"- Candidate: `{Path(str(result.get('candidate_docx'))).name}`",
        f"- Failures: {summary.get('failures', 0)}",
        f"- Warnings: {summary.get('warnings', 0)}",
        f"- Text similarity: {summary.get('text_similarity')}",
        "",
        "## Issues",
        "",
    ]
    issues = list(result.get("issues") or [])
    if not issues:
        lines.append("No blocking or warning issues detected.")
    else:
        for issue in issues:
            lines.append(
                f"- **{issue.get('level', '').upper()}** `{issue.get('code')}`: "
                f"{issue.get('message')}"
            )

    text_section = sections.get("text") or {}
    lines.extend(["", "## Text", ""])
    lines.append(f"- Paragraph similarity: {text_section.get('similarity')}")
    lines.append(f"- Changed blocks: {text_section.get('changed_block_count', 0)}")
    for sample in text_section.get("samples") or []:
        lines.append(
            f"- `{sample.get('tag')}` reference[{sample.get('reference_range')}] "
            f"candidate[{sample.get('candidate_range')}]"
        )

    table_section = sections.get("tables") or {}
    lines.extend(["", "## Tables", ""])
    lines.append(
        f"- Table count: {table_section.get('reference_count')} -> "
        f"{table_section.get('candidate_count')}"
    )
    for sample in table_section.get("samples") or []:
        lines.append(f"- {sample.get('message')}")

    style_section = sections.get("styles") or {}
    lines.extend(["", "## Styles", ""])
    for sample in style_section.get("samples") or []:
        lines.append(f"- {sample.get('message')}")

    qa_section = sections.get("qa") or {}
    lines.extend(["", "## QA", ""])
    lines.append(
        f"- QA status: {qa_section.get('reference_status')} -> "
        f"{qa_section.get('candidate_status')}"
    )
    for sample in qa_section.get("samples") or []:
        lines.append(f"- {sample.get('message')}")

    return "\n".join(lines).rstrip() + "\n"


def _snapshot_docx(path: Path) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        snapshot["openable"] = False
        snapshot["error"] = "file_not_found"
        return snapshot
    try:
        doc = Document(str(path))
    except Exception as exc:
        snapshot["openable"] = False
        snapshot["error"] = str(exc)
        return snapshot

    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    tables = [_table_snapshot(table, idx) for idx, table in enumerate(doc.tables)]
    snapshot.update(
        {
            "openable": True,
            "paragraphs": paragraphs,
            "paragraph_count": len(paragraphs),
            "table_count": len(tables),
            "tables": tables,
            "style_summary": _style_summary(doc),
        }
    )
    return snapshot


def _table_snapshot(table: Any, index: int) -> dict[str, Any]:
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    row_count = len(rows)
    col_count = max((len(row) for row in rows), default=0)
    header = rows[0] if rows else []
    return {
        "index": index,
        "rows": rows,
        "row_count": row_count,
        "col_count": col_count,
        "header": header,
        "text": "\n".join("\t".join(row) for row in rows),
        "style_summary": _table_style_summary(table),
    }


def _style_summary(doc: Any) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for paragraph in doc.paragraphs:
        _count_paragraph_runs(counter, paragraph)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _count_paragraph_runs(counter, paragraph)
    return dict(sorted(counter.items()))


def _table_style_summary(table: Any) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for row in table.rows:
        for cell in row.cells:
            borders = cell._tc.xpath("./w:tcPr/w:tcBorders/*")
            if borders:
                counter["cell_border_elements"] += len(borders)
            for paragraph in cell.paragraphs:
                _count_paragraph_runs(counter, paragraph)
    return dict(sorted(counter.items()))


def _count_paragraph_runs(counter: Counter[str], paragraph: Any) -> None:
    if paragraph.style is not None and paragraph.style.name:
        counter[f"paragraph_style:{paragraph.style.name}"] += 1
    for run in paragraph.runs:
        text = run.text or ""
        if not text.strip():
            continue
        font_name = run.font.name
        if font_name:
            counter[f"font:{font_name}"] += 1
        size = run.font.size.pt if run.font.size else None
        if size is not None:
            counter[f"font_size:{round(size, 1)}"] += 1
        if run.bold:
            counter["bold_runs"] += 1
        if run.italic:
            counter["italic_runs"] += 1
        if _is_underlined(run):
            counter["underlined_runs"] += 1
        color = run.font.color.rgb
        if color is not None:
            counter[f"color:{str(color).upper()}"] += 1
            if str(color).upper() not in {"000000", "FFFFFF"}:
                counter["non_black_non_white_color_runs"] += 1


def _is_underlined(run: Any) -> bool:
    if run.font.underline:
        return True
    for underline in run._r.xpath(".//w:u"):
        value = underline.get(qn("w:val"))
        if value not in {None, "none", "0", "false"}:
            return True
    return False


def _compare_document_openability(
    ref: Mapping[str, Any],
    cand: Mapping[str, Any],
    reference_path: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    status = "PASS" if ref.get("openable") and cand.get("openable") else "FAIL"
    issues = []
    if not ref.get("openable"):
        issues.append(
            {
                "level": "error",
                "code": "REFERENCE_DOCX_NOT_OPENABLE",
                "message": f"Reference DOCX cannot be opened: {reference_path}",
            }
        )
    if not cand.get("openable"):
        issues.append(
            {
                "level": "error",
                "code": "CANDIDATE_DOCX_NOT_OPENABLE",
                "message": f"Candidate DOCX cannot be opened: {candidate_path}",
            }
        )
    return {"status": status, "issues": issues}


def _compare_text(
    ref: Mapping[str, Any], cand: Mapping[str, Any], *, max_samples: int
) -> dict[str, Any]:
    ref_paras = list(ref.get("paragraphs") or [])
    cand_paras = list(cand.get("paragraphs") or [])
    matcher = SequenceMatcher(a=ref_paras, b=cand_paras, autojunk=False)
    samples = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        samples.append(
            {
                "tag": tag,
                "reference_range": [i1, i2],
                "candidate_range": [j1, j2],
                "reference_sample": ref_paras[i1:i2][:3],
                "candidate_sample": cand_paras[j1:j2][:3],
            }
        )
        if len(samples) >= max_samples:
            break

    similarity = round(matcher.ratio(), 6)
    status = "PASS" if similarity == 1.0 else "WARN"
    issues = []
    if status == "WARN":
        issues.append(
            {
                "level": "warning",
                "code": "TEXT_DIFF",
                "message": f"DOCX text differs; similarity={similarity}.",
            }
        )
    return {
        "status": status,
        "similarity": similarity,
        "reference_paragraph_count": len(ref_paras),
        "candidate_paragraph_count": len(cand_paras),
        "changed_block_count": len([op for op in matcher.get_opcodes() if op[0] != "equal"]),
        "samples": samples,
        "unified_diff_sample": list(
            unified_diff(
                ref_paras,
                cand_paras,
                fromfile="reference",
                tofile="candidate",
                lineterm="",
            )
        )[: max_samples * 4],
        "issues": issues,
    }


def _compare_tables(
    ref: Mapping[str, Any], cand: Mapping[str, Any], *, max_samples: int
) -> dict[str, Any]:
    ref_tables = list(ref.get("tables") or [])
    cand_tables = list(cand.get("tables") or [])
    issues = []
    samples = []
    if len(ref_tables) != len(cand_tables):
        issues.append(
            {
                "level": "error",
                "code": "TABLE_COUNT_DIFF",
                "message": f"Table count differs: {len(ref_tables)} -> {len(cand_tables)}.",
            }
        )
        samples.append(
            {
                "message": f"Table count differs: {len(ref_tables)} -> {len(cand_tables)}",
            }
        )

    for idx, (ref_table, cand_table) in enumerate(zip(ref_tables, cand_tables)):
        ref_shape = [ref_table["row_count"], ref_table["col_count"]]
        cand_shape = [cand_table["row_count"], cand_table["col_count"]]
        if ref_shape != cand_shape:
            issues.append(
                {
                    "level": "error",
                    "code": "TABLE_SHAPE_DIFF",
                    "message": f"Table {idx} shape differs: {ref_shape} -> {cand_shape}.",
                }
            )
            samples.append(
                {
                    "table_index": idx,
                    "message": f"Table {idx} shape differs: {ref_shape} -> {cand_shape}",
                }
            )
            if len(samples) >= max_samples:
                break
            continue
        if ref_table.get("header") != cand_table.get("header"):
            issues.append(
                {
                    "level": "warning",
                    "code": "TABLE_HEADER_DIFF",
                    "message": f"Table {idx} header differs.",
                }
            )
            samples.append(
                {
                    "table_index": idx,
                    "message": f"Table {idx} header differs",
                    "reference": ref_table.get("header"),
                    "candidate": cand_table.get("header"),
                }
            )
        cell_diffs = _table_cell_diffs(ref_table["rows"], cand_table["rows"], max_samples)
        if cell_diffs:
            issues.append(
                {
                    "level": "warning",
                    "code": "TABLE_CELL_DIFF",
                    "message": f"Table {idx} has {len(cell_diffs)} sampled cell differences.",
                }
            )
            samples.extend(
                {
                    "table_index": idx,
                    "message": f"Table {idx} cell {item['cell']} differs",
                    **item,
                }
                for item in cell_diffs
            )
        if len(samples) >= max_samples:
            break

    return {
        "status": _section_status(issues),
        "reference_count": len(ref_tables),
        "candidate_count": len(cand_tables),
        "samples": samples[:max_samples],
        "issues": issues,
    }


def _table_cell_diffs(
    ref_rows: list[list[str]], cand_rows: list[list[str]], max_samples: int
) -> list[dict[str, Any]]:
    diffs = []
    for r_idx, (ref_row, cand_row) in enumerate(zip(ref_rows, cand_rows)):
        for c_idx, (ref_cell, cand_cell) in enumerate(zip(ref_row, cand_row)):
            if ref_cell != cand_cell:
                diffs.append(
                    {
                        "cell": [r_idx, c_idx],
                        "reference": ref_cell,
                        "candidate": cand_cell,
                    }
                )
                if len(diffs) >= max_samples:
                    return diffs
    return diffs


def _compare_styles(
    ref: Mapping[str, Any], cand: Mapping[str, Any], *, max_samples: int
) -> dict[str, Any]:
    issues = []
    samples = []
    ref_summary = dict(ref.get("style_summary") or {})
    cand_summary = dict(cand.get("style_summary") or {})
    for key in sorted(set(ref_summary) | set(cand_summary)):
        if ref_summary.get(key, 0) != cand_summary.get(key, 0):
            samples.append(
                {
                    "key": key,
                    "reference": ref_summary.get(key, 0),
                    "candidate": cand_summary.get(key, 0),
                    "message": (
                        f"Style metric {key} differs: "
                        f"{ref_summary.get(key, 0)} -> {cand_summary.get(key, 0)}"
                    ),
                }
            )
            if len(samples) >= max_samples:
                break
    if samples:
        issues.append(
            {
                "level": "warning",
                "code": "STYLE_DIFF",
                "message": f"Basic DOCX style metrics differ ({len(samples)} sampled).",
            }
        )
    return {
        "status": _section_status(issues),
        "samples": samples,
        "issues": issues,
    }


def _compare_qa(
    ref_qa: Optional[Mapping[str, Any]],
    cand_qa: Optional[Mapping[str, Any]],
    *,
    max_samples: int,
) -> dict[str, Any]:
    issues = []
    samples = []
    ref_status = ref_qa.get("status") if ref_qa else None
    cand_status = cand_qa.get("status") if cand_qa else None
    if cand_status == "FAIL":
        issues.append(
            {
                "level": "error",
                "code": "CANDIDATE_QA_FAIL",
                "message": "Candidate QA status is FAIL.",
            }
        )
    elif ref_status and cand_status and ref_status != cand_status:
        issues.append(
            {
                "level": "warning",
                "code": "QA_STATUS_DIFF",
                "message": f"QA status differs: {ref_status} -> {cand_status}.",
            }
        )
    ref_codes = _qa_issue_codes(ref_qa)
    cand_codes = _qa_issue_codes(cand_qa)
    added = sorted(cand_codes - ref_codes)
    removed = sorted(ref_codes - cand_codes)
    if added or removed:
        issues.append(
            {
                "level": "warning",
                "code": "QA_ISSUE_CODE_DIFF",
                "message": f"QA issue codes differ: added={added}, removed={removed}.",
            }
        )
        samples.append({"message": "QA issue code diff", "added": added, "removed": removed})
    return {
        "status": _section_status(issues),
        "reference_status": ref_status,
        "candidate_status": cand_status,
        "reference_issue_codes": sorted(ref_codes),
        "candidate_issue_codes": sorted(cand_codes),
        "samples": samples[:max_samples],
        "issues": issues,
    }


def _load_qa(path: Optional[str], docx_path: Path) -> Optional[Mapping[str, Any]]:
    qa_path = Path(path).resolve() if path else docx_path.with_suffix(".qa.json")
    if not qa_path.exists():
        return None
    try:
        return json.loads(qa_path.read_text(encoding="utf-8"))
    except Exception:
        return {"status": None, "issues": [{"code": "QA_READ_FAILED"}]}


def _qa_issue_codes(qa: Optional[Mapping[str, Any]]) -> set[str]:
    if not qa:
        return set()
    return {
        str(item.get("code"))
        for item in qa.get("issues") or []
        if isinstance(item, Mapping) and item.get("code")
    }


def _collect_issues(sections: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues = []
    for section_name, section in sections.items():
        for item in section.get("issues") or []:
            row = dict(item)
            row["section"] = section_name
            issues.append(row)
    return issues


def _overall_status(issues: list[Mapping[str, Any]]) -> str:
    if any(item.get("level") == "error" for item in issues):
        return "FAIL"
    if any(item.get("level") == "warning" for item in issues):
        return "WARN"
    return "PASS"


def _section_status(issues: list[Mapping[str, Any]]) -> str:
    if any(item.get("level") == "error" for item in issues):
        return "FAIL"
    if any(item.get("level") == "warning" for item in issues):
        return "WARN"
    return "PASS"
