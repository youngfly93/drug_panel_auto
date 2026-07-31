"""Canonical project identity resolution for report submission paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reportgen.core.enhancer_registry import normalize_project_type

from app.services.reportgen_bridge import ReportGenBridge


class ProjectIdentityConflictError(ValueError):
    """Raised when trusted project identity sources disagree."""


@dataclass(frozen=True)
class ProjectIdentity:
    project_type: str | None
    project_name: str | None
    detected_project_type: str | None
    detection: dict[str, Any]


def _normalize_project_type(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return normalize_project_type(text)
    except Exception:
        return text.lower()


def _infer_name_type(
    bridge: ReportGenBridge,
    value: Any,
) -> tuple[str | None, str | None]:
    text = str(value or "").strip()
    if not text:
        return None, None
    inferred = bridge.infer_project_type_from_text(text)
    if not inferred.get("detected"):
        return None, None
    return (
        _normalize_project_type(inferred.get("project_type")),
        str(inferred.get("project_name") or "").strip() or None,
    )


def _canonical_project_name(
    bridge: ReportGenBridge,
    project_type: str | None,
    *fallbacks: Any,
) -> str | None:
    if project_type:
        resolver = getattr(bridge, "project_name_for_type", None)
        if callable(resolver):
            resolved = str(resolver(project_type) or "").strip()
            if resolved:
                return resolved
    for value in fallbacks:
        text = str(value or "").strip()
        if text:
            return text
    return None


def resolve_project_identity(
    bridge: ReportGenBridge,
    *,
    excel_path: str | Path,
    excel_data: Any,
    requested_project_type: Any = None,
    requested_project_name: Any = None,
    clinical_project_name: Any = None,
) -> ProjectIdentity:
    """Resolve one canonical project identity and fail closed on disagreement.

    The comparison is deliberately value-free apart from product identifiers;
    no patient fields or filenames are included in the exception text.
    """
    detection = bridge.detect_project_type(str(excel_path), excel_data=excel_data)
    detector_conflicts = {
        _normalize_project_type(item)
        for item in detection.get("identity_conflicts") or []
        if _normalize_project_type(item)
    }
    if len(detector_conflicts) > 1:
        details = "、".join(sorted(detector_conflicts))
        raise ProjectIdentityConflictError(
            "项目身份冲突："
            f"Excel结构与受信项目文本同时指向不同Panel（{details}）。"
            "为防止跨癌种或跨Panel生成，系统已在任务入队前阻断；"
            "请核对工作簿来源。"
        )
    detected_type = (
        _normalize_project_type(detection.get("project_type"))
        if detection.get("detected")
        else None
    )
    requested_type = _normalize_project_type(requested_project_type)
    request_name_type, request_inferred_name = _infer_name_type(
        bridge,
        requested_project_name,
    )
    clinical_name_type, clinical_inferred_name = _infer_name_type(
        bridge,
        clinical_project_name,
    )

    candidates = [
        ("人工选择", requested_type),
        ("Excel/文件识别", detected_type),
        ("请求项目名称", request_name_type),
        ("临床表单项目名称", clinical_name_type),
    ]
    distinct_types = {value for _source, value in candidates if value}
    if len(distinct_types) > 1:
        details = "、".join(f"{source}={value}" for source, value in candidates if value)
        raise ProjectIdentityConflictError(
            "项目身份冲突："
            f"{details}。为防止跨癌种或跨Panel生成，系统已在任务入队前阻断；"
            "请重新上传并确认项目类型。"
        )

    effective_type = requested_type or detected_type or request_name_type or clinical_name_type
    detected_name = (
        str(detection.get("project_name") or "").strip() if detected_type == effective_type else ""
    )
    effective_name = _canonical_project_name(
        bridge,
        effective_type,
        detected_name,
        request_inferred_name,
        clinical_inferred_name,
        requested_project_name,
        clinical_project_name,
    )
    return ProjectIdentity(
        project_type=effective_type,
        project_name=effective_name,
        detected_project_type=detected_type,
        detection=dict(detection or {}),
    )
