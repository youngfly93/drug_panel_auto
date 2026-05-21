"""Read-only rule engine facade for M7 migration work."""

from __future__ import annotations

from typing import Any, Mapping

from reportgen.rules.loader import RulePackageReport, load_rule_package


class PanelRuleEngine:
    """Small facade around loaded panel rules.

    M7.1 intentionally keeps this read-only. Later M7 steps can add evaluators
    here without changing report generation call sites again.
    """

    def __init__(self, rule_package: RulePackageReport) -> None:
        self.rule_package = rule_package
        self._rules_by_name: dict[str, Mapping[str, Any]] = {
            file.rule_name: file.data for file in rule_package.files if file.ok
        }
        self._rules_by_id: dict[str, Mapping[str, Any]] = {
            file.rule_id: file.data for file in rule_package.files if file.ok
        }

    @classmethod
    def from_panel_package(cls, panel_package: Any) -> "PanelRuleEngine":
        return cls(load_rule_package(panel_package))

    @property
    def provenance(self) -> dict[str, Any]:
        return self.rule_package.to_provenance()

    def get(self, name_or_id: str, default: Any = None) -> Any:
        """Return a loaded rule mapping by logical name or rule_id."""
        return self._rules_by_name.get(name_or_id) or self._rules_by_id.get(
            name_or_id, default
        )
