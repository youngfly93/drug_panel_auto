"""Default DOCX post-render processors.

These processors deliberately wrap the existing TemplateRenderer helper
methods. M1 is a structural migration: preserve output behavior while making
the pipeline order visible and configurable later by panel package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from reportgen.core.processors.base import ProcessorContext


@dataclass(frozen=True)
class FunctionProcessor:
    name: str
    warning_message: str
    action: Callable[[ProcessorContext], None]
    enabled_predicate: Callable[[ProcessorContext], bool] = lambda _ctx: True

    def enabled(self, ctx: ProcessorContext) -> bool:
        return self.enabled_predicate(ctx)

    def run(self, ctx: ProcessorContext) -> None:
        self.action(ctx)


def build_default_docx_processors() -> list[FunctionProcessor]:
    """Return the default post-render processor chain in execution order."""
    return [
        FunctionProcessor(
            "empty_table_rows",
            "空表格行清理失败",
            lambda c: c.renderer._cleanup_empty_table_rows(c.output_path),
        ),
        FunctionProcessor(
            "part3_formatted_sections",
            "Part 3 格式化渲染失败",
            lambda c: c.renderer._render_part3_formatted(
                c.output_path, c.template_context
            ),
        ),
        FunctionProcessor(
            "signature_placeholder",
            "签名占位处理失败",
            _run_signature_placeholders,
        ),
        FunctionProcessor(
            "report_content",
            "报告内容后处理失败",
            lambda c: c.renderer._apply_report_content_fixes(
                c.output_path, c.template_context, c.template_path
            ),
        ),
        FunctionProcessor(
            "bullet_lists",
            "项目符号清理失败",
            _run_bullet_lists,
        ),
        FunctionProcessor(
            "signature_layout",
            "签名区布局修复失败",
            lambda c: c.renderer._normalize_signature_layout(
                c.output_path, c.template_context
            ),
        ),
        FunctionProcessor(
            "cover_artifacts",
            "封面残留清理失败",
            lambda c: c.renderer._cleanup_cover_artifacts(c.output_path),
        ),
        FunctionProcessor(
            "section_spacing",
            "章节间距清理失败",
            lambda c: c.renderer._cleanup_section_spacing(c.output_path),
        ),
        FunctionProcessor(
            "front_matter_spacing",
            "首页导读页空白清理失败",
            lambda c: c.renderer._normalize_front_matter_spacing(c.output_path),
        ),
        FunctionProcessor(
            "page_layout",
            "页面布局统一失败",
            lambda c: c.renderer._normalize_final_section_layout(c.output_path),
        ),
        FunctionProcessor(
            "gene_list_and_qc",
            "基因列表/质控表样式修复失败",
            _run_gene_list_and_qc,
        ),
        FunctionProcessor(
            "variant_tables",
            "表格宽度压缩失败",
            _run_variant_tables,
        ),
        FunctionProcessor(
            "hla_tail",
            "尾部HLA表移除失败",
            lambda c: c.renderer._remove_trailing_hla_table(c.output_path),
            enabled_predicate=lambda c: not c.renderer._truthy(
                c.template_context.get("show_hla_table")
            ),
        ),
        FunctionProcessor(
            "blank_page_cleanup",
            "尾部空白页清理失败",
            lambda c: c.renderer._cleanup_trailing_blank_page(c.output_path),
        ),
        FunctionProcessor(
            "toc_refresh",
            "目录页码刷新失败",
            _run_toc_refresh,
        ),
        FunctionProcessor(
            "final_refresh_cleanup",
            "目录刷新后尾部空白页清理失败",
            _run_final_refresh_cleanup,
        ),
        FunctionProcessor(
            "underlines_and_styles",
            "模板下划线清理失败",
            _run_underlines_and_styles,
        ),
    ]


def _run_bullet_lists(ctx: ProcessorContext) -> None:
    ctx.renderer._normalize_multiline_bullet_paragraphs(ctx.output_path)
    ctx.renderer._remove_empty_numbered_paragraphs(ctx.output_path)


def _run_gene_list_and_qc(ctx: ProcessorContext) -> None:
    ctx.renderer._compact_gene_list_tables(ctx.output_path, ctx.template_context)
    ctx.renderer._normalize_quality_control_tables(ctx.output_path)


def _run_variant_tables(ctx: ProcessorContext) -> None:
    ctx.renderer._fit_tables_to_page_width(ctx.output_path)
    ctx.renderer._optimize_variant_table_layout(ctx.output_path)


def _run_toc_refresh(ctx: ProcessorContext) -> None:
    try:
        ctx.renderer._set_update_fields(ctx.output_path)
    except Exception:
        pass
    try:
        ctx.renderer._refresh_fields_with_native_engine(ctx.output_path)
    except Exception as refresh_err:
        ctx.logger.warning("目录页码刷新失败，将继续最终刷新兜底", error=str(refresh_err))
    try:
        ctx.renderer._set_update_fields(ctx.output_path)
    except Exception:
        pass


def _run_final_refresh_cleanup(ctx: ProcessorContext) -> None:
    ctx.renderer._normalize_final_section_layout(ctx.output_path)
    ctx.renderer._compact_gene_list_tables(ctx.output_path, ctx.template_context)
    ctx.renderer._normalize_quality_control_tables(ctx.output_path)
    ctx.renderer._optimize_variant_table_layout(ctx.output_path)
    ctx.renderer._cleanup_trailing_blank_page(ctx.output_path)
    ctx.renderer._remove_blank_page_breaks_before_headings(
        ctx.output_path,
        (
            "2. 结直肠癌诊疗知识",
            "3. 癌症相关信号通路",
            "4. 基因检测列表",
            "5. 参考文献",
        ),
    )
    try:
        ctx.renderer._refresh_fields_with_native_engine(ctx.output_path)
        ctx.renderer._set_update_fields(ctx.output_path)
    except Exception as refresh_err:
        ctx.logger.warning("最终目录页码刷新失败", error=str(refresh_err))
    ctx.renderer._normalize_toc_decoration_layout(ctx.output_path)
    ctx.renderer._restore_reviewed_body_headers(ctx.output_path)
    ctx.renderer._populate_static_toc_page_numbers(ctx.output_path, ctx.template_context)


def _run_underlines_and_styles(ctx: ProcessorContext) -> None:
    ctx.renderer._remove_template_underlines(ctx.output_path)
    ctx.renderer._restore_variant_summary_table_style(
        ctx.output_path, ctx.template_context
    )
    ctx.renderer._restore_variant_detail_table_style(
        ctx.output_path, ctx.template_context
    )
    ctx.renderer._restore_biomarker_table_style(ctx.output_path, ctx.template_context)
    ctx.renderer._restore_detection_content_underlines(ctx.output_path)
    ctx.renderer._restore_patient_letter_fill_underlines(ctx.output_path)


def _run_signature_placeholders(ctx: ProcessorContext) -> None:
    ctx.renderer._render_signature_placeholder(ctx.output_path, ctx.template_context)
    ctx.renderer._replace_signature_anchor_images(ctx.output_path, ctx.template_context)
