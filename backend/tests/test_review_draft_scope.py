# ruff: noqa: E402
"""A passed engineering draft never counts as clinical production promotion."""

import hashlib
import sys
from pathlib import Path

import pytest
import yaml
from docx import Document

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.check_production_panel_scope import (
    REQUIRED_DRAFT_GATES,
    draft_producer_fingerprint,
    validate_scope,
)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, allow_unicode=True))


def synthetic_draft(root):
    panel = root / "panels/test_draft"
    panel.mkdir(parents=True)
    doc = Document()
    doc.add_paragraph("报告组评审草稿（非临床交付）")
    doc.save(panel / "template.docx")
    save(
        panel / "panel.yaml",
        {
            "panel_id": "test_draft",
            "status": "draft",
            "default_template": "draft",
            "templates": [{"id": "draft", "status": "draft", "file": "template.docx"}],
        },
    )
    evidence = {
        "scope": "report_group_review_only",
        "user_authorized": True,
        "producer_sha256": draft_producer_fingerprint(root, "test_draft"),
        "template_sha256": hashlib.sha256((panel / "template.docx").read_bytes()).hexdigest(),
        "case_aliases": ["A", "B", "C"],
        "gates": {
            gate: {"status": "PASS", "receipt_sha256": "a" * 64} for gate in REQUIRED_DRAFT_GATES
        },
    }
    return {
        "panel_id": "test_draft",
        "production_eligible": False,
        "draft_generation_eligible": True,
        "enforced_targets": ["iyun129"],
        "draft_generation_evidence": evidence,
    }


def check(root, manifest, disabled=""):
    save(root / "config/panel_product_readiness/test_draft.yaml", manifest)
    return validate_scope(
        project_root=root,
        target="iyun129",
        web_disabled=disabled,
        core_disabled=disabled,
        frontend_disabled=disabled,
    )


def test_verified_draft_may_open_without_clinical_promotion(tmp_path):
    result = check(tmp_path, synthetic_draft(tmp_path))
    assert result["status"] == "PASS"
    assert result["checked_manifests"][0]["production_eligible"] is False


@pytest.mark.parametrize("gate", REQUIRED_DRAFT_GATES)
def test_unrun_engineering_gate_cannot_be_bypassed(tmp_path, gate):
    manifest = synthetic_draft(tmp_path)
    manifest["draft_generation_evidence"]["gates"][gate]["status"] = "NOT_RUN"
    result = check(tmp_path, manifest)
    assert result["status"] == "FAIL"
    assert any(gate in issue for issue in result["issues"])


def test_producer_edit_invalidates_the_draft_evidence(tmp_path):
    manifest = synthetic_draft(tmp_path)
    source = tmp_path / "reportgen/new_producer.py"
    source.parent.mkdir()
    source.write_text("changed = True\n")
    assert check(tmp_path, manifest)["status"] == "FAIL"


def test_draft_marker_removal_and_active_promotion_are_not_silent(tmp_path):
    manifest = synthetic_draft(tmp_path)
    path = tmp_path / "panels/test_draft/panel.yaml"
    package = yaml.safe_load(path.read_text())
    package["status"] = "active"
    save(path, package)
    result = check(tmp_path, manifest)
    assert result["status"] == "FAIL"
    assert any("requires a draft" in issue for issue in result["issues"])


def test_unvalidated_draft_must_stay_in_all_three_disabled_scopes(tmp_path):
    manifest = synthetic_draft(tmp_path)
    manifest["draft_generation_eligible"] = False
    assert check(tmp_path, manifest)["status"] == "FAIL"
    assert check(tmp_path, manifest, "test_draft")["status"] == "PASS"


def test_clinical_promotion_cannot_reuse_engineering_receipts(tmp_path):
    manifest = synthetic_draft(tmp_path)
    manifest["production_eligible"] = True
    assert check(tmp_path, manifest)["status"] == "FAIL"
