"""Schema validation primitives for panel rule files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml


RULE_SCHEMA_VERSION = "1.0"
RULE_METADATA_KEYS = {
    "schema_version",
    "panel_id",
    "rule_id",
    "version",
    "updated",
    "status",
    "notes",
    "description",
}


@dataclass(frozen=True)
class RuleValidationIssue:
    """One rule-file validation finding."""

    level: str
    code: str
    message: str
    path: str = ""
    rule_name: str = ""
    rule_id: str = ""
    hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "rule_name": self.rule_name,
            "rule_id": self.rule_id,
            "hint": self.hint,
        }


@dataclass
class RuleFileReport:
    """Validated metadata for one YAML rule file."""

    rule_name: str
    path: str
    ok: bool
    data: Mapping[str, Any] = field(default_factory=dict)
    issues: list[RuleValidationIssue] = field(default_factory=list)

    @property
    def rule_id(self) -> str:
        value = self.data.get("rule_id") if isinstance(self.data, Mapping) else None
        return str(value or self.rule_name)

    @property
    def version(self) -> str:
        value = self.data.get("version") if isinstance(self.data, Mapping) else None
        return str(value or "")

    @property
    def status(self) -> str:
        value = self.data.get("status") if isinstance(self.data, Mapping) else None
        return str(value or "")

    @property
    def schema_version(self) -> str:
        value = (
            self.data.get("schema_version") if isinstance(self.data, Mapping) else None
        )
        return str(value or "")

    @property
    def updated(self) -> str:
        value = self.data.get("updated") if isinstance(self.data, Mapping) else None
        return str(value or "")

    def to_provenance(self, *, sha256: str = "") -> dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "rule_id": self.rule_id,
            "schema_version": self.schema_version,
            "version": self.version,
            "status": self.status,
            "updated": self.updated,
            "path": self.path,
            "sha256": sha256,
        }


class DuplicateKeyError(ValueError):
    """Raised when a YAML mapping contains a duplicate key."""


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(loader: UniqueKeyLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            mark = getattr(key_node, "start_mark", None)
            where = f" at line {mark.line + 1}" if mark is not None else ""
            raise DuplicateKeyError(f"Duplicate YAML key {key!r}{where}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_rule_yaml(path: str | Path) -> Mapping[str, Any]:
    """Load a YAML rule file and reject duplicate keys."""
    with Path(path).open("r", encoding="utf-8") as fh:
        data = yaml.load(fh, Loader=UniqueKeyLoader) or {}
    if not isinstance(data, Mapping):
        raise ValueError("Rule file must be a mapping at top level")
    return data


def validate_rule_mapping(
    data: Any,
    *,
    path: str | Path,
    rule_name: str,
    expected_panel_id: str | None = None,
) -> RuleFileReport:
    """Validate one rule mapping and return machine-readable findings."""
    issues: list[RuleValidationIssue] = []
    path_str = str(path)

    def add(code: str, message: str, *, hint: str = "") -> None:
        issues.append(
            RuleValidationIssue(
                level="ERROR",
                code=code,
                message=message,
                path=path_str,
                rule_name=rule_name,
                rule_id=str(data.get("rule_id") or rule_name)
                if isinstance(data, Mapping)
                else "",
                hint=hint,
            )
        )

    if not isinstance(data, Mapping):
        add("RULE_TOP_LEVEL_INVALID", "Rule file must be a mapping at top level.")
        return RuleFileReport(rule_name, path_str, False, {}, issues)

    schema_version = data.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        add("RULE_SCHEMA_VERSION_REQUIRED", "schema_version is required.")
    elif schema_version != RULE_SCHEMA_VERSION:
        add(
            "RULE_SCHEMA_VERSION_INVALID",
            f"schema_version must be {RULE_SCHEMA_VERSION!r}.",
        )

    panel_id = data.get("panel_id")
    if not isinstance(panel_id, str) or not panel_id.strip():
        add("RULE_PANEL_ID_REQUIRED", "panel_id is required.")
    elif expected_panel_id and panel_id != expected_panel_id:
        add(
            "RULE_PANEL_ID_MISMATCH",
            f"panel_id {panel_id!r} does not match package {expected_panel_id!r}.",
        )

    rule_id = data.get("rule_id")
    if rule_id is not None and (not isinstance(rule_id, str) or not rule_id.strip()):
        add("RULE_ID_INVALID", "rule_id must be a non-empty string when provided.")

    version = data.get("version")
    if version is not None and (
        not isinstance(version, str) or not version.strip()
    ):
        add("RULE_VERSION_INVALID", "version must be a non-empty string when provided.")

    content_keys = [key for key in data.keys() if key not in RULE_METADATA_KEYS]
    if not content_keys:
        add(
            "RULE_CONTENT_EMPTY",
            "Rule file must contain at least one non-metadata content section.",
        )

    return RuleFileReport(
        rule_name=rule_name,
        path=path_str,
        ok=not issues,
        data=data,
        issues=issues,
    )
