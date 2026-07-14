#!/usr/bin/env python3
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


def _sha256_files(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted({item.resolve() for item in paths if item.is_file()}):
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
    required = ("platform", "engine", "version")
    result = {key: str(raw.get(key) or "").strip() for key in required}
    missing = [key for key, value in result.items() if not value]
    if missing:
        raise ValueError(
            "candidate_renderer is missing required fields: " + ", ".join(missing)
        )
    evidence = str(raw.get("evidence") or "").strip()
    if evidence:
        result["evidence"] = evidence
    return result


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
            "targeted_summary",
            "part3",
            "reviewed_variant_rows",
            "vertical_merges",
        ):
            if not expectations.get(required):
                errors.append(f"{alias}: missing expectation {required}")
        rows.append(
            {
                "case_alias": alias,
                "panel_id": contract.get("panel_id"),
                "contract_sha256": _sha256_files([path]),
            }
        )
    if not rows:
        errors.append("no historical golden contracts discovered")
    return {
        "status": "PASS" if not errors else "FAIL",
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
    for case in cases:
        alias = str(case.get("case_alias") or "")
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
        qa_status = "MISSING"
        if candidate_qa and candidate_qa.is_file():
            qa_status = str(json.loads(candidate_qa.read_text(encoding="utf-8")).get("status") or "")
        allowed_qa = set(case.get("allowed_qa_statuses") or ["PASS"])
        case_errors: list[str] = []
        if contract_result.get("status") != "PASS":
            case_errors.append("historical contract failed")
        if diff_result.get("status") == "FAIL":
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
                "diff_status": diff_result.get("status"),
                "qa_status": qa_status,
                "candidate_renderer_fingerprint": candidate_renderer,
                "reference_sha256": contract_result.get("reference", {}).get("docx_sha256"),
                "candidate_sha256": contract_result.get("docx_sha256"),
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
    result: dict[str, Any] = {"registry": registry, "status": registry["status"]}
    if args.manifest:
        runtime = run_manifest_gate(
            Path(args.manifest).resolve(),
            Path(args.output_root).resolve(),
        )
        result["runtime"] = runtime
        if runtime["status"] != "PASS":
            result["status"] = "FAIL"
    elif not args.contracts_only:
        result["status"] = "FAIL"
        result["error"] = "--manifest or --contracts-only is required"

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
