"""Read-only production diagnostics endpoints.

The payload is intentionally sanitized: no Excel filenames, report paths,
patient fields, task errors, or free-form warnings are returned.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.task import Task
from app.schemas.common import ApiResponse
from app.services.generation_queue import queue_stats
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
    by_status = {
        "pending": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "partial_failed": 0,
        "cancelled": 0,
    }
    for status, count in rows:
        by_status[str(status or "unknown")] = int(count)
    total = sum(by_status.values())
    return {
        "total": total,
        "by_status": by_status,
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
