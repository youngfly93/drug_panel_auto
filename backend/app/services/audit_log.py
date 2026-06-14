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
    if not request:
        return "未登录操作员"
    for header in ("x-reportgen-operator", "x-operator", "x-user-name"):
        value = (request.headers.get(header) or "").strip()
        if value:
            return value[:80]
    return "未登录操作员"


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
    payload.setdefault("operator", request_operator(request))
    event = AuditLog(
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
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "operator": details.get("operator") or "未登录操作员",
        "details": details,
    }
