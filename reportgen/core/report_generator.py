"""
报告生成器

核心业务逻辑编排，协调所有组件生成报告。
"""

import json
import math
import os
import time
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from reportgen.config.loader import ConfigLoader
from reportgen.core.data_cleaner import DataCleaner
from reportgen.core.enhancer_registry import (
    get_enhancer,
    get_panel_registry,
    normalize_project_type,
)
from reportgen.core.excel_reader import ExcelReader
from reportgen.core.field_mapper import FieldMapper
from reportgen.core.field_provenance import (
    build_field_provenance_report,
    write_field_provenance_report,
)
from reportgen.core.pipeline import (
    GenerationContext,
    GenerationPipeline,
    StageHandle,
    summarize_stage_results,
)
from reportgen.core.processors import critical_docx_processor_names
from reportgen.core.qa_report import (
    attach_pipeline_summary,
    build_docx_qa_report,
    write_docx_qa_report,
)
from reportgen.core.report_summary import build_report_summary, write_report_summary
from reportgen.core.signature_library import resolve_signature_path
from reportgen.core.template_renderer import TemplateRenderer
from reportgen.models.excel_data import ExcelDataSource
from reportgen.models.report_data import ReportData
from reportgen.panels.validation import validate_panel_package_path
from reportgen.panels.release_scope import ensure_project_type_enabled
from reportgen.rules import (
    PanelRuleEngine,
    apply_pdl1_product_display_fields,
    load_pdl1_product_contract,
    validate_pdl1_product_contract,
)
from reportgen.rules.evaluators import apply_report_text_rules, collect_report_texts
from reportgen.utils.file_utils import (
    ensure_directory_exists,
    get_unique_filename,
    safe_filename,
)
from reportgen.utils.logger import get_logger


BIOMARKER_FIELD_ALIASES = {
    "msi_status": ("msi_status", "MSI状态"),
    "tmb_value": ("tmb_value", "TMB"),
    "pdl1_tps": ("pdl1_tps", "PD-L1 TPS", "TPS"),
    "pdl1_cps": ("pdl1_cps", "PD-L1 CPS", "CPS"),
    "pdl1_result": ("pdl1_result", "PD-L1结果", "PD-L1 Result"),
}


def _numeric_biomarker_value(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    text = str(value).strip().rstrip("%").strip()
    if not text:
        return None
    try:
        numeric = float(text)
        return numeric if math.isfinite(numeric) else None
    except ValueError:
        return None


def validate_panel_biomarker_contracts(
    report_data: ReportData,
    biomarker_contracts: Any,
) -> list[dict[str, Any]]:
    """Validate required biomarker values and cross-field classifications.

    The rule shape is panel-owned. In addition to the existing
    ``required``/``allowed_values`` contract, numeric fields may declare
    ``minimum``/``maximum`` and categorical fields may declare
    ``classification_ranges`` keyed by their allowed display value.
    """
    if not isinstance(biomarker_contracts, dict):
        return []

    failures: list[dict[str, Any]] = []

    def resolved_value(field_name: str) -> Any:
        aliases = BIOMARKER_FIELD_ALIASES.get(field_name, (field_name,))
        return next(
            (
                report_data.get_field(alias)
                for alias in aliases
                if report_data.get_field(alias) not in (None, "")
            ),
            None,
        )

    for raw_field_name, spec in biomarker_contracts.items():
        field_name = str(raw_field_name)
        if not isinstance(spec, dict):
            continue
        value = resolved_value(field_name)
        # Numeric zero is a valid value for TMB/TPS/CPS. Avoid truthiness here:
        # ``str(value or "")`` would silently turn 0 into a missing result.
        text_value = "" if value is None else str(value).strip()
        allowed = [str(item).strip() for item in spec.get("allowed_values") or []]
        missing_values = {
            str(item).strip()
            for item in spec.get("missing_values") or ["", "未检测", "--"]
        }
        if spec.get("required", False) and (
            text_value in missing_values or (allowed and text_value not in allowed)
        ):
            failures.append(
                {
                    "field": field_name,
                    "reason": "missing_or_disallowed",
                    "value": text_value,
                    "allowed_values": allowed,
                }
            )
            continue

        if text_value in missing_values:
            continue
        if allowed and text_value not in allowed:
            failures.append(
                {
                    "field": field_name,
                    "reason": "disallowed_value",
                    "value": text_value,
                    "allowed_values": allowed,
                }
            )
            continue

        if "minimum" in spec or "maximum" in spec:
            numeric = _numeric_biomarker_value(value)
            if numeric is None:
                failures.append(
                    {
                        "field": field_name,
                        "reason": "not_numeric",
                        "value": text_value,
                    }
                )
                continue
            minimum = spec.get("minimum")
            maximum = spec.get("maximum")
            if minimum is not None and numeric < float(minimum):
                failures.append(
                    {
                        "field": field_name,
                        "reason": "below_minimum",
                        "value": text_value,
                        "minimum": minimum,
                    }
                )
            if maximum is not None and numeric > float(maximum):
                failures.append(
                    {
                        "field": field_name,
                        "reason": "above_maximum",
                        "value": text_value,
                        "maximum": maximum,
                    }
                )

        ranges = spec.get("classification_ranges")
        if not isinstance(ranges, dict) or text_value not in ranges:
            continue
        range_spec = ranges.get(text_value)
        if not isinstance(range_spec, dict):
            continue
        source_field = str(range_spec.get("field") or "").strip()
        source_value = resolved_value(source_field)
        numeric = _numeric_biomarker_value(source_value)
        if not source_field or numeric is None:
            failures.append(
                {
                    "field": field_name,
                    "reason": "classification_source_missing",
                    "source_field": source_field,
                }
            )
            continue
        minimum = range_spec.get("minimum")
        maximum = range_spec.get("maximum")
        min_inclusive = bool(range_spec.get("minimum_inclusive", True))
        max_inclusive = bool(range_spec.get("maximum_inclusive", True))
        below = minimum is not None and (
            numeric < float(minimum)
            if min_inclusive
            else numeric <= float(minimum)
        )
        above = maximum is not None and (
            numeric > float(maximum)
            if max_inclusive
            else numeric >= float(maximum)
        )
        if below or above:
            failures.append(
                {
                    "field": field_name,
                    "reason": "classification_inconsistent",
                    "value": text_value,
                    "source_field": source_field,
                    "source_value": source_value,
                }
            )
    return failures


def apply_pdl1_display_fields(report_data: ReportData) -> None:
    """Build neutral report text from controlled PD-L1 form values.

    This function deliberately reports the supplied IHC values without
    generating a patient-level treatment recommendation.
    """
    tps = report_data.get_field("pdl1_tps")
    cps = report_data.get_field("pdl1_cps")
    result = str(report_data.get_field("pdl1_result") or "").strip()
    if tps in (None, "") and cps in (None, "") and not result:
        return

    def display(value: Any) -> str:
        numeric = _numeric_biomarker_value(value)
        if numeric is None:
            return str(value or "--").strip()
        return f"{numeric:g}"

    report_data.set_field(
        "pdl1_table_interpretation",
        "本次PD-L1免疫组化检测结果："
        f"TPS {display(tps)}%，CPS {display(cps)}，{result or '结果未填写'}。"
        "本结果须结合病理类型、分期、检测抗体及现行诊疗规范综合判断。",
    )


@dataclass
class _GenerationState:
    """Mutable state passed between generation stages."""

    excel_file: str
    template_file: str
    output_dir: str
    output_filename: Optional[str] = None
    strict_mode: bool = False
    excel_data: Optional[ExcelDataSource] = None
    return_context: bool = False
    template_contract_mode: str = "warn"
    project_type: Optional[str] = None
    project_name: Optional[str] = None
    canonical_project_type: Optional[str] = None
    panel_registration: Any = None
    panel_package: Any = None
    panel_package_validation: Optional[dict[str, Any]] = None
    report_data: Optional[ReportData] = None
    report_content: dict[str, Any] = dc_field(default_factory=dict)
    output_path: Optional[str] = None
    final_output: Optional[str] = None
    generation_id: Optional[str] = None
    template_context: Optional[dict[str, Any]] = None
    template_contract_report: Optional[dict[str, Any]] = None
    template_processor_names: Optional[tuple[str, ...]] = None
    processor_report: list[Any] = dc_field(default_factory=list)
    field_provenance: Optional[dict[str, Any]] = None
    field_provenance_file: Optional[str] = None
    rule_provenance: Optional[dict[str, Any]] = None
    report_text_rules: dict[str, str] = dc_field(default_factory=dict)
    qa_report: Optional[dict[str, Any]] = None
    qa_report_file: Optional[str] = None
    report_summary: Optional[dict[str, Any]] = None
    report_summary_file: Optional[str] = None
    stage_results_file: Optional[str] = None
    qa_visual_render: Optional[str] = None
    qa_visual_render_required: Optional[bool] = None
    qa_visual_render_dpi: Optional[int] = None
    qa_visual_render_timeout_seconds: Optional[int] = None
    qa_visual_render_output_dir: Optional[str] = None
    qa_visual_render_tmp_dir: Optional[str] = None


class ReportGenerator:
    """
    报告生成器

    协调Excel读取、字段映射、数据清洗和模板渲染，生成最终报告。
    """

    def __init__(
        self,
        config_dir: str = "config",
        template_dir: str = "templates",
        log_file: Optional[str] = None,
        log_level: str = "INFO",
    ):
        """
        初始化报告生成器

        Args:
            config_dir: 配置目录
            template_dir: 模板目录
            log_file: 日志文件路径
        """
        self.config_dir = config_dir
        self.template_dir = template_dir
        self.log_level = log_level
        self.logger = get_logger(log_file=log_file, level=log_level)
        self.config_loader = ConfigLoader(
            config_dir=config_dir, log_file=log_file, log_level=log_level
        )

        # 初始化各个组件
        self.excel_reader = ExcelReader(
            config_dir=config_dir, log_file=log_file, log_level=log_level
        )
        self.field_mapper = FieldMapper(
            config_dir=config_dir, log_file=log_file, log_level=log_level
        )
        self.data_cleaner = DataCleaner(log_file=log_file, log_level=log_level)
        self.template_renderer = TemplateRenderer(
            log_file=log_file, log_level=log_level
        )

    # 关键字段定义（严格模式下必须存在）
    CRITICAL_FIELDS = ["patient_name", "sample_id"]

    # 重要字段定义（严格模式下缺失会警告，但不阻断）
    IMPORTANT_FIELDS = ["age", "gender", "cancer_type", "hospital"]

    def generate(
        self,
        excel_file: str,
        template_file: str,
        output_dir: str,
        output_filename: Optional[str] = None,
        strict_mode: bool = False,
        excel_data: Optional[ExcelDataSource] = None,
        return_context: bool = False,
        template_contract_mode: str = "warn",
        project_type: Optional[str] = None,
        project_name: Optional[str] = None,
        qa_visual_render: Optional[str] = None,
        qa_visual_render_required: Optional[bool] = None,
        qa_visual_render_dpi: Optional[int] = None,
        qa_visual_render_timeout_seconds: Optional[int] = None,
        qa_visual_render_output_dir: Optional[str] = None,
        qa_visual_render_tmp_dir: Optional[str] = None,
    ) -> dict:
        """
        生成单个报告

        Args:
            excel_file: Excel文件路径
            template_file: 模板文件路径
            output_dir: 输出目录
            output_filename: 输出文件名（可选，默认自动生成）
            strict_mode: 严格模式（缺失关键字段时阻断生成）

        Returns:
            生成结果字典，包含:
                - success: 是否成功
                - output_file: 输出文件路径
                - duration: 耗时（秒）
                - errors: 错误列表
        """
        start_time = time.time()
        state = _GenerationState(
            excel_file=excel_file,
            template_file=template_file,
            output_dir=output_dir,
            output_filename=output_filename,
            strict_mode=strict_mode,
            excel_data=excel_data,
            return_context=return_context,
            template_contract_mode=template_contract_mode,
            project_type=project_type,
            project_name=project_name,
            qa_visual_render=qa_visual_render,
            qa_visual_render_required=qa_visual_render_required,
            qa_visual_render_dpi=qa_visual_render_dpi,
            qa_visual_render_timeout_seconds=qa_visual_render_timeout_seconds,
            qa_visual_render_output_dir=qa_visual_render_output_dir,
            qa_visual_render_tmp_dir=qa_visual_render_tmp_dir,
        )
        pipeline = GenerationPipeline(
            GenerationContext(
                request={
                    "excel_file": excel_file,
                    "template_file": template_file,
                    "output_dir": output_dir,
                    "output_filename": output_filename,
                    "strict_mode": strict_mode,
                    "template_contract_mode": template_contract_mode,
                    "project_type": project_type,
                    "project_name": project_name,
                    "qa_visual_render": qa_visual_render,
                    "qa_visual_render_required": qa_visual_render_required,
                }
            )
        )

        self.logger.info(
            "开始生成报告",
            excel_file=excel_file,
            template=template_file,
            output_dir=output_dir,
        )

        try:
            pipeline.run_step(
                "PanelResolutionStage", self._stage_panel_resolution, state
            )
            failure = pipeline.run_step(
                "PanelPackageValidationStage",
                self._stage_panel_package_validation,
                state,
                start_time,
            )
            if failure is not None:
                return self._finish_generation(state, pipeline, failure)

            pipeline.run_step("ExcelReadStage", self._stage_excel_read, state)
            pipeline.run_step(
                "FieldResolutionStage", self._stage_field_resolution, state
            )
            pipeline.run_step(
                "PanelRuleExecutionStage", self._stage_panel_rule_execution, state
            )
            failure = pipeline.run_step(
                "InputContractValidationStage",
                self._stage_input_contract_validation,
                state,
                start_time,
            )
            if failure is not None:
                return self._finish_generation(state, pipeline, failure)

            pipeline.run_step("OutputPathStage", self._stage_output_path, state)
            failure = pipeline.run_step(
                "TemplateContractStage",
                self._stage_template_contract,
                state,
                start_time,
            )
            if failure is not None:
                return self._finish_generation(state, pipeline, failure)

            pipeline.run_step("TemplateRenderStage", self._stage_template_render, state)
            pipeline.run_step(
                "FieldProvenanceStage", self._stage_field_provenance, state
            )
            pipeline.run_step("QAStage", self._stage_qa, state)
            pipeline.run_step("ReportSummaryStage", self._stage_report_summary, state)

            duration = time.time() - start_time
            self.logger.info(
                "报告生成成功",
                output=state.final_output,
                duration_seconds=f"{duration:.2f}",
            )
            return self._finish_generation(
                state,
                pipeline,
                self._build_success_payload(state, duration),
            )

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(
                "报告生成失败",
                excel_file=excel_file,
                error=str(e),
                duration_seconds=f"{duration:.2f}",
            )
            return self._finish_generation(
                state,
                pipeline,
                {
                    "success": False,
                    "output_file": None,
                    "duration": duration,
                    "errors": [str(e)],
                    "warnings": [],
                },
            )

    def _finish_generation(
        self,
        state: _GenerationState,
        pipeline: GenerationPipeline,
        payload: dict,
    ) -> dict:
        """Attach common pipeline metadata and persist a stage sidecar if possible."""
        stage_results = pipeline.to_list()
        payload["stage_results"] = stage_results

        output_file = payload.get("output_file") or state.final_output
        generation_id = payload.get("generation_id") or state.generation_id
        if not generation_id and output_file:
            generation_id = Path(str(output_file)).stem
        if not generation_id:
            generation_id = "generation"
        if generation_id:
            payload["generation_id"] = generation_id

        if output_file or state.output_dir:
            try:
                stage_results_file = self._write_stage_results_report(
                    output_file=str(output_file) if output_file else None,
                    output_dir=state.output_dir,
                    generation_id=generation_id,
                    stage_results=stage_results,
                )
                state.stage_results_file = stage_results_file
                payload["stage_results_file"] = stage_results_file
            except Exception as exc:
                payload.setdefault("warnings", []).append(
                    f"生成阶段报告失败: {exc}"
                )
        if state.qa_report is not None and state.final_output and state.qa_report_file:
            state.qa_report = attach_pipeline_summary(
                state.qa_report,
                stage_results=stage_results,
                stage_results_file=state.stage_results_file,
            )
            state.qa_report_file = write_docx_qa_report(
                state.qa_report,
                state.final_output,
                qa_file=state.qa_report_file,
            )
            payload["qa_report"] = state.qa_report
            payload["qa_report_file"] = state.qa_report_file
            payload["qa_status"] = state.qa_report.get("status")
        return payload

    @staticmethod
    def _write_stage_results_report(
        *,
        output_file: Optional[str],
        output_dir: Optional[str],
        generation_id: Optional[str],
        stage_results: list[dict[str, Any]],
    ) -> str:
        """Write a sidecar JSON file containing the observable pipeline trace."""
        output_path = Path(output_file) if output_file else None
        if output_path:
            sidecar_path = output_path.with_suffix(".stage_results.json")
        elif output_dir:
            sidecar_path = Path(output_dir) / "generation.stage_results.json"
        else:
            raise ValueError("output_file or output_dir is required")
        payload = {
            "generation_id": generation_id
            or (output_path.stem if output_path else "generation"),
            "output_file": str(output_path) if output_path else None,
            "pipeline": summarize_stage_results(
                stage_results,
                stage_results_file=str(sidecar_path),
            ),
            "stage_results": stage_results,
        }
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(sidecar_path)

    def _stage_panel_resolution(
        self,
        stage: StageHandle,
        state: _GenerationState,
    ) -> None:
        state.canonical_project_type = normalize_project_type(state.project_type)
        ensure_project_type_enabled(state.canonical_project_type)
        state.project_name = self._normalize_project_name(
            state.project_name,
            state.canonical_project_type,
        )
        state.panel_registration = self._get_panel_registration(
            state.canonical_project_type
        )
        state.panel_package = (
            state.panel_registration.package
            if state.panel_registration is not None
            else None
        )
        stage.metrics.update(
            {
                "project_type": state.canonical_project_type,
                "project_name": state.project_name,
                "panel_id": (
                    getattr(state.panel_package, "panel_id", None)
                    if state.panel_package is not None
                    else None
                ),
            }
        )

    def _stage_panel_package_validation(
        self,
        stage: StageHandle,
        state: _GenerationState,
        start_time: float,
    ) -> Optional[dict]:
        state.panel_package_validation = self._validate_panel_package_for_generation(
            state.panel_package
        )
        if state.panel_package_validation:
            stage.metrics.update(
                {
                    "status": state.panel_package_validation.get("status"),
                    "issue_count": len(
                        state.panel_package_validation.get("issues") or []
                    ),
                }
            )
        else:
            stage.skip(message="No panel package is registered for this request.")

        if state.panel_package_validation and not state.panel_package_validation.get(
            "ok"
        ):
            duration = time.time() - start_time
            error_msg = self._format_panel_validation_failure(
                state.canonical_project_type,
                state.panel_package_validation,
            )
            stage.fail(
                "PANEL_PACKAGE_VALIDATION_FAILED",
                error_msg,
                details={
                    "project_type": state.canonical_project_type,
                    "summary": state.panel_package_validation.get("summary"),
                },
            )
            self.logger.error(
                "Panel Package校验失败，阻断生成",
                project_type=state.canonical_project_type,
                errors=state.panel_package_validation.get("issues") or [],
            )
            return {
                "success": False,
                "output_file": None,
                "duration": duration,
                "errors": [error_msg],
                "warnings": [],
                "panel_package_validation": state.panel_package_validation,
            }
        state.rule_provenance = self._load_rule_provenance(state.panel_package)
        if state.rule_provenance:
            stage.metrics["rule_file_count"] = state.rule_provenance.get("file_count")
            stage.artifacts["rule_provenance"] = {
                "panel_id": state.rule_provenance.get("panel_id"),
                "status": state.rule_provenance.get("status"),
                "file_count": state.rule_provenance.get("file_count"),
            }
        return None

    def _stage_excel_read(self, stage: StageHandle, state: _GenerationState) -> None:
        if state.excel_data is None:
            self.logger.log_event("excel_reading_started", file=state.excel_file)
            state.excel_data = self.excel_reader.read(state.excel_file)
            self.logger.log_event(
                "excel_reading_completed",
                file=state.excel_file,
                single_values=len(state.excel_data.single_values),
                tables=len(state.excel_data.table_data),
            )
            stage.metrics["source"] = "file"
        else:
            if state.excel_file and str(state.excel_file) != str(
                state.excel_data.file_path
            ):
                self.logger.warning(
                    "传入的excel_data与excel_file路径不一致，优先使用excel_data.file_path",
                    excel_file=state.excel_file,
                    excel_data_path=state.excel_data.file_path,
                )
                stage.warn(
                    "EXCEL_PATH_MISMATCH",
                    "excel_data.file_path differs from excel_file; reused excel_data.",
                    details={
                        "excel_file": str(state.excel_file),
                        "excel_data_path": str(state.excel_data.file_path),
                    },
                )
            self.logger.log_event(
                "excel_reading_skipped",
                file=state.excel_data.file_path,
                single_values=len(state.excel_data.single_values),
                tables=len(state.excel_data.table_data),
            )
            stage.metrics["source"] = "provided_excel_data"
        stage.metrics.update(
            {
                "single_values": len(state.excel_data.single_values),
                "tables": len(state.excel_data.table_data),
            }
        )

    def _stage_field_resolution(
        self,
        stage: StageHandle,
        state: _GenerationState,
    ) -> None:
        if state.excel_data is None:
            raise RuntimeError("Excel data is unavailable before field resolution.")

        self.logger.log_event("field_mapping_started")
        state.report_data = self.field_mapper.map(
            state.excel_data,
            panel_package=state.panel_package,
        )
        rd = state.report_data.get_field("report_date")
        if rd is None or (isinstance(rd, str) and rd.strip() == ""):
            self._fill_missing_report_date(state.report_data)
            stage.warn(
                "REPORT_DATE_MISSING",
                "report_date is missing and was set to the generation date.",
            )
        self.logger.log_event(
            "field_mapping_completed",
            validation_errors=len(state.report_data.validation_errors),
        )

        self.logger.log_event("data_cleaning_started")
        state.report_data = self.data_cleaner.validate_and_clean(state.report_data)
        self.logger.log_event(
            "data_cleaning_completed",
            validation_errors=len(state.report_data.validation_errors),
        )

        if state.project_name and state.canonical_project_type:
            cur_pn = state.report_data.get_field("project_name")
            if cur_pn != state.project_name:
                state.report_data.set_field("project_name", state.project_name)
                self.logger.info(
                    "项目检测结果覆盖project_name",
                    old=cur_pn,
                    new=state.project_name,
                )

        report_content = self.config_loader.get_setting("report_content", {}) or {}
        state.report_content = report_content if isinstance(report_content, dict) else {}
        if state.report_content:
            state.report_data.set_field("report_content", state.report_content)
        panel_style = self._load_panel_style_config(state.panel_package)
        if panel_style:
            state.report_data.set_field("panel_style", panel_style)
        self._resolve_signature_image_fields(state.report_data)
        state.report_text_rules = self._load_report_text_rules(state.panel_package)
        applied_text_rules = apply_report_text_rules(
            state.report_data,
            state.report_text_rules,
        )
        if applied_text_rules:
            state.report_data.set_field("report_text_rule_keys", applied_text_rules)
            stage.metrics["report_text_rule_count"] = len(applied_text_rules)
        stage.metrics["validation_errors"] = len(state.report_data.validation_errors)

    def _resolve_signature_image_fields(self, report_data: ReportData) -> None:
        """Fill signature image paths from configured signer names when needed.

        When a signer name is supplied but neither an uploaded image nor a
        signature-library match is available, surface a warning so the operator
        is prompted instead of silently shipping a blank signature slot.
        """
        bindings = (
            ("detector", "issuer", "detector_signature_image_path", "检测者"),
            ("reviewer", "reviewer", "reviewer_signature_image_path", "审核者"),
        )
        for role, name_field, path_field, label in bindings:
            current_path = str(report_data.get_field(path_field) or "").strip()
            if current_path:
                continue
            signer_name = str(report_data.get_field(name_field) or "").strip()
            if not signer_name:
                continue
            resolved = resolve_signature_path(self.config_dir, role, signer_name)
            if resolved:
                report_data.set_field(path_field, resolved)
            else:
                report_data.add_validation_error(
                    f"{label}「{signer_name}」在签名库中无对应签名图，"
                    f"签名区将留空；请在签名库登记该人员，或上传临时签名图后重新生成。"
                )

    @staticmethod
    def _resolve_panel_reviewed_part3_overlay(panel_package: Any) -> Optional[str]:
        """Resolve the active panel's own reviewed Part-3 knowledge overlay.

        Returns the path string when the panel package declares a
        ``reviewed_part3_knowledge`` rule (panel.yaml ``rules``), else ``None``.
        Panel-scoping this overlay (instead of one global CRC file applied to
        every panel) keeps CRC panels on the CRC reviewed wording while non-CRC
        panels get no overlay and fall back to the base (de-identified) KB.
        """
        if panel_package is None:
            return None
        raw = getattr(panel_package, "raw", None) or {}
        declared = raw.get("reviewed_part3_overlay")
        if not declared:
            return None
        try:
            path = panel_package._resolve_path(str(declared))
        except Exception:
            return None
        try:
            return str(path) if path is not None and path.exists() else None
        except Exception:
            return None

    @classmethod
    def _resolve_panel_reviewed_part3_overlays(cls, panel_package: Any) -> list[str]:
        """Resolve the base overlay plus optional panel-specific additions."""
        if panel_package is None:
            return []
        paths: list[str] = []
        primary = cls._resolve_panel_reviewed_part3_overlay(panel_package)
        if primary:
            paths.append(primary)
        raw = getattr(panel_package, "raw", None) or {}
        additions = raw.get("reviewed_part3_overlay_additions") or []
        if isinstance(additions, str):
            additions = [additions]
        for declared in additions if isinstance(additions, list) else []:
            try:
                path = panel_package._resolve_path(str(declared))
            except Exception:
                continue
            if path is not None and path.exists() and str(path) not in paths:
                paths.append(str(path))
        return paths

    def _stage_panel_rule_execution(
        self,
        stage: StageHandle,
        state: _GenerationState,
    ) -> None:
        if state.excel_data is None or state.report_data is None:
            raise RuntimeError("Report data is unavailable before panel rule execution.")

        gene_knowledge_provider = None
        panel_raw = getattr(state.panel_package, "raw", None) or {}
        part3_policy = panel_raw.get("part3_knowledge") or {}
        part3_enabled = bool(part3_policy.get("enabled", True))
        if not part3_enabled:
            disabled_notice = str(
                part3_policy.get("disabled_notice")
                or "第三部分医学知识尚未完成审核，当前版本不输出相关解释。"
            ).strip()
            state.report_data.set_field("part3_knowledge_status", "disabled")
            state.report_data.set_field("part3_disabled_notice", disabled_notice)
            stage.metrics["part3_knowledge_enabled"] = False
        else:
            try:
                kb_enabled = bool(
                    self.config_loader.get_setting(
                        "knowledge_bases.gene_knowledge_db.enabled", False
                    )
                ) or bool(
                    self.config_loader.get_setting(
                        "knowledge_bases.gene_transcript_db.enabled", False
                    )
                )
                if kb_enabled:
                    from reportgen.knowledge import (  # lazy import
                        GeneKnowledgeProvider,
                        load_panel_knowledge_redactions,
                    )

                    kb_cfg = self.config_loader.get_setting("knowledge_bases", {}) or {}
                    # Panel-scope the reviewed Part-3 overlay: each panel uses its
                    # own reviewed_part3_knowledge (declared in panel.yaml rules).
                    # Panels that don't declare one get NO overlay instead of
                    # inheriting the global CRC file — so non-CRC panels
                    # (lung/endometrial) no longer pick up colorectal wording.
                    gene_kb_cfg = dict(kb_cfg.get("gene_knowledge_db", {}) or {})
                    gene_kb_cfg["reviewed_part3_overlay_path"] = ""
                    gene_kb_cfg["reviewed_part3_overlay_paths"] = (
                        self._resolve_panel_reviewed_part3_overlays(
                            state.panel_package
                        )
                    )
                    provider_cfg = {
                        "enabled": True,
                        "panel_id": state.canonical_project_type,
                        "gene_symbol_aliases": (
                            panel_raw.get("gene_symbol_aliases")
                            or {}
                        ),
                        "gene_knowledge_db": gene_kb_cfg,
                        "gene_transcript_db": kb_cfg.get("gene_transcript_db", {}),
                        "knowledge_redactions": (
                            load_panel_knowledge_redactions(
                                state.panel_package
                            )
                        ),
                    }
                    gene_knowledge_provider = GeneKnowledgeProvider(provider_cfg)
                stage.metrics["part3_knowledge_enabled"] = bool(
                    gene_knowledge_provider
                )
            except Exception as kb_err:
                gene_knowledge_provider = None
                stage.warn("GENE_KNOWLEDGE_PROVIDER_UNAVAILABLE", str(kb_err))

        self.logger.log_event(
            "template_enhancement_started",
            project_type=state.canonical_project_type,
        )
        enhancer = get_enhancer(state.canonical_project_type)
        state.report_data = enhancer.enhance(
            state.report_data,
            state.excel_data,
            field_mapper=self.field_mapper,
            gene_knowledge_provider=gene_knowledge_provider,
            base_path=str(Path(self.config_dir).parent),
            project_type=state.canonical_project_type,
            panel_package=state.panel_package,
        )
        pdl1_product_contract = load_pdl1_product_contract(
            state.panel_package
        )
        apply_pdl1_product_display_fields(
            state.report_data,
            pdl1_product_contract,
        )
        apply_pdl1_display_fields(state.report_data)
        self._apply_clinical_diagnosis_for_display(state.report_data)
        self.logger.log_event(
            "template_enhancement_completed",
            variants=len(state.report_data.get_table("variants") or []),
            summary_variants=len(state.report_data.get_table("summary_variants") or []),
            undetected_genes=len(state.report_data.get_table("undetected_genes") or []),
        )

        consultation_phone = str(
            state.report_content.get("consultation_phone", "") or ""
        ).strip()
        consultation_template = str(
            state.report_content.get(
                "consultation_line_template",
                "咨询电话：{phone}。",
            )
            or ""
        ).strip()
        if consultation_phone and consultation_template:
            try:
                consultation_line = consultation_template.format(
                    phone=consultation_phone
                )
            except Exception:
                consultation_line = consultation_template
            state.report_data.set_field("consultation_phone", consultation_phone)
            state.report_data.set_field("consultation_line", consultation_line)
        state.report_data.set_field(
            "show_hla_table",
            bool(state.report_content.get("show_hla_table", False)),
        )

        self._set_patient_salutation(state.report_data)
        stage.metrics.update(
            {
                "variants": len(state.report_data.get_table("variants") or []),
                "summary_variants": len(
                    state.report_data.get_table("summary_variants") or []
                ),
                "undetected_genes": len(
                    state.report_data.get_table("undetected_genes") or []
                ),
            }
        )

    def _stage_input_contract_validation(
        self,
        stage: StageHandle,
        state: _GenerationState,
        start_time: float,
    ) -> Optional[dict]:
        if state.report_data is None:
            raise RuntimeError("Report data is unavailable before input validation.")

        if not state.report_data.is_valid():
            self.logger.warning(
                "报告数据验证失败", errors=state.report_data.validation_errors
            )
            stage.warn(
                "REPORT_DATA_VALIDATION_WARNINGS",
                "Report data has validation warnings.",
                details={"warnings": list(state.report_data.validation_errors)},
            )

        # Panel-declared biomarkers are production input requirements, not
        # optional QA hints. Enforce them even when the caller uses the legacy
        # non-strict mode, otherwise a parser miss can silently become
        # “未检测” in two separate report sections.
        panel_contract = (
            state.panel_package.input_contract
            if state.panel_package is not None
            else {}
        )
        biomarker_contracts = (
            panel_contract.get("biomarkers")
            if isinstance(panel_contract, dict)
            else {}
        ) or {}
        biomarker_failures = validate_panel_biomarker_contracts(
            state.report_data,
            biomarker_contracts,
        )
        if biomarker_failures:
            duration = time.time() - start_time
            error_msg = "Panel 必检生物标志物缺失或无法解析，阻断报告生成"
            stage.fail(
                "PANEL_REQUIRED_BIOMARKER_MISSING",
                error_msg,
                details={"failures": biomarker_failures},
            )
            self.logger.error(error_msg, failures=biomarker_failures)
            return {
                "success": False,
                "output_file": None,
                "duration": duration,
                "errors": [error_msg],
                "warnings": state.report_data.validation_errors,
                "panel_package_validation": state.panel_package_validation,
            }

        pdl1_contract = load_pdl1_product_contract(state.panel_package)
        pdl1_failures = validate_pdl1_product_contract(
            state.report_data,
            pdl1_contract,
        )
        if pdl1_failures:
            duration = time.time() - start_time
            error_msg = (
                "PD-L1检测方案或逐病例来源尚未满足产品合同，"
                "阻断报告生成"
            )
            stage.fail(
                "PANEL_PDL1_PRODUCT_CONTRACT_BLOCKED",
                error_msg,
                details={"failures": pdl1_failures},
            )
            self.logger.error(error_msg, failures=pdl1_failures)
            return {
                "success": False,
                "output_file": None,
                "duration": duration,
                "errors": [error_msg],
                "warnings": state.report_data.validation_errors,
                "panel_package_validation": state.panel_package_validation,
            }

        if state.strict_mode:
            missing_critical = self._check_critical_fields(state.report_data)
            if missing_critical:
                duration = time.time() - start_time
                error_msg = f"严格模式：缺失关键字段 {missing_critical}，阻断生成"
                stage.fail(
                    "STRICT_MODE_MISSING_CRITICAL_FIELDS",
                    error_msg,
                    details={"missing_fields": missing_critical},
                )
                self.logger.error(error_msg)
                return {
                    "success": False,
                    "output_file": None,
                    "duration": duration,
                    "errors": [error_msg],
                    "warnings": state.report_data.validation_errors,
                    "panel_package_validation": state.panel_package_validation,
                }

            missing_important = self._check_important_fields(state.report_data)
            if missing_important:
                self.logger.warning(
                    "严格模式：缺失重要字段（不阻断）",
                    missing_fields=missing_important,
                )
                stage.warn(
                    "STRICT_MODE_MISSING_IMPORTANT_FIELDS",
                    "Important fields are missing but do not block generation.",
                    details={"missing_fields": missing_important},
                )

        return None

    def _stage_output_path(self, stage: StageHandle, state: _GenerationState) -> None:
        if state.excel_data is None or state.report_data is None:
            raise RuntimeError("Report data is unavailable before output path setup.")

        if not state.output_filename:
            state.output_filename = self._generate_output_filename(
                state.excel_data,
                state.report_data,
            )

        max_len = self.config_loader.get_setting("naming.max_filename_length", 200)
        illegal_replace = self.config_loader.get_setting(
            "naming.illegal_chars_replace", "_"
        )
        state.output_filename = safe_filename(
            state.output_filename,
            max_length=int(max_len),
            replacement=str(illegal_replace),
        )

        ensure_directory_exists(state.output_dir)

        overwrite_existing = bool(
            self.config_loader.get_setting("generation.output.overwrite_existing", False)
        )
        if not overwrite_existing:
            state.output_filename = get_unique_filename(
                state.output_dir,
                state.output_filename,
            )

        state.output_path = str(Path(state.output_dir) / state.output_filename)
        state.generation_id = Path(state.output_path).stem
        stage.artifacts["output_path"] = state.output_path
        stage.artifacts["generation_id"] = state.generation_id
        stage.metrics["overwrite_existing"] = overwrite_existing

    def _stage_template_contract(
        self,
        stage: StageHandle,
        state: _GenerationState,
        start_time: float,
    ) -> Optional[dict]:
        if state.report_data is None:
            raise RuntimeError("Report data is unavailable before template contract.")

        state.template_context = self.template_renderer.build_context(state.report_data)
        state.template_context["project_type"] = state.canonical_project_type
        state.template_context["_require_deterministic_layout"] = (
            state.canonical_project_type
            in {"crc_301", "crc_301_msi", "crc_358", "crc_358_msi"}
        )
        template_contract_spec = self._get_template_contract_spec(state.panel_package)

        state.template_contract_mode = str(
            state.template_contract_mode or "none"
        ).lower()
        if state.template_contract_mode not in {"none", "warn", "fail"}:
            raise ValueError(
                "template_contract_mode must be one of: none|warn|fail "
                f"(got {state.template_contract_mode!r})"
            )

        state.template_contract_report = None
        required_markers = (
            list(template_contract_spec.get("required_markers") or [])
            if isinstance(template_contract_spec, dict)
            else []
        )
        state.template_context["required_structural_markers"] = required_markers
        state.report_data.set_field(
            "required_structural_markers",
            required_markers,
        )
        if state.template_contract_mode == "none" and not required_markers:
            stage.skip(message="Template contract validation is disabled.")
            return None

        state.template_contract_report = self.template_renderer.validate_template_contract(
            state.template_file,
            state.template_context,
            contract_spec=template_contract_spec,
        )
        stage.metrics["ok"] = bool(state.template_contract_report.get("ok", False))
        declared_contract = state.template_contract_report.get("declared_contract") or {}

        # Structural Part 3 requirements are safety gates, not advisory template
        # warnings. They remain blocking even when the caller selected the
        # historical "warn" contract mode.
        structural_errors: list[str] = []
        missing_markers = list(
            declared_contract.get("missing_required_markers") or []
        )
        duplicate_markers = list(
            declared_contract.get("duplicate_required_markers") or []
        )
        if missing_markers:
            structural_errors.append(f"missing markers: {missing_markers}")
        if duplicate_markers:
            structural_errors.append(f"duplicate markers: {duplicate_markers}")

        if "__PART3_MARKER__" in required_markers:
            processor_names = self._get_template_processor_names(
                state.panel_package,
                state.template_file,
            )
            if "part3_formatted_sections" not in (processor_names or ()):
                structural_errors.append(
                    "required Part 3 processor is not declared"
                )
            try:
                total_variants = int(
                    float(state.template_context.get("total_variants_count") or 0)
                )
            except (TypeError, ValueError):
                total_variants = 0
            gene_sections = state.template_context.get("gene_knowledge_sections")
            expected_variant_keys = [
                str(value).strip()
                for value in (
                    state.template_context.get("part3_expected_variant_keys") or []
                )
                if str(value).strip()
            ]
            rendered_variant_keys = [
                str(value).strip()
                for value in (
                    state.template_context.get("part3_rendered_variant_keys") or []
                )
                if str(value).strip()
            ]
            part3_explicitly_disabled = (
                str(
                    state.template_context.get("part3_knowledge_status") or ""
                ).strip().lower()
                == "disabled"
                and bool(
                    str(
                        state.template_context.get("part3_disabled_notice") or ""
                    ).strip()
                )
            )
            if expected_variant_keys:
                missing_variant_keys = sorted(
                    set(expected_variant_keys) - set(rendered_variant_keys)
                )
                unexpected_variant_keys = sorted(
                    set(rendered_variant_keys) - set(expected_variant_keys)
                )
                if (
                    missing_variant_keys
                    or unexpected_variant_keys
                    or len(rendered_variant_keys) != len(expected_variant_keys)
                ):
                    structural_errors.append(
                        "Part 3 variant coverage mismatch: "
                        f"expected={len(expected_variant_keys)}, "
                        f"rendered={len(rendered_variant_keys)}, "
                        f"missing={missing_variant_keys}, "
                        f"unexpected={unexpected_variant_keys}"
                    )
            elif (
                total_variants > 0
                and not gene_sections
                and not part3_explicitly_disabled
            ):
                structural_errors.append(
                    "variants are present but gene_knowledge_sections is empty"
                )
            stage.metrics["part3_explicitly_disabled"] = (
                part3_explicitly_disabled
            )

        if structural_errors:
            duration = time.time() - start_time
            msg = "Part 3 结构契约校验失败，已阻断生成：" + "; ".join(
                structural_errors
            )
            details = {
                "required_markers": required_markers,
                "missing_required_markers": missing_markers,
                "duplicate_required_markers": duplicate_markers,
                "structural_errors": structural_errors,
                "part3_expected_variant_keys": state.template_context.get(
                    "part3_expected_variant_keys"
                ),
                "part3_rendered_variant_keys": state.template_context.get(
                    "part3_rendered_variant_keys"
                ),
            }
            stage.fail("PART3_CONTRACT_FAILED", msg, details=details)
            self.logger.error(msg)
            return {
                "success": False,
                "output_file": None,
                "duration": duration,
                "errors": [msg],
                "warnings": state.report_data.validation_errors,
                "panel_package_validation": state.panel_package_validation,
                "template_contract": state.template_contract_report,
                **(
                    {"context": state.template_context}
                    if state.return_context
                    else {}
                ),
            }

        if state.template_contract_mode == "none":
            stage.skip(
                message="General template contract validation is disabled; required structural markers passed."
            )
            return None

        if state.template_contract_report.get("ok", False):
            return None

        missing_paths = state.template_contract_report.get("missing_paths")
        missing_lists = state.template_contract_report.get("missing_lists")
        missing_row_fields = state.template_contract_report.get("missing_row_fields")
        msg = (
            "模板契约校验失败：模板引用或声明式结构不满足要求。"
            f" missing_paths={missing_paths},"
            f" missing_lists={missing_lists},"
            f" missing_row_fields={missing_row_fields}"
            f" declared_contract={declared_contract}"
        )
        details = {
            "missing_paths": missing_paths,
            "missing_lists": missing_lists,
            "missing_row_fields": missing_row_fields,
        }
        if state.template_contract_mode == "fail":
            duration = time.time() - start_time
            stage.fail("TEMPLATE_CONTRACT_FAILED", msg, details=details)
            self.logger.error(msg)
            return {
                "success": False,
                "output_file": None,
                "duration": duration,
                "errors": [msg],
                "warnings": state.report_data.validation_errors,
                "panel_package_validation": state.panel_package_validation,
                "template_contract": state.template_contract_report,
                **({"context": state.template_context} if state.return_context else {}),
            }

        stage.warn("TEMPLATE_CONTRACT_WARN", msg, details=details)
        self.logger.warning(msg)
        return None

    def _stage_template_render(self, stage: StageHandle, state: _GenerationState) -> None:
        if state.report_data is None or state.output_path is None:
            raise RuntimeError("Report data is unavailable before template rendering.")

        self.logger.log_event("template_rendering_started", output=state.output_path)
        state.final_output = self.template_renderer.render(
            state.template_file,
            state.report_data,
            state.output_path,
            post_processor_names=self._get_template_processor_names(
                state.panel_package,
                state.template_file,
            ),
            critical_processor_names=critical_docx_processor_names(
                state.canonical_project_type
            ),
            template_context=state.template_context,
        )
        state.processor_report = list(
            getattr(self.template_renderer, "last_processor_report", []) or []
        )
        self.logger.log_event("template_rendering_completed", output=state.final_output)
        stage.artifacts["output_file"] = state.final_output
        stage.metrics["post_processors"] = len(state.processor_report)
        state.template_processor_names = self._get_template_processor_names(
            state.panel_package,
            state.template_file,
        )
        stage.metrics["declared_processors"] = list(
            state.template_processor_names or []
        )

    def _stage_field_provenance(
        self,
        stage: StageHandle,
        state: _GenerationState,
    ) -> None:
        if (
            state.final_output is None
            or state.report_data is None
            or state.excel_data is None
        ):
            raise RuntimeError("Rendered report is unavailable before provenance.")

        try:
            state.field_provenance = build_field_provenance_report(
                output_file=state.final_output,
                report_data=state.report_data,
                excel_data=state.excel_data,
                config_loader=self.config_loader,
                project_type=state.canonical_project_type,
                project_name=state.project_name,
                template_file=state.template_file,
                generation_id=state.generation_id or Path(state.final_output).stem,
            )
            state.field_provenance_file = write_field_provenance_report(
                state.field_provenance,
                state.final_output,
            )
            self.logger.log_event(
                "field_provenance_generated",
                output=state.field_provenance_file,
                field_count=len(state.field_provenance.get("fields") or {}),
            )
            stage.artifacts["field_provenance_file"] = state.field_provenance_file
            stage.metrics["field_count"] = len(
                state.field_provenance.get("fields") or {}
            )
        except Exception as provenance_err:
            self.logger.warning("生成字段来源报告失败", error=str(provenance_err))
            stage.warn("FIELD_PROVENANCE_FAILED", str(provenance_err))

    def _stage_qa(self, stage: StageHandle, state: _GenerationState) -> None:
        if state.final_output is None or state.report_data is None:
            raise RuntimeError("Rendered report is unavailable before QA.")

        try:
            visual_opts = self._resolve_visual_qa_options(state)
            state.qa_report = build_docx_qa_report(
                output_file=state.final_output,
                report_data=state.report_data,
                project_type=state.canonical_project_type,
                project_name=state.project_name,
                template_file=state.template_file,
                generation_id=state.generation_id or Path(state.final_output).stem,
                field_provenance=state.field_provenance,
                field_provenance_file=state.field_provenance_file,
                processor_report=state.processor_report,
                template_contract=state.template_contract_report,
                rule_provenance=state.rule_provenance,
                visual_render=visual_opts["mode"],
                visual_render_required=visual_opts["required"],
                visual_render_dpi=visual_opts["dpi"],
                visual_render_timeout_seconds=visual_opts["timeout_seconds"],
                visual_render_output_dir=visual_opts["output_dir"],
                visual_render_tmp_dir=visual_opts["tmp_dir"],
            )
            state.qa_report_file = write_docx_qa_report(
                state.qa_report,
                state.final_output,
            )
            self.logger.log_event(
                "qa_report_generated",
                output=state.qa_report_file,
                status=state.qa_report.get("status"),
                issue_count=len(state.qa_report.get("issues") or []),
            )
            stage.artifacts["qa_report_file"] = state.qa_report_file
            stage.metrics.update(
                {
                    "qa_status": state.qa_report.get("status"),
                    "issue_count": len(state.qa_report.get("issues") or []),
                }
            )
            if state.qa_report.get("status") == "FAIL":
                stage.fail(
                    "QA_REPORT_FAILED",
                    "Generated report QA status is FAIL.",
                    details={
                        "issue_count": len(state.qa_report.get("issues") or [])
                    },
                )
            elif state.qa_report.get("status") == "WARN":
                stage.warn(
                    "QA_REPORT_WARN",
                    "Generated report QA status is WARN.",
                    details={
                        "issue_count": len(state.qa_report.get("issues") or [])
                    },
                )
        except Exception as qa_err:
            self.logger.warning("生成QA报告失败", error=str(qa_err))
            stage.warn("QA_REPORT_GENERATION_FAILED", str(qa_err))

    def _stage_report_summary(
        self,
        stage: StageHandle,
        state: _GenerationState,
    ) -> None:
        if state.final_output is None or state.report_data is None:
            raise RuntimeError("Rendered report is unavailable before summary.")

        try:
            state.report_summary = build_report_summary(
                report_data=state.report_data,
                project_type=state.canonical_project_type,
                project_name=state.project_name,
                panel_status=self._panel_status(state.panel_package),
                template_status=self._template_status(
                    state.panel_package,
                    state.template_file,
                ),
                generation_id=state.generation_id or Path(state.final_output).stem,
                output_file=state.final_output,
                qa_report=state.qa_report,
                warnings=state.report_data.validation_errors,
            )
            state.report_summary_file = write_report_summary(
                state.report_summary,
                state.final_output,
            )
            self.logger.log_event(
                "report_summary_generated",
                output=state.report_summary_file,
                variant_count=state.report_summary.get("variants", {}).get("total"),
            )
            stage.artifacts["report_summary_file"] = state.report_summary_file
            stage.metrics.update(
                {
                    "variant_count": state.report_summary.get("variants", {}).get(
                        "total"
                    ),
                    "drug_related_count": state.report_summary.get(
                        "variants", {}
                    ).get("drug_related"),
                    "qa_status": state.report_summary.get("qa", {}).get("status"),
                }
            )
        except Exception as summary_err:
            self.logger.warning("生成报告结果摘要失败", error=str(summary_err))
            stage.warn("REPORT_SUMMARY_FAILED", str(summary_err))

    @staticmethod
    def _panel_status(panel_package: Any) -> Optional[str]:
        if panel_package is None:
            return None
        raw = getattr(panel_package, "raw", None)
        if isinstance(raw, dict):
            status = ReportGenerator._clean_status(raw.get("status"))
            if status:
                return status
        return ReportGenerator._clean_status(getattr(panel_package, "status", None))

    @staticmethod
    def _template_status(
        panel_package: Any,
        template_file: Optional[str],
    ) -> Optional[str]:
        if panel_package is None:
            return None

        if template_file:
            requested = Path(template_file).resolve()
            for template_id, template in (
                getattr(panel_package, "templates", None) or {}
            ).items():
                try:
                    resolved = panel_package.resolve_template_file(template_id).resolve()
                except Exception:
                    continue
                if resolved == requested:
                    return ReportGenerator._clean_status(
                        getattr(template, "status", None)
                    )

        try:
            return ReportGenerator._clean_status(
                getattr(panel_package.default_template, "status", None)
            )
        except Exception:
            return None

    @staticmethod
    def _clean_status(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _build_success_payload(
        self,
        state: _GenerationState,
        duration: float,
    ) -> dict:
        if state.report_data is None:
            raise RuntimeError("Report data is unavailable when building result.")
        return {
            "success": True,
            "output_file": state.final_output,
            "duration": duration,
            "errors": [],
            "warnings": state.report_data.validation_errors,
            "panel_package_validation": state.panel_package_validation,
            "rule_provenance": state.rule_provenance,
            "template_contract": state.template_contract_report,
            "field_provenance": state.field_provenance,
            "field_provenance_file": state.field_provenance_file,
            "post_processors": state.processor_report,
            "qa_report": state.qa_report,
            "qa_report_file": state.qa_report_file,
            "qa_status": state.qa_report.get("status") if state.qa_report else None,
            "report_summary": state.report_summary,
            "report_summary_file": state.report_summary_file,
            "generation_id": state.generation_id,
            **({"context": state.template_context} if state.return_context else {}),
        }

    @staticmethod
    def _get_panel_registration(project_type: Optional[str]):
        """Return the panel registry entry for a canonical project type."""
        if not str(project_type or "").strip():
            return None
        try:
            return get_panel_registry().get(project_type)
        except Exception:
            return None

    @staticmethod
    def _get_panel_processor_names(panel_package) -> Optional[tuple[str, ...]]:
        """Return panel-declared processor names.

        ``None`` means legacy/default chain. An empty tuple is intentional and
        disables post-render processors for packages that do not need DOCX
        surgery.
        """
        if panel_package is None:
            return None
        processors = getattr(panel_package, "processors", None)
        if processors is None:
            return None
        return tuple(str(name) for name in processors)

    @classmethod
    def _get_template_processor_names(
        cls,
        panel_package,
        template_file: Optional[str],
    ) -> Optional[tuple[str, ...]]:
        """Return template-level processors, falling back to panel processors.

        Template-level processors let a golden-template pilot use a much smaller
        DOCX surgery chain while the legacy template keeps the full chain.
        """
        panel_processors = cls._get_panel_processor_names(panel_package)
        if panel_package is None or not template_file:
            return panel_processors

        try:
            selected = Path(template_file).resolve()
        except Exception:
            return panel_processors

        templates = getattr(panel_package, "templates", {}) or {}
        for template in templates.values():
            try:
                candidate = panel_package.resolve_template_file(
                    template.template_id
                ).resolve()
            except Exception:
                continue
            if candidate == selected and template.processors is not None:
                return tuple(str(name) for name in template.processors)
        return panel_processors

    @staticmethod
    def _resolve_visual_qa_options(state: _GenerationState) -> dict[str, Any]:
        """Resolve optional visual QA controls from args, then environment."""

        def first(value: Any, env_name: str, default: Any) -> Any:
            if value is not None:
                return value
            return os.environ.get(env_name, default)

        def as_int(value: Any, default: int) -> int:
            try:
                return int(value)
            except Exception:
                return default

        def as_bool(value: Any, default: bool = False) -> bool:
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in {"1", "true", "yes", "y", "on"}:
                return True
            if text in {"0", "false", "no", "n", "off"}:
                return False
            return default

        return {
            "mode": first(
                state.qa_visual_render,
                "REPORTGEN_QA_VISUAL_RENDER",
                "none",
            ),
            "required": as_bool(
                first(
                    state.qa_visual_render_required,
                    "REPORTGEN_QA_VISUAL_RENDER_REQUIRED",
                    False,
                )
            ),
            "dpi": as_int(
                first(
                    state.qa_visual_render_dpi,
                    "REPORTGEN_QA_VISUAL_RENDER_DPI",
                    120,
                ),
                120,
            ),
            "timeout_seconds": as_int(
                first(
                    state.qa_visual_render_timeout_seconds,
                    "REPORTGEN_QA_VISUAL_RENDER_TIMEOUT",
                    120,
                ),
                120,
            ),
            "output_dir": first(
                state.qa_visual_render_output_dir,
                "REPORTGEN_QA_VISUAL_RENDER_OUTPUT_DIR",
                None,
            ),
            "tmp_dir": first(
                state.qa_visual_render_tmp_dir,
                "REPORTGEN_QA_VISUAL_RENDER_TMPDIR",
                None,
            ),
        }

    @staticmethod
    def _normalize_project_name(
        project_name: Optional[str], project_type: Optional[str] = None
    ) -> Optional[str]:
        """Normalize UI-supplied panel names to the canonical display name.

        Templates append wording such as "检测项目" in prose. Web forms and
        operators sometimes pass a display label that already includes the same
        suffix; stripping it here keeps report copy deterministic without making
        each template compensate for caller-specific phrasing.
        """
        if project_name is None:
            return None
        normalized = str(project_name).strip()
        if not normalized:
            return normalized
        suffixes = ("检测项目",)
        for suffix in suffixes:
            while normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)].strip()
        return normalized

    @staticmethod
    def _load_panel_style_config(panel_package) -> dict:
        """Load optional panel-level visual style rules from style.yaml.

        Legacy panel packages may still keep a ``style`` block in panel_rules;
        keep that as a fallback while M7 migrates rules into dedicated files.
        """
        if panel_package is None:
            return {}
        try:
            import yaml
        except Exception:
            return {}

        for rule_name in ("style", "panel_rules"):
            try:
                rule_file = panel_package.resolve_rule_file(rule_name)
                if not rule_file.exists():
                    continue
                with rule_file.open("r", encoding="utf-8") as fh:
                    rules = yaml.safe_load(fh) or {}
            except Exception:
                continue
            if not isinstance(rules, dict):
                continue
            style = rules.get("style")
            if isinstance(style, dict):
                return style
        return {}

    @staticmethod
    def _get_template_contract_spec(panel_package) -> Optional[dict]:
        """Return the panel-declared template contract for a package."""
        if panel_package is None:
            return None
        spec = getattr(panel_package, "template_contract", None)
        return dict(spec) if isinstance(spec, dict) else None

    @staticmethod
    def _validate_panel_package_for_generation(panel_package) -> Optional[dict]:
        """Run the strict package gate used by report generation."""
        if panel_package is None:
            return None
        panel_yaml = Path(panel_package.root_dir) / "panel.yaml"
        project_root = Path(panel_package.root_dir).resolve().parent.parent
        panels_dir = Path(panel_package.root_dir).resolve().parent
        try:
            return validate_panel_package_path(
                panel_yaml,
                project_root=project_root,
                panels_dir=panels_dir,
            ).to_dict()
        except Exception as exc:
            return {
                "scope": str(panel_yaml),
                "status": "FAIL",
                "ok": False,
                "panels_checked": [getattr(panel_package, "panel_id", "")],
                "summary": {"errors": 1, "warnings": 0, "issues": 1},
                "issues": [
                    {
                        "level": "ERROR",
                        "code": "PANEL_VALIDATION_GATE_ERROR",
                        "message": f"Panel Package validation gate failed: {exc}",
                        "panel_id": getattr(panel_package, "panel_id", ""),
                        "path": str(panel_yaml),
                        "hint": "",
                    }
                ],
            }

    @staticmethod
    def _load_rule_provenance(panel_package) -> Optional[dict[str, Any]]:
        """Load panel-local rule files and return provenance for QA reports."""
        if panel_package is None:
            return None
        try:
            return PanelRuleEngine.from_panel_package(panel_package).provenance
        except Exception as exc:
            return {
                "schema_version": "1.0",
                "panel_id": getattr(panel_package, "panel_id", ""),
                "status": "FAIL",
                "ok": False,
                "file_count": 0,
                "files": [],
                "issues": [
                    {
                        "level": "ERROR",
                        "code": "RULE_PROVENANCE_LOAD_FAILED",
                        "message": f"Panel rule provenance cannot be loaded: {exc}",
                        "path": str(Path(panel_package.root_dir) / "panel.yaml"),
                        "rule_name": "",
                        "rule_id": "",
                        "hint": "",
                    }
                ],
            }

    @staticmethod
    def _load_report_text_rules(panel_package) -> dict[str, str]:
        """Load configured report wording from panel report_text rules."""
        if panel_package is None:
            return {}
        try:
            rule_engine = PanelRuleEngine.from_panel_package(panel_package)
            return collect_report_texts(rule_engine.get("report_text"))
        except Exception:
            return {}

    @staticmethod
    def _format_panel_validation_failure(
        project_type: Optional[str], validation: dict
    ) -> str:
        """Build a concise human-readable generation gate failure."""
        issues = list(validation.get("issues") or [])
        summary = "; ".join(
            f"{item.get('code')}: {item.get('message')}" for item in issues[:5]
        )
        if len(issues) > 5:
            summary += f"; ... plus {len(issues) - 5} more"
        panel = project_type or ",".join(validation.get("panels_checked") or [])
        return f"Panel Package校验失败，已阻断生成：{panel}。{summary}"

    def _generate_output_filename(self, excel_data, report_data: ReportData) -> str:
        """
        生成输出文件名

        Args:
            excel_data: Excel数据源
            report_data: 报告数据

        Returns:
            输出文件名
        """
        pattern = self.config_loader.get_setting("naming.output_pattern", None)
        timestamp_format = self.config_loader.get_setting(
            "naming.timestamp_format", "%Y%m%d_%H%M%S"
        )
        date_format = self.config_loader.get_setting("naming.date_format", "%Y-%m-%d")

        now = datetime.now()
        filename_context = {
            "patient_name": report_data.get_field("patient_name") or "",
            "sample_id": report_data.get_field("sample_id")
            or excel_data.metadata.get("sample_id_from_filename")
            or "",
            "project_name": report_data.get_field("project_name") or "",
            "report_date": report_data.get_field("report_date")
            or now.strftime(date_format),
            "timestamp": now.strftime(timestamp_format),
        }

        filename = None
        if pattern:
            try:
                filename = str(pattern).format(**filename_context)
                # Clean up consecutive underscores and leading/trailing underscores
                # caused by empty fields (e.g. "_MLB123_..." when patient_name is empty)
                import re
                filename = re.sub(r'_+', '_', filename)  # collapse multiple underscores
                filename = filename.lstrip('_')  # remove leading underscore
            except KeyError as e:
                self.logger.warning(
                    "文件名模板包含未知变量，回退默认命名",
                    pattern=pattern,
                    missing_key=str(e),
                )

        # 回退默认命名规则：患者名-样本号-报告.docx
        if not filename:
            parts = []
            if filename_context["patient_name"]:
                parts.append(str(filename_context["patient_name"]))
            if filename_context["sample_id"]:
                parts.append(str(filename_context["sample_id"]))
            if not parts:
                parts.append(Path(excel_data.file_path).stem)
            parts.append("报告")
            filename = "-".join(parts)

        if not filename.lower().endswith(".docx"):
            filename += ".docx"

        self.logger.debug("生成输出文件名", filename=filename)
        return filename

    def _fill_missing_report_date(self, report_data: ReportData) -> None:
        """Fill missing report_date with the generation date."""
        report_date = date.today().isoformat()
        report_data.set_field("report_date", report_date)
        self.logger.warning("report_date缺失，已使用生成报告当天日期", report_date=report_date)

    def _mark_missing_report_date(self, report_data: ReportData) -> None:
        """Backward-compatible wrapper for callers that fill missing report_date."""
        self._fill_missing_report_date(report_data)

    def _set_patient_salutation(self, report_data: ReportData) -> None:
        """Derive the patient-letter salutation from the mapped gender field."""
        gender_text = str(report_data.get_field("gender") or "").strip()
        report_data.set_field(
            "patient_salutation",
            "女士" if "女" in gender_text else "先生",
        )

    def _apply_clinical_diagnosis_for_display(self, report_data: ReportData) -> None:
        """Use clinical_diagnosis for the basic-info display when cancer_type is empty.

        `cancer_type` is also used by drug-knowledge filters. Keeping the displayed
        diagnosis separate prevents form-only diagnosis text from narrowing drug
        evidence lookup unless the caller intentionally sets `cancer_type`.
        """
        diagnosis = str(report_data.get_field("clinical_diagnosis") or "").strip()
        current = str(report_data.get_field("cancer_type") or "").strip()
        if diagnosis and diagnosis not in {"-", "--"} and current in {"", "-", "--"}:
            report_data.set_field("cancer_type", diagnosis)

    def validate_inputs(
        self, excel_file: str, template_file: str, output_dir: str
    ) -> tuple[bool, list[str]]:
        """
        验证输入参数

        Args:
            excel_file: Excel文件路径
            template_file: 模板文件路径
            output_dir: 输出目录

        Returns:
            (是否有效, 错误列表)
        """
        errors = []

        # 验证Excel文件
        from reportgen.utils.validators import validate_excel_file

        is_valid, error = validate_excel_file(excel_file)
        if not is_valid:
            errors.append(f"Excel文件无效: {error}")

        # 验证模板文件
        is_valid, error = self.template_renderer.validate_template(template_file)
        if not is_valid:
            errors.append(f"模板文件无效: {error}")

        # 验证输出目录（可以不存在，会自动创建）
        from reportgen.utils.validators import validate_directory_writable

        if Path(output_dir).exists():
            is_valid, error = validate_directory_writable(output_dir)
            if not is_valid:
                errors.append(f"输出目录无效: {error}")

        return len(errors) == 0, errors

    def _check_critical_fields(self, report_data: ReportData) -> list[str]:
        """
        检查关键字段是否存在

        Args:
            report_data: 报告数据

        Returns:
            缺失的关键字段列表
        """
        missing = []
        for field in self.CRITICAL_FIELDS:
            value = report_data.get_field(field)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                missing.append(field)
        return missing

    def _check_important_fields(self, report_data: ReportData) -> list[str]:
        """
        检查重要字段是否存在

        Args:
            report_data: 报告数据

        Returns:
            缺失的重要字段列表
        """
        missing = []
        for field in self.IMPORTANT_FIELDS:
            value = report_data.get_field(field)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                missing.append(field)
        return missing

    def get_statistics(self) -> dict:
        """
        获取生成器统计信息

        Returns:
            统计信息字典
        """
        return {
            "config_dir": self.config_dir,
            "template_dir": self.template_dir,
            "single_value_mappings": len(self.field_mapper.single_value_mappings),
            "table_mappings": len(self.field_mapper.table_mappings),
        }
