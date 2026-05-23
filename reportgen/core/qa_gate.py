"""Pre-deploy QA gate for panel report generation."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from reportgen.core.golden_case import GoldenCaseOptions, run_golden_case
from reportgen.core.report_diff import ReportDiffOptions, compare_reports
from reportgen.panels.validation import validate_panel_registry
from reportgen.utils.artifacts import write_json


DEFAULT_GATE_PANELS = ("crc_358_msi", "crc_301_msi", "lung_methylation")
DEFAULT_PYTEST_ARGS = ("backend/tests/test_report_regression.py", "-q")
DEFAULT_RUFF_PATHS = (
    "reportgen/cli.py",
    "reportgen/core/qa_gate.py",
    "reportgen/core/golden_case.py",
    "reportgen/core/report_diff.py",
    "reportgen/panels/validation.py",
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
    fail_on_warn: bool = True
    pytest_args: Sequence[str] = DEFAULT_PYTEST_ARGS
    ruff_paths: Sequence[str] = DEFAULT_RUFF_PATHS
    render: str = "none"
    render_required: bool = False
    log_level: str = "ERROR"
    max_samples: int = 30


def run_quality_gate(options: Optional[QualityGateOptions] = None) -> dict[str, Any]:
    """Run the end-to-end report generation quality gate."""
    opts = options or QualityGateOptions()
    project_root = Path(opts.project_root).resolve()
    output_root = _resolve_output_root(opts.output_root, project_root)
    output_root.mkdir(parents=True, exist_ok=True)

    steps: list[dict[str, Any]] = []
    started = time.perf_counter()
    steps.append(_run_panel_validation(project_root, fail_on_warn=opts.fail_on_warn))

    if opts.run_lint:
        steps.append(
            _run_command_step(
                "ruff_check",
                [sys.executable, "-m", "ruff", "check", *opts.ruff_paths],
                cwd=project_root,
                logs_dir=output_root / "logs",
            )
        )
    else:
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
        steps.extend(
            _run_golden_steps(
                opts,
                project_root=project_root,
                output_root=output_root,
            )
        )
    else:
        steps.append(_skipped_step("golden_cases", "golden case step disabled"))

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
            "fail_on_warn": opts.fail_on_warn,
            "pytest_args": list(opts.pytest_args),
            "ruff_paths": list(opts.ruff_paths),
            "render": opts.render,
            "render_required": opts.render_required,
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


def _skipped_step(name: str, message: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "SKIPPED",
        "duration_seconds": 0.0,
        "message": message,
    }


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
