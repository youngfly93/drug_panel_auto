import io
from pathlib import Path

import pytest
from fastapi import UploadFile
from PIL import Image

from app.config import settings
from app.services.file_manager import (
    UploadLimitExceeded,
    get_upload_path,
    resolve_pdl1_image_metadata,
    safe_client_filename,
    save_pdl1_image_upload,
    save_upload_with_digest,
)


def _upload(filename: str, content: bytes = b"synthetic") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


@pytest.mark.parametrize(
    ("untrusted", "expected"),
    [
        ("../../../../escaped.xlsx", "escaped.xlsx"),
        (r"..\..\escaped.xlsx", "escaped.xlsx"),
        ("folder/病例.xlsx", "病例.xlsx"),
    ],
)
def test_upload_filename_cannot_escape_uuid_directory(
    tmp_path,
    monkeypatch,
    untrusted,
    expected,
):
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)

    _upload_id, stored_path, size, _digest = save_upload_with_digest(
        _upload(untrusted)
    )

    assert stored_path.name == expected
    assert size == len(b"synthetic")
    assert stored_path.resolve().is_relative_to(settings.upload_dir.resolve())
    assert stored_path.parent.parent.parent == settings.upload_dir
    assert not (tmp_path / "escaped.xlsx").exists()


def test_safe_client_filename_handles_control_and_empty_names():
    assert safe_client_filename("folder/\x00case.xlsx", "upload.xlsx") == "case.xlsx"
    assert safe_client_filename("../..", "upload.xlsx") == "upload.xlsx"


def test_per_file_limit_aborts_and_removes_partial_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)

    with pytest.raises(UploadLimitExceeded) as exc_info:
        save_upload_with_digest(_upload("oversize.xlsx", b"x"))

    assert exc_info.value.status_code == 413
    assert not list(settings.upload_dir.rglob("*.xlsx"))
    assert not list(settings.upload_dir.rglob("*.part"))


def test_get_upload_path_rejects_similar_prefix_outside_storage(tmp_path, monkeypatch):
    storage = tmp_path / "store"
    storage.mkdir()
    monkeypatch.setattr(settings, "storage_root", storage)
    outside = tmp_path / "store-evil" / "case.xlsx"

    with pytest.raises(ValueError, match="Path traversal"):
        get_upload_path(str(outside))

    inside = storage / "uploads" / "case.xlsx"
    assert get_upload_path(str(inside)) == inside.resolve()


def _image_upload(filename: str = "case.jpg") -> UploadFile:
    buffer = io.BytesIO()
    image = Image.new("RGB", (48, 32), color=(235, 225, 210))
    image.save(buffer, format="JPEG", exif=b"Exif\x00\x00SYNTHETIC-METADATA")
    buffer.seek(0)
    return UploadFile(filename=filename, file=buffer)


def test_pdl1_upload_is_sanitized_and_bound_to_owner_and_sample(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")

    receipt = save_pdl1_image_upload(
        _image_upload(),
        owner_user_id=7,
    )
    stored_ref = str(receipt["stored_path"])
    assert not stored_ref.startswith("/")
    stored = settings.pdl1_image_dir / stored_ref
    assert stored.is_file()
    assert b"SYNTHETIC-METADATA" not in stored.read_bytes()

    metadata = resolve_pdl1_image_metadata(
        stored_ref,
        owner_user_id=7,
        sample_id="CASE-LUNG-001",
    )
    assert metadata["bound_sample_id"] == "CASE-LUNG-001"
    assert metadata["width"] == 48
    assert metadata["height"] == 32
    assert Path(str(metadata["resolved_path"])) == stored.resolve()

    with pytest.raises(ValueError, match="当前账号"):
        resolve_pdl1_image_metadata(
            stored_ref,
            owner_user_id=8,
            sample_id="CASE-LUNG-001",
        )
    with pytest.raises(ValueError, match="其他样本"):
        resolve_pdl1_image_metadata(
            stored_ref,
            owner_user_id=7,
            sample_id="CASE-LUNG-002",
        )


def test_pdl1_upload_rejects_tampering_and_absolute_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
    receipt = save_pdl1_image_upload(
        _image_upload(),
        owner_user_id=7,
    )
    stored_ref = str(receipt["stored_path"])
    stored = settings.pdl1_image_dir / stored_ref
    stored.write_bytes(stored.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="内容校验失败"):
        resolve_pdl1_image_metadata(
            stored_ref,
            owner_user_id=7,
            sample_id="CASE-LUNG-001",
        )
    with pytest.raises(ValueError, match="凭据格式无效"):
        resolve_pdl1_image_metadata(
            str(stored.resolve()),
            owner_user_id=7,
            sample_id="CASE-LUNG-001",
        )
