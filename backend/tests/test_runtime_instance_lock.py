from __future__ import annotations

import json

import pytest

from app.services.runtime_instance_lock import RuntimeInstanceLock


def test_runtime_instance_lock_rejects_overlapping_process_owner(tmp_path) -> None:
    path = tmp_path / "reportgen-web.instance.lock"
    first = RuntimeInstanceLock(path).acquire()
    try:
        owner = json.loads(path.read_text(encoding="utf-8"))
        assert owner["pid"] > 0
        assert owner["cwd"]
        assert path.stat().st_mode & 0o777 == 0o600
        with pytest.raises(RuntimeError, match="Another ReportGen Web process owns"):
            RuntimeInstanceLock(path).acquire()
    finally:
        first.release()

    second = RuntimeInstanceLock(path).acquire()
    second.release()
