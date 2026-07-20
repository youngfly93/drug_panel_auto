"""Structured governance and provenance helpers for Panel knowledge entries."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


REVIEW_STATUSES = {
    "approved_for_runtime",
    "provisional_runtime",
    "legacy_runtime",
    "needs_review",
    "rejected",
    "superseded",
}
RUNTIME_STATUSES = {
    "approved_for_runtime",
    "provisional_runtime",
    "legacy_runtime",
}
BLOCKED_STATUSES = REVIEW_STATUSES - RUNTIME_STATUSES

PII_PATTERNS = {
    "sample_id": re.compile(r"\b(?:LZ|LW|lz|lw)\d{5,}\b"),
    "report_no": re.compile(r"报告编号"),
    "name_label": re.compile(r"姓名[:：]"),
    "sender": re.compile(r"送检者"),
    "date": re.compile(r"\b20\d{2}[./-]\d{1,2}[./-]\d{1,2}\b"),
}
SECTION_LEAK_PATTERNS = {
    "reading_notes": re.compile(r"3\.\s*阅读说明"),
    "reference_instruction": re.compile(r"文中参考文献及临床试验编号说明"),
    "glossary_instruction": re.compile(r"医学及生物学常见名词说明"),
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def stable_entry_id(panel_id: str, kind: str, row: Mapping[str, Any]) -> str:
    """Return a position-independent identifier for a knowledge selector."""
    payload = (
        _clean(panel_id).lower(),
        _clean(kind).lower(),
        _clean(row.get("gene")).upper(),
        _clean(row.get("c_hgvs")).upper(),
        _clean(row.get("p_hgvs")).upper(),
        _clean(row.get("type") or row.get("drug_type")).lower(),
        _clean(row.get("applicability")).lower(),
        _clean(row.get("drug_name")),
        _clean(row.get("header")),
    )
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()[:16]
    return f"{_clean(panel_id).lower()}-{_clean(kind).lower()}-{digest}"


def governance_defaults(
    data: Mapping[str, Any] | None,
    kind: str,
    row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve file-level governance defaults, including combined overlays."""
    tagged = _as_dict((row or {}).get("_governance_defaults"))
    if tagged:
        return tagged
    governance = _as_dict((data or {}).get("governance"))
    defaults = _as_dict(governance.get("defaults"))
    return _as_dict(defaults.get(kind))


def _source_ref(ref_type: str, ref_id: str, url: str = "") -> dict[str, str]:
    item = {"type": _clean(ref_type), "id": _clean(ref_id)}
    if _clean(url):
        item["url"] = _clean(url)
    return item


def _coerce_source_ref(value: Any) -> dict[str, str] | None:
    if isinstance(value, Mapping):
        ref_type = _clean(value.get("type") or value.get("source_type"))
        ref_id = _clean(value.get("id") or value.get("source_id"))
        url = _clean(value.get("url") or value.get("source_url"))
        if ref_type and (ref_id or url):
            return _source_ref(ref_type, ref_id or url, url)
        return None
    text = _clean(value)
    if not text:
        return None
    if text.startswith(("http://", "https://")):
        return _source_ref("web", text, text)
    if re.fullmatch(r"PMID:\d+", text, re.I):
        pmid = text.split(":", 1)[1]
        return _source_ref(
            "pubmed", f"PMID:{pmid}", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        )
    return _source_ref("declared_reference", text)


def _text_source_refs(text: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for bracket in re.findall(r"\[([^\]]+)]", text):
        for pmid in re.findall(r"(?<!\d)([1-9]\d{6,8})(?!\d)", bracket):
            refs.append(
                _source_ref(
                    "pubmed",
                    f"PMID:{pmid}",
                    f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                )
            )
        upper = bracket.upper()
        for name in ("NCBI", "OMIM", "GENECARDS", "FDA", "NCCN"):
            if name in upper:
                refs.append(_source_ref("database_or_guideline", name))
    for nct in re.findall(r"\bNCT\d{8}\b", text, re.I):
        refs.append(
            _source_ref(
                "clinical_trial",
                nct.upper(),
                f"https://clinicaltrials.gov/study/{nct.upper()}",
            )
        )
    return refs


def structured_source_refs(
    data: Mapping[str, Any] | None,
    row: Mapping[str, Any],
    kind: str,
) -> list[dict[str, str]]:
    """Collect declared and inline sources into a stable structured list."""
    defaults = governance_defaults(data, kind, row)
    candidates: list[Any] = []
    for source in (defaults.get("source_refs") or []):
        candidates.append(source)
    for key in ("source_refs", "sources"):
        raw = row.get(key)
        if isinstance(raw, (list, tuple)):
            candidates.extend(raw)
    source_url = _clean(row.get("source_url"))
    if source_url:
        candidates.append({"type": "web", "id": source_url, "url": source_url})
    for review_key in ("first_pass_review", "review_metadata"):
        review = _as_dict(row.get(review_key))
        candidates.extend(review.get("references") or [])
    text = "\n".join(
        _clean(row.get(field))
        for field in (
            "intro",
            "fixed_domain_text",
            "mutation_analysis",
            "relation",
            "clinical",
            "indication",
            "review_basis",
            "source_note",
        )
    )
    candidates.extend(_text_source_refs(text))

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        item = _coerce_source_ref(candidate)
        if not item:
            continue
        key = (item["type"], item["id"], item.get("url", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def effective_governance(
    data: Mapping[str, Any] | None,
    row: Mapping[str, Any],
    kind: str,
) -> dict[str, Any]:
    """Resolve status, review metadata and sources without mutating content."""
    defaults = governance_defaults(data, kind, row)
    first_pass = _as_dict(row.get("first_pass_review"))
    review_metadata = {
        **_as_dict(defaults.get("review_metadata")),
        **_as_dict(row.get("review_metadata")),
        **first_pass,
    }
    status = _clean(row.get("review_status") or defaults.get("review_status")).lower()
    if not status:
        status = "not_recorded"
    declared_runtime = row.get("runtime_eligible")
    if not isinstance(declared_runtime, bool):
        declared_runtime = defaults.get("runtime_eligible")
    runtime_eligible = (
        bool(declared_runtime)
        if isinstance(declared_runtime, bool)
        else status in RUNTIME_STATUSES
    )
    secondary_status = _clean(
        review_metadata.get("secondary_review_status")
        or row.get("secondary_review_status")
        or defaults.get("secondary_review_status")
    )
    return {
        "status": status,
        "runtime_eligible": runtime_eligible,
        "review_basis": _clean(
            row.get("review_basis")
            or defaults.get("review_basis")
            or review_metadata.get("decision")
        ),
        "reviewer": _clean(
            review_metadata.get("reviewer") or defaults.get("reviewer")
        ),
        "reviewer_type": _clean(
            review_metadata.get("reviewer_type") or defaults.get("reviewer_type")
        ),
        "reviewed_at": _clean(
            review_metadata.get("reviewed_at") or defaults.get("reviewed_at")
        ),
        "evidence_as_of": _clean(
            review_metadata.get("evidence_as_of")
            or row.get("evidence_as_of")
            or defaults.get("evidence_as_of")
        ),
        "evidence_level": _clean(
            row.get("evidence_level") or defaults.get("evidence_level")
        ),
        "cancer_scope": _clean(
            row.get("cancer_scope") or defaults.get("cancer_scope")
        ),
        "secondary_review_status": secondary_status,
        "risk_level": _clean(
            review_metadata.get("risk_level")
            or row.get("risk_level")
            or defaults.get("risk_level")
        ),
        "source_refs": structured_source_refs(data, row, kind),
    }


def row_text(row: Mapping[str, Any]) -> str:
    return "\n".join(
        _clean(row.get(field))
        for field in (
            "gene",
            "c_hgvs",
            "p_hgvs",
            "header",
            "drug_name",
            "intro",
            "fixed_domain_text",
            "mutation_analysis",
            "relation",
            "clinical",
            "indication",
        )
    )


def _selector(row: Mapping[str, Any], kind: str) -> tuple[str, ...]:
    fields = ["gene", "c_hgvs", "p_hgvs"]
    if kind in {"drug", "targeted_drug"}:
        fields.extend(["type", "applicability", "drug_name", "header"])
    return tuple(_clean(row.get(field)).upper() for field in fields)


def validate_knowledge_rows(
    data: Mapping[str, Any],
    rows: Iterable[Mapping[str, Any]],
    *,
    panel_id: str,
    kind: str,
) -> dict[str, Any]:
    """Validate one production knowledge collection and return gate metrics."""
    row_list = list(rows)
    selectors = [_selector(row, kind) for row in row_list]
    duplicate_selectors = [
        selector for selector, count in Counter(selectors).items() if count > 1
    ]
    issues: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    source_type_counts: Counter[str] = Counter()
    runtime_rows = 0
    secondary_complete = 0
    structured_sources = 0
    evidence_level_rows = 0
    cancer_scope_rows = 0

    for index, row in enumerate(row_list, start=1):
        gene = _clean(row.get("gene")).upper()
        entry_id = stable_entry_id(panel_id, kind, row)
        governance = effective_governance(data, row, kind)
        status = governance["status"]
        status_counts[status] += 1
        runtime_rows += int(governance["runtime_eligible"])
        structured_sources += int(bool(governance["source_refs"]))
        evidence_level_rows += int(bool(governance["evidence_level"]))
        cancer_scope_rows += int(bool(governance["cancer_scope"]))
        secondary_complete += int(
            governance["secondary_review_status"]
            in {"completed", "approved", "report_group_approved"}
        )
        for source in governance["source_refs"]:
            source_type_counts[source["type"]] += 1

        def add(code: str, message: str) -> None:
            issues.append(
                {
                    "code": code,
                    "message": message,
                    "entry_id": entry_id,
                    "gene": gene,
                    "row": index,
                }
            )

        if not gene:
            add("MISSING_GENE", "knowledge row has no gene")
        if status not in REVIEW_STATUSES:
            add("INVALID_REVIEW_STATUS", f"unsupported review status: {status}")
        if status in RUNTIME_STATUSES and not governance["runtime_eligible"]:
            add("RUNTIME_STATUS_CONFLICT", f"{status} must be runtime eligible")
        if status in BLOCKED_STATUSES and governance["runtime_eligible"]:
            add("RUNTIME_STATUS_CONFLICT", f"{status} must be blocked at runtime")
        if not governance["source_refs"]:
            add("MISSING_STRUCTURED_SOURCE", "knowledge row has no structured source")
        if status in {"approved_for_runtime", "provisional_runtime"}:
            for field in ("reviewer", "reviewed_at", "evidence_as_of"):
                if not governance[field]:
                    add("INCOMPLETE_REVIEW_METADATA", f"missing {field}")
        if status == "provisional_runtime" and not governance[
            "secondary_review_status"
        ]:
            add(
                "INCOMPLETE_REVIEW_METADATA",
                "provisional runtime row must declare secondary review status",
            )
        if kind == "drug":
            for field in ("drug_name", "relation", "clinical"):
                if not _clean(row.get(field)):
                    add("INCOMPLETE_DRUG_ROW", f"missing {field}")
        text = row_text(row)
        for name, pattern in PII_PATTERNS.items():
            if pattern.search(text):
                add("PII_RISK", f"matched {name}")
        for name, pattern in SECTION_LEAK_PATTERNS.items():
            if pattern.search(text):
                add("SECTION_LEAK", f"matched {name}")

    if duplicate_selectors:
        issues.append(
            {
                "code": "DUPLICATE_SELECTOR",
                "message": f"duplicate selectors: {len(duplicate_selectors)}",
                "examples": [list(item) for item in duplicate_selectors[:20]],
            }
        )
    total = len(row_list)
    return {
        "panel_id": panel_id,
        "kind": kind,
        "total_rows": total,
        "runtime_rows": runtime_rows,
        "blocked_rows": total - runtime_rows,
        "status_counts": dict(status_counts),
        "structured_source_rows": structured_sources,
        "structured_source_percent": round(100.0 * structured_sources / total, 2)
        if total
        else 100.0,
        "evidence_level_rows": evidence_level_rows,
        "evidence_level_percent": round(100.0 * evidence_level_rows / total, 2)
        if total
        else 100.0,
        "cancer_scope_rows": cancer_scope_rows,
        "cancer_scope_percent": round(100.0 * cancer_scope_rows / total, 2)
        if total
        else 100.0,
        "secondary_review_complete_rows": secondary_complete,
        "source_type_counts": dict(source_type_counts),
        "duplicate_selectors": len(duplicate_selectors),
        "issues": issues,
        "status": "PASS" if not issues else "FAIL",
    }


def load_and_validate_overlay(path: Path, panel_id: str) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    governance = _as_dict(data.get("governance"))
    issues: list[dict[str, Any]] = []
    if _clean(governance.get("schema_version")) != "1.0":
        issues.append(
            {
                "code": "INVALID_GOVERNANCE_SCHEMA",
                "message": "governance.schema_version must be 1.0",
            }
        )
    gene = validate_knowledge_rows(
        data,
        data.get("gene_sections") or [],
        panel_id=panel_id,
        kind="gene",
    )
    drug = validate_knowledge_rows(
        data,
        data.get("drug_sections") or [],
        panel_id=panel_id,
        kind="drug",
    )
    issues.extend(gene["issues"])
    issues.extend(drug["issues"])
    return {
        "panel_id": panel_id,
        "path": str(path),
        "status": "PASS" if not issues else "FAIL",
        "gene": gene,
        "drug": drug,
        "issues": issues,
    }
