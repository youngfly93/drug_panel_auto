"""Default DOCX post-render processors.

These processors deliberately wrap the existing TemplateRenderer helper
methods. M1 is a structural migration: preserve output behavior while making
the pipeline order visible and configurable later by panel package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from reportgen.core.processors.base import ProcessorContext


def _env_truthy(name: str) -> bool:
    import os

    return str(os.environ.get(name) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


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
            "rebuild_references",
            "参考文献按引用重建失败",
            lambda c: c.renderer._rebuild_reference_section(
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
            "targeted_drug_brand_summary",
            "靶向药物商品名汇总失败",
            lambda c: c.renderer._apply_targeted_drug_brand_summary(
                c.output_path, c.template_context
            ),
        ),
        FunctionProcessor(
            "immune_table_notes",
            "免疫表条件备注处理失败",
            lambda c: c.renderer._apply_immune_table_notes(
                c.output_path, c.template_context
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
            _run_signature_layout,
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
    ctx.renderer._restore_reviewed_vertical_cell_merges(ctx.output_path)


def _run_toc_refresh(ctx: ProcessorContext) -> None:
    # P1 perf: the actual LO field-refresh here is redundant — the layout
    # modifications in final_refresh_cleanup shift page numbers anyway, and
    # final_refresh_cleanup re-refreshes after. Keeping the LO call here just
    # produces a TOC that gets immediately invalidated. Skip the LO refresh,
    # keep set_update_fields (cheap XML flag, no LO process). Saves ~6 s per
    # report. Set REPORTGEN_KEEP_EARLY_TOC_REFRESH=1 to restore old behavior.
    import os
    try:
        ctx.renderer._set_update_fields(ctx.output_path)
    except Exception:
        pass
    if os.environ.get("REPORTGEN_KEEP_EARLY_TOC_REFRESH") == "1":
        try:
            ctx.renderer._refresh_fields_with_native_engine(ctx.output_path)
        except Exception as refresh_err:
            ctx.logger.warning("目录页码刷新失败，将继续最终刷新兜底", error=str(refresh_err))
        try:
            ctx.renderer._set_update_fields(ctx.output_path)
        except Exception:
            pass


def _run_final_refresh_cleanup(ctx: ProcessorContext) -> None:
    heading_cleanup_targets = (
        "基因变异解析",
        "靶向药物/免疫用药提示解析",
        "3. 阅读说明",
        "2.3 NCCN 推荐临床常规靶向药物相关基因检测结果（不限于本癌种）",
        "2. 结直肠癌诊疗知识",
        "3. 癌症相关信号通路",
        "4. 基因检测列表",
        "5. 参考文献",
        "本次检测质控结果",
    )
    report_content = ctx.template_context.get("report_content") or {}
    forced_page_break_headings = tuple(
        report_content.get("force_page_break_before_headings") or ()
    )

    def enforce_configured_page_breaks() -> None:
        enforce = getattr(
            ctx.renderer, "_enforce_page_break_before_headings", None
        )
        if forced_page_break_headings and callable(enforce):
            enforce(ctx.output_path, forced_page_break_headings)

    ctx.renderer._normalize_final_section_layout(ctx.output_path)
    # The golden template-specific processor list does not run the broad
    # section-spacing pass. Compact only the Part 3 boundary here so the report
    # guide's intentional spacer block remains untouched.
    ctx.renderer._cleanup_section_spacing(
        ctx.output_path,
        ("第三部分：基因变异及相应靶向/免疫药物解析",),
    )
    ctx.renderer._remove_standalone_page_breaks_before_pathway_tables(
        ctx.output_path
    )
    ctx.renderer._compact_gene_list_tables(ctx.output_path, ctx.template_context)
    ctx.renderer._normalize_quality_control_tables(ctx.output_path)
    ctx.renderer._optimize_variant_table_layout(ctx.output_path)
    ctx.renderer._cleanup_trailing_blank_page(ctx.output_path)
    ctx.renderer._remove_blank_page_breaks_before_headings(
        ctx.output_path,
        heading_cleanup_targets,
    )
    enforce_configured_page_breaks()
    if _env_truthy("REPORTGEN_FAST_TOC") or _env_truthy(
        "REPORTGEN_SKIP_FINAL_LO_REFRESH"
    ):
        try:
            ctx.renderer._set_update_fields(ctx.output_path)
        except Exception:
            pass
        try:
            ctx.logger.info(
                "已跳过最终 LibreOffice 目录刷新",
                output=ctx.output_path,
                reason="REPORTGEN_FAST_TOC",
            )
        except Exception:
            pass
    else:
        try:
            ctx.renderer._refresh_fields_with_native_engine(ctx.output_path)
            ctx.renderer._set_update_fields(ctx.output_path)
        except Exception as refresh_err:
            ctx.logger.warning("最终目录页码刷新失败", error=str(refresh_err))
    # LibreOffice can recreate template-owned blank page-break paragraphs while
    # refreshing TOC fields. Re-run the narrow exact-heading cleanup after the
    # refresh, before the final TOC fallback pagination is detected.
    ctx.renderer._remove_blank_page_breaks_before_headings(
        ctx.output_path,
        heading_cleanup_targets,
    )
    enforce_configured_page_breaks()
    ctx.renderer._normalize_toc_decoration_layout(ctx.output_path)
    ctx.renderer._restore_reviewed_body_headers(ctx.output_path)
    # 注：此处不再 _populate_static_toc_page_numbers。该操作要 LibreOffice 把整份
    # 文档转 PDF，为可刷新 PAGEREF 提供一份缓存页码。原先在这里和
    # underlines_and_styles 末尾各跑一次，而本步结果会被后者覆盖。只保留最后
    # 一次，省掉重复的全文档渲染。


def _run_underlines_and_styles(ctx: ProcessorContext) -> None:
    ctx.renderer._remove_template_underlines(ctx.output_path)
    ctx.renderer._restore_variant_summary_table_style(
        ctx.output_path, ctx.template_context
    )
    ctx.renderer._restore_variant_detail_table_style(
        ctx.output_path, ctx.template_context
    )
    ctx.renderer._restore_biomarker_table_style(ctx.output_path, ctx.template_context)
    ctx.renderer._restore_clinical_result_table_style(
        ctx.output_path, ctx.template_context
    )
    ctx.renderer._restore_detection_content_underlines(ctx.output_path)
    ctx.renderer._render_patient_salutation(ctx.output_path, ctx.template_context)
    ctx.renderer._normalize_repeated_terminal_punctuation(ctx.output_path)
    ctx.renderer._restore_patient_letter_fill_underlines(ctx.output_path)
    ctx.renderer._restore_msi_result_emphasis(ctx.output_path, ctx.template_context)
    ctx.renderer._restore_part3_dynamic_styles(ctx.output_path, ctx.template_context)
    bold_brands = getattr(ctx.renderer, "_bold_drug_brand_brackets", None)
    if callable(bold_brands):
        bold_brands(ctx.output_path)
    # LibreOffice/Word field refresh can rewrite image relationships. Render the
    # detector/reviewer signatures as inline images at the very end so they sit
    # cleanly on the label baseline and uploaded signatures remain effective.
    ctx.renderer._render_inline_signatures(ctx.output_path, ctx.template_context)
    ctx.renderer._remove_empty_numbered_paragraphs(ctx.output_path)
    # Final step: recolor the Part 3 intro ❖ bullet to black. Must be last —
    # the field-refresh processors rebuild numbering.xml and re-introduce the
    # template's red marker, so any earlier recolor is overwritten.
    try:
        ctx.renderer._recolor_part3_intro_marker(ctx.output_path)
    except Exception as recolor_err:
        ctx.logger.warning("第三部分装饰符回黑失败", error=str(recolor_err))
    report_content = ctx.template_context.get("report_content") or {}
    force_breaks = getattr(
        ctx.renderer, "_enforce_page_break_before_headings", None
    )
    configured_headings = tuple(
        report_content.get("force_page_break_before_headings") or ()
    )
    if configured_headings and callable(force_breaks):
        force_breaks(ctx.output_path, configured_headings)
    # These are final-output normalizers. They intentionally run after all
    # LibreOffice/TOC refreshes and after other python-docx saves so the direct
    # reference font and floating back-cover coordinates are the final state.
    normalize_references = getattr(
        ctx.renderer, "_normalize_reference_section_style", None
    )
    if callable(normalize_references):
        normalize_references(ctx.output_path, ctx.template_context)
    normalize_back_cover = getattr(
        ctx.renderer, "_normalize_back_cover_artwork", None
    )
    if callable(normalize_back_cover):
        normalize_back_cover(ctx.output_path, ctx.template_context)
    # Pagination must be finalized only after every layout-affecting normalizer
    # above (notably forced section breaks and reference font normalization).
    # Otherwise the cached PAGEREF values describe a pre-final document and can
    # drift by many pages. Do not swallow convergence failures: this processor
    # is release-critical, so the normal processor error path must block the
    # half-finalized report instead of returning it with a warning-only TOC.
    ctx.renderer._populate_static_toc_page_numbers(
        ctx.output_path, ctx.template_context
    )


def _run_signature_placeholders(ctx: ProcessorContext) -> None:
    ctx.renderer._render_signature_placeholder(ctx.output_path, ctx.template_context)


def _run_signature_layout(ctx: ProcessorContext) -> None:
    # Normalize the label line + separate the report date. Inline signature
    # images are rendered at the very end (underlines_and_styles) so they
    # survive the LibreOffice field refreshes that run in between.
    ctx.renderer._normalize_signature_layout(ctx.output_path, ctx.template_context)
