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

from reportgen.core.pipeline.summary import summarize_stage_results
from reportgen.models.report_data import ReportData
from reportgen.utils.artifacts import write_json
from reportgen.utils.docx_render import render_docx_to_pngs


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
    processor_report: Optional[list[Mapping[str, Any]]] = None,
    template_contract: Optional[Mapping[str, Any]] = None,
    rule_provenance: Optional[Mapping[str, Any]] = None,
    stage_results: Optional[list[Mapping[str, Any]]] = None,
    stage_results_file: Optional[str] = None,
    visual_render: Optional[str] = None,
    visual_render_required: bool = False,
    visual_render_dpi: int = 120,
    visual_render_timeout_seconds: int = 120,
    visual_render_output_dir: Optional[str] = None,
    visual_render_tmp_dir: Optional[str] = None,
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

    checks["template_contract"] = _template_contract_check(template_contract)
    if checks["template_contract"]["status"] == "FAIL":
        issue(
            "error",
            "TEMPLATE_CONTRACT_FAILED",
            checks["template_contract"]["message"],
        )
    checks["rules"] = _rule_provenance_check(rule_provenance)
    if checks["rules"]["status"] == "FAIL":
        issue("error", "RULE_PROVENANCE_FAILED", checks["rules"]["message"])

    if not output_path.exists():
        issue("error", "DOCX_NOT_FOUND", f"Output DOCX not found: {output_file}")
        return attach_pipeline_summary(
            _finalize_report(
                generated_at=generated_at,
                generation_id=generation_id,
                project_type=project_type,
                project_name=project_name,
                template_file=template_file,
                output_file=output_file,
                checks=checks,
                metrics=metrics,
                issues=issues,
                template_contract=template_contract,
                rule_provenance=rule_provenance,
            ),
            stage_results=stage_results,
            stage_results_file=stage_results_file,
        )

    try:
        doc = Document(str(output_path))
        checks["docx_openable"] = {"status": "PASS", "value": True}
    except Exception as exc:
        issue("error", "DOCX_OPEN_FAILED", f"DOCX cannot be opened: {exc}")
        checks["docx_openable"] = {"status": "FAIL", "value": False}
        return attach_pipeline_summary(
            _finalize_report(
                generated_at=generated_at,
                generation_id=generation_id,
                project_type=project_type,
                project_name=project_name,
                template_file=template_file,
                output_file=output_file,
                checks=checks,
                metrics=metrics,
                issues=issues,
                template_contract=template_contract,
                rule_provenance=rule_provenance,
            ),
            stage_results=stage_results,
            stage_results_file=stage_results_file,
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

    checks["visual_render"] = _build_visual_render_check(
        output_path,
        mode=visual_render,
        required=visual_render_required,
        dpi=visual_render_dpi,
        timeout_seconds=visual_render_timeout_seconds,
        output_dir=visual_render_output_dir,
        tmp_dir=visual_render_tmp_dir,
    )
    for visual_issue in _visual_render_issues(checks["visual_render"]):
        issue(**visual_issue)
    metrics["visual_render_page_count"] = len(
        checks["visual_render"].get("rendered_pages") or []
    )

    checks["blank_page_detection"] = _blank_page_detection_check(
        checks["visual_render"]
    ) or {
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

    processor_rows = list(processor_report or [])
    processor_errors = [
        row
        for row in processor_rows
        if isinstance(row, Mapping) and row.get("status") == "ERROR"
    ]
    checks["post_processors"] = {
        "status": "WARN"
        if processor_errors
        else ("PASS" if processor_report is not None else "SKIP"),
        "count": len(processor_rows),
        "error_count": len(processor_errors),
        "errors": processor_errors,
    }
    if processor_errors:
        issue(
            "warning",
            "POST_PROCESSOR_ERRORS",
            "One or more DOCX post-render processors reported errors.",
        )

    table_checks = _build_table_checks(table_metrics, project_type, context)
    checks.update(table_checks)
    for table_issue in _table_issues(table_checks):
        issue(**table_issue)

    style_checks = _build_style_checks(doc, project_type, context)
    checks.update(style_checks)
    for style_issue in _style_issues(style_checks):
        issue(**style_issue)

    business_checks = _build_business_checks(compact_text, context, project_type)
    checks.update(business_checks)
    for business_issue in _business_issues(business_checks):
        issue(**business_issue)

    return attach_pipeline_summary(
        _finalize_report(
            generated_at=generated_at,
            generation_id=generation_id,
            project_type=project_type,
            project_name=project_name,
            template_file=template_file,
            output_file=output_file,
            field_provenance_file=field_provenance_file,
            processor_report=processor_report,
            template_contract=template_contract,
            rule_provenance=rule_provenance,
            checks=checks,
            metrics=metrics,
            issues=issues,
        ),
        stage_results=stage_results,
        stage_results_file=stage_results_file,
    )


def write_docx_qa_report(
    report: Mapping[str, Any], output_file: str, qa_file: Optional[str] = None
) -> str:
    """Write QA JSON next to the generated DOCX and return the JSON path."""
    path = Path(qa_file) if qa_file else Path(output_file).with_suffix(".qa.json")
    write_json(path, dict(report))
    return str(path)


def attach_pipeline_summary(
    report: Mapping[str, Any],
    *,
    stage_results: Optional[list[Mapping[str, Any]]] = None,
    stage_results_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Attach pipeline summary and fold it into QA status."""
    result = dict(report)
    pipeline = summarize_stage_results(
        stage_results,
        stage_results_file=stage_results_file,
    )
    checks = dict(result.get("checks") or {})
    checks["pipeline"] = {
        "status": pipeline["status"],
        "message": _pipeline_message(pipeline),
        "stage_count": pipeline["stage_count"],
        "failed_stages": pipeline["failed_stages"],
        "warning_stages": pipeline["warning_stages"],
        "stage_results_file": pipeline["stage_results_file"],
    }
    issues = list(result.get("issues") or [])
    if pipeline["status"] == "FAIL":
        issues.append(
            {
                "level": "error",
                "code": "PIPELINE_FAILED",
                "message": _pipeline_message(pipeline),
            }
        )
    elif pipeline["status"] == "WARN":
        issues.append(
            {
                "level": "warning",
                "code": "PIPELINE_WARN",
                "message": _pipeline_message(pipeline),
            }
        )

    has_error = any(i.get("level") == "error" for i in issues)
    has_warning = any(i.get("level") == "warning" for i in issues)
    result["pipeline"] = pipeline
    result["checks"] = checks
    result["issues"] = issues
    result["status"] = "FAIL" if has_error else ("WARN" if has_warning else "PASS")
    return result


def _pipeline_message(pipeline: Mapping[str, Any]) -> str:
    status = pipeline.get("status")
    if status == "FAIL":
        return "Generation pipeline failed: " + ", ".join(
            pipeline.get("failed_stages") or []
        )
    if status == "WARN":
        return "Generation pipeline completed with warnings: " + ", ".join(
            pipeline.get("warning_stages") or []
        )
    return "Generation pipeline passed."


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
    processor_report: Optional[list[Mapping[str, Any]]] = None,
    template_contract: Optional[Mapping[str, Any]] = None,
    rule_provenance: Optional[Mapping[str, Any]] = None,
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
        "post_processors": list(processor_report or []),
        "template_contract": dict(template_contract) if template_contract else None,
        "rules": dict(rule_provenance) if rule_provenance else None,
        "checks": dict(checks),
        "metrics": dict(metrics),
        "issues": issues,
    }


def _template_contract_check(
    template_contract: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    if not template_contract:
        return {
            "status": "SKIP",
            "message": "No template contract report was provided.",
        }

    declared = template_contract.get("declared_contract") or {}
    missing_paths = list(template_contract.get("missing_paths") or [])
    missing_lists = list(template_contract.get("missing_lists") or [])
    missing_row_fields = dict(template_contract.get("missing_row_fields") or {})
    missing_required_variables = list(
        declared.get("missing_required_variables") or []
    )
    missing_required_lists = list(declared.get("missing_required_lists") or [])
    missing_required_tables = list(declared.get("missing_required_tables") or [])
    table_errors = dict(declared.get("table_errors") or {})

    ok = bool(template_contract.get("ok"))
    return {
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "missing_paths": missing_paths,
        "missing_lists": missing_lists,
        "missing_row_fields": missing_row_fields,
        "missing_required_variables": missing_required_variables,
        "missing_required_lists": missing_required_lists,
        "missing_required_tables": missing_required_tables,
        "table_errors": table_errors,
        "message": (
            "Template contract passed."
            if ok
            else "Template contract failed: "
            f"missing_paths={missing_paths}, missing_lists={missing_lists}, "
            f"missing_required_variables={missing_required_variables}, "
            f"missing_required_lists={missing_required_lists}, "
            f"missing_required_tables={missing_required_tables}, "
            f"table_errors={table_errors}"
        ),
    }


def _rule_provenance_check(
    rule_provenance: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    if not rule_provenance:
        return {
            "status": "SKIP",
            "message": "No panel rule provenance was provided.",
            "file_count": 0,
            "files": [],
        }

    ok = bool(rule_provenance.get("ok", True))
    files = list(rule_provenance.get("files") or [])
    issues = list(rule_provenance.get("issues") or [])
    return {
        "status": "PASS" if ok else "FAIL",
        "panel_id": rule_provenance.get("panel_id"),
        "file_count": len(files),
        "files": files,
        "issues": issues,
        "message": (
            f"Panel rules loaded: {len(files)} file(s)."
            if ok
            else f"Panel rule validation failed with {len(issues)} issue(s)."
        ),
    }


def _build_visual_render_check(
    output_path: Path,
    *,
    mode: Optional[str],
    required: bool,
    dpi: int,
    timeout_seconds: int,
    output_dir: Optional[str],
    tmp_dir: Optional[str],
) -> Dict[str, Any]:
    normalized_mode = str(mode or "none").strip().lower()
    result: Dict[str, Any] = {
        "status": "SKIP",
        "requested": normalized_mode,
        "required": bool(required),
        "message": "Visual render QA was not requested.",
        "rendered_pages": [],
        "output_dir": None,
        "error": None,
    }
    if normalized_mode == "none":
        return result
    if normalized_mode not in {"first", "all"}:
        result.update(
            {
                "status": "FAIL" if required else "WARN",
                "message": f"Unsupported visual render mode: {mode!r}.",
                "error": "unsupported_mode",
            }
        )
        return result

    render_dir = (
        Path(output_dir)
        if output_dir
        else output_path.parent / "rendered_pages" / output_path.stem
    )
    first_page = 1 if normalized_mode == "first" else None
    last_page = 1 if normalized_mode == "first" else None

    try:
        pngs = render_docx_to_pngs(
            output_path,
            output_dir=render_dir,
            dpi=int(dpi),
            first_page=first_page,
            last_page=last_page,
            keep_pdf=False,
            timeout_seconds=int(timeout_seconds),
            tmp_dir=Path(tmp_dir) if tmp_dir else None,
        )
    except Exception as exc:
        result.update(
            {
                "status": "FAIL" if required else "WARN",
                "message": f"Visual render failed: {exc}",
                "output_dir": str(render_dir),
                "error": str(exc),
            }
        )
        for attr in ("stage", "command", "stdout", "stderr"):
            value = getattr(exc, attr, None)
            if not value:
                continue
            if attr == "command":
                result[attr] = list(value)
            elif attr in {"stdout", "stderr"}:
                result[f"{attr}_tail"] = str(value)[-2000:]
            else:
                result[attr] = value
        return result

    result.update(
        {
            "rendered_pages": [str(path) for path in pngs],
            "output_dir": str(render_dir),
        }
    )
    if not pngs:
        result.update(
            {
                "status": "FAIL" if required else "WARN",
                "message": "Visual render completed but produced no PNG pages.",
                "error": "no_rendered_pages",
            }
        )
        return result

    pixel_check = _inspect_rendered_png_pages(pngs)
    result["pixel_check"] = pixel_check
    if pixel_check["status"] in {"WARN", "FAIL"}:
        result.update(
            {
                "status": "FAIL" if required else "WARN",
                "message": pixel_check["message"],
            }
        )
        return result

    result.update(
        {
            "status": "PASS",
            "message": "Visual render produced inspectable PNG pages.",
        }
    )
    return result


def _visual_render_issues(check: Mapping[str, Any]) -> Iterable[Dict[str, str]]:
    status = check.get("status")
    if status not in {"WARN", "FAIL"}:
        return

    level = "error" if status == "FAIL" else "warning"
    error = str(check.get("error") or "")
    pixel_check = check.get("pixel_check")
    if isinstance(pixel_check, Mapping):
        if pixel_check.get("blank_pages"):
            code = "VISUAL_RENDER_BLANK_PAGES"
        elif pixel_check.get("low_content_pages"):
            code = "VISUAL_RENDER_LOW_CONTENT"
        elif pixel_check.get("unreadable_pages"):
            code = "VISUAL_RENDER_UNREADABLE_PAGES"
        else:
            code = "VISUAL_RENDER_WARN"
    elif error == "no_rendered_pages":
        code = "VISUAL_RENDER_NO_PAGES"
    elif error == "unsupported_mode":
        code = "VISUAL_RENDER_UNSUPPORTED_MODE"
    else:
        code = "VISUAL_RENDER_FAILED"

    yield {
        "level": level,
        "code": code,
        "message": str(check.get("message") or "Visual render QA reported an issue."),
    }


def _blank_page_detection_check(
    visual_check: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    if visual_check.get("requested") == "none":
        return None

    pixel_check = visual_check.get("pixel_check")
    if not isinstance(pixel_check, Mapping):
        return {
            "status": "SKIP",
            "message": "Visual render did not produce inspectable page pixels.",
        }
    if pixel_check.get("status") == "SKIP":
        return {
            "status": "SKIP",
            "message": str(
                pixel_check.get("message")
                or "Rendered page pixel inspection was skipped."
            ),
        }

    blank_pages = list(pixel_check.get("blank_pages") or [])
    low_content_pages = list(pixel_check.get("low_content_pages") or [])
    unreadable_pages = list(pixel_check.get("unreadable_pages") or [])
    if blank_pages or low_content_pages or unreadable_pages:
        return {
            "status": visual_check.get("status") or "WARN",
            "message": "Visual page inspection found blank or low-content page images.",
            "blank_pages": blank_pages,
            "low_content_pages": low_content_pages,
            "unreadable_pages": unreadable_pages,
            "thresholds": pixel_check.get("thresholds") or {},
        }
    return {
        "status": "PASS",
        "message": "Visual page inspection did not find blank rendered pages.",
        "checked_pages": pixel_check.get("checked_pages") or 0,
        "thresholds": pixel_check.get("thresholds") or {},
    }


def _inspect_rendered_png_pages(pngs: Iterable[Path]) -> Dict[str, Any]:
    thresholds = {
        "blank_nonwhite_ratio": 0.001,
        "blank_dark_ratio": 0.0002,
        "low_content_dark_ratio": 0.0015,
    }
    try:
        from PIL import Image
    except Exception as exc:
        return {
            "status": "SKIP",
            "message": f"Pillow is unavailable; skipped rendered PNG pixel checks: {exc}",
            "checked_pages": 0,
            "thresholds": thresholds,
        }

    pages: List[Dict[str, Any]] = []
    unreadable: List[str] = []
    for path in pngs:
        try:
            pages.append(_rendered_png_page_metrics(Path(path), Image, thresholds))
        except Exception as exc:
            unreadable.append(f"{path}: {exc}")

    blank_pages = [row["path"] for row in pages if row.get("blank")]
    low_content_pages = [row["path"] for row in pages if row.get("low_content")]
    if unreadable or blank_pages or low_content_pages:
        parts: List[str] = []
        if unreadable:
            parts.append(f"{len(unreadable)} rendered PNG page(s) could not be read")
        if blank_pages:
            parts.append(f"{len(blank_pages)} rendered page(s) look blank")
        if low_content_pages:
            parts.append(f"{len(low_content_pages)} rendered page(s) look low-content")
        return {
            "status": "WARN",
            "message": "; ".join(parts) + ".",
            "checked_pages": len(pages),
            "pages": pages,
            "blank_pages": blank_pages,
            "low_content_pages": low_content_pages,
            "unreadable_pages": unreadable,
            "thresholds": thresholds,
        }

    return {
        "status": "PASS",
        "message": "Rendered PNG pixel checks passed.",
        "checked_pages": len(pages),
        "pages": pages,
        "blank_pages": [],
        "low_content_pages": [],
        "unreadable_pages": [],
        "thresholds": thresholds,
    }


def _rendered_png_page_metrics(
    path: Path,
    image_module: Any,
    thresholds: Mapping[str, float],
) -> Dict[str, Any]:
    with image_module.open(path) as image:
        original_size = [int(image.width), int(image.height)]
        sampled = image.convert("RGBA")
        sampled.thumbnail((300, 300))
        pixels = list(sampled.getdata())

    visible = [pixel for pixel in pixels if pixel[3] > 10]
    visible_count = len(visible) or 1
    nonwhite_count = sum(
        1 for red, green, blue, _alpha in visible if min(red, green, blue) < 248
    )
    dark_count = sum(
        1
        for red, green, blue, _alpha in visible
        if (red + green + blue) / 3 < 210
    )
    nonwhite_ratio = nonwhite_count / visible_count
    dark_ratio = dark_count / visible_count
    blank = (
        nonwhite_ratio < float(thresholds["blank_nonwhite_ratio"])
        and dark_ratio < float(thresholds["blank_dark_ratio"])
    )
    low_content = (
        not blank
        and dark_ratio < float(thresholds["low_content_dark_ratio"])
    )
    return {
        "path": str(path),
        "file_size_bytes": path.stat().st_size,
        "image_size": original_size,
        "sampled_pixels": visible_count,
        "nonwhite_ratio": round(nonwhite_ratio, 6),
        "dark_ratio": round(dark_ratio, 6),
        "blank": blank,
        "low_content": low_content,
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


def _build_style_checks(
    doc: Any,
    project_type: Optional[str],
    context: Mapping[str, Any],
) -> Dict[str, Any]:
    if not _is_crc(project_type):
        return {}

    style = context.get("panel_style")
    if not isinstance(style, Mapping):
        return {
            "docx_style_rules": {
                "status": "SKIP",
                "message": "No panel_style rules were provided in report context.",
                "checked_table_count": 0,
                "failures": [],
            }
        }

    failures: List[Dict[str, Any]] = []
    checked = 0
    table_counts = {
        "variant_summary_table": 0,
        "variant_detail_table": 0,
        "biomarker_table": 0,
    }

    for table_idx, table in enumerate(doc.tables):
        if _is_variant_summary_style_table(table):
            table_counts["variant_summary_table"] += 1
            checked += 1
            failures.extend(
                _check_variant_summary_table_style(
                    table,
                    table_idx=table_idx,
                    style=_style_config(style, "variant_summary_table"),
                )
            )
        if _is_variant_detail_style_table(table):
            table_counts["variant_detail_table"] += 1
            checked += 1
            failures.extend(
                _check_variant_detail_table_style(
                    table,
                    table_idx=table_idx,
                    style=_style_config(style, "variant_detail_table"),
                )
            )
        if _is_biomarker_style_table(table):
            table_counts["biomarker_table"] += 1
            checked += 1
            failures.extend(
                _check_biomarker_table_style(
                    table,
                    table_idx=table_idx,
                    style=_style_config(style, "biomarker_table"),
                )
            )

    if not checked:
        return {
            "docx_style_rules": {
                "status": "SKIP",
                "message": "No style-managed CRC tables were detected.",
                "checked_table_count": 0,
                "table_counts": table_counts,
                "failures": [],
            }
        }

    return {
        "docx_style_rules": {
            "status": "FAIL" if failures else "PASS",
            "message": (
                f"DOCX style QA found {len(failures)} issue(s)."
                if failures
                else "DOCX style QA passed."
            ),
            "checked_table_count": checked,
            "table_counts": table_counts,
            "failures": failures[:30],
            "failure_count": len(failures),
        }
    }


def _style_issues(checks: Mapping[str, Any]) -> Iterable[Dict[str, str]]:
    check = checks.get("docx_style_rules")
    if isinstance(check, Mapping) and check.get("status") == "FAIL":
        yield {
            "level": "error",
            "code": "DOCX_STYLE_RULES",
            "message": str(check.get("message") or "DOCX style rules failed."),
        }


def _style_config(root: Mapping[str, Any], table_name: str) -> Dict[str, Any]:
    defaults = root.get("defaults")
    merged = dict(defaults) if isinstance(defaults, Mapping) else {}
    table = root.get(table_name)
    if isinstance(table, Mapping):
        merged.update(table)
    return merged


def _hex_color(value: Any, default: str) -> str:
    text = str(value or default).strip().lstrip("#").upper()
    if len(text) != 6 or not all(ch in "0123456789ABCDEF" for ch in text):
        return default.upper()
    return text


def _bool_style(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _is_variant_summary_style_table(table: Any) -> bool:
    if _table_col_count(table) != 4 or not table.rows:
        return False
    header = _compact(" ".join(cell.text for cell in table.rows[0].cells))
    return all(
        token in header
        for token in ("基因", "突变位点", "潜在获益靶向药物", "可能耐药")
    )


def _is_variant_detail_style_table(table: Any) -> bool:
    if _table_col_count(table) != 9 or len(table.rows) < 2:
        return False
    row0 = _compact(" ".join(cell.text for cell in table.rows[0].cells))
    row1 = _compact(" ".join(cell.text for cell in table.rows[1].cells))
    return all(token in row0 for token in ("基因名称", "基因突变信息", "靶向药物信息")) and all(
        token in row1 for token in ("转录本号", "潜在获益靶向药物")
    )


def _is_biomarker_style_table(table: Any) -> bool:
    if _table_col_count(table) != 3 or not table.rows:
        return False
    text = _compact("\n".join(cell.text for row in table.rows for cell in row.cells))
    return all(token in text for token in ("TMB", "MSI", "用药提示"))


def _check_variant_summary_table_style(
    table: Any,
    *,
    table_idx: int,
    style: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    expected = {
        "header_fill": _hex_color(style.get("header_fill"), "00C4D8"),
        "header_font_color": _hex_color(style.get("header_font_color"), "FFFFFF"),
        "body_font_color": _hex_color(style.get("body_font_color"), "000000"),
        "link_color": _hex_color(style.get("link_color"), "0000FF"),
        "link_underline": _bool_style(style.get("link_underline"), True),
    }
    failures = _check_header_style(
        table,
        table_idx=table_idx,
        table_name="variant_summary_table",
        header_rows={0},
        expected_fill=expected["header_fill"],
        expected_font_color=expected["header_font_color"],
    )
    for row_idx, row in enumerate(table.rows[1:], start=1):
        for col_idx, cell in enumerate(row.cells):
            dash_only = (cell.text or "").strip() in {"", "-", "--", "—"}
            link_cell = col_idx == 0 or (col_idx in {2, 3} and not dash_only)
            failures.extend(
                _check_cell_runs(
                    cell,
                    table_idx=table_idx,
                    row_idx=row_idx,
                    col_idx=col_idx,
                    table_name="variant_summary_table",
                    expected_color=expected["link_color"] if link_cell else expected["body_font_color"],
                    expected_underline=expected["link_underline"] if link_cell else False,
                )
            )
    return failures


def _check_variant_detail_table_style(
    table: Any,
    *,
    table_idx: int,
    style: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    expected = {
        "header_fill": _hex_color(style.get("header_fill"), "00C4D8"),
        "header_font_color": _hex_color(style.get("header_font_color"), "F9FBFA"),
        "body_font_color": _hex_color(style.get("body_font_color"), "000000"),
        "link_color": _hex_color(style.get("link_color"), "0000FF"),
        "link_underline": _bool_style(style.get("link_underline"), True),
    }
    failures = _check_header_style(
        table,
        table_idx=table_idx,
        table_name="variant_detail_table",
        header_rows={0, 1},
        expected_fill=expected["header_fill"],
        expected_font_color=expected["header_font_color"],
    )
    for row_idx, row in enumerate(table.rows[2:], start=2):
        for col_idx, cell in enumerate(row.cells):
            dash_only = (cell.text or "").strip() in {"", "-", "--", "—"}
            link_cell = col_idx == 0 or (col_idx in {7, 8} and not dash_only)
            failures.extend(
                _check_cell_runs(
                    cell,
                    table_idx=table_idx,
                    row_idx=row_idx,
                    col_idx=col_idx,
                    table_name="variant_detail_table",
                    expected_color=expected["link_color"] if link_cell else expected["body_font_color"],
                    expected_underline=expected["link_underline"] if link_cell else False,
                )
            )
    return failures


def _check_biomarker_table_style(
    table: Any,
    *,
    table_idx: int,
    style: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    expected = {
        "header_fill": _hex_color(style.get("header_fill"), "00C4D8"),
        "header_font_color": _hex_color(style.get("header_font_color"), "F9FBFA"),
        "body_font_color": _hex_color(style.get("body_font_color"), "000000"),
    }
    failures = _check_header_style(
        table,
        table_idx=table_idx,
        table_name="biomarker_table",
        header_rows={0},
        expected_fill=expected["header_fill"],
        expected_font_color=expected["header_font_color"],
    )
    for row_idx, row in enumerate(table.rows[1:], start=1):
        for col_idx, cell in enumerate(row.cells):
            failures.extend(
                _check_cell_runs(
                    cell,
                    table_idx=table_idx,
                    row_idx=row_idx,
                    col_idx=col_idx,
                    table_name="biomarker_table",
                    expected_color=expected["body_font_color"],
                    expected_underline=False,
                )
            )
    return failures


def _check_header_style(
    table: Any,
    *,
    table_idx: int,
    table_name: str,
    header_rows: set[int],
    expected_fill: str,
    expected_font_color: str,
) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    for row_idx in header_rows:
        if row_idx >= len(table.rows):
            continue
        for col_idx, cell in enumerate(table.rows[row_idx].cells):
            actual_fill = _cell_fill(cell)
            if actual_fill and actual_fill != expected_fill:
                failures.append(
                    _style_failure(
                        table_name,
                        table_idx,
                        row_idx,
                        col_idx,
                        "header_fill",
                        expected_fill,
                        actual_fill,
                    )
                )
            elif not actual_fill:
                failures.append(
                    _style_failure(
                        table_name,
                        table_idx,
                        row_idx,
                        col_idx,
                        "header_fill",
                        expected_fill,
                        None,
                    )
                )
            failures.extend(
                _check_cell_runs(
                    cell,
                    table_idx=table_idx,
                    row_idx=row_idx,
                    col_idx=col_idx,
                    table_name=table_name,
                    expected_color=expected_font_color,
                    expected_underline=False,
                )
            )
    return failures


def _check_cell_runs(
    cell: Any,
    *,
    table_idx: int,
    row_idx: int,
    col_idx: int,
    table_name: str,
    expected_color: str,
    expected_underline: bool,
) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            if not (run.text or "").strip():
                continue
            actual_color = _run_color(run)
            if actual_color and actual_color != expected_color:
                failures.append(
                    _style_failure(
                        table_name,
                        table_idx,
                        row_idx,
                        col_idx,
                        "font_color",
                        expected_color,
                        actual_color,
                    )
                )
            elif not actual_color:
                failures.append(
                    _style_failure(
                        table_name,
                        table_idx,
                        row_idx,
                        col_idx,
                        "font_color",
                        expected_color,
                        None,
                    )
                )
            actual_underline = bool(run.font.underline)
            if actual_underline != expected_underline:
                failures.append(
                    _style_failure(
                        table_name,
                        table_idx,
                        row_idx,
                        col_idx,
                        "underline",
                        expected_underline,
                        actual_underline,
                    )
                )
    return failures


def _style_failure(
    table_name: str,
    table_idx: int,
    row_idx: int,
    col_idx: int,
    property_name: str,
    expected: Any,
    actual: Any,
) -> Dict[str, Any]:
    return {
        "table": table_name,
        "table_index": table_idx,
        "row": row_idx,
        "col": col_idx,
        "property": property_name,
        "expected": expected,
        "actual": actual,
    }


def _cell_fill(cell: Any) -> Optional[str]:
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        return None
    value = shd.get(qn("w:fill"))
    return str(value).upper() if value else None


def _run_color(run: Any) -> Optional[str]:
    value = run.font.color.rgb
    return str(value).upper() if value is not None else None


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
