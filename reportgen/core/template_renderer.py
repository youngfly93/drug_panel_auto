"""
模板渲染器

负责使用docxtpl渲染Docx模板。
"""

from pathlib import Path
from typing import Optional

from docx import Document

from reportgen.core.template_contract import (
    extract_template_contract,
    validate_contract,
)
from reportgen.models.report_data import ReportData
from reportgen.utils.logger import get_logger
from reportgen.utils.validators import validate_docx_file


class TemplateRenderer:
    """
    模板渲染器

    使用docxtpl将报告数据填充到Docx模板。
    """

    def __init__(self, log_file: Optional[str] = None, log_level: str = "INFO"):
        """
        初始化模板渲染器

        Args:
            log_file: 日志文件路径
            log_level: 日志级别
        """
        self.logger = get_logger(log_file=log_file, level=log_level)

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

            # 渲染后清理：移除完全空白的表格行（避免循环控制行残留导致的空行）
            try:
                self._cleanup_empty_table_rows(output_path)
            except Exception:
                # 清理失败不影响主流程
                pass

            # Part 3 后处理：将占位标记替换为格式化的基因解读段落
            try:
                self._render_part3_formatted(output_path, context)
            except Exception as e:
                self.logger.warning("Part 3 格式化渲染失败", error=str(e))

            # 设置 updateFields=true，让 Word 打开时自动刷新目录/页码域
            try:
                self._set_update_fields(output_path)
            except Exception:
                pass

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

    def build_context(self, report_data: ReportData) -> dict:
        """Build a normalized template context from ReportData."""
        return self._normalize_template_context(report_data.get_template_context())

    def validate_template_contract(self, template_path: str, context: dict) -> dict:
        """Validate that the template's referenced variables exist in the context.

        Returns:
            A JSON-serializable dict describing missing variables/fields.
        """
        contract = extract_template_contract(template_path)
        validation = validate_contract(contract, context=context)
        return {
            "ok": bool(validation.ok),
            "missing_paths": list(validation.missing_paths),
            "missing_lists": list(validation.missing_lists),
            "missing_row_fields": {
                k: list(v) for k, v in validation.missing_row_fields.items()
            },
            "missing_row_examples": validation.missing_row_examples,
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

    def _render_part3_formatted(self, file_path: str, context: dict) -> None:
        """将 {{PART3_PLACEHOLDER}} 替换为格式化的 Part 3 段落。

        对齐参考终版格式：
        - 变异标题：bold=True, size=12pt, color=FF0000(有药物)/0000FF(无药物), 前缀"u "
        - 变异说明：size=10.5pt
        - 基因简介：size=10.5pt
        - 药物标题：bold=True, color=FF0000
        """
        from docx.shared import Pt, RGBColor
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        doc = Document(file_path)

        # 找到占位标记段落
        placeholder_para = None
        placeholder_idx = None
        for i, p in enumerate(doc.paragraphs):
            if "__PART3_MARKER__" in p.text:
                placeholder_para = p
                placeholder_idx = i
                break

        if placeholder_para is None:
            return  # 无占位标记，跳过

        # 获取数据
        sections = context.get("gene_knowledge_sections", [])
        benefit_sections = context.get("drug_benefit_sections", [])
        caution_sections = context.get("drug_caution_sections", [])
        references = context.get("gene_references", [])
        total_count = context.get("total_variants_count", 0)
        drug_count = context.get("drug_related_count", 0)

        # 辅助函数：在指定元素后插入新段落
        def add_para_after(prev_element, text, bold=False, size=10.5,
                          color=None, prefix=""):
            new_p = OxmlElement("w:p")
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
