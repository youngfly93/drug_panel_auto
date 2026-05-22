"""Panel package loading primitives."""

from reportgen.panels.loader import (
    PanelPackage,
    PanelPackageLoader,
    PanelTemplate,
    load_panel_package,
)
from reportgen.panels.registry import (
    PanelRegistration,
    PanelRegistry,
    UnknownPanelError,
)
from reportgen.panels.validation import (
    PanelPackageValidator,
    PanelValidationIssue,
    PanelValidationReport,
    validate_panel_package,
    validate_panel_package_path,
    validate_panel_registry,
)

__all__ = [
    "PanelPackage",
    "PanelPackageLoader",
    "PanelRegistration",
    "PanelRegistry",
    "PanelTemplate",
    "PanelPackageValidator",
    "PanelValidationIssue",
    "PanelValidationReport",
    "UnknownPanelError",
    "load_panel_package",
    "validate_panel_package",
    "validate_panel_package_path",
    "validate_panel_registry",
]
