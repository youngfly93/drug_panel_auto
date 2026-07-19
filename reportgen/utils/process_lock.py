"""Small cross-process lock used by the shared LibreOffice listener."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Iterator


@contextlib.contextmanager
def exclusive_file_lock(path: str | Path) -> Iterator[None]:
    """Hold an advisory exclusive lock for the lifetime of the context."""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        try:
            import fcntl
        except ImportError:  # pragma: no cover - production renderer is Linux
            yield
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
