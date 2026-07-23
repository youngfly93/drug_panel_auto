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

from docx import Document


ROOT = Path(__file__).resolve().parents[1]
KNOWN_INPUTS = {
    "267a8cbab4d112ea38660dcb1734bb4fb3a7269f50abed6d83a9bf1262ee5646": {
        "alias": "CASE-LUNG-A",
        "contract_id": "case_lung_a",
        "pdl1_tps": 1.0,
        "pdl1_cps": 1.0,
        "pdl1_result": "阳性（低表达）",
    },
    "623c96cee1eb7b16cacb62cababba3b790e82007a00a59d0f159efbe025db000": {
        "alias": "CASE-LUNG-B",
        "contract_id": "case_lung_b",
        "pdl1_tps": 50.0,
        "pdl1_cps": 52.0,
        "pdl1_result": "阳性（高表达）",
    },
    "7b39431044c4a9298f7663c97a47c4df83b5b1e0875d88a64b3e24c05bfa498a": {
        "alias": "CASE-LUNG-C",
        "contract_id": "case_lung_c",
        "pdl1_tps": 5.0,
        "pdl1_cps": 6.0,
        "pdl1_result": "阳性（低表达）",
    },
}
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _safe_variant_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "gene": row.get("gene"),
            "cHGVS": row.get("cHGVS"),
            "pHGVS": row.get("pHGVS"),
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
    }


def _enhance_case(bridge, excel_data, case: dict[str, Any]) -> dict[str, Any]:
    from reportgen.core.context_contract import (
        check_context_contract,
        load_context_contract,
    )
    from reportgen.core.enhancer_registry import get_enhancer, get_panel_registry
    from reportgen.core.report_generator import validate_panel_biomarker_contracts
    from reportgen.models.excel_data import ExcelDataSource

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
    biomarker_failures = validate_panel_biomarker_contracts(
        report_data,
        package.input_contract.get("biomarkers"),
    )
    context = report_data.get_template_context()
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
            "本病例未提供可追溯的PD-L1免疫组化图像",
        )
        forbidden_texts = (
            "__PART3_MARKER__",
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
    for digest, case in sorted(
        KNOWN_INPUTS.items(),
        key=lambda item: item[1]["alias"],
    ):
        excel_path = located[digest]
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
            result = _enhance_case(bridge, excel_data, case)
            report_generation = (
                _render_case(
                    bridge,
                    excel_path,
                    case,
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
        if row["auto_detection"]["detected"]:
            failures.append(f"{row['alias']}: untrusted filename auto-detected")
        if row["targeted_drug_count"] != 0:
            failures.append(f"{row['alias']}: disabled drug rules produced rows")
        if row["biomarker_contract_status"] != "PASS":
            failures.append(f"{row['alias']}: biomarker contract failed")
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
