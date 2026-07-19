"""Persistent LibreOffice listener for fast field refresh.

Starts once at uvicorn startup, reused by all template renders via UNO.
Sets the ``REPORTGEN_LO_LISTENER_PORT`` env var so the renderer skips
its per-call ``subprocess.Popen`` cold start (each cold start is ~5–8 s).

Non-fatal: if the listener fails to start (no soffice, port busy, etc.),
the renderer falls back to spawning a fresh listener per call.
"""
from __future__ import annotations

import contextlib
import logging
import os
import shutil
import socket
import subprocess
import threading
from pathlib import Path
from typing import Optional

from reportgen.utils.libreoffice_profile import initialize_libreoffice_profile
from reportgen.utils.process_lock import exclusive_file_lock

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
        _log.warning(
            "port %d busy; persistent LO listener disabled (will fallback to per-call)",
            port,
        )
        return

    profile_root = profile_root or Path("/tmp/reportgen_lo_persistent_profile")
    profile_root.mkdir(parents=True, exist_ok=True)
    try:
        initialize_libreoffice_profile(profile_root, require_available=True)
    except Exception as exc:
        _log.warning(
            "deterministic LibreOffice profile initialization failed: %s", exc
        )
        return
    _profile_dir = profile_root

    cmd = [
        soffice,
        f"-env:UserInstallation={profile_root.resolve().as_uri()}",
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
    _log.info(
        "LibreOffice persistent listener started on port %d (pid %d)",
        port,
        _listener_proc.pid,
    )


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


@contextlib.contextmanager
def listener_access_lock():
    """Serialize warmup and report refreshes across threads and worker processes."""
    lock_path = Path(
        os.environ.get("REPORTGEN_LO_LOCK_FILE", "/tmp/reportgen_lo_listener.lock")
    )
    with _lock:
        with exclusive_file_lock(lock_path):
            yield


def warmup_async(*, port: int = _DEFAULT_PORT, timeout: float = 60.0) -> None:
    """Spawn a daemon thread that exercises the listener once.

    Without this, the first real report after server start pays a ~28 s warmup
    cost while LO lazy-loads Writer/text/index modules. By touching those
    modules eagerly (load+close a blank Writer doc), the first user request
    arrives to a fully-warm listener.

    Fire-and-forget: the service can start accepting requests immediately;
    if a request races warmup, it just waits as before.
    """
    import time

    def _do_warmup() -> None:
        import shutil
        import subprocess

        soffice_python = "/usr/bin/python3"
        if not Path(soffice_python).exists():
            soffice_python = shutil.which("python3") or ""
        if not soffice_python:
            _log.warning("warmup skipped: no python3 with uno on PATH")
            return

        # Inline UNO script — load a blank Writer doc and close it. That forces
        # the listener to fully initialize Writer module + text/field machinery.
        warmup_code = (
            "import uno\n"
            "from com.sun.star.beans import PropertyValue\n"
            "ctx = uno.getComponentContext()\n"
            "resolver = ctx.ServiceManager.createInstanceWithContext("
            "'com.sun.star.bridge.UnoUrlResolver', ctx)\n"
            f"rctx = resolver.resolve('uno:socket,host=127.0.0.1,port={port};"
            "urp;StarOffice.ComponentContext')\n"
            "desktop = rctx.ServiceManager.createInstanceWithContext("
            "'com.sun.star.frame.Desktop', rctx)\n"
            "def _prop(n,v):\n"
            "    p = PropertyValue(); p.Name=n; p.Value=v; return p\n"
            "doc = desktop.loadComponentFromURL("
            "'private:factory/swriter', '_blank', 0, (_prop('Hidden', True),))\n"
            "try:\n"
            "    doc.refresh()\n"
            "    doc.TextFields.refresh()\n"
            "finally:\n"
            "    doc.close(True)\n"
        )

        # Listener may still be coming up; UNO resolve() in the script will
        # retry naturally via exception (script does not retry, so we retry here)
        start = time.time()
        deadline = start + timeout
        last_err = ""
        with listener_access_lock():
            while time.time() < deadline:
                try:
                    proc = subprocess.run(
                        [soffice_python, "-c", warmup_code],
                        capture_output=True,
                        text=True,
                        timeout=min(30, deadline - time.time() + 1),
                    )
                    if proc.returncode == 0:
                        _log.info(
                            "LibreOffice listener warmup completed in %.1f s",
                            time.time() - start,
                        )
                        return
                    last_err = (proc.stderr or proc.stdout or "").strip().splitlines()
                    last_err = last_err[-1] if last_err else "unknown"
                except subprocess.TimeoutExpired:
                    last_err = "subprocess timeout"
                time.sleep(1)
        _log.warning("LO warmup did not complete in %.0fs: %s", timeout, last_err)

    t = threading.Thread(target=_do_warmup, name="lo-warmup", daemon=True)
    t.start()
