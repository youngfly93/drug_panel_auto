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

__all__ = [
    "PanelPackage",
    "PanelPackageLoader",
    "PanelRegistration",
    "PanelRegistry",
    "PanelTemplate",
    "UnknownPanelError",
    "load_panel_package",
]
