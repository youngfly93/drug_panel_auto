"""Panel package and registry validation.

The loader intentionally stays permissive so legacy code can read package
metadata. This module is the stricter gate used by CLI checks and registry
health checks before a package is treated as production-ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence, Union

import yaml
from docx import Document

from reportgen.docx_sections import inspect_structural_marker
from reportgen.panels.loader import (
    QA_PROFILE_FILENAME,
    PanelPackage,
    PanelPackageLoader,
    validate_panel_package_config,
)
from reportgen.rules.loader import load_rule_package


PANEL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*$")
VALID_PACKAGE_STATUSES = {"draft", "pilot", "active", "deprecated"}
VALID_TEMPLATE_STATUSES = {"draft", "pilot", "active", "deprecated"}
VALID_QA_SEVERITIES = {"off", "warn", "fail"}
YAML_SUFFIXES = {".yaml", ".yml"}
DOCX_SUFFIXES = {".docx"}


@dataclass(frozen=True)
class PanelValidationIssue:
    """One package or registry validation finding."""

    level: str
    code: str
    message: str
    panel_id: str = ""
    path: str = ""
    hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "panel_id": self.panel_id,
            "path": self.path,
            "hint": self.hint,
        }


@dataclass
class PanelValidationReport:
    """Aggregated panel validation result."""

    scope: str
    issues: list[PanelValidationIssue] = field(default_factory=list)
    panels_checked: list[str] = field(default_factory=list)
    rule_packages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def errors(self) -> list[PanelValidationIssue]:
        return [issue for issue in self.issues if issue.level == "ERROR"]

    @property
    def warnings(self) -> list[PanelValidationIssue]:
        return [issue for issue in self.issues if issue.level == "WARN"]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        if self.errors:
            return "FAIL"
        if self.warnings:
            return "WARN"
        return "PASS"

    def add(
        self,
        level: str,
        code: str,
        message: str,
        *,
        panel_id: str = "",
        path: Union[str, Path, None] = None,
        hint: str = "",
    ) -> None:
        self.issues.append(
            PanelValidationIssue(
                level=level,
                code=code,
                message=message,
                panel_id=panel_id,
                path=str(path or ""),
                hint=hint,
            )
        )

    def extend(self, other: "PanelValidationReport") -> None:
        self.issues.extend(other.issues)
        for panel_id in other.panels_checked:
            if panel_id not in self.panels_checked:
                self.panels_checked.append(panel_id)
        self.rule_packages.extend(other.rule_packages)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "status": self.status,
            "ok": self.ok,
            "panels_checked": list(self.panels_checked),
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "issues": len(self.issues),
            },
            "rule_packages": list(self.rule_packages),
            "issues": [issue.to_dict() for issue in self.issues],
        }


class PanelPackageValidator:
    """Validate panel package layout and declarations."""

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
        self.loader = PanelPackageLoader(
            project_root=self.project_root,
            panels_dir=self.panels_dir,
        )

    def validate_panel(self, panel_id: str) -> PanelValidationReport:
        panel_yaml = self._resolve_panel_yaml(panel_id)
        return self.validate_file(panel_yaml)

    def validate_file(self, panel_yaml: Union[str, Path]) -> PanelValidationReport:
        path = Path(panel_yaml).resolve()
        report = PanelValidationReport(scope=str(path))

        if path.name != "panel.yaml":
            report.add(
                "ERROR",
                "PANEL_YAML_NAME",
                "Panel package metadata file must be named panel.yaml",
                path=path,
            )
        if not path.exists():
            report.add(
                "ERROR",
                "PANEL_YAML_MISSING",
                "Panel package is missing panel.yaml",
                path=path,
            )
            return report

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            report.add(
                "ERROR",
                "PANEL_YAML_UNREADABLE",
                f"panel.yaml cannot be read as YAML: {exc}",
                path=path,
            )
            return report

        ok, errors = validate_panel_package_config(raw)
        panel_id = str(raw.get("panel_id") or "")
        if panel_id:
            report.panels_checked.append(panel_id)
        if not ok:
            for msg in errors:
                report.add(
                    "ERROR",
                    "PANEL_YAML_SCHEMA",
                    msg,
                    panel_id=panel_id,
                    path=path,
                )
            return report

        try:
            package = self.loader.load_file(path)
        except Exception as exc:
            report.add(
                "ERROR",
                "PANEL_PACKAGE_LOAD_FAILED",
                f"Panel package cannot be loaded: {exc}",
                panel_id=panel_id,
                path=path,
            )
            return report

        self._validate_package(package, raw, report)
        return report

    def validate_all(self) -> PanelValidationReport:
        report = PanelValidationReport(scope=str(self.panels_dir))
        if not self.panels_dir.exists():
            report.add(
                "ERROR",
                "PANELS_DIR_MISSING",
                "panels directory does not exist",
                path=self.panels_dir,
            )
            return report

        panel_yamls = sorted(self.panels_dir.glob("*/panel.yaml"))
        if not panel_yamls:
            report.add(
                "ERROR",
                "NO_PANEL_PACKAGES",
                "No panel packages were found under panels/",
                path=self.panels_dir,
            )
            return report

        valid_packages: list[PanelPackage] = []
        for panel_yaml in panel_yamls:
            sub_report = self.validate_file(panel_yaml)
            report.extend(sub_report)
            if sub_report.ok:
                valid_packages.append(self.loader.load_file(panel_yaml))

        self._validate_registry_aliases(valid_packages, report)
        return report

    def _resolve_panel_yaml(self, panel_id: str) -> Path:
        requested = str(panel_id or "").strip().lower()
        direct = self.panels_dir / requested / "panel.yaml"
        if direct.exists():
            return direct

        for panel_yaml in sorted(self.panels_dir.glob("*/panel.yaml")):
            try:
                raw = yaml.safe_load(panel_yaml.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            names = [raw.get("panel_id"), *(raw.get("aliases") or [])]
            if requested in {str(name or "").strip().lower() for name in names}:
                return panel_yaml
        return direct

    def _validate_package(
        self,
        package: PanelPackage,
        raw: Mapping[str, Any],
        report: PanelValidationReport,
    ) -> None:
        panel_id = package.panel_id
        panel_yaml = package.root_dir / "panel.yaml"

        if not PANEL_ID_PATTERN.match(panel_id):
            report.add(
                "ERROR",
                "PANEL_ID_FORMAT",
                "panel_id must use lowercase letters, digits, and underscores",
                panel_id=panel_id,
                path=panel_yaml,
            )
        if package.root_dir.name != panel_id:
            report.add(
                "ERROR",
                "PANEL_DIR_NAME_MISMATCH",
                "Panel directory name must exactly match panel_id",
                panel_id=panel_id,
                path=package.root_dir,
                hint=f"Rename directory to {panel_id!r} or update panel_id.",
            )

        status = str(raw.get("status") or "").strip()
        if not status:
            report.add(
                "ERROR",
                "PACKAGE_STATUS_REQUIRED",
                "status is required and must be one of draft/pilot/active/deprecated",
                panel_id=panel_id,
                path=panel_yaml,
            )
        elif status not in VALID_PACKAGE_STATUSES:
            report.add(
                "ERROR",
                "PACKAGE_STATUS_INVALID",
                f"Unsupported package status: {status!r}",
                panel_id=panel_id,
                path=panel_yaml,
            )

        if not str(raw.get("version") or "").strip():
            report.add(
                "ERROR",
                "PACKAGE_VERSION_REQUIRED",
                "version is required so generated reports can be traced to "
                "a package revision",
                panel_id=panel_id,
                path=panel_yaml,
            )

        self._validate_templates(package, raw, report)
        self._validate_declared_file_map(
            package,
            package.rules,
            report,
            section="rules",
            allowed_suffixes=YAML_SUFFIXES,
        )
        self._validate_panel_rules(package, report)
        self._validate_declared_file_map(
            package,
            package.mappings,
            report,
            section="mappings",
            allowed_suffixes=YAML_SUFFIXES,
        )
        self._validate_declared_file_map(
            package,
            package.context_contracts,
            report,
            section="context_contracts",
            allowed_suffixes=YAML_SUFFIXES,
        )
        self._validate_enhancer(package, report)
        self._validate_processors(package, report)
        self._validate_contracts(package, raw, report)
        self._validate_qa_profile(package, report)
        self._validate_golden_cases(package, raw, report)

    def _validate_templates(
        self,
        package: PanelPackage,
        raw: Mapping[str, Any],
        report: PanelValidationReport,
    ) -> None:
        panel_id = package.panel_id
        template_statuses = {
            str(item.get("id")): str(item.get("status") or "active")
            for item in raw.get("templates", [])
            if isinstance(item, Mapping)
        }
        for template_id, template in package.templates.items():
            status = template_statuses.get(template_id, template.status)
            if status not in VALID_TEMPLATE_STATUSES:
                report.add(
                    "ERROR",
                    "TEMPLATE_STATUS_INVALID",
                    f"Unsupported template status: {status!r}",
                    panel_id=panel_id,
                    path=package.root_dir / "panel.yaml",
                )
            self._validate_declared_file(
                package,
                template.file,
                report,
                label=f"templates.{template_id}.file",
                allowed_suffixes=DOCX_SUFFIXES,
            )

        try:
            default_template = package.default_template
        except Exception as exc:
            report.add(
                "ERROR",
                "DEFAULT_TEMPLATE_INVALID",
                str(exc),
                panel_id=panel_id,
                path=package.root_dir / "panel.yaml",
            )
            return

        default_status = template_statuses.get(
            default_template.template_id, default_template.status
        )
        if default_status == "deprecated":
            report.add(
                "ERROR",
                "DEFAULT_TEMPLATE_DEPRECATED",
                "default_template cannot point to a deprecated template",
                panel_id=panel_id,
                path=package.root_dir / "panel.yaml",
            )

    def _validate_declared_file_map(
        self,
        package: PanelPackage,
        values: Mapping[str, str],
        report: PanelValidationReport,
        *,
        section: str,
        allowed_suffixes: set[str],
    ) -> None:
        for name, value in values.items():
            self._validate_declared_file(
                package,
                value,
                report,
                label=f"{section}.{name}",
                allowed_suffixes=allowed_suffixes,
            )

    def _validate_declared_file(
        self,
        package: PanelPackage,
        value: str,
        report: PanelValidationReport,
        *,
        label: str,
        allowed_suffixes: set[str],
    ) -> None:
        raw_path = Path(str(value or ""))
        panel_id = package.panel_id
        panel_yaml = package.root_dir / "panel.yaml"

        if not str(value or "").strip():
            report.add(
                "ERROR",
                "DECLARED_PATH_EMPTY",
                f"{label} cannot be empty",
                panel_id=panel_id,
                path=panel_yaml,
            )
            return
        if raw_path.is_absolute():
            report.add(
                "ERROR",
                "DECLARED_PATH_ABSOLUTE",
                f"{label} must be relative to the panel or project root",
                panel_id=panel_id,
                path=value,
            )
        if ".." in raw_path.parts:
            report.add(
                "ERROR",
                "DECLARED_PATH_PARENT_REF",
                f"{label} must not use '..' path segments",
                panel_id=panel_id,
                path=value,
            )

        if raw_path.suffix.lower() not in allowed_suffixes:
            report.add(
                "ERROR",
                "DECLARED_PATH_SUFFIX",
                f"{label} has unsupported suffix {raw_path.suffix!r}",
                panel_id=panel_id,
                path=value,
                hint=f"Expected one of: {', '.join(sorted(allowed_suffixes))}",
            )

        resolved = self._resolve_declared_path(package, raw_path)
        if not _is_within_any(resolved, [package.root_dir, self.project_root]):
            report.add(
                "ERROR",
                "DECLARED_PATH_OUTSIDE_ROOT",
                f"{label} resolves outside the panel/project root",
                panel_id=panel_id,
                path=resolved,
            )
        if not resolved.exists() or not resolved.is_file():
            report.add(
                "ERROR",
                "DECLARED_FILE_MISSING",
                f"{label} points to a missing file",
                panel_id=panel_id,
                path=resolved,
            )

    def _resolve_declared_path(self, package: PanelPackage, raw_path: Path) -> Path:
        if raw_path.is_absolute():
            return raw_path.expanduser().resolve()

        panel_relative = (package.root_dir / raw_path).resolve()
        project_relative = (self.project_root / raw_path).resolve()
        if panel_relative.exists():
            return panel_relative
        if project_relative.exists():
            return project_relative
        if raw_path.parts and raw_path.parts[0] in {
            "context_contracts",
            "golden_cases",
            "rules",
            "templates",
        }:
            return panel_relative
        return project_relative

    def _validate_enhancer(
        self, package: PanelPackage, report: PanelValidationReport
    ) -> None:
        enhancer = str(package.enhancer or "").strip()
        if not enhancer:
            return
        if enhancer == "reportgen.core.enhancer_registry:CRC358Enhancer":
            return
        try:
            module_name, attr_name = enhancer.split(":", 1)
            attr = getattr(import_module(module_name), attr_name)
        except Exception as exc:
            report.add(
                "ERROR",
                "ENHANCER_IMPORT_FAILED",
                f"enhancer cannot be imported: {exc}",
                panel_id=package.panel_id,
                path=package.root_dir / "panel.yaml",
            )
            return

        if not hasattr(attr, "enhance"):
            try:
                instance = attr()
            except Exception as exc:
                report.add(
                    "ERROR",
                    "ENHANCER_INVALID",
                    f"enhancer is not usable and cannot be instantiated: {exc}",
                    panel_id=package.panel_id,
                    path=package.root_dir / "panel.yaml",
                )
                return
            if not hasattr(instance, "enhance"):
                report.add(
                    "ERROR",
                    "ENHANCER_INVALID",
                    "enhancer must expose an enhance(...) method",
                    panel_id=package.panel_id,
                    path=package.root_dir / "panel.yaml",
                )

    def _validate_processors(
        self, package: PanelPackage, report: PanelValidationReport
    ) -> None:
        self._validate_processor_list(
            package,
            report,
            names=package.processors,
            path=package.root_dir / "panel.yaml",
            scope="panel processors",
        )
        for template_id, template in package.templates.items():
            if template.processors is None:
                continue
            self._validate_processor_list(
                package,
                report,
                names=template.processors,
                path=package.root_dir / "panel.yaml",
                scope=f"templates.{template_id}.processors",
            )

    def _validate_processor_list(
        self,
        package: PanelPackage,
        report: PanelValidationReport,
        *,
        names: Iterable[str],
        path: Union[str, Path],
        scope: str,
    ) -> None:
        seen: set[str] = set()
        known = _known_processor_names()
        for name in names:
            if name in seen:
                report.add(
                    "ERROR",
                    "PROCESSOR_DUPLICATED",
                    f"Processor {name!r} is declared more than once in {scope}",
                    panel_id=package.panel_id,
                    path=path,
                )
            seen.add(name)
            if known and name not in known:
                report.add(
                    "ERROR",
                    "PROCESSOR_UNKNOWN",
                    f"Unknown DOCX processor in {scope}: {name!r}",
                    panel_id=package.panel_id,
                    path=path,
                )
        for issue in _validate_processor_sequence(names):
            if issue.get("code") in {"PROCESSOR_UNKNOWN", "PROCESSOR_DUPLICATED"}:
                continue
            report.add(
                "ERROR",
                str(issue.get("code") or "PROCESSOR_INVALID"),
                f"{scope}: {issue.get('message') or 'Invalid DOCX processor sequence.'}",
                panel_id=package.panel_id,
                path=path,
            )

    def _validate_panel_rules(
        self, package: PanelPackage, report: PanelValidationReport
    ) -> None:
        rule_report = load_rule_package(package)
        payload = rule_report.to_dict()
        if payload["file_count"] or payload["issues"]:
            report.rule_packages.append(payload)

        for issue in rule_report.issues:
            report.add(
                "ERROR" if issue.level == "ERROR" else "WARN",
                issue.code,
                issue.message,
                panel_id=package.panel_id,
                path=issue.path,
                hint=issue.hint,
            )

    def _validate_contracts(
        self,
        package: PanelPackage,
        raw: Mapping[str, Any],
        report: PanelValidationReport,
    ) -> None:
        for section in ("input_contract", "template_contract"):
            value = raw.get(section)
            if not isinstance(value, Mapping) or not value:
                report.add(
                    "ERROR",
                    "CONTRACT_REQUIRED",
                    f"{section} must be declared and non-empty",
                    panel_id=package.panel_id,
                    path=package.root_dir / "panel.yaml",
                )

        input_contract = raw.get("input_contract") or {}
        if isinstance(input_contract, Mapping):
            required_tables = input_contract.get("required_tables")
            if not isinstance(required_tables, list) or not required_tables:
                report.add(
                    "ERROR",
                    "INPUT_REQUIRED_TABLES_EMPTY",
                    "input_contract.required_tables must be a non-empty list",
                    panel_id=package.panel_id,
                    path=package.root_dir / "panel.yaml",
                )

        template_contract = raw.get("template_contract") or {}
        required_markers = (
            template_contract.get("required_markers", [])
            if isinstance(template_contract, Mapping)
            else []
        )
        if isinstance(required_markers, list) and required_markers:
            try:
                template_path = package.resolve_template_file()
                document = Document(template_path)
            except Exception as exc:
                report.add(
                    "ERROR",
                    "TEMPLATE_MARKER_CHECK_FAILED",
                    f"Cannot inspect default template markers: {exc}",
                    panel_id=package.panel_id,
                    path=package.root_dir / "panel.yaml",
                )
            else:
                for raw_marker in required_markers:
                    marker = str(raw_marker or "").strip()
                    if not marker:
                        continue
                    marker_indices, count = inspect_structural_marker(
                        document,
                        marker,
                    )
                    if not marker_indices:
                        report.add(
                            "ERROR",
                            "TEMPLATE_MARKER_MISSING",
                            f"Default template is missing required marker {marker!r}",
                            panel_id=package.panel_id,
                            path=template_path,
                        )
                    elif count > 1:
                        report.add(
                            "ERROR",
                            "TEMPLATE_MARKER_DUPLICATED",
                            f"Default template contains required marker {marker!r} {count} times",
                            panel_id=package.panel_id,
                            path=template_path,
                        )

    def _validate_golden_cases(
        self,
        package: PanelPackage,
        raw: Mapping[str, Any],
        report: PanelValidationReport,
    ) -> None:
        cases = raw.get("golden_cases")
        if not isinstance(cases, list) or not cases:
            report.add(
                "ERROR",
                "GOLDEN_CASE_REQUIRED",
                "Each panel package must declare at least one golden case",
                panel_id=package.panel_id,
                path=package.root_dir / "panel.yaml",
            )
            return

        ids: set[str] = set()
        for idx, item in enumerate(cases):
            if not isinstance(item, Mapping):
                report.add(
                    "ERROR",
                    "GOLDEN_CASE_INVALID",
                    f"golden_cases[{idx}] must be a dict",
                    panel_id=package.panel_id,
                    path=package.root_dir / "panel.yaml",
                )
                continue
            case_id = str(item.get("id") or "").strip()
            if not case_id:
                report.add(
                    "ERROR",
                    "GOLDEN_CASE_ID_REQUIRED",
                    f"golden_cases[{idx}].id is required",
                    panel_id=package.panel_id,
                    path=package.root_dir / "panel.yaml",
                )
            elif case_id in ids:
                report.add(
                    "ERROR",
                    "GOLDEN_CASE_ID_DUPLICATED",
                    f"golden case id {case_id!r} is duplicated",
                    panel_id=package.panel_id,
                    path=package.root_dir / "panel.yaml",
                )
            ids.add(case_id)
            if not str(item.get("runner") or "").strip() and not str(
                item.get("command") or ""
            ).strip():
                report.add(
                    "ERROR",
                    "GOLDEN_CASE_RUNNER_REQUIRED",
                    "Each golden case must declare runner or command",
                    panel_id=package.panel_id,
                    path=package.root_dir / "panel.yaml",
                )

    def _validate_qa_profile(
        self,
        package: PanelPackage,
        report: PanelValidationReport,
    ) -> None:
        path = package.resolve_qa_profile_file()
        if not path.exists():
            report.add(
                "ERROR",
                "QA_PROFILE_REQUIRED",
                f"Panel package must declare {QA_PROFILE_FILENAME}",
                panel_id=package.panel_id,
                path=path,
            )
            return

        profile = package.qa_profile
        if not isinstance(profile, Mapping):
            report.add(
                "ERROR",
                "QA_PROFILE_INVALID",
                f"{QA_PROFILE_FILENAME} must be a dict",
                panel_id=package.panel_id,
                path=path,
            )
            return
        if str(profile.get("schema_version") or "") != "1.0":
            report.add(
                "ERROR",
                "QA_PROFILE_SCHEMA_VERSION",
                "qa.yaml schema_version must be '1.0'",
                panel_id=package.panel_id,
                path=path,
            )
        if str(profile.get("panel_id") or "") != package.panel_id:
            report.add(
                "ERROR",
                "QA_PROFILE_PANEL_MISMATCH",
                "qa.yaml panel_id must match panel.yaml panel_id",
                panel_id=package.panel_id,
                path=path,
            )

        self._validate_current_output_profile(package, profile, path, report)
        legacy = profile.get("legacy_reference", {})
        if legacy is None:
            return
        if not isinstance(legacy, Mapping):
            report.add(
                "ERROR",
                "QA_LEGACY_REFERENCE_INVALID",
                "legacy_reference must be a dict when present",
                panel_id=package.panel_id,
                path=path,
            )
            return

        enabled = legacy.get("enabled", False)
        if not isinstance(enabled, bool):
            report.add(
                "ERROR",
                "QA_LEGACY_ENABLED_INVALID",
                "legacy_reference.enabled must be a bool",
                panel_id=package.panel_id,
                path=path,
            )
        sample_count = legacy.get("sample_count", 5)
        if not isinstance(sample_count, int) or sample_count <= 0:
            report.add(
                "ERROR",
                "QA_LEGACY_SAMPLE_COUNT_INVALID",
                "legacy_reference.sample_count must be a positive integer",
                panel_id=package.panel_id,
                path=path,
            )
        source_dir_name = legacy.get("source_dir_name", package.panel_id)
        if not isinstance(source_dir_name, str) or not source_dir_name.strip():
            report.add(
                "ERROR",
                "QA_LEGACY_SOURCE_DIR_INVALID",
                "legacy_reference.source_dir_name must be a non-empty string",
                panel_id=package.panel_id,
                path=path,
            )

        for key in ("required_features", "required_sections", "privacy_checks"):
            self._validate_qa_severity_map(
                legacy.get(key, {}),
                key=key,
                package=package,
                path=path,
                report=report,
            )
        if "require_table_shapes" in legacy:
            value = legacy.get("require_table_shapes")
            if value not in VALID_QA_SEVERITIES:
                report.add(
                    "ERROR",
                    "QA_LEGACY_SEVERITY_INVALID",
                    "legacy_reference.require_table_shapes must be off/warn/fail",
                    panel_id=package.panel_id,
                    path=path,
                )

    def _validate_current_output_profile(
        self,
        package: PanelPackage,
        profile: Mapping[str, Any],
        path: Path,
        report: PanelValidationReport,
    ) -> None:
        current = profile.get("current_output", {})
        if current is None:
            return
        if not isinstance(current, Mapping):
            report.add(
                "ERROR",
                "QA_CURRENT_OUTPUT_INVALID",
                "current_output must be a dict when present",
                panel_id=package.panel_id,
                path=path,
            )
            return
        enabled = current.get("enabled", False)
        if not isinstance(enabled, bool):
            report.add(
                "ERROR",
                "QA_CURRENT_ENABLED_INVALID",
                "current_output.enabled must be a bool",
                panel_id=package.panel_id,
                path=path,
            )
        source = current.get("source", "golden_reference")
        if source not in {"golden_reference", "golden_candidate"}:
            report.add(
                "ERROR",
                "QA_CURRENT_SOURCE_INVALID",
                "current_output.source must be golden_reference or golden_candidate",
                panel_id=package.panel_id,
                path=path,
            )
        for key in ("required_features", "required_sections", "privacy_checks"):
            self._validate_qa_severity_map(
                current.get(key, {}),
                key=f"current_output.{key}",
                package=package,
                path=path,
                report=report,
            )
        if "require_table_shapes" in current:
            value = current.get("require_table_shapes")
            if value not in VALID_QA_SEVERITIES:
                report.add(
                    "ERROR",
                    "QA_CURRENT_SEVERITY_INVALID",
                    "current_output.require_table_shapes must be off/warn/fail",
                    panel_id=package.panel_id,
                    path=path,
                )

    def _validate_qa_severity_map(
        self,
        value: Any,
        *,
        key: str,
        package: PanelPackage,
        path: Path,
        report: PanelValidationReport,
    ) -> None:
        label = key if "." in key else f"legacy_reference.{key}"
        if isinstance(value, list):
            for idx, item in enumerate(value):
                if not isinstance(item, str) or not item.strip():
                    report.add(
                        "ERROR",
                        "QA_LEGACY_RULE_INVALID",
                        f"{label}[{idx}] must be a non-empty string",
                        panel_id=package.panel_id,
                        path=path,
                    )
            return
        if isinstance(value, Mapping):
            for name, severity in value.items():
                if not isinstance(name, str) or not name.strip():
                    report.add(
                        "ERROR",
                        "QA_LEGACY_RULE_INVALID",
                        f"{label} contains an empty rule name",
                        panel_id=package.panel_id,
                        path=path,
                    )
                if severity not in VALID_QA_SEVERITIES:
                    report.add(
                        "ERROR",
                        "QA_LEGACY_SEVERITY_INVALID",
                        f"{label}.{name} must be off/warn/fail",
                        panel_id=package.panel_id,
                        path=path,
                    )
            return
        report.add(
            "ERROR",
            "QA_LEGACY_RULES_INVALID",
            f"{label} must be a list or dict",
            panel_id=package.panel_id,
            path=path,
        )

    def _validate_registry_aliases(
        self, packages: Sequence[PanelPackage], report: PanelValidationReport
    ) -> None:
        owners: dict[str, str] = {}
        for package in packages:
            names = [package.panel_id, *package.aliases]
            for raw_name in names:
                name = str(raw_name or "").strip().lower()
                if not name:
                    continue
                owner = owners.get(name)
                if owner and owner != package.panel_id:
                    report.add(
                        "ERROR",
                        "REGISTRY_ALIAS_COLLISION",
                        f"Registry name {name!r} is claimed by both "
                        f"{owner!r} and {package.panel_id!r}",
                        panel_id=package.panel_id,
                        path=package.root_dir / "panel.yaml",
                    )
                else:
                    owners[name] = package.panel_id


def validate_panel_package_path(
    panel_yaml: Union[str, Path],
    *,
    project_root: Union[str, Path] = ".",
    panels_dir: Union[str, Path] = "panels",
) -> PanelValidationReport:
    """Validate one panel.yaml file."""
    return PanelPackageValidator(project_root, panels_dir).validate_file(panel_yaml)


def validate_panel_package(
    panel_id: str,
    *,
    project_root: Union[str, Path] = ".",
    panels_dir: Union[str, Path] = "panels",
) -> PanelValidationReport:
    """Validate one package by panel id."""
    return PanelPackageValidator(project_root, panels_dir).validate_panel(panel_id)


def validate_panel_registry(
    *,
    project_root: Union[str, Path] = ".",
    panels_dir: Union[str, Path] = "panels",
) -> PanelValidationReport:
    """Validate all packages and their registry alias namespace."""
    return PanelPackageValidator(project_root, panels_dir).validate_all()


def _known_processor_names() -> set[str]:
    # Keep this module import-light: panel validate must work even when the
    # runtime registry cannot be built because a package is invalid.
    from reportgen.core.processors.registry import known_docx_processor_names

    return known_docx_processor_names()


def _validate_processor_sequence(names: Iterable[str]) -> list[dict[str, Any]]:
    from reportgen.core.processors.registry import validate_docx_processor_sequence

    return validate_docx_processor_sequence(names)


def _is_within_any(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False
