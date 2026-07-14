"""Validate a DOCX against a de-identified historical golden contract."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Mapping

import yaml
from docx import Document

from reportgen.core.report_diff import _extract_part3_sections, _snapshot_docx


def _normalized_text_sha256(text: str) -> str:
    compact = re.sub(r"\s+", "", str(text or ""))
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_historical_golden_contract(path: str | Path) -> dict[str, Any]:
    contract = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if contract.get("schema_version") != "1.0":
        raise ValueError("Unsupported historical golden contract schema")
    if not contract.get("case_alias") or not contract.get("panel_id"):
        raise ValueError("Historical golden contract requires case_alias and panel_id")
    if (contract.get("privacy") or {}).get("contains_phi") is not False:
        raise ValueError("Committed historical golden contracts must declare contains_phi=false")
    return contract


def _targeted_summary_gene_order(tables: list[Mapping[str, Any]]) -> list[str]:
    for table in tables:
        rows = list(table.get("rows") or [])
        if not rows:
            continue
        header = "".join(str(cell) for cell in rows[0])
        if "潜在获益靶向药物" not in header or "可能耐药" not in header:
            continue
        return [str(row[0]).strip() for row in rows[1:] if row and str(row[0]).strip()]
    return []


def _targeted_drug_brand_pairs(paragraphs: list[Any]) -> list[str]:
    marker = "上表涉及的已上市的药物名称及对应的商品名称"
    candidates = [str(text or "").strip() for text in paragraphs if marker in str(text or "")]
    targeted = next(
        (text for text in candidates if re.match(r"^\s*2\s*[.．]", text)),
        candidates[0] if candidates else "",
    )
    if not targeted:
        return []
    tail = targeted.split("：", 1)[-1]
    return [
        f"{drug.strip()}[{brand.strip()}]"
        for drug, brand in re.findall(r"([^、。：:\n]+)\[([^\]]+)\]", tail)
    ]


def _part3_gene_section_vafs(
    sections: Mapping[str, Mapping[str, Any]],
) -> list[float | None]:
    """Extract displayed VAFs from Part 3 gene-section headers in order."""
    values: list[float | None] = []
    for section in sections.values():
        header = str(section.get("text") or "").splitlines()[0:1]
        match = re.search(r"；\s*(\d+(?:\.\d+)?)%\s*$", header[0] if header else "")
        values.append(float(match.group(1)) if match else None)
    return values


def _prefix_match(sections: Mapping[str, Any], prefix: str) -> tuple[str | None, Any]:
    matches = [(key, value) for key, value in sections.items() if key.startswith(prefix)]
    if len(matches) != 1:
        return None, None
    return matches[0]


def _find_table(
    tables: list[Mapping[str, Any]], required_terms: list[str]
) -> Mapping[str, Any] | None:
    for table in tables:
        rows = list(table.get("rows") or [])
        header = "".join(str(cell) for row in rows[:2] for cell in row)
        if all(term in header for term in required_terms):
            return table
    return None


def _meaningful_lines(value: Any) -> list[str]:
    return [
        line.strip()
        for line in str(value or "").splitlines()
        if line.strip() and line.strip() not in {"-", "--", "—"}
    ]


def _variant_row_matches(row: list[Any], expected: Mapping[str, Any]) -> bool:
    if len(row) < 5:
        return False
    gene = str(row[0] or "").strip().upper()
    locus = re.sub(r"\s+", "", str(row[4] or "")).upper()
    c_hgvs = re.sub(r"\s+", "", str(expected.get("c_hgvs") or "")).upper()
    p_hgvs = re.sub(r"\s+", "", str(expected.get("p_hgvs") or "")).upper()
    return (
        gene == str(expected.get("gene") or "").strip().upper()
        and bool(c_hgvs)
        and c_hgvs in locus
        and (not p_hgvs or p_hgvs in locus)
    )


def _gene_order_from_multiline_result(value: Any) -> list[str]:
    lines = _meaningful_lines(value)
    if lines and lines[0].startswith("检出（"):
        lines = lines[1:]
    return [line.split("：", 1)[0].strip() for line in lines if "：" in line]


def _docx_runtime_contract(path: Path) -> dict[str, Any]:
    doc = Document(path)
    vertical_merges: dict[str, int] = {}
    for table in doc.tables:
        header = "".join(cell.text for row in table.rows[:2] for cell in row.cells)
        if all(term in header for term in ("基因名称", "转录本号", "染色体")):
            vertical_merges["variant_detail"] = table._tbl.xml.count("w:vMerge")
        if all(term in header for term in ("检测基因", "检测内容", "检测结果")):
            vertical_merges["nccn_results"] = table._tbl.xml.count("w:vMerge")

    greeting_honorifics: list[str] = []
    signature_drawings = 0
    repeated_full_stops = 0
    for paragraph in doc.element.xpath(".//w:p"):
        text = "".join(node.text or "" for node in paragraph.xpath(".//w:t"))
        repeated_full_stops += text.count("。。") + text.count("．．")
        if "尊敬的" in text:
            if "女士" in text:
                greeting_honorifics.append("女士")
            if "先生" in text:
                greeting_honorifics.append("先生")
        if "检测者" in text and "审核者" in text:
            signature_drawings += len(paragraph.xpath(".//w:drawing"))
    return {
        "vertical_merges": vertical_merges,
        "greeting_honorifics": greeting_honorifics,
        "signature_drawings": signature_drawings,
        "repeated_full_stops": repeated_full_stops,
    }


def validate_historical_golden_docx(
    *,
    contract: Mapping[str, Any],
    docx_path: str | Path,
    require_reference_sha: bool = False,
    reference_docx_path: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(docx_path)
    snapshot = _snapshot_docx(path)
    errors: list[dict[str, Any]] = []

    def check(code: str, passed: bool, *, expected: Any, actual: Any) -> None:
        if not passed:
            errors.append({"code": code, "expected": expected, "actual": actual})

    if not snapshot.get("openable"):
        return {
            "status": "FAIL",
            "case_alias": contract.get("case_alias"),
            "docx": str(path),
            "errors": [{"code": "DOCX_NOT_OPENABLE", "actual": snapshot.get("error")}],
        }

    expected = contract.get("expectations") or {}
    source = contract.get("source") or {}
    actual_sha = _file_sha256(path)
    reference_result: dict[str, Any] | None = None
    if require_reference_sha and reference_docx_path is None:
        errors.append({"code": "REFERENCE_DOCX_REQUIRED", "actual": None})
    if reference_docx_path is not None:
        expected_sha = source.get("reference_docx_sha256")
        reference_path = Path(reference_docx_path)
        reference_sha = _file_sha256(reference_path) if reference_path.is_file() else None
        reference_result = {
            "docx": str(reference_path),
            "docx_sha256": reference_sha,
        }
        check(
            "REFERENCE_SHA256",
            reference_sha == expected_sha,
            expected=expected_sha,
            actual=reference_sha,
        )

    check(
        "TABLE_COUNT",
        int(snapshot.get("table_count") or 0) == int(expected.get("table_count") or 0),
        expected=expected.get("table_count"),
        actual=snapshot.get("table_count"),
    )

    summary_order = _targeted_summary_gene_order(list(snapshot.get("tables") or []))
    expected_summary = expected.get("targeted_summary") or {}
    check(
        "TARGETED_SUMMARY_ROW_COUNT",
        len(summary_order) == int(expected_summary.get("row_count") or 0),
        expected=expected_summary.get("row_count"),
        actual=len(summary_order),
    )
    check(
        "TARGETED_SUMMARY_GENE_ORDER",
        summary_order == list(expected_summary.get("gene_order") or []),
        expected=expected_summary.get("gene_order"),
        actual=summary_order,
    )

    expected_brand_summary = expected.get("targeted_drug_brand_summary") or {}
    actual_brand_pairs = _targeted_drug_brand_pairs(
        list(snapshot.get("paragraphs") or [])
    )
    if expected_brand_summary:
        expected_brand_pairs = list(expected_brand_summary.get("ordered_pairs") or [])
        check(
            "TARGETED_DRUG_BRAND_SUMMARY_COUNT",
            len(actual_brand_pairs) == len(expected_brand_pairs),
            expected=len(expected_brand_pairs),
            actual=len(actual_brand_pairs),
        )
        check(
            "TARGETED_DRUG_BRAND_SUMMARY_ORDER",
            actual_brand_pairs == expected_brand_pairs,
            expected=expected_brand_pairs,
            actual=actual_brand_pairs,
        )

    tables = list(snapshot.get("tables") or [])
    variant_table = _find_table(
        tables, ["基因名称", "转录本号", "潜在获益靶向药物"]
    )
    variant_rows = list((variant_table or {}).get("rows") or [])[2:]
    summary_table = _find_table(tables, ["基因", "突变位点", "潜在获益靶向药物"])
    summary_rows = list((summary_table or {}).get("rows") or [])[1:]
    for row in expected.get("reviewed_variant_rows") or []:
        matches = [candidate for candidate in variant_rows if _variant_row_matches(candidate, row)]
        check(
            "REVIEWED_VARIANT_ROW_PRESENT",
            len(matches) == 1,
            expected={key: row.get(key) for key in ("gene", "c_hgvs", "p_hgvs")},
            actual=len(matches),
        )
        if len(matches) == 1:
            candidate = matches[0]
            try:
                actual_vaf = float(str(candidate[6]).replace("%", ""))
            except (IndexError, TypeError, ValueError):
                actual_vaf = None
            check(
                "REVIEWED_VARIANT_VAF",
                actual_vaf is not None
                and abs(actual_vaf - float(row.get("vaf"))) < 0.001,
                expected=row.get("vaf"),
                actual=actual_vaf,
            )
            for column, field, code in (
                (7, "benefit_count", "REVIEWED_VARIANT_BENEFIT_COUNT"),
                (8, "caution_count", "REVIEWED_VARIANT_CAUTION_COUNT"),
            ):
                actual_count = len(_meaningful_lines(candidate[column]))
                check(
                    code,
                    actual_count == int(row.get(field) or 0),
                    expected=row.get(field),
                    actual=actual_count,
                )

        summary_matches = [
            candidate
            for candidate in summary_rows
            if len(candidate) >= 4
            and str(candidate[0]).strip().upper()
            == str(row.get("gene") or "").strip().upper()
            and re.sub(r"\s+", "", str(row.get("c_hgvs") or "")).upper()
            in re.sub(r"\s+", "", str(candidate[1] or "")).upper()
        ]
        if int(row.get("benefit_count") or 0) or int(row.get("caution_count") or 0):
            check(
                "TARGETED_SUMMARY_REVIEWED_ROW_PRESENT",
                len(summary_matches) == 1,
                expected=row.get("gene"),
                actual=len(summary_matches),
            )
            if len(summary_matches) == 1:
                check(
                    "TARGETED_SUMMARY_BENEFIT_COUNT",
                    len(_meaningful_lines(summary_matches[0][2]))
                    == int(row.get("benefit_count") or 0),
                    expected=row.get("benefit_count"),
                    actual=len(_meaningful_lines(summary_matches[0][2])),
                )
                check(
                    "TARGETED_SUMMARY_CAUTION_COUNT",
                    len(_meaningful_lines(summary_matches[0][3]))
                    == int(row.get("caution_count") or 0),
                    expected=row.get("caution_count"),
                    actual=len(_meaningful_lines(summary_matches[0][3])),
                )

    biomarker_expectation = expected.get("biomarker_summary") or {}
    if biomarker_expectation:
        biomarker_table = _find_table(tables, ["TMB/MSI/其它生物标志物", "用药提示"])
        immune_order: list[str] = []
        for row in list((biomarker_table or {}).get("rows") or []):
            if row and "免疫正相关基因" in str(row[0]):
                immune_order = _gene_order_from_multiline_result(row[1])
                break
        check(
            "IMMUNE_POSITIVE_GENE_ORDER",
            immune_order == list(biomarker_expectation.get("immune_positive_gene_order") or []),
            expected=biomarker_expectation.get("immune_positive_gene_order"),
            actual=immune_order,
        )

    approved_expectation = expected.get("approved_drug_table") or {}
    if approved_expectation:
        approved_table = _find_table(tables, ["药物名称", "相关基因", "药物适应情况"])
        approved_names = [
            _meaningful_lines(row[0])[0]
            for row in list((approved_table or {}).get("rows") or [])[1:]
            if row and _meaningful_lines(row[0])
        ]
        check(
            "APPROVED_DRUG_TABLE_ORDER",
            approved_names == list(approved_expectation.get("drug_order") or []),
            expected=approved_expectation.get("drug_order"),
            actual=approved_names,
        )

    runtime_contract = _docx_runtime_contract(path)
    patient_letter = expected.get("patient_letter") or {}
    if patient_letter:
        expected_salutation = str(patient_letter.get("salutation") or "")
        actual_honorifics = runtime_contract["greeting_honorifics"]
        check(
            "PATIENT_SALUTATION",
            bool(actual_honorifics)
            and set(actual_honorifics) == {expected_salutation},
            expected=expected_salutation,
            actual=actual_honorifics,
        )
    for merge_name, merge_count in (expected.get("vertical_merges") or {}).items():
        check(
            "VERTICAL_MERGE_COUNT",
            runtime_contract["vertical_merges"].get(merge_name) == int(merge_count),
            expected={merge_name: merge_count},
            actual={merge_name: runtime_contract["vertical_merges"].get(merge_name)},
        )
    if "signature_drawings_min" in expected:
        check(
            "SIGNATURE_DRAWINGS",
            runtime_contract["signature_drawings"]
            >= int(expected.get("signature_drawings_min") or 0),
            expected={"min": expected.get("signature_drawings_min")},
            actual=runtime_contract["signature_drawings"],
        )
    check(
        "REPEATED_FULL_STOPS",
        runtime_contract["repeated_full_stops"] == 0,
        expected=0,
        actual=runtime_contract["repeated_full_stops"],
    )

    part3 = _extract_part3_sections(list(snapshot.get("paragraphs") or []))
    gene_sections = part3.get("gene_sections") or {}
    drug_sections = part3.get("drug_sections") or {}
    expected_part3 = expected.get("part3") or {}
    check(
        "PART3_GENE_SECTION_COUNT",
        len(gene_sections) == int(expected_part3.get("gene_section_count") or 0),
        expected=expected_part3.get("gene_section_count"),
        actual=len(gene_sections),
    )
    check(
        "PART3_DRUG_SECTION_COUNT",
        len(drug_sections) == int(expected_part3.get("drug_section_count") or 0),
        expected=expected_part3.get("drug_section_count"),
        actual=len(drug_sections),
    )

    actual_gene_order = list(gene_sections)
    expected_gene_order = list(expected_part3.get("gene_section_order") or [])
    if expected_gene_order:
        check(
            "PART3_GENE_SECTION_ORDER",
            actual_gene_order == expected_gene_order,
            expected=expected_gene_order,
            actual=actual_gene_order,
        )

    actual_gene_vafs = _part3_gene_section_vafs(gene_sections)
    if expected_part3.get("strict_vaf_descending") is True:
        vafs_complete = all(value is not None for value in actual_gene_vafs)
        numeric_vafs = [value for value in actual_gene_vafs if value is not None]
        vafs_descending = all(
            left >= right
            for left, right in zip(numeric_vafs, numeric_vafs[1:])
        )
        check(
            "PART3_GENE_SECTION_VAF_ORDER",
            vafs_complete and vafs_descending,
            expected="strict_descending",
            actual=actual_gene_vafs,
        )

    required_order = list(expected_part3.get("required_relative_order") or [])
    actual_relative_order = [key for key in actual_gene_order if key in required_order]
    check(
        "PART3_REQUIRED_RELATIVE_ORDER",
        actual_relative_order == required_order,
        expected=required_order,
        actual=actual_relative_order,
    )

    for row in expected_part3.get("required_gene_sections") or []:
        key = str(row.get("key") or "")
        section = gene_sections.get(key)
        check("PART3_GENE_SECTION_PRESENT", section is not None, expected=key, actual=None)
        if section is not None:
            actual = _normalized_text_sha256(section.get("text") or "")
            check(
                "PART3_GENE_SECTION_HASH",
                actual == row.get("normalized_text_sha256"),
                expected={"key": key, "sha256": row.get("normalized_text_sha256")},
                actual={"key": key, "sha256": actual},
            )

    for row in expected_part3.get("required_drug_sections") or []:
        prefix = str(row.get("key_prefix") or "")
        matched_key, section = _prefix_match(drug_sections, prefix)
        check("PART3_DRUG_SECTION_PRESENT", section is not None, expected=prefix, actual=matched_key)
        if section is not None:
            actual = _normalized_text_sha256(section.get("text") or "")
            check(
                "PART3_DRUG_SECTION_HASH",
                actual == row.get("normalized_text_sha256"),
                expected={"key_prefix": prefix, "sha256": row.get("normalized_text_sha256")},
                actual={"key": matched_key, "sha256": actual},
            )

    return {
        "schema_version": "1.0",
        "status": "PASS" if not errors else "FAIL",
        "case_alias": contract.get("case_alias"),
        "panel_id": contract.get("panel_id"),
        "docx": str(path),
        "docx_sha256": actual_sha,
        "reference": reference_result,
        "checks": {
            "table_count": snapshot.get("table_count"),
            "targeted_summary_gene_order": summary_order,
            "targeted_drug_brand_pairs": actual_brand_pairs,
            "part3_gene_section_count": len(gene_sections),
            "part3_gene_section_order": actual_gene_order,
            "part3_gene_section_vafs": actual_gene_vafs,
            "part3_drug_section_count": len(drug_sections),
            "runtime_contract": runtime_contract,
        },
        "errors": errors,
    }
