"""Pipeline status summarization helpers."""

from __future__ import annotations

from typing import Any, Mapping, Optional


def summarize_stage_results(
    stage_results: list[Mapping[str, Any]] | None,
    *,
    stage_results_file: Optional[str] = None,
) -> dict[str, Any]:
    """Return a compact PASS/WARN/FAIL summary for generation stages."""
    rows = [row for row in (stage_results or []) if isinstance(row, Mapping)]
    failed = [str(row.get("name") or "") for row in rows if row.get("status") == "FAIL"]
    warned = [str(row.get("name") or "") for row in rows if row.get("status") == "WARN"]
    skipped = [
        str(row.get("name") or "")
        for row in rows
        if row.get("status") in {"SKIP", "SKIPPED"}
    ]
    status = "FAIL" if failed else ("WARN" if warned else "PASS")
    return {
        "status": status,
        "stage_count": len(rows),
        "pass_count": sum(1 for row in rows if row.get("status") == "PASS"),
        "warn_count": len(warned),
        "fail_count": len(failed),
        "skipped_count": len(skipped),
        "failed_stages": failed,
        "warning_stages": warned,
        "skipped_stages": skipped,
        "stage_results_file": str(stage_results_file) if stage_results_file else None,
    }

