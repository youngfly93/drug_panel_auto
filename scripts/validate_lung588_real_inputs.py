#!/usr/bin/env python3
# 步骤: 71 肺癌588真实输入脱敏契约验证
# 上游: 外部受控肺癌Excel、panels/lung_588_pdl1/context_contracts/
# 输出: .work/lung588_real_input_audit/validation.json
# 种子: 无（确定性字段映射与契约比对）
"""Validate local lung588 inputs without writing patient identifiers to artifacts."""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from docx import Document
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
KNOWN_INPUTS = {
    "267a8cbab4d112ea38660dcb1734bb4fb3a7269f50abed6d83a9bf1262ee5646": {
        "alias": "CASE-LUNG-A",
        "contract_id": "case_lung_a",
        "pdl1_tps": 1.0,
        "pdl1_cps": 1.0,
        "pdl1_result": "阳性（低表达）",
        "expected_targeted_drug_count": 0,
        "expected_immune_positive_count": 0,
        "expected_immune_negative_count": 0,
    },
    "623c96cee1eb7b16cacb62cababba3b790e82007a00a59d0f159efbe025db000": {
        "alias": "CASE-LUNG-B",
        "contract_id": "case_lung_b",
        "pdl1_tps": 50.0,
        "pdl1_cps": 52.0,
        "pdl1_result": "阳性（高表达）",
        "expected_targeted_drug_count": 0,
        "expected_immune_positive_count": 5,
        "expected_immune_negative_count": 0,
    },
    "7b39431044c4a9298f7663c97a47c4df83b5b1e0875d88a64b3e24c05bfa498a": {
        "alias": "CASE-LUNG-C",
        "contract_id": "case_lung_c",
        "pdl1_tps": 5.0,
        "pdl1_cps": 6.0,
        "pdl1_result": "阳性（低表达）",
        "expected_targeted_drug_count": 2,
        "expected_immune_positive_count": 2,
        "expected_immune_negative_count": 1,
    },
}
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
UAT_POLICY_PATH = (
    ROOT
    / "panels"
    / "lung_588_pdl1"
    / "uat"
    / "lung588_risk_based_release_policy.yaml"
)
REPORT_GROUP_UAT_DECISIONS_PATH = (
    ROOT
    / "panels"
    / "lung_588_pdl1"
    / "uat"
    / "lung588_report_group_uat_decisions.yaml"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_synthetic_pdl1_image(path: Path, alias: str) -> None:
    """Create a deterministic non-clinical image used only for render QA."""

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (960, 640), "white")
    draw = ImageDraw.Draw(image)
    digest = hashlib.sha256(alias.encode("utf-8")).digest()
    for index in range(80):
        x = (digest[index % len(digest)] * 37 + index * 61) % 920
        y = (digest[(index + 7) % len(digest)] * 29 + index * 43) % 600
        radius = 8 + digest[(index + 13) % len(digest)] % 18
        shade = 75 + digest[(index + 17) % len(digest)] % 120
        draw.ellipse(
            (x, y, x + radius, y + radius),
            fill=(shade, 70, min(220, shade + 35)),
        )
    draw.rectangle((10, 10, 949, 629), outline=(80, 80, 80), width=3)
    image.save(path, format="PNG", optimize=True)


def _source_revision() -> str:
    """Return a quiet immutable source identity in Git and release archives."""

    configured = str(os.environ.get("REPORTGEN_SOURCE_REVISION") or "").strip()
    if COMMIT_RE.fullmatch(configured):
        return configured

    revision_file = ROOT / "REVISION"
    if revision_file.is_file():
        lines = revision_file.read_text(encoding="utf-8").strip().splitlines()
        revision = lines[0] if lines else ""
        if COMMIT_RE.fullmatch(revision):
            return revision

    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    revision = completed.stdout.strip()
    return (
        revision if completed.returncode == 0 and COMMIT_RE.fullmatch(revision) else ""
    )


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected a mapping in {path}")
    return payload


def _load_uat_release_policy(path: Path = UAT_POLICY_PATH) -> dict[str, Any]:
    policy = _load_yaml_mapping(path)
    case_policy = policy.get("real_case_policy")
    if not isinstance(case_policy, dict):
        raise RuntimeError("lung588 UAT policy is missing real_case_policy")
    if case_policy.get("fixed_minimum_real_case_count") is not None:
        raise RuntimeError(
            "lung588 risk-based UAT policy must not restore a fixed case count"
        )
    for key in ("required_review_fraction", "required_pass_fraction"):
        value = case_policy.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or float(value) != 1.0
        ):
            raise RuntimeError(f"lung588 UAT policy has invalid {key}: {value!r}")
    if not case_policy.get("require_non_empty_case_set"):
        raise RuntimeError("lung588 UAT policy must require a non-empty real case set")
    return policy


def _load_report_group_uat_decisions(
    path: Path = REPORT_GROUP_UAT_DECISIONS_PATH,
    *,
    expected_policy_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    payload = _load_yaml_mapping(path)
    if expected_policy_id and payload.get("policy_id") != expected_policy_id:
        raise RuntimeError(
            "lung588 report-group UAT register does not match the active policy"
        )
    decisions: dict[str, dict[str, Any]] = {}
    for item in payload.get("cases") or []:
        if not isinstance(item, dict):
            raise RuntimeError("lung588 report-group UAT case entry must be a mapping")
        alias = str(item.get("alias") or "").strip()
        decision = str(item.get("decision") or "").strip().lower()
        if not alias:
            raise RuntimeError("lung588 report-group UAT case alias is required")
        if alias in decisions:
            raise RuntimeError(f"duplicate lung588 report-group UAT alias: {alias}")
        if decision not in {"pass", "fail", "pending"}:
            raise RuntimeError(
                f"invalid lung588 report-group UAT decision for {alias}: {decision!r}"
            )
        p0_count = item.get("p0_count")
        if decision in {"pass", "fail"} and (
            isinstance(p0_count, bool)
            or not isinstance(p0_count, int)
            or p0_count < 0
        ):
            raise RuntimeError(
                f"completed lung588 UAT decision for {alias} requires p0_count"
            )
        decisions[alias] = {
            "decision": decision,
            "reviewer": str(item.get("reviewer") or "").strip(),
            "reviewed_at": str(item.get("reviewed_at") or "").strip(),
            "p0_count": p0_count,
        }
    return decisions


def _safe_variant_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "gene": row.get("gene"),
            "transcript": row.get("transcript"),
            "chromosome": row.get("chromosome"),
            "exon": row.get("exon"),
            "cHGVS": row.get("cHGVS"),
            "pHGVS": row.get("pHGVS"),
            "mutation_type": row.get("mutation_type"),
            "gene_class": row.get("gene_class"),
            "frequency": row.get("frequency"),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def _clinical_info(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "patient_name": case["alias"],
        "sample_id": case["alias"],
        "report_number": case["alias"],
        "project_name": "肺癌588基因+PD-L1",
        "clinical_diagnosis": "肺癌（脱敏验证）",
        "report_date": "2026-07-23",
        "pdl1_tps": case["pdl1_tps"],
        "pdl1_cps": case["pdl1_cps"],
        "pdl1_result": case["pdl1_result"],
        "pdl1_image_path": str(case["pdl1_image_path"]),
        "pdl1_assay_profile_id": ("legacy_unspecified_ihc_transcription_v1"),
        "pdl1_source_record_id": (f"SYNTHETIC-VISUAL-QA-IHC-{case['alias']}"),
        "pdl1_source_record_date": "2026-07-23",
        "pdl1_specimen_id": (f"SYNTHETIC-VISUAL-QA-SPECIMEN-{case['alias']}"),
        "pdl1_image_disposition": "病例专属图像（报告展示）",
        "lung_histology": "非小细胞肺癌",
        "disease_extent": "转移性",
        "prior_systemic_therapy": "已接受",
        "companion_diagnostic_status": "已确认符合",
    }


def _enhance_case(bridge, excel_data, case: dict[str, Any]) -> dict[str, Any]:
    from reportgen.core.context_contract import (
        check_context_contract,
        load_context_contract,
    )
    from reportgen.core.enhancer_registry import get_enhancer, get_panel_registry
    from reportgen.core.report_generator import validate_panel_biomarker_contracts
    from reportgen.core.report_summary import build_report_summary
    from reportgen.models.excel_data import ExcelDataSource
    from reportgen.rules.pdl1 import (
        apply_pdl1_product_display_fields,
        load_pdl1_product_contract,
        validate_pdl1_product_contract,
    )

    working = ExcelDataSource(
        file_path=excel_data.file_path,
        single_values=copy.deepcopy(excel_data.single_values or {}),
        table_data=copy.deepcopy(excel_data.table_data or {}),
        sheet_names=list(excel_data.sheet_names or []),
        metadata=copy.deepcopy(excel_data.metadata or {}),
    )
    clinical_info = _clinical_info(case)
    bridge._inject_clinical_info_into_excel(working, clinical_info)
    registration = get_panel_registry().get("lung_588_pdl1")
    package = registration.package
    report_data = bridge.field_mapper.map(working, panel_package=package)
    report_data = bridge.data_cleaner.validate_and_clean(report_data)
    part3_policy = package.raw.get("part3_knowledge") or {}
    gene_knowledge_provider = (
        bridge._build_gene_knowledge_provider()
        if part3_policy.get("enabled", True)
        else None
    )
    report_data = get_enhancer("lung_588_pdl1").enhance(
        report_data,
        working,
        field_mapper=bridge.field_mapper,
        gene_knowledge_provider=gene_knowledge_provider,
        base_path=str(ROOT),
        project_type="lung_588_pdl1",
        panel_package=package,
    )
    pdl1_product_contract = load_pdl1_product_contract(package)
    apply_pdl1_product_display_fields(
        report_data,
        pdl1_product_contract,
    )
    biomarker_failures = validate_panel_biomarker_contracts(
        report_data,
        package.input_contract.get("biomarkers"),
    )
    pdl1_product_failures = validate_pdl1_product_contract(
        report_data,
        pdl1_product_contract,
    )
    context = report_data.get_template_context()
    web_summary = build_report_summary(
        report_data=report_data,
        project_type="lung_588_pdl1",
        project_name="肺癌588基因+PD-L1",
    )
    contract_report = None
    contract_id = case.get("contract_id")
    if contract_id:
        contract_path = package.resolve_context_contract_file(contract_id)
        contract_report = check_context_contract(
            context,
            load_context_contract(contract_path),
            contract_path=contract_path,
        )
    return {
        "variant_rows": _safe_variant_rows(
            list(report_data.get_table("all_variants") or [])
        ),
        "targeted_drug_count": len(
            list(report_data.get_table("targeted_drug_tips") or [])
        ),
        "immune_positive_count": len(
            list(report_data.get_table("immune_positive_variants") or [])
        ),
        "immune_negative_count": len(
            list(report_data.get_table("immune_negative_variants") or [])
        ),
        "biomarkers": {
            "tmb_value": report_data.get_field("tmb_value"),
            "tmb_status": report_data.get_field("tmb_status"),
            "msi_status": report_data.get_field("msi_status"),
            "pdl1_tps": report_data.get_field("pdl1_tps"),
            "pdl1_cps": report_data.get_field("pdl1_cps"),
            "pdl1_result": report_data.get_field("pdl1_result"),
        },
        "biomarker_contract_status": "PASS" if not biomarker_failures else "FAIL",
        "biomarker_failures": biomarker_failures,
        "pdl1_product_contract_status": (
            "PASS" if not pdl1_product_failures else "FAIL"
        ),
        "pdl1_product_failures": pdl1_product_failures,
        "pdl1_input_provenance": "synthetic_visual_qa_only",
        "web_preview": {
            "drug_related_variant_count": web_summary["variants"]["drug_related"],
            "targeted_drug_count": web_summary["drugs"]["targeted_count"],
            "targeted_module_status": web_summary["drugs"]["targeted_status"],
            "immune": web_summary["biomarkers"]["immune"],
        },
        "context_contract": {
            "contract_id": contract_id,
            "status": contract_report["status"]
            if contract_report
            else "NOT_APPLICABLE",
            "summary": contract_report["summary"] if contract_report else {},
        },
    }


def _render_case(
    bridge,
    excel_path: Path,
    case: dict[str, Any],
    output_dir: Path,
    *,
    dpi: int,
) -> dict[str, Any]:
    result = bridge.generate_report(
        str(excel_path),
        str(output_dir),
        clinical_info=_clinical_info(case),
        project_type="lung_588_pdl1",
        project_name="肺癌588基因+PD-L1",
        strict_mode=False,
        template_contract_mode="fail",
        qa_visual_render="all",
        qa_visual_render_required=True,
        qa_visual_render_dpi=dpi,
        qa_visual_render_timeout_seconds=180,
    )
    output_file = Path(str(result.get("output_file") or ""))
    qa_path = output_file.with_suffix(".qa.json") if output_file.name else None
    qa_payload: dict[str, Any] = {}
    if qa_path is not None and qa_path.is_file():
        qa_payload = json.loads(qa_path.read_text(encoding="utf-8"))
    visual = (qa_payload.get("checks") or {}).get("visual_render") or {}
    pixel = visual.get("pixel_check") or {}

    content_failures: list[str] = []
    if output_file.is_file():
        document = Document(output_file)
        visible = "\n".join(
            [paragraph.text for paragraph in document.paragraphs]
            + [
                cell.text
                for table in document.tables
                for row in table.rows
                for cell in row.cells
            ]
        )
        required_texts = (
            "Gene List for MLseq (n=588)",
            "肺癌专属知识当前未启用",
            "图1. 免疫组化：PD-L1",
        )
        forbidden_texts = (
            "__PART3_MARKER__",
            "__PDL1_CASE_IMAGE__",
            "原始记录未提供抗体克隆",
            "不据此推导检测方案等效性",
            "n=329",
            "{{",
            "{%",
            "colorectal",
            "colon cancer",
            "结直肠癌",
            "工程草案",
            "报告组二审",
            "报告组复核",
            "脱敏UAT",
            "待报告组审核",
        )
        content_failures.extend(
            f"missing:{text}" for text in required_texts if text not in visible
        )
        lowered = visible.lower()
        content_failures.extend(
            f"forbidden:{text}" for text in forbidden_texts if text.lower() in lowered
        )
    else:
        content_failures.append("output_missing")

    blank_pages = list(pixel.get("blank_pages") or [])
    low_content_pages = list(pixel.get("unexpected_low_content_pages") or [])
    status = (
        "PASS"
        if result.get("success")
        and result.get("qa_status") == "PASS"
        and qa_payload.get("status") == "PASS"
        and not blank_pages
        and not low_content_pages
        and not content_failures
        else "FAIL"
    )
    return {
        "status": status,
        "output_alias": output_file.name,
        "qa_status": qa_payload.get("status") or result.get("qa_status"),
        "page_count": pixel.get("checked_pages"),
        "blank_page_count": len(blank_pages),
        "unexpected_low_content_page_count": len(low_content_pages),
        "content_failures": content_failures,
        "error_count": len(result.get("errors") or []),
    }


def _build_uat_readiness(
    rows: list[dict[str, Any]],
    *,
    policy: dict[str, Any] | None = None,
    report_group_decisions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate every available real case without a fixed numeric denominator."""

    policy = policy or _load_uat_release_policy()
    case_policy = policy["real_case_policy"]
    report_group_decisions = (
        report_group_decisions
        if report_group_decisions is not None
        else _load_report_group_uat_decisions(
            expected_policy_id=str(policy["policy_id"])
        )
    )
    aliases = [str(row.get("alias") or "").strip() for row in rows]
    ngs_structure_pass_count = sum(
        row["auto_detection"]["detected"]
        and row["auto_detection"]["project_type"] == "lung_588_pdl1"
        and row.get("targeted_drug_count", 0)
        == row.get("expected_targeted_drug_count", 0)
        and row.get("immune_positive_count", 0)
        == row.get("expected_immune_positive_count", 0)
        and row.get("immune_negative_count", 0)
        == row.get("expected_immune_negative_count", 0)
        and row["biomarker_contract_status"] == "PASS"
        and row["context_contract"]["status"] in {"PASS", "NOT_APPLICABLE"}
        for row in rows
    )
    pdl1_product_pass_count = sum(
        row["pdl1_product_contract_status"] == "PASS" for row in rows
    )
    verified_case_pdl1_source_count = sum(
        row["pdl1_input_provenance"] == "case_specific_verified_ihc_source"
        for row in rows
    )
    missing_case_alias_count = sum(not alias for alias in aliases)
    missing_decision_aliases = [
        alias
        for alias in aliases
        if alias and alias not in report_group_decisions
    ]
    complete_decisions = {
        alias: report_group_decisions[alias]
        for alias in aliases
        if alias in report_group_decisions
        and report_group_decisions[alias]["decision"] in {"pass", "fail"}
        and report_group_decisions[alias]["reviewer"]
        and report_group_decisions[alias]["reviewed_at"]
        and isinstance(report_group_decisions[alias].get("p0_count"), int)
        and not isinstance(report_group_decisions[alias].get("p0_count"), bool)
    }
    report_group_reviewed_case_count = len(complete_decisions)
    report_group_passed_case_count = sum(
        item["decision"] == "pass" for item in complete_decisions.values()
    )
    report_group_failed_case_count = sum(
        item["decision"] == "fail" for item in complete_decisions.values()
    )
    p0_count = sum(int(item["p0_count"]) for item in complete_decisions.values())
    required_review_case_count = len(rows)
    p0_allowed = int(case_policy.get("p0_allowed", 0))
    blockers: list[dict[str, str]] = []
    if not rows:
        blockers.append(
            {
                "code": "NO_REGISTERED_REAL_CASES",
                "message": "the frozen release has no registered real lung588 cases",
            }
        )
    if missing_case_alias_count:
        blockers.append(
            {
                "code": "REAL_CASE_ALIAS_MISSING",
                "message": f"{missing_case_alias_count} observed cases lack a stable alias",
            }
        )
    if ngs_structure_pass_count != len(rows):
        blockers.append(
            {
                "code": "NGS_STRUCTURE_INCOMPLETE",
                "message": (
                    f"{len(rows) - ngs_structure_pass_count} observed cases "
                    "do not pass the frozen NGS structure contract"
                ),
            }
        )
    if pdl1_product_pass_count != len(rows):
        blockers.append(
            {
                "code": "PDL1_PRODUCT_CONTRACT_BLOCKED",
                "message": (
                    f"{len(rows) - pdl1_product_pass_count} observed cases "
                    "do not pass an enabled PD-L1 product contract"
                ),
            }
        )
    if verified_case_pdl1_source_count != len(rows):
        blockers.append(
            {
                "code": "PDL1_CASE_SOURCE_NOT_VERIFIED",
                "message": (
                    f"{len(rows) - verified_case_pdl1_source_count} observed "
                    "cases use synthetic machine-QA values rather than a "
                    "verified case-specific IHC source"
                ),
            }
        )
    if missing_decision_aliases:
        blockers.append(
            {
                "code": "REPORT_GROUP_UAT_RECORD_MISSING",
                "message": (
                    f"{len(missing_decision_aliases)} observed cases are absent "
                    "from the report-group UAT register"
                ),
            }
        )
    if report_group_reviewed_case_count != required_review_case_count:
        blockers.append(
            {
                "code": "REPORT_GROUP_UAT_INCOMPLETE",
                "message": (
                    f"{report_group_reviewed_case_count}/"
                    f"{required_review_case_count} observed cases have a complete "
                    "report-group UAT decision, reviewer and date"
                ),
            }
        )
    if report_group_failed_case_count:
        blockers.append(
            {
                "code": "REPORT_GROUP_UAT_FAILED",
                "message": (
                    f"{report_group_failed_case_count} observed cases have a "
                    "report-group FAIL decision"
                ),
            }
        )
    if p0_count > p0_allowed:
        blockers.append(
            {
                "code": "P0_DEFECTS_PRESENT",
                "message": f"P0 count {p0_count} exceeds allowed count {p0_allowed}",
            }
        )
    formal_uat_status = "PASS" if not blockers else "BLOCKED"
    return {
        "scope": "risk_based_all_available_real_cases",
        "policy_id": policy["policy_id"],
        "case_set_policy": case_policy["selection"],
        "fixed_minimum_real_case_count": None,
        "observed_real_input_count": len(rows),
        "required_report_group_review_case_count": required_review_case_count,
        "ngs_structure_pass_count": ngs_structure_pass_count,
        "ngs_structure_status": (
            "PASS" if ngs_structure_pass_count == len(rows) else "FAIL"
        ),
        "pdl1_product_pass_count": pdl1_product_pass_count,
        "pdl1_product_status": (
            "PASS" if pdl1_product_pass_count == len(rows) else "BLOCKED"
        ),
        "verified_case_pdl1_source_count": (verified_case_pdl1_source_count),
        "report_group_reviewed_case_count": (report_group_reviewed_case_count),
        "report_group_passed_case_count": report_group_passed_case_count,
        "report_group_failed_case_count": report_group_failed_case_count,
        "p0_count": p0_count,
        "p0_allowed": p0_allowed,
        "formal_uat_status": formal_uat_status,
        "formal_uat_requirement_met": formal_uat_status == "PASS",
        "blockers": blockers,
    }


def validate_inputs(
    input_dir: Path,
    *,
    render_output_dir: Path | None = None,
    render_dpi: int = 120,
) -> dict[str, Any]:
    os.environ["RG_WEB_UPSTREAM_ROOT"] = str(ROOT)
    # This is an offline promotion gate for a draft Panel, not a production
    # service process. Explicitly open the local product so the same script can
    # be run from a shell that inherited iyun129's disabled-panel boundary.
    os.environ["RG_WEB_DISABLED_PROJECT_TYPES"] = ""
    os.environ["REPORTGEN_DISABLED_PROJECT_TYPES"] = ""
    for import_path in (str(ROOT / "backend"), str(ROOT)):
        if import_path not in sys.path:
            sys.path.insert(0, import_path)

    from app.services.reportgen_bridge import ReportGenBridge

    bridge = ReportGenBridge(
        config_dir=str(ROOT / "config"),
        template_dir=str(ROOT / "templates"),
    )
    located: dict[str, Path] = {}
    for path in sorted(input_dir.glob("*.xlsx")):
        if path.name.startswith(("._", "~$")):
            continue
        digest = _sha256(path)
        if digest in KNOWN_INPUTS:
            located[digest] = path

    missing = sorted(set(KNOWN_INPUTS) - set(located))
    if missing:
        raise RuntimeError(
            f"missing {len(missing)} frozen lung588 inputs; hashes only: {missing}"
        )

    rows: list[dict[str, Any]] = []
    synthetic_image_dir = (
        render_output_dir
        if render_output_dir is not None
        else ROOT / ".work" / "lung588_real_input_audit"
    ) / "synthetic_pdl1_images"
    for digest, case in sorted(
        KNOWN_INPUTS.items(),
        key=lambda item: item[1]["alias"],
    ):
        excel_path = located[digest]
        runtime_case = dict(case)
        image_path = synthetic_image_dir / f"{case['alias']}.png"
        _write_synthetic_pdl1_image(image_path, str(case["alias"]))
        runtime_case["pdl1_image_path"] = image_path
        # Upstream loggers may mention real filenames/sample IDs. Capture both
        # streams so this validation emits only the de-identified payload below.
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            excel_data = bridge.read_excel(str(excel_path))
            detected = bridge.detect_project_type(
                str(excel_path), excel_data=excel_data
            )
            result = _enhance_case(bridge, excel_data, runtime_case)
            report_generation = (
                _render_case(
                    bridge,
                    excel_path,
                    runtime_case,
                    render_output_dir,
                    dpi=render_dpi,
                )
                if render_output_dir is not None and case.get("contract_id")
                else {"status": "NOT_RUN"}
            )
        rows.append(
            {
                "alias": case["alias"],
                "source_sha256": digest,
                "expected_targeted_drug_count": case[
                    "expected_targeted_drug_count"
                ],
                "expected_immune_positive_count": case[
                    "expected_immune_positive_count"
                ],
                "expected_immune_negative_count": case[
                    "expected_immune_negative_count"
                ],
                "sheet_count": len(excel_data.sheet_names or []),
                "auto_detection": {
                    "detected": bool(detected.get("detected")),
                    "project_type": detected.get("project_type"),
                },
                **result,
                "report_generation": report_generation,
            }
        )

    failures: list[str] = []
    for row in rows:
        if (
            not row["auto_detection"]["detected"]
            or row["auto_detection"]["project_type"] != "lung_588_pdl1"
        ):
            failures.append(
                f"{row['alias']}: lung588 structural identity was not detected"
            )
        if row["targeted_drug_count"] != row["expected_targeted_drug_count"]:
            failures.append(
                f"{row['alias']}: targeted drug rows differ from the exact-event contract"
            )
        if row["immune_positive_count"] != row["expected_immune_positive_count"]:
            failures.append(
                f"{row['alias']}: positive immune rows differ from the exact-event contract"
            )
        if row["immune_negative_count"] != row["expected_immune_negative_count"]:
            failures.append(
                f"{row['alias']}: negative immune rows differ from the exact-event contract"
            )
        preview = row["web_preview"]
        if preview["targeted_drug_count"] != row["expected_targeted_drug_count"]:
            failures.append(
                f"{row['alias']}: web preview targeted-drug count is inconsistent"
            )
        if preview["drug_related_variant_count"] != row[
            "expected_targeted_drug_count"
        ]:
            failures.append(
                f"{row['alias']}: web preview drug-related variant count is inconsistent"
            )
        positive_result = str(preview["immune"].get("positive") or "")
        negative_result = str(preview["immune"].get("negative") or "")
        if row["expected_immune_positive_count"] and not positive_result.startswith(
            "检出（"
        ):
            failures.append(f"{row['alias']}: web preview lost positive immune hits")
        if not row["expected_immune_positive_count"] and positive_result != "未检出":
            failures.append(f"{row['alias']}: web preview positive immune zero is wrong")
        if row["expected_immune_negative_count"] and not negative_result.startswith(
            "检出（"
        ):
            failures.append(f"{row['alias']}: web preview lost negative immune hits")
        if not row["expected_immune_negative_count"] and negative_result != "未检出":
            failures.append(f"{row['alias']}: web preview negative immune zero is wrong")
        if row["biomarker_contract_status"] != "PASS":
            failures.append(f"{row['alias']}: biomarker contract failed")
        if row["pdl1_product_contract_status"] != "PASS":
            failures.append(f"{row['alias']}: PD-L1 product contract blocked")
        contract_status = row["context_contract"]["status"]
        if contract_status not in {"PASS", "NOT_APPLICABLE"}:
            failures.append(f"{row['alias']}: context contract failed")
        render_status = row["report_generation"]["status"]
        if render_output_dir is not None and row["context_contract"]["contract_id"]:
            if render_status != "PASS":
                failures.append(f"{row['alias']}: rendered report gate failed")
    return {
        "schema_version": "1.0",
        "panel_id": "lung_588_pdl1",
        "status": "FAIL" if failures else "PASS",
        "source_commit": _source_revision(),
        "case_count": len(rows),
        "uat_readiness": _build_uat_readiness(rows),
        "cases": rows,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".work" / "lung588_real_input_audit" / "validation.json",
    )
    parser.add_argument(
        "--render-output-dir",
        type=Path,
        help="Optionally render the two historical gold cases with full visual QA.",
    )
    parser.add_argument("--render-dpi", type=int, default=120)
    args = parser.parse_args()
    render_output_dir = (
        args.render_output_dir.resolve() if args.render_output_dir is not None else None
    )
    if render_output_dir is not None:
        render_output_dir.mkdir(parents=True, exist_ok=True)
    payload = validate_inputs(
        args.input_dir.resolve(),
        render_output_dir=render_output_dir,
        render_dpi=args.render_dpi,
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "case_count": payload["case_count"],
                "variant_counts": {
                    row["alias"]: len(row["variant_rows"]) for row in payload["cases"]
                },
                "contract_statuses": {
                    row["alias"]: row["context_contract"]["status"]
                    for row in payload["cases"]
                },
                "pdl1_product_statuses": {
                    row["alias"]: row["pdl1_product_contract_status"]
                    for row in payload["cases"]
                },
                "uat_readiness": payload["uat_readiness"],
                "render_statuses": {
                    row["alias"]: row["report_generation"]["status"]
                    for row in payload["cases"]
                },
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
