"""Build a compact, structured summary for generated panel reports."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from reportgen.models.report_data import ReportData

EMPTY_VALUES = {"", "-", "--", "无", "未填写", "未知", "none", "null", "nan", "n/a", "na"}


def build_report_summary(
    *,
    report_data: ReportData,
    project_type: Optional[str] = None,
    project_name: Optional[str] = None,
    panel_status: Optional[str] = None,
    template_status: Optional[str] = None,
    generation_id: Optional[str] = None,
    output_file: Optional[str] = None,
    qa_report: Optional[dict[str, Any]] = None,
    warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Return a panel-agnostic summary for the task detail page.

    The summary is derived from the same structured context used to render the
    Word report. It intentionally avoids parsing DOCX text so the UI remains a
    read-only view of generation data, not a second report engine.
    """

    context = report_data.context or {}
    qa_issues = (qa_report or {}).get("issues") or []
    variants = _first_table(report_data, ("variants_2_1", "summary_variants", "variants"))
    summary_variants = _first_table(report_data, ("summary_variants", "variants_2_1", "variants"))
    detected_variants = [row for row in variants if _is_detected_variant(row)]
    display_variants = detected_variants or variants
    targeted_drugs = _table(report_data, "targeted_drug_tips")
    chemotherapy = _table(report_data, "chemotherapy")

    total_variants = _as_int(
        _first_nonempty(
            context,
            ("total_variants_count", "variant_count", "detected_variants_count"),
        )
    )
    if total_variants is None:
        total_variants = _count_detected_variants(variants)

    drug_related_count = _as_int(_first_nonempty(context, ("drug_related_count",)))
    if drug_related_count is None:
        drug_related_count = _count_drug_related_rows(variants)

    qa_status = (qa_report or {}).get("status")
    warning_items = list(warnings or report_data.validation_errors or [])
    manual_review = _manual_review_items(
        qa_status=qa_status,
        qa_issues=qa_issues,
        warnings=warning_items,
        panel_status=panel_status,
        template_status=template_status,
    )

    return {
        "schema_version": "1.0",
        "generation_id": generation_id,
        "project_type": project_type,
        "project_name": project_name
        or _safe_text(_first_nonempty(context, ("project_name", "检测项目", "项目名称"))),
        "output_file": output_file,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "panel": {
            "status": _nullable_text(panel_status),
            "template_status": _nullable_text(template_status),
        },
        "patient": {
            "patient_name": _safe_text(
                _first_nonempty(context, ("patient_name", "姓名", "患者姓名"))
            ),
            "sample_id": _safe_text(
                _first_nonempty(context, ("sample_id", "report_number", "报告编号"))
            ),
            "report_number": _safe_text(
                _first_nonempty(context, ("report_number", "sample_id", "报告编号"))
            ),
            "gender": _safe_text(_first_nonempty(context, ("gender", "性别"))),
            "age": _safe_text(_first_nonempty(context, ("age", "年龄"))),
            "sample_type": _safe_text(
                _first_nonempty(context, ("sample_type", "sample_kind", "样本类型"))
            ),
            "clinical_diagnosis": _safe_text(
                _first_nonempty(
                    context,
                    ("clinical_diagnosis", "diagnosis", "cancer_type", "临床诊断"),
                )
            ),
            "receive_date": _safe_text(
                _first_nonempty(context, ("receive_date", "sample_receive_date", "收样日期"))
            ),
            "report_date": _safe_text(
                _first_nonempty(
                    context,
                    ("report_date", "report_date_dot", "release_date", "报告日期"),
                )
            ),
        },
        "biomarkers": {
            "tmb": {
                "summary": _safe_text(_first_nonempty(context, ("tmb_summary", "tmb"))),
                "value": _safe_text(_first_nonempty(context, ("tmb_value", "TMB"))),
                "status": _safe_text(_first_nonempty(context, ("tmb_status",))),
            },
            "msi": {
                "summary": _safe_text(_first_nonempty(context, ("msi_summary",))),
                "status": _safe_text(_first_nonempty(context, ("msi_status", "MSI状态"))),
            },
            "immune": {
                "status": _safe_text(
                    _first_nonempty(context, ("immune_module_status",))
                ),
                "positive": _safe_text(
                    _first_nonempty(context, ("immune_positive_result",))
                ),
                "negative": _safe_text(
                    _first_nonempty(context, ("immune_negative_result",))
                ),
                "hyperprogression": _safe_text(
                    _first_nonempty(context, ("immune_hyperprogression_result",))
                ),
            },
        },
        "variants": {
            "total": total_variants,
            "drug_related": drug_related_count,
            "summary_count": len(summary_variants),
            "by_class": _count_by(
                display_variants,
                (
                    "gene_class",
                    "classification",
                    "variant_level",
                    "mutation_level",
                    "变异等级",
                ),
            ),
            "key_rows": [_normalize_variant_row(row) for row in display_variants[:8]],
            "summary_rows": [_normalize_variant_row(row) for row in summary_variants[:8]],
        },
        "drugs": {
            # targeted_drug_tips may be configured as an all-variant display
            # table. Keep the medical count tied to rows with an actual drug
            # conclusion and expose the display count separately.
            "targeted_count": _count_drug_related_rows(targeted_drugs),
            "targeted_status": _safe_text(
                _first_nonempty(context, ("targeted_drug_module_status",))
            ),
            "displayed_variant_count": len(targeted_drugs),
            "chemotherapy_count": len(chemotherapy),
            "chemotherapy_status": _safe_text(
                _first_nonempty(context, ("chemotherapy_module_status",))
            ),
            "approved_display_policy": _safe_text(
                context.get("approved_drug_rows_display_mode")
            ),
            "approved_universe_count": _as_int(
                context.get("approved_drug_rows_total_count")
            ),
            "approved_suppressed_count": _as_int(
                context.get("approved_drug_rows_suppressed_count")
            ),
            "approved_suppressed_names": _safe_text_list(
                context.get("approved_drug_rows_suppressed_names")
            ),
            "targeted_rows": [_normalize_drug_row(row) for row in targeted_drugs[:8]],
            "chemotherapy_rows": [_normalize_chemo_row(row) for row in chemotherapy[:8]],
        },
        "qa": {
            "status": qa_status,
            "issue_count": len(qa_issues),
            "errors": sum(1 for item in qa_issues if item.get("level") == "error"),
            "warnings": sum(1 for item in qa_issues if item.get("level") != "error"),
        },
        "manual_review": manual_review,
    }


def write_report_summary(
    summary: dict[str, Any],
    output_file: str,
    *,
    summary_file: Optional[str] = None,
) -> str:
    """Persist a report summary next to the generated DOCX."""

    path = Path(summary_file) if summary_file else Path(output_file).with_suffix(".summary.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(path)


def _first_nonempty(context: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = context.get(key)
        if not _is_empty(value):
            return value
    return None


def _table(report_data: ReportData, name: str) -> list[dict[str, Any]]:
    rows = report_data.get_table(name) or []
    return [row for row in rows if isinstance(row, dict)]


def _first_table(report_data: ReportData, names: Iterable[str]) -> list[dict[str, Any]]:
    for name in names:
        rows = _table(report_data, name)
        if rows:
            return rows
    return []


def _normalize_variant_row(row: dict[str, Any]) -> dict[str, Any]:
    c_hgvs = _safe_text(_pick(row, ("cHGVS", "c_hgvs", "c_point", "cDNA", "cDNA变异")))
    p_hgvs = _safe_text(_pick(row, ("pHGVS", "p_hgvs", "p_point", "protein", "氨基酸变异")))
    locus = _safe_text(_pick(row, ("locus", "variant_site", "site", "变异位点")))
    return {
        "gene": _safe_text(_pick(row, ("gene", "Gene", "基因"))),
        "transcript": _safe_text(_pick(row, ("transcript", "Transcript", "转录本"))),
        "variant_site": _join_nonempty((locus, c_hgvs, p_hgvs), sep="；"),
        "variant_type": _safe_text(
            _pick(row, ("var_type_cn", "mutation_type", "variant_type", "变异类型"))
        ),
        "classification": _safe_text(
            _pick(
                row,
                ("gene_class", "classification", "variant_level", "mutation_level", "变异等级"),
            )
        ),
        "frequency": _safe_text(_pick(row, ("af_pct", "frequency", "Freq(%)", "AF", "丰度"))),
        "benefit_drugs": _safe_text(
            _pick(row, ("benefit_drugs_full", "benefit_drugs", "潜在获益药物"))
        ),
        "caution_drugs": _safe_text(
            _pick(row, ("caution_drugs_full", "caution_drugs", "潜在耐药药物"))
        ),
    }


def _normalize_drug_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "gene": _safe_text(_pick(row, ("gene", "Gene", "基因"))),
        "variant_site": _safe_text(_pick(row, ("variant_site", "locus", "site", "变异位点"))),
        "benefit_drugs": _drug_display_text(
            row, ("benefit_drugs_full", "benefit_drugs", "潜在获益药物")
        ),
        "caution_drugs": _drug_display_text(
            row, ("caution_drugs_full", "caution_drugs", "潜在耐药药物")
        ),
    }


def _normalize_chemo_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "drug": _safe_text(_pick(row, ("Drug", "drug", "药物"))),
        "gene": _safe_text(_pick(row, ("Gene", "gene", "基因"))),
        "indication": _safe_text(_pick(row, ("药物适应情况", "indication", "适应症"))),
    }


def _pick(row: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if not _is_empty(value):
            return value
    return None


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "\n".join(_safe_text(item) for item in value if not _is_empty(item))
    text = str(value).strip()
    return "" if text.lower() in EMPTY_VALUES else text


def _safe_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return [text for text in (_safe_text(item) for item in values) if text]


def _drug_display_text(row: dict[str, Any], keys: Iterable[str]) -> str:
    """Preserve the explicit no-conclusion marker used by report drug tables."""

    placeholder = ""
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if isinstance(value, str) and value.strip() in {"-", "--", "—"}:
            placeholder = "--"
            continue
        text = _safe_text(value)
        if text:
            return text
    return placeholder


def _nullable_text(value: Any) -> Optional[str]:
    text = _safe_text(value)
    return text or None


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in EMPTY_VALUES
    return False


def _join_nonempty(values: Iterable[Any], *, sep: str) -> str:
    texts = [_safe_text(value) for value in values]
    return sep.join(text for text in texts if text)


def _as_int(value: Any) -> Optional[int]:
    if _is_empty(value):
        return None
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def _count_detected_variants(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if _is_detected_variant(row))


def _count_drug_related_rows(rows: list[dict[str, Any]]) -> int:
    return sum(
        1
        for row in rows
        if not _is_empty(row.get("benefit_drugs")) or not _is_empty(row.get("caution_drugs"))
    )


def _is_detected_variant(row: dict[str, Any]) -> bool:
    text = " ".join(
        _safe_text(_pick(row, ("locus", "variant_site", "cHGVS", "pHGVS", "检测结果", "result"))).split()
    )
    if not text:
        return bool(_safe_text(_pick(row, ("gene", "Gene", "基因"))))
    return not any(marker in text for marker in ("未见突变", "未检出", "阴性"))


def _count_by(rows: list[dict[str, Any]], keys: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        label = _safe_text(_pick(row, keys))
        if not label:
            label = "未分级"
        counts[label] = counts.get(label, 0) + 1
    return counts


def _manual_review_items(
    *,
    qa_status: Optional[str],
    qa_issues: list[dict[str, Any]],
    warnings: list[str],
    panel_status: Optional[str],
    template_status: Optional[str],
) -> list[str]:
    items: list[str] = []
    if qa_status == "FAIL":
        items.append("QA 状态为 FAIL，下载报告前需先查看 QA 问题列表。")
    elif qa_status == "WARN":
        items.append("QA 状态为 WARN，建议核对警告项后再下发。")
    if warnings:
        items.append(f"生成过程记录 {len(warnings)} 条 warning，需要确认是否影响交付。")
    if qa_issues and qa_status not in {"FAIL", "WARN"}:
        items.append(f"QA 记录 {len(qa_issues)} 条问题，请抽查。")
    items.extend(_status_review_items(panel_status, template_status))
    return items


def _status_review_items(
    panel_status: Optional[str],
    template_status: Optional[str],
) -> list[str]:
    grouped: dict[str, list[str]] = {}
    for source, status in (
        ("Panel", panel_status),
        ("模板", template_status),
    ):
        normalized = _normalize_status(status)
        if normalized not in {"draft", "pilot"}:
            continue
        grouped.setdefault(normalized, []).append(source)

    items: list[str] = []
    for status, sources in grouped.items():
        source_label = "、".join(sources)
        if status == "draft":
            items.append(f"{source_label}状态为 draft（草稿）：需人工复核，勿直接交付。")
        elif status == "pilot":
            items.append(f"{source_label}状态为 pilot（试运行）：需人工复核后再交付。")
    return items


def _normalize_status(status: Optional[str]) -> str:
    return _safe_text(status).strip().lower()
