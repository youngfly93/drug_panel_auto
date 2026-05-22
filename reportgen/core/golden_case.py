"""
Golden case runner for end-to-end report regression checks.

The golden case deliberately uses a synthetic CRC 358 + MSI workbook. It gives
the project a reproducible one-command regression target without committing
real patient source files.
"""

from __future__ import annotations

import re
from hashlib import sha1
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import pandas as pd
from docx import Document

from reportgen.core.enhancer_registry import get_panel_registry
from reportgen.core.report_generator import ReportGenerator
from reportgen.utils.artifacts import write_json
from reportgen.utils.docx_render import render_docx_to_pngs


SUPPORTED_PANELS = {
    "crc_358_msi": "crc_358_msi",
    "crc_358": "crc_358_msi",
    "lung_methylation": "lung_methylation",
}


@dataclass(frozen=True)
class GoldenCaseOptions:
    """Options for a single golden case run."""

    panel: str = "crc_358_msi"
    config_dir: str = "config"
    template_dir: str = "templates"
    template_file: Optional[str] = None
    output_root: Optional[str] = None
    log_level: str = "ERROR"
    template_contract_mode: str = "fail"
    render: str = "none"
    render_dpi: int = 120
    render_timeout_seconds: int = 120
    render_required: bool = False
    render_tmp_dir: Optional[str] = None


CRC_358_MSI_EXPECTATIONS: Dict[str, Any] = {
    "project_type": "crc_358_msi",
    "project_name": "结直肠癌358基因+MSI",
    "expected_context": {
        "total_variants_count": 2,
        "drug_related_count": 1,
        "tmb_status": "L",
        "msi_status": "MSS",
    },
    "required_qa_checks": [
        "unrendered_placeholders",
        "empty_numbered_paragraphs",
        "post_processors",
        "variant_detail_table_shape",
        "variant_summary_table_present",
        "targeted_drug_tip_table_present",
        "biomarker_table_present",
        "total_variant_count_text",
        "drug_related_count_text",
    ],
    "required_text": [
        "本次共检出体细胞变异：2个",
        "与靶向药物用药相关的变异有：1个",
        "6.5mutations/Mb，TMB-L",
        "微卫星稳定型，MSS",
        "多项临床研究表明，TMB-H的肿瘤",
        "研究表明，MSI-H的实体瘤",
        "ERBB2",
        "c.1979G>A",
        "p.G660D",
    ],
}


LUNG_METHYLATION_EXPECTATIONS: Dict[str, Any] = {
    "project_type": "lung_methylation",
    "project_name": "肺癌甲基化",
    "expected_context": {
        "patient_name": "黄金甲基化患者",
        "sample_id": "LUNG999001",
        "project_name": "肺癌甲基化",
        "methylation_result": "阳性",
    },
    "required_qa_checks": [
        "template_contract",
        "unrendered_placeholders",
        "empty_numbered_paragraphs",
        "post_processors",
    ],
    "required_text": [
        "肺癌甲基化检测报告",
        "黄金甲基化患者",
        "LUNG999001",
        "肺癌甲基化",
        "阳性",
        "SHOX2",
        "RASSF1A",
        "78.5",
    ],
}


def run_golden_case(
    options: Optional[GoldenCaseOptions] = None, **kwargs: Any
) -> Dict[str, Any]:
    """Run the configured golden case and return a machine-readable summary."""
    opts = options or GoldenCaseOptions(**kwargs)
    panel = _normalize_panel(opts.panel)
    case = _golden_case_spec(panel)
    expectations = case["expectations"]

    output_root = _resolve_output_root(opts.output_root, panel)
    input_dir = output_root / "input"
    report_dir = output_root / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    excel_file = case["builder"](input_dir / case["input_filename"])
    template_file = _resolve_template_file(opts)

    generator = ReportGenerator(
        config_dir=opts.config_dir,
        template_dir=opts.template_dir,
        log_level=opts.log_level,
    )
    generation = generator.generate(
        excel_file=str(excel_file),
        template_file=str(template_file),
        output_dir=str(report_dir),
        output_filename=case["output_filename"],
        strict_mode=True,
        return_context=True,
        template_contract_mode=opts.template_contract_mode,
        project_type=panel,
        project_name=expectations["project_name"],
    )

    assertion = assert_golden_case_output(generation, expectations=expectations)
    visual_render = run_visual_render(
        generation.get("output_file"),
        output_root=output_root,
        mode=opts.render,
        dpi=opts.render_dpi,
        timeout_seconds=opts.render_timeout_seconds,
        required=opts.render_required,
        tmp_dir=opts.render_tmp_dir,
    )
    checks = list(assertion["checks"])
    if visual_render["requested"] != "none":
        checks.append(
            {
                "name": "visual_render",
                "passed": visual_render["status"] == "PASS"
                or not opts.render_required,
                "message": visual_render["message"],
                "details": visual_render,
            }
        )

    summary = {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "panel": panel,
        "ok": bool(generation.get("success"))
        and assertion["ok"]
        and (visual_render["status"] != "FAIL"),
        "input_excel": str(excel_file),
        "template_file": str(template_file),
        "output_root": str(output_root),
        "output_file": generation.get("output_file"),
        "qa_report_file": generation.get("qa_report_file"),
        "field_provenance_file": generation.get("field_provenance_file"),
        "qa_status": generation.get("qa_status"),
        "duration": generation.get("duration"),
        "generation_errors": generation.get("errors") or [],
        "generation_warnings": generation.get("warnings") or [],
        "visual_render": visual_render,
        "checks": checks,
    }
    summary["errors"] = [
        check["message"] for check in summary["checks"] if not check["passed"]
    ] + list(generation.get("errors") or [])

    report_path = output_root / "golden_case_report.json"
    write_json(report_path, summary)
    summary["golden_report_file"] = str(report_path)
    return summary


def run_visual_render(
    output_file: Any,
    *,
    output_root: Path,
    mode: str = "none",
    dpi: int = 120,
    timeout_seconds: int = 120,
    required: bool = False,
    tmp_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Render a generated golden DOCX to PNG pages when requested."""
    normalized_mode = str(mode or "none").strip().lower()
    if normalized_mode not in {"none", "first", "all"}:
        raise ValueError(f"Unsupported render mode: {mode!r}")

    result: Dict[str, Any] = {
        "requested": normalized_mode,
        "required": bool(required),
        "status": "SKIPPED",
        "message": "visual rendering was not requested",
        "rendered_pages": [],
        "output_dir": None,
        "error": None,
    }
    if normalized_mode == "none":
        return result

    if not output_file:
        result.update(
            {
                "status": "FAIL" if required else "WARN",
                "message": "visual rendering requested but no DOCX output exists",
                "error": "missing_output_file",
            }
        )
        return result

    output_path = Path(str(output_file))
    render_dir = output_root / "rendered_pages" / output_path.stem
    first_page = 1 if normalized_mode == "first" else None
    last_page = 1 if normalized_mode == "first" else None
    try:
        pngs = render_docx_to_pngs(
            output_path,
            output_dir=render_dir,
            dpi=int(dpi),
            first_page=first_page,
            last_page=last_page,
            keep_pdf=False,
            timeout_seconds=int(timeout_seconds),
            tmp_dir=Path(tmp_dir) if tmp_dir else None,
        )
    except Exception as exc:
        result.update(
            {
                "status": "FAIL" if required else "WARN",
                "message": f"visual rendering failed: {exc}",
                "output_dir": str(render_dir),
                "error": str(exc),
            }
        )
        stage = getattr(exc, "stage", None)
        if stage:
            result["stage"] = stage
        command = getattr(exc, "command", None)
        if command:
            result["command"] = list(command)
        stdout = getattr(exc, "stdout", None)
        stderr = getattr(exc, "stderr", None)
        if stdout:
            result["stdout_tail"] = str(stdout)[-2000:]
        if stderr:
            result["stderr_tail"] = str(stderr)[-2000:]
        return result

    result.update(
        {
            "status": "PASS" if pngs else ("FAIL" if required else "WARN"),
            "message": "visual rendering produced PNG pages"
            if pngs
            else "visual rendering completed but produced no PNG pages",
            "rendered_pages": [str(path) for path in pngs],
            "output_dir": str(render_dir),
        }
    )
    return result


def _golden_case_spec(panel: str) -> Dict[str, Any]:
    if panel == "lung_methylation":
        return {
            "expectations": LUNG_METHYLATION_EXPECTATIONS,
            "builder": build_lung_methylation_golden_excel,
            "input_filename": "LUNG999001_lung_methylation_golden.xlsx",
            "output_filename": "golden_lung_methylation.docx",
        }
    return {
        "expectations": CRC_358_MSI_EXPECTATIONS,
        "builder": build_crc_358_msi_golden_excel,
        "input_filename": "LZ999001_crc_358_msi_golden.xlsx",
        "output_filename": "golden_crc_358_msi.docx",
    }


def build_crc_358_msi_golden_excel(path: Path | str) -> Path:
    """Create a synthetic CRC 358 + MSI workbook suitable for the golden case."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    meta = pd.DataFrame(
        [
            {
                "患者姓名": "黄金测试患者",
                "样本编号": "LZ999001",
                "报告编号": "MLJY-LZ999001",
                "性别": "男",
                "年龄": 58,
                "临床诊断": "结直肠癌",
                "肿瘤类型": "结直肠癌",
                "样本类型": "组织",
                "取材手段": "手术",
                "取材部位": "结肠",
                "项目名称": "结直肠癌358基因+MSI",
                "检测项目": "结直肠癌358基因+MSI",
                "送检日期": "2026-01-08",
                "报告日期": "2026-01-15",
                "检测方法": "NGS高通量测序",
            }
        ]
    )

    variations = pd.DataFrame(
        [
            {
                "Gene_Symbol": "ERBB2",
                "Transcript": "NM_004448.4",
                "Chr": "17",
                "ExIn_ID": "EX17",
                "cHGVS": "c.1979G>A",
                "pHGVS_S": "p.G660D",
                "Freq(%)": 22.5,
                "Function": "Missense",
                "ExistInsmall358": 1,
                "ExistIn552": "Ⅰ类",
                "CLNSIG": "Pathogenic",
            },
            {
                "Gene_Symbol": "FBXW7",
                "Transcript": "NM_033632.3",
                "Chr": "4",
                "ExIn_ID": "EX10",
                "cHGVS": "c.1394G>A",
                "pHGVS_S": "p.R465H",
                "Freq(%)": 12.7,
                "Function": "Missense",
                "ExistInsmall358": 1,
                "ExistIn552": "Ⅲ类",
                "CLNSIG": "Uncertain_significance",
            },
        ]
    )

    tmb = pd.DataFrame(
        [
            ["TCGA fit", None, None, None],
            ["SampleTP", "Var_num", "Bed_size", "TMB"],
            ["tissue", 65, 10_000_000, 6.5],
        ]
    )
    msisensor = pd.DataFrame(
        [
            ["control", 1000, 3, 0.3, "MSS"],
            ["tumor", 1000, 12, 1.2, "MSS"],
        ],
        columns=["Sample", "Total", "Unstable", "Percent", "Status"],
    )
    qc = pd.DataFrame(
        [
            ["Q30", 95.5],
            ["Coverage", 99.8],
            ["Average sequencing depth", 800],
            ["Insert", 180],
        ]
    )

    empty_cnv = pd.DataFrame(columns=["Gene", "Chr", "Start", "End", "CopyNumber"])
    empty_fusion = pd.DataFrame(
        columns=["Gene1", "Gene2", "Chr1", "Pos1", "Chr2", "Pos2"]
    )

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        meta.to_excel(writer, sheet_name="Meta", index=False)
        variations.to_excel(writer, sheet_name="Variations", index=False)
        tmb.to_excel(writer, sheet_name="TMB", index=False, header=False)
        msisensor.to_excel(writer, sheet_name="Msisensor", index=False)
        qc.to_excel(writer, sheet_name="QC", index=False, header=False)
        empty_cnv.to_excel(writer, sheet_name="Cnv", index=False)
        empty_fusion.to_excel(writer, sheet_name="Fusion", index=False)

    return out


def build_lung_methylation_golden_excel(path: Path | str) -> Path:
    """Create a synthetic lung methylation workbook for M3 panel testing."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    meta = pd.DataFrame(
        [
            {
                "患者姓名": "黄金甲基化患者",
                "样本编号": "LUNG999001",
                "报告编号": "MLJY-LUNG999001",
                "性别": "女",
                "年龄": 62,
                "临床诊断": "肺癌",
                "肿瘤类型": "肺癌",
                "样本类型": "血浆",
                "项目名称": "肺癌甲基化",
                "检测项目": "肺癌甲基化",
                "甲基化结果": "阳性",
                "送检日期": "2026-02-01",
                "报告日期": "2026-02-08",
                "检测方法": "甲基化特异性测序",
            }
        ]
    )
    sites = pd.DataFrame(
        [
            {
                "基因": "SHOX2",
                "位点": "cg000001",
                "甲基化水平": 78.5,
                "阈值": 10.0,
                "结果": "阳性",
            },
            {
                "基因": "RASSF1A",
                "位点": "cg000002",
                "甲基化水平": 32.1,
                "阈值": 8.0,
                "结果": "阳性",
            },
        ]
    )

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        meta.to_excel(writer, sheet_name="Meta", index=False)
        sites.to_excel(writer, sheet_name="甲基化位点", index=False)

    return out


def assert_golden_case_output(
    generation: Mapping[str, Any],
    *,
    expectations: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Assert a generated report against frozen golden expectations."""
    expected = expectations or CRC_358_MSI_EXPECTATIONS
    checks: List[Dict[str, Any]] = []

    def check(name: str, passed: bool, message: str, **details: Any) -> None:
        checks.append(
            {"name": name, "passed": bool(passed), "message": message, **details}
        )

    output_file = generation.get("output_file")
    output_path = Path(str(output_file)) if output_file else None
    check(
        "generation_success",
        bool(generation.get("success")),
        "report generator returned success",
        errors=generation.get("errors") or [],
    )
    check(
        "output_docx_exists",
        bool(output_path and output_path.exists()),
        "generated DOCX exists",
        output_file=str(output_file) if output_file else None,
    )

    context = generation.get("context") or {}
    for field, value in (expected.get("expected_context") or {}).items():
        check(
            f"context_{field}",
            context.get(field) == value,
            f"context field {field} matches expected value",
            expected=value,
            actual=context.get(field),
        )

    qa = generation.get("qa_report") or {}
    check(
        "qa_status_pass",
        qa.get("status") == "PASS",
        "QA report status is PASS",
        actual=qa.get("status"),
        issues=qa.get("issues") or [],
    )
    check(
        "field_provenance_present",
        bool(generation.get("field_provenance_file")),
        "field provenance sidecar was generated",
        field_provenance_file=generation.get("field_provenance_file"),
    )

    qa_checks = qa.get("checks") if isinstance(qa, Mapping) else {}
    for qa_check_name in expected.get("required_qa_checks") or []:
        item = qa_checks.get(qa_check_name, {}) if isinstance(qa_checks, Mapping) else {}
        status = item.get("status")
        check(
            f"qa_{qa_check_name}",
            status == "PASS",
            f"QA check {qa_check_name} is PASS",
            actual=status,
            details=item,
        )

    post_processors = (
        generation.get("post_processors") or qa.get("post_processors") or []
    )
    processor_errors = [
        row
        for row in post_processors
        if isinstance(row, Mapping) and row.get("status") == "ERROR"
    ]
    check(
        "post_processors_no_errors",
        not processor_errors,
        "post-render processors completed without ERROR status",
        errors=processor_errors,
    )

    text = _read_docx_text(output_path) if output_path and output_path.exists() else ""
    compact_text = _compact(text)
    for required in expected.get("required_text") or []:
        check(
            f"text_contains_{_slug(required)}",
            _compact(required) in compact_text,
            "required golden text appears in rendered DOCX",
            required=required,
        )

    return {"ok": all(row["passed"] for row in checks), "checks": checks}


def _normalize_panel(panel: str) -> str:
    normalized = SUPPORTED_PANELS.get(str(panel or "").strip())
    if not normalized:
        supported = ", ".join(sorted(SUPPORTED_PANELS))
        raise ValueError(f"Unsupported golden panel: {panel!r}. Supported: {supported}")
    return normalized


def _resolve_output_root(output_root: Optional[str], panel: str) -> Path:
    if output_root:
        return Path(output_root).resolve()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (Path("tmp") / "golden_cases" / f"{panel}_{stamp}").resolve()


def _resolve_template_file(opts: GoldenCaseOptions) -> Path:
    if opts.template_file:
        template = Path(opts.template_file)
    else:
        template = None
        try:
            registration = get_panel_registry().get(_normalize_panel(opts.panel))
            if registration and registration.package:
                template = registration.package.resolve_template_file()
        except Exception:
            template = None
        if template is None:
            template = (
                Path(opts.template_dir)
                / "aligned_template_with_cnv_fusion_hla_FIXED.docx"
            )
    template = template.resolve()
    if not template.exists():
        raise FileNotFoundError(f"Golden case template not found: {template}")
    return template


def _read_docx_text(path: Path) -> str:
    doc = Document(str(path))
    parts: List[str] = []
    for paragraph in doc.paragraphs:
        if paragraph.text:
            parts.append(paragraph.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text:
                    parts.append(cell.text)
    return "\n".join(parts)


def _compact(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _slug(text: str) -> str:
    value = re.sub(r"\W+", "_", _compact(text), flags=re.ASCII).strip("_").lower()
    if value:
        return value[:60]
    digest = sha1(str(text).encode("utf-8")).hexdigest()[:12]
    return f"required_text_{digest}"
