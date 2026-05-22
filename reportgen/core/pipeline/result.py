"""Serializable stage result objects for report generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StageIssue:
    """Machine-readable issue emitted by one generation stage."""

    level: str
    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class StageResult:
    """Execution summary for a pipeline stage."""

    name: str
    status: str = "PASS"
    started_at: str = field(default_factory=_utc_now_iso)
    duration_ms: Optional[float] = None
    issues: List[StageIssue] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def add_issue(
        self,
        *,
        level: str,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.issues.append(
            StageIssue(
                level=level,
                code=code,
                message=message,
                details=details or {},
            )
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "issues": [issue.to_dict() for issue in self.issues],
            "artifacts": dict(self.artifacts),
            "metrics": dict(self.metrics),
        }

