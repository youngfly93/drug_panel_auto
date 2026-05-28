"""Persistent LibreOffice listener for fast field refresh.

Starts once at uvicorn startup, reused by all template renders via UNO.
Sets the ``REPORTGEN_LO_LISTENER_PORT`` env var so the renderer skips
its per-call ``subprocess.Popen`` cold start (each cold start is ~5–8 s).

Non-fatal: if the listener fails to start (no soffice, port busy, etc.),
the renderer falls back to spawning a fresh listener per call.
"""
from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import threading
from pathlib import Path
from typing import Optional

_log = logging.getLogger("reportgen-web.lo-listener")

_DEFAULT_PORT = 2202
_listener_proc: Optional[subprocess.Popen] = None
_profile_dir: Optional[Path] = None
_lock = threading.Lock()  # serialize UNO calls from this Python process


def _port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
    except OSError:
        return False
    else:
        return True
    finally:
        s.close()


def start_listener(
    *,
    port: int = _DEFAULT_PORT,
    profile_root: Optional[Path] = None,
) -> None:
    """Start a persistent LibreOffice listener (idempotent, non-fatal on failure)."""
    global _listener_proc, _profile_dir

    if _listener_proc is not None and _listener_proc.poll() is None:
        return  # already running

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        _log.warning("soffice not found on PATH; persistent LO listener disabled")
        return

    if not _port_free(port):
        _log.warning("port %d busy; persistent LO listener disabled (will fallback to per-call)", port)
        return

    profile_root = profile_root or Path("/tmp/reportgen_lo_persistent_profile")
    profile_root.mkdir(parents=True, exist_ok=True)
    _profile_dir = profile_root

    cmd = [
        soffice,
        f"-env:UserInstallation=file://{profile_root.as_posix()}",
        "--headless",
        "--nologo",
        "--nolockcheck",
        "--nodefault",
        "--norestore",
        f"--accept=socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext",
    ]
    try:
        _listener_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        _log.warning("failed to start LO listener: %s", exc)
        return

    os.environ["REPORTGEN_LO_LISTENER_PORT"] = str(port)
    _log.info("LibreOffice persistent listener started on port %d (pid %d)", port, _listener_proc.pid)


def stop_listener() -> None:
    """Terminate the persistent LO listener if running."""
    global _listener_proc
    if _listener_proc is None:
        return
    try:
        _listener_proc.terminate()
        try:
            _listener_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _listener_proc.kill()
            _listener_proc.wait(timeout=5)
    except Exception as exc:
        _log.warning("error stopping LO listener: %s", exc)
    finally:
        _listener_proc = None
        os.environ.pop("REPORTGEN_LO_LISTENER_PORT", None)
        _log.info("LibreOffice persistent listener stopped")


def is_alive() -> bool:
    return _listener_proc is not None and _listener_proc.poll() is None


def get_lock() -> threading.Lock:
    """Module-level lock to serialize concurrent UNO calls against the shared listener."""
    return _lock
