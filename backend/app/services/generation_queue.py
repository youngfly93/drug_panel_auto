"""Shared in-process generation queue for report jobs."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

from app.config import settings

T = TypeVar("T")

_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_executor_workers: int | None = None
_queued = 0
_active = 0
_submitted_total = 0
_finished_total = 0


def _worker_count() -> int:
    return max(1, int(settings.max_workers or 1))


def _get_executor() -> ThreadPoolExecutor:
    global _executor, _executor_workers
    workers = _worker_count()
    with _lock:
        if _executor is None or _executor_workers != workers:
            if _executor is not None:
                _executor.shutdown(wait=False, cancel_futures=False)
            _executor = ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="reportgen-job",
            )
            _executor_workers = workers
        return _executor


def submit_generation_job(func: Callable[..., T], /, *args, **kwargs) -> None:
    """Submit a generation job without blocking the request thread."""
    global _queued, _active, _submitted_total, _finished_total
    executor = _get_executor()
    with _lock:
        _queued += 1
        _submitted_total += 1

    def runner() -> T:
        global _queued, _active, _finished_total
        with _lock:
            _queued = max(0, _queued - 1)
            _active += 1
        try:
            return func(*args, **kwargs)
        finally:
            with _lock:
                _active = max(0, _active - 1)
                _finished_total += 1

    executor.submit(runner)


def queue_stats() -> dict:
    with _lock:
        return {
            "max_workers": _worker_count(),
            "queued": _queued,
            "active": _active,
            "submitted_total": _submitted_total,
            "finished_total": _finished_total,
        }


def shutdown_generation_queue() -> None:
    global _executor, _executor_workers, _queued, _active
    with _lock:
        executor = _executor
        _executor = None
        _executor_workers = None
        _queued = 0
        _active = 0
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=False)
