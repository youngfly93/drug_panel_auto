"""Safety contracts for the CRC358-only production release scope."""

from pathlib import Path

from reportgen.core.report_generator import ReportGenerator
from reportgen.panels.loader import PanelPackageLoader
from reportgen.panels.release_scope import (
    PanelReleaseDisabledError,
    disabled_project_types,
    ensure_project_type_enabled,
)
from reportgen.rules.targeted_drugs import load_targeted_drug_rule_context

ROOT = Path(__file__).resolve().parents[2]


def test_release_scope_parser_and_guard_are_fail_closed(monkeypatch):
    monkeypatch.setenv(
        "REPORTGEN_DISABLED_PROJECT_TYPES",
        "crc_301_msi; demo_panel",
    )

    assert disabled_project_types() == {"crc_301_msi", "demo_panel"}
    assert ensure_project_type_enabled("crc_358_msi") == "crc_358_msi"
    try:
        ensure_project_type_enabled("crc_301_msi")
    except PanelReleaseDisabledError as exc:
        assert "未开放生产生成" in str(exc)
    else:
        raise AssertionError("disabled panel was not rejected")


def test_report_generator_blocks_crc301_before_reading_input(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTGEN_DISABLED_PROJECT_TYPES", "crc_301_msi")
    generator = ReportGenerator(
        config_dir=str(ROOT / "config"),
        template_dir=str(ROOT / "templates"),
        log_level="ERROR",
    )

    result = generator.generate(
        excel_file=str(tmp_path / "does-not-exist.xlsx"),
        template_file=str(tmp_path / "does-not-exist.docx"),
        output_dir=str(tmp_path / "output"),
        project_type="crc_301_msi",
    )

    assert result["success"] is False
    assert result["output_file"] is None
    assert any("未开放生产生成" in error for error in result["errors"])
    assert not any(
        row["name"] == "ExcelReadStage" for row in result["stage_results"]
    )


def test_pending_crc358_selectors_remain_visible_but_not_runtime_eligible():
    package = PanelPackageLoader(project_root=ROOT).load("crc_358_msi")
    context = load_targeted_drug_rule_context(package)

    assert context is not None and context["enabled"] is True
    pending = [
        row
        for row in context["blocked_reviewed_variant_overrides"]
        if row.get("secondary_review_status")
        == "pending_report_group_secondary_review"
    ]
    assert len(pending) == 14
    assert not any(
        row.get("secondary_review_status")
        == "pending_report_group_secondary_review"
        for row in context["reviewed_variant_overrides"]
    )
