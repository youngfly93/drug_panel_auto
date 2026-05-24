"""
DOCX rendering utilities (DOCX -> PDF -> PNG).

This is used for visual inspection of generated reports or templates.

Dependencies (system):
  - LibreOffice: `soffice`
  - Poppler: `pdftoppm`

Notes:
  - LibreOffice headless on macOS 25.x can crash while bootstrapping a fresh
    temporary profile, which triggers a GUI crash reporter. macOS therefore
    uses the system profile by default; set REPORTGEN_LIBREOFFICE_PROFILE_MODE
    to "isolated" to force per-run profile isolation.
  - The renderer copies input to an isolated ASCII filename.
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
    return "system" if platform.system() == "Darwin" else "isolated"


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
    """Convert the staged DOCX to PDF, falling back for macOS LO crashes."""
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

    convert_cmd = _isolated_profile_convert_cmd(
        soffice=soffice,
        tmp_docx=tmp_docx,
        workdir=workdir,
        profile_dir=profile_dir,
    )
    try:
        _run_checked(
            convert_cmd,
            timeout_seconds=timeout_seconds,
            stage="docx_to_pdf",
        )
    except DocxRenderError as isolated_error:
        # LibreOffice on macOS 25.x can abort while bootstrapping a fresh
        # per-run profile. The system profile path is less isolated, but it
        # keeps visual QA available instead of failing a valid DOCX render.
        fallback_cmd = _system_profile_convert_cmd(
            soffice=soffice,
            tmp_docx=tmp_docx,
            workdir=workdir,
        )
        try:
            _run_checked(
                fallback_cmd,
                timeout_seconds=timeout_seconds,
                stage="docx_to_pdf_fallback",
            )
        except DocxRenderError as fallback_error:
            fallback_error.stderr = (
                (fallback_error.stderr or "")
                + "\n\nIsolated LibreOffice profile stderr:\n"
                + (isolated_error.stderr or "")
            )
            raise fallback_error from isolated_error
        warnings.warn(
            "LibreOffice isolated-profile DOCX render failed; retried with "
            "the system profile.",
            RuntimeWarning,
            stacklevel=2,
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
    with tempfile.TemporaryDirectory(
        prefix="reportgen_render_", dir=str(tmp_root)
    ) as workdir_str:
        workdir = Path(workdir_str)
        profile_dir = workdir / "lo_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        tmp_docx = workdir / "input.docx"
        shutil.copy2(docx_path, tmp_docx)

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

        # PDF -> PNGs
        output_prefix = output_dir / docx_path.stem
        ppm_cmd = [
            pdftoppm,
            "-png",
            "-r",
            str(int(dpi)),
        ]
        if first_page is not None:
            ppm_cmd.extend(["-f", str(int(first_page))])
        if last_page is not None:
            ppm_cmd.extend(["-l", str(int(last_page))])
        ppm_cmd.extend([str(pdf_path), str(output_prefix)])
        _run_checked(
            ppm_cmd,
            timeout_seconds=timeout_seconds,
            stage="pdf_to_png",
        )

        pngs = sorted(output_dir.glob(f"{docx_path.stem}-*.png"))
        if keep_pdf:
            shutil.copy2(pdf_path, output_dir / f"{docx_path.stem}.pdf")
        return pngs
