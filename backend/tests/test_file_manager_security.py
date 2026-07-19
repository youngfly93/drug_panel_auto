import io

import pytest
from fastapi import UploadFile

from app.config import settings
from app.services.file_manager import (
    UploadLimitExceeded,
    get_upload_path,
    safe_client_filename,
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
