"""Panel package loading primitives."""

from reportgen.panels.loader import (
    PanelPackage,
    PanelPackageLoader,
    PanelTemplate,
    load_panel_package,
)
from reportgen.panels.input_contract import (
    describe_input_contract_failure,
    input_contract_failures_as_missing,
    validate_excel_input_contract,
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
    "describe_input_contract_failure",
    "input_contract_failures_as_missing",
    "validate_excel_input_contract",
    "validate_panel_package",
    "validate_panel_package_path",
    "validate_panel_registry",
]
