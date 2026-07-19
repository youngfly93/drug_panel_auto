"""Sanitized operation audit helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import AuditLog

SAFE_DETAIL_KEYS = {
    "download_kind",
    "duration_seconds",
    "file_index",
    "file_size_bytes",
    "file_size_mb",
    "gate_blockers",
    "gate_status",
    "include_cancelled",
    "include_failed",
    "item_count",
    "operator",
    "override_gate",
    "project_type",
    "qa_filter",
    "qa_visual_render",
    "result",
    "review_status",
    "review_status_label",
    "retry_files",
    "source",
    "status",
    "strict_mode",
    "task_status",
    "task_type",
    "template_contract_mode",
    "template_name",
    "total_files",
}


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:160]
    return str(value)[:160]


def sanitize_details(details: dict[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {}
    return {
        key: _safe_value(value)
        for key, value in details.items()
        if key in SAFE_DETAIL_KEYS
    }


def request_operator(request: Request | None) -> str:
    """Resolve the immutable actor established by JWT authentication."""
    user = getattr(getattr(request, "state", None), "current_user", None)
    if user is None:
        return "系统任务"
    display_name = getattr(user, "display_name", None)
    username = getattr(user, "username", None)
    return str(display_name or username or f"user:{user.id}")[:80]


def record_audit_event(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Persist a best-effort audit event without leaking clinical payloads."""
    payload = sanitize_details(details)
    user = getattr(getattr(request, "state", None), "current_user", None)
    # Never trust a request body/header supplied operator label. Authentication is
    # the sole source of truth for both the display label and relational user id.
    payload["operator"] = request_operator(request)
    event = AuditLog(
        user_id=user.id if user is not None else None,
        action=action[:50],
        resource_type=resource_type[:50],
        resource_id=resource_id[:100],
        details=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ip_address=request.client.host[:45] if request and request.client else None,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    try:
        db.add(event)
        db.commit()
    except Exception:
        db.rollback()


def audit_event_payload(event: AuditLog) -> dict[str, Any]:
    try:
        details = json.loads(event.details or "{}")
    except json.JSONDecodeError:
        details = {}
    if not isinstance(details, dict):
        details = {}
    details = sanitize_details(details)
    return {
        "id": event.id,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "user_id": event.user_id,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "operator": details.get("operator") or "系统任务",
        "details": details,
    }
