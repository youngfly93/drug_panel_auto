"""File upload and storage management."""

import hashlib
import json
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, UploadFile, status

from app.config import settings

ALLOWED_SIGNATURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_FEEDBACK_EXTENSIONS = {".docx", ".doc", ".pdf", ".txt", ".md"}
UPLOAD_CHUNK_SIZE = 1024 * 1024


class UploadLimitExceeded(HTTPException):
    """HTTP 413 raised while streaming an upload beyond its configured limit."""

    def __init__(self, *, max_bytes: int, scope: str = "单个文件") -> None:
        max_mb = max_bytes / 1024 / 1024
        super().__init__(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"{scope}超过允许大小（上限 {max_mb:g} MB）",
        )


def max_upload_bytes() -> int:
    """Return the configured per-file limit in bytes."""
    return max(0, int(settings.max_upload_size_mb * 1024 * 1024))


def max_batch_upload_bytes() -> int:
    """Return the configured aggregate batch limit in bytes."""
    return max(0, int(settings.max_batch_upload_size_mb * 1024 * 1024))


def safe_client_filename(filename: str | None, default: str) -> str:
    """Reduce an untrusted browser filename to one local path component."""
    value = str(filename or "").replace("\\", "/")
    name = value.rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    if name in {"", ".", ".."}:
        name = default
    return name


def write_upload_stream(
    fileobj: BinaryIO,
    dest_path: Path,
    *,
    max_bytes: int | None = None,
    scope: str = "单个文件",
) -> tuple[int, str]:
    """Atomically stream one upload with a hard byte limit and SHA-256."""
    limit = max_upload_bytes() if max_bytes is None else max(0, int(max_bytes))
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest_path.with_name(f".{dest_path.name}.{uuid.uuid4().hex}.part")
    digest = hashlib.sha256()
    size = 0
    try:
        with part_path.open("xb") as handle:
            while chunk := fileobj.read(UPLOAD_CHUNK_SIZE):
                size += len(chunk)
                if size > limit:
                    raise UploadLimitExceeded(max_bytes=limit, scope=scope)
                digest.update(chunk)
                handle.write(chunk)
        os.replace(part_path, dest_path)
    finally:
        part_path.unlink(missing_ok=True)
    return size, digest.hexdigest()


def _safe_destination(dest_dir: Path, filename: str) -> Path:
    candidate = (dest_dir / filename).resolve()
    try:
        candidate.relative_to(dest_dir.resolve())
    except ValueError as exc:  # defensive: safe_client_filename should already prevent this
        raise ValueError("Path traversal detected") from exc
    return candidate


def _remove_empty_upload_dir(dest_dir: Path) -> None:
    try:
        dest_dir.rmdir()
    except OSError:
        pass


def save_upload_with_digest(file: UploadFile) -> tuple[str, Path, int, str]:
    """Save an upload once while computing its SHA-256 content digest."""
    upload_id = str(uuid.uuid4())
    today = date.today().isoformat()
    dest_dir = settings.upload_dir / today / upload_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = safe_client_filename(file.filename, "upload.xlsx")
    dest_path = _safe_destination(dest_dir, filename)
    try:
        size, digest = write_upload_stream(file.file, dest_path)
    except Exception:
        dest_path.unlink(missing_ok=True)
        _remove_empty_upload_dir(dest_dir)
        raise

    return upload_id, dest_path, size, digest


def save_upload(file: UploadFile) -> tuple[str, Path, int]:
    """
    Save an uploaded file to storage.

    Returns: (upload_id, stored_path, file_size_bytes)
    """
    upload_id, dest_path, size, _digest = save_upload_with_digest(file)
    return upload_id, dest_path, size


def get_upload_path(stored_path: str) -> Path:
    """Resolve and validate a stored file path."""
    p = Path(stored_path)
    # Security: ensure path is under storage
    resolved = p.resolve()
    storage_resolved = settings.storage_root.resolve()
    try:
        resolved.relative_to(storage_resolved)
    except ValueError as exc:
        raise ValueError("Path traversal detected") from exc
    return resolved


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

    try:
        size, _digest = write_upload_stream(file.file, dest_path)
    except Exception:
        dest_path.unlink(missing_ok=True)
        raise

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

    try:
        size, _digest = write_upload_stream(file.file, dest_path)
    except Exception:
        dest_path.unlink(missing_ok=True)
        raise

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
