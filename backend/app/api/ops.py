"""Read-only production diagnostics endpoints.

The payload is intentionally sanitized: no Excel filenames, report paths,
patient fields, task errors, or free-form warnings are returned.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.task import Task, TaskResult
from app.schemas.common import ApiResponse
from app.services.batch_lifecycle import (
    BATCH_ACTIVE_STATUSES,
    BATCH_QUEUED_STATUSES,
    BATCH_WORKING_STATUSES,
)
from app.services.generation_queue import queue_stats
from app.services.runtime_instance_lock import runtime_instance_lock_status
from app.services.task_recovery import last_recovery_summary

router = APIRouter(prefix="/admin/ops", tags=["ops"])


DEFAULT_RUNTIME_DIR = Path("/media/desk16/iyun6208/apps/reportgen-web-runtime")
DEFAULT_BACKUP_DIR = Path("/media/desk16/iyun6208/apps/reportgen-web-backups")
DOWNLOAD_EVENT_TYPES = {
    "report_download_started",
    "report_download_completed",
    "report_download_slow",
    "report_download_failed",
}
TERMINAL_DOWNLOAD_EVENT_TYPES = {
    "report_download_completed",
    "report_download_slow",
    "report_download_failed",
}
DISK_WARNING_PERCENT = 80
DISK_DANGER_PERCENT = 90
BACKUP_WARNING_HOURS = 30
BACKUP_DANGER_HOURS = 48
DOWNLOAD_SLOW_WARNING_MS = 30_000
LOAD_TEST_MIN_UNITS = 10
LOAD_TEST_PASS_RATE = 98.0
LOAD_TEST_WARN_RATE = 95.0
LOAD_TEST_P95_WARNING_SECONDS = 900
RETENTION_DEFAULTS = {
    "backup_keep_days": 30,
    "release_keep_count": 8,
    "preview_keep_days": 7,
    "log_keep_days": 14,
    "upload_keep_days": 30,
    "report_keep_days": 180,
    "zip_keep_days": 14,
    "audit_log_keep_days": 365,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _runtime_dir() -> Path:
    return Path(os.environ.get("RG_WEB_RUNTIME_DIR") or DEFAULT_RUNTIME_DIR)


def _backup_dir() -> Path:
    return Path(os.environ.get("RG_WEB_BACKUP_DIR") or DEFAULT_BACKUP_DIR)


def _read_text(path: Path, *, max_bytes: int = 65536) -> str:
    try:
        with path.open("rb") as handle:
            data = handle.read(max_bytes)
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def _tail_lines(path: Path, *, line_count: int = 1000, max_bytes: int = 2_000_000) -> list[str]:
    if line_count <= 0:
        return []
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            data = handle.read()
    except OSError:
        return []
    return data.decode("utf-8", errors="replace").splitlines()[-line_count:]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(_read_text(path, max_bytes=262144))
    except (json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _retention_policy() -> dict[str, Any]:
    return {
        "backup_keep_days": _env_int("BACKUP_KEEP_DAYS", RETENTION_DEFAULTS["backup_keep_days"]),
        "release_keep_count": _env_int("RELEASE_KEEP_COUNT", RETENTION_DEFAULTS["release_keep_count"]),
        "preview_keep_days": _env_int("PREVIEW_KEEP_DAYS", RETENTION_DEFAULTS["preview_keep_days"]),
        "log_keep_days": _env_int("LOG_KEEP_DAYS", RETENTION_DEFAULTS["log_keep_days"]),
        "upload_keep_days": _env_int("UPLOAD_KEEP_DAYS", RETENTION_DEFAULTS["upload_keep_days"]),
        "report_keep_days": _env_int("REPORT_KEEP_DAYS", RETENTION_DEFAULTS["report_keep_days"]),
        "zip_keep_days": _env_int("ZIP_KEEP_DAYS", RETENTION_DEFAULTS["zip_keep_days"]),
        "audit_log_keep_days": _env_int(
            "AUDIT_LOG_KEEP_DAYS",
            RETENTION_DEFAULTS["audit_log_keep_days"],
        ),
    }


def _safe_path_name(path_text: str | None) -> str | None:
    if not path_text:
        return None
    return Path(path_text).name


def _read_current_release(runtime_dir: Path) -> dict[str, Any]:
    release_path = _read_text(runtime_dir / "current_release", max_bytes=4096).strip()
    release_name = _safe_path_name(release_path)
    revision = None
    if release_path:
        revision = _read_text(Path(release_path) / "REVISION", max_bytes=4096).strip() or None
    return {
        "release": release_name,
        "revision_short": revision[:8] if revision else None,
        "revision": revision,
    }


def _disk_usage(path: Path) -> dict[str, Any]:
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        usage = shutil.disk_usage(probe)
    except OSError:
        return {"available": False}

    used = usage.total - usage.free
    used_percent = round((used / usage.total) * 100, 2) if usage.total else None
    return {
        "available": True,
        "total_bytes": usage.total,
        "used_bytes": used,
        "free_bytes": usage.free,
        "used_percent": used_percent,
    }


def _bucket_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "top_level_entries": 0}
    try:
        top_level_entries = sum(1 for _ in path.iterdir())
    except OSError:
        top_level_entries = None
    return {"exists": True, "top_level_entries": top_level_entries}


def _libreoffice_listener_status() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["pgrep", "-f", "soffice.*port=2202"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"checked": False, "running": None}
    return {"checked": True, "running": result.returncode == 0}


def _task_counts(db: Session) -> dict[str, Any]:
    rows = db.query(Task.status, func.count(Task.id)).group_by(Task.status).all()
    raw_by_status = {
        "queued": 0,
        "preflight": 0,
        "generating": 0,
        "qa": 0,
        "pending": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "partial_failed": 0,
        "cancelled": 0,
    }
    for status, count in rows:
        raw_by_status[str(status or "unknown")] = int(count)
    total = sum(raw_by_status.values())
    by_status = dict(raw_by_status)
    by_status["pending"] = sum(
        raw_by_status.get(status, 0) for status in BATCH_QUEUED_STATUSES
    )
    by_status["running"] = sum(
        raw_by_status.get(status, 0) for status in BATCH_WORKING_STATUSES
    )
    return {
        "total": total,
        "by_status": by_status,
        "by_stage": raw_by_status,
        "failed_total": by_status.get("failed", 0) + by_status.get("partial_failed", 0),
    }


def _recent_tasks(db: Session, *, limit: int) -> list[dict[str, Any]]:
    rows = (
        db.query(Task)
        .order_by(Task.created_at.desc())
        .limit(max(0, min(limit, 50)))
        .all()
    )
    return [
        {
            "id": task.id,
            "task_type": task.task_type,
            "status": task.status,
            "project_type": task.project_type,
            "total_files": task.total_files,
            "completed_files": task.completed_files,
            "failed_files": task.failed_files,
            "created_at": _iso(task.created_at),
            "started_at": _iso(task.started_at),
            "completed_at": _iso(task.completed_at),
            "duration_seconds": task.duration_seconds,
        }
        for task in rows
    ]


def _download_event_name(event: dict[str, Any]) -> str:
    return str(event.get("event_type") or event.get("message") or "")


def _sanitize_download_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": event.get("timestamp"),
        "event_type": _download_event_name(event),
        "task_id": event.get("task_id"),
        "task_type": event.get("task_type"),
        "task_status": event.get("task_status"),
        "project_type": event.get("project_type"),
        "download_kind": event.get("download_kind"),
        "file_size_bytes": event.get("file_size_bytes"),
        "file_size_mb": event.get("file_size_mb"),
        "duration_ms": event.get("duration_ms"),
        "throughput_mbps": event.get("throughput_mbps"),
        "range_request": bool(event.get("range_header")),
        "cf_ray_present": bool(event.get("cf_ray")),
        "error_type": event.get("error_type"),
    }


def _download_diagnostics(
    log_path: Path,
    *,
    event_limit: int,
    tail_line_count: int = 5000,
    since: datetime | None = None,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for line in _tail_lines(log_path, line_count=tail_line_count):
        if "report_download_" not in line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if _download_event_name(payload) not in DOWNLOAD_EVENT_TYPES:
            continue
        if since:
            event_time = _parse_datetime(str(payload.get("timestamp") or ""))
            if not event_time or event_time < since:
                continue
        events.append(payload)

    terminal = [
        event
        for event in events
        if _download_event_name(event) in TERMINAL_DOWNLOAD_EVENT_TYPES
    ]
    durations = [
        float(event["duration_ms"])
        for event in terminal
        if isinstance(event.get("duration_ms"), (int, float))
    ]
    sizes = [
        float(event["file_size_bytes"])
        for event in terminal
        if isinstance(event.get("file_size_bytes"), (int, float))
    ]
    recent = [_sanitize_download_event(event) for event in terminal[-event_limit:]]
    return {
        "log_present": log_path.exists(),
        "summary": {
            "events": len(events),
            "started": sum(
                1 for event in events if _download_event_name(event) == "report_download_started"
            ),
            "terminal": len(terminal),
            "completed": sum(
                1 for event in terminal if _download_event_name(event) == "report_download_completed"
            ),
            "slow": sum(
                1 for event in terminal if _download_event_name(event) == "report_download_slow"
            ),
            "failed": sum(
                1 for event in terminal if _download_event_name(event) == "report_download_failed"
            ),
            "avg_duration_ms": round(mean(durations), 3) if durations else None,
            "max_duration_ms": round(max(durations), 3) if durations else None,
            "largest_file_mb": round(max(sizes) / 1024 / 1024, 3) if sizes else None,
        },
        "recent_terminal_events": recent,
    }


def _line_timestamp(line: str) -> str | None:
    if len(line) < 19:
        return None
    timestamp = line[:19]
    try:
        datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return timestamp


def _last_line_matching(lines: list[str], *needles: str) -> str | None:
    for line in reversed(lines):
        if any(needle in line for needle in needles):
            return line
    return None


def _classify_watchdog_line(line: str | None, *, ok: str, warn: str, fail: str) -> dict[str, Any]:
    if not line:
        return {"status": "unknown", "last_at": None}
    if ok in line:
        status = "ok"
    elif warn in line:
        status = "warn"
    elif fail in line or "restart" in line:
        status = "fail"
    else:
        status = "unknown"
    return {"status": status, "last_at": _line_timestamp(line)}


def _watchdog_status(log_path: Path) -> dict[str, Any]:
    lines = _tail_lines(log_path, line_count=300)
    web_line = _last_line_matching(lines, "web ok", "web fail", "web restart")
    tunnel_line = _last_line_matching(lines, "tunnel ok", "tunnel warn", "tunnel fail", "tunnel restart")
    libreoffice_line = _last_line_matching(lines, "libreoffice listener")
    disk_line = _last_line_matching(lines, "disk warn")
    return {
        "log_present": log_path.exists(),
        "last_event_at": _line_timestamp(lines[-1]) if lines else None,
        "web": _classify_watchdog_line(web_line, ok="web ok", warn="web warn", fail="web fail"),
        "tunnel": _classify_watchdog_line(
            tunnel_line,
            ok="tunnel ok",
            warn="tunnel warn",
            fail="tunnel fail",
        ),
        "libreoffice": {
            "status": "ok" if libreoffice_line and "listener ok" in libreoffice_line else "missing"
            if libreoffice_line
            else "unknown",
            "last_at": _line_timestamp(libreoffice_line) if libreoffice_line else None,
        },
        "disk": {
            "status": "warn" if disk_line else "ok",
            "last_at": _line_timestamp(disk_line) if disk_line else None,
        },
    }


def _maintenance_status(log_path: Path) -> dict[str, Any]:
    lines = _tail_lines(log_path, line_count=500)
    backup_line = _last_line_matching(lines, "backup complete")
    verify_line = _last_line_matching(lines, "verify complete")
    cleanup_line = _last_line_matching(lines, "cleanup complete")
    running_line = _last_line_matching(lines, "maintenance already running")
    return {
        "log_present": log_path.exists(),
        "last_event_at": _line_timestamp(lines[-1]) if lines else None,
        "last_backup_at": _line_timestamp(backup_line) if backup_line else None,
        "last_verify_at": _line_timestamp(verify_line) if verify_line else None,
        "last_cleanup_at": _line_timestamp(cleanup_line) if cleanup_line else None,
        "last_lock_notice_at": _line_timestamp(running_line) if running_line else None,
    }


def _backup_item(path: Path) -> dict[str, Any]:
    stat_result = path.stat()
    manifest = _load_json(path.with_suffix(path.suffix + ".manifest.json"))
    sha256_text = _read_text(path.with_suffix(path.suffix + ".sha256"), max_bytes=256).strip()
    sha256 = sha256_text.split()[0] if sha256_text else None
    revision = manifest.get("revision")
    return {
        "filename": path.name,
        "size_bytes": stat_result.st_size,
        "modified_at": datetime.fromtimestamp(stat_result.st_mtime, timezone.utc).isoformat(),
        "sha256_prefix": sha256[:12] if sha256 else None,
        "manifest": {
            "present": bool(manifest),
            "created_at": manifest.get("created_at"),
            "revision_short": revision[:8] if isinstance(revision, str) else None,
            "included_storage_roots": manifest.get("included_storage_roots") or [],
            "storage_stats": manifest.get("storage_stats") or {},
            "db_backup": manifest.get("db_backup") or {},
        },
    }


def _backup_status(backup_dir: Path, *, limit: int = 5) -> dict[str, Any]:
    if not backup_dir.exists():
        return {"backup_dir_present": False, "latest": None, "items": []}
    archives = sorted(
        backup_dir.glob("reportgen-web-backup-*.tar.gz"),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
    items = [_backup_item(path) for path in archives[:limit]]
    return {
        "backup_dir_present": True,
        "latest": items[0] if items else None,
        "items": items,
    }


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        payload = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return payload if isinstance(payload, list) else []


def _issue_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("error_type", "type", "message", "error", "detail", "title"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return str(item)


def _classify_issue(text: str) -> str:
    value = text.lower()
    if "timeout" in value or "timed out" in value or "超时" in text:
        return "生成超时"
    if "download" in value or "下载" in text:
        return "下载链路问题"
    if "qa" in value or "质控" in text or "校验" in text:
        return "QA/质控风险"
    if "template" in value or "docxtpl" in value or "jinja" in value or "模板" in text:
        return "模板渲染错误"
    if "excel" in value or "xlsx" in value or "sheet" in value or "工作表" in text:
        return "Excel 数据问题"
    if "字段" in text or "validation" in value or "required" in value:
        return "字段校验问题"
    if "libreoffice" in value or "soffice" in value or "word" in value or "刷新" in text:
        return "Word 刷新问题"
    if "permission" in value or "denied" in value or "路径" in text or "path" in value:
        return "文件权限/路径问题"
    return "其他错误/警告"


def _count_issues(counter: Counter[tuple[str, str]], severity: str, items: list[Any]) -> None:
    for item in items:
        text = _issue_text(item).strip()
        if text:
            counter[(severity, _classify_issue(text))] += 1


def _qa_status_from_output(output_path: str | None) -> str | None:
    payload = _qa_payload_from_output(output_path)
    status = payload.get("status") if payload else None
    return str(status).upper() if status else None


def _qa_payload_from_output(output_path: str | None) -> dict[str, Any]:
    if not output_path:
        return {}
    path = Path(output_path).with_suffix(".qa.json")
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _count_qa_reasons(counter: Counter[tuple[str, str]], qa_report: dict[str, Any]) -> None:
    status = str(qa_report.get("status") or "").upper()
    if status not in {"FAIL", "WARN"}:
        return

    checks = qa_report.get("checks") or {}
    template_contract = checks.get("template_contract") or {}
    missing_paths = {
        str(value)
        for value in (
            list(template_contract.get("missing_paths") or [])
            + list(template_contract.get("missing_required_variables") or [])
        )
    }
    if {"report_date_compact", "report_date_dot"} & missing_paths:
        counter[("error", "QA: 报告日期缺失或未进入模板上下文")] += 1
    if "receive_date_compact" in missing_paths:
        counter[("error", "QA: 收样日期缺失或未进入模板上下文")] += 1
    other_missing = {
        value
        for value in missing_paths
        if value not in {"report_date_compact", "report_date_dot", "receive_date_compact"}
    }
    if other_missing:
        counter[("error", "QA: 模板上下文变量缺失")] += len(other_missing)

    missing_lists = template_contract.get("missing_required_lists") or []
    missing_tables = template_contract.get("missing_required_tables") or []
    if missing_lists:
        counter[("error", "QA: 模板循环列表缺失")] += len(missing_lists)
    if missing_tables:
        counter[("error", "QA: 模板表格结构缺失")] += len(missing_tables)

    style_check = checks.get("docx_style_rules") or {}
    if style_check.get("status") == "FAIL":
        failures = style_check.get("failures") or []
        counter[("error", "QA: DOCX 表格样式规则失败")] += max(1, len(failures))

    issue_codes = {
        str(issue.get("code") or "")
        for issue in (qa_report.get("issues") or [])
        if isinstance(issue, dict)
    }
    for code in sorted(issue_codes):
        if code in {"", "TEMPLATE_CONTRACT_FAILED", "DOCX_STYLE_RULES", "PIPELINE_FAILED"}:
            continue
        counter[("error", f"QA: {code}")] += 1


def _empty_file_counts() -> dict[str, int]:
    return {
        "total": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "pending": 0,
        "running": 0,
    }


def _task_unit_counts(task: Task, results: list[TaskResult]) -> dict[str, int]:
    counts = _empty_file_counts()
    if task.task_type == "batch":
        status_counts = Counter((result.status or "pending") for result in results)
        observed_total = sum(status_counts.values())
        total = max(
            int(task.total_files or 0),
            observed_total,
            int(task.completed_files or 0) + int(task.failed_files or 0),
        )
        counts.update(
            {
                "total": total,
                "completed": int(status_counts.get("completed") or task.completed_files or 0),
                "failed": int(status_counts.get("failed") or task.failed_files or 0),
                "cancelled": int(status_counts.get("cancelled") or 0),
                "pending": sum(
                    int(status_counts.get(status) or 0)
                    for status in BATCH_QUEUED_STATUSES
                ),
                "running": sum(
                    int(status_counts.get(status) or 0)
                    for status in BATCH_WORKING_STATUSES
                ),
            }
        )
        accounted = (
            counts["completed"]
            + counts["failed"]
            + counts["cancelled"]
            + counts["pending"]
            + counts["running"]
        )
        if counts["total"] > accounted and task.status in BATCH_ACTIVE_STATUSES:
            counts["pending"] += counts["total"] - accounted
        return counts

    counts["total"] = 1
    if task.status == "completed":
        counts["completed"] = 1
    elif task.status in {"failed", "partial_failed"}:
        counts["failed"] = 1
    elif task.status == "cancelled":
        counts["cancelled"] = 1
    elif task.status == "running":
        counts["running"] = 1
    else:
        counts["pending"] = 1
    return counts


def _percentile(values: list[float], percentile: float) -> float | None:
    clean = sorted(float(value) for value in values if isinstance(value, (int, float)))
    if not clean:
        return None
    if len(clean) == 1:
        return round(clean[0], 3)
    position = (len(clean) - 1) * (percentile / 100)
    lower = int(position)
    upper = min(lower + 1, len(clean) - 1)
    weight = position - lower
    return round(clean[lower] * (1 - weight) + clean[upper] * weight, 3)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 2)


def _gate_check(check_id: str, label: str, status: str, value: str, threshold: str) -> dict[str, str]:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "value": value,
        "threshold": threshold,
    }


def _load_test_gate(data: dict[str, Any]) -> dict[str, Any]:
    totals = data["totals"]
    durations = data["durations"]
    downloads = data["downloads"]["summary"]
    qa = data["qa"]
    checks: list[dict[str, str]] = []

    total_units = int(totals["units_total"])
    success_rate = totals["success_rate"]
    if total_units < LOAD_TEST_MIN_UNITS:
        checks.append(
            _gate_check(
                "sample_size",
                "压测样本量",
                "warning",
                str(total_units),
                f">= {LOAD_TEST_MIN_UNITS} 份",
            )
        )
    else:
        checks.append(
            _gate_check("sample_size", "压测样本量", "pass", str(total_units), f">= {LOAD_TEST_MIN_UNITS} 份")
        )

    if success_rate is None:
        checks.append(_gate_check("success_rate", "生成成功率", "warning", "-", f">= {LOAD_TEST_PASS_RATE}%"))
    elif success_rate < LOAD_TEST_WARN_RATE:
        checks.append(
            _gate_check(
                "success_rate",
                "生成成功率",
                "block",
                f"{success_rate:.2f}%",
                f">= {LOAD_TEST_PASS_RATE}%",
            )
        )
    elif success_rate < LOAD_TEST_PASS_RATE:
        checks.append(
            _gate_check(
                "success_rate",
                "生成成功率",
                "warning",
                f"{success_rate:.2f}%",
                f">= {LOAD_TEST_PASS_RATE}%",
            )
        )
    else:
        checks.append(
            _gate_check(
                "success_rate",
                "生成成功率",
                "pass",
                f"{success_rate:.2f}%",
                f">= {LOAD_TEST_PASS_RATE}%",
            )
        )

    failed_units = int(totals["units_failed"])
    checks.append(
        _gate_check(
            "failed_units",
            "生成失败",
            "block" if failed_units else "pass",
            str(failed_units),
            "0",
        )
    )

    active_units = int(totals["units_pending"]) + int(totals["units_running"])
    checks.append(
        _gate_check(
            "active_units",
            "未完成文件",
            "warning" if active_units else "pass",
            str(active_units),
            "0",
        )
    )

    qa_fail = int(qa["fail"])
    qa_warn = int(qa["warn"])
    qa_status = "block" if qa_fail else "warning" if qa_warn else "pass"
    checks.append(
        _gate_check("qa_risk", "QA 风险", qa_status, f"FAIL {qa_fail} / WARN {qa_warn}", "FAIL 0 / WARN 0")
    )

    download_failed = int(downloads.get("failed") or 0)
    download_slow = int(downloads.get("slow") or 0)
    download_status = "block" if download_failed else "warning" if download_slow else "pass"
    checks.append(
        _gate_check(
            "download_quality",
            "下载质量",
            download_status,
            f"失败 {download_failed} / 慢 {download_slow}",
            "失败 0 / 慢 0",
        )
    )

    p95_task_seconds = durations.get("p95_task_seconds")
    if isinstance(p95_task_seconds, (int, float)) and p95_task_seconds > LOAD_TEST_P95_WARNING_SECONDS:
        duration_status = "warning"
        value = f"{p95_task_seconds:.1f}s"
    elif isinstance(p95_task_seconds, (int, float)):
        duration_status = "pass"
        value = f"{p95_task_seconds:.1f}s"
    else:
        duration_status = "warning"
        value = "-"
    checks.append(
        _gate_check(
            "p95_duration",
            "P95 生成耗时",
            duration_status,
            value,
            f"<= {LOAD_TEST_P95_WARNING_SECONDS}s",
        )
    )

    if any(check["status"] == "block" for check in checks):
        status = "block"
        title = "暂不建议放行"
    elif any(check["status"] == "warning" for check in checks):
        status = "warning"
        title = "可试运行，需人工确认"
    else:
        status = "pass"
        title = "压测指标通过"
    return {"status": status, "title": title, "checks": checks}


def _project_key(project_type: str | None) -> str:
    return project_type or "unknown"


def _load_test_summary(db: Session, *, window_hours: int, recent_batch_limit: int) -> dict[str, Any]:
    runtime_dir = _runtime_dir()
    since_aware = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    since_naive = _utc_naive_now() - timedelta(hours=window_hours)
    tasks = (
        db.query(Task)
        .filter(Task.created_at >= since_naive)
        .order_by(Task.created_at.desc())
        .all()
    )
    task_ids = [task.id for task in tasks]
    result_rows: list[tuple[TaskResult, str | None]] = []
    if task_ids:
        result_rows = (
            db.query(TaskResult, Task.project_type)
            .join(Task, TaskResult.task_id == Task.id)
            .filter(Task.created_at >= since_naive)
            .all()
        )
    results_by_task: dict[str, list[TaskResult]] = defaultdict(list)
    for result, _project_type in result_rows:
        results_by_task[result.task_id].append(result)

    totals = {
        "tasks_total": len(tasks),
        "single_tasks": 0,
        "batch_tasks": 0,
        "units_total": 0,
        "units_completed": 0,
        "units_failed": 0,
        "units_cancelled": 0,
        "units_pending": 0,
        "units_running": 0,
        "task_status_counts": {
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "partial_failed": 0,
            "cancelled": 0,
        },
    }
    qa_counts = {"pass": 0, "warn": 0, "fail": 0, "missing": 0}
    issue_counter: Counter[tuple[str, str]] = Counter()
    task_durations: list[float] = []
    file_durations: list[float] = []
    project_stats: dict[str, dict[str, Any]] = {}

    def project_bucket(project_type: str | None) -> dict[str, Any]:
        key = _project_key(project_type)
        if key not in project_stats:
            project_stats[key] = {
                "project_type": key,
                "tasks": 0,
                "units_total": 0,
                "units_completed": 0,
                "units_failed": 0,
                "qa_warn": 0,
                "qa_fail": 0,
                "_durations": [],
            }
        return project_stats[key]

    for task in tasks:
        totals["single_tasks" if task.task_type != "batch" else "batch_tasks"] += 1
        totals["task_status_counts"][task.status or "pending"] = (
            int(totals["task_status_counts"].get(task.status or "pending") or 0) + 1
        )
        results = results_by_task.get(task.id, [])
        unit_counts = _task_unit_counts(task, results)
        bucket = project_bucket(task.project_type)
        bucket["tasks"] += 1
        for key in ("total", "completed", "failed", "cancelled", "pending", "running"):
            totals[f"units_{key}"] += unit_counts[key]
        bucket["units_total"] += unit_counts["total"]
        bucket["units_completed"] += unit_counts["completed"]
        bucket["units_failed"] += unit_counts["failed"]

        if isinstance(task.duration_seconds, (int, float)):
            task_durations.append(float(task.duration_seconds))
            bucket["_durations"].append(float(task.duration_seconds))

        _count_issues(issue_counter, "error", _json_list(task.errors))
        _count_issues(issue_counter, "warning", _json_list(task.warnings))

        if task.task_type == "batch":
            for result in results:
                if isinstance(result.duration_seconds, (int, float)):
                    file_durations.append(float(result.duration_seconds))
                _count_issues(issue_counter, "error", _json_list(result.errors))
                _count_issues(issue_counter, "warning", _json_list(result.warnings))
                if result.status == "completed":
                    qa_payload = _qa_payload_from_output(result.output_path)
                    qa_status = str(qa_payload.get("status") or "").upper() or None
                    _count_qa_reasons(issue_counter, qa_payload)
                    if qa_status == "PASS":
                        qa_counts["pass"] += 1
                    elif qa_status == "WARN":
                        qa_counts["warn"] += 1
                        bucket["qa_warn"] += 1
                    elif qa_status == "FAIL":
                        qa_counts["fail"] += 1
                        bucket["qa_fail"] += 1
                    else:
                        qa_counts["missing"] += 1
        elif task.status == "completed":
            qa_payload = _qa_payload_from_output(task.output_path)
            qa_status = str(qa_payload.get("status") or "").upper() or None
            _count_qa_reasons(issue_counter, qa_payload)
            if qa_status == "PASS":
                qa_counts["pass"] += 1
            elif qa_status == "WARN":
                qa_counts["warn"] += 1
                bucket["qa_warn"] += 1
            elif qa_status == "FAIL":
                qa_counts["fail"] += 1
                bucket["qa_fail"] += 1
            else:
                qa_counts["missing"] += 1

    terminal_units = (
        totals["units_completed"] + totals["units_failed"] + totals["units_cancelled"]
    )
    totals["completion_rate"] = _rate(terminal_units, totals["units_total"])
    totals["success_rate"] = _rate(totals["units_completed"], totals["units_total"])

    project_breakdown = []
    for bucket in project_stats.values():
        durations = bucket.pop("_durations")
        bucket["success_rate"] = _rate(bucket["units_completed"], bucket["units_total"])
        bucket["avg_task_seconds"] = round(mean(durations), 3) if durations else None
        project_breakdown.append(bucket)
    project_breakdown.sort(key=lambda item: item["units_total"], reverse=True)

    recent_batches = []
    for task in [task for task in tasks if task.task_type == "batch"][:recent_batch_limit]:
        unit_counts = _task_unit_counts(task, results_by_task.get(task.id, []))
        recent_batches.append(
            {
                "task_id": task.id,
                "status": task.status,
                "project_type": task.project_type,
                "created_at": _iso(task.created_at),
                "completed_at": _iso(task.completed_at),
                "duration_seconds": task.duration_seconds,
                "total_files": unit_counts["total"],
                "completed_files": unit_counts["completed"],
                "failed_files": unit_counts["failed"],
                "cancelled_files": unit_counts["cancelled"],
                "pending_files": unit_counts["pending"],
                "running_files": unit_counts["running"],
            }
        )

    failure_reasons = [
        {"severity": severity, "reason": reason, "count": count}
        for (severity, reason), count in issue_counter.most_common(12)
    ]
    downloads = _download_diagnostics(
        runtime_dir / "logs" / "uvicorn.log",
        event_limit=20,
        tail_line_count=10000,
        since=since_aware,
    )
    data = {
        "schema_version": "1.0",
        "generated_at": _now_iso(),
        "window_hours": window_hours,
        "since": since_aware.isoformat(),
        "totals": totals,
        "qa": qa_counts,
        "durations": {
            "avg_task_seconds": round(mean(task_durations), 3) if task_durations else None,
            "p95_task_seconds": _percentile(task_durations, 95),
            "avg_file_seconds": round(mean(file_durations), 3) if file_durations else None,
            "p95_file_seconds": _percentile(file_durations, 95),
        },
        "downloads": downloads,
        "failure_reasons": failure_reasons,
        "project_breakdown": project_breakdown,
        "recent_batches": recent_batches,
    }
    data["gate"] = _load_test_gate(data)
    return data


def _hours_since(value: str | None) -> float | None:
    parsed = _parse_datetime(value)
    if not parsed:
        return None
    return (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600


def _alert(
    alert_id: str,
    severity: str,
    label: str,
    title: str,
    message: str,
    *,
    threshold: str | None = None,
) -> dict[str, str | None]:
    return {
        "id": alert_id,
        "severity": severity,
        "label": label,
        "title": title,
        "message": message,
        "threshold": threshold,
    }


def _ops_alerts(snapshot: dict[str, Any]) -> list[dict[str, str | None]]:
    alerts: list[dict[str, str | None]] = []
    runtime = snapshot["runtime"]
    watchdog = runtime["watchdog"]
    queue = runtime["generation_queue"]
    disk = snapshot["storage"]["disk"]
    downloads = snapshot["downloads"]["summary"]
    task_counts = snapshot["tasks"]["counts"]
    latest_backup = snapshot["backups"]["latest"]

    for key, label in (("web", "Web 服务"), ("tunnel", "公网隧道")):
        current = watchdog[key]["status"]
        if current == "fail":
            alerts.append(
                _alert(
                    f"watchdog.{key}.fail",
                    "danger",
                    label,
                    f"{label}异常",
                    "Watchdog 最近一次检查失败，需要确认服务或隧道是否可访问。",
                    threshold="status=fail",
                )
            )
        elif current == "warn":
            alerts.append(
                _alert(
                    f"watchdog.{key}.warn",
                    "warning",
                    label,
                    f"{label}需要关注",
                    "Watchdog 最近一次检查返回警告，建议观察下一轮检查结果。",
                    threshold="status=warn",
                )
            )

    libreoffice_running = runtime["libreoffice_listener"]["running"]
    libreoffice_status = watchdog["libreoffice"]["status"]
    if libreoffice_running is False or libreoffice_status in {"fail", "missing"}:
        alerts.append(
            _alert(
                "libreoffice.listener.missing",
                "warning",
                "LibreOffice",
                "LibreOffice listener 未就绪",
                "报告刷新目录、页码和域时可能变慢；可由 watchdog 或重启应用恢复。",
                threshold="listener running",
            )
        )

    used_percent = disk.get("used_percent")
    if isinstance(used_percent, (int, float)):
        if used_percent >= DISK_DANGER_PERCENT:
            alerts.append(
                _alert(
                    "disk.critical",
                    "danger",
                    "磁盘",
                    "磁盘空间紧张",
                    f"当前使用率 {used_percent:.1f}%，报告生成和 ZIP 打包可能失败。",
                    threshold=f">= {DISK_DANGER_PERCENT}%",
                )
            )
        elif used_percent >= DISK_WARNING_PERCENT:
            alerts.append(
                _alert(
                    "disk.warning",
                    "warning",
                    "磁盘",
                    "磁盘空间偏高",
                    f"当前使用率 {used_percent:.1f}%，建议尽快检查保留和清理策略。",
                    threshold=f">= {DISK_WARNING_PERCENT}%",
                )
            )

    queued = int(queue.get("queued") or 0)
    max_workers = max(1, int(queue.get("max_workers") or 1))
    if queued >= max_workers:
        alerts.append(
            _alert(
                "queue.backlog.high",
                "danger",
                "队列",
                "生成队列堆积",
                f"当前排队 {queued} 个，已达到执行槽数量 {max_workers}，报告组会感知等待。",
                threshold="queued >= max_workers",
            )
        )
    elif queued > 0:
        alerts.append(
            _alert(
                "queue.backlog",
                "warning",
                "队列",
                "有任务正在排队",
                f"当前排队 {queued} 个，继续观察是否持续堆积。",
                threshold="queued > 0",
            )
        )

    failed_total = int(task_counts.get("failed_total") or 0)
    if failed_total > 0:
        alerts.append(
            _alert(
                "tasks.failed",
                "warning",
                "任务",
                "存在失败或部分失败任务",
                f"累计失败/部分失败 {failed_total} 个，请在任务队列中复核。",
                threshold="failed_total > 0",
            )
        )

    failed_downloads = int(downloads.get("failed") or 0)
    slow_downloads = int(downloads.get("slow") or 0)
    max_duration_ms = downloads.get("max_duration_ms")
    if failed_downloads > 0:
        alerts.append(
            _alert(
                "downloads.failed",
                "danger",
                "下载",
                "存在失败下载",
                f"最近终态下载中失败 {failed_downloads} 次，需要优先确认网络或文件发送链路。",
                threshold="failed > 0",
            )
        )
    if slow_downloads > 0:
        alerts.append(
            _alert(
                "downloads.slow",
                "warning",
                "下载",
                "存在慢下载",
                f"最近终态下载中慢下载 {slow_downloads} 次，建议结合任务详情确认 ZIP 大小和耗时。",
                threshold="slow > 0",
            )
        )
    if isinstance(max_duration_ms, (int, float)) and max_duration_ms >= DOWNLOAD_SLOW_WARNING_MS:
        alerts.append(
            _alert(
                "downloads.duration.high",
                "warning",
                "下载",
                "最大下载耗时偏高",
                f"最近最大下载耗时 {max_duration_ms / 1000:.1f} 秒。",
                threshold=f">= {DOWNLOAD_SLOW_WARNING_MS / 1000:.0f}s",
            )
        )

    if not latest_backup:
        alerts.append(
            _alert(
                "backup.missing",
                "danger",
                "备份",
                "没有可用备份",
                "生产数据没有最近备份记录，请立即运行维护脚本。",
                threshold="latest backup exists",
            )
        )
    else:
        backup_age = _hours_since(latest_backup.get("modified_at"))
        if backup_age is None or backup_age > BACKUP_DANGER_HOURS:
            alerts.append(
                _alert(
                    "backup.stale",
                    "danger",
                    "备份",
                    "最近备份过期",
                    "最近备份超过 48 小时或时间无法解析，请检查维护任务。",
                    threshold=f"> {BACKUP_DANGER_HOURS}h",
                )
            )
        elif backup_age > BACKUP_WARNING_HOURS:
            alerts.append(
                _alert(
                    "backup.warning",
                    "warning",
                    "备份",
                    "最近备份偏旧",
                    f"最近备份约 {backup_age:.1f} 小时前完成。",
                    threshold=f"> {BACKUP_WARNING_HOURS}h",
                )
            )

    if not runtime["maintenance"]["last_cleanup_at"]:
        alerts.append(
            _alert(
                "maintenance.cleanup.missing",
                "warning",
                "维护",
                "未记录清理完成时间",
                "无法确认旧预览、日志和 release 是否已定期清理。",
                threshold="cleanup complete",
            )
        )

    return alerts


@router.get("/status", response_model=ApiResponse[dict])
def ops_status(
    recent_task_limit: int = Query(10, ge=0, le=50),
    download_event_limit: int = Query(20, ge=0, le=100),
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """Return a sanitized, read-only operational snapshot."""
    runtime_dir = _runtime_dir()
    log_dir = runtime_dir / "logs"
    storage_root = settings.storage_root
    data = {
        "schema_version": "1.1",
        "generated_at": _now_iso(),
        "deployment": _read_current_release(runtime_dir),
        "runtime": {
            "runtime_dir_present": runtime_dir.exists(),
            "instance_lock": runtime_instance_lock_status(),
            "libreoffice_listener": _libreoffice_listener_status(),
            "generation_queue": queue_stats(),
            "generation_limits": {
                "process_isolation": bool(settings.generation_process_isolation),
                "timeout_seconds": int(settings.generation_process_timeout_seconds),
            },
            "task_recovery": last_recovery_summary(),
            "watchdog": _watchdog_status(log_dir / "watchdog.log"),
            "maintenance": _maintenance_status(log_dir / "maintenance.log"),
        },
        "storage": {
            "disk": _disk_usage(storage_root),
            "buckets": {
                "uploads": _bucket_summary(settings.upload_dir),
                "reports": _bucket_summary(settings.report_dir),
                "previews": _bucket_summary(settings.preview_dir),
                "signatures": _bucket_summary(settings.signature_dir),
                "reference_reports": _bucket_summary(settings.reference_report_dir),
            },
        },
        "tasks": {
            "counts": _task_counts(db),
            "recent": _recent_tasks(db, limit=recent_task_limit),
        },
        "downloads": _download_diagnostics(
            log_dir / "uvicorn.log",
            event_limit=download_event_limit,
        ),
        "retention": _retention_policy(),
        "backups": _backup_status(_backup_dir()),
    }
    data["alerts"] = _ops_alerts(data)
    return ApiResponse(data=data)


@router.get("/load-test-summary", response_model=ApiResponse[dict])
def load_test_summary(
    window_hours: int = Query(168, ge=1, le=720),
    recent_batch_limit: int = Query(12, ge=0, le=50),
    db: Session = Depends(get_db),
) -> ApiResponse[dict]:
    """Return a sanitized production pressure-test dashboard payload."""
    return ApiResponse(
        data=_load_test_summary(
            db,
            window_hours=window_hours,
            recent_batch_limit=recent_batch_limit,
        )
    )
