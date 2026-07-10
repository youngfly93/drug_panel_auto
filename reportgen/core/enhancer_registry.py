"""
Panel enhancer registry.

Dispatches report enhancement to the correct panel-specific enhancer
based on detected project type, decoupling the orchestrator from any
single panel implementation.
"""

from importlib import import_module
from pathlib import Path
from typing import Any, Optional, Protocol

from reportgen.models.report_data import ReportData
from reportgen.panels.loader import PanelPackageLoader
from reportgen.panels.registry import PanelRegistry, UnknownPanelError
from reportgen.panels.validation import validate_panel_registry


class PanelEnhancer(Protocol):
    """Protocol for panel-specific report enhancers."""

    def enhance(
        self,
        report_data: ReportData,
        excel_data: Any,
        *,
        field_mapper: Any = None,
        gene_knowledge_provider: Any = None,
        base_path: Optional[str] = None,
        project_type: Optional[str] = None,
        panel_package: Any = None,
    ) -> ReportData: ...


class NoopEnhancer:
    """Pass-through enhancer that returns data unchanged.

    Used only when the caller has not supplied a project type or for explicitly
    registered non-CRC legacy project types.
    """

    def enhance(
        self,
        report_data: ReportData,
        excel_data: Any,
        *,
        field_mapper: Any = None,
        gene_knowledge_provider: Any = None,
        base_path: Optional[str] = None,
        project_type: Optional[str] = None,
        panel_package: Any = None,
    ) -> ReportData:
        return report_data


class CRC358Enhancer:
    """CRC 358/301 panel enhancer.

    Delegates to ``template_bridge_358.enhance_report_data()``.
    Uses lazy import to avoid circular dependencies.
    """

    def enhance(
        self,
        report_data: ReportData,
        excel_data: Any,
        *,
        field_mapper: Any = None,
        gene_knowledge_provider: Any = None,
        base_path: Optional[str] = None,
        project_type: Optional[str] = None,
        panel_package: Any = None,
    ) -> ReportData:
        from reportgen.core.template_bridge_358 import enhance_report_data

        panel_config_path = None
        if panel_package is not None:
            try:
                panel_config_path = str(panel_package.resolve_rule_file("panel_rules"))
            except Exception:
                panel_config_path = None

        return enhance_report_data(
            report_data,
            excel_data,
            field_mapper=field_mapper,
            gene_knowledge_provider=gene_knowledge_provider,
            base_path=base_path,
            panel_id=project_type,
            panel_config_path=panel_config_path,
            panel_package=panel_package,
        )


_NOOP = NoopEnhancer()
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _build_default_registry() -> PanelRegistry:
    """Build the compatibility registry used by the legacy generator."""
    registry = PanelRegistry()

    crc_enhancer = CRC358Enhancer()
    loaded_packages: set[str] = set()
    validation_report = validate_panel_registry(project_root=_PROJECT_ROOT)
    if not validation_report.ok:
        issue_lines = "\n".join(
            f"- {issue.panel_id or 'registry'} {issue.code}: {issue.message}"
            for issue in validation_report.errors
        )
        raise RuntimeError(f"Panel registry validation failed:\n{issue_lines}")

    for package in PanelPackageLoader(project_root=_PROJECT_ROOT).load_all():
        registry.register(
            package.panel_id,
            _load_enhancer(package.enhancer, fallback=_NOOP),
            aliases=package.aliases,
            package=package,
        )
        loaded_packages.add(package.panel_id)

    if "crc_358_msi" not in loaded_packages:
        registry.register("crc_358_msi", crc_enhancer, aliases=("crc_358",))
    if "crc_301_msi" not in loaded_packages:
        registry.register("crc_301_msi", crc_enhancer, aliases=("crc_301",))

    # Legacy project types still intentionally run without CRC enhancement until
    # they get real panel packages/enhancers.
    if "mlf_result" not in loaded_packages:
        registry.register("mlf_result", _NOOP)
    if "lung_methylation" not in loaded_packages:
        registry.register("lung_methylation", _NOOP)
    return registry


def _load_enhancer(path: str, *, fallback: PanelEnhancer) -> PanelEnhancer:
    """Load an enhancer instance from ``module:attribute`` notation."""
    raw = str(path or "").strip()
    if not raw:
        return fallback
    if raw in {
        "reportgen.core.enhancer_registry:CRC358Enhancer",
        f"{__name__}:CRC358Enhancer",
    }:
        return CRC358Enhancer()

    try:
        module_name, attr_name = raw.split(":", 1)
        attr = getattr(import_module(module_name), attr_name)
        return attr() if isinstance(attr, type) else attr
    except Exception:
        return fallback


_PANEL_REGISTRY = _build_default_registry()


def get_enhancer(project_type: Optional[str] = None) -> PanelEnhancer:
    """Look up the enhancer for a given project type.

    When *project_type* is ``None`` (caller didn't detect or pass a type),
    returns :class:`NoopEnhancer` to avoid注入错误口径的业务逻辑。
    Explicit unknown panel ids raise :class:`UnknownPanelError` instead of
    silently using Noop.
    """
    if not str(project_type or "").strip():
        return _NOOP
    enhancer = _PANEL_REGISTRY.get_enhancer(project_type)
    if enhancer is None:
        raise UnknownPanelError(f"未注册的Panel项目类型: {project_type!r}")
    return enhancer


def register_enhancer(project_type: str, enhancer: PanelEnhancer) -> None:
    """Register a custom enhancer for a project type."""
    _PANEL_REGISTRY.register(project_type, enhancer)


def normalize_project_type(project_type: Optional[str]) -> Optional[str]:
    """Normalize a project type alias to the canonical panel id."""
    return _PANEL_REGISTRY.normalize(project_type, strict=True)


def is_registered_project_type(project_type: Optional[str]) -> bool:
    """Return whether the project type is known to the panel registry."""
    return _PANEL_REGISTRY.is_registered(project_type)


def get_registered_project_types() -> list[str]:
    """Return canonical project types registered for enhancement dispatch."""
    return _PANEL_REGISTRY.panel_ids()


def get_panel_registry() -> PanelRegistry:
    """Return the process-level panel registry."""
    return _PANEL_REGISTRY


__all__ = [
    "CRC358Enhancer",
    "NoopEnhancer",
    "PanelEnhancer",
    "UnknownPanelError",
    "get_enhancer",
    "get_panel_registry",
    "get_registered_project_types",
    "is_registered_project_type",
    "normalize_project_type",
    "register_enhancer",
]
