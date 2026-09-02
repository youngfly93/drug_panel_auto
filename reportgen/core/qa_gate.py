"""Pre-deploy QA gate for panel report generation."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from reportgen.core.golden_case import GoldenCaseOptions, run_golden_case
from reportgen.core.legacy_reference import (
    DATE_RE,
    REPORT_ID_RE,
    SAMPLE_ID_RE,
    LegacySnapshotOptions,
    build_legacy_reference_snapshots,
    snapshot_docx_report,
)
from reportgen.core.report_diff import ReportDiffOptions, compare_reports
from reportgen.knowledge.release_gate import run_knowledge_release_gate
from reportgen.panels.loader import PanelPackage, PanelPackageLoader
from reportgen.panels.validation import validate_panel_registry
from reportgen.utils.artifacts import write_json


DEFAULT_GATE_PANELS = ("crc_358_msi", "crc_301_msi", "lung_methylation")
LEGACY_REFERENCE_ROOT_ENV = "REPORTGEN_LEGACY_REPORTS_ROOT"
DEFAULT_PYTEST_ARGS = (
    "backend/tests/test_report_regression.py",
    "backend/tests/test_knowledge_governance.py",
    # 金标样式基线回归（慢，端到端生成对比）——后处理改动若弄坏关键表样式/
    # ❖颜色/签名/参考文献，qa-gate 即红。上生产前必跑。
    "backend/tests/test_style_baseline.py",
    "-q",
)
DEFAULT_RUFF_PATHS = (
    "reportgen/cli.py",
    "reportgen/core/processors/docx.py",
    "reportgen/core/qa_report.py",
    "reportgen/core/qa_gate.py",
    "reportgen/core/golden_case.py",
    "reportgen/core/legacy_reference.py",
    "reportgen/core/report_diff.py",
    "reportgen/core/report_generator.py",
    "reportgen/core/template_bridge_358.py",
    "reportgen/core/template_renderer.py",
    "reportgen/knowledge/gene_knowledge.py",
    "reportgen/knowledge/governance.py",
    "reportgen/knowledge/release_gate.py",
    "reportgen/rules/part3.py",
    "scripts/check_knowledge_release_ready.py",
    "reportgen/panels/loader.py",
    "reportgen/panels/validation.py",
    "reportgen/utils/libreoffice_profile.py",
)


@dataclass(frozen=True)
class QualityGateOptions:
    """Options for the reusable CI/pre-deploy quality gate."""

    project_root: str = "."
    output_root: Optional[str] = None
    panels: Sequence[str] = DEFAULT_GATE_PANELS
    run_lint: bool = True
    run_pytest: bool = True
    run_golden: bool = True
    run_diff: bool = True
    run_current_output: bool = True
    run_legacy_reference: bool = True
    fail_on_warn: bool = True
    pytest_args: Sequence[str] = DEFAULT_PYTEST_ARGS
    ruff_paths: Sequence[str] = DEFAULT_RUFF_PATHS
    render: str = "none"
    render_required: bool = False
    log_level: str = "ERROR"
    max_samples: int = 30
    legacy_source_root: Optional[str] = None
    legacy_panels: Sequence[str] = ()
    legacy_sample_count: Optional[int] = None
    legacy_required: bool = False


def run_quality_gate(options: Optional[QualityGateOptions] = None) -> dict[str, Any]:
    """Run the end-to-end report generation quality gate."""
    opts = options or QualityGateOptions()
    project_root = Path(opts.project_root).resolve()
    output_root = _resolve_output_root(opts.output_root, project_root)
    output_root.mkdir(parents=True, exist_ok=True)

    steps: list[dict[str, Any]] = []
    started = time.perf_counter()
    steps.append(_run_panel_validation(project_root, fail_on_warn=opts.fail_on_warn))
    steps.append(_run_knowledge_validation(project_root, output_root=output_root))

    if opts.run_lint:
        toolchain_step = _run_qa_toolchain_check(project_root)
        steps.append(toolchain_step)
        if toolchain_step["status"] == "PASS":
            steps.append(
                _run_command_step(
                    "ruff_check",
                    [sys.executable, "-m", "ruff", "check", *opts.ruff_paths],
                    cwd=project_root,
                    logs_dir=output_root / "logs",
                )
            )
        else:
            steps.append(
                _skipped_step(
                    "ruff_check",
                    "QA toolchain contract failed; lint was not executed.",
                )
            )
    else:
        steps.append(_skipped_step("qa_toolchain", "lint step disabled"))
        steps.append(_skipped_step("ruff_check", "lint step disabled"))

    if opts.run_pytest:
        steps.append(
            _run_command_step(
                "pytest_regression",
                [sys.executable, "-m", "pytest", *opts.pytest_args],
                cwd=project_root,
                logs_dir=output_root / "logs",
            )
        )
    else:
        steps.append(_skipped_step("pytest_regression", "pytest step disabled"))

    if opts.run_golden:
        golden_steps = _run_golden_steps(
            opts,
            project_root=project_root,
            output_root=output_root,
        )
        steps.extend(golden_steps)
    else:
        golden_steps = []
        steps.append(_skipped_step("golden_cases", "golden case step disabled"))

    if opts.run_current_output:
        steps.extend(
            _run_current_output_steps(
                opts,
                project_root=project_root,
                output_root=output_root / "current_output",
                prior_steps=golden_steps,
            )
        )
    else:
        steps.append(
            _skipped_step("current_output", "current output contract step disabled")
        )

    if opts.run_legacy_reference:
        steps.extend(
            _run_legacy_reference_steps(
                opts,
                project_root=project_root,
                output_root=output_root / "legacy_reference",
            )
        )
    else:
        steps.append(
            _skipped_step("legacy_reference", "legacy reference step disabled")
        )

    status = _overall_status(steps)
    result = {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "status": status,
        "ok": status == "PASS",
        "project_root": str(project_root),
        "output_root": str(output_root),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "options": {
            "panels": list(opts.panels),
            "run_lint": opts.run_lint,
            "run_pytest": opts.run_pytest,
            "run_golden": opts.run_golden,
            "run_diff": opts.run_diff,
            "run_current_output": opts.run_current_output,
            "run_legacy_reference": opts.run_legacy_reference,
            "fail_on_warn": opts.fail_on_warn,
            "pytest_args": list(opts.pytest_args),
            "ruff_paths": list(opts.ruff_paths),
            "render": opts.render,
            "render_required": opts.render_required,
            "legacy_source_root": opts.legacy_source_root
            or os.environ.get(LEGACY_REFERENCE_ROOT_ENV),
            "legacy_panels": list(opts.legacy_panels),
            "legacy_sample_count": opts.legacy_sample_count,
            "legacy_required": opts.legacy_required,
        },
        "summary": {
            "passed": sum(1 for step in steps if step["status"] == "PASS"),
            "warned": sum(1 for step in steps if step["status"] == "WARN"),
            "failed": sum(1 for step in steps if step["status"] == "FAIL"),
            "skipped": sum(1 for step in steps if step["status"] == "SKIPPED"),
        },
        "steps": steps,
    }
    report_file = output_root / "qa_gate_report.json"
    write_json(report_file, result)
    result["report_file"] = str(report_file)
    return result


def _run_panel_validation(project_root: Path, *, fail_on_warn: bool) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        report = validate_panel_registry(project_root=project_root)
        payload = report.to_dict()
        has_errors = bool(payload["summary"]["errors"])
        has_warnings = bool(payload["summary"]["warnings"])
        status = "FAIL" if has_errors or (fail_on_warn and has_warnings) else "PASS"
        if has_warnings and not fail_on_warn and not has_errors:
            status = "WARN"
        return {
            "name": "panel_validate",
            "status": status,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "summary": payload.get("summary"),
            "panels_checked": payload.get("panels_checked"),
            "issues": payload.get("issues") or [],
        }
    except Exception as exc:
        return _exception_step("panel_validate", started, exc)


def _run_qa_toolchain_check(project_root: Path) -> dict[str, Any]:
    """Verify the interpreter has the repository-pinned release tooling."""
    started = time.perf_counter()
    requirements_file = project_root / "requirements-qa.txt"
    result: dict[str, Any] = {
        "name": "qa_toolchain",
        "duration_seconds": 0.0,
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "requirements_file": str(requirements_file),
    }
    if not requirements_file.is_file():
        result.update(
            {
                "status": "FAIL",
                "issues": [
                    {
                        "level": "error",
                        "code": "QA_ENV_REQUIREMENTS_MISSING",
                        "message": "requirements-qa.txt is missing.",
                    }
                ],
            }
        )
        result["duration_seconds"] = round(time.perf_counter() - started, 3)
        return result

    requirement_text = requirements_file.read_text(encoding="utf-8")
    match = re.search(r"(?mi)^\s*ruff\s*==\s*([^\s#]+)", requirement_text)
    if not match:
        result.update(
            {
                "status": "FAIL",
                "issues": [
                    {
                        "level": "error",
                        "code": "QA_ENV_RUFF_PIN_MISSING",
                        "message": "requirements-qa.txt must contain an exact Ruff pin.",
                    }
                ],
            }
        )
        result["duration_seconds"] = round(time.perf_counter() - started, 3)
        return result

    required_version = match.group(1)
    try:
        installed_version = importlib_metadata.version("ruff")
    except importlib_metadata.PackageNotFoundError:
        installed_version = None
    result.update(
        {
            "required_ruff_version": required_version,
            "installed_ruff_version": installed_version,
        }
    )
    if installed_version is None:
        result.update(
            {
                "status": "FAIL",
                "issues": [
                    {
                        "level": "error",
                        "code": "QA_ENV_MISSING_DEPENDENCY",
                        "message": (
                            "Ruff is not installed in the QA interpreter; run "
                            "'python -m pip install -r requirements-qa.txt'."
                        ),
                    }
                ],
            }
        )
    elif installed_version != required_version:
        result.update(
            {
                "status": "FAIL",
                "issues": [
                    {
                        "level": "error",
                        "code": "QA_ENV_VERSION_MISMATCH",
                        "message": (
                            f"Ruff {installed_version} is installed but "
                            f"{required_version} is required."
                        ),
                    }
                ],
            }
        )
    else:
        result.update({"status": "PASS", "issues": []})
    result["duration_seconds"] = round(time.perf_counter() - started, 3)
    return result


def _run_knowledge_validation(
    project_root: Path, *, output_root: Path
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = run_knowledge_release_gate(
            project_root,
            output_path=output_root / "knowledge_release_gate.json",
        )
        return {
            "name": "knowledge_release_gate",
            "status": result["status"],
            "duration_seconds": round(time.perf_counter() - started, 3),
            "summary": result.get("summary") or {},
            "issues": result.get("issues") or [],
            "report_file": result.get("report_file"),
        }
    except Exception as exc:
        return _exception_step("knowledge_release_gate", started, exc)


def _run_golden_steps(
    opts: QualityGateOptions,
    *,
    project_root: Path,
    output_root: Path,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for panel in opts.panels:
        panel_id = str(panel).strip()
        if not panel_id:
            continue
        reference = _run_single_golden(
            panel_id,
            project_root=project_root,
            output_root=output_root / "golden" / panel_id / "reference",
            opts=opts,
            step_name=f"golden_{panel_id}_reference",
        )
        steps.append(reference)

        if not opts.run_diff:
            continue

        candidate = _run_single_golden(
            panel_id,
            project_root=project_root,
            output_root=output_root / "golden" / panel_id / "candidate",
            opts=opts,
            step_name=f"golden_{panel_id}_candidate",
        )
        steps.append(candidate)
        steps.append(
            _run_repeated_golden_diff(
                panel_id,
                reference,
                candidate,
                output_root=output_root / "diff" / panel_id,
                fail_on_warn=opts.fail_on_warn,
                max_samples=opts.max_samples,
            )
        )
    if not steps:
        steps.append(_skipped_step("golden_cases", "no panels selected"))
    return steps


def _run_current_output_steps(
    opts: QualityGateOptions,
    *,
    project_root: Path,
    output_root: Path,
    prior_steps: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    profiles = _select_current_output_profiles(opts, project_root=project_root)
    if not profiles:
        return [
            _skipped_step(
                "current_output",
                "no current output panels enabled by QA profile",
            )
        ]

    golden_outputs = _golden_output_steps_by_panel(prior_steps)
    steps: list[dict[str, Any]] = []
    for profile in profiles:
        panel = str(profile["panel_id"])
        source_name = str(profile.get("source") or "golden_reference")
        source_step = golden_outputs.get((panel, source_name))
        if not source_step:
            steps.append(
                _skipped_step(
                    f"current_output_{panel}",
                    f"source output not available: {source_name}",
                    panel=panel,
                )
            )
            continue
        if source_step.get("status") != "PASS":
            steps.append(
                _skipped_step(
                    f"current_output_{panel}",
                    f"source output did not pass: {source_step.get('name')}",
                    panel=panel,
                )
            )
            continue
        output_file = source_step.get("output_file")
        if not output_file:
            steps.append(
                _skipped_step(
                    f"current_output_{panel}",
                    f"source output file missing: {source_step.get('name')}",
                    panel=panel,
                )
            )
            continue
        steps.append(
            _run_single_current_output_contract(
                panel,
                output_file=Path(str(output_file)),
                output_root=output_root / panel,
                profile=profile,
                source_step=str(source_step.get("name") or ""),
                fail_on_warn=opts.fail_on_warn,
            )
        )
    return steps


def _golden_output_steps_by_panel(
    steps: Sequence[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    outputs: dict[tuple[str, str], dict[str, Any]] = {}
    for step in steps:
        panel = str(step.get("panel") or "")
        name = str(step.get("name") or "")
        if not panel:
            continue
        if name == f"golden_{panel}_reference":
            outputs[(panel, "golden_reference")] = step
        elif name == f"golden_{panel}_candidate":
            outputs[(panel, "golden_candidate")] = step
    return outputs


def _run_single_current_output_contract(
    panel: str,
    *,
    output_file: Path,
    output_root: Path,
    profile: dict[str, Any],
    source_step: str,
    fail_on_warn: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        snapshot = snapshot_docx_report(output_file, panel=panel)
        snapshot_file = output_root / "current_output_snapshot.json"
        write_json(snapshot_file, snapshot)
        issues = _audit_report_snapshot(snapshot, profile=profile)
        issues.extend(_audit_snapshot_file_privacy(snapshot_file, profile=profile))
        status = _status_from_issues(issues, fail_on_warn=fail_on_warn)
        return {
            "name": f"current_output_{panel}",
            "status": status,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "panel": panel,
            "source_step": source_step,
            "output_file": str(output_file),
            "snapshot_file": str(snapshot_file),
            "summary": {
                "features": snapshot.get("features") or {},
                "section_presence": snapshot.get("section_presence") or {},
                "table_count": snapshot.get("table_count"),
            },
            "qa_profile_file": profile.get("qa_profile_file"),
            "issues": issues,
        }
    except Exception as exc:
        return _exception_step(f"current_output_{panel}", started, exc, panel=panel)


def _run_legacy_reference_steps(
    opts: QualityGateOptions,
    *,
    project_root: Path,
    output_root: Path,
) -> list[dict[str, Any]]:
    profiles = _select_legacy_reference_profiles(opts, project_root=project_root)
    if not profiles:
        return [
            _skipped_step(
                "legacy_reference",
                "no legacy reference panels enabled by QA profile",
            )
        ]

    source_root = _resolve_legacy_source_root(opts, project_root=project_root)
    if not source_root.exists():
        return [
            _legacy_reference_unavailable_step(
                "legacy_reference",
                f"legacy source root not found: {source_root}",
                source_root=source_root,
                required=opts.legacy_required,
            )
        ]

    steps: list[dict[str, Any]] = []
    for profile in profiles:
        panel = str(profile["panel_id"])
        source_dir = source_root / str(profile["source_dir_name"])
        if not source_dir.exists():
            steps.append(
                _legacy_reference_unavailable_step(
                    f"legacy_reference_{panel}",
                    f"legacy source dir not found: {source_dir}",
                    source_root=source_root,
                    source_dir=source_dir,
                    required=opts.legacy_required,
                )
            )
            continue
        steps.append(
            _run_single_legacy_reference(
                panel,
                source_dir=source_dir,
                output_root=output_root / panel,
                sample_count=int(opts.legacy_sample_count or profile["sample_count"]),
                profile=profile,
                fail_on_warn=opts.fail_on_warn,
            )
        )
    return steps


def _select_legacy_reference_profiles(
    opts: QualityGateOptions,
    *,
    project_root: Path,
) -> list[dict[str, Any]]:
    profiles = {
        profile["panel_id"]: profile
        for profile in _load_legacy_reference_profiles(project_root)
    }
    requested = [
        str(panel).strip() for panel in opts.legacy_panels if str(panel).strip()
    ]
    if not requested:
        return [
            profile for profile in profiles.values() if bool(profile.get("enabled"))
        ]

    selected: list[dict[str, Any]] = []
    for panel in requested:
        profile = profiles.get(panel)
        if profile is None:
            profile = _default_legacy_reference_profile(panel)
        selected.append(profile)
    return selected


def _select_current_output_profiles(
    opts: QualityGateOptions,
    *,
    project_root: Path,
) -> list[dict[str, Any]]:
    profiles = {
        profile["panel_id"]: profile
        for profile in _load_current_output_profiles(project_root)
    }
    requested = [str(panel).strip() for panel in opts.panels if str(panel).strip()]
    if not requested:
        return [
            profile for profile in profiles.values() if bool(profile.get("enabled"))
        ]
    return [
        profiles[panel]
        for panel in requested
        if panel in profiles and bool(profiles[panel].get("enabled"))
    ]


def _load_legacy_reference_profiles(project_root: Path) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for package in PanelPackageLoader(project_root=project_root).load_all():
        profiles.append(_legacy_reference_profile_from_package(package))
    return profiles


def _load_current_output_profiles(project_root: Path) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for package in PanelPackageLoader(project_root=project_root).load_all():
        profiles.append(_current_output_profile_from_package(package))
    return profiles


def _legacy_reference_profile_from_package(package: PanelPackage) -> dict[str, Any]:
    raw = package.qa_profile.get("legacy_reference") or {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "panel_id": package.panel_id,
        "enabled": bool(raw.get("enabled", False)),
        "source_dir_name": str(raw.get("source_dir_name") or package.panel_id),
        "sample_count": int(raw.get("sample_count") or 5),
        "required_features": _severity_map(raw.get("required_features") or {}),
        "required_sections": _severity_map(raw.get("required_sections") or {}),
        "require_table_shapes": _severity(
            raw.get("require_table_shapes"), default="warn"
        ),
        "privacy_checks": _severity_map(raw.get("privacy_checks") or {}),
        "qa_profile_file": str(package.resolve_qa_profile_file()),
    }


def _current_output_profile_from_package(package: PanelPackage) -> dict[str, Any]:
    raw = package.qa_profile.get("current_output") or {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "panel_id": package.panel_id,
        "enabled": bool(raw.get("enabled", False)),
        "source": str(raw.get("source") or "golden_reference"),
        "required_features": _severity_map(raw.get("required_features") or {}),
        "required_sections": _severity_map(raw.get("required_sections") or {}),
        "require_table_shapes": _severity(
            raw.get("require_table_shapes"), default="warn"
        ),
        "privacy_checks": _severity_map(raw.get("privacy_checks") or {}),
        "qa_profile_file": str(package.resolve_qa_profile_file()),
    }


def _default_legacy_reference_profile(panel: str) -> dict[str, Any]:
    return {
        "panel_id": panel,
        "enabled": True,
        "source_dir_name": panel,
        "sample_count": 5,
        "required_features": {},
        "required_sections": {},
        "require_table_shapes": "warn",
        "privacy_checks": {
            "source_dir": "fail",
            "report_id": "fail",
            "sample_id": "fail",
            "date": "fail",
        },
        "qa_profile_file": "",
    }


def _severity_map(value: Any) -> dict[str, str]:
    if isinstance(value, list):
        return {str(item): "warn" for item in value if str(item).strip()}
    if not isinstance(value, dict):
        return {}
    return {
        str(key): _severity(severity)
        for key, severity in value.items()
        if str(key).strip()
    }


def _severity(value: Any, *, default: str = "warn") -> str:
    normalized = str(value or default).strip().lower()
    return normalized if normalized in {"off", "warn", "fail"} else default


def _resolve_legacy_source_root(
    opts: QualityGateOptions,
    *,
    project_root: Path,
) -> Path:
    raw = (
        opts.legacy_source_root
        or os.environ.get(LEGACY_REFERENCE_ROOT_ENV)
        or str(project_root / "legacy_reports_by_panel")
    )
    return Path(raw).expanduser().resolve()


def _legacy_reference_unavailable_step(
    name: str,
    message: str,
    *,
    source_root: Path,
    required: bool,
    source_dir: Optional[Path] = None,
) -> dict[str, Any]:
    step = {
        "name": name,
        "status": "FAIL" if required else "SKIPPED",
        "duration_seconds": 0.0,
        "message": message,
        "source_root": str(source_root),
    }
    if source_dir is not None:
        step["source_dir"] = str(source_dir)
    if required:
        step["issues"] = [
            {
                "level": "error",
                "code": "LEGACY_REFERENCE_SOURCE_MISSING",
                "message": message,
            }
        ]
    return step


def _run_single_legacy_reference(
    panel: str,
    *,
    source_dir: Path,
    output_root: Path,
    sample_count: int,
    profile: dict[str, Any],
    fail_on_warn: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = build_legacy_reference_snapshots(
            LegacySnapshotOptions(
                panel=panel,
                source_dir=str(source_dir),
                output_dir=str(output_root),
                sample_count=int(sample_count),
            )
        )
        issues = _audit_legacy_reference_output(
            output_root=output_root,
            expected_sample_count=int(sample_count),
            profile=profile,
        )
        status = _status_from_issues(issues, fail_on_warn=fail_on_warn)
        return {
            "name": f"legacy_reference_{panel}",
            "status": status,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "panel": panel,
            "source_dir": str(source_dir),
            "output_root": result.get("output_dir"),
            "manifest_file": result.get("manifest_file"),
            "markdown_file": result.get("markdown_file"),
            "summary": {
                "source_docx_count": result.get("source_docx_count"),
                "readable_docx_count": result.get("readable_docx_count"),
                "read_error_count": result.get("read_error_count"),
                "selected_count": result.get("selected_count"),
            },
            "qa_profile_file": profile.get("qa_profile_file"),
            "issues": issues,
        }
    except Exception as exc:
        return _exception_step(f"legacy_reference_{panel}", started, exc, panel=panel)


def _audit_legacy_reference_output(
    *,
    output_root: Path,
    expected_sample_count: int,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    manifest_path = output_root / "manifest.json"
    if not manifest_path.exists():
        return [
            _legacy_issue(
                "error",
                "LEGACY_MANIFEST_MISSING",
                f"legacy reference manifest not found: {manifest_path}",
            )
        ]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    privacy_checks = profile.get("privacy_checks") or {}
    source_dir_issue = _legacy_issue_from_severity(
        privacy_checks.get("source_dir"),
        "LEGACY_SOURCE_NOT_REDACTED",
        "legacy manifest must not persist source_dir by default",
    )
    if manifest.get("source_dir") != "<redacted>" and source_dir_issue:
        issues.append(source_dir_issue)

    source_count = int(manifest.get("source_docx_count") or 0)
    readable_count = int(manifest.get("readable_docx_count") or 0)
    selected_count = int(manifest.get("selected_count") or 0)
    if source_count <= 0:
        issues.append(
            _legacy_issue("error", "LEGACY_SOURCE_EMPTY", "no legacy DOCX files found")
        )
    if readable_count <= 0:
        issues.append(
            _legacy_issue(
                "error",
                "LEGACY_READABLE_EMPTY",
                "no readable legacy DOCX files found",
            )
        )
    if selected_count <= 0:
        issues.append(
            _legacy_issue(
                "error",
                "LEGACY_SELECTED_EMPTY",
                "no legacy reference samples were selected",
            )
        )
    if 0 < selected_count < min(max(1, expected_sample_count), readable_count):
        issues.append(
            _legacy_issue(
                "warning",
                "LEGACY_SELECTED_BELOW_TARGET",
                "selected legacy reference sample count is below target",
            )
        )

    selected_samples = manifest.get("selected_samples") or []
    for sample in selected_samples:
        issues.extend(_audit_legacy_reference_sample(sample, profile=profile))
    issues.extend(
        _audit_legacy_reference_privacy(output_root=output_root, profile=profile)
    )
    return issues


def _audit_legacy_reference_sample(
    sample: dict[str, Any],
    *,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    return _audit_report_snapshot(sample, profile=profile)


def _audit_report_snapshot(
    snapshot: dict[str, Any],
    *,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    reference_id = (
        snapshot.get("reference_id")
        or snapshot.get("source_label")
        or snapshot.get("detected_panel")
        or "<unknown>"
    )
    features = snapshot.get("features") or {}
    required_features = profile.get("required_features") or {}
    for field, severity in required_features.items():
        if features.get(field) is None:
            issue = _legacy_issue_from_severity(
                severity,
                "LEGACY_FEATURE_MISSING",
                f"{reference_id} missing extracted feature: {field}",
            )
            if issue:
                issues.append(issue)
    table_shape_issue = _legacy_issue_from_severity(
        profile.get("require_table_shapes"),
        "LEGACY_TABLE_SHAPES_MISSING",
        f"{reference_id} has no table shape fingerprint",
    )
    if not features.get("table_shape_counts") and table_shape_issue:
        issues.append(table_shape_issue)

    required_sections = profile.get("required_sections") or {}
    sections = snapshot.get("section_presence") or {}
    for section, severity in required_sections.items():
        if not sections.get(section):
            issue = _legacy_issue_from_severity(
                severity,
                "LEGACY_SECTION_MISSING",
                f"{reference_id} missing expected section: {section}",
            )
            if issue:
                issues.append(issue)
    return issues


def _audit_legacy_reference_privacy(
    *,
    output_root: Path,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    samples_dir = output_root / "samples"
    for sample_file in sorted(samples_dir.glob("*.json")):
        if sample_file.name.startswith("._"):
            continue
        issues.extend(_audit_snapshot_file_privacy(sample_file, profile=profile))
    return issues


def _audit_snapshot_file_privacy(
    snapshot_file: Path,
    *,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    privacy_checks = profile.get("privacy_checks") or {}
    issues: list[dict[str, Any]] = []
    text = snapshot_file.read_text(encoding="utf-8")
    report_id_issue = _legacy_issue_from_severity(
        privacy_checks.get("report_id"),
        "LEGACY_REPORT_ID_LEAK",
        f"report id leaked in {snapshot_file.name}",
    )
    if REPORT_ID_RE.search(text) and report_id_issue:
        issues.append(report_id_issue)
    sample_id_issue = _legacy_issue_from_severity(
        privacy_checks.get("sample_id"),
        "LEGACY_SAMPLE_ID_LEAK",
        f"sample id leaked in {snapshot_file.name}",
    )
    if SAMPLE_ID_RE.search(text) and sample_id_issue:
        issues.append(sample_id_issue)
    date_issue = _legacy_issue_from_severity(
        privacy_checks.get("date"),
        "LEGACY_DATE_LEAK",
        f"date-like value leaked in {snapshot_file.name}",
    )
    if DATE_RE.search(text) and date_issue:
        issues.append(date_issue)
    return issues


def _legacy_issue(level: str, code: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "message": message}


def _legacy_issue_from_severity(
    severity: Any,
    code: str,
    message: str,
) -> Optional[dict[str, str]]:
    normalized = _severity(severity, default="off")
    if normalized == "off":
        return None
    return _legacy_issue(
        "error" if normalized == "fail" else "warning",
        code,
        message,
    )


def _status_from_issues(issues: Sequence[dict[str, Any]], *, fail_on_warn: bool) -> str:
    if any(issue.get("level") == "error" for issue in issues):
        return "FAIL"
    if any(issue.get("level") == "warning" for issue in issues):
        return "FAIL" if fail_on_warn else "WARN"
    return "PASS"


def _run_single_golden(
    panel: str,
    *,
    project_root: Path,
    output_root: Path,
    opts: QualityGateOptions,
    step_name: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = run_golden_case(
            GoldenCaseOptions(
                panel=panel,
                config_dir=str(project_root / "config"),
                output_root=str(output_root),
                log_level=opts.log_level,
                render=opts.render,
                render_required=opts.render_required,
            )
        )
        failed_checks = [
            row for row in result.get("checks", []) if not row.get("passed")
        ]
        status = "PASS" if result.get("ok") and not failed_checks else "FAIL"
        return {
            "name": step_name,
            "status": status,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "panel": panel,
            "output_root": result.get("output_root"),
            "output_file": result.get("output_file"),
            "qa_report_file": result.get("qa_report_file"),
            "golden_report_file": result.get("golden_report_file"),
            "qa_status": result.get("qa_status"),
            "failed_checks": failed_checks,
            "errors": result.get("errors") or [],
        }
    except Exception as exc:
        return _exception_step(step_name, started, exc, panel=panel)


def _run_repeated_golden_diff(
    panel: str,
    reference: dict[str, Any],
    candidate: dict[str, Any],
    *,
    output_root: Path,
    fail_on_warn: bool,
    max_samples: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    reference_docx = reference.get("output_file")
    candidate_docx = candidate.get("output_file")
    if reference.get("status") != "PASS" or candidate.get("status") != "PASS":
        return {
            "name": f"golden_{panel}_repeat_diff",
            "status": "SKIPPED",
            "duration_seconds": round(time.perf_counter() - started, 3),
            "panel": panel,
            "message": "golden generation did not pass; diff skipped",
        }
    try:
        diff = compare_reports(
            ReportDiffOptions(
                reference_docx=str(reference_docx),
                candidate_docx=str(candidate_docx),
                output_dir=str(output_root),
                reference_qa=reference.get("qa_report_file"),
                candidate_qa=candidate.get("qa_report_file"),
                max_samples=int(max_samples),
            )
        )
        diff_status = str(diff.get("status") or "FAIL")
        status = "FAIL" if diff_status == "FAIL" else "PASS"
        if diff_status == "WARN":
            status = "FAIL" if fail_on_warn else "WARN"
        return {
            "name": f"golden_{panel}_repeat_diff",
            "status": status,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "panel": panel,
            "diff_status": diff_status,
            "summary": diff.get("summary"),
            "json_file": diff.get("json_file"),
            "markdown_file": diff.get("markdown_file"),
            "issues": diff.get("issues") or [],
        }
    except Exception as exc:
        return _exception_step(f"golden_{panel}_repeat_diff", started, exc, panel=panel)


def _run_command_step(
    name: str,
    command: Sequence[str],
    *,
    cwd: Path,
    logs_dir: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except Exception as exc:
        return _exception_step(name, started, exc)

    log_file = logs_dir / f"{_slug(name)}.log"
    log_file.write_text(
        "\n".join(
            [
                "$ " + " ".join(command),
                "",
                "[stdout]",
                completed.stdout or "",
                "",
                "[stderr]",
                completed.stderr or "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "name": name,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "command": list(command),
        "returncode": completed.returncode,
        "log_file": str(log_file),
        "stdout_tail": (completed.stdout or "")[-2000:],
        "stderr_tail": (completed.stderr or "")[-2000:],
    }


def _overall_status(steps: Sequence[dict[str, Any]]) -> str:
    if any(step.get("status") == "FAIL" for step in steps):
        return "FAIL"
    if any(step.get("status") == "WARN" for step in steps):
        return "WARN"
    return "PASS"


def _skipped_step(name: str, message: str, **extra: Any) -> dict[str, Any]:
    row = {
        "name": name,
        "status": "SKIPPED",
        "duration_seconds": 0.0,
        "message": message,
    }
    row.update(extra)
    return row


def _exception_step(
    name: str,
    started: float,
    exc: Exception,
    **extra: Any,
) -> dict[str, Any]:
    row = {
        "name": name,
        "status": "FAIL",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "error": str(exc),
        "error_type": type(exc).__name__,
    }
    row.update(extra)
    return row


def _resolve_output_root(output_root: Optional[str], project_root: Path) -> Path:
    if output_root:
        return Path(output_root).resolve()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (project_root / "tmp" / "qa_gate" / stamp).resolve()


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
