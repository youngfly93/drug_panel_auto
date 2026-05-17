"""
模板渲染器

负责使用docxtpl渲染Docx模板。
"""

from pathlib import Path
from typing import Any, Optional

from docx import Document

from reportgen.core.processors import (
    ProcessorContext,
    build_default_docx_processors,
    run_processors,
)
from reportgen.core.template_contract import (
    declared_validation_to_dict,
    extract_template_contract,
    validate_contract,
    validate_declared_contract,
)
from reportgen.models.report_data import ReportData
from reportgen.utils.logger import get_logger
from reportgen.utils.validators import validate_docx_file


class TemplateRenderer:
    """
    模板渲染器

    使用docxtpl将报告数据填充到Docx模板。
    """

    WORD_REFRESH_TIMEOUT_SECONDS = 20

    def __init__(self, log_file: Optional[str] = None, log_level: str = "INFO"):
        """
        初始化模板渲染器

        Args:
            log_file: 日志文件路径
            log_level: 日志级别
        """
        self.logger = get_logger(log_file=log_file, level=log_level)
        self.last_processor_report: list[dict[str, Any]] = []

    def render(
        self, template_path: str, report_data: ReportData, output_path: str
    ) -> str:
        """
        渲染模板并保存

        Args:
            template_path: 模板文件路径
            report_data: 报告数据
            output_path: 输出文件路径

        Returns:
            输出文件路径

        Raises:
            FileNotFoundError: 模板文件不存在
            ValueError: 渲染失败
        """
        # 验证模板文件
        is_valid, error = validate_docx_file(template_path, must_exist=True)
        if not is_valid:
            self.logger.error("模板文件验证失败", template=template_path, error=error)
            raise FileNotFoundError(error)

        # 验证输出路径
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        self.logger.info("开始渲染模板", template=template_path, output=output_path)
        self.last_processor_report = []

        try:
            try:
                from docxtpl import DocxTemplate
            except ModuleNotFoundError as e:
                raise ModuleNotFoundError(
                    "缺少依赖 'docxtpl'，无法渲染docx模板；请先安装 requirements.txt 中的依赖"
                ) from e

            # 加载模板
            doc = DocxTemplate(template_path)

            # 获取模板上下文
            context = self.build_context(report_data)

            self.logger.debug(
                "模板上下文",
                fields=len([k for k, v in context.items() if not isinstance(v, list)]),
                tables=len([k for k, v in context.items() if isinstance(v, list)]),
            )

            # 渲染
            doc.render(context)

            # 保存
            doc.save(output_path)

            self._run_post_render_processors(output_path, context, template_path)

            # 验证生成的文件可以被正常打开
            try:
                Document(output_path)
            except Exception as verify_err:
                self.logger.error(
                    "生成的docx文件无法打开，可能已损坏",
                    output=output_path,
                    error=str(verify_err),
                )
                raise ValueError(f"生成的docx文件无法打开: {verify_err}")

            self.logger.info("模板渲染成功", output=output_path)

            return output_path

        except Exception as e:
            self.logger.error(
                "模板渲染失败", template=template_path, output=output_path, error=str(e)
            )
            raise ValueError(f"模板渲染失败: {e}")

    def build_post_render_processors(self):
        """Build the ordered DOCX post-render processor chain."""
        return build_default_docx_processors()

    def _run_post_render_processors(
        self, output_path: str, context: dict, template_path: str
    ) -> None:
        """Run post-render processors and keep an execution report."""
        processor_context = ProcessorContext(
            renderer=self,
            output_path=output_path,
            template_path=template_path,
            template_context=context,
            logger=self.logger,
        )
        results = run_processors(
            self.build_post_render_processors(), processor_context
        )
        self.last_processor_report = [result.to_dict() for result in results]

        errors = [r for r in self.last_processor_report if r.get("status") == "ERROR"]
        self.logger.info(
            "DOCX后处理完成",
            processors=len(self.last_processor_report),
            errors=len(errors),
        )

    def _normalize_template_context(self, obj):
        """Normalize template context.

        docxtpl/Jinja2 will render None as the string 'None' when used as `{{ var }}`.
        For medical reports this is almost always undesired; normalize missing values
        to empty strings before rendering.
        """
        import math

        if obj is None:
            return ""

        # Handle NaN (float) without importing pandas/numpy
        if isinstance(obj, float):
            try:
                if math.isnan(obj):
                    return ""
            except Exception:
                pass
            return obj

        if isinstance(obj, dict):
            return {k: self._normalize_template_context(v) for k, v in obj.items()}

        if isinstance(obj, list):
            return [self._normalize_template_context(v) for v in obj]

        if isinstance(obj, tuple):
            return tuple(self._normalize_template_context(v) for v in obj)

        return obj

    @staticmethod
    def _truthy(value) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _report_content_config(context: dict | None) -> dict:
        if not isinstance(context, dict):
            return {}
        cfg = context.get("report_content")
        return cfg if isinstance(cfg, dict) else {}

    @staticmethod
    def _float_config(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _format_static_text(text: str, values: dict[str, Any]) -> str:
        try:
            return text.format(**values)
        except Exception:
            return text

    @staticmethod
    def _paragraph_specs(raw: Any) -> list[tuple[str, dict[str, Any]]]:
        specs: list[tuple[str, dict[str, Any]]] = []
        if not isinstance(raw, list):
            return specs

        allowed = {
            "bold",
            "size",
            "color",
            "page_break_before",
            "space_before_pt",
            "space_after_pt",
            "first_line_indent_cm",
            "line_spacing_multiple",
        }
        for item in raw:
            if isinstance(item, str):
                text = item
                options: dict[str, Any] = {}
            elif isinstance(item, dict):
                text = str(item.get("text") or "")
                options = {k: item[k] for k in allowed if k in item}
            else:
                continue
            specs.append((text, options))
        return specs

    def build_context(self, report_data: ReportData) -> dict:
        """Build a normalized template context from ReportData."""
        return self._normalize_template_context(report_data.get_template_context())

    def _remove_template_underlines(self, file_path: str) -> None:
        """Remove explicit run underlines inherited from template placeholders."""
        from docx.oxml.ns import qn

        doc = Document(file_path)
        changed = False

        def remove_underlines(element) -> None:
            nonlocal changed
            for underline in list(element.xpath(".//w:u")):
                if underline.get(qn("w:val")) in {"none", "false", "0"}:
                    continue
                parent = underline.getparent()
                if parent is not None:
                    parent.remove(underline)
                    changed = True

        containers = [doc.element]
        for section in doc.sections:
            containers.extend(
                [
                    section.header._element,
                    section.first_page_header._element,
                    section.even_page_header._element,
                    section.footer._element,
                    section.first_page_footer._element,
                    section.even_page_footer._element,
                ]
            )

        for element in containers:
            remove_underlines(element)

        if changed:
            doc.save(file_path)

    def _normalize_multiline_bullet_paragraphs(self, file_path: str) -> None:
        """Split newline-packed bullet text into separate bullet paragraphs.

        docxtpl renders newline characters inside a placeholder as line breaks in
        the same paragraph. Some reviewed templates reserve blank bullet
        paragraphs after that placeholder, which otherwise become visible empty
        bullet dots after rendering.
        """
        from copy import deepcopy

        from docx.oxml import OxmlElement
        from docx.text.paragraph import Paragraph

        doc = Document(file_path)
        changed = False

        def has_numbering(paragraph) -> bool:
            ppr = paragraph._p.pPr
            return ppr is not None and ppr.numPr is not None

        def non_empty_lines(paragraph) -> list[str]:
            return [
                line.strip()
                for line in (paragraph.text or "").splitlines()
                if line.strip()
            ]

        def set_text(paragraph, text: str) -> None:
            if paragraph.runs:
                paragraph.runs[0].text = text
                for run in paragraph.runs[1:]:
                    run.text = ""
            else:
                paragraph.add_run(text)

        def remove_paragraph(paragraph) -> None:
            element = paragraph._element
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)

        def insert_numbered_after(paragraph, text: str) -> Paragraph:
            new_p = OxmlElement("w:p")
            ppr = paragraph._p.pPr
            if ppr is not None:
                new_p.append(deepcopy(ppr))
            paragraph._p.addnext(new_p)
            inserted = Paragraph(new_p, paragraph._parent)
            inserted.add_run(text)
            return inserted

        paragraphs = list(doc.paragraphs)
        idx = 0
        while idx < len(paragraphs):
            paragraph = paragraphs[idx]
            lines = non_empty_lines(paragraph)
            if not has_numbering(paragraph) or len(lines) <= 1:
                idx += 1
                continue

            set_text(paragraph, lines[0])
            cursor = paragraph
            next_idx = idx + 1

            for line in lines[1:]:
                if (
                    next_idx < len(paragraphs)
                    and has_numbering(paragraphs[next_idx])
                    and not (paragraphs[next_idx].text or "").strip()
                ):
                    cursor = paragraphs[next_idx]
                    set_text(cursor, line)
                    next_idx += 1
                else:
                    cursor = insert_numbered_after(cursor, line)

            while (
                next_idx < len(paragraphs)
                and has_numbering(paragraphs[next_idx])
                and not (paragraphs[next_idx].text or "").strip()
            ):
                remove_paragraph(paragraphs[next_idx])
                next_idx += 1

            changed = True
            paragraphs = list(doc.paragraphs)
            idx += len(lines)

        if changed:
            doc.save(file_path)

    def _remove_empty_numbered_paragraphs(self, file_path: str) -> None:
        """Remove visible empty bullet/numbered paragraphs left by templates."""
        doc = Document(file_path)
        changed = False

        def has_numbering(paragraph) -> bool:
            ppr = paragraph._p.pPr
            return bool(ppr is not None and ppr.numPr is not None)

        def clear_numbering(paragraph) -> bool:
            ppr = paragraph._p.pPr
            if ppr is None or ppr.numPr is None:
                return False
            ppr.remove(ppr.numPr)
            return True

        for paragraph in list(doc.paragraphs):
            if not has_numbering(paragraph):
                continue
            if (paragraph.text or "").strip():
                continue
            parent = paragraph._element.getparent()
            if parent is None:
                continue
            parent.remove(paragraph._element)
            changed = True

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        if (paragraph.text or "").strip():
                            continue
                        if clear_numbering(paragraph):
                            changed = True

        if changed:
            doc.save(file_path)

    def _restore_detection_content_underlines(self, file_path: str) -> None:
        """Restore intentional fill-in underlines in the detection-content sentence."""
        doc = Document(file_path)
        changed = False

        for paragraph in doc.paragraphs:
            text = paragraph.text or ""
            if "对委托人" not in text or "DNA" not in text or "基因进行检测" not in text:
                continue

            in_fill = False
            for run in paragraph.runs:
                run_text = run.text or ""
                if "对委托人" in run_text:
                    in_fill = True
                    if run.font.underline is not None:
                        run.font.underline = None
                        changed = True
                    continue
                if in_fill and run_text.strip().startswith("的"):
                    in_fill = False
                    if run.font.underline is not None:
                        run.font.underline = None
                        changed = True
                    continue
                if in_fill:
                    if run.font.underline is not True:
                        run.font.underline = True
                        changed = True
                elif run.font.underline is not None:
                    run.font.underline = None
                    changed = True

        if changed:
            doc.save(file_path)

    def _restore_variant_summary_table_style(self, file_path: str) -> None:
        """Restore reviewed link-style formatting in the 2.1 variant summary table."""
        from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Cm, Pt, RGBColor

        doc = Document(file_path)
        changed = False

        def is_variant_summary_table(table) -> bool:
            if len(table.columns) != 4 or not table.rows:
                return False
            header = " ".join(cell.text.replace("\n", "") for cell in table.rows[0].cells)
            return (
                "基因" in header
                and "突变位点" in header
                and "潜在获益靶向药物" in header
                and "可能耐药或慎重药物" in header
            )

        def set_cell_shading(cell, fill: str) -> None:
            tc_pr = cell._tc.get_or_add_tcPr()
            shd = tc_pr.find(qn("w:shd"))
            if shd is None:
                shd = OxmlElement("w:shd")
                tc_pr.append(shd)
            shd.set(qn("w:fill"), fill)

        def set_cell_borders(cell) -> None:
            tc_pr = cell._tc.get_or_add_tcPr()
            borders = tc_pr.find(qn("w:tcBorders"))
            if borders is None:
                borders = OxmlElement("w:tcBorders")
                tc_pr.append(borders)
            for side in ("top", "left", "bottom", "right"):
                border = borders.find(qn(f"w:{side}"))
                if border is None:
                    border = OxmlElement(f"w:{side}")
                    borders.append(border)
                border.set(qn("w:val"), "single")
                border.set(qn("w:sz"), "6")
                border.set(qn("w:space"), "0")
                border.set(qn("w:color"), "000000")

        def style_cell(cell, row_idx: int, col_idx: int) -> None:
            header = row_idx == 0
            dash_only = (cell.text or "").strip() in {"-", "--", "—"}
            link_cell = row_idx > 0 and (col_idx == 0 or (col_idx in {2, 3} and not dash_only))

            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_borders(cell)
            if header:
                set_cell_shading(cell, "00C4D8")

            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                paragraph.paragraph_format.space_before = Pt(0)
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.0
                for run in paragraph.runs:
                    run.font.size = Pt(9)
                    if header:
                        run.font.bold = True
                        run.font.underline = False
                        run.font.color.rgb = RGBColor(255, 255, 255)
                    elif link_cell:
                        run.font.bold = False
                        run.font.underline = True
                        run.font.color.rgb = RGBColor(0, 0, 255)
                    else:
                        run.font.bold = False
                        run.font.underline = False
                        run.font.color.rgb = RGBColor(0, 0, 0)

        for table in doc.tables:
            if not is_variant_summary_table(table):
                continue
            for row_idx, row in enumerate(table.rows):
                row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
                if row_idx == 0:
                    row.height = Cm(0.4)
                else:
                    row.height = Cm(0.5)
                for col_idx, cell in enumerate(row.cells):
                    style_cell(cell, row_idx, col_idx)
            changed = True

        if changed:
            doc.save(file_path)

    def _restore_variant_detail_table_style(self, file_path: str) -> None:
        """Restore the reviewed 9-column 2.1 variant-detail table styling."""
        from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Pt, RGBColor

        doc = Document(file_path)
        changed = False

        def is_variant_detail_table(table) -> bool:
            if len(table.columns) != 9 or len(table.rows) < 2:
                return False
            row0 = " ".join(cell.text.replace("\n", "") for cell in table.rows[0].cells)
            row1 = " ".join(cell.text.replace("\n", "") for cell in table.rows[1].cells)
            return (
                "基因名称" in row0
                and "基因突变信息" in row0
                and "靶向药物信息" in row0
                and "转录本号" in row1
                and "潜在获益靶向药物" in row1
            )

        def set_cell_shading(cell, fill: str) -> None:
            tc_pr = cell._tc.get_or_add_tcPr()
            shd = tc_pr.find(qn("w:shd"))
            if shd is None:
                shd = OxmlElement("w:shd")
                tc_pr.append(shd)
            shd.set(qn("w:fill"), fill)

        def set_cell_borders(cell) -> None:
            tc_pr = cell._tc.get_or_add_tcPr()
            borders = tc_pr.find(qn("w:tcBorders"))
            if borders is None:
                borders = OxmlElement("w:tcBorders")
                tc_pr.append(borders)
            for side in ("top", "left", "bottom", "right"):
                border = borders.find(qn(f"w:{side}"))
                if border is None:
                    border = OxmlElement(f"w:{side}")
                    borders.append(border)
                border.set(qn("w:val"), "single")
                border.set(qn("w:sz"), "6")
                border.set(qn("w:space"), "0")
                border.set(qn("w:color"), "000000")

        def set_run_font(run, *, header: bool, link: bool) -> None:
            run.font.name = "微软雅黑"
            run.font.size = Pt(9)
            run.font.bold = True if header else False
            r_pr = run._element.get_or_add_rPr()
            r_fonts = r_pr.rFonts
            if r_fonts is None:
                r_fonts = OxmlElement("w:rFonts")
                r_pr.append(r_fonts)
            r_fonts.set(qn("w:ascii"), "微软雅黑")
            r_fonts.set(qn("w:hAnsi"), "微软雅黑")
            r_fonts.set(qn("w:eastAsia"), "微软雅黑")
            if header:
                run.font.underline = False
                run.font.color.rgb = RGBColor(249, 251, 250)
            elif link:
                run.font.underline = True
                run.font.color.rgb = RGBColor(0, 0, 255)
            else:
                run.font.underline = False
                run.font.color.rgb = RGBColor(0, 0, 0)

        for table in doc.tables:
            if not is_variant_detail_table(table):
                continue
            for row_idx, row in enumerate(table.rows):
                row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
                for col_idx, cell in enumerate(row.cells):
                    header = row_idx in {0, 1}
                    text = (cell.text or "").strip()
                    dash_only = text in {"", "-", "--", "—"}
                    link = row_idx >= 2 and (col_idx == 0 or (col_idx in {7, 8} and not dash_only))
                    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    set_cell_borders(cell)
                    if header:
                        set_cell_shading(cell, "00C4D8")
                    for paragraph in cell.paragraphs:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        paragraph.paragraph_format.space_before = Pt(0)
                        paragraph.paragraph_format.space_after = Pt(0)
                        paragraph.paragraph_format.line_spacing = 1.0
                        for run in paragraph.runs:
                            set_run_font(run, header=header, link=link)
            changed = True

        if changed:
            doc.save(file_path)

    def _restore_biomarker_table_style(self, file_path: str) -> None:
        """Restore template typography for the TMB/MSI biomarker result table."""
        from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Pt, RGBColor

        doc = Document(file_path)
        changed = False

        def is_biomarker_table(table) -> bool:
            if len(table.columns) != 3 or not table.rows:
                return False
            text = "\n".join(cell.text for row in table.rows for cell in row.cells)
            return "TMB/MSI/其它生物标志物检测结果" in text and "用药提示" in text

        def set_cell_shading(cell, fill: str) -> None:
            tc_pr = cell._tc.get_or_add_tcPr()
            shd = tc_pr.find(qn("w:shd"))
            if shd is None:
                shd = OxmlElement("w:shd")
                tc_pr.append(shd)
            shd.set(qn("w:fill"), fill)

        def set_cell_borders(cell) -> None:
            tc_pr = cell._tc.get_or_add_tcPr()
            borders = tc_pr.find(qn("w:tcBorders"))
            if borders is None:
                borders = OxmlElement("w:tcBorders")
                tc_pr.append(borders)
            for side in ("top", "left", "bottom", "right"):
                border = borders.find(qn(f"w:{side}"))
                if border is None:
                    border = OxmlElement(f"w:{side}")
                    borders.append(border)
                border.set(qn("w:val"), "single")
                border.set(qn("w:sz"), "6")
                border.set(qn("w:space"), "0")
                border.set(qn("w:color"), "000000")

        def apply_font(run, *, header: bool) -> None:
            run.font.name = "微软雅黑"
            run.font.size = Pt(10 if header else 9)
            run.font.bold = True if header else False
            run.font.underline = False
            run.font.color.rgb = RGBColor(249, 251, 250) if header else RGBColor(0, 0, 0)
            r_pr = run._element.get_or_add_rPr()
            r_fonts = r_pr.rFonts
            if r_fonts is None:
                r_fonts = OxmlElement("w:rFonts")
                r_pr.append(r_fonts)
            r_fonts.set(qn("w:ascii"), "微软雅黑")
            r_fonts.set(qn("w:hAnsi"), "微软雅黑")
            r_fonts.set(qn("w:eastAsia"), "微软雅黑")

        for table in doc.tables:
            if not is_biomarker_table(table):
                continue
            for row_idx, row in enumerate(table.rows):
                for cell in row.cells:
                    header = row_idx == 0
                    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                    set_cell_borders(cell)
                    if header:
                        set_cell_shading(cell, "00C4D8")
                    for paragraph in cell.paragraphs:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        paragraph.paragraph_format.space_before = Pt(0)
                        paragraph.paragraph_format.space_after = Pt(0)
                        paragraph.paragraph_format.line_spacing = 1.0
                        for run in paragraph.runs:
                            apply_font(run, header=header)
            changed = True

        if changed:
            doc.save(file_path)

    def _apply_report_content_fixes(
        self,
        file_path: str,
        context: dict,
        template_path: str | None = None,
    ) -> None:
        """Apply deterministic report-level fixes that are hard to express in Jinja.

        This keeps one shared template usable for both 358 and 301 CRC reports while
        matching the reviewed final-report layout.
        """
        import os
        import re
        import tempfile
        from zipfile import ZipFile

        from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Cm, Pt

        doc = Document(file_path)
        changed = False
        content_cfg = self._report_content_config(context)

        class ParagraphProxy:
            def __init__(self, element):
                self._p = element

        def iter_all_paragraphs(container):
            for p in container.paragraphs:
                yield p
            for table in container.tables:
                for row in table.rows:
                    for cell in row.cells:
                        yield from iter_all_paragraphs(cell)

        def replace_in_runs(paragraph, replacer) -> bool:
            updated = False
            for run in paragraph.runs:
                old = run.text
                new = replacer(old)
                if new != old:
                    run.text = new
                    updated = True
            return updated

        def set_paragraph_text(paragraph, text: str) -> bool:
            if paragraph.runs:
                paragraph.runs[0].text = text
                for run in paragraph.runs[1:]:
                    run.text = ""
            else:
                paragraph.add_run(text)
            return True

        def remove_paragraph(paragraph) -> bool:
            element = paragraph._element
            parent = element.getparent()
            if parent is None:
                return False
            parent.remove(element)
            return True

        def insert_paragraph_after(
            paragraph,
            text: str,
            *,
            bold: bool = False,
            size: float = 10.5,
            color: str | None = None,
            page_break_before: bool = False,
            space_before_pt: float | None = None,
            space_after_pt: float | None = None,
            first_line_indent_cm: float | None = None,
            line_spacing_multiple: float | None = None,
        ):
            new_p = OxmlElement("w:p")
            ppr = None

            def get_ppr():
                nonlocal ppr
                if ppr is None:
                    ppr = OxmlElement("w:pPr")
                return ppr

            if page_break_before:
                pbr = OxmlElement("w:pageBreakBefore")
                get_ppr().append(pbr)
            if first_line_indent_cm is not None:
                ind = OxmlElement("w:ind")
                ind.set(
                    qn("w:firstLine"),
                    str(int(float(first_line_indent_cm) * 567)),
                )
                get_ppr().append(ind)
            if (
                space_before_pt is not None
                or space_after_pt is not None
                or line_spacing_multiple is not None
            ):
                spacing = OxmlElement("w:spacing")
                if space_before_pt is not None:
                    spacing.set(qn("w:before"), str(int(float(space_before_pt) * 20)))
                if space_after_pt is not None:
                    spacing.set(qn("w:after"), str(int(float(space_after_pt) * 20)))
                if line_spacing_multiple is not None:
                    spacing.set(qn("w:line"), str(int(float(line_spacing_multiple) * 240)))
                    spacing.set(qn("w:lineRule"), "auto")
                get_ppr().append(spacing)
            if ppr is not None:
                new_p.append(ppr)
            run = OxmlElement("w:r")
            rpr = OxmlElement("w:rPr")
            if bold:
                rpr.append(OxmlElement("w:b"))
            if size:
                sz = OxmlElement("w:sz")
                sz.set(qn("w:val"), str(int(size * 2)))
                rpr.append(sz)
                sz_cs = OxmlElement("w:szCs")
                sz_cs.set(qn("w:val"), str(int(size * 2)))
                rpr.append(sz_cs)
            if color:
                c = OxmlElement("w:color")
                c.set(qn("w:val"), color)
                rpr.append(c)
            run.append(rpr)
            t = OxmlElement("w:t")
            t.text = text
            t.set(qn("xml:space"), "preserve")
            run.append(t)
            new_p.append(run)
            paragraph._p.addnext(new_p)
            return ParagraphProxy(new_p)

        def insert_spacer_after(paragraph, space_after_pt: float):
            new_p = OxmlElement("w:p")
            ppr = OxmlElement("w:pPr")
            spacing = OxmlElement("w:spacing")
            spacing.set(qn("w:after"), str(int(float(space_after_pt) * 20)))
            ppr.append(spacing)
            new_p.append(ppr)
            paragraph._p.addnext(new_p)
            return ParagraphProxy(new_p)

        def set_table_no_borders(table) -> None:
            tbl_pr = table._tbl.tblPr
            borders = tbl_pr.find(qn("w:tblBorders"))
            if borders is None:
                borders = OxmlElement("w:tblBorders")
                tbl_pr.append(borders)
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
                elem = borders.find(qn(f"w:{edge}"))
                if elem is None:
                    elem = OxmlElement(f"w:{edge}")
                    borders.append(elem)
                elem.set(qn("w:val"), "nil")

        def cm_to_twips(value: float) -> int:
            return int(float(value) * 567)

        def set_cell_margins_zero(cell) -> None:
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_mar = tc_pr.find(qn("w:tcMar"))
            if tc_mar is None:
                tc_mar = OxmlElement("w:tcMar")
                tc_pr.append(tc_mar)
            for edge in ("top", "left", "bottom", "right"):
                elem = tc_mar.find(qn(f"w:{edge}"))
                if elem is None:
                    elem = OxmlElement(f"w:{edge}")
                    tc_mar.append(elem)
                elem.set(qn("w:w"), "0")
                elem.set(qn("w:type"), "dxa")

        def set_fixed_table_widths(table, widths_cm: list[float]) -> None:
            table.autofit = False
            tbl = table._tbl
            tbl_pr = tbl.tblPr
            layout = tbl_pr.find(qn("w:tblLayout"))
            if layout is None:
                layout = OxmlElement("w:tblLayout")
                tbl_pr.append(layout)
            layout.set(qn("w:type"), "fixed")

            total = sum(cm_to_twips(width) for width in widths_cm)
            tbl_w = tbl_pr.find(qn("w:tblW"))
            if tbl_w is None:
                tbl_w = OxmlElement("w:tblW")
                tbl_pr.append(tbl_w)
            tbl_w.set(qn("w:type"), "dxa")
            tbl_w.set(qn("w:w"), str(total))

            grid = tbl.find(qn("w:tblGrid"))
            if grid is None:
                grid = OxmlElement("w:tblGrid")
                tbl.insert(1, grid)
            for child in list(grid):
                grid.remove(child)
            for width in widths_cm:
                col = OxmlElement("w:gridCol")
                col.set(qn("w:w"), str(cm_to_twips(width)))
                grid.append(col)

            for row in table.rows:
                for idx, cell in enumerate(row.cells):
                    width = cm_to_twips(widths_cm[min(idx, len(widths_cm) - 1)])
                    tc_pr = cell._tc.get_or_add_tcPr()
                    tc_w = tc_pr.find(qn("w:tcW"))
                    if tc_w is None:
                        tc_w = OxmlElement("w:tcW")
                        tc_pr.append(tc_w)
                    tc_w.set(qn("w:type"), "dxa")
                    tc_w.set(qn("w:w"), str(width))

        temp_paths: list[str] = []

        def resolve_contact_qr(contact_cfg: dict) -> str | None:
            qr_path = str(contact_cfg.get("qr_image_path") or "").strip()
            if qr_path:
                path = Path(qr_path).expanduser()
                if not path.is_absolute():
                    path = Path(file_path).resolve().parent / path
                if path.exists():
                    return str(path)

            media_name = str(contact_cfg.get("qr_template_media") or "").strip()
            if not media_name or not template_path:
                return None
            tpl = Path(template_path)
            if not tpl.exists():
                return None
            try:
                with ZipFile(tpl) as zf:
                    if media_name not in zf.namelist():
                        return None
                    suffix = Path(media_name).suffix or ".png"
                    handle = tempfile.NamedTemporaryFile(
                        delete=False,
                        suffix=suffix,
                    )
                    with handle:
                        handle.write(zf.read(media_name))
                    temp_paths.append(handle.name)
                    return handle.name
            except Exception:
                return None

        def insert_contact_block_after(paragraph, contact_cfg: dict):
            if not isinstance(contact_cfg, dict) or not self._truthy(
                contact_cfg.get("enabled", True)
            ):
                return paragraph, False

            lines = contact_cfg.get("lines") or []
            lines = [str(line).strip() for line in lines if str(line).strip()]
            if not lines:
                return paragraph, False

            current = paragraph
            space_before = self._float_config(contact_cfg.get("space_before_pt"), 0.0)
            if space_before > 0:
                current = insert_spacer_after(current, space_before)

            table = doc.add_table(rows=1, cols=2)
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            set_table_no_borders(table)
            left_width = self._float_config(contact_cfg.get("left_width_cm"), 10.5)
            right_width = self._float_config(contact_cfg.get("right_width_cm"), 4.0)
            font_size = self._float_config(contact_cfg.get("font_size"), 9.0)
            qr_width = self._float_config(contact_cfg.get("qr_width_cm"), 3.6)

            for idx, cell in enumerate(table.rows[0].cells):
                cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                cell.width = Cm(left_width if idx == 0 else right_width)
                set_cell_margins_zero(cell)
            set_fixed_table_widths(table, [left_width, right_width])

            left = table.rows[0].cells[0]
            left.text = ""
            for idx, line in enumerate(lines):
                p = left.paragraphs[0] if idx == 0 else left.add_paragraph()
                p.paragraph_format.space_after = Pt(8)
                p.paragraph_format.space_before = Pt(0)
                run = p.add_run(line)
                run.font.size = Pt(font_size)

            right = table.rows[0].cells[1]
            right.text = ""
            p = right.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            qr = resolve_contact_qr(contact_cfg)
            if qr:
                run = p.add_run()
                run.add_picture(qr, width=Cm(qr_width))

            current._p.addnext(table._tbl)
            return ParagraphProxy(table._tbl), True

        def ensure_page_break_before(paragraph) -> bool:
            ppr = paragraph._p.get_or_add_pPr()
            if ppr.find(qn("w:pageBreakBefore")) is not None:
                return False
            ppr.append(OxmlElement("w:pageBreakBefore"))
            return True

        def normalized_status(value) -> str:
            return str(value or "").strip().upper()

        def has_tmb_h() -> bool:
            status = normalized_status(context.get("tmb_status"))
            if status in {"H", "HIGH", "TMB-H"}:
                return True
            if status:
                return False
            return "TMB-H" in str(context.get("tmb_summary") or "").upper()

        def has_msi_h() -> bool:
            status = normalized_status(context.get("msi_status"))
            if status in {"MSI-H", "MSIH", "HIGH"}:
                return True
            if status:
                return False
            return "MSI-H" in str(context.get("msi_summary") or "").upper()

        def has_known_tmb() -> bool:
            status = normalized_status(context.get("tmb_status"))
            return bool(status and status not in {"未检测", "NOT DETECTED", "NA", "N/A", "NONE"})

        def has_known_msi() -> bool:
            status = normalized_status(context.get("msi_status"))
            return bool(status and status not in {"未检测", "NOT DETECTED", "NA", "N/A", "NONE"})

        def has_immune_biomarker_conflict() -> bool:
            tmb_positive = has_tmb_h()
            msi_positive = has_msi_h()
            return (
                (tmb_positive and has_known_msi() and not msi_positive)
                or (msi_positive and has_known_tmb() and not tmb_positive)
            )

        def compact_date(text: str) -> str:
            return re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", r"\1\2\3", text)

        def dotted_date(text: str) -> str:
            return re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", r"\1.\2.\3", text)

        # Cover dates use compact yyyymmdd; signature/report footer uses yyyy.mm.dd.
        for paragraph in doc.paragraphs:
            text = paragraph.text or ""
            if "报告导读" in text:
                break
            if "送检日期" in text or "报告日期" in text:
                changed = replace_in_runs(paragraph, compact_date) or changed

        for paragraph in doc.paragraphs:
            text = paragraph.text or ""
            if "检测者" in text and "报告日期" in text:
                changed = replace_in_runs(paragraph, dotted_date) or changed

        # Keep the front matter aligned with the reviewed report: cover, report
        # guide, patient letter, and TOC are separate pages.
        for paragraph in doc.paragraphs:
            if (paragraph.text or "").strip() == "报告导读":
                changed = ensure_page_break_before(paragraph) or changed
                break

        # The first information table displays project code, not the source MLS file id.
        report_number = str(context.get("report_number") or "").strip()
        project_code = ""
        match = re.search(r"(LZ\d+)", report_number, flags=re.IGNORECASE)
        if match:
            project_code = match.group(1).upper()
        sample_id = str(context.get("sample_id") or "").strip()
        if project_code:
            for table in doc.tables:
                for row in table.rows:
                    row_text = " ".join(cell.text for cell in row.cells)
                    if "项目编码" not in row_text:
                        continue
                    for cell in row.cells:
                        if sample_id and sample_id in cell.text:
                            for p in cell.paragraphs:
                                changed = replace_in_runs(
                                    p, lambda s: s.replace(sample_id, project_code)
                                ) or changed
                    break

        # 301/358 report body should reflect the selected project gene count.
        project_name = str(context.get("project_name") or "").strip()
        panel_match = re.search(r"(\d+)\s*基因", project_name)
        if panel_match:
            panel_count = panel_match.group(1)
            for paragraph in doc.paragraphs:
                if "与肿瘤密切相关的" in (paragraph.text or "") and "个基因" in paragraph.text:
                    # The numeric token is split into its own run in the template.
                    for run in paragraph.runs:
                        if run.text.strip().isdigit():
                            run.text = re.sub(r"\d+", panel_count, run.text)
                            changed = True
                    changed = replace_in_runs(
                        paragraph,
                        lambda s: re.sub(r"与肿瘤密切相关的\d+个基因", f"与肿瘤密切相关的{panel_count}个基因", s),
                    ) or changed

        brand_summary = str(context.get("targeted_drug_brand_summary") or "").strip()
        brand_prefix = "2.上表涉及的已上市的药物名称及对应的商品名称："
        for paragraph in doc.paragraphs:
            if "上表涉及的已上市的药物名称及对应的商品名称" not in (paragraph.text or ""):
                continue
            if brand_summary:
                changed = set_paragraph_text(
                    paragraph,
                    f"{brand_prefix}{brand_summary}",
                ) or changed
            else:
                changed = set_paragraph_text(
                    paragraph,
                    "2.上表未涉及可汇总商品名的已上市药物。",
                ) or changed
            break

        if not has_tmb_h():
            tmb_h_drug_note = re.compile(
                r"并且，\s*FDA\s*已批准帕博利珠单抗用于治疗\s*TMB-H\s*的不可切除或转移性的成人和儿童实体瘤。"
            )
            for paragraph in doc.paragraphs:
                text = paragraph.text or ""
                if (
                    "FDA" not in text
                    or "TMB-H" not in text
                    or "帕博利珠单抗" not in text
                    or "不可切除或转移性的成人和儿童实体瘤" not in text
                ):
                    continue
                new_text = tmb_h_drug_note.sub("", text).strip()
                new_text = re.sub(r"\s+。", "。", new_text)
                if new_text != text:
                    changed = set_paragraph_text(paragraph, new_text) or changed

        if not has_immune_biomarker_conflict():
            for paragraph in list(doc.paragraphs):
                text = paragraph.text or ""
                if "免疫治疗生物标志物包括" in text and "相对独立" in text:
                    changed = remove_paragraph(paragraph) or changed

        # Patient info table should stop at project code; hospital/pathology/QC rows
        # were requested to be removed from this location.
        remove_markers = ("送检医院", "病理号", "平均深度", "Q30", "覆盖度")
        for table in doc.tables:
            if not any("项目编码" in cell.text for row in table.rows for cell in row.cells):
                continue
            for row in list(table.rows):
                row_text = " ".join(cell.text for cell in row.cells)
                if any(marker in row_text for marker in remove_markers):
                    row._tr.getparent().remove(row._tr)
                    changed = True
            break

        # Add the configured consultation line before the patient letter if missing.
        consultation_line = str(context.get("consultation_line") or "").strip()
        has_phone = bool(consultation_line) and any(
            consultation_line in (p.text or "") for p in doc.paragraphs
        )
        if consultation_line and not has_phone:
            for paragraph in doc.paragraphs:
                if "检测结果仅对本次送检样本负责" not in (paragraph.text or ""):
                    continue
                new_p = OxmlElement("w:p")
                ppr = OxmlElement("w:pPr")
                jc = OxmlElement("w:jc")
                jc.set(qn("w:val"), "left")
                ppr.append(jc)
                new_p.append(ppr)
                r = OxmlElement("w:r")
                rpr = OxmlElement("w:rPr")
                b = OxmlElement("w:b")
                rpr.append(b)
                r.append(rpr)
                t = OxmlElement("w:t")
                t.text = consultation_line
                r.append(t)
                new_p.append(r)
                paragraph._p.addnext(new_p)
                changed = True
                break

        # The reviewed CRC report contains a fuller patient letter than the base
        # template. The inserted paragraphs are configured under
        # settings.report_content.patient_letter.
        letter_text = "\n".join(p.text or "" for p in iter_all_paragraphs(doc))
        letter_cfg = content_cfg.get("patient_letter") if isinstance(content_cfg, dict) else {}
        letter_cfg = letter_cfg if isinstance(letter_cfg, dict) else {}
        greeting_specs = self._paragraph_specs(letter_cfg.get("after_greeting"))
        modern_specs = self._paragraph_specs(letter_cfg.get("after_modern_medicine"))
        configured_letter_text = "\n".join(text for text, _ in greeting_specs + modern_specs)
        has_configured_letter = bool(configured_letter_text) and all(
            text and text in letter_text
            for text, _ in greeting_specs + modern_specs
            if "{" not in text
        )
        if (greeting_specs or modern_specs) and not has_configured_letter:
            project_display = str(
                context.get("project_name")
                or context.get("project_display_name")
                or "本次基因检测"
            ).strip()
            format_values = {
                "project_name": project_display,
                "project_display_name": project_display,
            }
            greeting = None
            modern = None
            for paragraph in iter_all_paragraphs(doc):
                text = (paragraph.text or "").strip()
                if text == "您好！" and greeting is None:
                    greeting = paragraph
                if "现代医学已经证明" in text and modern is None:
                    modern = paragraph
            if greeting is not None:
                current = greeting
                for text, options in greeting_specs:
                    current = insert_paragraph_after(
                        current,
                        self._format_static_text(text, format_values),
                        **({"size": 10.5} | options),
                    )
                changed = True
            if modern is not None:
                current = modern
                for text, options in modern_specs:
                    current = insert_paragraph_after(
                        current,
                        self._format_static_text(text, format_values),
                        **({"size": 10.5} | options),
                    )
                changed = True

        # The patient letter starts on a new page.
        for paragraph in iter_all_paragraphs(doc):
            if (paragraph.text or "").strip() != "致您的一封信":
                continue
            changed = ensure_page_break_before(paragraph) or changed
            break

        # Restore configured company-introduction tail pages after the NGS method
        # limitation section.
        full_text = "\n".join(p.text or "" for p in iter_all_paragraphs(doc))
        tail_cfg = content_cfg.get("tail_content") if isinstance(content_cfg, dict) else {}
        tail_cfg = tail_cfg if isinstance(tail_cfg, dict) else {}
        tail_marker = str(tail_cfg.get("marker_text") or "").strip()
        tail_anchor = str(tail_cfg.get("anchor_text") or "").strip()
        tail_specs = self._paragraph_specs(tail_cfg.get("paragraphs"))
        if tail_marker and tail_anchor and tail_specs and tail_marker not in full_text:
            for paragraph in doc.paragraphs:
                if tail_anchor not in (paragraph.text or ""):
                    continue
                current = paragraph
                for text, kwargs in tail_specs:
                    current = insert_paragraph_after(current, text, **kwargs)
                current, contact_changed = insert_contact_block_after(
                    current,
                    tail_cfg.get("contact_block") or {},
                )
                changed = contact_changed or changed
                changed = True
                break

        if tail_marker and tail_marker in full_text:
            contact_cfg = tail_cfg.get("contact_block") or {}
            contact_lines = [
                str(line).strip()
                for line in (contact_cfg.get("lines") or [])
                if str(line).strip()
            ]
            if contact_lines and not all(line in full_text for line in contact_lines):
                for paragraph in doc.paragraphs:
                    if tail_marker not in (paragraph.text or ""):
                        continue
                    current = paragraph
                    # Attach the contact block after the last configured intro
                    # paragraph if it already exists.
                    for candidate in doc.paragraphs:
                        if (
                            "助力我国肿瘤精准医学的发展" in (candidate.text or "")
                            and candidate._p.getparent() is not None
                        ):
                            current = candidate
                    _, contact_changed = insert_contact_block_after(
                        current,
                        contact_cfg,
                    )
                    changed = contact_changed or changed
                    changed = True
                    break

        if changed:
            doc.save(file_path)
        for path in temp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass

    def validate_template_contract(
        self,
        template_path: str,
        context: dict,
        contract_spec: dict | None = None,
    ) -> dict:
        """Validate template references and optional panel-declared requirements.

        Returns:
            A JSON-serializable dict describing missing variables/fields.
        """
        contract = extract_template_contract(template_path)
        validation = validate_contract(contract, context=context)
        declared_report = None
        declared_ok = True
        if contract_spec:
            declared_validation = validate_declared_contract(
                template_path,
                contract,
                contract_spec,
            )
            declared_report = declared_validation_to_dict(
                declared_validation,
                contract_spec,
            )
            declared_ok = bool(declared_validation.ok)

        return {
            "ok": bool(validation.ok and declared_ok),
            "template_path": contract.template_path,
            "required_paths": list(contract.required_paths),
            "required_lists": list(contract.required_lists),
            "loop_row_fields": {
                k: list(v) for k, v in contract.loop_row_fields.items()
            },
            "missing_paths": list(validation.missing_paths),
            "missing_lists": list(validation.missing_lists),
            "missing_row_fields": {
                k: list(v) for k, v in validation.missing_row_fields.items()
            },
            "missing_row_examples": validation.missing_row_examples,
            "declared_contract": declared_report,
        }

    def validate_template(self, template_path: str) -> tuple[bool, Optional[str]]:
        """
        验证模板文件

        Args:
            template_path: 模板文件路径

        Returns:
            (是否有效, 错误消息)
        """
        # 基本文件验证
        is_valid, error = validate_docx_file(template_path, must_exist=True)
        if not is_valid:
            return False, error

        # 尝试加载模板
        try:
            try:
                from docxtpl import DocxTemplate
            except ModuleNotFoundError:
                return False, (
                    "缺少依赖 'docxtpl'，无法校验模板；请先安装 requirements.txt 中的依赖"
                )

            DocxTemplate(template_path)
            self.logger.debug("模板验证成功", template=template_path)
            return True, None
        except Exception as e:
            error_msg = f"模板文件无效: {e}"
            self.logger.error("模板验证失败", template=template_path, error=str(e))
            return False, error_msg

    def get_template_variables(self, template_path: str) -> list[str]:
        """
        获取模板中的变量列表

        Args:
            template_path: 模板文件路径

        Returns:
            变量名列表（包括单值变量和循环变量）
        """
        import re
        from zipfile import ZipFile

        try:
            variables = set()

            # 读取docx文件（本质是zip包）
            with ZipFile(template_path, "r") as zf:
                # 读取document.xml（主要内容）
                xml_files = [
                    "word/document.xml",
                    "word/header1.xml",
                    "word/header2.xml",
                    "word/footer1.xml",
                    "word/footer2.xml",
                ]

                for xml_file in xml_files:
                    try:
                        content = zf.read(xml_file).decode("utf-8")

                        # 提取 {{ variable }} 格式的变量
                        # 匹配单值变量: {{ var }} 或 {{ obj.attr }}
                        single_var_re = (
                            r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*"
                            r"(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)\s*\}\}"
                        )
                        single_vars = re.findall(
                            single_var_re,
                            content,
                        )
                        variables.update(single_vars)

                        # 提取 {% for item in list %} 中的list变量
                        for_vars = re.findall(
                            r"\{%\s*for\s+\w+\s+in\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*%\}",
                            content,
                        )
                        variables.update(for_vars)

                        # 提取 row.xxx 格式（循环内的字段引用）
                        row_vars = re.findall(r"row\.([a-zA-Z_][a-zA-Z0-9_]*)", content)
                        variables.update([f"row.{v}" for v in row_vars])

                        # 提取 row['xxx'] 格式
                        row_bracket_vars = re.findall(r"row\['([^']+)'\]", content)
                        variables.update([f"row['{v}']" for v in row_bracket_vars])

                    except KeyError:
                        # 文件不存在，跳过
                        continue

            result = sorted(list(variables))
            self.logger.debug(
                "提取模板变量成功", template=template_path, count=len(result)
            )
            return result

        except Exception as e:
            self.logger.error("提取模板变量失败", template=template_path, error=str(e))
            return []

    def validate_template_variables(
        self,
        template_path: str,
        available_variables: list[str],
        *,
        available_row_keys: Optional[set[str]] = None,
    ) -> tuple[bool, list[str], list[str]]:
        """
        校验模板变量是否都有对应的数据源

        Args:
            template_path: 模板文件路径
            available_variables: 可用的变量名列表（来自mapping配置）

        Returns:
            (是否全部匹配, 缺失变量列表, 未使用变量列表)
        """
        template_vars = self.get_template_variables(template_path)

        # 分离单值变量和循环变量
        single_vars = [
            v
            for v in template_vars
            if not v.startswith("row.") and not v.startswith("row[")
        ]

        # 检查缺失的变量（模板中有，但mapping中没有）
        missing_vars = [v for v in single_vars if v not in available_variables]

        # 校验循环行字段（row.* / row['*']）是否在mapping的列定义/同义词中出现
        if available_row_keys is not None:
            row_vars = [
                v for v in template_vars if v.startswith("row.") or v.startswith("row[")
            ]
            for v in row_vars:
                if v.startswith("row."):
                    key = v[len("row.") :]
                    if key and key not in available_row_keys:
                        missing_vars.append(v)
                elif v.startswith("row['") and v.endswith("']"):
                    key = v[len("row['") : -len("']")]
                    if key and key not in available_row_keys:
                        missing_vars.append(v)

        # 检查未使用的变量（mapping中有，但模板中没有）
        unused_vars = [v for v in available_variables if v not in single_vars]

        is_valid = len(missing_vars) == 0

        if missing_vars:
            self.logger.warning(
                "模板变量校验：发现未定义的变量",
                missing_count=len(missing_vars),
                missing_vars=missing_vars[:10],  # 只显示前10个
            )

        return is_valid, missing_vars, unused_vars

    # -------------------- internal helpers --------------------
    def _cleanup_empty_table_rows(self, file_path: str) -> None:
        """打开生成的docx，删除所有完全空白的表格行。

        空白行定义：该行所有单元格的 .text 去除空白后均为空字符串。
        """
        doc = Document(file_path)
        removed = 0
        for tbl in doc.tables:
            # 收集需要删除的 row 索引（从下往上删更安全）
            to_delete = []
            for idx, row in enumerate(tbl.rows):
                if all((cell.text or "").strip() == "" for cell in row.cells):
                    to_delete.append(idx)
            for idx in reversed(to_delete):
                tr = tbl.rows[idx]._tr
                tbl._tbl.remove(tr)
                removed += 1
        # #15: 删除只有表头的空数据表格（CNV/Fusion）
        tables_removed = 0
        cnv_fusion_markers = [
            (["起始位置", "终止位置", "拷贝数"], "CNV"),
            (["基因1", "基因2", "断点"], "Fusion"),
        ]
        for tbl in list(doc.tables):
            if len(tbl.rows) <= 1:  # 只有表头，无数据行
                header_text = " ".join(c.text.strip() for c in tbl.rows[0].cells) if tbl.rows else ""
                for markers, name in cnv_fusion_markers:
                    if all(m in header_text for m in markers):
                        tbl._tbl.getparent().remove(tbl._tbl)
                        tables_removed += 1
                        self.logger.debug(f"移除空{name}表格", table=name)
                        break
        if tables_removed:
            removed += tables_removed  # ensure save happens

        if removed or tables_removed:
            self.logger.debug("移除空白表格行", removed_rows=removed, removed_tables=tables_removed)
            doc.save(file_path)

    def _cleanup_cover_artifacts(self, file_path: str) -> None:
        """删除封面模板里误留的纯数字调试段落。"""
        import re

        doc = Document(file_path)
        removed = 0
        for paragraph in list(doc.paragraphs[:20]):
            text = (paragraph.text or "").strip()
            if not re.fullmatch(r"3{6,}", text):
                continue
            paragraph._element.getparent().remove(paragraph._element)
            removed += 1

        if removed:
            doc.save(file_path)
            self.logger.debug("已清理封面数字残留", removed=removed)

    def _cleanup_trailing_blank_page(self, file_path: str) -> None:
        """删除最后正文后多余的分页符和空白段落。

        只在最后一个有效正文块之后没有任何可见内容时处理，避免误删正常分页。
        """
        import os
        import shutil
        import tempfile
        import xml.etree.ElementTree as ET
        from zipfile import ZIP_DEFLATED, ZipFile

        ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        w_body = f"{{{ns_w}}}body"
        w_p = f"{{{ns_w}}}p"
        w_tbl = f"{{{ns_w}}}tbl"
        w_t = f"{{{ns_w}}}t"
        w_br = f"{{{ns_w}}}br"
        w_drawing = f"{{{ns_w}}}drawing"
        w_pict = f"{{{ns_w}}}pict"
        w_sectpr = f"{{{ns_w}}}sectPr"
        w_type = f"{{{ns_w}}}type"
        ignorable_tail_tags = {
            f"{{{ns_w}}}bookmarkStart",
            f"{{{ns_w}}}bookmarkEnd",
            f"{{{ns_w}}}proofErr",
            f"{{{ns_w}}}permStart",
            f"{{{ns_w}}}permEnd",
        }

        def text_of(elem) -> str:
            return "".join((node.text or "") for node in elem.iter(w_t)).strip()

        def has_visible_content(elem) -> bool:
            if text_of(elem):
                return True
            if any(True for _ in elem.iter(w_drawing)):
                return True
            if any(True for _ in elem.iter(w_pict)):
                return True
            return False

        def is_blank_paragraph(elem) -> bool:
            return elem.tag == w_p and not has_visible_content(elem)

        def is_ignorable_tail_element(elem) -> bool:
            return is_blank_paragraph(elem) or elem.tag in ignorable_tail_tags

        with ZipFile(file_path, "r") as zin:
            document_xml = zin.read("word/document.xml")
            document_info = zin.getinfo("word/document.xml")
            other_entries = [
                (info, zin.read(info.filename))
                for info in zin.infolist()
                if info.filename != "word/document.xml"
            ]

        root = ET.fromstring(document_xml)
        body = root.find(f".//{w_body}")
        if body is None:
            return

        children = list(body)
        content_end = len(children)
        if content_end and children[-1].tag == w_sectpr:
            content_end -= 1

        last_content_idx = None
        for idx in range(content_end - 1, -1, -1):
            child = children[idx]
            if child.tag in (w_p, w_tbl) and has_visible_content(child):
                last_content_idx = idx
                break
        if last_content_idx is None:
            return

        trailing = children[last_content_idx + 1:content_end]
        if any(not is_ignorable_tail_element(elem) for elem in trailing):
            return

        changed = 0

        # 移除最后有效段落里位于文档末尾的分页符。
        last_content = children[last_content_idx]
        if last_content.tag == w_p:
            for br in list(last_content.iter(w_br)):
                if br.get(w_type) != "page":
                    continue
                parent = None
                for candidate in last_content.iter():
                    if br in list(candidate):
                        parent = candidate
                        break
                if parent is not None:
                    parent.remove(br)
                    changed += 1

        for elem in trailing:
            if is_blank_paragraph(elem):
                body.remove(elem)
                changed += 1

        if not changed:
            return

        fd, tmp_name = tempfile.mkstemp(suffix=".docx")
        os.close(fd)
        try:
            with ZipFile(tmp_name, "w", compression=ZIP_DEFLATED) as zout:
                zout.writestr(
                    document_info,
                    ET.tostring(root, encoding="utf-8", xml_declaration=True),
                )
                for info, data in other_entries:
                    zout.writestr(info, data)
            shutil.move(tmp_name, file_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

        self.logger.debug("已清理文档尾部空白页", changed=changed)

    def _cleanup_section_spacing(self, file_path: str) -> None:
        """删除章节标题前的空白段落。

        仅删除与章节标题同一父节点、且紧邻标题前的完全空白段落，
        避免误伤正常留白。
        """
        import copy
        import os
        import shutil
        import tempfile
        import xml.etree.ElementTree as ET
        from zipfile import ZIP_DEFLATED, ZipFile

        ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        w_p = f"{{{ns_w}}}p"
        w_t = f"{{{ns_w}}}t"
        w_drawing = f"{{{ns_w}}}drawing"
        w_ppr = f"{{{ns_w}}}pPr"
        w_sectpr = f"{{{ns_w}}}sectPr"

        section_titles = (
            "报告导读",
            "致您的一封信",
            "第一部分：基本信息",
            "第二部分：检测结果",
            "第三部分：基因变异及相应靶向/免疫药物解析",
            "第四部分：附录",
        )

        def para_text(elem) -> str:
            return "".join((node.text or "") for node in elem.iter(w_t)).strip()

        def is_blank_paragraph(elem) -> bool:
            if para_text(elem):
                return False
            if any(True for _ in elem.iter(w_drawing)):
                return False
            return True

        def is_section_heading(elem) -> bool:
            text = para_text(elem)
            if not text or len(text) > 120:
                return False
            return any(title in text for title in section_titles)

        with ZipFile(file_path, "r") as zin:
            document_xml = zin.read("word/document.xml")
            other_entries = [(info, zin.read(info.filename)) for info in zin.infolist() if info.filename != "word/document.xml"]

        root = ET.fromstring(document_xml)
        removed = 0

        for parent in root.iter():
            children = list(parent)
            if not children:
                continue

            to_remove = []
            for idx, child in enumerate(children):
                if child.tag != w_p or not is_section_heading(child):
                    continue
                prev_idx = idx - 1
                blank_cluster = []
                while prev_idx >= 0:
                    prev = children[prev_idx]
                    if prev.tag != w_p or not is_blank_paragraph(prev):
                        break
                    blank_cluster.append(prev)
                    prev_idx -= 1
                if not blank_cluster:
                    continue

                sectpr = None
                for blank in blank_cluster:
                    ppr = blank.find(w_ppr)
                    if ppr is None:
                        continue
                    current_sectpr = ppr.find(w_sectpr)
                    if current_sectpr is not None:
                        sectpr = copy.deepcopy(current_sectpr)
                        break

                if sectpr is not None and prev_idx >= 0 and children[prev_idx].tag == w_p:
                    target_p = children[prev_idx]
                    target_ppr = target_p.find(w_ppr)
                    if target_ppr is None:
                        target_ppr = ET.Element(w_ppr)
                        target_p.insert(0, target_ppr)
                    existing_sectpr = target_ppr.find(w_sectpr)
                    if existing_sectpr is not None:
                        target_ppr.remove(existing_sectpr)
                    target_ppr.append(sectpr)

                to_remove.extend(blank_cluster)

            seen = set()
            for elem in to_remove:
                marker = id(elem)
                if marker in seen:
                    continue
                parent.remove(elem)
                seen.add(marker)
                removed += 1

        if removed == 0:
            return

        fd, tmp_name = tempfile.mkstemp(suffix=".docx")
        os.close(fd)
        try:
            with ZipFile(tmp_name, "w", compression=ZIP_DEFLATED) as zout:
                with ZipFile(file_path, "r") as zin:
                    document_info = zin.getinfo("word/document.xml")
                zout.writestr(
                    document_info,
                    ET.tostring(root, encoding="utf-8", xml_declaration=True),
                )
                for info, data in other_entries:
                    zout.writestr(info, data)
            shutil.move(tmp_name, file_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

        self.logger.debug("清理章节前空白段落", removed=removed)

    def _render_part3_formatted(self, file_path: str, context: dict) -> None:
        """将 {{PART3_PLACEHOLDER}} 替换为格式化的 Part 3 段落。

        对齐参考终版格式：
        - 变异标题：bold=True, size=12pt, color=FF0000(有药物)/0000FF(无药物), 前缀"u "
        - 变异说明：size=10.5pt
        - 基因简介：size=10.5pt
        - 药物标题：bold=True, color=FF0000
        """
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        doc = Document(file_path)
        content_cfg = self._report_content_config(context)

        # 找到占位标记段落
        placeholder_para = None
        for p in doc.paragraphs:
            if "__PART3_MARKER__" in p.text:
                placeholder_para = p
                break

        if placeholder_para is None:
            return  # 无占位标记，跳过

        def element_text(element) -> str:
            return "".join(node.text or "" for node in element.iter(qn("w:t")))

        amino_table_element = None
        previous = placeholder_para._element.getprevious()
        if previous is not None and previous.tag == qn("w:tbl") and "氨基酸缩写" in element_text(previous):
            amino_table_element = previous
            amino_table_element.getparent().remove(amino_table_element)

        # 获取数据
        sections = context.get("gene_knowledge_sections", [])
        benefit_sections = context.get("drug_benefit_sections", [])
        caution_sections = context.get("drug_caution_sections", [])
        references = context.get("gene_references", [])
        total_count = context.get("total_variants_count", 0)
        drug_count = context.get("drug_related_count", 0)

        # 辅助函数：在指定元素后插入新段落
        def add_para_after(prev_element, text, bold=False, size=10.5,
                          color=None, prefix="", page_break_before=False):
            new_p = OxmlElement("w:p")
            if page_break_before:
                ppr = OxmlElement("w:pPr")
                page_break = OxmlElement("w:pageBreakBefore")
                ppr.append(page_break)
                new_p.append(ppr)
            if prefix:
                # 前缀 run
                pr = OxmlElement("w:r")
                pt_elem = OxmlElement("w:t")
                pt_elem.text = prefix
                pt_elem.set(qn("xml:space"), "preserve")
                pr.append(pt_elem)
                new_p.append(pr)

            new_r = OxmlElement("w:r")
            # 格式
            rPr = OxmlElement("w:rPr")
            if bold:
                b_elem = OxmlElement("w:b")
                rPr.append(b_elem)
            if size:
                sz = OxmlElement("w:sz")
                sz.set(qn("w:val"), str(int(size * 2)))  # half-points
                rPr.append(sz)
                szCs = OxmlElement("w:szCs")
                szCs.set(qn("w:val"), str(int(size * 2)))
                rPr.append(szCs)
            if color:
                c_elem = OxmlElement("w:color")
                c_elem.set(qn("w:val"), color)
                rPr.append(c_elem)
            # 生产报告不加背景色（#5 fix: 去掉浅蓝阴影）

            new_r.append(rPr)
            new_t = OxmlElement("w:t")
            new_t.text = text
            new_t.set(qn("xml:space"), "preserve")
            new_r.append(new_t)
            new_p.append(new_r)

            prev_element.addnext(new_p)
            return new_p

        # 从占位标记位置开始，链式插入
        current = placeholder_para._element

        # 总述
        current = add_para_after(
            current,
            f"在本次检测范围内，检出体细胞变异{total_count}个，"
            f"其中与靶向/免疫药物相关的变异{drug_count}个。"
            "对第二部分中的基因变异和靶向/免疫药物提示进行详细解析。",
            size=10.5,
        )

        # 空行
        current = add_para_after(current, "")

        # === 基因变异解读 ===
        for section in sections:
            header = section.get("header", "")
            has_drug = section.get("has_drug", False)
            header_color = "FF0000" if has_drug else "0000FF"

            # 变异标题：bold, 12pt, red/blue, 前缀圆点 "● "
            current = add_para_after(
                current, header,
                bold=True, size=12, color=header_color, prefix="\u25cf ",
            )

            # 基因简介（紧跟标题，无多余空行）
            intro = section.get("intro", "")
            if intro:
                current = add_para_after(
                    current, "基因简介：", bold=True, size=10.5
                )
                current = add_para_after(current, intro, size=10.5)

            # 基因变异说明
            desc = section.get("mutation_desc", "")
            if desc:
                current = add_para_after(
                    current, "基因变异说明：", bold=True, size=10.5
                )
                current = add_para_after(current, desc, size=10.5)

            # 基因变异解析
            analysis = section.get("mutation_analysis", "")
            if analysis:
                current = add_para_after(
                    current, "基因变异解析：", bold=True, size=10.5
                )
                current = add_para_after(current, analysis, size=10.5)

            # 变异之间留一个空行分隔
            current = add_para_after(current, "")

        # === 靶向药物解析 ===
        if benefit_sections or caution_sections:
            current = add_para_after(
                current, "靶向药物/免疫用药提示解析",
                bold=True, size=12,
            )
            current = add_para_after(current, "")

        # 获益药物
        if benefit_sections:
            current = add_para_after(
                current, "潜在获益靶向/免疫药物解析",
                bold=True, size=11,
            )
            current = add_para_after(current, "")

            for ds in benefit_sections:
                gene = ds.get("gene", "")
                variant = ds.get("variant", "")
                drug_name = ds.get("drug_name", "")
                clinical = ds.get("clinical", "")

                current = add_para_after(
                    current,
                    f"{gene}：{variant}突变相应靶向药物",
                    bold=True, size=12, color="FF0000",
                )
                if drug_name:
                    current = add_para_after(current, drug_name, size=10.5)
                if clinical:
                    current = add_para_after(current, clinical, size=10.5)
                current = add_para_after(current, "")

        # 负相关药物
        if caution_sections:
            current = add_para_after(
                current, "潜在负相关靶向/免疫药物解析",
                bold=True, size=11,
            )
            current = add_para_after(current, "")

            for ds in caution_sections:
                gene = ds.get("gene", "")
                variant = ds.get("variant", "")
                drug_name = ds.get("drug_name", "")
                clinical = ds.get("clinical", "")

                current = add_para_after(
                    current,
                    f"{gene}：{variant}突变相应负相关靶向药物",
                    bold=True, size=12, color="FF0000",
                )
                if drug_name:
                    current = add_para_after(current, drug_name, size=10.5)
                if clinical:
                    current = add_para_after(current, clinical, size=10.5)
                current = add_para_after(current, "")

        # === 参考文献 ===
        if references:
            current = add_para_after(
                current, "参考文献",
                bold=True, size=12,
            )
            current = add_para_after(current, "")
            for ref in references:
                current = add_para_after(current, ref, size=9)

        reading_blocks = self._paragraph_specs(content_cfg.get("part3_reading_blocks"))
        for text, options in reading_blocks:
            para_options = {"size": 10.5}
            para_options.update(options)
            current = add_para_after(current, text, **para_options)

        if amino_table_element is not None:
            current.addnext(amino_table_element)
            current = amino_table_element

        # 删除占位标记段落
        placeholder_para._element.getparent().remove(placeholder_para._element)

        doc.save(file_path)
        self.logger.info(
            "Part 3 格式化渲染完成",
            sections=len(sections),
            benefit=len(benefit_sections),
            caution=len(caution_sections),
            references=len(references),
        )

    def _render_signature_placeholder(self, file_path: str, context: dict) -> None:
        """处理签名占位符。

        当前优先保证最终报告不出现原始 `__SIG_IMG__` 文本；
        若提供了有效签名图片，则在占位处插入图片。
        """
        from pathlib import Path

        from docx.oxml import OxmlElement
        from docx.shared import Mm
        from docx.text.run import Run

        doc = Document(file_path)
        signature_path = str(context.get("signature_image_path") or "").strip()
        signature_exists = bool(signature_path) and Path(signature_path).exists()
        updated = False

        for paragraph in doc.paragraphs:
            for run in paragraph.runs:
                if "__SIG_IMG__" not in run.text:
                    continue

                before, after = run.text.split("__SIG_IMG__", 1)
                run.text = before

                if signature_exists:
                    new_r = OxmlElement("w:r")
                    run._r.addnext(new_r)
                    picture_run = Run(new_r, paragraph)
                    picture_run.add_picture(signature_path, width=Mm(22))
                    anchor_run = new_r
                else:
                    anchor_run = run._r

                if after:
                    tail_r = OxmlElement("w:r")
                    anchor_run.addnext(tail_r)
                    tail_run = Run(tail_r, paragraph)
                    tail_run.text = after

                updated = True

        if updated:
            doc.save(file_path)
            self.logger.debug(
                "签名占位处理完成",
                image_inserted=signature_exists,
            )

    def _normalize_signature_layout(self, file_path: str, context: dict) -> None:
        """Stabilize the detector/reviewer signature block.

        The legacy template stores two handwritten signature images as floating
        anchors in the blank paragraph immediately before the text line:
        "检测者：...审核者：...报告日期：...". Different renderers position those
        anchors slightly differently, so they can overlap the report date. Keep
        the signatures on their own label line and move the date to a separate
        right-aligned paragraph, which is stable across Word/WPS/LibreOffice.
        """
        import os
        import re
        import shutil
        import tempfile
        import xml.etree.ElementTree as ET
        from zipfile import ZIP_DEFLATED, ZipFile

        ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        ns_wp = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
        for prefix, uri in {
            "w": ns_w,
            "wp": ns_wp,
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
        }.items():
            ET.register_namespace(prefix, uri)

        w_body = f"{{{ns_w}}}body"
        w_p = f"{{{ns_w}}}p"
        w_ppr = f"{{{ns_w}}}pPr"
        w_jc = f"{{{ns_w}}}jc"
        w_r = f"{{{ns_w}}}r"
        w_t = f"{{{ns_w}}}t"
        wp_anchor = f"{{{ns_wp}}}anchor"
        wp_position_h = f"{{{ns_wp}}}positionH"
        wp_position_v = f"{{{ns_wp}}}positionV"
        wp_pos_offset = f"{{{ns_wp}}}posOffset"

        def para_text(elem) -> str:
            return "".join((node.text or "") for node in elem.iter(w_t))

        def append_run(paragraph, text: str) -> None:
            run = ET.SubElement(paragraph, w_r)
            t = ET.SubElement(run, w_t)
            t.text = text
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

        def replace_para_text(paragraph, text: str) -> None:
            ppr = paragraph.find(w_ppr)
            for child in list(paragraph):
                if child is not ppr:
                    paragraph.remove(child)
            append_run(paragraph, text)

        def make_date_para(text: str) -> ET.Element:
            paragraph = ET.Element(w_p)
            ppr = ET.SubElement(paragraph, w_ppr)
            jc = ET.SubElement(ppr, w_jc)
            jc.set(f"{{{ns_w}}}val", "right")
            append_run(paragraph, text)
            return paragraph

        def set_anchor_offset(anchor, x: int | None = None, y: int | None = None) -> None:
            position_h = anchor.find(wp_position_h)
            if position_h is not None and x is not None:
                pos = position_h.find(wp_pos_offset)
                if pos is not None:
                    pos.text = str(x)
            position_v = anchor.find(wp_position_v)
            if position_v is not None and y is not None:
                pos = position_v.find(wp_pos_offset)
                if pos is not None:
                    pos.text = str(y)

        with ZipFile(file_path, "r") as zin:
            document_xml = zin.read("word/document.xml")
            document_info = zin.getinfo("word/document.xml")
            other_entries = [
                (info, zin.read(info.filename))
                for info in zin.infolist()
                if info.filename != "word/document.xml"
            ]

        root = ET.fromstring(document_xml)
        body = root.find(w_body)
        if body is None:
            return

        children = list(body)
        changed = False

        for idx, elem in enumerate(children):
            if elem.tag != w_p:
                continue
            text = para_text(elem)
            if "检测者" not in text or "审核者" not in text or "报告日期" not in text:
                continue
            if "__SIG_IMG__" in text:
                text = text.replace("__SIG_IMG__", "")

            date_match = re.search(r"报告日期[:：]\s*([0-9.\-/年月日]+)", text)
            report_date = date_match.group(1).strip() if date_match else ""
            if not report_date:
                report_date = str(context.get("report_date") or "").strip()
            report_date = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", r"\1.\2.\3", report_date)

            replace_para_text(elem, "检测者：                    审核者：")
            changed = True

            # Keep the two legacy floating signatures on the label line, but
            # away from the report date. Values are relative to the text column.
            if idx > 0:
                previous = children[idx - 1]
                anchors = sorted(
                    list(previous.iter(wp_anchor)),
                    key=lambda a: int(
                        (
                            a.find(wp_position_h).find(wp_pos_offset).text
                            if a.find(wp_position_h) is not None
                            and a.find(wp_position_h).find(wp_pos_offset) is not None
                            else "0"
                        )
                    ),
                )
                for anchor, x in zip(anchors[:2], (628650, 2200000)):
                    set_anchor_offset(anchor, x=x, y=120000)
                    anchor.set("allowOverlap", "0")
                    changed = True

            date_text = f"报告日期：{report_date}" if report_date else "报告日期："
            next_elem = children[idx + 1] if idx + 1 < len(children) else None
            if next_elem is not None and next_elem.tag == w_p and para_text(next_elem).startswith("报告日期："):
                replace_para_text(next_elem, date_text)
            else:
                body.insert(idx + 1, make_date_para(date_text))
            changed = True
            break

        if not changed:
            return

        fd, tmp_name = tempfile.mkstemp(suffix=".docx")
        os.close(fd)
        try:
            with ZipFile(tmp_name, "w", compression=ZIP_DEFLATED) as zout:
                zout.writestr(
                    document_info,
                    ET.tostring(root, encoding="utf-8", xml_declaration=True),
                )
                for info, data in other_entries:
                    zout.writestr(info, data)
            shutil.move(tmp_name, file_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

        self.logger.debug("已稳定签名区布局")

    def _fit_tables_to_page_width(self, file_path: str) -> None:
        """缩放超宽表格，使其不超过正文版心。"""
        from docx.oxml.ns import qn

        doc = Document(file_path)
        content_widths = []
        for section in doc.sections:
            try:
                content_widths.append(
                    int(
                        section.page_width.twips
                        - section.left_margin.twips
                        - section.right_margin.twips
                    )
                )
            except Exception:
                continue

        if not content_widths:
            return

        max_width = max(2000, min(content_widths))
        namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        scaled = 0

        for table in doc.tables:
            tbl = table._tbl
            tbl_pr = tbl.find(qn("w:tblPr"))
            if tbl_pr is None:
                continue

            tbl_w = tbl_pr.find(qn("w:tblW"))
            grid = tbl.find(qn("w:tblGrid"))
            grid_cols = [] if grid is None else grid.findall(qn("w:gridCol"))
            grid_width = sum(int(col.get(qn("w:w")) or 0) for col in grid_cols)
            table_width = int(tbl_w.get(qn("w:w")) or 0) if tbl_w is not None else 0
            current_width = max(grid_width, table_width)

            if current_width <= 0 or current_width <= max_width:
                continue

            ratio = max_width / current_width

            if tbl_w is not None:
                tbl_w.set(qn("w:type"), "dxa")
                tbl_w.set(qn("w:w"), str(max_width))

            for col in grid_cols:
                original = int(col.get(qn("w:w")) or 0)
                if original > 0:
                    col.set(qn("w:w"), str(max(240, int(original * ratio))))

            for tc_w in tbl.findall(".//w:tcPr/w:tcW", namespaces):
                if tc_w.get(qn("w:type")) not in (None, "dxa"):
                    continue
                original = int(tc_w.get(qn("w:w")) or 0)
                if original > 0:
                    tc_w.set(qn("w:type"), "dxa")
                    tc_w.set(qn("w:w"), str(max(240, int(original * ratio))))

            scaled += 1

        if scaled:
            doc.save(file_path)
            self.logger.debug("已压缩超宽表格", scaled=scaled, max_width=max_width)

    def _optimize_variant_table_layout(self, file_path: str) -> None:
        """Reflow the 2.1 variant table into a readable portrait-page layout."""
        # The reviewed report keeps the template's 9-column 2.1 table. Earlier
        # versions compacted it to four columns, which broke customer-approved
        # headings, font styling, and colors. Keep this hook as a no-op for
        # backward compatibility with older callers.
        return

        from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Pt, RGBColor

        doc = Document(file_path)
        changed = False
        # Sum = 8300 twips, matching the A4 text width used by the report.
        # The original template has nine narrow columns; Word/LibreOffice wraps
        # short labels into nearly unreadable fragments. Keep all source fields,
        # but group the genomic details into one logical column.
        widths = [1100, 2600, 3000, 1600]
        headers = [
            "基因",
            "基因突变信息",
            "潜在获益靶向药物（证据等级）",
            "可能耐药或慎重药物（证据等级）",
        ]

        def clean_text(value: str) -> str:
            text = (value or "").strip()
            lines = [line.strip() for line in text.splitlines()]
            return "\n".join(line for line in lines if line)

        def normalize_dash(value: str) -> str:
            text = clean_text(value)
            return text if text and text not in {"-", "--", "—"} else "--"

        def keep_value(value: str) -> bool:
            text = clean_text(value)
            return bool(text and text not in {"-", "--", "—"})

        def set_cell_shading(cell, fill: str) -> None:
            tc_pr = cell._tc.get_or_add_tcPr()
            shd = tc_pr.find(qn("w:shd"))
            if shd is None:
                shd = OxmlElement("w:shd")
                tc_pr.append(shd)
            shd.set(qn("w:fill"), fill)

        def set_cell_borders(cell, color: str = "000000", size: str = "6") -> None:
            tc_pr = cell._tc.get_or_add_tcPr()
            borders = tc_pr.find(qn("w:tcBorders"))
            if borders is None:
                borders = OxmlElement("w:tcBorders")
                tc_pr.append(borders)
            for side in ("top", "left", "bottom", "right"):
                border = borders.find(qn(f"w:{side}"))
                if border is None:
                    border = OxmlElement(f"w:{side}")
                    borders.append(border)
                border.set(qn("w:val"), "single")
                border.set(qn("w:sz"), size)
                border.set(qn("w:space"), "0")
                border.set(qn("w:color"), color)

        def set_table_fixed_layout(table) -> None:
            tbl_pr = table._tbl.tblPr
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            layout = tbl_pr.find(qn("w:tblLayout"))
            if layout is None:
                layout = OxmlElement("w:tblLayout")
                tbl_pr.append(layout)
            layout.set(qn("w:type"), "fixed")

            tbl_w = tbl_pr.find(qn("w:tblW"))
            if tbl_w is None:
                tbl_w = OxmlElement("w:tblW")
                tbl_pr.append(tbl_w)
            tbl_w.set(qn("w:type"), "dxa")
            tbl_w.set(qn("w:w"), str(sum(widths)))

            cell_mar = tbl_pr.find(qn("w:tblCellMar"))
            if cell_mar is None:
                cell_mar = OxmlElement("w:tblCellMar")
                tbl_pr.append(cell_mar)
            for side in ("top", "left", "bottom", "right"):
                margin = cell_mar.find(qn(f"w:{side}"))
                if margin is None:
                    margin = OxmlElement(f"w:{side}")
                    cell_mar.append(margin)
                margin.set(qn("w:w"), "70")
                margin.set(qn("w:type"), "dxa")

        def set_cell_width(cell, width: int) -> None:
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:type"), "dxa")
            tc_w.set(qn("w:w"), str(width))

        def set_grid(table) -> None:
            grid = table._tbl.tblGrid
            if grid is None:
                grid = OxmlElement("w:tblGrid")
                table._tbl.insert(0, grid)
            for child in list(grid):
                grid.remove(child)
            for width in widths:
                col = OxmlElement("w:gridCol")
                col.set(qn("w:w"), str(width))
                grid.append(col)

        def style_cell(cell, *, header: bool = False, gene: bool = False) -> None:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            set_cell_borders(cell, color="000000", size="6")
            if header:
                set_cell_shading(cell, "00C4D8")
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_before = Pt(0)
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.0
                paragraph.alignment = (
                    WD_ALIGN_PARAGRAPH.CENTER
                    if header or gene
                    else WD_ALIGN_PARAGRAPH.LEFT
                )
                for run in paragraph.runs:
                    run.font.size = Pt(8.0 if header or gene else 7.4)
                    run.font.bold = bool(header or gene)
                    if header:
                        run.font.color.rgb = RGBColor(255, 255, 255)

        def mutation_info(cells) -> str:
            transcript = clean_text(cells[1].text)
            chrom = clean_text(cells[2].text)
            exon = clean_text(cells[3].text)
            site = clean_text(cells[4].text)
            mutation_type = clean_text(cells[5].text)
            frequency = clean_text(cells[6].text)

            parts = []
            if keep_value(site):
                parts.append(f"位点：{site}")
            if keep_value(transcript):
                parts.append(f"转录本：{transcript}")
            location = []
            if keep_value(chrom):
                location.append(f"染色体 {chrom}")
            if keep_value(exon):
                location.append(f"外显子 {exon}")
            if location:
                parts.append("；".join(location))
            if keep_value(mutation_type):
                parts.append(f"突变类型：{mutation_type}")
            if keep_value(frequency):
                freq = frequency if frequency.endswith("%") else f"{frequency}%"
                parts.append(f"频率：{freq}")
            return "\n".join(parts) if parts else "--"

        def replace_with_compact_table(table) -> None:
            new_table = doc.add_table(rows=1, cols=4)
            try:
                new_table.style = table.style
            except Exception:
                pass

            set_table_fixed_layout(new_table)
            set_grid(new_table)

            header_row = new_table.rows[0]
            header_row.height = None
            for idx, label in enumerate(headers):
                cell = header_row.cells[idx]
                cell.text = label
                set_cell_width(cell, widths[idx])
                style_cell(cell, header=True)
            tr_pr = header_row._tr.get_or_add_trPr()
            tbl_header = tr_pr.find(qn("w:tblHeader"))
            if tbl_header is None:
                tr_pr.append(OxmlElement("w:tblHeader"))

            for source_row in table.rows[2:]:
                cells = source_row.cells
                if len(cells) < 9:
                    continue
                gene = clean_text(cells[0].text)
                info = mutation_info(cells)
                benefit = normalize_dash(cells[7].text)
                caution = normalize_dash(cells[8].text)
                if not gene and info == "--" and benefit == "--" and caution == "--":
                    continue

                row = new_table.add_row()
                values = [gene or "--", info, benefit, caution]
                for idx, value in enumerate(values):
                    cell = row.cells[idx]
                    cell.text = value
                    set_cell_width(cell, widths[idx])
                    style_cell(cell, gene=(idx == 0))

            old_tbl = table._tbl
            old_tbl.addprevious(new_table._tbl)
            old_tbl.getparent().remove(old_tbl)

        for table in list(doc.tables):
            if len(table.columns) != 9 or not table.rows:
                continue
            header_text = " ".join(cell.text for cell in table.rows[0].cells)
            if "基因名称" not in header_text or "靶向药物信息" not in header_text:
                continue
            replace_with_compact_table(table)
            changed = True

        if changed:
            doc.save(file_path)
            self.logger.debug("已优化2.1变异表布局")

    def _normalize_final_section_layout(self, file_path: str) -> None:
        """统一所有 section 的版心，避免正文后半段页面宽度异常。"""
        doc = Document(file_path)
        sections = list(doc.sections)
        if len(sections) < 2:
            return

        text = "\n".join(p.text for p in doc.paragraphs)
        if "第三部分：基因变异及相应靶向/免疫药物解析" not in text:
            return

        reference = sections[0]

        reference_metrics = (
            reference.page_width.twips,
            reference.page_height.twips,
            reference.left_margin.twips,
            reference.right_margin.twips,
            reference.top_margin.twips,
            reference.bottom_margin.twips,
            reference.header_distance.twips,
            reference.footer_distance.twips,
        )
        changed = 0
        for target in sections[1:]:
            target_metrics = (
                target.page_width.twips,
                target.page_height.twips,
                target.left_margin.twips,
                target.right_margin.twips,
                target.top_margin.twips,
                target.bottom_margin.twips,
                target.header_distance.twips,
                target.footer_distance.twips,
            )
            if target_metrics == reference_metrics:
                continue

            target.page_width = reference.page_width
            target.page_height = reference.page_height
            target.left_margin = reference.left_margin
            target.right_margin = reference.right_margin
            target.top_margin = reference.top_margin
            target.bottom_margin = reference.bottom_margin
            target.header_distance = reference.header_distance
            target.footer_distance = reference.footer_distance
            changed += 1

        if changed:
            doc.save(file_path)
            self.logger.debug("已统一页面布局", sections=changed)

    def _restore_reviewed_body_headers(self, file_path: str) -> None:
        """Keep appendix/result sections on the reviewed report header scheme.

        LibreOffice/docxtpl can materialize later sections with blank headers. The
        reviewed template uses the body header (logo + patient name + slogan) and
        its attached watermark/footer rule on the gene-list and tail pages, so
        later sections should link back to the first section that already has
        that body header.
        """
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        doc = Document(file_path)
        sections = list(doc.sections)
        if len(sections) < 3:
            return

        def header_text(section) -> str:
            parts = [p.text for p in section.header.paragraphs]
            for table in section.header.tables:
                for row in table.rows:
                    for cell in row.cells:
                        parts.append(cell.text)
            return "\n".join(parts)

        source_idx = None
        for idx, section in enumerate(sections):
            text = header_text(section)
            if "姓名：" in text and "科技服务人类健康" in text:
                source_idx = idx
                break

        if source_idx is None:
            return

        def ensure_footer_top_rule(footer) -> bool:
            changed_footer = False
            targets = footer.paragraphs or []
            if not targets:
                return False

            # The reviewed body/footer style has a black rule above the page
            # number. Some render paths preserve the page number text box but
            # drop the rule, so restore the rule without depending on page text.
            paragraph = targets[0]
            ppr = paragraph._p.get_or_add_pPr()
            p_bdr = ppr.find(qn("w:pBdr"))
            if p_bdr is None:
                p_bdr = OxmlElement("w:pBdr")
                ppr.append(p_bdr)
                changed_footer = True
            top = p_bdr.find(qn("w:top"))
            if top is None:
                top = OxmlElement("w:top")
                p_bdr.append(top)
                changed_footer = True
            attrs = {
                qn("w:val"): "single",
                qn("w:sz"): "4",
                qn("w:space"): "0",
                qn("w:color"): "000000",
            }
            for key, value in attrs.items():
                if top.get(key) != value:
                    top.set(key, value)
                    changed_footer = True
            return changed_footer

        changed = 0
        for section in sections[source_idx:]:
            text = header_text(section)
            has_body_header = "科技服务人类健康" in text

            if not has_body_header and section.different_first_page_header_footer:
                section.different_first_page_header_footer = False
                changed += 1
            if not has_body_header:
                for hdr in (
                    section.header,
                    section.first_page_header,
                    section.even_page_header,
                ):
                    if not hdr.is_linked_to_previous:
                        hdr.is_linked_to_previous = True
                        changed += 1
            for footer in (
                section.footer,
                section.first_page_footer,
                section.even_page_footer,
            ):
                if ensure_footer_top_rule(footer):
                    changed += 1

        if changed:
            doc.save(file_path)
            self.logger.debug("已恢复后置章节页眉页脚", sections=changed)

    def _normalize_toc_decoration_layout(self, file_path: str) -> None:
        """Move the TOC decorative vertical line left of the generated entries.

        The template keeps the cyan TOC line as a floating shape anchored to the
        "目    录" paragraph. Word/WPS/LibreOffice can lay out refreshed TOC text
        slightly differently, so the fixed template offset may cross the entry
        text. We only touch the line and small circle anchored to the TOC title.
        """
        import os
        import re
        import shutil
        import tempfile
        import xml.etree.ElementTree as ET
        from zipfile import ZIP_DEFLATED, ZipFile

        ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        ns_wp = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
        ns_v = "urn:schemas-microsoft-com:vml"
        for prefix, uri in {
            "w": ns_w,
            "wp": ns_wp,
            "v": ns_v,
            "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
            "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
            "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
            "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
            "o": "urn:schemas-microsoft-com:office:office",
        }.items():
            ET.register_namespace(prefix, uri)

        w_p = f"{{{ns_w}}}p"
        w_t = f"{{{ns_w}}}t"
        wp_anchor = f"{{{ns_wp}}}anchor"
        wp_position_h = f"{{{ns_wp}}}positionH"
        wp_position_v = f"{{{ns_wp}}}positionV"
        wp_pos_offset = f"{{{ns_wp}}}posOffset"
        wp_extent = f"{{{ns_wp}}}extent"
        wp_doc_pr = f"{{{ns_wp}}}docPr"
        v_line = f"{{{ns_v}}}line"
        v_shape = f"{{{ns_v}}}shape"

        line_offset_emu = 127000  # 10pt from the text area
        circle_offset_emu = 92710  # keep the circle centered on the line
        line_offset_top_emu = 533400  # 42pt below the TOC title anchor
        circle_offset_top_emu = 457200  # 36pt, centered above the line
        line_margin_left_pt = 10.0
        circle_margin_left_pt = 7.3
        line_margin_top_pt = 42.0
        circle_margin_top_pt = 36.0

        def para_text(elem) -> str:
            return "".join((node.text or "") for node in elem.iter(w_t))

        def is_toc_title(elem) -> bool:
            return "目录" in para_text(elem).replace(" ", "")

        def emu_value(elem, attr: str) -> int:
            try:
                return int(elem.get(attr) or "0")
            except ValueError:
                return 0

        def style_pt(style: str, key: str) -> float | None:
            match = re.search(rf"(?:^|;){re.escape(key)}:([-0-9.]+)pt", style)
            if not match:
                return None
            try:
                return float(match.group(1))
            except ValueError:
                return None

        def set_style_pt(style: str, key: str, value: float) -> str:
            formatted = f"{value:g}pt"
            pattern = rf"((?:^|;){re.escape(key)}:)[^;]+"
            if re.search(pattern, style):
                return re.sub(pattern, rf"\g<1>{formatted}", style, count=1)
            if style and not style.endswith(";"):
                style += ";"
            return f"{style}{key}:{formatted};"

        with ZipFile(file_path, "r") as zin:
            document_xml = zin.read("word/document.xml")
            document_info = zin.getinfo("word/document.xml")
            other_entries = [
                (info, zin.read(info.filename))
                for info in zin.infolist()
                if info.filename != "word/document.xml"
            ]

        root = ET.fromstring(document_xml)
        changed = 0

        for para in root.iter(w_p):
            if not is_toc_title(para):
                continue

            for anchor in para.iter(wp_anchor):
                doc_pr = anchor.find(wp_doc_pr)
                name = doc_pr.get("name", "") if doc_pr is not None else ""
                extent = anchor.find(wp_extent)
                if extent is None:
                    continue
                cx = emu_value(extent, f"{{{ns_wp}}}cx") or emu_value(extent, "cx")
                cy = emu_value(extent, f"{{{ns_wp}}}cy") or emu_value(extent, "cy")
                position_h = anchor.find(wp_position_h)
                pos_offset = position_h.find(wp_pos_offset) if position_h is not None else None
                position_v = anchor.find(wp_position_v)
                v_pos_offset = position_v.find(wp_pos_offset) if position_v is not None else None
                if pos_offset is None:
                    continue

                if "直接连接符" in name and cx <= 100000 and cy >= 2000000:
                    if pos_offset.text != str(line_offset_emu):
                        pos_offset.text = str(line_offset_emu)
                        changed += 1
                    if v_pos_offset is not None and v_pos_offset.text != str(line_offset_top_emu):
                        v_pos_offset.text = str(line_offset_top_emu)
                        changed += 1
                elif "椭圆" in name and cx <= 200000 and cy <= 200000:
                    if pos_offset.text != str(circle_offset_emu):
                        pos_offset.text = str(circle_offset_emu)
                        changed += 1
                    if v_pos_offset is not None and v_pos_offset.text != str(circle_offset_top_emu):
                        v_pos_offset.text = str(circle_offset_top_emu)
                        changed += 1

            for shape in list(para.iter(v_line)) + list(para.iter(v_shape)):
                style = shape.get("style") or ""
                height = style_pt(style, "height")
                width = style_pt(style, "width")
                if shape.tag == v_line and height and width and height >= 200 and width <= 5:
                    new_style = set_style_pt(style, "margin-left", line_margin_left_pt)
                    new_style = set_style_pt(new_style, "margin-top", line_margin_top_pt)
                elif (
                    shape.tag == v_shape
                    and height
                    and width
                    and 3 <= height <= 12
                    and 3 <= width <= 12
                ):
                    new_style = set_style_pt(style, "margin-left", circle_margin_left_pt)
                    new_style = set_style_pt(new_style, "margin-top", circle_margin_top_pt)
                else:
                    continue
                if new_style != style:
                    shape.set("style", new_style)
                    changed += 1

        if not changed:
            return

        fd, tmp_name = tempfile.mkstemp(suffix=".docx")
        os.close(fd)
        try:
            with ZipFile(tmp_name, "w", compression=ZIP_DEFLATED) as zout:
                zout.writestr(
                    document_info,
                    ET.tostring(root, encoding="utf-8", xml_declaration=True),
                )
                for info, data in other_entries:
                    zout.writestr(info, data)
            shutil.move(tmp_name, file_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

        self.logger.debug("已调整目录装饰线位置", changed=changed)

    def _populate_static_toc_page_numbers(self, file_path: str) -> None:
        """Write visible TOC page numbers from the final rendered PDF layout.

        LibreOffice can refresh the PAGEREF fields but may leave the tab run
        hidden, and in some environments it also preserves stale page numbers.
        Rendering the final docx to PDF gives us the authoritative pagination
        without requiring Microsoft Word UI permissions.
        """
        import shutil

        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        pdftotext = shutil.which("pdftotext")
        pdfinfo = shutil.which("pdfinfo")
        if not soffice or not pdftotext or not pdfinfo:
            self.logger.debug(
                "缺少 PDF 布局工具，跳过静态目录页码写回",
                soffice=bool(soffice),
                pdftotext=bool(pdftotext),
                pdfinfo=bool(pdfinfo),
            )
            return

        page_numbers = self._detect_toc_page_numbers_from_pdf_layout(
            file_path=file_path,
            soffice=soffice,
            pdftotext=pdftotext,
            pdfinfo=pdfinfo,
        )
        if not page_numbers:
            return

        if not self._write_static_toc_page_numbers(file_path, page_numbers):
            return

        # Re-render after removing TOC fields and updateFields. Static TOC
        # rewriting can slightly change layout, so the second pass is the
        # number set users will actually see in PDF/Word.
        final_numbers = self._detect_toc_page_numbers_from_pdf_layout(
            file_path=file_path,
            soffice=soffice,
            pdftotext=pdftotext,
            pdfinfo=pdfinfo,
        )
        if final_numbers and final_numbers != page_numbers:
            self._write_static_toc_page_numbers(file_path, final_numbers)
            page_numbers = final_numbers

        self.logger.info("已按最终 PDF 版式写回目录页码", output=file_path, page_numbers=page_numbers)

    def _write_static_toc_page_numbers(self, file_path: str, page_numbers: dict[str, int]) -> bool:
        """Replace TOC field results with plain visible labels and page numbers."""
        import os
        import re
        import shutil
        import tempfile
        from zipfile import ZIP_DEFLATED, ZipFile

        try:
            from lxml import etree
        except Exception as exc:
            self.logger.debug("缺少 lxml，跳过静态目录页码写回", error=str(exc))
            return False

        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        w_ns = ns["w"]

        def qn(tag: str) -> str:
            return f"{{{w_ns}}}{tag}"

        def normalize_label(text: str) -> str:
            text = re.sub(r"\s+", "", text or "")
            text = re.sub(r"\d+$", "", text)
            return text

        src = Path(file_path)
        with ZipFile(src, "r") as zin:
            document_xml = zin.read("word/document.xml")
            root = etree.fromstring(document_xml)

            toc_sdt = None
            for sdt in root.xpath(".//w:sdt", namespaces=ns):
                instr = "".join(sdt.xpath(".//w:instrText/text()", namespaces=ns))
                text = "".join(sdt.xpath(".//w:t/text()", namespaces=ns))
                if "TOC" in instr or (
                    "第一部分" in text and "第四部分" in text and "参考文献" in text
                ):
                    toc_sdt = sdt
                    break
            if toc_sdt is None:
                return False

            section_labels = [
                "第一部分：基本信息",
                "第二部分：检测结果",
                "第三部分：基因变异及相应靶向/免疫药物解析",
                "第四部分：附录",
            ]
            display_labels = {
                normalize_label(label): label
                for label in [*section_labels, *page_numbers.keys()]
            }
            normalized_numbers = {
                normalize_label(label): str(number)
                for label, number in page_numbers.items()
            }
            changed = False

            def make_run(text: str | None = None, *, tab: bool = False) -> Any:
                run = etree.Element(qn("r"))
                r_pr = etree.SubElement(run, qn("rPr"))
                fonts = etree.SubElement(r_pr, qn("rFonts"))
                fonts.set(qn("ascii"), "微软雅黑")
                fonts.set(qn("hAnsi"), "微软雅黑")
                fonts.set(qn("eastAsia"), "微软雅黑")
                fonts.set(qn("cs"), "Times New Roman")
                size = etree.SubElement(r_pr, qn("sz"))
                size.set(qn("val"), "22")
                size_cs = etree.SubElement(r_pr, qn("szCs"))
                size_cs.set(qn("val"), "22")
                underline = etree.SubElement(r_pr, qn("u"))
                underline.set(qn("val"), "none")
                if tab:
                    etree.SubElement(run, qn("tab"))
                else:
                    t = etree.SubElement(run, qn("t"))
                    t.text = text or ""
                return run

            for para in toc_sdt.xpath(".//w:p", namespaces=ns):
                text_nodes = para.xpath(".//w:t", namespaces=ns)
                para_text = "".join(node.text or "" for node in text_nodes)
                label = normalize_label(para_text)
                display_label = display_labels.get(label)
                if display_label is None:
                    continue

                # Replace the field/hyperlink result with plain static runs.
                # This prevents later Office/PDF engines from hiding or
                # regenerating the PAGEREF result differently.
                for child in list(para):
                    if child.tag != qn("pPr"):
                        para.remove(child)
                para.append(make_run(display_label))
                if label in normalized_numbers:
                    para.append(make_run(tab=True))
                    para.append(make_run(normalized_numbers[label]))
                changed = True

            if not changed:
                return False

            patched_xml = etree.tostring(
                root,
                xml_declaration=True,
                encoding="UTF-8",
                standalone="yes",
            )

            fd, tmp_name = tempfile.mkstemp(
                suffix=".docx",
                prefix=f"{src.stem}_toc_",
                dir=str(src.parent),
            )
            os.close(fd)
            tmp_path = Path(tmp_name)
            try:
                with ZipFile(tmp_path, "w", ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        if item.filename == "word/document.xml":
                            data = patched_xml
                        elif item.filename == "word/settings.xml":
                            data = self._remove_update_fields_setting(zin.read(item.filename))
                        else:
                            data = zin.read(item.filename)
                        zout.writestr(item, data)
                shutil.move(str(tmp_path), str(src))
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

        return True

    def _remove_update_fields_setting(self, settings_xml: bytes) -> bytes:
        """Disable automatic field refresh after static TOC page numbers are written."""
        try:
            from lxml import etree
        except Exception:
            return settings_xml

        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        root = etree.fromstring(settings_xml)
        changed = False
        for elem in root.xpath(".//w:updateFields", namespaces=ns):
            parent = elem.getparent()
            if parent is not None:
                parent.remove(elem)
                changed = True
        if not changed:
            return settings_xml
        return etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone="yes",
        )

    def _detect_toc_page_numbers_from_pdf_layout(
        self,
        *,
        file_path: str,
        soffice: str,
        pdftotext: str,
        pdfinfo: str,
    ) -> dict[str, int]:
        """Render DOCX to PDF and infer report-page numbers for TOC entries."""
        import re
        import shutil
        import subprocess
        import tempfile

        toc_entries: list[tuple[str, tuple[str, ...]]] = [
            ("患者及样本信息", ("患者信息", "患者及样本信息")),
            ("检测内容", ("检测内容",)),
            ("检测结果小结", ("1.检测结果小结", "检测结果小结")),
            ("靶向药物相关检测结果", ("2.靶向药物相关检测结果", "靶向药物相关检测结果")),
            ("免疫治疗疗效评估", ("3.免疫治疗疗效评估", "免疫治疗疗效评估")),
            ("检测结果说明", ("4.检测结果说明", "检测结果说明")),
            ("基因变异解析", ("基因变异解析",)),
            ("靶向药物/免疫用药提示解析", ("靶向药物/免疫用药提示解析",)),
            ("阅读说明", ("阅读说明",)),
            ("常见问题解答", ("常见问题解答",)),
            ("结直肠癌诊疗知识", ("结直肠癌诊疗知识",)),
            ("癌症相关信号通路", ("癌症相关信号通路",)),
            ("基因检测列表", ("基因检测列表", "GeneListforMLseq")),
            ("参考文献", ("5.参考文献",)),
        ]

        def normalize(text: str) -> str:
            return re.sub(r"\s+", "", text or "")

        with tempfile.TemporaryDirectory(prefix="reportgen_pdf_") as tmp_dir, tempfile.TemporaryDirectory(
            prefix="reportgen_pdf_profile_"
        ) as profile_dir:
            tmp_dir_path = Path(tmp_dir)
            input_dir = tmp_dir_path / "input"
            output_dir = tmp_dir_path / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            tmp_input = input_dir / "input.docx"
            shutil.copy2(file_path, tmp_input)

            cmd = [
                soffice,
                f"-env:UserInstallation=file://{Path(profile_dir).as_posix()}",
                "--headless",
                "--nologo",
                "--nolockcheck",
                "--nodefault",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(tmp_input),
            ]
            try:
                subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=180,
                )
            except Exception as exc:
                self.logger.debug("目录页码 PDF 渲染失败，跳过静态写回", error=str(exc))
                return {}

            pdf_path = output_dir / "input.pdf"
            if not pdf_path.exists():
                return {}

            try:
                info = subprocess.run(
                    [pdfinfo, str(pdf_path)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30,
                ).stdout
                match = re.search(r"^Pages:\s+(\d+)", info, flags=re.MULTILINE)
                page_count = int(match.group(1)) if match else 0
            except Exception:
                page_count = 0
            if page_count <= 0:
                return {}

            page_texts: dict[int, str] = {}
            normalized_pages: dict[int, str] = {}
            for page in range(1, page_count + 1):
                try:
                    text = subprocess.run(
                        [pdftotext, "-f", str(page), "-l", str(page), str(pdf_path), "-"],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=30,
                    ).stdout
                except Exception:
                    text = ""
                page_texts[page] = text
                normalized_pages[page] = normalize(text)

        toc_page = next(
            (
                page for page, text in normalized_pages.items()
                if "目录" in text and "第一部分" in text and "参考文献" in text
            ),
            None,
        )
        if toc_page is None:
            return {}

        content_start = next(
            (
                page for page in range(toc_page + 1, page_count + 1)
                if "患者信息" in normalized_pages.get(page, "")
                and "检测内容" in normalized_pages.get(page, "")
            ),
            None,
        )
        if content_start is None:
            content_start = toc_page + 1

        page_numbers: dict[str, int] = {}
        for label, needles in toc_entries:
            found_page = None
            for page in range(content_start, page_count + 1):
                page_text = normalized_pages.get(page, "")
                if any(normalize(needle) in page_text for needle in needles):
                    found_page = page
                    break
            if found_page is not None:
                page_numbers[label] = found_page - content_start + 1

        return page_numbers

    def _compact_gene_list_tables(self, file_path: str, context: dict | None = None) -> None:
        """Align static gene-list tables with the reviewed report layout."""
        from docx.enum.table import WD_ROW_HEIGHT_RULE
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Cm, Pt

        doc = Document(file_path)
        changed = 0
        content_cfg = self._report_content_config(context)
        style_cfg = content_cfg.get("gene_list_table_style")
        style_cfg = style_cfg if isinstance(style_cfg, dict) else {}
        row_height_cm = self._float_config(style_cfg.get("row_height_cm"), 0.88)
        header_font_size = self._float_config(style_cfg.get("header_font_size"), 14.0)
        body_font_size = self._float_config(style_cfg.get("body_font_size"), 10.5)

        for table in doc.tables:
            if not table.rows:
                continue
            header_text = " ".join(cell.text for cell in table.rows[0].cells)
            if "Gene List for MLseq" not in header_text and "基因检测列表" not in header_text:
                continue

            for row_idx, row in enumerate(table.rows):
                row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
                row.height = Cm(row_height_cm)
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        paragraph.paragraph_format.space_before = Pt(0)
                        paragraph.paragraph_format.space_after = Pt(0)
                        paragraph.paragraph_format.line_spacing = 1.0
                        for run in paragraph.runs:
                            run.font.size = Pt(body_font_size if row_idx else header_font_size)
                            run.font.underline = False
                changed += 1

        if changed:
            doc.save(file_path)
            self.logger.debug("已对齐基因检测列表样式", rows=changed)

    def _normalize_quality_control_tables(self, file_path: str) -> None:
        """Prevent template-inherited underlines in the quality-control table."""
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt

        doc = Document(file_path)
        changed = 0
        for table in doc.tables:
            if not table.rows:
                continue
            header_text = " ".join(cell.text.strip() for cell in table.rows[0].cells)
            if "质控项" not in header_text or "质控结果" not in header_text:
                continue
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        paragraph.paragraph_format.space_before = Pt(0)
                        paragraph.paragraph_format.space_after = Pt(0)
                        for run in paragraph.runs:
                            run.font.underline = False
                            changed += 1

        if changed:
            doc.save(file_path)
            self.logger.debug("已修复质控表下划线继承", runs=changed)

    def _remove_trailing_hla_table(self, file_path: str) -> None:
        """移除文档尾部孤立的 HLA 表格。"""
        doc = Document(file_path)
        if not doc.tables:
            return

        last_table = doc.tables[-1]
        first_row_text = " ".join(cell.text.strip() for cell in last_table.rows[0].cells) if last_table.rows else ""
        if "HLA位点" not in first_row_text:
            return

        last_table._tbl.getparent().remove(last_table._tbl)
        doc.save(file_path)
        self.logger.debug("已移除文档尾部HLA表格")

    def _set_update_fields(self, file_path: str) -> None:
        """设置 docx 的 updateFields 属性，让 Word 打开时自动刷新目录/页码域。"""
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        doc = Document(file_path)
        settings = doc.settings.element

        # 添加 <w:updateFields w:val="true"/>
        update_fields = settings.find(qn("w:updateFields"))
        if update_fields is None:
            update_fields = OxmlElement("w:updateFields")
            settings.append(update_fields)
        update_fields.set(qn("w:val"), "true")

        doc.save(file_path)
        self.logger.debug("已设置 updateFields=true，Word 打开时将刷新目录")

    def _refresh_fields_with_native_engine(self, file_path: str) -> None:
        """优先使用可用的原生排版引擎刷新目录/页码域。"""
        import os
        import sys

        if not self._document_contains_toc(file_path):
            self.logger.debug("文档不包含 TOC 域，跳过目录刷新", output=file_path)
            return

        if sys.platform.startswith("linux"):
            self._refresh_fields_with_libreoffice(file_path)
            return

        if sys.platform == "darwin":
            use_word = str(os.environ.get("REPORTGEN_REFRESH_WITH_WORD") or "").strip().lower()
            if use_word in {"1", "true", "yes", "y", "on"}:
                try:
                    self._refresh_fields_with_word_macos(file_path)
                    return
                except Exception as exc:
                    self.logger.debug(
                        "Word 刷新目录失败，尝试回退",
                        output=file_path,
                        error=str(exc),
                    )
            # Word opened via AppleScript often triggers macOS sandbox prompts
            # for files on external volumes. LibreOffice is the non-interactive
            # default; Word refresh remains opt-in through REPORTGEN_REFRESH_WITH_WORD.
            self._refresh_fields_with_libreoffice(file_path)
            return

        self._refresh_fields_with_libreoffice(file_path)

    def _document_contains_toc(self, file_path: str) -> bool:
        """检查 docx 是否包含 TOC 域。"""
        from zipfile import ZipFile

        try:
            with ZipFile(file_path, "r") as zf:
                document_xml = zf.read("word/document.xml").decode("utf-8", "ignore")
        except Exception as exc:
            raise RuntimeError(f"读取文档目录域失败: {exc}") from exc

        return "TOC" in document_xml

    def _refresh_fields_with_word_macos(self, file_path: str) -> None:
        """使用 macOS 上的 Microsoft Word 最佳努力刷新目录和页码域。"""
        import shutil
        import subprocess

        osascript = shutil.which("osascript")
        word_app = Path("/Applications/Microsoft Word.app")
        if not osascript or not word_app.exists():
            raise RuntimeError("未找到 Microsoft Word 或 osascript")

        script_lines = [
            'tell application "Microsoft Word"',
            "set display alerts to alerts none",
            "set wasRunning to running",
            "set preDocCount to count of documents",
            "set visible to false",
            f'open file name "{file_path}"',
            "delay 4",
            "try",
            "repeat with tocRef in (tables of contents of document 1)",
            "update tocRef",
            "update page numbers tocRef",
            "end repeat",
            "end try",
            "try",
            "save document 1",
            "end try",
            "delay 1",
            "set remainingDocs to 0",
            "try",
            "set remainingDocs to count of documents",
            "end try",
            "if (wasRunning is false) and (preDocCount = 0) and (remainingDocs = 0) then",
            "try",
            "quit saving no",
            "end try",
            "end if",
            "return remainingDocs",
            "end tell",
        ]
        command = [osascript, "-l", "AppleScript"]
        for line in script_lines:
            command.extend(["-e", line])

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=self.WORD_REFRESH_TIMEOUT_SECONDS,
                check=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Microsoft Word 刷新目录超时"
                f"（{self.WORD_REFRESH_TIMEOUT_SECONDS}秒），"
                "可能缺少 Apple Events 授权或 Word 首次启动未完成"
            ) from exc
        self.logger.debug(
            "已执行 Microsoft Word 目录刷新流程",
            output=file_path,
            log=result.stdout.strip(),
        )

    def _refresh_fields_with_libreoffice(self, file_path: str) -> None:
        """使用 LibreOffice 最佳努力刷新目录/页码域。

        仅在系统存在 `soffice`/`libreoffice` 且文档中包含 TOC 域时执行。
        失败时抛异常，由上层降级回 `updateFields=true`。
        """
        import shutil

        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice:
            self.logger.debug("未找到 LibreOffice 二进制", output=file_path)
            raise RuntimeError("未找到 LibreOffice，目录页码仅保留 updateFields 兜底")

        if not self._document_contains_toc(file_path):
            self.logger.debug("文档不包含 TOC 域，跳过 LibreOffice 目录刷新", output=file_path)
            return

        try:
            self._refresh_fields_with_libreoffice_uno(file_path, soffice)
            return
        except Exception as exc:
            self.logger.debug(
                "LibreOffice UNO 刷新失败，回退 convert-to 路径",
                output=file_path,
                error=str(exc),
            )

        self._refresh_fields_with_libreoffice_convert(file_path, soffice)

    def _refresh_fields_with_libreoffice_uno(self, file_path: str, soffice: str) -> None:
        """通过 LibreOffice UNO 显式更新目录索引并重新保存 docx。"""
        import shutil
        import socket
        import subprocess
        import tempfile
        import textwrap

        python_candidates = [Path("/usr/bin/python3"), Path(shutil.which("python3") or "")]
        uno_python = None
        for candidate in python_candidates:
            if not candidate or not str(candidate):
                continue
            if not candidate.exists():
                continue
            probe = subprocess.run(
                [str(candidate), "-c", "import uno"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if probe.returncode == 0:
                uno_python = str(candidate)
                break
        if not uno_python:
            raise RuntimeError("未找到支持 python3-uno 的系统 Python")

        with tempfile.TemporaryDirectory(prefix="reportgen_lo_") as tmp_dir, tempfile.TemporaryDirectory(
            prefix="reportgen_lo_profile_"
        ) as profile_dir:
            input_dir = Path(tmp_dir) / "input"
            output_dir = Path(tmp_dir) / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            tmp_input = input_dir / "input.docx"
            refreshed = output_dir / "refreshed.docx"
            shutil.copy2(file_path, tmp_input)

            probe_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe_sock.bind(("127.0.0.1", 0))
            port = probe_sock.getsockname()[1]
            probe_sock.close()

            uno_script = Path(tmp_dir) / "refresh_with_uno.py"
            uno_script.write_text(
                textwrap.dedent(
                    """
                    import sys
                    import time
                    import uno
                    from com.sun.star.beans import PropertyValue

                    def prop(name, value):
                        item = PropertyValue()
                        item.Name = name
                        item.Value = value
                        return item

                    input_path, output_path, port = sys.argv[1], sys.argv[2], sys.argv[3]
                    local_ctx = uno.getComponentContext()
                    resolver = local_ctx.ServiceManager.createInstanceWithContext(
                        "com.sun.star.bridge.UnoUrlResolver",
                        local_ctx,
                    )

                    ctx = None
                    last_error = None
                    deadline = time.time() + 30
                    while time.time() < deadline:
                        try:
                            ctx = resolver.resolve(
                                f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext"
                            )
                            break
                        except Exception as exc:
                            last_error = exc
                            time.sleep(0.5)

                    if ctx is None:
                        raise RuntimeError(f"UNO 连接失败: {last_error}")

                    desktop = ctx.ServiceManager.createInstanceWithContext(
                        "com.sun.star.frame.Desktop",
                        ctx,
                    )
                    load_props = (
                        prop("Hidden", True),
                        prop("ReadOnly", False),
                        prop("UpdateDocMode", 1),
                    )
                    doc = desktop.loadComponentFromURL(
                        uno.systemPathToFileUrl(input_path),
                        "_blank",
                        0,
                        load_props,
                    )
                    try:
                        doc.refresh()
                    except Exception:
                        pass
                    try:
                        doc.TextFields.refresh()
                    except Exception:
                        pass
                    try:
                        indexes = doc.getDocumentIndexes()
                        for idx in range(indexes.getCount()):
                            indexes.getByIndex(idx).update()
                    except Exception:
                        pass
                    time.sleep(1)
                    doc.storeAsURL(
                        uno.systemPathToFileUrl(output_path),
                        (prop("FilterName", "Office Open XML Text"),),
                    )
                    doc.close(True)
                    """
                ).strip(),
                encoding="utf-8",
            )

            listener_cmd = [
                soffice,
                f"-env:UserInstallation=file://{Path(profile_dir).as_posix()}",
                "--headless",
                "--nologo",
                "--nolockcheck",
                "--nodefault",
                f"--accept=socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext",
            ]
            listener = subprocess.Popen(
                listener_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            try:
                result = subprocess.run(
                    [uno_python, str(uno_script), str(tmp_input), str(refreshed), str(port)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=180,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("LibreOffice 刷新目录超时") from exc
            except subprocess.CalledProcessError as exc:
                log = "\n".join(part for part in [(exc.stdout or "").strip(), (exc.stderr or "").strip()] if part)
                raise RuntimeError(
                    f"LibreOffice UNO 刷新失败: {log or exc}"
                ) from exc
            finally:
                listener.terminate()
                try:
                    listener.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    listener.kill()
                    listener.wait(timeout=5)

            if not refreshed.exists():
                log = "\n".join(
                    part for part in [(result.stdout or "").strip(), (result.stderr or "").strip()] if part
                )
                raise RuntimeError(
                    f"LibreOffice UNO 未生成刷新后的文档: {log}"
                )

            try:
                Document(refreshed)
            except Exception as exc:
                raise RuntimeError(f"LibreOffice UNO 生成的文档不可读: {exc}") from exc

            shutil.copy2(refreshed, file_path)
            log = "\n".join(part for part in [(result.stdout or "").strip(), (result.stderr or "").strip()] if part)
            self.logger.info(
                "已使用 LibreOffice 刷新目录/页码",
                output=file_path,
                engine=Path(soffice).name,
                log=log,
            )

    def _refresh_fields_with_libreoffice_convert(self, file_path: str, soffice: str) -> None:
        """回退路径：通过 LibreOffice convert-to 重写 docx。"""
        import shutil
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory(prefix="reportgen_lo_") as tmp_dir, tempfile.TemporaryDirectory(
            prefix="reportgen_lo_profile_"
        ) as profile_dir:
            input_dir = Path(tmp_dir) / "input"
            output_dir = Path(tmp_dir) / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            tmp_input = input_dir / "input.docx"
            shutil.copy2(file_path, tmp_input)

            cmd = [
                soffice,
                f"-env:UserInstallation=file://{Path(profile_dir).as_posix()}",
                "--headless",
                "--nologo",
                "--nolockcheck",
                "--nodefault",
                "--convert-to",
                'docx:Office Open XML Text',
                "--outdir",
                str(output_dir),
                str(tmp_input),
            ]
            try:
                result = subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=180,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("LibreOffice convert-to 刷新目录超时") from exc
            except subprocess.CalledProcessError as exc:
                log = "\n".join(part for part in [(exc.stdout or "").strip(), (exc.stderr or "").strip()] if part)
                raise RuntimeError(
                    f"LibreOffice convert-to 刷新目录失败: {log or exc}"
                ) from exc

            refreshed = output_dir / "input.docx"
            if not refreshed.exists():
                log = "\n".join(
                    part for part in [(result.stdout or "").strip(), (result.stderr or "").strip()] if part
                )
                raise RuntimeError(
                    f"LibreOffice convert-to 未生成刷新后的文档: {log}"
                )

            try:
                Document(refreshed)
            except Exception as exc:
                raise RuntimeError(f"LibreOffice convert-to 生成的文档不可读: {exc}") from exc

            shutil.copy2(refreshed, file_path)
            log = "\n".join(part for part in [(result.stdout or "").strip(), (result.stderr or "").strip()] if part)
            self.logger.info(
                "已使用 LibreOffice 刷新目录/页码",
                output=file_path,
                engine=Path(soffice).name,
                log=log,
            )
