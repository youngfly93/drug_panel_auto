"""Panel rule package loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from reportgen.rules.schema import (
    DuplicateKeyError,
    RuleFileReport,
    RuleValidationIssue,
    load_rule_yaml,
    validate_rule_mapping,
)


@dataclass
class RulePackageReport:
    """Validation and provenance for the rules declared by one panel package."""

    panel_id: str
    files: list[RuleFileReport] = field(default_factory=list)
    issues: list[RuleValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def status(self) -> str:
        return "PASS" if self.ok else "FAIL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "panel_id": self.panel_id,
            "status": self.status,
            "ok": self.ok,
            "file_count": len(self.files),
            "files": [
                {
                    **file.to_provenance(
                        sha256=_sha256_file(file.path) if Path(file.path).exists() else ""
                    ),
                    "ok": file.ok,
                }
                for file in self.files
            ],
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_provenance(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "panel_id": self.panel_id,
            "status": self.status,
            "ok": self.ok,
            "file_count": len(self.files),
            "files": [
                file.to_provenance(
                    sha256=_sha256_file(file.path) if Path(file.path).exists() else ""
                )
                for file in self.files
            ],
            "issues": [issue.to_dict() for issue in self.issues],
        }


class RulePackageLoader:
    """Load and validate panel-local rule files declared in panel.yaml."""

    def load_package(self, panel_package: Any) -> RulePackageReport:
        report = RulePackageReport(panel_id=str(getattr(panel_package, "panel_id", "")))
        rules = getattr(panel_package, "rules", {}) or {}
        if not isinstance(rules, Mapping):
            report.issues.append(
                RuleValidationIssue(
                    level="ERROR",
                    code="RULE_DECLARATIONS_INVALID",
                    message="panel.yaml rules must be a mapping.",
                    path=str(Path(getattr(panel_package, "root_dir", "")) / "panel.yaml"),
                )
            )
            return report

        seen_rule_ids: dict[str, str] = {}
        for rule_name, raw_path in sorted(rules.items()):
            if not _is_panel_rule(panel_package, str(raw_path)):
                continue
            path = panel_package.resolve_rule_file(str(rule_name))
            try:
                data = load_rule_yaml(path)
            except DuplicateKeyError as exc:
                issue = RuleValidationIssue(
                    level="ERROR",
                    code="RULE_DUPLICATE_KEY",
                    message=str(exc),
                    path=str(path),
                    rule_name=str(rule_name),
                )
                report.issues.append(issue)
                report.files.append(
                    RuleFileReport(
                        rule_name=str(rule_name),
                        path=str(path),
                        ok=False,
                        data={},
                        issues=[issue],
                    )
                )
                continue
            except Exception as exc:
                issue = RuleValidationIssue(
                    level="ERROR",
                    code="RULE_FILE_UNREADABLE",
                    message=f"Rule file cannot be read as YAML: {exc}",
                    path=str(path),
                    rule_name=str(rule_name),
                )
                report.issues.append(issue)
                report.files.append(
                    RuleFileReport(
                        rule_name=str(rule_name),
                        path=str(path),
                        ok=False,
                        data={},
                        issues=[issue],
                    )
                )
                continue

            file_report = validate_rule_mapping(
                data,
                path=path,
                rule_name=str(rule_name),
                expected_panel_id=report.panel_id,
            )
            report.files.append(file_report)
            report.issues.extend(file_report.issues)

            if file_report.ok:
                rule_id = file_report.rule_id
                owner = seen_rule_ids.get(rule_id)
                if owner and owner != file_report.path:
                    report.issues.append(
                        RuleValidationIssue(
                            level="ERROR",
                            code="RULE_ID_DUPLICATED",
                            message=f"rule_id {rule_id!r} is declared more than once.",
                            path=file_report.path,
                            rule_name=file_report.rule_name,
                            rule_id=rule_id,
                            hint=f"Already declared in {owner}.",
                        )
                    )
                else:
                    seen_rule_ids[rule_id] = file_report.path

        return report


def load_rule_package(panel_package: Any) -> RulePackageReport:
    """Convenience wrapper for loading one panel package's rule files."""
    return RulePackageLoader().load_package(panel_package)


def _is_panel_rule(panel_package: Any, raw_path: str) -> bool:
    path = Path(str(raw_path or ""))
    if path.is_absolute():
        return False
    if not path.parts:
        return False
    if path.parts[0] != "rules":
        return False
    try:
        resolved = panel_package._resolve_path(str(path))
        Path(resolved).resolve().relative_to(Path(panel_package.root_dir).resolve())
        return True
    except Exception:
        return False


def _sha256_file(path: str | Path) -> str:
    try:
        return sha256(Path(path).read_bytes()).hexdigest()
    except Exception:
        return ""
