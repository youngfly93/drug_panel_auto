"""
DOCX rendering utilities (DOCX -> PDF -> PNG).

This is used for visual inspection of generated reports or templates.

Dependencies (system):
  - LibreOffice: `soffice`
  - Poppler: `pdftoppm`

Notes:
  - LibreOffice headless on macOS can be sensitive to non-ASCII paths for its
    profile directory; we always use the system temp directory.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional


def _which_or_raise(name: str, *, hint: str) -> str:
    path = shutil.which(name)
    if not path:
        raise FileNotFoundError(f"Missing required command '{name}'. {hint}")
    return path


def _file_uri(path: Path) -> str:
    # LibreOffice expects file:///absolute/path style URIs.
    return f"file://{path.resolve().as_posix()}"


def render_docx_to_pngs(
    docx_path: Path,
    *,
    output_dir: Path,
    dpi: int = 150,
    keep_pdf: bool = False,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None,
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

    with tempfile.TemporaryDirectory(prefix=f"render_{docx_path.stem}_") as workdir_str:
        workdir = Path(workdir_str)
        profile_dir = workdir / "lo_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        # DOCX -> PDF
        convert_cmd = [
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
            str(docx_path),
        ]
        subprocess.run(
            convert_cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        pdf_path = workdir / f"{docx_path.stem}.pdf"
        if not pdf_path.exists():
            # LibreOffice may sanitize the name; pick the newest PDF in workdir.
            pdfs = sorted(
                workdir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True
            )
            if not pdfs:
                raise RuntimeError(
                    "LibreOffice conversion did not produce a PDF output."
                )
            pdf_path = pdfs[0]

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
        subprocess.run(
            ppm_cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        pngs = sorted(output_dir.glob(f"{docx_path.stem}-*.png"))
        if keep_pdf:
            shutil.copy2(pdf_path, output_dir / f"{docx_path.stem}.pdf")
        return pngs
