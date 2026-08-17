import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.config import settings  # noqa: E402
from app.services.generation_process import (  # noqa: E402
    GenerationProcessError,
    GenerationTimeoutError,
    run_callable_with_timeout,
    run_generate_report_with_timeout,
)


def _return_payload(value):
    return {"value": value}


def _return_large_payload(size):
    return {"blob": b"x" * size}


def _sleep_payload(seconds):
    time.sleep(seconds)
    return {"done": True}


def _raise_payload():
    raise RuntimeError("synthetic child failure")


class DirectBridge:
    def __init__(self):
        self.called = False

    def generate_report(self, **kwargs):
        self.called = True
        return {"success": True, "kwargs": kwargs}


def test_run_callable_with_timeout_returns_child_payload():
    result = run_callable_with_timeout(
        _return_payload,
        args=("ok",),
        timeout_seconds=15,
    )

    assert result == {"value": "ok"}


def test_run_callable_with_timeout_drains_large_child_payload_before_join():
    result = run_callable_with_timeout(
        _return_large_payload,
        args=(4_000_000,),
        timeout_seconds=15,
    )

    assert len(result["blob"]) == 4_000_000


def test_run_callable_with_timeout_raises_on_child_error():
    with pytest.raises(GenerationProcessError) as exc:
        run_callable_with_timeout(_raise_payload, timeout_seconds=15)

    assert "RuntimeError" in str(exc.value)
    assert "synthetic child failure" in str(exc.value)


def test_run_callable_with_timeout_terminates_slow_child_quickly():
    started = time.monotonic()

    with pytest.raises(GenerationTimeoutError) as exc:
        run_callable_with_timeout(
            _sleep_payload,
            args=(5,),
            timeout_seconds=0.2,
            grace_seconds=0.1,
        )

    assert "已终止生成子进程" in str(exc.value)
    assert time.monotonic() - started < 3


def test_run_generate_report_with_timeout_keeps_test_bridges_direct(monkeypatch):
    monkeypatch.setattr(settings, "generation_process_isolation", True)
    bridge = DirectBridge()

    result = run_generate_report_with_timeout(
        bridge,
        excel_path="case.xlsx",
        output_dir="out",
    )

    assert bridge.called is True
    assert result["success"] is True
    assert result["kwargs"]["excel_path"] == "case.xlsx"
