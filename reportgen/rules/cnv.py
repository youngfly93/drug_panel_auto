"""Source-preserving CNV display, without copy-number thresholds or dosing rules."""

from typing import Any, Mapping

from reportgen.models.excel_data import ExcelDataSource


def source_status(row: Mapping[str, Any]) -> str:
    for key in ("Status", "status", "Cnvkit"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    # Legacy workbooks may provide only a numeric copy number. Preserve the
    # field label and value for review; do not invent a calling threshold.
    copy_number = row.get("CopyNumber")
    if copy_number is not None and str(copy_number).strip():
        return f"CopyNumber={str(copy_number).strip()}"
    return "未提供"


def cnv_kind(row: Mapping[str, Any]) -> str:
    """Only explicit call words are interpretable; 0/1 and gain are not AMP."""
    status = source_status(row).casefold()
    if status in {"amp", "amplification", "amplified", "扩增"}:
        return "amp"
    if status in {"gain", "增益", "增加"}:
        return "gain"
    if status in {"loss", "del", "deletion", "缺失", "丢失"}:
        return "loss"
    if status in {"neutral", "normal", "diploid", "中性", "正常"}:
        return "neutral"
    return "unknown"


def cnv_review_text(source: ExcelDataSource, gene: str) -> str:
    """Return a conservative source observation, not a new clinical claim."""
    rows = [
        row
        for row in source.get_table_data("Cnv")
        if str(row.get("Gene") or row.get("gene") or "").strip().upper() == gene.upper()
    ]
    if not rows:
        if ("Cnv" not in source.sheet_names and "Cnv" not in source.table_data) or (
            source.metadata.get("cnv_parse", {}).get("status") == "unavailable"
        ):
            return "CNV未提供，无法判定；待复核"
        return ""
    kinds = {cnv_kind(row) for row in rows}
    if kinds == {"neutral"}:
        return ""
    labels = {"amp": "扩增", "gain": "增益", "loss": "缺失", "unknown": "未解释状态"}
    label = (
        labels.get(next(iter(kinds)), "未解释状态") if len(kinds) == 1 else "状态不一致"
    )
    statuses = "、".join(dict.fromkeys(source_status(row) for row in rows))
    return f"CNV：{label}（源表 {statuses}）；扩增判定及临床意义待复核"
