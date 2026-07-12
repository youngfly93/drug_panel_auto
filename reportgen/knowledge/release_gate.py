"""Production-only knowledge release gate and multidimensional coverage report."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from openpyxl import load_workbook

from reportgen.knowledge.governance import (
    effective_governance,
    load_and_validate_overlay,
    validate_knowledge_rows,
)
from reportgen.panels.loader import PanelPackageLoader


DEFAULT_PANELS = ("crc_301_msi", "crc_358_msi")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percent(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 2) if denominator else 100.0


def _validate_manifest(project_root: Path) -> dict[str, Any]:
    path = project_root / "data/knowledge_bases/processed/knowledge_base_manifest.yaml"
    issues: list[dict[str, Any]] = []
    if not path.exists():
        return {
            "status": "FAIL",
            "path": str(path),
            "artifacts": [],
            "issues": [
                {
                    "code": "MISSING_BASE_MANIFEST",
                    "message": "base knowledge manifest is missing",
                }
            ],
        }
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if str(raw.get("schema_version") or "") != "1.0":
        issues.append(
            {
                "code": "INVALID_BASE_MANIFEST_SCHEMA",
                "message": "schema_version must be 1.0",
            }
        )
    artifacts: list[dict[str, Any]] = []
    for artifact_id, item in (raw.get("artifacts") or {}).items():
        if not isinstance(item, Mapping):
            issues.append(
                {
                    "code": "INVALID_BASE_ARTIFACT",
                    "message": f"{artifact_id} must be a mapping",
                }
            )
            continue
        declared_path = Path(str(item.get("path") or ""))
        resolved = (project_root / declared_path).resolve()
        try:
            resolved.relative_to(project_root.resolve())
        except ValueError:
            issues.append(
                {
                    "code": "BASE_ARTIFACT_PATH_ESCAPE",
                    "message": str(declared_path),
                }
            )
            continue
        expected = str(item.get("sha256") or "").lower()
        actual = _sha256(resolved) if resolved.exists() else ""
        source_refs = item.get("source_refs") or []
        artifact = {
            "artifact_id": str(artifact_id),
            "path": str(declared_path),
            "exists": resolved.exists(),
            "sha256_matches": bool(expected and actual == expected),
            "source_type": str(item.get("source_type") or ""),
            "source_refs": len(source_refs) if isinstance(source_refs, list) else 0,
            "evidence_as_of": str(item.get("evidence_as_of") or ""),
        }
        artifacts.append(artifact)
        if not artifact["exists"]:
            issues.append(
                {
                    "code": "MISSING_BASE_ARTIFACT",
                    "message": str(declared_path),
                }
            )
        elif not artifact["sha256_matches"]:
            issues.append(
                {
                    "code": "BASE_ARTIFACT_HASH_MISMATCH",
                    "message": str(declared_path),
                    "expected": expected,
                    "actual": actual,
                }
            )
        if not artifact["source_type"] or not artifact["source_refs"]:
            issues.append(
                {
                    "code": "INCOMPLETE_BASE_PROVENANCE",
                    "message": str(declared_path),
                }
            )
    return {
        "status": "PASS" if not issues else "FAIL",
        "path": str(path.relative_to(project_root)),
        "review_status": str((raw.get("policy") or {}).get("review_status") or ""),
        "artifacts": artifacts,
        "issues": issues,
    }


def _base_genes(project_root: Path) -> set[str]:
    path = project_root / "data/knowledge_bases/processed/gene_knowledge_db.xlsx"
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet_name = next(
        (name for name in workbook.sheetnames if "基因变异解析" in name), ""
    )
    if not sheet_name:
        return set()
    rows = workbook[sheet_name].iter_rows(values_only=True)
    headers = [str(value or "").strip() for value in next(rows, ())]
    try:
        gene_index = headers.index("基因名称")
    except ValueError:
        gene_index = 0
    return {
        str(row[gene_index] or "").strip().upper()
        for row in rows
        if gene_index < len(row)
        and str(row[gene_index] or "").strip()
        and str(row[gene_index] or "").strip() != "基因"
    }


def _overlay_paths(package: Any) -> list[Path]:
    raw = getattr(package, "raw", None) or {}
    values: list[str] = []
    primary = raw.get("reviewed_part3_overlay")
    if primary:
        values.append(str(primary))
    additions = raw.get("reviewed_part3_overlay_additions") or []
    if isinstance(additions, str):
        additions = [additions]
    values.extend(str(value) for value in additions if str(value).strip())
    return [package._resolve_path(value).resolve() for value in values]


def _declared_genes(package: Any) -> set[str]:
    path = package.resolve_rule_file("knowledge_coverage")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        str(value).strip().upper()
        for value in raw.get("reportable_genes") or []
        if str(value).strip()
    }


def _validate_drug_rules(package: Any) -> dict[str, Any]:
    path = package.resolve_rule_file("drugs")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    governance = raw.get("governance") or {}
    issues: list[dict[str, Any]] = []
    if str(governance.get("schema_version") or "") != "1.0":
        issues.append(
            {
                "code": "INVALID_DRUG_GOVERNANCE_SCHEMA",
                "message": f"{package.panel_id} drugs governance must be 1.0",
            }
        )
    policy = raw.get("targeted_drug_rules") or {}
    rows: list[dict[str, Any]] = []
    for gene, rule in (policy.get("overrides") or {}).items():
        if isinstance(rule, Mapping):
            rows.append({"gene": gene, **dict(rule)})
    rows.extend(
        dict(row)
        for row in policy.get("reviewed_variant_overrides") or []
        if isinstance(row, Mapping)
    )
    targeted = validate_knowledge_rows(
        raw,
        rows,
        panel_id=package.panel_id,
        kind="targeted_drug",
    )
    # A source-only inheritance declaration legitimately has no local targeted
    # rows or targeted defaults; its source panel is validated independently.
    source_panel_id = str(policy.get("source_panel_id") or "")
    if rows:
        issues.extend(targeted["issues"])
    elif source_panel_id:
        targeted["status"] = "INHERITED"

    approved_rows = [
        row for row in raw.get("approved_drug_rows") or [] if isinstance(row, Mapping)
    ]
    approved_statuses: Counter[str] = Counter()
    approved_source_rows = 0
    for index, row in enumerate(approved_rows, start=1):
        effective = effective_governance(raw, row, "approved_drug")
        approved_statuses[effective["status"]] += 1
        approved_source_rows += int(bool(effective["source_refs"]))
        if not row.get("drug") or not str(row.get("indication") or "").strip():
            issues.append(
                {
                    "code": "INCOMPLETE_APPROVED_DRUG_ROW",
                    "message": f"approved drug row {index} is incomplete",
                }
            )
        if not effective["source_refs"]:
            issues.append(
                {
                    "code": "MISSING_APPROVED_DRUG_SOURCE",
                    "message": f"approved drug row {index} has no source",
                }
            )
    return {
        "path": str(path),
        "status": "PASS" if not issues else "FAIL",
        "version": str(raw.get("version") or ""),
        "updated": str(raw.get("updated") or ""),
        "targeted_rules": targeted,
        "approved_drug_rows": {
            "total_rows": len(approved_rows),
            "status_counts": dict(approved_statuses),
            "structured_source_rows": approved_source_rows,
            "structured_source_percent": _percent(
                approved_source_rows, len(approved_rows)
            ),
        },
        "issues": issues,
    }


def _panel_report(project_root: Path, panel_id: str, base_genes: set[str]) -> dict[str, Any]:
    package = PanelPackageLoader(project_root=project_root).load(panel_id)
    declared = _declared_genes(package)
    paths = _overlay_paths(package)
    overlay_reports: list[dict[str, Any]] = []
    runtime_overlay_genes: set[str] = set()
    all_gene_rows = 0
    all_drug_rows = 0
    gene_level_rows = 0
    variant_level_rows = 0
    event_level_drug_rows = 0
    status_counts: Counter[str] = Counter()
    structured_source_rows = 0
    evidence_level_rows = 0
    cancer_scope_rows = 0
    secondary_complete_rows = 0
    governance_total = 0
    issues: list[dict[str, Any]] = []

    for path in paths:
        origin_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        origin_panel = str((origin_data.get("source") or {}).get("panel") or panel_id)
        overlay_report = load_and_validate_overlay(path, origin_panel)
        overlay_reports.append(overlay_report)
        issues.extend(overlay_report["issues"])
        for kind, section in (("gene", "gene_sections"), ("drug", "drug_sections")):
            rows = [row for row in origin_data.get(section) or [] if isinstance(row, Mapping)]
            for row in rows:
                effective = effective_governance(origin_data, row, kind)
                governance_total += 1
                status_counts[effective["status"]] += 1
                structured_source_rows += int(bool(effective["source_refs"]))
                evidence_level_rows += int(bool(effective["evidence_level"]))
                cancer_scope_rows += int(bool(effective["cancer_scope"]))
                secondary_complete_rows += int(
                    effective["secondary_review_status"]
                    in {"completed", "approved", "report_group_approved"}
                )
                if kind == "gene":
                    all_gene_rows += 1
                    variant = bool(str(row.get("c_hgvs") or "").strip() or str(row.get("p_hgvs") or "").strip())
                    variant_level_rows += int(variant)
                    gene_level_rows += int(not variant)
                    if effective["runtime_eligible"]:
                        runtime_overlay_genes.add(str(row.get("gene") or "").strip().upper())
                else:
                    all_drug_rows += 1
                    event_level_drug_rows += int(bool(str(row.get("applicability") or "").strip()))

    runtime_gene_union = base_genes | runtime_overlay_genes
    missing = declared - runtime_gene_union
    drug_rules = _validate_drug_rules(package)
    issues.extend(drug_rules["issues"])
    if missing:
        issues.append(
            {
                "code": "RUNTIME_GENE_COVERAGE_GAP",
                "message": f"{len(missing)} declared genes have no runtime explanation",
                "genes": sorted(missing),
            }
        )
    if status_counts.get("not_recorded", 0):
        issues.append(
            {
                "code": "UNSTANDARDIZED_REVIEW_STATUS",
                "message": f"{status_counts['not_recorded']} overlay rows are not recorded",
            }
        )

    modern_review_rows = (
        status_counts.get("approved_for_runtime", 0)
        + status_counts.get("provisional_runtime", 0)
        + status_counts.get("needs_review", 0)
        + status_counts.get("rejected", 0)
        + status_counts.get("superseded", 0)
    )
    return {
        "panel_id": panel_id,
        "status": "PASS" if not issues else "FAIL",
        "overlay_files": overlay_reports,
        "drug_rules": drug_rules,
        "multidimensional_coverage": {
            "gene_explanation": {
                "total_genes": len(declared),
                "runtime_covered_genes": len(declared & runtime_gene_union),
                "percent": _percent(len(declared & runtime_gene_union), len(declared)),
                "missing_genes": sorted(missing),
            },
            "review_governance": {
                "total_overlay_rows": governance_total,
                "status_counts": dict(status_counts),
                "standardized_rows": governance_total - status_counts.get("not_recorded", 0),
                "standardized_percent": _percent(
                    governance_total - status_counts.get("not_recorded", 0),
                    governance_total,
                ),
                "modern_review_rows": modern_review_rows,
                "modern_review_percent": _percent(modern_review_rows, governance_total),
                "secondary_review_complete_rows": secondary_complete_rows,
                "secondary_review_complete_percent": _percent(
                    secondary_complete_rows, governance_total
                ),
            },
            "source_provenance": {
                "structured_source_rows": structured_source_rows,
                "structured_source_percent": _percent(
                    structured_source_rows, governance_total
                ),
                "evidence_level_rows": evidence_level_rows,
                "evidence_level_percent": _percent(
                    evidence_level_rows, governance_total
                ),
                "cancer_scope_rows": cancer_scope_rows,
                "cancer_scope_percent": _percent(cancer_scope_rows, governance_total),
            },
            "specificity": {
                "gene_rows": all_gene_rows,
                "gene_level_rows": gene_level_rows,
                "variant_level_rows": variant_level_rows,
                "drug_rows": all_drug_rows,
                "event_scoped_drug_rows": event_level_drug_rows,
            },
        },
        "issues": issues,
    }


def run_knowledge_release_gate(
    project_root: str | Path,
    *,
    panel_ids: Sequence[str] = DEFAULT_PANELS,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    manifest = _validate_manifest(root)
    base_genes = _base_genes(root)
    panels = [_panel_report(root, panel_id, base_genes) for panel_id in panel_ids]
    issues = list(manifest["issues"])
    for panel in panels:
        issues.extend(panel["issues"])
    result = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not issues else "FAIL",
        "base_manifest": manifest,
        "panels": panels,
        "summary": {
            "panels_checked": len(panels),
            "panels_passed": sum(panel["status"] == "PASS" for panel in panels),
            "issues": len(issues),
        },
        "issues": issues,
    }
    if output_path:
        target = Path(output_path)
        if not target.is_absolute():
            target = root / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        result["report_file"] = str(target)
    return result
