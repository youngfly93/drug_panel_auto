"""Request-scoped targeted-drug rules resolved from a panel package."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from reportgen.panels.loader import PanelPackageLoader
from reportgen.knowledge.governance import effective_governance
from reportgen.rules.schema import load_rule_yaml


_PANEL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ClinicalContextDecision:
    """Fail-closed decision for one context-bounded treatment rule."""

    eligible: bool
    reasons: tuple[str, ...] = ()


def evaluate_required_clinical_context(
    rule: Mapping[str, Any],
    *,
    clinical_context: Optional[Mapping[str, Any]],
    contract: Optional[Mapping[str, Any]],
) -> ClinicalContextDecision:
    """Evaluate one rule's structured treatment-eligibility context.

    Rules without ``required_context_fields`` retain existing behaviour.
    Context-bounded rules are rejected when the contract, a rule-level scope,
    or a patient value is missing, invalid, uncertain, or outside the reviewed
    rule scope.  This function never infers a value from free-text diagnosis.
    """

    raw_required = rule.get("required_context_fields")
    if isinstance(raw_required, str):
        required_fields = [raw_required.strip()] if raw_required.strip() else []
    elif isinstance(raw_required, (list, tuple, set)):
        required_fields = [
            str(field).strip() for field in raw_required if str(field).strip()
        ]
    else:
        required_fields = []
    if not required_fields:
        return ClinicalContextDecision(eligible=True)

    if not isinstance(contract, Mapping):
        return ClinicalContextDecision(
            eligible=False,
            reasons=("CONTEXT_CONTRACT_MISSING",),
        )
    field_contracts = contract.get("fields")
    if not isinstance(field_contracts, Mapping):
        return ClinicalContextDecision(
            eligible=False,
            reasons=("CONTEXT_CONTRACT_FIELDS_MISSING",),
        )
    requirements = rule.get("context_requirements")
    if not isinstance(requirements, Mapping):
        return ClinicalContextDecision(
            eligible=False,
            reasons=("RULE_CONTEXT_REQUIREMENTS_MISSING",),
        )

    patient_values = clinical_context if isinstance(clinical_context, Mapping) else {}
    reasons: list[str] = []
    for field in required_fields:
        raw_field_contract = field_contracts.get(field)
        if not isinstance(raw_field_contract, Mapping):
            reasons.append(f"CONTRACT_FIELD_MISSING:{field}")
            continue

        value = str(patient_values.get(field) or "").strip()
        if not value:
            reasons.append(f"CONTEXT_VALUE_MISSING:{field}")
            continue

        allowed_values = {
            str(item).strip()
            for item in (raw_field_contract.get("allowed_values") or [])
            if str(item).strip()
        }
        if allowed_values and value not in allowed_values:
            reasons.append(f"CONTEXT_VALUE_INVALID:{field}")
            continue

        uncertain_values = {
            str(item).strip()
            for item in (raw_field_contract.get("uncertain_values") or [])
            if str(item).strip()
        }
        if value in uncertain_values:
            reasons.append(f"CONTEXT_VALUE_UNCERTAIN:{field}")
            continue

        raw_requirement = requirements.get(field)
        if isinstance(raw_requirement, str):
            accepted_values = (
                {raw_requirement.strip()} if raw_requirement.strip() else set()
            )
        elif isinstance(raw_requirement, (list, tuple, set)):
            accepted_values = {
                str(item).strip() for item in raw_requirement if str(item).strip()
            }
        elif isinstance(raw_requirement, Mapping):
            accepted_values = {
                str(item).strip()
                for item in (raw_requirement.get("allowed_values") or [])
                if str(item).strip()
            }
        else:
            accepted_values = set()
        if not accepted_values:
            reasons.append(f"RULE_CONTEXT_REQUIREMENT_MISSING:{field}")
            continue
        if value not in accepted_values:
            reasons.append(f"CONTEXT_OUT_OF_SCOPE:{field}")

    return ClinicalContextDecision(
        eligible=not reasons,
        reasons=tuple(reasons),
    )


def _partition_rows_by_clinical_context(
    rows: list[dict[str, Any]],
    *,
    clinical_context: Optional[Mapping[str, Any]],
    contract: Optional[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Move context-ineligible runtime rows into the blocking selector set."""

    eligible_rows: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    for row in rows:
        decision = evaluate_required_clinical_context(
            row,
            clinical_context=clinical_context,
            contract=contract,
        )
        if decision.eligible:
            eligible_rows.append(row)
            continue
        blocked = dict(row)
        blocked["_clinical_context_block_reasons"] = list(decision.reasons)
        blocked_rows.append(blocked)
    return eligible_rows, blocked_rows


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def reviewed_variant_transcripts(row: Mapping[str, Any]) -> set[str]:
    """Return exact, version-preserving transcript selectors for one rule."""

    value = row.get("transcript") or row.get("transcripts")
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        return set()
    return {
        str(item).strip().upper()
        for item in values
        if str(item).strip()
    }


def reviewed_variant_transcript_matches(
    row: Mapping[str, Any],
    transcript: Any,
) -> bool:
    """Fail closed when a rule declares a transcript and input does not match.

    Rules that predate transcript selectors keep their historical behaviour.
    When a selector is declared, its accession *and version* are part of the
    reviewed event identity; a missing or version-mismatched runtime value must
    not be inferred from the gene or HGVS fields.
    """

    allowed = reviewed_variant_transcripts(row)
    if not allowed:
        return True
    candidate = str(transcript or "").strip().upper()
    return bool(candidate) and candidate in allowed


def reviewed_variant_selector_specificity(row: Mapping[str, Any]) -> int:
    """Return a stable specificity score for a reviewed variant selector.

    Exact c./p. selectors must outrank a broader gene/class or LoF guard.  A
    transcript-bound selector outranks an otherwise identical c./p. selector,
    but never outranks a selector with an additional exact HGVS component.
    Otherwise a newly added pending gene-level guard can silently suppress an
    older, report-group-reviewed exact variant.  The score is deliberately
    structural: it does not depend on runtime/review status.
    """

    def has_value(*keys: str) -> bool:
        for key in keys:
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                return True
            if isinstance(value, (list, tuple, set)) and any(
                str(item).strip() for item in value
            ):
                return True
        return False

    exact_count = int(has_value("c_hgvs", "cHGVS")) + int(
        has_value("p_hgvs", "pHGVS")
    )
    if exact_count == 0 and has_value("variant_site", "locus"):
        # A structured locus is more specific than a gene/class rule, even
        # when its c./p. components have not yet been split by the caller.
        exact_count = 1
    applicability = str(
        row.get("applicability")
        or row.get("applies_to")
        or row.get("variant_applicability")
        or ""
    ).strip().upper()
    has_bounded_applicability = applicability not in {
        "",
        "ANY",
        "ALL",
        "ANYVARIANT",
    }
    has_level = has_value(
        "variant_level",
        "variant_levels",
        "level",
        "levels",
    )
    has_transcript = has_value("transcript", "transcripts")
    has_gene = has_value("gene", "genes")
    return (
        exact_count * 100
        + int(has_transcript) * 20
        + int(has_bounded_applicability) * 10
        + int(has_level) * 2
        + int(has_gene)
    )


def select_reviewed_variant_rule(
    active_rows: list[dict[str, Any]],
    blocked_rows: list[dict[str, Any]],
    *,
    matches: Callable[[dict[str, Any]], bool],
) -> tuple[Optional[dict[str, Any]], bool]:
    """Select one matching reviewed rule with deterministic fail-closed ties.

    More-specific selectors win regardless of status.  When selectors are
    equally specific, a blocked row wins so an ambiguous duplicate cannot
    reopen a drug conclusion.  Within the same status/specificity, YAML order
    remains stable for backward compatibility.
    """

    best: Optional[dict[str, Any]] = None
    best_blocked = False
    best_score = -1
    for blocked, rows in ((False, active_rows), (True, blocked_rows)):
        for row in rows:
            if not matches(row):
                continue
            score = reviewed_variant_selector_specificity(row)
            if score > best_score or (
                score == best_score and blocked and not best_blocked
            ):
                best = row
                best_blocked = blocked
                best_score = score
    return best, best_blocked


def _gene_overrides(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(gene).strip().upper(): dict(rule)
        for gene, rule in value.items()
        if str(gene).strip() and isinstance(rule, Mapping)
    }


def _as_panel_ids(row: Mapping[str, Any]) -> set[str]:
    """Return an optional allow-list of panel ids declared by a rule row."""
    value = row.get("panel_ids") or row.get("panels") or row.get("panel_id")
    if value is None:
        return set()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        return set()
    return {str(item).strip() for item in values if str(item).strip()}


def _rows_for_panel(
    rows: list[dict[str, Any]], panel_id: str
) -> list[dict[str, Any]]:
    """Keep shared rows and rows explicitly scoped to the request panel."""
    return [
        row
        for row in rows
        if not _as_panel_ids(row) or panel_id in _as_panel_ids(row)
    ]


def _governed_rows(
    raw: Mapping[str, Any], rows: list[dict[str, Any]], *, panel_id: str
) -> list[dict[str, Any]]:
    rows = _rows_for_panel(rows, panel_id)
    if not isinstance(raw.get("governance"), Mapping):
        return rows
    return [
        row
        for row in rows
        if effective_governance(raw, row, "targeted_drug")["runtime_eligible"]
    ]


def _blocked_governed_rows(
    raw: Mapping[str, Any], rows: list[dict[str, Any]], *, panel_id: str
) -> list[dict[str, Any]]:
    """Keep governed non-runtime selectors as explicit fail-closed guards."""
    rows = _rows_for_panel(rows, panel_id)
    if not isinstance(raw.get("governance"), Mapping):
        return []
    return [
        row
        for row in rows
        if not effective_governance(raw, row, "targeted_drug")["runtime_eligible"]
    ]


def _governed_gene_overrides(
    raw: Mapping[str, Any], value: Any
) -> dict[str, dict[str, Any]]:
    rows = _gene_overrides(value)
    if not isinstance(raw.get("governance"), Mapping):
        return rows
    return {
        gene: rule
        for gene, rule in rows.items()
        if effective_governance(
            raw, {"gene": gene, **rule}, "targeted_drug"
        )["runtime_eligible"]
    }


def _load_clinical_context_contract(
    panel_package: Any,
    policy: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    """Load the non-patient context schema named by a targeted-drug policy."""

    inline = policy.get("clinical_context_contract")
    if isinstance(inline, Mapping):
        return dict(inline)

    rule_name = str(policy.get("clinical_context_rule") or "").strip()
    if not rule_name:
        return None
    try:
        path = panel_package.resolve_rule_file(rule_name)
        raw = load_rule_yaml(path)
    except Exception:
        return None
    contract = raw.get("clinical_context_contract")
    return dict(contract) if isinstance(contract, Mapping) else None


def _disabled_context(panel_id: str, *, reason: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "base_db_enabled": False,
        "allowed_source_dbs": [],
        "allow_internal_rows": False,
        "require_cancer_profile_match": True,
        "approved_drug_rows_enabled": False,
        "summary_display_scope": "drug_matched_variants",
        "summary_display_variant_levels": ["Ⅰ类", "Ⅱ类"],
        "panel_id": panel_id,
        "source_panel_id": panel_id,
        "shared": False,
        "reason": reason,
        "overrides": {},
        "reviewed_variant_overrides": [],
        "blocked_reviewed_variant_overrides": [],
        "applicability_rules": [],
        "clinical_context_contract": {},
        "clinical_context_enforced": False,
    }


def load_targeted_drug_rule_context(
    panel_package: Any,
    *,
    clinical_context: Optional[Mapping[str, Any]] = None,
    _visited: Optional[set[str]] = None,
) -> Optional[dict[str, Any]]:
    """Load the current panel's targeted-drug policy without mutable globals.

    ``None`` deliberately means legacy/no-panel mode. An explicit package that
    does not declare an enabled policy returns a disabled context, so it can
    never fall back to CRC rules by accident.
    """

    if panel_package is None:
        return None

    panel_id = str(getattr(panel_package, "panel_id", "") or "").strip()
    if not panel_id:
        return _disabled_context("", reason="panel_id_missing")

    visited = set(_visited or set())
    if panel_id in visited:
        raise ValueError(f"targeted-drug rule inheritance cycle: {panel_id}")
    visited.add(panel_id)

    try:
        drugs_path = panel_package.resolve_rule_file("drugs")
        raw = load_rule_yaml(drugs_path)
    except Exception:
        return _disabled_context(panel_id, reason="drugs_rule_unavailable")

    policy = raw.get("targeted_drug_rules") if isinstance(raw, Mapping) else None
    if not isinstance(policy, Mapping):
        return _disabled_context(panel_id, reason="policy_not_declared")
    if not bool(policy.get("enabled", False)):
        return _disabled_context(panel_id, reason="policy_disabled")

    source_panel_id = str(policy.get("source_panel_id") or "").strip()
    if source_panel_id and source_panel_id != panel_id:
        if not _PANEL_ID_RE.fullmatch(source_panel_id):
            raise ValueError(
                f"invalid targeted-drug source_panel_id: {source_panel_id!r}"
            )
        project_root = Path(panel_package.root_dir).resolve().parent.parent
        source_package = PanelPackageLoader(project_root=project_root).load(
            source_panel_id
        )
        inherited = load_targeted_drug_rule_context(
            source_package,
            clinical_context=clinical_context,
            _visited=visited,
        )
        if not inherited or not inherited.get("enabled"):
            return _disabled_context(
                panel_id,
                reason=f"source_panel_disabled:{source_panel_id}",
            )
        return {
            **inherited,
            "panel_id": panel_id,
            "source_panel_id": source_panel_id,
            "shared": True,
            "reviewed_variant_overrides": _rows_for_panel(
                list(inherited.get("reviewed_variant_overrides") or []), panel_id
            ),
            "blocked_reviewed_variant_overrides": _rows_for_panel(
                list(inherited.get("blocked_reviewed_variant_overrides") or []),
                panel_id,
            ),
        }

    context_contract = _load_clinical_context_contract(panel_package, policy)
    active_rows = _governed_rows(
        raw,
        _dict_rows(policy.get("reviewed_variant_overrides")),
        panel_id=panel_id,
    )
    active_rows, context_blocked_rows = _partition_rows_by_clinical_context(
        active_rows,
        clinical_context=clinical_context,
        contract=context_contract,
    )
    blocked_rows = _blocked_governed_rows(
        raw,
        _dict_rows(policy.get("reviewed_variant_overrides")),
        panel_id=panel_id,
    )
    blocked_rows.extend(context_blocked_rows)

    return {
        "enabled": True,
        "base_db_enabled": bool(policy.get("base_db_enabled", False)),
        "allowed_source_dbs": sorted(
            {
                str(source).strip().upper()
                for source in (policy.get("allowed_source_dbs") or [])
                if str(source).strip()
            }
        ),
        "allow_internal_rows": bool(policy.get("allow_internal_rows", False)),
        "require_cancer_profile_match": bool(
            policy.get("require_cancer_profile_match", False)
        ),
        "approved_drug_rows_enabled": bool(
            policy.get("approved_drug_rows_enabled", False)
        ),
        "summary_display_scope": str(
            policy.get("summary_display_scope") or "drug_matched_variants"
        ).strip().lower(),
        "summary_display_variant_levels": [
            str(level).strip()
            for level in (
                policy.get("summary_display_variant_levels") or ["Ⅰ类", "Ⅱ类"]
            )
            if str(level).strip()
        ],
        "panel_id": panel_id,
        "source_panel_id": panel_id,
        "shared": False,
        "reason": "",
        "overrides": _governed_gene_overrides(
            raw,
            policy.get("overrides") or policy.get("gene_overrides")
        ),
        "reviewed_variant_overrides": active_rows,
        "blocked_reviewed_variant_overrides": blocked_rows,
        "applicability_rules": _dict_rows(
            policy.get("applicability_rules")
            or policy.get("targeted_drug_applicability_rules")
        ),
        "clinical_context_contract": context_contract or {},
        "clinical_context_enforced": bool(context_contract),
    }
