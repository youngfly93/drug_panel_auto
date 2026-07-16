"""Shared lifecycle vocabulary for file-based batch report tasks."""

from __future__ import annotations

from collections.abc import Mapping

BATCH_QUEUED_STATUSES = frozenset({"queued", "pending"})
BATCH_WORKING_STATUSES = frozenset({"preflight", "generating", "qa", "running"})
BATCH_ACTIVE_STATUSES = BATCH_QUEUED_STATUSES | BATCH_WORKING_STATUSES
BATCH_TERMINAL_STATUSES = frozenset(
    {"completed", "partial_failed", "failed", "cancelled"}
)

BATCH_ITEM_ACTIVE_STATUSES = BATCH_ACTIVE_STATUSES
BATCH_ITEM_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

BATCH_STATUS_KEYS = (
    "queued",
    "preflight",
    "generating",
    "qa",
    "pending",  # legacy compatibility
    "running",  # legacy compatibility
    "completed",
    "failed",
    "cancelled",
)


def empty_batch_status_counts() -> dict[str, int]:
    return {status: 0 for status in BATCH_STATUS_KEYS}


def pending_file_count(counts: Mapping[str, int]) -> int:
    return sum(int(counts.get(status, 0) or 0) for status in BATCH_QUEUED_STATUSES)


def working_file_count(counts: Mapping[str, int]) -> int:
    return sum(int(counts.get(status, 0) or 0) for status in BATCH_WORKING_STATUSES)


def is_batch_active(status: str | None) -> bool:
    return str(status or "") in BATCH_ACTIVE_STATUSES
