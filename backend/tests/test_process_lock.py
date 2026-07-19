from __future__ import annotations

import multiprocessing
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.utils.process_lock import exclusive_file_lock


def _hold_lock(lock_path: str, events, name: str, hold_seconds: float) -> None:
    with exclusive_file_lock(lock_path):
        events.put((name, "entered", time.monotonic()))
        time.sleep(hold_seconds)
        events.put((name, "exited", time.monotonic()))


@pytest.mark.skipif(sys.platform == "win32", reason="production file lock is POSIX")
def test_exclusive_file_lock_serializes_processes(tmp_path) -> None:
    context = multiprocessing.get_context("spawn")
    events = context.Queue()
    lock_path = str(tmp_path / "libreoffice.lock")
    first = context.Process(
        target=_hold_lock,
        args=(lock_path, events, "first", 0.3),
    )
    first.start()
    first_entered = events.get(timeout=2)
    assert first_entered[:2] == ("first", "entered")

    second = context.Process(
        target=_hold_lock,
        args=(lock_path, events, "second", 0.0),
    )
    second.start()
    remaining = [events.get(timeout=3) for _ in range(3)]
    first.join(timeout=2)
    second.join(timeout=2)

    event_times = {(name, state): stamp for name, state, stamp in [first_entered, *remaining]}
    assert first.exitcode == 0
    assert second.exitcode == 0
    assert event_times[("second", "entered")] >= event_times[("first", "exited")]
