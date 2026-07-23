"""Panel rule loading and validation."""

from reportgen.rules.engine import PanelRuleEngine
from reportgen.rules.loader import (
    RulePackageLoader,
    RulePackageReport,
    load_rule_package,
)
from reportgen.rules.pdl1 import (
    apply_pdl1_product_display_fields,
    load_pdl1_product_contract,
    validate_pdl1_product_contract,
)
from reportgen.rules.schema import (
    RULE_SCHEMA_VERSION,
    RuleFileReport,
    RuleValidationIssue,
    load_rule_yaml,
    validate_rule_mapping,
)

__all__ = [
    "RULE_SCHEMA_VERSION",
    "PanelRuleEngine",
    "RuleFileReport",
    "RulePackageLoader",
    "RulePackageReport",
    "RuleValidationIssue",
    "load_rule_package",
    "load_rule_yaml",
    "load_pdl1_product_contract",
    "validate_pdl1_product_contract",
    "apply_pdl1_product_display_fields",
    "validate_rule_mapping",
]
