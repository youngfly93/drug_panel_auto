"""Shared context for a report generation pipeline run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class GenerationContext:
    """Mutable state shared by generation stages.

    M6 keeps this deliberately small: existing generation code still owns the
    real objects, while the context provides a stable place for future stages to
    exchange request metadata, artifacts, and metrics.
    """

    request: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

