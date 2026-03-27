"""File upload and storage management."""

import shutil
import uuid
from datetime import date
from pathlib import Path

from fastapi import UploadFile

from app.config import settings


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
