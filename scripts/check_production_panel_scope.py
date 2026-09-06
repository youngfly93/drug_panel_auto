#!/usr/bin/env python3
"""Fail closed when a blocked panel is missing from a production scope guard."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import yaml

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVIEW_NOTICE = "报告组评审草稿（非临床交付）"
REQUIRED_DRAFT_GATES = (
    "scan_hardcoded_literals",
    "two_case_leak_test",
    "render_blank_page_check",
    "linux_visual_qa",
    "derived_input_matrix",
    "web_batch_uat",
    "qa_gate",
)


def draft_producer_fingerprint(project_root: Path, panel_id: str) -> str:
    """Bind review evidence to actual producer bytes, without a commit cycle.

    Readiness/audit receipts are excluded; changing a producer, family contract,
    shared rule or this panel's template invalidates the engineering evidence.
    Private patient enrichment and runtime files are never part of this digest.
    """
    paths: set[Path] = set()
    for pattern in (
        "reportgen/**/*.py",
        "backend/app/**/*.py",
        "frontend/src/**/*.ts",
        "frontend/src/**/*.vue",
        "config/*.yaml",
        "panels/*/panel.yaml",
        f"panels/{panel_id}/**/*",
        "scripts/build_lung_draft_packages.py",
        "scripts/validate_lung_small_panel_drafts.py",
    ):
        paths.update(project_root.glob(pattern))
    rows = {}
    for path in sorted(paths):
        if (
            not path.is_file()
            or path.name.startswith("._")
            or path.suffix not in {".py", ".yaml", ".docx", ".ts", ".vue"}
            or path.name == "patient_info.yaml"
        ):
            continue
        rows[str(path.relative_to(project_root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _draft_evidence_issues(
    project_root: Path, panel_id: str, manifest: dict[str, Any]
) -> list[str]:
    issues = []
    evidence = manifest.get("draft_generation_evidence")
    if not isinstance(evidence, dict):
        return [f"{panel_id}: draft_generation_evidence must be a mapping"]
    if evidence.get("scope") != "report_group_review_only":
        issues.append(f"{panel_id}: draft evidence must not grant clinical production")
    if evidence.get("user_authorized") is not True:
        issues.append(f"{panel_id}: draft deployment lacks explicit user authorization")
    if evidence.get("producer_sha256") != draft_producer_fingerprint(
        project_root, panel_id
    ):
        issues.append(f"{panel_id}: draft evidence producer fingerprint is stale")
    for gate in REQUIRED_DRAFT_GATES:
        record = (evidence.get("gates") or {}).get(gate) or {}
        if record.get("status") != "PASS" or not SHA256_RE.fullmatch(
            str(record.get("receipt_sha256") or "")
        ):
            issues.append(f"{panel_id}: draft gate {gate} lacks a passed receipt")
    if evidence.get("case_aliases") != ["A", "B", "C"]:
        issues.append(f"{panel_id}: draft evidence does not cover A/B/C")
    package_path = project_root / "panels" / panel_id / "panel.yaml"
    try:
        package = _read_manifest(package_path)
        templates = [
            t
            for t in package.get("templates") or []
            if t.get("id") == package.get("default_template")
        ]
        if (
            package.get("status") != "draft"
            or len(templates) != 1
            or templates[0].get("status") != "draft"
        ):
            raise ValueError(
                "draft eligibility requires a draft package and draft default template"
            )
        template = (package_path.parent / templates[0]["file"]).resolve()
        if not template.is_relative_to(package_path.parent.resolve()):
            raise ValueError("template escapes its package")
        if hashlib.sha256(template.read_bytes()).hexdigest() != evidence.get(
            "template_sha256"
        ):
            raise ValueError("draft evidence template checksum is stale")
        with ZipFile(template) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
            visible = "".join(
                t.text or ""
                for t in root.iter(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
                )
            )
        if REVIEW_NOTICE not in visible:
            raise ValueError("template lacks the visible non-clinical review boundary")
    except (OSError, KeyError, ValueError, yaml.YAMLError) as exc:
        issues.append(f"{panel_id}: {exc}")
    return issues


def _split_scope(value: str) -> set[str]:
    return {
        item.strip().lower()
        for item in re.split(r"[,;\s]+", str(value or ""))
        if item.strip()
    }


def _read_manifest(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: readiness manifest must be a mapping")
    return payload


def _promotion_evidence_issues(
    panel_id: str,
    evidence: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    for key in ("formal_reference_docx", "matched_source_excel"):
        record = evidence.get(key)
        if not isinstance(record, dict) or record.get("registered") is not True:
            issues.append(f"{panel_id}: {key} is not registered")
            continue
        digest = str(record.get("sha256") or "").strip().lower()
        if not SHA256_RE.fullmatch(digest):
            issues.append(f"{panel_id}: {key}.sha256 is not a valid SHA-256")
    if evidence.get("same_case_verified") is not True:
        issues.append(f"{panel_id}: same_case_verified is not true")
    review = evidence.get("report_group_secondary_review")
    if not isinstance(review, dict) or str(review.get("status") or "").upper() not in {
        "APPROVED",
        "PASS",
    }:
        issues.append(f"{panel_id}: report-group secondary review is not approved")
    for key in ("historical_golden_gate", "linux_visual_qa"):
        record = evidence.get(key)
        if (
            not isinstance(record, dict)
            or str(record.get("status") or "").upper() != "PASS"
        ):
            issues.append(f"{panel_id}: {key} has not passed")
    return issues


def validate_scope(
    *,
    project_root: Path,
    target: str,
    web_disabled: str,
    core_disabled: str,
    frontend_disabled: str,
) -> dict[str, Any]:
    scopes = {
        "web": _split_scope(web_disabled),
        "core": _split_scope(core_disabled),
        "frontend": _split_scope(frontend_disabled),
    }
    issues: list[str] = []
    checked: list[dict[str, Any]] = []
    manifest_specs = [
        (path, path.parent.name, "panel_package")
        for path in project_root.glob("panels/*/release_readiness.yaml")
        if not path.name.startswith("._")
    ]
    manifest_specs.extend(
        (path, path.stem, "product_intake")
        for path in project_root.glob("config/panel_product_readiness/*.yaml")
        if not path.name.startswith("._")
    )
    seen_panel_ids: set[str] = set()
    for path, expected_panel_id, source_kind in sorted(manifest_specs):
        try:
            manifest = _read_manifest(path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            issues.append(str(exc))
            continue
        panel_id = str(manifest.get("panel_id") or "").strip().lower()
        if not panel_id or panel_id != expected_panel_id:
            issues.append(f"{path}: panel_id must match its readiness record location")
            continue
        if panel_id in seen_panel_ids:
            issues.append(f"{panel_id}: duplicate release-readiness manifests")
            continue
        seen_panel_ids.add(panel_id)
        targets = {
            str(item).strip().lower()
            for item in manifest.get("enforced_targets", [])
            if str(item).strip()
        }
        production_eligible = manifest.get("production_eligible") is True
        draft_eligible = manifest.get("draft_generation_eligible") is True
        row = {
            "panel_id": panel_id,
            "source_kind": source_kind,
            "production_eligible": production_eligible,
            "draft_generation_eligible": draft_eligible,
            "enforced_for_target": target.lower() in targets,
        }
        checked.append(row)
        if production_eligible:
            evidence = manifest.get("promotion_evidence")
            if not isinstance(evidence, dict):
                issues.append(f"{panel_id}: promotion_evidence must be a mapping")
            else:
                issues.extend(_promotion_evidence_issues(panel_id, evidence))
            continue
        if draft_eligible:
            issues.extend(_draft_evidence_issues(project_root, panel_id, manifest))
            continue
        if target.lower() not in targets:
            continue
        for scope_name, disabled in scopes.items():
            if panel_id not in disabled:
                issues.append(
                    f"{panel_id}: BLOCKED panel is missing from {scope_name} "
                    f"disabled scope for {target}"
                )
    return {
        "schema_version": 1,
        "target": target,
        "status": "PASS" if not issues else "FAIL",
        "checked_manifests": checked,
        "scopes": {key: sorted(value) for key, value in scopes.items()},
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--target", default="iyun129")
    parser.add_argument(
        "--web-disabled",
        default=os.environ.get("RG_WEB_DISABLED_PROJECT_TYPES", ""),
    )
    parser.add_argument(
        "--core-disabled",
        default=os.environ.get("REPORTGEN_DISABLED_PROJECT_TYPES", ""),
    )
    parser.add_argument(
        "--frontend-disabled",
        default=os.environ.get("VITE_DISABLED_PROJECT_TYPES", ""),
    )
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    result = validate_scope(
        project_root=args.project_root.resolve(),
        target=args.target,
        web_disabled=args.web_disabled,
        core_disabled=args.core_disabled,
        frontend_disabled=args.frontend_disabled,
    )
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
