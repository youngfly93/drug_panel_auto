"""
DOCX rendering utilities (DOCX -> PDF -> PNG).

This is used for visual inspection of generated reports or templates.

Dependencies (system):
  - LibreOffice: `soffice`
  - Poppler: `pdftoppm`

Notes:
  - Every isolated profile is pre-seeded with ReportGen's deterministic CJK
    font substitutions before LibreOffice starts. This prevents a missing
    Word font from changing fallback families and pagination between runs.
  - The renderer copies input to an isolated ASCII filename.
  - The LibreOffice user profile stays on the host temporary filesystem even
    when report artifacts live on an external volume; macOS LibreOffice can
    abort while bootstrapping a profile directly on removable storage.
  - Set REPORTGEN_RENDER_TMPDIR, or pass tmp_dir, when the system temp volume is
    small or unreliable.
"""

from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import tempfile
import warnings
from pathlib import Path
from typing import List, Optional, Sequence

from reportgen.utils.libreoffice_profile import (
    font_substitution_fingerprint,
    initialize_libreoffice_profile,
    stabilize_docx_fonts_for_libreoffice_render,
)


class DocxRenderError(RuntimeError):
    """Raised when DOCX visual rendering fails at a known stage."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        command: Sequence[str],
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.command = list(command)
        self.stdout = stdout
        self.stderr = stderr


def _which_or_raise(name: str, *, hint: str) -> str:
    path = shutil.which(name)
    if not path:
        raise FileNotFoundError(f"Missing required command '{name}'. {hint}")
    return path


def _file_uri(path: Path) -> str:
    # LibreOffice expects file:///absolute/path style URIs.
    return f"file://{path.resolve().as_posix()}"


def _render_tmp_root(output_dir: Path, tmp_dir: Optional[Path] = None) -> Path:
    configured: Optional[Path] = None
    if tmp_dir is not None:
        configured = Path(tmp_dir)
    elif os.environ.get("REPORTGEN_RENDER_TMPDIR"):
        configured = Path(os.environ["REPORTGEN_RENDER_TMPDIR"])
    if configured is not None:
        configured.mkdir(parents=True, exist_ok=True)
        return configured
    output_tmp = output_dir.resolve().parent / ".reportgen_render_tmp"
    output_tmp.mkdir(parents=True, exist_ok=True)
    return output_tmp


def _run_checked(
    cmd: Sequence[str],
    *,
    timeout_seconds: int,
    stage: str,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.Popen(
        list(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=max(1, int(timeout_seconds)))
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            proc.kill()
        stdout, stderr = proc.communicate()
        raise DocxRenderError(
            f"DOCX render stage '{stage}' timed out after {timeout_seconds}s.",
            stage=stage,
            command=cmd,
            stdout=stdout or "",
            stderr=stderr or "",
        ) from None
    if proc.returncode != 0:
        raise DocxRenderError(
            f"DOCX render stage '{stage}' failed with exit code {proc.returncode}.",
            stage=stage,
            command=cmd,
            stdout=stdout or "",
            stderr=stderr or "",
        )
    return subprocess.CompletedProcess(list(cmd), proc.returncode, stdout, stderr)


def _libreoffice_profile_mode() -> str:
    """Return LibreOffice profile mode: system or isolated."""
    raw = (
        os.environ.get("REPORTGEN_LIBREOFFICE_PROFILE_MODE")
        or os.environ.get("REPORTGEN_RENDER_PROFILE_MODE")
        or ""
    )
    mode = str(raw).strip().lower()
    if mode in {"system", "isolated"}:
        return mode
    if mode and mode != "auto":
        warnings.warn(
            "Unsupported REPORTGEN_LIBREOFFICE_PROFILE_MODE value "
            f"{raw!r}; using automatic mode.",
            RuntimeWarning,
            stacklevel=2,
        )
    return "isolated"


def _command_version(command: str, *args: str) -> str:
    try:
        process = subprocess.run(
            [command, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return "unavailable"
    lines = (process.stdout or process.stderr).strip().splitlines()
    return lines[0] if lines else "unknown"


def renderer_fingerprint() -> dict[str, object]:
    """Return the actual DOCX visual-render stack used on this host."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    pdftoppm = shutil.which("pdftoppm")
    profile_mode = _libreoffice_profile_mode()
    result: dict[str, object] = {
        "platform": platform.system(),
        "machine": platform.machine(),
        "engine": Path(soffice).name if soffice else "none",
        "engine_version": (
            _command_version(soffice, "--version") if soffice else "unavailable"
        ),
        "profile_mode": profile_mode,
        "pdf_renderer": Path(pdftoppm).name if pdftoppm else "none",
        "pdf_renderer_version": (
            _command_version(pdftoppm, "-v") if pdftoppm else "unavailable"
        ),
    }
    if profile_mode == "isolated":
        result.update(font_substitution_fingerprint(require_available=False))
    else:
        result.update(
            {
                "font_substitution_profile": "unmanaged-system-profile",
                "font_substitution_profile_sha256": "",
                "font_substitutions": {},
            }
        )
    return result


def _isolated_profile_convert_cmd(
    *,
    soffice: str,
    tmp_docx: Path,
    workdir: Path,
    profile_dir: Path,
) -> List[str]:
    return [
        soffice,
        f"-env:UserInstallation={_file_uri(profile_dir)}",
        "--headless",
        "--nologo",
        "--nofirststartwizard",
        "--norestore",
        "--convert-to",
        "pdf",
        "--outdir",
        str(workdir),
        str(tmp_docx),
    ]


def _system_profile_convert_cmd(
    *,
    soffice: str,
    tmp_docx: Path,
    workdir: Path,
) -> List[str]:
    return [
        soffice,
        "--headless",
        "--nologo",
        "--nodefault",
        "--nolockcheck",
        "--nofirststartwizard",
        "--norestore",
        "--convert-to",
        "pdf",
        "--outdir",
        str(workdir),
        str(tmp_docx),
    ]


def _pdf_page_count(pdf_path: Path) -> Optional[int]:
    """Return the PDF page count via pdfinfo, or None when unavailable."""
    import re

    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        return None
    try:
        info = subprocess.run(
            [pdfinfo, str(pdf_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except Exception:
        return None
    match = re.search(r"^Pages:\s+(\d+)", info, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def _pdf_to_png_workers() -> int:
    raw = os.environ.get("REPORTGEN_PDF_TO_PNG_WORKERS", "8")
    try:
        return max(1, int(raw))
    except ValueError:
        return 8


def _find_pdf_output(workdir: Path) -> Path:
    pdf_path = workdir / "input.pdf"
    if not pdf_path.exists():
        # LibreOffice may sanitize the name; pick the newest PDF in workdir.
        pdfs = sorted(
            workdir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if not pdfs:
            raise RuntimeError("LibreOffice conversion did not produce a PDF output.")
        pdf_path = pdfs[0]
    return pdf_path


def _docx_to_pdf(
    *,
    soffice: str,
    tmp_docx: Path,
    workdir: Path,
    profile_dir: Path,
    timeout_seconds: int,
) -> Path:
    """Convert the staged DOCX to PDF with an explicit renderer profile."""
    if _libreoffice_profile_mode() == "system":
        _run_checked(
            _system_profile_convert_cmd(
                soffice=soffice,
                tmp_docx=tmp_docx,
                workdir=workdir,
            ),
            timeout_seconds=timeout_seconds,
            stage="docx_to_pdf_system",
        )
        return _find_pdf_output(workdir)

    # Prefer the persistent UNO listener when the web backend runs one: it is
    # seeded with the same deterministic profile as the disposable per-call
    # profile below, and skips the 10-30 s soffice cold start per render.
    from reportgen.utils.uno_pdf import convert_docx_to_pdf_via_listener

    listener_pdf = workdir / "input.pdf"
    if convert_docx_to_pdf_via_listener(
        tmp_docx,
        listener_pdf,
        timeout_seconds=timeout_seconds,
    ):
        return _find_pdf_output(workdir)

    initialize_libreoffice_profile(profile_dir, require_available=True)
    convert_cmd = _isolated_profile_convert_cmd(
        soffice=soffice,
        tmp_docx=tmp_docx,
        workdir=workdir,
        profile_dir=profile_dir,
    )
    _run_checked(
        convert_cmd,
        timeout_seconds=timeout_seconds,
        stage="docx_to_pdf",
    )

    return _find_pdf_output(workdir)


def render_docx_to_pngs(
    docx_path: Path,
    *,
    output_dir: Path,
    dpi: int = 150,
    keep_pdf: bool = False,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None,
    timeout_seconds: int = 120,
    tmp_dir: Optional[Path] = None,
) -> List[Path]:
    """Render a .docx file to page PNGs via LibreOffice + Poppler."""
    docx_path = docx_path.resolve()
    if not docx_path.exists():
        raise FileNotFoundError(f"Input docx not found: {docx_path}")
    if docx_path.suffix.lower() != ".docx":
        raise ValueError(f"Input must be a .docx file: {docx_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    soffice = _which_or_raise(
        "soffice",
        hint=(
            "Install LibreOffice and ensure 'soffice' is on PATH "
            "(macOS: brew install --cask libreoffice)."
        ),
    )
    pdftoppm = _which_or_raise(
        "pdftoppm",
        hint="Install Poppler (macOS: brew install poppler).",
    )

    tmp_root = _render_tmp_root(output_dir, tmp_dir=tmp_dir)
    with (
        tempfile.TemporaryDirectory(
            prefix="reportgen_render_", dir=str(tmp_root)
        ) as workdir_str,
        tempfile.TemporaryDirectory(prefix="reportgen_lo_profile_") as profile_dir_str,
    ):
        workdir = Path(workdir_str)
        profile_dir = Path(profile_dir_str)

        tmp_docx = workdir / "input.docx"
        shutil.copy2(docx_path, tmp_docx)
        # Normalize fonts only in the disposable render copy.  Empty East Asia
        # theme fonts and legacy names such as 幼圆 otherwise resolve to
        # different macOS faces across identical LibreOffice cold starts.
        stabilize_docx_fonts_for_libreoffice_render(
            tmp_docx,
            require_available=False,
        )

        # DOCX -> PDF. LibreOffice is usually more reliable when both profile
        # and input paths are ASCII-only; `_docx_to_pdf` contains a guarded
        # fallback for macOS builds that crash while creating a fresh profile.
        pdf_path = _docx_to_pdf(
            soffice=soffice,
            tmp_docx=tmp_docx,
            workdir=workdir,
            profile_dir=profile_dir,
            timeout_seconds=timeout_seconds,
        )

        # PDF -> PNGs. Rasterization is CPU-bound and page-independent, and
        # pdftoppm pads page numbers by the document total either way, so an
        # all-pages render is chunked into contiguous ranges across workers
        # (85 pages at 120 dpi: ~50 s serial vs ~7 s with 8 workers).
        output_prefix = output_dir / docx_path.stem

        def _ppm_cmd(range_first: Optional[int], range_last: Optional[int]) -> List[str]:
            cmd = [pdftoppm, "-png", "-r", str(int(dpi))]
            if range_first is not None:
                cmd.extend(["-f", str(int(range_first))])
            if range_last is not None:
                cmd.extend(["-l", str(int(range_last))])
            cmd.extend([str(pdf_path), str(output_prefix)])
            return cmd

        total_pages = (
            _pdf_page_count(pdf_path)
            if first_page is None and last_page is None
            else None
        )
        workers = _pdf_to_png_workers()
        if total_pages and total_pages > workers > 1:
            from concurrent.futures import ThreadPoolExecutor

            chunk = -(-total_pages // workers)
            ranges = [
                (start, min(start + chunk - 1, total_pages))
                for start in range(1, total_pages + 1, chunk)
            ]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(
                        _run_checked,
                        _ppm_cmd(range_start, range_end),
                        timeout_seconds=timeout_seconds,
                        stage=f"pdf_to_png_{range_start}_{range_end}",
                    )
                    for range_start, range_end in ranges
                ]
                for future in futures:
                    future.result()
        else:
            _run_checked(
                _ppm_cmd(first_page, last_page),
                timeout_seconds=timeout_seconds,
                stage="pdf_to_png",
            )

        pngs = sorted(output_dir.glob(f"{docx_path.stem}-*.png"))
        if keep_pdf:
            shutil.copy2(pdf_path, output_dir / f"{docx_path.stem}.pdf")
        return pngs
