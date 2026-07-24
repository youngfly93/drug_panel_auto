#!/usr/bin/env python3
# 步骤: 72 肺癌588受控试运行合成边界报告验证
# 上游: panels/lung_588_pdl1/、config/、肺588模板
# 输出: .work/lung588_pilot_boundary_suite/validation.json 与7份合成报告
# 种子: 20260724（固定合成病例，不含真实患者信息）
"""Generate seven deterministic, de-identified lung588 pilot boundary reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from docx import Document


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (
    ROOT
    / "panels"
    / "lung_588_pdl1"
    / "templates"
    / "lung_588_pdl1_golden_template_v0.docx"
)
PROFILE_ID = "legacy_unspecified_ihc_transcription_v1"


def _variant(
    gene: str,
    c_hgvs: str,
    p_hgvs: str,
    gene_class: str,
    frequency: float,
    *,
    transcript: str,
    chromosome: str,
    exon: str,
) -> dict[str, Any]:
    return {
        "ExistIn552": gene_class,
        "Gene_Symbol": gene,
        "Transcript": transcript,
        "Chr": chromosome,
        "Exon": exon,
        "cHGVS": c_hgvs,
        "pHGVS_S": p_hgvs,
        "Mutation_Type": "SNV",
        "Freq(%)": frequency,
    }


SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "id": "SYN-L588-01-PDL1-NEGATIVE",
        "tps": 0,
        "cps": 0,
        "result": "阴性",
        "tmb": 0,
        "msi": "MSS",
        "variants": [
            _variant(
                "TP53",
                "c.734G>A",
                "p.G245D",
                "Ⅱ类",
                30,
                transcript="NM_000546.6",
                chromosome="17",
                exon="7",
            )
        ],
    },
    {
        "id": "SYN-L588-02-PDL1-LOW-LOWER",
        "tps": 1,
        "cps": 1,
        "result": "阳性（低表达）",
        "tmb": 5,
        "msi": "MSS",
        "variants": [
            _variant(
                "BRAF",
                "c.1799T>A",
                "p.V600E",
                "Ⅰ类",
                28.2,
                transcript="NM_004333.6",
                chromosome="7",
                exon="15",
            )
        ],
    },
    {
        "id": "SYN-L588-03-PDL1-LOW-UPPER",
        "tps": 49,
        "cps": 60,
        "result": "阳性（低表达）",
        "tmb": 9.9,
        "msi": "MSS",
        "variants": [
            _variant(
                "BRAF",
                "c.1781A>G",
                "p.D594G",
                "Ⅱ类",
                12.5,
                transcript="NM_004333.6",
                chromosome="7",
                exon="15",
            )
        ],
    },
    {
        "id": "SYN-L588-04-PDL1-HIGH-LOWER",
        "tps": 50,
        "cps": 52,
        "result": "阳性（高表达）",
        "tmb": 10,
        "msi": "MSS",
        "variants": [
            _variant(
                "ERBB2",
                "c.1979G>A",
                "p.G660D",
                "Ⅰ类",
                8.5,
                transcript="NM_004448.4",
                chromosome="17",
                exon="17",
            )
        ],
    },
    {
        "id": "SYN-L588-05-PDL1-HIGH-UPPER",
        "tps": 100,
        "cps": 100,
        "result": "阳性（高表达）",
        "tmb": 20,
        "msi": "MSS",
        "variants": [
            _variant(
                "EGFR",
                "c.2573T>G",
                "p.L858R",
                "Ⅰ类",
                42,
                transcript="NM_005228.5",
                chromosome="7",
                exon="21",
            )
        ],
    },
    {
        "id": "SYN-L588-06-MSIH-TMBH",
        "tps": 5,
        "cps": 6,
        "result": "阳性（低表达）",
        "tmb": 30,
        "msi": "MSI-H",
        "variants": [
            _variant(
                "KRAS",
                "c.34G>T",
                "p.G12C",
                "Ⅰ类",
                25,
                transcript="NM_004985.5",
                chromosome="12",
                exon="2",
            )
        ],
    },
    {
        "id": "SYN-L588-07-MULTI-VARIANT",
        "tps": 5,
        "cps": 6,
        "result": "阳性（低表达）",
        "tmb": 6.3,
        "msi": "MSS",
        "variants": [
            _variant(
                "TP53",
                "c.578A>T",
                "p.H193L",
                "Ⅱ类",
                40 - index,
                transcript="NM_000546.6",
                chromosome="17",
                exon="6",
            )
            for index in range(12)
        ],
    },
)


def _source_revision() -> str:
    revision_file = ROOT / "REVISION"
    if revision_file.is_file():
        revision = revision_file.read_text(encoding="utf-8").strip()
        if len(revision) == 40:
            return revision
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _visible_text(path: Path) -> str:
    document = Document(path)
    return "\n".join(
        [
            *(paragraph.text for paragraph in document.paragraphs),
            *(
                cell.text
                for table in document.tables
                for row in table.rows
                for cell in row.cells
            ),
        ]
    )


def _build_excel_data(
    scenario: dict[str, Any],
    xlsx_path: Path,
):
    from reportgen.models.excel_data import ExcelDataSource

    case_id = scenario["id"]
    return ExcelDataSource(
        file_path=str(xlsx_path),
        single_values={
            "患者姓名": case_id,
            "样本编号": case_id,
            "性别": "男",
            "年龄": 60,
            "送检医院": "合成验证机构",
            "癌种": "肺癌",
            "检测项目": "肺癌588基因+PD-L1",
            "报告日期": "2026-07-24",
            "TMB": scenario["tmb"],
            "MSI状态": scenario["msi"],
            "PD-L1 TPS": scenario["tps"],
            "PD-L1 CPS": scenario["cps"],
            "PD-L1结果": scenario["result"],
            "PD-L1检测方案": PROFILE_ID,
            "PD-L1原始记录编号": f"SYNTHETIC-IHC-{case_id}",
            "PD-L1原始记录日期": "2026-07-24",
            "PD-L1检测标本标识": f"SYNTHETIC-SPECIMEN-{case_id}",
            "PD-L1图像处置": "无病例专属图像（报告不展示）",
        },
        table_data={"Variations": scenario["variants"]},
        sheet_names=["Variations"],
    )


def run(output_dir: Path, *, require_visual: bool, dpi: int) -> dict[str, Any]:
    os.environ["RG_WEB_UPSTREAM_ROOT"] = str(ROOT)
    os.environ["REPORTGEN_DISABLED_PROJECT_TYPES"] = ""
    for import_path in (str(ROOT), str(ROOT / "backend")):
        if import_path not in sys.path:
            sys.path.insert(0, import_path)

    from reportgen.core.report_generator import ReportGenerator

    output_dir.mkdir(parents=True, exist_ok=True)
    generator = ReportGenerator(
        config_dir=str(ROOT / "config"),
        log_level="ERROR",
    )
    case_rows: list[dict[str, Any]] = []
    all_ids = {scenario["id"] for scenario in SCENARIOS}
    for scenario in SCENARIOS:
        case_id = scenario["id"]
        xlsx_path = output_dir / f"{case_id}.xlsx"
        xlsx_path.write_bytes(b"REPORTGEN_SYNTHETIC_FIXTURE\n")
        result = generator.generate(
            excel_file=str(xlsx_path),
            excel_data=_build_excel_data(scenario, xlsx_path),
            template_file=str(TEMPLATE),
            output_dir=str(output_dir / case_id),
            output_filename=f"{case_id}.docx",
            strict_mode=True,
            return_context=True,
            template_contract_mode="fail",
            project_type="lung_588_pdl1",
            project_name="肺癌588基因+PD-L1",
            qa_visual_render="all" if require_visual else None,
            qa_visual_render_required=require_visual,
            qa_visual_render_dpi=dpi,
            qa_visual_render_timeout_seconds=180,
        )
        output_path = Path(str(result.get("output_file") or ""))
        failures: list[str] = []
        if not result.get("success"):
            failures.append("generation_failed")
        if not output_path.is_file():
            failures.append("output_missing")
            visible = ""
        else:
            visible = _visible_text(output_path)
            if "原始记录未提供" not in visible:
                failures.append("missing_unknown_method_notice")
            if "不据此推导" not in visible:
                failures.append("missing_no_inference_notice")
            if "22C3" in visible:
                failures.append("invented_22c3_method")
            if "肺癌专属知识当前未启用" not in visible:
                failures.append("missing_part3_disabled_notice")
            for other_id in sorted(all_ids - {case_id}):
                if other_id in visible:
                    failures.append(f"cross_case_leak:{other_id}")
        context = result.get("context") or {}
        if context.get("targeted_drug_tips"):
            failures.append("unreviewed_targeted_drug_rows_visible")
        if context.get("gene_knowledge_sections"):
            failures.append("unreviewed_part3_sections_visible")

        qa_status = result.get("qa_status")
        if require_visual and qa_status != "PASS":
            failures.append(f"visual_qa_not_pass:{qa_status or 'missing'}")
        case_rows.append(
            {
                "case_id": case_id,
                "expected_outcome": "PASS",
                "status": "PASS" if not failures else "FAIL",
                "pdl1_tps": scenario["tps"],
                "pdl1_cps": scenario["cps"],
                "pdl1_result": scenario["result"],
                "tmb_value": scenario["tmb"],
                "msi_status": scenario["msi"],
                "input_variant_count": len(scenario["variants"]),
                "runtime_targeted_drug_count": len(
                    context.get("targeted_drug_tips") or []
                ),
                "runtime_part3_section_count": len(
                    context.get("gene_knowledge_sections") or []
                ),
                "qa_status": qa_status,
                "output_sha256": (
                    _sha256(output_path) if output_path.is_file() else ""
                ),
                "failures": failures,
            }
        )

    payload = {
        "schema_version": "1.0",
        "panel_id": "lung_588_pdl1",
        "suite_id": "lung588_controlled_pilot_synthetic_boundary_v1",
        "source_revision": _source_revision(),
        "contains_real_patient_data": False,
        "synthetic_case_count": len(case_rows),
        "passed_case_count": sum(row["status"] == "PASS" for row in case_rows),
        "visual_qa_required": require_visual,
        "status": (
            "PASS"
            if case_rows and all(row["status"] == "PASS" for row in case_rows)
            else "FAIL"
        ),
        "cases": case_rows,
        "release_boundary": {
            "counts_as_real_case_uat": False,
            "counts_as_engineering_boundary_coverage": True,
            "active_release_still_requires_ten_real_cases": True,
            "treatment_inference_allowed": False,
        },
    }
    receipt = output_dir / "validation.json"
    receipt.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(ROOT / ".work" / "lung588_pilot_boundary_suite_20260724"),
    )
    parser.add_argument("--require-visual", action="store_true")
    parser.add_argument("--dpi", type=int, default=120)
    args = parser.parse_args()
    payload = run(
        args.output_dir.resolve(),
        require_visual=args.require_visual,
        dpi=args.dpi,
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "synthetic_case_count": payload["synthetic_case_count"],
                "passed_case_count": payload["passed_case_count"],
                "visual_qa_required": payload["visual_qa_required"],
                "output": str(args.output_dir.resolve() / "validation.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
