"""DOCX -> PDF conversion through the persistent LibreOffice UNO listener.

Cold-starting ``soffice --convert-to pdf`` costs 10-30 s per call on a loaded
host (fresh profile bootstrap + process start). The web backend already keeps
one deterministic-profile LibreOffice listener alive for TOC field refreshes
(``REPORTGEN_LO_LISTENER_PORT``); reusing it for PDF export removes that cold
start from the static-TOC pagination probe (2+ conversions per report) and
from visual QA rendering.

Layout parity: the listener profile is seeded by the same
``initialize_libreoffice_profile`` used for the disposable per-call profiles,
so pagination is produced by the same engine + font substitution set. Callers
must still perform their own input staging (field freeze / font
stabilization) before handing the file over.

Fail-open contract: :func:`convert_docx_to_pdf_via_listener` returns ``False``
whenever the listener path is unavailable or fails, so callers keep their
existing cold-start conversion as the authoritative fallback. Set
``REPORTGEN_PDF_VIA_LISTENER=0`` to disable this path entirely.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Optional

from reportgen.utils.process_lock import exclusive_file_lock

_UNO_EXPORT_SCRIPT = textwrap.dedent(
    """
    import sys
    import time
    import uno
    from com.sun.star.beans import PropertyValue

    def prop(name, value):
        item = PropertyValue()
        item.Name = name
        item.Value = value
        return item

    input_path, output_path, port = sys.argv[1], sys.argv[2], sys.argv[3]
    local_ctx = uno.getComponentContext()
    resolver = local_ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver",
        local_ctx,
    )

    ctx = None
    last_error = None
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            ctx = resolver.resolve(
                f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext"
            )
            break
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)

    if ctx is None:
        raise RuntimeError(f"UNO connection failed: {last_error}")

    desktop = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop",
        ctx,
    )
    # Mirror the headless ``--convert-to pdf`` load as closely as possible:
    # no UpdateDocMode override, hidden frame, read-only source document.
    load_props = (
        prop("Hidden", True),
        prop("ReadOnly", True),
    )
    doc = desktop.loadComponentFromURL(
        uno.systemPathToFileUrl(input_path),
        "_blank",
        0,
        load_props,
    )
    try:
        doc.storeToURL(
            uno.systemPathToFileUrl(output_path),
            (prop("FilterName", "writer_pdf_Export"),),
        )
    finally:
        doc.close(False)
    """
).strip()


def _listener_port() -> Optional[int]:
    raw = os.environ.get("REPORTGEN_LO_LISTENER_PORT", "")
    return int(raw) if raw.isdigit() else None


def _listener_pdf_enabled() -> bool:
    raw = str(os.environ.get("REPORTGEN_PDF_VIA_LISTENER", "1")).strip().lower()
    return raw not in {"0", "false", "no", "n", "off"}


def _uno_python() -> Optional[str]:
    for candidate in (Path("/usr/bin/python3"), Path(shutil.which("python3") or "")):
        if not str(candidate) or not candidate.exists():
            continue
        probe = subprocess.run(
            [str(candidate), "-c", "import uno"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if probe.returncode == 0:
            return str(candidate)
    return None


def convert_docx_to_pdf_via_listener(
    input_docx: Path | str,
    output_pdf: Path | str,
    *,
    timeout_seconds: int = 180,
) -> bool:
    """Export ``input_docx`` to ``output_pdf`` through the persistent listener.

    Returns ``True`` when the PDF was produced by the listener path, ``False``
    when the path is unavailable (no listener / no python3-uno / disabled) or
    the conversion failed for any reason. Never raises: callers are expected
    to fall back to their cold-start conversion.
    """
    if not _listener_pdf_enabled():
        return False
    port = _listener_port()
    if port is None:
        return False
    uno_python = _uno_python()
    if uno_python is None:
        return False

    input_path = Path(input_docx)
    output_path = Path(output_pdf)
    if not input_path.exists():
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lock_path = Path(
        os.environ.get("REPORTGEN_LO_LOCK_FILE", "/tmp/reportgen_lo_listener.lock")
    )
    try:
        with (
            exclusive_file_lock(lock_path),
            tempfile.TemporaryDirectory(prefix="reportgen_uno_pdf_") as tmp_dir,
        ):
            script_path = Path(tmp_dir) / "export_pdf_with_uno.py"
            script_path.write_text(_UNO_EXPORT_SCRIPT, encoding="utf-8")
            subprocess.run(
                [
                    uno_python,
                    str(script_path),
                    str(input_path),
                    str(output_path),
                    str(port),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=max(1, int(timeout_seconds)),
            )
    except Exception:
        with contextlib.suppress(Exception):
            output_path.unlink(missing_ok=True)
        return False

    return output_path.exists() and output_path.stat().st_size > 0
