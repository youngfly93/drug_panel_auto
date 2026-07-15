"""File upload and storage management."""

import json
import re
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import UploadFile

from app.config import settings

ALLOWED_SIGNATURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_FEEDBACK_EXTENSIONS = {".docx", ".doc", ".pdf", ".txt", ".md"}


def save_upload(file: UploadFile) -> tuple[str, Path, int]:
    """
    Save an uploaded file to storage.

    Returns: (upload_id, stored_path, file_size_bytes)
    """
    upload_id = str(uuid.uuid4())
    today = date.today().isoformat()
    dest_dir = settings.upload_dir / today / upload_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / (file.filename or "upload.xlsx")

    # Stream to disk
    size = 0
    with open(dest_path, "wb") as f:
        while chunk := file.file.read(8192):
            size += len(chunk)
            f.write(chunk)

    return upload_id, dest_path, size


def get_upload_path(stored_path: str) -> Path:
    """Resolve and validate a stored file path."""
    p = Path(stored_path)
    # Security: ensure path is under storage
    resolved = p.resolve()
    storage_resolved = settings.storage_root.resolve()
    if not str(resolved).startswith(str(storage_resolved)):
        raise ValueError("Path traversal detected")
    return p


def ensure_report_dir(task_id: str) -> Path:
    """Create and return the output directory for a task."""
    out = settings.report_dir / task_id
    out.mkdir(parents=True, exist_ok=True)
    return out


def save_signature_upload(file: UploadFile) -> tuple[Path, int]:
    """
    Save an uploaded signature image under storage/signatures.

    Returns: (stored_path, file_size_bytes)
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SIGNATURE_EXTENSIONS:
        raise ValueError(
            "签名图片仅支持 PNG/JPG/JPEG/WEBP 格式"
        )

    today = date.today().isoformat()
    dest_dir = settings.signature_dir / today
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / f"{uuid.uuid4()}{suffix}"

    size = 0
    with open(dest_path, "wb") as f:
        while chunk := file.file.read(8192):
            size += len(chunk)
            f.write(chunk)

    return dest_path, size


def _safe_dir_id(value: str) -> str:
    """Strict alnum/_/- for use as a directory name (sample ids are alnum)."""
    return re.sub(r"[^0-9A-Za-z_\-]", "", (value or "").strip())


def _safe_component(value: str) -> str:
    """Keep unicode but strip path separators / control chars / dotdot."""
    cleaned = re.sub(r"[/\\\x00-\x1f]", "", (value or "").strip())
    return cleaned.replace("..", "")


def save_feedback_upload(
    file: UploadFile,
    sample_id: str,
    *,
    note: str = "",
    task_id: str = "",
) -> tuple[Path, int]:
    """
    Save a report-group feedback document under storage/feedback/<sample_id>/.

    Also writes a ``<file>.meta.json`` sidecar for later triage.

    Returns: (stored_path, file_size_bytes)
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_FEEDBACK_EXTENSIONS:
        raise ValueError("反馈文件仅支持 DOCX/DOC/PDF/TXT/MD 格式")

    safe_id = _safe_dir_id(sample_id) or "unsorted"
    dest_dir = settings.feedback_dir / safe_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = _safe_component(Path(file.filename or "feedback").stem) or "feedback"
    dest_path = dest_dir / f"{stem}_{stamp}{suffix}"

    size = 0
    with open(dest_path, "wb") as f:
        while chunk := file.file.read(8192):
            size += len(chunk)
            f.write(chunk)

    meta = {
        "original_filename": file.filename,
        "stored_filename": dest_path.name,
        "sample_id": sample_id,
        "task_id": task_id,
        "note": note,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "size_bytes": size,
        "status": "new",
    }
    meta_path = dest_path.with_name(dest_path.name + ".meta.json")
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return dest_path, size
