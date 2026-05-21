"""Rule evaluator extension points.

Concrete evaluators are intentionally deferred until M7.2+. Keeping this module
now gives future panel-specific rule migration a stable import path.
"""

from __future__ import annotations

from typing import Any, Protocol


class RuleEvaluator(Protocol):
    """Protocol for future rule evaluators."""

    def evaluate(self, data: Any, rules: dict[str, Any]) -> Any:
        """Evaluate one rule set against input data."""
