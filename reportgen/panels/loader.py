"""
Panel Package loader.

M2 starts with a compatibility loader: it can read panel metadata, template
declarations, rule files, processors, and golden-case declarations without
changing the legacy generation path yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

import yaml


PANEL_SCHEMA_VERSION = "1.0"
QA_PROFILE_FILENAME = "qa.yaml"


@dataclass(frozen=True)
class PanelTemplate:
    """A template declared by a panel package."""

    template_id: str
    file: str
    version: str = ""
    status: str = "active"
    description: str = ""
    processors: Optional[tuple[str, ...]] = None


@dataclass(frozen=True)
class PanelPackage:
    """Parsed panel package metadata."""

    panel_id: str
    display_name: str
    root_dir: Path
    version: str = ""
    aliases: tuple[str, ...] = ()
    enhancer: str = ""
    default_template_id: str = ""
    templates: Dict[str, PanelTemplate] = field(default_factory=dict)
    rules: Dict[str, str] = field(default_factory=dict)
    mappings: Dict[str, str] = field(default_factory=dict)
    processors: tuple[str, ...] = ()
    project_detector_rules: Dict[str, Any] = field(default_factory=dict)
    input_contract: Dict[str, Any] = field(default_factory=dict)
    template_contract: Dict[str, Any] = field(default_factory=dict)
    context_contracts: Dict[str, str] = field(default_factory=dict)
    qa_profile: Dict[str, Any] = field(default_factory=dict)
    golden_cases: tuple[Dict[str, Any], ...] = ()
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def default_template(self) -> PanelTemplate:
        """Return the default template declaration."""
        if not self.default_template_id:
            raise ValueError(f"Panel {self.panel_id!r} has no default template")
        try:
            return self.templates[self.default_template_id]
        except KeyError as exc:
            raise ValueError(
                f"Panel {self.panel_id!r} default template "
                f"{self.default_template_id!r} is not declared"
            ) from exc

    def resolve_template_file(self, template_id: Optional[str] = None) -> Path:
        """Resolve a template file path to an absolute path."""
        template = self.templates[template_id] if template_id else self.default_template
        return self._resolve_path(template.file)

    def resolve_rule_file(self, rule_name: str) -> Path:
        """Resolve a rule file path by logical rule name."""
        try:
            rule_path = self.rules[rule_name]
        except KeyError as exc:
            raise KeyError(f"Panel {self.panel_id!r} has no rule {rule_name!r}") from exc
        return self._resolve_path(rule_path)

    def resolve_mapping_file(self, mapping_name: str = "default") -> Path:
        """Resolve a mapping file path by logical mapping name."""
        try:
            mapping_path = self.mappings[mapping_name]
        except KeyError as exc:
            raise KeyError(
                f"Panel {self.panel_id!r} has no mapping {mapping_name!r}"
            ) from exc
        return self._resolve_path(mapping_path)

    def resolve_qa_profile_file(self) -> Path:
        """Resolve this package's QA profile path."""
        return self.root_dir / QA_PROFILE_FILENAME

    def resolve_context_contract_file(self, contract_id: str) -> Path:
        """Resolve a declared pre-render context contract file."""
        try:
            contract_path = self.context_contracts[contract_id]
        except KeyError as exc:
            raise KeyError(
                f"Panel {self.panel_id!r} has no context contract {contract_id!r}"
            ) from exc
        return self._resolve_path(contract_path)

    def _resolve_path(self, value: str) -> Path:
        path = Path(str(value)).expanduser()
        if path.is_absolute():
            return path

        panel_relative = (self.root_dir / path).resolve()
        if panel_relative.exists():
            return panel_relative

        project_relative = (self.root_dir.parent.parent / path).resolve()
        return project_relative


class PanelPackageLoader:
    """Load panel packages from a project-level ``panels/`` directory."""

    def __init__(
        self,
        project_root: Union[str, Path] = ".",
        panels_dir: Union[str, Path] = "panels",
    ) -> None:
        self.project_root = Path(project_root).resolve()
        panels_path = Path(panels_dir)
        if not panels_path.is_absolute():
            panels_path = self.project_root / panels_path
        self.panels_dir = panels_path.resolve()

    def load(self, panel_id: str) -> PanelPackage:
        """Load one panel package by directory name."""
        panel_dir = self.panels_dir / str(panel_id)
        panel_yaml = panel_dir / "panel.yaml"
        if not panel_yaml.exists():
            raise FileNotFoundError(f"Panel package not found: {panel_yaml}")
        return self.load_file(panel_yaml)

    def load_file(self, panel_yaml: Union[str, Path]) -> PanelPackage:
        """Load one panel package from an explicit ``panel.yaml`` path."""
        path = Path(panel_yaml).resolve()
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        ok, errors = validate_panel_package_config(raw)
        if not ok:
            joined = "\n".join(f"- {msg}" for msg in errors)
            raise ValueError(f"panel.yaml schema validation failed:\n{joined}")

        templates = {
            item["id"]: PanelTemplate(
                template_id=str(item["id"]),
                file=str(item["file"]),
                version=str(item.get("version") or ""),
                status=str(item.get("status") or "active"),
                description=str(item.get("description") or ""),
                processors=_parse_optional_processors(item.get("processors")),
            )
            for item in raw.get("templates", [])
        }

        processors = tuple(
            str(item["name"] if isinstance(item, Mapping) else item)
            for item in raw.get("processors", [])
            if str(item["name"] if isinstance(item, Mapping) else item).strip()
        )
        golden_cases = tuple(
            dict(item)
            for item in raw.get("golden_cases", [])
            if isinstance(item, Mapping)
        )
        qa_profile = _load_qa_profile(path.parent)

        return PanelPackage(
            panel_id=str(raw["panel_id"]),
            display_name=str(raw["display_name"]),
            root_dir=path.parent,
            version=str(raw.get("version") or ""),
            aliases=tuple(str(x) for x in raw.get("aliases", [])),
            enhancer=str(raw.get("enhancer") or ""),
            default_template_id=str(raw.get("default_template") or ""),
            templates=templates,
            rules={str(k): str(v) for k, v in (raw.get("rules") or {}).items()},
            mappings={str(k): str(v) for k, v in (raw.get("mappings") or {}).items()},
            processors=processors,
            project_detector_rules=dict(raw.get("project_detector_rules") or {}),
            input_contract=dict(raw.get("input_contract") or {}),
            template_contract=dict(raw.get("template_contract") or {}),
            context_contracts={
                str(k): str(v) for k, v in (raw.get("context_contracts") or {}).items()
            },
            qa_profile=qa_profile,
            golden_cases=golden_cases,
            raw=dict(raw),
        )

    def load_all(self) -> List[PanelPackage]:
        """Load every package that has a ``panel.yaml`` file."""
        if not self.panels_dir.exists():
            return []
        packages: List[PanelPackage] = []
        for panel_yaml in sorted(self.panels_dir.glob("*/panel.yaml")):
            packages.append(self.load_file(panel_yaml))
        return packages


def load_panel_package(
    panel_id: str,
    *,
    project_root: Union[str, Path] = ".",
    panels_dir: Union[str, Path] = "panels",
) -> PanelPackage:
    """Convenience function for loading a panel package."""
    return PanelPackageLoader(project_root=project_root, panels_dir=panels_dir).load(
        panel_id
    )


def _load_qa_profile(panel_dir: Path) -> Dict[str, Any]:
    path = panel_dir / QA_PROFILE_FILENAME
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, Mapping):
        raise ValueError(f"{QA_PROFILE_FILENAME} must be a dict at top level")
    return dict(raw)


def _parse_optional_processors(value: Any) -> Optional[tuple[str, ...]]:
    """Parse an optional template-level processor list.

    ``None`` means inherit panel-level processors. An empty list is intentional
    and disables all post-render processors for that template.
    """
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    result: list[str] = []
    for item in value:
        name = item.get("name") if isinstance(item, Mapping) else item
        text = str(name or "").strip()
        if text:
            result.append(text)
    return tuple(result)


def validate_panel_package_config(cfg: Any) -> tuple[bool, List[str]]:
    """Validate the M2 ``panel.yaml`` shape without external dependencies."""
    errors: List[str] = []
    if not isinstance(cfg, Mapping):
        return False, ["panel.yaml must be a dict at top level"]

    _require_str(cfg, "schema_version", errors)
    if str(cfg.get("schema_version")) != PANEL_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {PANEL_SCHEMA_VERSION!r} "
            f"(got {cfg.get('schema_version')!r})"
        )
    _require_str(cfg, "panel_id", errors)
    _require_str(cfg, "display_name", errors)
    _require_str(cfg, "default_template", errors)

    aliases = cfg.get("aliases", [])
    if aliases is not None and not _is_str_list(aliases):
        errors.append("aliases must be a list[str]")

    templates = cfg.get("templates")
    if not isinstance(templates, list) or not templates:
        errors.append("templates must be a non-empty list")
        templates = []

    template_ids: set[str] = set()
    for idx, item in enumerate(templates):
        if not isinstance(item, Mapping):
            errors.append(f"templates[{idx}] must be a dict")
            continue
        tid = item.get("id")
        if not isinstance(tid, str) or not tid.strip():
            errors.append(f"templates[{idx}].id is required")
        elif tid in template_ids:
            errors.append(f"templates has duplicated id {tid!r}")
        else:
            template_ids.add(tid)
        _require_str(item, "file", errors, prefix=f"templates[{idx}]")
        if "processors" in item and not _valid_processors(item.get("processors")):
            errors.append(
                f"templates[{idx}].processors must be a list[str|{{name: str}}]"
            )

    default_template = cfg.get("default_template")
    if (
        isinstance(default_template, str)
        and template_ids
        and default_template not in template_ids
    ):
        errors.append(
            f"default_template {default_template!r} is not declared in templates"
        )

    for section in (
        "rules",
        "mappings",
        "project_detector_rules",
        "input_contract",
        "template_contract",
        "context_contracts",
    ):
        value = cfg.get(section, {})
        if value is not None and not isinstance(value, Mapping):
            errors.append(f"{section} must be a dict")

    processors = cfg.get("processors", [])
    if processors is not None and not _valid_processors(processors):
        errors.append("processors must be a list[str|{name: str}]")

    golden_cases = cfg.get("golden_cases", [])
    if golden_cases is not None and not isinstance(golden_cases, list):
        errors.append("golden_cases must be a list")

    return len(errors) == 0, errors


def _require_str(
    cfg: Mapping[str, Any],
    key: str,
    errors: List[str],
    *,
    prefix: str = "",
) -> None:
    label = f"{prefix}.{key}" if prefix else key
    value = cfg.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} is required")


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _valid_processors(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if isinstance(item, str) and item.strip():
            continue
        if isinstance(item, Mapping) and isinstance(item.get("name"), str):
            if item.get("name").strip():
                continue
        return False
    return True
