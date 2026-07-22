"""Environment-scoped production release guard for report panels."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from typing import Any


DISABLED_PROJECT_TYPES_ENV = "REPORTGEN_DISABLED_PROJECT_TYPES"


class PanelReleaseDisabledError(RuntimeError):
    """Raised when a panel is intentionally unavailable in this release."""


def disabled_project_types(value: Any = None) -> set[str]:
    """Return normalized panel ids from an env/string/iterable declaration."""
    raw = os.environ.get(DISABLED_PROJECT_TYPES_ENV, "") if value is None else value
    if isinstance(raw, str):
        values: Iterable[Any] = re.split(r"[,;\s]+", raw)
    elif isinstance(raw, Iterable):
        values = raw
    else:
        values = (raw,)
    return {
        str(item).strip().lower()
        for item in values
        if str(item or "").strip()
    }


def ensure_project_type_enabled(
    project_type: Any,
    *,
    disabled: Any = None,
) -> str:
    """Fail closed when a canonical project type is disabled for this release."""
    canonical = str(project_type or "").strip().lower()
    if canonical and canonical in disabled_project_types(disabled):
        raise PanelReleaseDisabledError(
            f"项目类型 {canonical} 当前未开放生产生成；完成该 Panel 病例级 UAT 后方可启用。"
        )
    return canonical
