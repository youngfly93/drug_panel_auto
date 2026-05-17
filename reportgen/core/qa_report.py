"""
Post-generation QA report for rendered DOCX outputs.

The checks in this module are intentionally machine-readable and conservative:
they catch known high-risk report regressions without tying the pipeline to one
patient case. Panel-specific assertions are enabled from project/report context.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from docx import Document

from reportgen.models.report_data import ReportData
from reportgen.utils.artifacts import write_json


PLACEHOLDER_RE = re.compile(
    r"(\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}|__[A-Z][A-Z0-9_]{2,}__)",
    re.DOTALL,
)
CRC_PROJECT_TYPES = {"crc_301", "crc_301_msi", "crc_358", "crc_358_msi"}


def build_docx_qa_report(
    *,
    output_file: str,
    report_data: Optional[ReportData] = None,
    project_type: Optional[str] = None,
    project_name: Optional[str] = None,
    template_file: Optional[str] = None,
    generation_id: Optional[str] = None,
    field_provenance: Optional[Mapping[str, Any]] = None,
    field_provenance_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a structured QA report for one generated DOCX file."""
    generated_at = datetime.now().isoformat()
    output_path = Path(output_file)
    context = report_data.context if report_data is not None else {}
    issues: List[Dict[str, str]] = []
    checks: Dict[str, Any] = {}
    metrics: Dict[str, Any] = {
        "file_size_bytes": output_path.stat().st_size if output_path.exists() else None,
    }

    def issue(level: str, code: str, message: str) -> None:
        issues.append({"level": level, "code": code, "message": message})

    if not output_path.exists():
        issue("error", "DOCX_NOT_FOUND", f"Output DOCX not found: {output_file}")
        return _finalize_report(
            generated_at=generated_at,
            generation_id=generation_id,
            project_type=project_type,
            project_name=project_name,
            template_file=template_file,
            output_file=output_file,
            checks=checks,
            metrics=metrics,
            issues=issues,
        )

    try:
        doc = Document(str(output_path))
        checks["docx_openable"] = {"status": "PASS", "value": True}
    except Exception as exc:
        issue("error", "DOCX_OPEN_FAILED", f"DOCX cannot be opened: {exc}")
        checks["docx_openable"] = {"status": "FAIL", "value": False}
        return _finalize_report(
            generated_at=generated_at,
            generation_id=generation_id,
            project_type=project_type,
            project_name=project_name,
            template_file=template_file,
            output_file=output_file,
            checks=checks,
            metrics=metrics,
            issues=issues,
        )

    paragraphs = list(_iter_all_paragraphs(doc))
    text = _read_docx_text(doc)
    compact_text = _compact(text)
    table_metrics = _inspect_tables(doc)
    metrics.update(
        {
            "paragraph_count": len(paragraphs),
            "table_count": len(doc.tables),
            "section_count": len(doc.sections),
            **table_metrics,
        }
    )

    placeholder_matches = PLACEHOLDER_RE.findall(text)
    brace_counts = {
        "{{": text.count("{{"),
        "}}": text.count("}}"),
        "{%": text.count("{%"),
        "%}": text.count("%}"),
    }
    placeholder_count = len(placeholder_matches) + sum(brace_counts.values())
    checks["unrendered_placeholders"] = {
        "status": "FAIL" if placeholder_count else "PASS",
        "count": placeholder_count,
        "samples": [_trim_sample(v) for v in placeholder_matches[:5]],
        "brace_counts": brace_counts,
    }
    if placeholder_count:
        issue("error", "UNRENDERED_PLACEHOLDER", "Rendered DOCX still contains template placeholders.")

    empty_numbered = [
        _paragraph_location(p) for p in paragraphs if _is_empty_numbered_paragraph(p)
    ]
    checks["empty_numbered_paragraphs"] = {
        "status": "FAIL" if empty_numbered else "PASS",
        "count": len(empty_numbered),
        "locations": empty_numbered[:10],
    }
    if empty_numbered:
        issue("error", "EMPTY_NUMBERED_PARAGRAPH", "Rendered DOCX contains visible empty bullet/numbered paragraphs.")

    toc = _inspect_toc(paragraphs)
    checks["toc_page_numbers"] = toc
    if toc["status"] == "WARN":
        issue("warning", "TOC_PAGE_NUMBERS_MISSING", toc["message"])

    checks["blank_page_detection"] = {
        "status": "SKIP",
        "message": "DOCX-level QA cannot reliably identify visual blank pages; use PDF/PNG render QA for this check.",
    }

    if field_provenance:
        checks["field_provenance"] = {
            "status": "PASS",
            "file": field_provenance_file,
            "key_field_sources": _field_source_summary(field_provenance),
        }
    else:
        checks["field_provenance"] = {
            "status": "SKIP",
            "file": field_provenance_file,
            "key_field_sources": {},
            "message": "No field provenance report was provided.",
        }

    table_checks = _build_table_checks(table_metrics, project_type, context)
    checks.update(table_checks)
    for table_issue in _table_issues(table_checks):
        issue(**table_issue)

    business_checks = _build_business_checks(compact_text, context, project_type)
    checks.update(business_checks)
    for business_issue in _business_issues(business_checks):
        issue(**business_issue)

    return _finalize_report(
        generated_at=generated_at,
        generation_id=generation_id,
        project_type=project_type,
        project_name=project_name,
        template_file=template_file,
        output_file=output_file,
        field_provenance_file=field_provenance_file,
        checks=checks,
        metrics=metrics,
        issues=issues,
    )


def write_docx_qa_report(
    report: Mapping[str, Any], output_file: str, qa_file: Optional[str] = None
) -> str:
    """Write QA JSON next to the generated DOCX and return the JSON path."""
    path = Path(qa_file) if qa_file else Path(output_file).with_suffix(".qa.json")
    write_json(path, dict(report))
    return str(path)


def _finalize_report(
    *,
    generated_at: str,
    generation_id: Optional[str],
    project_type: Optional[str],
    project_name: Optional[str],
    template_file: Optional[str],
    output_file: str,
    checks: Mapping[str, Any],
    metrics: Mapping[str, Any],
    issues: List[Dict[str, str]],
    field_provenance_file: Optional[str] = None,
) -> Dict[str, Any]:
    has_error = any(i.get("level") == "error" for i in issues)
    has_warning = any(i.get("level") == "warning" for i in issues)
    status = "FAIL" if has_error else ("WARN" if has_warning else "PASS")
    return {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "generation_id": generation_id,
        "status": status,
        "project_type": project_type,
        "project_name": project_name,
        "template_file": str(template_file) if template_file else None,
        "output_file": str(output_file),
        "field_provenance_file": str(field_provenance_file)
        if field_provenance_file
        else None,
        "checks": dict(checks),
        "metrics": dict(metrics),
        "issues": issues,
    }


def _iter_all_paragraphs(doc) -> Iterable[Any]:
    for paragraph in doc.paragraphs:
        yield paragraph
    for table_idx, table in enumerate(doc.tables):
        for row_idx, row in enumerate(table.rows):
            for cell_idx, cell in enumerate(row.cells):
                for para_idx, paragraph in enumerate(cell.paragraphs):
                    paragraph._qa_location = (
                        f"table:{table_idx}:r{row_idx}:c{cell_idx}:p{para_idx}"
                    )
                    yield paragraph


def _field_source_summary(field_provenance: Mapping[str, Any]) -> Dict[str, str]:
    fields = field_provenance.get("fields") or {}
    if not isinstance(fields, Mapping):
        return {}
    return {
        str(field): str(info.get("source") or "unknown")
        for field, info in fields.items()
        if isinstance(info, Mapping)
    }


def _read_docx_text(doc) -> str:
    parts: List[str] = []
    for paragraph in _iter_all_paragraphs(doc):
        value = paragraph.text or ""
        if value:
            parts.append(value)
    return "\n".join(parts)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _trim_sample(value: str, limit: int = 120) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value if len(value) <= limit else value[: limit - 1] + "..."


def _paragraph_location(paragraph: Any) -> str:
    return str(getattr(paragraph, "_qa_location", "body"))


def _is_empty_numbered_paragraph(paragraph: Any) -> bool:
    if (paragraph.text or "").strip():
        return False
    ppr = paragraph._p.pPr
    return bool(ppr is not None and ppr.numPr is not None)


def _inspect_toc(paragraphs: List[Any]) -> Dict[str, Any]:
    texts = [(p.text or "").strip() for p in paragraphs]
    start_idx = None
    for idx, text in enumerate(texts):
        if text == "目录" or text.startswith("目录 "):
            start_idx = idx
            break
    if start_idx is None:
        return {"status": "SKIP", "message": "No TOC heading found."}

    toc_lines: List[str] = []
    for text in texts[start_idx + 1 : start_idx + 100]:
        if not text:
            continue
        if text.startswith(("第一部分", "一、基本信息", "致您的一封信")):
            break
        toc_lines.append(text)

    page_like = [
        line
        for line in toc_lines
        if re.search(r"(第[一二三四五六七八九十]+部分|\d+(?:\.\d+)+|[一二三四五六七八九十]+、).*\d+\s*$", line)
    ]
    if not toc_lines:
        return {"status": "WARN", "line_count": 0, "message": "TOC area is empty."}
    if not page_like:
        return {
            "status": "WARN",
            "line_count": len(toc_lines),
            "message": "TOC lines were found, but no line appears to contain page numbers.",
            "sample_lines": toc_lines[:8],
        }
    return {
        "status": "PASS",
        "line_count": len(toc_lines),
        "page_numbered_line_count": len(page_like),
        "sample_lines": toc_lines[:8],
    }


def _inspect_tables(doc) -> Dict[str, Any]:
    summary = {
        "targeted_drug_tip_tables": [],
        "variant_summary_tables": [],
        "variant_detail_tables": [],
        "bad_variant_detail_tables": [],
        "biomarker_tables": [],
    }

    for idx, table in enumerate(doc.tables):
        col_count = _table_col_count(table)
        row_count = len(table.rows)
        preview = _table_preview(table, max_rows=4)
        compact_preview = _compact(preview)
        entry = {"index": idx, "rows": row_count, "cols": col_count}

        if all(token in compact_preview for token in ("突变位点", "潜在获益")):
            summary["targeted_drug_tip_tables"].append(entry)

        if all(token in compact_preview for token in ("基因突变信息", "潜在获益靶向药物")):
            summary["variant_summary_tables"].append(entry)

        has_detail_header = all(
            token in compact_preview
            for token in ("基因名称", "转录本号", "染色体", "外显子")
        )
        if has_detail_header:
            if col_count >= 8:
                summary["variant_detail_tables"].append(entry)
            else:
                summary["bad_variant_detail_tables"].append(entry)

        if all(token in compact_preview for token in ("TMB", "MSI", "用药提示")):
            summary["biomarker_tables"].append(entry)

    return summary


def _table_col_count(table: Any) -> int:
    if not table.rows:
        return 0
    return max((len(row.cells) for row in table.rows), default=0)


def _table_preview(table: Any, *, max_rows: int) -> str:
    rows: List[str] = []
    for row in table.rows[:max_rows]:
        rows.append(" ".join((cell.text or "").strip() for cell in row.cells))
    return "\n".join(rows)


def _is_crc(project_type: Optional[str]) -> bool:
    return (project_type or "").lower() in CRC_PROJECT_TYPES


def _build_table_checks(
    table_metrics: Mapping[str, Any],
    project_type: Optional[str],
    context: Mapping[str, Any],
) -> Dict[str, Any]:
    has_variants = bool(context.get("variants") or context.get("summary_variants"))
    crc = _is_crc(project_type)

    def status_for(count: int, required: bool) -> str:
        if not required:
            return "SKIP"
        return "PASS" if count else "FAIL"

    return {
        "variant_detail_table_shape": {
            "status": "FAIL"
            if table_metrics.get("bad_variant_detail_tables")
            else status_for(len(table_metrics.get("variant_detail_tables") or []), crc and has_variants),
            "tables": table_metrics.get("variant_detail_tables") or [],
            "bad_tables": table_metrics.get("bad_variant_detail_tables") or [],
            "required": crc and has_variants,
        },
        "variant_summary_table_present": {
            "status": status_for(len(table_metrics.get("variant_summary_tables") or []), crc),
            "tables": table_metrics.get("variant_summary_tables") or [],
            "required": crc,
        },
        "targeted_drug_tip_table_present": {
            "status": status_for(len(table_metrics.get("targeted_drug_tip_tables") or []), crc),
            "tables": table_metrics.get("targeted_drug_tip_tables") or [],
            "required": crc,
        },
        "biomarker_table_present": {
            "status": status_for(len(table_metrics.get("biomarker_tables") or []), crc),
            "tables": table_metrics.get("biomarker_tables") or [],
            "required": crc,
        },
    }


def _table_issues(checks: Mapping[str, Any]) -> Iterable[Dict[str, str]]:
    messages = {
        "variant_detail_table_shape": "CRC variant detail table is missing or has an unexpected column shape.",
        "variant_summary_table_present": "CRC 2.1 variant summary table was not detected.",
        "targeted_drug_tip_table_present": "CRC targeted drug tip table was not detected.",
        "biomarker_table_present": "CRC TMB/MSI biomarker table was not detected.",
    }
    for key, check in checks.items():
        if check.get("status") == "FAIL":
            yield {"level": "error", "code": key.upper(), "message": messages[key]}


def _build_business_checks(
    compact_text: str,
    context: Mapping[str, Any],
    project_type: Optional[str],
) -> Dict[str, Any]:
    checks: Dict[str, Any] = {}
    if not _is_crc(project_type):
        return checks

    total_count = _as_int(context.get("total_variants_count"))
    drug_count = _as_int(context.get("drug_related_count"))

    if total_count is not None:
        expected = f"本次共检出体细胞变异：{total_count}个"
        checks["total_variant_count_text"] = {
            "status": "PASS" if _compact(expected) in compact_text else "FAIL",
            "expected": expected,
        }

    if drug_count is not None:
        expected = f"与靶向药物用药相关的变异有：{drug_count}个"
        checks["drug_related_count_text"] = {
            "status": "PASS" if _compact(expected) in compact_text else "FAIL",
            "expected": expected,
        }

    tmb_status = str(context.get("tmb_status") or "").strip()
    if tmb_status:
        checks["tmb_status_text"] = {
            "status": "PASS" if _compact(tmb_status) in compact_text else "WARN",
            "expected": tmb_status,
        }

    msi_status = str(context.get("msi_status") or "").strip()
    if msi_status:
        checks["msi_status_text"] = {
            "status": "PASS" if _compact(msi_status) in compact_text else "WARN",
            "expected": msi_status,
        }

    return checks


def _business_issues(checks: Mapping[str, Any]) -> Iterable[Dict[str, str]]:
    messages = {
        "total_variant_count_text": "Total variant count text does not match report context.",
        "drug_related_count_text": "Drug-related variant count text does not match report context.",
        "tmb_status_text": "TMB status from context was not found in rendered text.",
        "msi_status_text": "MSI status from context was not found in rendered text.",
    }
    for key, check in checks.items():
        status = check.get("status")
        if status == "FAIL":
            yield {"level": "error", "code": key.upper(), "message": messages[key]}
        elif status == "WARN":
            yield {"level": "warning", "code": key.upper(), "message": messages[key]}


def _as_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None
