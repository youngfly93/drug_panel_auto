#!/usr/bin/env python3
# 步骤: 历史金标准发布门禁
# 上游: 脱敏契约 + 外部 reference/candidate DOCX + candidate QA
# 输出: 历史金标准门禁 JSON 与逐病例 Diff 产物
# 种子: 不适用（确定性校验）
"""Release gate for de-identified contracts and external historical reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.core.historical_golden_contract import (  # noqa: E402
    load_historical_golden_contract,
    validate_historical_golden_docx,
)
from reportgen.core.report_diff import ReportDiffOptions, compare_reports  # noqa: E402
from reportgen.knowledge.release_gate import (  # noqa: E402
    validate_secondary_review_receipt,
)


def _sha256_files(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    # Finder may create AppleDouble ``._*`` sidecars on removable/macOS
    # volumes.  They are neither Git inputs nor files shipped by ``git
    # archive``; hashing them made the same Git tree produce different release
    # fingerprints on macOS and Linux.  Ignore these filesystem metadata files
    # (and the equivalent Finder directory marker) at the common hash boundary.
    controlled_paths = {
        item.resolve()
        for item in paths
        if item.is_file()
        and not item.name.startswith("._")
        and item.name != ".DS_Store"
    }
    for path in sorted(controlled_paths):
        try:
            label = path.relative_to(ROOT).as_posix()
        except ValueError:
            label = path.name
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_report_diff_sha256(diff_result: dict[str, Any]) -> str:
    """Fingerprint every stable report-diff field without paths/timestamps.

    The normalized payload covers the overall result, summary, issue list and
    every comparison section (including text, tables, Part 3, styles, QA and
    document structure).  Only its SHA-256 is persisted in the committed
    contract, so the historical reference keeps its original hash while any
    unreviewed difference category invalidates the approved deviation.
    """
    normalized = {
        "schema_version": diff_result.get("schema_version"),
        "status": diff_result.get("status"),
        "summary": diff_result.get("summary"),
        "issues": diff_result.get("issues"),
        "sections": diff_result.get("sections"),
    }
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reference_deviation_receipt(
    contract: dict[str, Any],
    contract_path: Path | None,
) -> dict[str, Any]:
    """Bind a historical deviation to the current approved content bundle."""
    policy = contract.get("approved_reference_deviation") or {}
    if not policy:
        return {
            "status": "NOT_REQUIRED",
            "receipt_id": "",
            "contract_artifact_bound": False,
            "issues": [],
        }

    panel_id = str(contract.get("panel_id") or "").strip()
    expected_receipt_id = str(policy.get("approval_receipt_id") or "").strip()
    if not panel_id or not expected_receipt_id or contract_path is None:
        return {
            "status": "FAIL",
            "receipt_id": "",
            "contract_artifact_bound": False,
            "issues": [
                {
                    "code": "REFERENCE_DEVIATION_RECEIPT_METADATA_MISSING",
                    "message": "panel_id, approval_receipt_id and contract_path are required",
                }
            ],
        }

    receipt = validate_secondary_review_receipt(ROOT, panel_id)
    issues = list(receipt.get("issues") or [])
    actual_receipt_id = str(receipt.get("receipt_id") or "").strip()
    if actual_receipt_id != expected_receipt_id:
        issues.append(
            {
                "code": "REFERENCE_DEVIATION_RECEIPT_ID_MISMATCH",
                "message": (
                    f"expected={expected_receipt_id} actual={actual_receipt_id}"
                ),
            }
        )

    resolved_contract = contract_path.resolve()
    contract_labels = {str(resolved_contract)}
    try:
        contract_labels.add(resolved_contract.relative_to(ROOT).as_posix())
    except ValueError:
        pass
    contract_artifact_bound = any(
        str(artifact.get("path") or "") in contract_labels
        and artifact.get("sha256_matches") is True
        for artifact in receipt.get("artifacts") or []
    )
    if not contract_artifact_bound:
        issues.append(
            {
                "code": "REFERENCE_DEVIATION_CONTRACT_NOT_BOUND",
                "message": str(contract_path),
            }
        )

    return {
        **receipt,
        "status": "PASS"
        if receipt.get("status") == "PASS"
        and actual_receipt_id == expected_receipt_id
        and contract_artifact_bound
        else "FAIL",
        "contract_artifact_bound": contract_artifact_bound,
        "issues": issues,
    }


def _approved_reference_deviation(
    contract: dict[str, Any],
    diff_result: dict[str, Any],
    *,
    contract_path: Path | None = None,
) -> dict[str, Any]:
    """Validate an exact, committed deviation from a historical reference."""
    policy = contract.get("approved_reference_deviation") or {}
    receipt = _reference_deviation_receipt(contract, contract_path)
    actual_sha = _normalized_report_diff_sha256(diff_result)
    expected_sha = (
        str(policy.get("normalized_report_diff_sha256") or "").strip().lower()
    )
    approval_status = str(policy.get("approval_status") or "").strip()
    supersedes = str(policy.get("supersedes") or "").strip()
    approved = (
        diff_result.get("status") == "FAIL"
        and policy.get("policy") == "exact_normalized_report_diff_v1"
        and approval_status == "report_group_approved"
        and bool(supersedes)
        and re.fullmatch(r"[0-9a-f]{64}", expected_sha) is not None
        and actual_sha == expected_sha
        and receipt.get("status") == "PASS"
    )
    return {
        "approved": approved,
        "policy": policy.get("policy"),
        "approval_status": approval_status,
        "supersedes": supersedes,
        "expected_normalized_report_diff_sha256": expected_sha,
        "actual_normalized_report_diff_sha256": actual_sha,
        "approval_receipt": receipt,
    }


def _current_revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _renderer_fingerprint() -> dict[str, str]:
    executable = shutil.which("soffice") or shutil.which("libreoffice") or ""
    version = "unavailable"
    if executable:
        process = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = (process.stdout or process.stderr).strip() or "unknown"
    return {
        "platform": platform.system(),
        "machine": platform.machine(),
        "engine": Path(executable).name if executable else "none",
        "version": version,
    }


def _candidate_renderer_fingerprint(case: dict[str, Any]) -> dict[str, str]:
    """Validate the renderer attested for the candidate DOCX itself."""
    raw = case.get("candidate_renderer")
    if not isinstance(raw, dict):
        raise ValueError("candidate_renderer must be a mapping")
    required = (
        "platform",
        "machine",
        "engine",
        "version",
        "profile_mode",
        "pdf_renderer",
        "pdf_renderer_version",
        "font_substitution_profile",
        "font_substitution_profile_sha256",
    )
    result = {key: str(raw.get(key) or "").strip() for key in required}
    missing = [key for key, value in result.items() if not value]
    if missing:
        raise ValueError(
            "candidate_renderer is missing required fields: " + ", ".join(missing)
        )
    if not re.fullmatch(
        r"[0-9a-f]{64}", result["font_substitution_profile_sha256"].lower()
    ):
        raise ValueError(
            "candidate_renderer font_substitution_profile_sha256 must be SHA256"
        )
    evidence = str(raw.get("evidence") or "").strip()
    if evidence:
        result["evidence"] = evidence
    return result


def _required_sha256(case: dict[str, Any], field: str) -> str:
    value = str(case.get(field) or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{field} must be an explicit 64-character SHA256")
    return value


def discover_contracts() -> list[Path]:
    return sorted(
        path
        for path in ROOT.glob("panels/*/golden_cases/*.yaml")
        if not path.name.startswith("._")
    )


def validate_contract_registry() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    aliases: set[str] = set()
    medical_blocked = False
    for path in discover_contracts():
        try:
            contract = load_historical_golden_contract(path)
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        alias = str(contract.get("case_alias") or "")
        if alias in aliases:
            errors.append(f"duplicate case_alias: {alias}")
        aliases.add(alias)
        reference_sha = str((contract.get("source") or {}).get("reference_docx_sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", reference_sha):
            errors.append(f"{alias}: invalid reference_docx_sha256")
        expectations = contract.get("expectations") or {}
        for required in (
            "variant_counts",
            "targeted_summary",
            "targeted_drug_brand_summary",
            "part3",
            "reviewed_variant_rows",
            "vertical_merges",
        ):
            if not expectations.get(required):
                errors.append(f"{alias}: missing expectation {required}")
        variant_counts = expectations.get("variant_counts") or {}
        for field in ("targeted_drug_related", "targeted_or_immune_related"):
            if not isinstance(variant_counts.get(field), int):
                errors.append(f"{alias}: invalid variant count expectation {field}")
        medical_uat = contract.get("medical_uat") or {}
        medical_uat_status = str(medical_uat.get("status") or "").strip().lower()
        if medical_uat_status not in {"approved", "blocked"}:
            errors.append(f"{alias}: medical_uat.status must be approved or blocked")
        if medical_uat_status != "approved":
            medical_blocked = True
        blockers = list(medical_uat.get("blockers") or [])
        if medical_uat_status == "blocked" and not blockers:
            errors.append(f"{alias}: blocked medical UAT requires at least one blocker")
        deviation = contract.get("approved_reference_deviation") or {}
        if deviation:
            if deviation.get("policy") != "exact_normalized_report_diff_v1":
                errors.append(f"{alias}: unsupported approved reference deviation policy")
            deviation_sha = str(
                deviation.get("normalized_report_diff_sha256") or ""
            ).lower()
            if not re.fullmatch(r"[0-9a-f]{64}", deviation_sha):
                errors.append(f"{alias}: invalid approved normalized report diff SHA256")
            if deviation.get("approval_status") != "report_group_approved":
                errors.append(f"{alias}: approved reference deviation lacks report-group approval")
            if not str(deviation.get("approval_receipt_id") or "").strip():
                errors.append(f"{alias}: approved reference deviation lacks approval receipt")
            if not str(deviation.get("supersedes") or "").strip():
                errors.append(f"{alias}: approved reference deviation lacks supersedes")
            receipt = _reference_deviation_receipt(contract, path)
            if receipt.get("status") != "PASS":
                codes = ",".join(
                    str(issue.get("code") or "UNKNOWN")
                    for issue in receipt.get("issues") or []
                )
                errors.append(
                    f"{alias}: approved reference deviation receipt invalid ({codes})"
                )
        brand_order = list(
            (expectations.get("targeted_drug_brand_summary") or {}).get(
                "ordered_pairs"
            )
            or []
        )
        if not brand_order or len(brand_order) != len(set(brand_order)):
            errors.append(f"{alias}: targeted drug brand order is empty or duplicated")
        part3 = expectations.get("part3") or {}
        gene_count = int(part3.get("gene_section_count") or 0)
        gene_order = list(part3.get("gene_section_order") or [])
        for field in (
            "group_by_gene",
            "gene_order_by_max_vaf_descending",
            "within_gene_vaf_descending",
        ):
            if part3.get(field) is not True:
                errors.append(f"{alias}: Part 3 grouped VAF gate {field} is not enabled")
        if gene_count <= 0 or len(gene_order) != gene_count:
            errors.append(
                f"{alias}: Part 3 exact gene order does not match gene section count"
            )
        rows.append(
            {
                "case_alias": alias,
                "panel_id": contract.get("panel_id"),
                "contract_sha256": _sha256_files([path]),
                "medical_uat_status": medical_uat_status,
                "medical_uat_blockers": blockers,
            }
        )
    if not rows:
        errors.append("no historical golden contracts discovered")
    return {
        "status": "PASS" if not errors else "FAIL",
        "medical_status": "BLOCKED" if medical_blocked else "PASS",
        "contract_count": len(rows),
        "contracts": rows,
        "errors": errors,
    }


def _resolve_external(value: str, manifest_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    project_candidate = (ROOT / path).resolve()
    if project_candidate.exists():
        return project_candidate
    return (manifest_dir / path).resolve()


def _panel_hashes(panel_id: str, contract_path: Path) -> dict[str, str]:
    panel_root = ROOT / "panels" / panel_id
    rule_files = list((panel_root / "rules").glob("**/*")) + [
        panel_root / "panel.yaml",
        contract_path,
    ]
    knowledge_files = list((ROOT / "data/knowledge_bases/processed").glob("*"))
    return {
        "rules_sha256": _sha256_files(rule_files),
        "knowledge_sha256": _sha256_files(knowledge_files),
    }


def run_manifest_gate(manifest_path: Path, output_root: Path) -> dict[str, Any]:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    errors: list[str] = []
    current_revision = _current_revision()
    expected_revision = str(manifest.get("source_revision") or "")
    if expected_revision != current_revision:
        errors.append("manifest source_revision does not match HEAD")
    cases = manifest.get("cases") or []
    if not isinstance(cases, list) or not cases:
        errors.append("manifest cases must be a non-empty list")
        cases = []

    results: list[dict[str, Any]] = []
    medical_blocked = False
    for case in cases:
        alias = str(case.get("case_alias") or "")
        case_errors: list[str] = []
        candidate_source_revision = str(
            case.get("candidate_source_revision") or ""
        ).strip()
        if candidate_source_revision != current_revision:
            case_errors.append("candidate_source_revision does not match HEAD")
        try:
            declared_candidate_sha = _required_sha256(case, "candidate_sha256")
            declared_candidate_qa_sha = _required_sha256(
                case,
                "candidate_qa_sha256",
            )
        except ValueError as exc:
            errors.append(f"{alias or 'unnamed'}: {exc}")
            continue
        try:
            candidate_renderer = _candidate_renderer_fingerprint(case)
        except ValueError as exc:
            errors.append(f"{alias or 'unnamed'}: {exc}")
            continue
        try:
            contract_path = _resolve_external(str(case["contract"]), manifest_path.parent)
            reference_path = _resolve_external(str(case["reference_docx"]), manifest_path.parent)
            candidate_path = _resolve_external(str(case["candidate_docx"]), manifest_path.parent)
            contract = load_historical_golden_contract(contract_path)
        except Exception as exc:
            errors.append(f"{alias or 'unnamed'}: invalid case paths: {exc}")
            continue
        if alias != contract.get("case_alias"):
            errors.append(f"{alias}: contract alias mismatch")
        medical_uat = contract.get("medical_uat") or {}
        medical_uat_status = str(medical_uat.get("status") or "").strip().lower()
        medical_uat_blockers = list(medical_uat.get("blockers") or [])
        if medical_uat_status != "approved":
            medical_blocked = True
        contract_result = validate_historical_golden_docx(
            contract=contract,
            docx_path=candidate_path,
            require_reference_sha=True,
            reference_docx_path=reference_path,
        )
        diff_dir = output_root / alias / "report_diff"
        qa_value = str(case.get("candidate_qa") or "").strip()
        candidate_qa = (
            _resolve_external(qa_value, manifest_path.parent) if qa_value else None
        )
        diff_result = compare_reports(
            ReportDiffOptions(
                reference_docx=str(reference_path),
                candidate_docx=str(candidate_path),
                candidate_qa=str(candidate_qa) if candidate_qa else None,
                output_dir=str(diff_dir),
                max_samples=100,
                normalize_whitespace=True,
                ignore_reference_artifacts=True,
                style_metric_policy="warn",
            )
        )
        approved_deviation = _approved_reference_deviation(
            contract,
            diff_result,
            contract_path=contract_path,
        )
        effective_diff_status = str(diff_result.get("status") or "")
        if approved_deviation["approved"]:
            effective_diff_status = "PASS_WITH_APPROVED_DEVIATION"
        qa_status = "MISSING"
        qa_payload: dict[str, Any] = {}
        if candidate_qa and candidate_qa.is_file():
            qa_payload = json.loads(candidate_qa.read_text(encoding="utf-8"))
            qa_status = str(qa_payload.get("status") or "")
        allowed_qa = set(case.get("allowed_qa_statuses") or ["PASS"])
        actual_candidate_sha = str(contract_result.get("docx_sha256") or "")
        actual_candidate_qa_sha = (
            _sha256_file(candidate_qa)
            if candidate_qa and candidate_qa.is_file()
            else ""
        )
        if declared_candidate_sha != actual_candidate_sha:
            case_errors.append("candidate_sha256 does not match candidate DOCX")
        if declared_candidate_qa_sha != actual_candidate_qa_sha:
            case_errors.append("candidate_qa_sha256 does not match candidate QA")
        qa_build = qa_payload.get("build_provenance") or {}
        qa_source_revision = str(qa_build.get("source_revision") or "").strip()
        if qa_source_revision != current_revision:
            case_errors.append("candidate QA source_revision does not match HEAD")
        if qa_source_revision != candidate_source_revision:
            case_errors.append(
                "candidate_source_revision does not match candidate QA provenance"
            )
        if qa_build.get("source_dirty") is not False:
            case_errors.append("candidate QA was not generated from a clean source tree")
        qa_output_sha = str(
            (qa_payload.get("metrics") or {}).get("output_sha256") or ""
        ).strip()
        if qa_output_sha != actual_candidate_sha:
            case_errors.append("candidate QA output_sha256 does not match candidate DOCX")
        visual_check = (qa_payload.get("checks") or {}).get("visual_render") or {}
        if not (
            visual_check.get("status") == "PASS"
            and visual_check.get("requested") == "all"
            and visual_check.get("required") is True
        ):
            case_errors.append("candidate QA requires full, blocking visual render PASS")
        qa_renderer_raw = visual_check.get("renderer_fingerprint") or {}
        qa_renderer = {
            "platform": str(qa_renderer_raw.get("platform") or "").strip(),
            "machine": str(qa_renderer_raw.get("machine") or "").strip(),
            "engine": str(qa_renderer_raw.get("engine") or "").strip(),
            "version": str(qa_renderer_raw.get("engine_version") or "").strip(),
            "profile_mode": str(
                qa_renderer_raw.get("profile_mode") or ""
            ).strip(),
            "pdf_renderer": str(
                qa_renderer_raw.get("pdf_renderer") or ""
            ).strip(),
            "pdf_renderer_version": str(
                qa_renderer_raw.get("pdf_renderer_version") or ""
            ).strip(),
            "font_substitution_profile": str(
                qa_renderer_raw.get("font_substitution_profile") or ""
            ).strip(),
            "font_substitution_profile_sha256": str(
                qa_renderer_raw.get("font_substitution_profile_sha256") or ""
            ).strip(),
        }
        if qa_renderer.get("platform") != "Linux":
            case_errors.append("candidate visual QA was not rendered on Linux")
        if qa_renderer != candidate_renderer:
            case_errors.append(
                "candidate_renderer does not match candidate QA renderer fingerprint"
            )
        if contract_result.get("status") != "PASS":
            case_errors.append("historical contract failed")
        if diff_result.get("status") == "FAIL" and not approved_deviation["approved"]:
            case_errors.append("historical report diff failed")
        if qa_status not in allowed_qa:
            case_errors.append(f"candidate QA status is {qa_status}")
        errors.extend(f"{alias}: {message}" for message in case_errors)
        hashes = _panel_hashes(str(contract.get("panel_id")), contract_path)
        results.append(
            {
                "case_alias": alias,
                "panel_id": contract.get("panel_id"),
                "status": "PASS" if not case_errors else "FAIL",
                "contract_status": contract_result.get("status"),
                "diff_status": effective_diff_status,
                "raw_diff_status": diff_result.get("status"),
                "approved_reference_deviation": approved_deviation,
                "qa_status": qa_status,
                "medical_uat_status": medical_uat_status,
                "medical_uat_blockers": medical_uat_blockers,
                "candidate_renderer_fingerprint": candidate_renderer,
                "candidate_qa_renderer_fingerprint": qa_renderer,
                "candidate_source_revision": candidate_source_revision,
                "reference_sha256": contract_result.get("reference", {}).get("docx_sha256"),
                "candidate_sha256": actual_candidate_sha,
                "candidate_qa_sha256": actual_candidate_qa_sha,
                "candidate_qa_build_provenance": qa_build,
                "diff_warning_codes": sorted(
                    {
                        str(item.get("code"))
                        for item in diff_result.get("issues") or []
                        if item.get("level") == "warning"
                    }
                ),
                **hashes,
            }
        )
    return {
        "schema_version": "1.0",
        "status": "PASS" if not errors else "FAIL",
        "medical_status": "BLOCKED" if medical_blocked else "PASS",
        "source_revision": current_revision,
        "gate_runner_fingerprint": _renderer_fingerprint(),
        "case_count": len(results),
        "cases": results,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts-only", action="store_true")
    parser.add_argument("--manifest")
    parser.add_argument("--output-root", default=".work/historical_golden_release_gate")
    parser.add_argument("--output-json")
    args = parser.parse_args()

    registry = validate_contract_registry()
    result: dict[str, Any] = {
        "registry": registry,
        "status": registry["status"],
        "medical_status": registry["medical_status"],
    }
    if args.manifest:
        runtime = run_manifest_gate(
            Path(args.manifest).resolve(),
            Path(args.output_root).resolve(),
        )
        result["runtime"] = runtime
        result["medical_status"] = runtime["medical_status"]
        if runtime["status"] != "PASS":
            result["status"] = "FAIL"
    elif not args.contracts_only:
        result["status"] = "FAIL"
        result["error"] = "--manifest or --contracts-only is required"

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output_json:
        output_json = Path(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
