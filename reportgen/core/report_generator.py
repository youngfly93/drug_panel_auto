"""
报告生成器

核心业务逻辑编排，协调所有组件生成报告。
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportgen.config.loader import ConfigLoader
from reportgen.core.data_cleaner import DataCleaner
from reportgen.core.enhancer_registry import (
    get_enhancer,
    get_panel_registry,
    normalize_project_type,
)
from reportgen.core.excel_reader import ExcelReader
from reportgen.core.field_provenance import (
    build_field_provenance_report,
    write_field_provenance_report,
)
from reportgen.core.field_mapper import FieldMapper
from reportgen.core.qa_report import build_docx_qa_report, write_docx_qa_report
from reportgen.core.template_renderer import TemplateRenderer
from reportgen.models.excel_data import ExcelDataSource
from reportgen.models.report_data import ReportData
from reportgen.panels.validation import validate_panel_package_path
from reportgen.utils.file_utils import (
    ensure_directory_exists,
    get_unique_filename,
    safe_filename,
)
from reportgen.utils.logger import get_logger


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

        self.logger.info(
            "开始生成报告",
            excel_file=excel_file,
            template=template_file,
            output_dir=output_dir,
        )

        try:
            canonical_project_type = normalize_project_type(project_type)
            project_name = self._normalize_project_name(
                project_name, canonical_project_type
            )
            panel_registration = self._get_panel_registration(canonical_project_type)
            panel_package = (
                panel_registration.package if panel_registration is not None else None
            )
            panel_package_validation = self._validate_panel_package_for_generation(
                panel_package
            )
            if panel_package_validation and not panel_package_validation.get("ok"):
                duration = time.time() - start_time
                error_msg = self._format_panel_validation_failure(
                    canonical_project_type,
                    panel_package_validation,
                )
                self.logger.error(
                    "Panel Package校验失败，阻断生成",
                    project_type=canonical_project_type,
                    errors=panel_package_validation.get("issues") or [],
                )
                return {
                    "success": False,
                    "output_file": None,
                    "duration": duration,
                    "errors": [error_msg],
                    "warnings": [],
                    "panel_package_validation": panel_package_validation,
                }

            # 1. 读取Excel（支持复用外部已读取的数据，避免重复IO）
            if excel_data is None:
                self.logger.log_event("excel_reading_started", file=excel_file)
                excel_data = self.excel_reader.read(excel_file)
                self.logger.log_event(
                    "excel_reading_completed",
                    file=excel_file,
                    single_values=len(excel_data.single_values),
                    tables=len(excel_data.table_data),
                )
            else:
                if excel_file and str(excel_file) != str(excel_data.file_path):
                    self.logger.warning(
                        "传入的excel_data与excel_file路径不一致，优先使用excel_data.file_path",
                        excel_file=excel_file,
                        excel_data_path=excel_data.file_path,
                    )
                self.logger.log_event(
                    "excel_reading_skipped",
                    file=excel_data.file_path,
                    single_values=len(excel_data.single_values),
                    tables=len(excel_data.table_data),
                )

            # 2. 字段映射
            self.logger.log_event("field_mapping_started")
            report_data = self.field_mapper.map(excel_data)
            self.logger.log_event(
                "field_mapping_completed",
                validation_errors=len(report_data.validation_errors),
            )

            # 3. 数据清洗
            self.logger.log_event("data_cleaning_started")
            report_data = self.data_cleaner.validate_and_clean(report_data)
            self.logger.log_event(
                "data_cleaning_completed",
                validation_errors=len(report_data.validation_errors),
            )

            # 3.5 如果项目检测提供了 project_name，写回上下文覆盖全局默认值
            if project_name and canonical_project_type:
                cur_pn = report_data.get_field("project_name")
                if cur_pn != project_name:
                    report_data.set_field("project_name", project_name)
                    self.logger.info(
                        "项目检测结果覆盖project_name",
                        old=cur_pn,
                        new=project_name,
                    )

            # Report body literals and report-structure switches remain
            # operator-configurable and need to be available during enhancement.
            report_content = self.config_loader.get_setting("report_content", {}) or {}
            if isinstance(report_content, dict):
                report_data.set_field("report_content", report_content)
            panel_style = self._load_panel_style_config(panel_package)
            if panel_style:
                report_data.set_field("panel_style", panel_style)

            # 3.6 358基因模板增强：添加模板特定的表格和字段
            # 可选接入：基因知识库（由 settings.yaml 决定是否启用）
            gene_knowledge_provider = None
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
                    from reportgen.knowledge import GeneKnowledgeProvider  # lazy import

                    kb_cfg = self.config_loader.get_setting("knowledge_bases", {}) or {}
                    provider_cfg = {
                        "enabled": True,
                        "gene_knowledge_db": kb_cfg.get("gene_knowledge_db", {}),
                        "gene_transcript_db": kb_cfg.get("gene_transcript_db", {}),
                    }
                    gene_knowledge_provider = GeneKnowledgeProvider(provider_cfg)
            except Exception:
                # 知识库不可用不影响主流程
                gene_knowledge_provider = None

            self.logger.log_event(
                "template_enhancement_started", project_type=canonical_project_type
            )
            enhancer = get_enhancer(canonical_project_type)
            report_data = enhancer.enhance(
                report_data,
                excel_data,
                field_mapper=self.field_mapper,
                gene_knowledge_provider=gene_knowledge_provider,
                base_path=str(Path(self.config_dir).parent),
                project_type=canonical_project_type,
                panel_package=panel_package,
            )
            self._apply_clinical_diagnosis_for_display(report_data)
            self.logger.log_event(
                "template_enhancement_completed",
                variants=len(report_data.get_table("variants") or []),
                summary_variants=len(report_data.get_table("summary_variants") or []),
                undetected_genes=len(report_data.get_table("undetected_genes") or []),
            )

            consultation_phone = str(
                report_content.get("consultation_phone", "")
                if isinstance(report_content, dict)
                else ""
                or ""
            ).strip()
            consultation_template = str(
                (
                    report_content.get(
                        "consultation_line_template",
                        "咨询电话：{phone}。",
                    )
                    if isinstance(report_content, dict)
                    else "咨询电话：{phone}。"
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
                report_data.set_field("consultation_phone", consultation_phone)
                report_data.set_field("consultation_line", consultation_line)
            report_data.set_field(
                "show_hla_table",
                bool(
                    report_content.get("show_hla_table", False)
                    if isinstance(report_content, dict)
                    else False
                ),
            )

            self._set_patient_salutation(report_data)

            # 检查验证错误
            if not report_data.is_valid():
                self.logger.warning(
                    "报告数据验证失败", errors=report_data.validation_errors
                )
                # 继续生成，但记录警告

            # 4. 严格模式：检查关键字段
            if strict_mode:
                missing_critical = self._check_critical_fields(report_data)
                if missing_critical:
                    duration = time.time() - start_time
                    error_msg = f"严格模式：缺失关键字段 {missing_critical}，阻断生成"
                    self.logger.error(error_msg)
                    return {
                        "success": False,
                        "output_file": None,
                        "duration": duration,
                        "errors": [error_msg],
                        "warnings": report_data.validation_errors,
                    }

                # 检查重要字段（警告但不阻断）
                missing_important = self._check_important_fields(report_data)
                if missing_important:
                    self.logger.warning(
                        "严格模式：缺失重要字段（不阻断）",
                        missing_fields=missing_important,
                    )

            # 4.5 report_date 缺失时显式标记，不静默回填当天日期。
            rd = report_data.get_field("report_date")
            if rd is None or (isinstance(rd, str) and rd.strip() == ""):
                self._mark_missing_report_date(report_data)

            # 5. 生成输出文件名
            if not output_filename:
                output_filename = self._generate_output_filename(
                    excel_data, report_data
                )

            # 确保文件名安全
            max_len = self.config_loader.get_setting("naming.max_filename_length", 200)
            illegal_replace = self.config_loader.get_setting(
                "naming.illegal_chars_replace", "_"
            )
            output_filename = safe_filename(
                output_filename,
                max_length=int(max_len),
                replacement=str(illegal_replace),
            )

            # 确保输出目录存在
            ensure_directory_exists(output_dir)

            # 是否允许覆盖已存在文件（默认：不覆盖，自动生成唯一文件名）
            overwrite_existing = bool(
                self.config_loader.get_setting(
                    "generation.output.overwrite_existing", False
                )
            )
            if not overwrite_existing:
                output_filename = get_unique_filename(output_dir, output_filename)

            output_path = str(Path(output_dir) / output_filename)

            # 5. 构建模板上下文（用于可追溯产物/契约校验）
            template_context = self.template_renderer.build_context(report_data)
            template_contract_spec = self._get_template_contract_spec(panel_package)

            # 5.1 模板契约校验（可选）
            template_contract_mode = str(template_contract_mode or "none").lower()
            if template_contract_mode not in {"none", "warn", "fail"}:
                raise ValueError(
                    "template_contract_mode must be one of: none|warn|fail "
                    f"(got {template_contract_mode!r})"
                )

            template_contract_report = None
            if template_contract_mode != "none":
                template_contract_report = (
                    self.template_renderer.validate_template_contract(
                        template_file,
                        template_context,
                        contract_spec=template_contract_spec,
                    )
                )
                if not template_contract_report.get("ok", False):
                    missing_paths = template_contract_report.get("missing_paths")
                    missing_lists = template_contract_report.get("missing_lists")
                    missing_row_fields = template_contract_report.get(
                        "missing_row_fields"
                    )
                    declared_contract = (
                        template_contract_report.get("declared_contract") or {}
                    )
                    msg = (
                        "模板契约校验失败：模板引用或声明式结构不满足要求。"
                        f" missing_paths={missing_paths},"
                        f" missing_lists={missing_lists},"
                        f" missing_row_fields={missing_row_fields}"
                        f" declared_contract={declared_contract}"
                    )
                    if template_contract_mode == "fail":
                        duration = time.time() - start_time
                        self.logger.error(msg)
                        return {
                            "success": False,
                            "output_file": None,
                            "duration": duration,
                            "errors": [msg],
                            "warnings": report_data.validation_errors,
                            "panel_package_validation": panel_package_validation,
                            "template_contract": template_contract_report,
                            **({"context": template_context} if return_context else {}),
                        }

                    self.logger.warning(msg)

            # 6. 渲染模板
            self.logger.log_event("template_rendering_started", output=output_path)
            final_output = self.template_renderer.render(
                template_file, report_data, output_path
            )
            processor_report = list(
                getattr(self.template_renderer, "last_processor_report", []) or []
            )
            self.logger.log_event("template_rendering_completed", output=final_output)

            # 7. 生成关键字段来源报告。M1 阶段只记录，不阻断出报告。
            field_provenance = None
            field_provenance_file = None
            try:
                field_provenance = build_field_provenance_report(
                    output_file=final_output,
                    report_data=report_data,
                    excel_data=excel_data,
                    config_loader=self.config_loader,
                    project_type=canonical_project_type,
                    project_name=project_name,
                    template_file=template_file,
                    generation_id=Path(final_output).stem,
                )
                field_provenance_file = write_field_provenance_report(
                    field_provenance, final_output
                )
                self.logger.log_event(
                    "field_provenance_generated",
                    output=field_provenance_file,
                    field_count=len(field_provenance.get("fields") or {}),
                )
            except Exception as provenance_err:
                self.logger.warning("生成字段来源报告失败", error=str(provenance_err))

            # 8. 生成机器可读 QA 报告。M1 阶段只记录，不阻断出报告。
            qa_report = None
            qa_report_file = None
            try:
                qa_report = build_docx_qa_report(
                    output_file=final_output,
                    report_data=report_data,
                    project_type=canonical_project_type,
                    project_name=project_name,
                    template_file=template_file,
                    generation_id=Path(final_output).stem,
                    field_provenance=field_provenance,
                    field_provenance_file=field_provenance_file,
                    processor_report=processor_report,
                    template_contract=template_contract_report,
                )
                qa_report_file = write_docx_qa_report(qa_report, final_output)
                self.logger.log_event(
                    "qa_report_generated",
                    output=qa_report_file,
                    status=qa_report.get("status"),
                    issue_count=len(qa_report.get("issues") or []),
                )
            except Exception as qa_err:
                self.logger.warning("生成QA报告失败", error=str(qa_err))

            # 计算耗时
            duration = time.time() - start_time

            self.logger.info(
                "报告生成成功", output=final_output, duration_seconds=f"{duration:.2f}"
            )

            return {
                "success": True,
                "output_file": final_output,
                "duration": duration,
                "errors": [],
                "warnings": report_data.validation_errors,
                "panel_package_validation": panel_package_validation,
                "template_contract": template_contract_report,
                "field_provenance": field_provenance,
                "field_provenance_file": field_provenance_file,
                "post_processors": processor_report,
                "qa_report": qa_report,
                "qa_report_file": qa_report_file,
                "qa_status": qa_report.get("status") if qa_report else None,
                **({"context": template_context} if return_context else {}),
            }

        except Exception as e:
            duration = time.time() - start_time

            self.logger.error(
                "报告生成失败",
                excel_file=excel_file,
                error=str(e),
                duration_seconds=f"{duration:.2f}",
            )

            return {
                "success": False,
                "output_file": None,
                "duration": duration,
                "errors": [str(e)],
                "warnings": [],
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
        """Load optional panel-level visual style rules from panel_rules YAML."""
        if panel_package is None:
            return {}
        try:
            import yaml

            rule_file = panel_package.resolve_rule_file("panel_rules")
            if not rule_file.exists():
                return {}
            with rule_file.open("r", encoding="utf-8") as fh:
                rules = yaml.safe_load(fh) or {}
        except Exception:
            return {}
        if not isinstance(rules, dict):
            return {}
        style = rules.get("style")
        return style if isinstance(style, dict) else {}

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

    def _mark_missing_report_date(self, report_data: ReportData) -> None:
        """Mark missing report_date explicitly instead of silently using today."""
        report_data.set_field("report_date", "未填写")
        if not any(
            str(err).startswith("缺失必填字段: report_date")
            for err in report_data.validation_errors
        ):
            report_data.add_validation_error("缺失必填字段: report_date")
        self.logger.warning("report_date缺失，报告中已标记为未填写")

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
