"""File upload and storage management."""

import fcntl
import hashlib
import json
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

ALLOWED_SIGNATURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_PDL1_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_FEEDBACK_EXTENSIONS = {".docx", ".doc", ".pdf", ".txt", ".md"}
UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_PDL1_IMAGE_PIXELS = 40_000_000


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


def save_pdl1_image_upload(
    file: UploadFile,
    *,
    owner_user_id: int,
) -> dict[str, object]:
    """Validate, sanitize and persist one case-specific PD-L1 IHC image.

    Browser filenames and image metadata are deliberately not retained.  The
    image is decoded and re-encoded as PNG so EXIF/embedded metadata cannot be
    copied into a patient report.  A digest-bound sidecar is later used to
    reject forged or moved paths during generation.
    """

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_PDL1_IMAGE_EXTENSIONS:
        raise ValueError("PD-L1图片仅支持 PNG/JPG/JPEG/WEBP 格式")

    image_id = uuid.uuid4().hex
    today = date.today().isoformat()
    dest_dir = settings.pdl1_image_dir / today
    dest_dir.mkdir(parents=True, exist_ok=True)
    raw_path = dest_dir / f".{image_id}.upload"
    dest_path = dest_dir / f"{image_id}.png"
    sidecar_path = dest_path.with_suffix(".json")

    try:
        write_upload_stream(file.file, raw_path)
        try:
            with Image.open(raw_path) as source:
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > MAX_PDL1_IMAGE_PIXELS:
                    raise ValueError("PD-L1图片像素尺寸无效或过大")
                source.load()
                normalized = ImageOps.exif_transpose(source)
                if normalized.mode not in {"RGB", "RGBA"}:
                    normalized = normalized.convert("RGB")
                elif normalized.mode == "RGBA":
                    # Preserve transparent annotations while still stripping
                    # all source metadata during the PNG re-encode.
                    normalized = normalized.copy()
                normalized.save(dest_path, format="PNG", optimize=True)
                width, height = normalized.size
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("PD-L1图片内容损坏或不是有效图片") from exc

        payload = dest_path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        uploaded_at = datetime.now().astimezone().isoformat(timespec="seconds")
        stored_ref = f"{today}/{dest_path.name}"
        metadata: dict[str, object] = {
            "schema_version": "1.0",
            "image_id": image_id,
            # Only an opaque storage-relative receipt leaves the API.  The
            # absolute host path remains an implementation detail.
            "stored_path": stored_ref,
            "owner_user_id": int(owner_user_id),
            "bound_sample_id": "",
            "uploaded_at": uploaded_at,
            "sha256": digest,
            "file_size_bytes": len(payload),
            "width": width,
            "height": height,
        }
        sidecar_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return metadata
    except Exception:
        dest_path.unlink(missing_ok=True)
        sidecar_path.unlink(missing_ok=True)
        raise
    finally:
        raw_path.unlink(missing_ok=True)


def resolve_pdl1_image_metadata(
    stored_path: str,
    *,
    owner_user_id: int,
    sample_id: str,
) -> dict[str, object]:
    """Resolve and bind a digest receipt to one account and one sample."""

    root = settings.pdl1_image_dir.resolve()
    receipt = Path(str(stored_path or "").strip())
    if receipt.is_absolute():
        raise ValueError("PD-L1图片凭据格式无效")
    path = (root / receipt).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("PD-L1图片路径不在受控存储目录内") from exc
    if path.suffix.lower() != ".png" or not path.is_file():
        raise ValueError("PD-L1图片不存在或格式无效")

    sidecar = path.with_suffix(".json")
    if not sidecar.is_file():
        raise ValueError("PD-L1图片缺少上传校验记录")
    normalized_sample_id = str(sample_id or "").strip()
    if not normalized_sample_id:
        raise ValueError("PD-L1图片绑定前缺少样本编号")

    try:
        with sidecar.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                metadata = json.load(handle)
                if not isinstance(metadata, dict):
                    raise ValueError("PD-L1图片上传校验记录格式无效")
                if str(metadata.get("stored_path") or "") != receipt.as_posix():
                    raise ValueError("PD-L1图片凭据与上传校验记录不一致")
                if int(metadata.get("owner_user_id") or -1) != int(owner_user_id):
                    raise ValueError("PD-L1图片不属于当前账号")

                bound_sample_id = str(metadata.get("bound_sample_id") or "").strip()
                if bound_sample_id and bound_sample_id != normalized_sample_id:
                    raise ValueError("PD-L1图片已绑定其他样本，请重新上传")
                actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual_digest != str(metadata.get("sha256") or ""):
                    raise ValueError("PD-L1图片内容校验失败，请重新上传")

                if not bound_sample_id:
                    metadata["bound_sample_id"] = normalized_sample_id
                    handle.seek(0)
                    json.dump(metadata, handle, ensure_ascii=False, indent=2)
                    handle.truncate()
                    handle.flush()
                    os.fsync(handle.fileno())
                resolved_metadata = dict(metadata)
                # This internal-only value is never returned by the upload
                # endpoint.  Generation needs the canonical host path after
                # the opaque receipt has passed owner/sample/digest checks.
                resolved_metadata["resolved_path"] = str(path)
                return resolved_metadata
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except json.JSONDecodeError as exc:
        raise ValueError("PD-L1图片上传校验记录损坏") from exc
    except OSError as exc:
        raise ValueError("PD-L1图片上传校验记录无法读取") from exc


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
