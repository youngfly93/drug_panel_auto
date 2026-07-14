"""Single-process guard for the SQLite-backed in-process generation queue."""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

from app.config import settings


class RuntimeInstanceLock:
    """Hold an advisory lock for the lifetime of one application process."""

    def __init__(self, path: Path):
        self.path = path
        self._handle: IO[str] | None = None

    @property
    def acquired(self) -> bool:
        return self._handle is not None

    def acquire(self) -> "RuntimeInstanceLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)
        self.path.chmod(0o600)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            owner = handle.read().strip() or "owner metadata unavailable"
            handle.close()
            raise RuntimeError(
                f"Another ReportGen Web process owns {self.path}: {owner}"
            ) from exc

        payload = {
            "pid": os.getpid(),
            "cwd": str(Path.cwd().resolve()),
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        }
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.flush()
        os.fsync(handle.fileno())
        self._handle = handle
        return self

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


_active_lock: RuntimeInstanceLock | None = None


def runtime_lock_path() -> Path:
    runtime_dir = os.environ.get("RG_WEB_RUNTIME_DIR", "").strip()
    if runtime_dir:
        return Path(runtime_dir) / "run" / "reportgen-web.instance.lock"
    return settings.storage_root / "run" / "reportgen-web.instance.lock"


def acquire_runtime_instance_lock() -> RuntimeInstanceLock | None:
    global _active_lock
    if not settings.runtime_instance_lock_enabled:
        return None
    lock = RuntimeInstanceLock(runtime_lock_path()).acquire()
    _active_lock = lock
    return lock


def release_runtime_instance_lock(lock: RuntimeInstanceLock | None) -> None:
    global _active_lock
    if lock is not None:
        lock.release()
    if _active_lock is lock:
        _active_lock = None


def runtime_instance_lock_status() -> dict[str, Any]:
    lock = _active_lock
    return {
        "enabled": bool(settings.runtime_instance_lock_enabled),
        # The operations endpoint is intentionally path-sanitized.  Operators
        # only need the stable lock filename; exposing its absolute runtime
        # directory would leak host topology through a public JSON payload.
        "lock_file": runtime_lock_path().name,
        "acquired": bool(lock and lock.acquired),
        "pid": os.getpid() if lock and lock.acquired else None,
    }
