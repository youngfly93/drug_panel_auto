"""
字段映射器

负责将Excel字段映射到模板变量。
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from reportgen.config.loader import ConfigLoader
from reportgen.core._field_mapper_immune import ImmuneGeneMixin
from reportgen.core._field_mapper_targeted_drugs import TargetedDrugMixin
from reportgen.models.excel_data import ExcelDataSource
from reportgen.models.mapping import FieldMapping, TableMapping
from reportgen.models.report_data import ReportData
from reportgen.utils.hgvs_utils import format_variant_site, infer_variant_type_cn
from reportgen.utils.logger import get_logger


class FieldMapper(TargetedDrugMixin, ImmuneGeneMixin):
    """
    字段映射器

    根据映射配置将Excel数据映射到模板变量。
    """

    def __init__(
        self,
        config_dir: str = "config",
        log_file: Optional[str] = None,
        log_level: str = "INFO",
    ):
        """
        初始化字段映射器

        Args:
            config_dir: 配置目录
            log_file: 日志文件路径
            log_level: 日志级别
        """
        self.config_loader = ConfigLoader(
            config_dir=config_dir, log_file=log_file, log_level=log_level
        )
        self.logger = get_logger(log_file=log_file, level=log_level)

        # 加载映射配置
        self.mapping_config = self.config_loader.load_mapping_config()

        # 🔥 NEW: 加载过滤配置
        self.filtering_config = self.config_loader.load_filtering_config()

        # 构建映射对象
        self.single_value_mappings = self._build_single_value_mappings()
        self.table_mappings = self._build_table_mappings()

        # 靶向药物提示数据库（可选）缓存：避免每次map都重复打开xlsx
        self._targeted_drug_db_loaded = False
        self._targeted_drug_db: Optional[pd.DataFrame] = None
        self._targeted_drug_db_cols: dict[str, str] = {}

        # 免疫相关基因列表（可选）缓存
        self._immune_gene_list_loaded = False
        self._immune_gene_sets: dict[str, set[str]] = {}

    def _build_single_value_mappings(self) -> Dict[str, FieldMapping]:
        """
        构建单值字段映射

        Returns:
            映射字典，key为变量名
        """
        mappings = {}
        single_values_config = self.mapping_config.get("single_values", {})

        for var_name, var_config in single_values_config.items():
            mapping = FieldMapping(
                variable_name=var_name,
                synonyms=var_config.get("synonyms", []),
                data_type=var_config.get("type", "string"),
                required=var_config.get("required", False),
                default_value=var_config.get("default_value"),
                format_template=var_config.get("format_template"),
                description=var_config.get("description", ""),
            )
            mappings[var_name] = mapping

        self.logger.debug("构建单值映射", count=len(mappings))
        return mappings

    def _build_table_mappings(self) -> Dict[str, TableMapping]:
        """
        构建表格映射

        Returns:
            映射字典，key为表格名
        """
        mappings = {}
        table_data_config = self.mapping_config.get("table_data", {})

        for table_name, table_config in table_data_config.items():
            # 构建列映射
            column_mappings = {}
            columns_config = table_config.get("columns", {})

            for col_var_name, col_config in columns_config.items():
                col_mapping = FieldMapping(
                    variable_name=col_var_name,
                    synonyms=col_config.get("synonyms", []),
                    data_type=col_config.get("type", "string"),
                    required=col_config.get("required", False),
                    default_value=col_config.get("default_value"),
                    format_template=col_config.get("format_template"),
                    description=col_config.get("description", ""),
                )
                column_mappings[col_var_name] = col_mapping

            # 构建表格映射
            table_mapping = TableMapping(
                table_name=table_name,
                sheet_name=table_config.get("sheet_name", ""),
                column_mappings=column_mappings,
                required=table_config.get("required", False),
                empty_behavior=table_config.get("empty_behavior", "show_placeholder"),
                filter=table_config.get("filter"),  # 🔥 NEW: 添加过滤配置支持
            )
            mappings[table_name] = table_mapping

        self.logger.debug("构建表格映射", count=len(mappings))
        return mappings

    def map(self, excel_data: ExcelDataSource) -> ReportData:
        """
        映射Excel数据到报告数据

        Args:
            excel_data: Excel数据源

        Returns:
            ReportData对象
        """
        self.logger.info("开始字段映射", source_file=excel_data.file_path)

        report_data = ReportData(
            metadata={"source_file": excel_data.file_path, **excel_data.metadata}
        )

        # ✅ 先尝试从metadata中获取样本编号
        sample_id_from_filename = excel_data.metadata.get("sample_id_from_filename")
        if sample_id_from_filename:
            report_data.set_field("sample_id", sample_id_from_filename)
            self.logger.info("从文件名提取样本编号", sample_id=sample_id_from_filename)

        # ✅ Week 3: 从配置文件加载患者信息
        patient_info = self.config_loader.load_patient_info(sample_id_from_filename)
        if patient_info:
            for key, value in patient_info.items():
                # 只在字段为空时才设置，避免覆盖已有数据
                if report_data.get_field(key) is None:
                    report_data.set_field(key, value)
                    self.logger.debug("从配置文件加载患者信息", field=key, value=value)

        # 映射单值字段
        self._map_single_values(excel_data, report_data)

        # 映射表格数据
        self._map_tables(excel_data, report_data)

        # 兼容性别名：为历史模板提供 TMB / MSI状态 字段
        # 每个逻辑块独立 try/except，避免单点故障导致所有衍生字段丢失

        # Block 1: TMB 兼容别名
        try:
            tmb_val = report_data.get_field("tmb_value")
            tmb_unit = report_data.get_field("tmb_unit") or ""
            if tmb_val is not None and report_data.get_field("TMB") is None:
                tmb_text = f"{tmb_val} {tmb_unit}".strip()
                report_data.set_field("TMB", tmb_text)
            if report_data.get_field("tmb") is None:
                if tmb_val is None:
                    report_data.set_field("tmb", "")
                else:
                    report_data.set_field("tmb", f"{tmb_val} {tmb_unit}".strip())
        except Exception as e:
            self.logger.warning("TMB兼容别名生成失败", error=str(e))

        # Block 2: MSI 兼容别名
        try:
            msi = report_data.get_field("msi_status")
            if msi is not None and report_data.get_field("MSI状态") is None:
                report_data.set_field("MSI状态", msi)
            if report_data.get_field("msi") is None:
                report_data.set_field("msi", msi or "")

            msi_cn = self._build_msi_status_cn(msi) or ""
            cur_msi_cn = (report_data.get_field("msi_status_cn") or "").strip()
            if (not cur_msi_cn) or (
                cur_msi_cn == "微卫星稳定型，MSS"
                and str(msi or "").strip().upper() not in {"", "MSS"}
            ):
                if msi_cn:
                    report_data.set_field("msi_status_cn", msi_cn)
        except Exception as e:
            self.logger.warning("MSI兼容别名生成失败", error=str(e))

        # Block 3: TMB 参考值/分级计算
        try:
            sample_type = str(report_data.get_field("sample_type") or "组织")
            threshold = (
                16 if ("血" in sample_type or "blood" in sample_type.lower()) else 10
            )

            try:
                cur_ref = report_data.get_field("tmb_reference")
                cur_ref_val = float(cur_ref) if cur_ref is not None else None
            except (ValueError, TypeError):
                cur_ref_val = None
            if cur_ref_val is None or (cur_ref_val == 10 and threshold == 16):
                report_data.set_field("tmb_reference", threshold)

            tmb_val = report_data.get_field("tmb_value")
            if tmb_val is not None:
                try:
                    tmb = float(tmb_val)
                    tmb_status = "H" if tmb >= threshold else "L"
                    report_data.set_field("tmb_status", tmb_status)
                    report_data.set_field(
                        "tmb_level_cn", "高" if tmb_status == "H" else "低"
                    )
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            self.logger.warning("TMB参考值/分级计算失败", error=str(e))

        # Block 4: 免疫治疗提示
        try:
            msi = report_data.get_field("msi_status")
            tmb_status = report_data.get_field("tmb_status")
            tips = self._build_immuno_tips(msi, tmb_status=tmb_status) or ""
            if (report_data.get_field("immuno_tips") or "").strip() == "":
                report_data.set_field("immuno_tips", tips)
        except Exception as e:
            self.logger.warning("免疫治疗提示生成失败", error=str(e))

        # Block 5: TMB 摘要
        try:
            tmb_summary = self._build_tmb_summary(report_data) or ""
            if (report_data.get_field("tmb_summary") or "").strip() == "":
                report_data.set_field("tmb_summary", tmb_summary)
        except Exception as e:
            self.logger.warning("TMB摘要生成失败", error=str(e))

        # Block 6: MSI 摘要
        try:
            msi = report_data.get_field("msi_status")
            msi_summary = self._build_msi_summary(msi) or ""
            if (report_data.get_field("msi_summary") or "").strip() == "":
                report_data.set_field("msi_summary", msi_summary)
        except Exception as e:
            self.logger.warning("MSI摘要生成失败", error=str(e))

        # Block 7: 免疫基因分类摘要
        try:
            immuno_summary = self._build_immuno_gene_summary(excel_data)
            for field, key in [
                ("immuno_positive_genes", "pos"),
                ("immuno_negative_genes", "neg"),
                ("immuno_hyperprogression_genes", "hyper"),
            ]:
                cur = report_data.get_field(field)
                if cur is None or str(cur).strip() in {"", "未检出"}:
                    report_data.set_field(field, immuno_summary[key])
        except Exception as e:
            self.logger.warning("免疫基因分类摘要生成失败", error=str(e))

        self.logger.info(
            "字段映射完成",
            fields_mapped=len(
                [k for k, v in report_data.context.items() if not isinstance(v, list)]
            ),
            tables_mapped=len(
                [k for k, v in report_data.context.items() if isinstance(v, list)]
            ),
            validation_errors=len(report_data.validation_errors),
        )

        return report_data

    def _build_immuno_tips(
        self, msi_status: Optional[str], tmb_status: Optional[str] = None
    ) -> Optional[str]:
        """生成终版风格的免疫治疗用药提示（固定科普段落，对齐人工终版报告）。"""
        return (
            "多项临床研究表明，TMB-H的肿瘤对免疫检查点抑制剂有更强的免疫应答效果\n"
            "常用免疫抑制剂有：#帕博利珠单抗、#纳武利尤单抗、#纳武利尤单抗+伊匹木单抗、阿替利珠单抗、"
            "度伐利尤单抗、特瑞普利单抗、信迪利单抗、卡瑞利珠单抗、#替雷利珠单抗、#恩沃利单抗、"
            "#多塔利单抗、#斯鲁利单抗、#普特利单抗、派安普利单抗、赛帕利单抗等"
        )

    def _map_single_values(
        self, excel_data: ExcelDataSource, report_data: ReportData
    ) -> None:
        """
        映射单值字段

        Args:
            excel_data: Excel数据源
            report_data: 报告数据
        """
        for var_name, mapping in self.single_value_mappings.items():
            # 在Excel数据中查找匹配的字段
            excel_value = None
            matched_column = None

            for excel_column, value in excel_data.single_values.items():
                if mapping.matches_column_name(excel_column):
                    excel_value = value
                    matched_column = excel_column
                    break

            # 如果找到匹配
            if excel_value is not None:
                formatted_value = mapping.format_value(excel_value)
                report_data.set_field(var_name, formatted_value)
                self.logger.debug(
                    "映射字段",
                    variable=var_name,
                    excel_column=matched_column,
                    value=formatted_value,
                )
            else:
                # ✅ 检查字段是否已经有值（比如从文件名提取的sample_id）
                existing_value = report_data.get_field(var_name)
                if existing_value is not None:
                    # 已经有值，不要覆盖
                    self.logger.debug(
                        "字段已有值，跳过映射",
                        variable=var_name,
                        existing_value=existing_value,
                    )
                    continue

                # 未找到匹配，使用默认值
                if mapping.required:
                    report_data.add_validation_error(
                        f"缺失必填字段: {var_name} ({mapping.synonyms})"
                    )
                    self.logger.warning(
                        "缺失必填字段", variable=var_name, synonyms=mapping.synonyms
                    )

                # 设置默认值
                report_data.set_field(var_name, mapping.default_value)

    def _map_tables(self, excel_data: ExcelDataSource, report_data: ReportData) -> None:
        """
        映射表格数据

        Args:
            excel_data: Excel数据源
            report_data: 报告数据
        """
        for table_name, table_mapping in self.table_mappings.items():
            # 2.1 专用九列表：由 Variations + CtDrug 聚合生成
            if table_name == "variants_2_1":
                rows = self._build_variants_2_1(excel_data, report_data)
                report_data.set_table(table_name, rows)
                self.logger.debug("映射表格(聚合)", table=table_name, rows=len(rows))
                continue
            # Special handling: build targeted_drug_tips by joining Variations
            # with CtDrug.
            if table_name == "targeted_drug_tips":
                rows = self._build_targeted_drug_tips(excel_data, report_data)
                report_data.set_table(table_name, rows)
                self.logger.debug("映射表格(聚合)", table=table_name, rows=len(rows))
                continue
            # 🔥 NEW: Special handling for drug detail tables (drug_顺铂, drug_卡铂, etc.)
            if table_name.startswith("drug_"):
                rows = self._build_drug_detail_table(
                    table_name, table_mapping, excel_data
                )
                report_data.set_table(table_name, rows)
                self.logger.debug("映射药物表格", table=table_name, rows=len(rows))
                continue
            # 查找对应的Excel表格
            excel_table_data = None

            # 首先尝试按sheet_name查找
            if table_mapping.sheet_name:
                excel_table_data = excel_data.get_table_data(table_mapping.sheet_name)

            # 如果没找到，尝试按table_name查找
            if not excel_table_data:
                for sheet_name in excel_data.sheet_names:
                    if table_name.lower() in sheet_name.lower():
                        excel_table_data = excel_data.get_table_data(sheet_name)
                        break

            # 映射表格行
            if excel_table_data:
                mapped_rows = []
                skipped_rows = 0
                filter_stats = {
                    "class_filtered": 0,
                    "low_freq": 0,
                    "not_significant": 0,
                    "invalid": 0,
                }

                for row in excel_table_data:
                    # ✅ 过滤无效数据行（带统计）
                    is_valid, filter_reason = self._validate_table_row_with_reason(
                        table_name, row
                    )
                    if not is_valid:
                        skipped_rows += 1
                        if filter_reason in filter_stats:
                            filter_stats[filter_reason] += 1
                        continue

                    mapped_row = table_mapping.map_row(row)
                    if mapped_row:  # 只添加非空行
                        # 跳过误读的表头行（值看起来像列名标识符）
                        _header_like = {
                            "gene1", "gene2", "chr1", "chr2", "pos1", "pos2",
                            "break1", "break2", "est_type", "#est_type",
                            "sv_type", "finalfreq", "gene", "chr", "start", "end",
                        }
                        _vals = {str(v).strip().lower() for v in mapped_row.values() if v}
                        if _vals and _vals <= _header_like:
                            continue  # 跳过表头误读行
                        # CtDrug表兼容：模板历史字段别名（药物适应情况/检测结果/用药提示）
                        if table_name == "chemotherapy":
                            self._apply_ctdrug_template_aliases(mapped_row)
                        # 注入小写别名：模板可能同时引用 Gene1 和 gene1
                        lowercase_aliases = {}
                        for k, v in mapped_row.items():
                            lk = k[0].lower() + k[1:] if k and k[0].isupper() else None
                            if lk and lk != k and lk not in mapped_row:
                                lowercase_aliases[lk] = v
                        if lowercase_aliases:
                            mapped_row.update(lowercase_aliases)
                        mapped_rows.append(mapped_row)

                report_data.set_table(table_name, mapped_rows)

                # INFO级别：输出过滤摘要（仅对variants表）
                if table_name == "variants" and skipped_rows > 0:
                    self.logger.info(
                        "变异数据过滤完成",
                        原始行数=len(excel_table_data),
                        保留行数=len(mapped_rows),
                        过滤总数=skipped_rows,
                        分级过滤=filter_stats.get("class_filtered", 0),
                        低频过滤=filter_stats.get("low_freq", 0),
                        非显著过滤=filter_stats.get("not_significant", 0),
                        无效数据=filter_stats.get("invalid", 0),
                    )

                self.logger.debug(
                    "映射表格",
                    table=table_name,
                    rows=len(mapped_rows),
                    skipped=skipped_rows,
                )
            else:
                # 表格不存在
                if table_mapping.required:
                    report_data.add_validation_error(
                        f"缺失必需表格: {table_name} (sheet: {table_mapping.sheet_name})"
                    )

                # 根据empty_behavior处理
                # 无论 show_placeholder 还是 hide_section，都写入空列表，
                # 确保模板契约校验（{% for row in xxx %}）不会误拦。
                # hide_section 的隐藏逻辑由模板中的 {% if xxx %} 条件控制。
                if table_mapping.empty_behavior in ("show_placeholder", "hide_section"):
                    report_data.set_table(table_name, [])
                elif table_mapping.empty_behavior == "error" and table_mapping.required:
                    report_data.add_validation_error(f"必需表格 {table_name} 为空")

    def _validate_table_row_with_reason(
        self, table_name: str, row: Dict[str, Any]
    ) -> tuple[bool, str]:
        """
        验证表格行是否有效，并返回过滤原因

        Args:
            table_name: 表格名称
            row: 行数据字典

        Returns:
            (是否有效, 过滤原因)

            原因:
              - class_filtered
              - low_freq
              - not_significant
              - invalid
              - ""
        """
        # 针对variants表的特殊验证规则（包含智能过滤）
        if table_name == "variants":
            var_filter_config = self.filtering_config.get("variations", {})

            # 检查是否启用过滤
            if not var_filter_config.get("enabled", True):
                # 只做基本验证
                gene_symbol = (
                    row.get("Gene_Symbol") or row.get("基因") or row.get("Gene")
                )
                variant = row.get("cHGVS") or row.get("变异")
                if pd.isna(gene_symbol) or gene_symbol is None:
                    return False, "invalid"
                if str(gene_symbol).strip() == "Gene":
                    return False, "invalid"
                if pd.isna(variant) or variant is None:
                    return False, "invalid"
                return True, ""

            # === 基本验证 ===
            basic_config = var_filter_config.get("basic_validation", {})

            if basic_config.get("require_gene", True):
                gene_cols = basic_config.get(
                    "gene_columns", ["Gene_Symbol", "基因", "Gene"]
                )
                gene_symbol = None
                for col in gene_cols:
                    gene_symbol = row.get(col)
                    if gene_symbol is not None:
                        break
                if pd.isna(gene_symbol) or gene_symbol is None:
                    return False, "invalid"
                if str(gene_symbol).strip() == "Gene":
                    return False, "invalid"

            if basic_config.get("require_variant", True):
                variant_cols = basic_config.get("variant_columns", ["cHGVS", "变异"])
                variant = None
                for col in variant_cols:
                    variant = row.get(col)
                    if variant is not None:
                        break
                if pd.isna(variant) or variant is None:
                    return False, "invalid"

            # === 分级过滤（若存在Ⅰ/Ⅱ/Ⅲ类列则优先） ===
            # 兼容两种格式：中文分级（Ⅰ类/Ⅱ类/Ⅲ类）或数字标记（1=在面板内/0=不在）
            class_filter_config = var_filter_config.get("class_filter", {})
            if class_filter_config.get("enabled", False):
                class_cols = class_filter_config.get("class_columns", ["ExistIn552"])
                allowed = {
                    str(x).strip()
                    for x in class_filter_config.get("allowed_classes", [])
                }
                cls_val = None
                for col in class_cols:
                    if col in row:
                        cls_val = row.get(col)
                        break
                if cls_val is not None and allowed:
                    cls_str = str(cls_val).strip()
                    # 数字格式兼容：1/True = 在面板内（通过过滤），0/False = 不在
                    if cls_str in ("1", "1.0", "True"):
                        pass  # 通过分级过滤
                    elif cls_str in ("0", "0.0", "False"):
                        return False, "class_filtered"
                    elif cls_str and cls_str not in allowed:
                        return False, "class_filtered"

            # === 智能过滤 ===
            is_high_freq = False
            freq_filter_config = var_filter_config.get("frequency_filter", {})
            if freq_filter_config.get("enabled", True):
                min_freq = freq_filter_config.get("min_frequency", 5.0)
                freq_cols = freq_filter_config.get(
                    "frequency_columns", ["Freq(%)", "AF"]
                )
                freq = None
                for col in freq_cols:
                    freq = row.get(col)
                    if freq is not None:
                        break
                if freq is not None and not pd.isna(freq):
                    try:
                        freq_value = float(freq)
                        is_high_freq = freq_value >= min_freq
                    except (ValueError, TypeError):
                        pass

            is_clinically_significant = False
            clin_filter_config = var_filter_config.get(
                "clinical_significance_filter", {}
            )
            if clin_filter_config.get("enabled", True):
                keywords = clin_filter_config.get(
                    "significant_keywords",
                    ["Missense", "Nonsense", "Frameshift", "Splice"],
                )
                func_cols = clin_filter_config.get(
                    "function_columns", ["Function", "功能", "Type"]
                )
                function = None
                for col in func_cols:
                    function = row.get(col)
                    if function is not None:
                        break
                if function is not None and not pd.isna(function):
                    function_str = str(function)
                    is_clinically_significant = any(
                        kw in function_str for kw in keywords
                    )

            # 保留高频或临床显著的变异
            if not is_high_freq and not is_clinically_significant:
                # 判断具体原因：如果有频率但低，是低频；否则是非显著
                if (
                    freq_filter_config.get("enabled", True)
                    and freq is not None
                    and not pd.isna(freq)
                ):
                    return False, "low_freq"
                return False, "not_significant"

            return True, ""

        # 其他表格使用原方法
        is_valid = self._is_valid_table_row(table_name, row)
        return is_valid, "" if is_valid else "invalid"

    def _is_valid_table_row(self, table_name: str, row: Dict[str, Any]) -> bool:
        """
        验证表格行是否有效

        Args:
            table_name: 表格名称
            row: 行数据字典

        Returns:
            是否为有效行
        """
        # 针对variants表的特殊验证规则（包含智能过滤）
        if table_name == "variants":
            # 🔥 使用配置中的过滤规则
            var_filter_config = self.filtering_config.get("variations", {})

            # 检查是否启用过滤
            if not var_filter_config.get("enabled", True):
                # 如果过滤未启用，只做基本验证
                gene_symbol = (
                    row.get("Gene_Symbol") or row.get("基因") or row.get("Gene")
                )
                variant = row.get("cHGVS") or row.get("变异")

                if pd.isna(gene_symbol) or gene_symbol is None:
                    return False
                if str(gene_symbol).strip() == "Gene":
                    return False
                if pd.isna(variant) or variant is None:
                    return False

                return True

            # === 基本验证配置 ===
            basic_config = var_filter_config.get("basic_validation", {})

            # 基因验证
            if basic_config.get("require_gene", True):
                gene_cols = basic_config.get(
                    "gene_columns", ["Gene_Symbol", "基因", "Gene"]
                )
                gene_symbol = None
                for col in gene_cols:
                    gene_symbol = row.get(col)
                    if gene_symbol is not None:
                        break

                if pd.isna(gene_symbol) or gene_symbol is None:
                    return False
                if str(gene_symbol).strip() == "Gene":
                    return False

            # 变异验证
            if basic_config.get("require_variant", True):
                variant_cols = basic_config.get("variant_columns", ["cHGVS", "变异"])
                variant = None
                for col in variant_cols:
                    variant = row.get(col)
                    if variant is not None:
                        break

                if pd.isna(variant) or variant is None:
                    return False

            # === 分级过滤（若存在Ⅰ/Ⅱ/Ⅲ类列则优先） ===
            # 兼容两种格式：中文分级（Ⅰ类/Ⅱ类/Ⅲ类）或数字标记（1=在面板内/0=不在）
            class_filter_config = var_filter_config.get("class_filter", {})
            if class_filter_config.get("enabled", False):
                class_cols = class_filter_config.get("class_columns", ["ExistIn552"])
                allowed = {
                    str(x).strip()
                    for x in class_filter_config.get("allowed_classes", [])
                }
                cls_val = None
                for col in class_cols:
                    if col in row:
                        cls_val = row.get(col)
                        break
                if cls_val is not None and allowed:
                    cls_str = str(cls_val).strip()
                    if cls_str in ("1", "1.0", "True"):
                        pass  # 通过分级过滤
                    elif cls_str in ("0", "0.0", "False"):
                        return False
                    elif cls_str and cls_str not in allowed:
                        return False

            # === 智能过滤 ===
            # 策略1: 频率过滤
            is_high_freq = False
            freq_filter_config = var_filter_config.get("frequency_filter", {})

            if freq_filter_config.get("enabled", True):
                min_freq = freq_filter_config.get("min_frequency", 5.0)
                freq_cols = freq_filter_config.get(
                    "frequency_columns", ["Freq(%)", "AF"]
                )

                freq = None
                for col in freq_cols:
                    freq = row.get(col)
                    if freq is not None:
                        break

                if freq is not None and not pd.isna(freq):
                    try:
                        freq_value = float(freq)
                        is_high_freq = freq_value >= min_freq
                    except (ValueError, TypeError):
                        pass

            # 策略2: 临床显著性过滤
            is_clinically_significant = False
            clin_filter_config = var_filter_config.get(
                "clinical_significance_filter", {}
            )

            if clin_filter_config.get("enabled", True):
                keywords = clin_filter_config.get(
                    "significant_keywords",
                    ["Missense", "Nonsense", "Frameshift", "Splice"],
                )
                func_cols = clin_filter_config.get(
                    "function_columns", ["Function", "功能", "Type"]
                )

                function = None
                for col in func_cols:
                    function = row.get(col)
                    if function is not None:
                        break

                if function is not None and not pd.isna(function):
                    function_str = str(function)
                    is_clinically_significant = any(
                        kw in function_str for kw in keywords
                    )

            # 保留高频或临床显著的变异（OR逻辑）
            if not (is_high_freq or is_clinically_significant):
                return False

            return True

        # 针对化疗药物表的验证规则
        elif table_name == "chemotherapy":
            drug_name = row.get("药物") or row.get("Drug")
            gene = row.get("检测基因") or row.get("Gene")

            # 药物名称和检测基因不能都为空
            if (pd.isna(drug_name) or drug_name is None) and (
                pd.isna(gene) or gene is None
            ):
                return False

            return True

        # 针对检测基因表的验证规则
        elif table_name == "genes":
            gene_name = row.get("Gene_Symbol") or row.get("基因") or row.get("Gene")

            # 基因名称不能为空
            if pd.isna(gene_name) or gene_name is None:
                return False

            # 不能是表头行
            if str(gene_name).strip() == "Gene":
                return False

            return True

        # 其他表格的默认验证：至少有一个字段非空
        non_null_count = sum(
            1 for value in row.values() if not pd.isna(value) and value is not None
        )
        return non_null_count > 0

    def get_mapping_for_variable(self, variable_name: str) -> Optional[FieldMapping]:
        """
        获取变量的映射配置

        Args:
            variable_name: 变量名

        Returns:
            FieldMapping或None
        """
        return self.single_value_mappings.get(variable_name)

    def get_table_mapping(self, table_name: str) -> Optional[TableMapping]:
        """
        获取表格的映射配置

        Args:
            table_name: 表格名

        Returns:
            TableMapping或None
        """
        return self.table_mappings.get(table_name)

    @staticmethod
    def _norm_text(v: Any) -> str:
        from reportgen.utils.text_utils import norm_text
        return norm_text(v)

    def _load_variants_2_1_baseline(self) -> list[dict[str, str]]:
        """加载九列表"未见突变"基线行（模板契约）。"""
        try:
            cfg_path = (
                Path(self.config_loader.config_dir) / "variant_table_baseline.yaml"
            )
        except Exception:
            return []
        if not cfg_path.exists():
            return []
        try:
            cfg = self.config_loader.load_yaml(str(cfg_path))
        except Exception as e:
            self.logger.warning(
                "读取variants_2_1基线配置失败", path=str(cfg_path), error=str(e)
            )
            return []

        rows = (cfg.get("variants_2_1", {}) or {}).get("unmutated_rows", [])
        if not isinstance(rows, list):
            return []
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            gene = str(r.get("gene") or "").strip()
            transcript = str(r.get("transcript") or "").strip()
            chr_ = str(r.get("chr") or "").strip()
            if not gene:
                continue
            out.append({"gene": gene, "transcript": transcript, "chr": chr_})
        return out

    def _build_tmb_summary(self, report_data: ReportData) -> Optional[str]:
        """生成终版风格的TMB展示字符串（含TMB-L/H与参考值提示）。"""
        tmb_val = report_data.get_field("tmb_value")
        if tmb_val is None:
            return None
        try:
            tmb = float(tmb_val)
        except Exception:
            return str(tmb_val)

        sample_type = str(report_data.get_field("sample_type") or "组织")
        threshold = (
            16 if ("血" in sample_type or "blood" in sample_type.lower()) else 10
        )
        level = "TMB-H" if tmb >= threshold else "TMB-L"
        direction = "高于" if tmb >= threshold else "低于"
        unit = str(report_data.get_field("tmb_unit") or "mutations/Mb")

        # 终版常见写法：数值+单位不加空格
        return (
            f"{tmb:.1f}{unit}，{level}\n"
            f"(本次检测结果{direction}参考值\n"
            f"{threshold} mutations/Mb)"
        )

    @staticmethod
    def _build_msi_summary(msi_status: Optional[str]) -> Optional[str]:
        if not msi_status:
            return None
        msi = str(msi_status).strip()
        up = msi.upper()
        if up == "MSS":
            return "微卫星稳定型，MSS"
        if up.startswith("MSI"):
            return f"微卫星不稳定型，{msi}"
        return msi

    @staticmethod
    def _build_msi_status_cn(msi_status: Optional[str]) -> Optional[str]:
        """生成MSI中文描述（与终版一致）。"""
        if not msi_status:
            return None
        msi = str(msi_status).strip()
        up = msi.upper()
        if up == "MSS":
            return "微卫星稳定型，MSS"
        if up == "MSI-H":
            return "微卫星高度不稳定，MSI-H"
        if up == "MSI-L":
            return "微卫星低度不稳定，MSI-L"
        return msi

    def _build_variants_2_1(
        self, excel_data: ExcelDataSource, report_data: ReportData
    ) -> list[dict]:
        """
        生成"2.1 基因变异检测结果及相关靶向药物信息"九列表数据。

        列：gene, transcript, chr, exon, locus, var_type_cn, af_pct,
            benefit_drugs, caution_drugs
        规则：
        - 取 Variations 的核心字段。
        - 仅展示分级为 Ⅰ/Ⅱ/Ⅲ 类的变异（ExistIn552），对齐终版报告"只展示Ⅰ/Ⅱ/Ⅲ类"。
        - exon 从 ExIn_ID 中提取数字（EX7/Exon7/EX16E -> 7/16）。
        - locus = cHGVS + ',\\n' + pHGVS_S（若p为*则仅cHGVS）。
        - var_type_cn 将 Function 翻译为中文标签。
        - 靶向药物提示：Ⅰ/Ⅱ类优先用自建数据库匹配（缺失则可用overrides），Ⅲ类固定为--。
        - 末尾补齐"未见突变"基线行（config/variant_table_baseline.yaml），用于对齐终版报告展示。
        """

        def exon_num(exid: Any) -> str:
            s = self._norm_text(exid)
            if not s:
                return ""
            m = re.search(r"(?i)(?:EX|EXON)(\d+)", s)
            return m.group(1) if m else s

        def chr_num(v: Any) -> str:
            s = self._norm_text(v)
            if not s:
                return ""
            return re.sub(r"(?i)^chr", "", s).strip()

        variations = excel_data.get_table_data("Variations") or []
        report_cancer_type = self._norm_text(report_data.get_field("cancer_type"))
        out: list[dict] = []
        mutated_genes: set[str] = set()

        for r in variations:
            level = self._norm_text(r.get("ExistIn552"))
            # 兼容数字格式：1=在面板内，映射为 Ⅲ类（具体分级由基因名判断）
            if level in ("1", "1.0"):
                # 按基因名判断分级（复用 CRC358 enhancer 的逻辑）
                from reportgen.core.template_bridge_358 import _get_gene_class
                gene_tmp = self._norm_text(
                    r.get("Gene_Symbol") or r.get("基因") or r.get("Gene")
                )
                level = _get_gene_class(gene_tmp, level) if gene_tmp else "Ⅲ类"
            elif level in ("0", "0.0"):
                continue  # 不在面板内
            if level not in {"Ⅰ类", "Ⅱ类", "Ⅲ类"}:
                continue

            gene = self._norm_text(
                r.get("Gene_Symbol") or r.get("基因") or r.get("Gene")
            )
            if not gene:
                continue

            # 终版报告只展示 CRC 重要基因（对齐人工终版 ~27 行）
            from reportgen.core.template_bridge_358 import CRC_IMPORTANT_GENES
            if gene.upper() not in CRC_IMPORTANT_GENES:
                continue

            c = self._norm_text(r.get("cHGVS"))
            # 必须是真正的 cHGVS（以 c. 开头），跳过知识库脏数据
            if not c or not c.startswith("c."):
                continue
            p = self._norm_text(r.get("pHGVS_S") or r.get("pHGVS_A"))
            locus = format_variant_site(c, p) or ""

            # Ⅲ类：终版报告不展示药物提示
            if level in {"Ⅰ类", "Ⅱ类"}:
                benefit, caution, _ = self._lookup_targeted_drugs_for_variant(
                    gene,
                    c_point=c,
                    p_point=p,
                    variant_level=level,
                    cancer_type=report_cancer_type,
                )
            else:
                benefit, caution = "--", "--"

            row = {
                "gene": gene,
                "transcript": self._norm_text(r.get("Transcript")),
                "chr": chr_num(r.get("Chr")),
                "exon": exon_num(r.get("ExIn_ID")),
                "locus": locus or "",
                # 批注：变异类型依据 c.HGVS 关键字 del/dup/ins/delins
                "var_type_cn": infer_variant_type_cn(c) or "点突变",
                "af_pct": self._norm_text(r.get("Freq(%)") or r.get("AF")),
                "benefit_drugs": benefit or "--",
                "caution_drugs": caution or "--",
            }
            out.append(row)
            mutated_genes.add(gene)

        # 补齐"未见突变"基线行（若配置存在）
        for base in self._load_variants_2_1_baseline():
            gene = self._norm_text(base.get("gene"))
            if not gene or gene in mutated_genes:
                continue
            out.append(
                {
                    "gene": gene,
                    "transcript": self._norm_text(base.get("transcript")),
                    "chr": self._norm_text(base.get("chr")),
                    "exon": "",
                    "locus": "未见突变",
                    "var_type_cn": "--",
                    "af_pct": "--",
                    "benefit_drugs": "--",
                    "caution_drugs": "--",
                }
            )

        return out

    def _apply_ctdrug_template_aliases(self, row: Dict[str, Any]) -> None:
        """为CtDrug来源的行补齐模板历史别名字段。

        aligned_template_with_cnv_fusion_hla_FIXED.docx 中存在历史字段引用：
        - 化疗表：row.药物适应情况 / row.检测结果
        - 药物明细表：row.用药提示 / row.检测结果

        但真实CtDrug列更常见的是：用药提示（仅供参考）/ 用药详细描述。
        这里统一做一次别名补齐，避免模板渲染为空。
        """
        # 1) 提取"提示"文本（优先用短提示，其次用长描述）
        tip = self._norm_text(row.get("用药提示（仅供参考）"))
        if not tip:
            tip = self._norm_text(row.get("用药提示"))
        if not tip:
            tip = self._norm_text(row.get("Recommendation"))
        if not tip:
            tip = self._norm_text(row.get("用药详细描述"))

        if not tip:
            return

        # 2) 标准化字段（映射配置里的recommendation/result）缺失时补齐
        if self._norm_text(row.get("recommendation")) == "":
            row["recommendation"] = tip
        if self._norm_text(row.get("result")) == "":
            row["result"] = tip

        # 3) 模板历史别名字段：仅在不存在时补齐，避免覆盖外部显式输入
        row.setdefault("药物适应情况", tip)
        row.setdefault("检测结果", tip)
        row.setdefault("用药提示", tip)

    def _build_drug_detail_table(
        self, table_name: str, table_mapping: TableMapping, excel_data: ExcelDataSource
    ) -> list[dict]:
        """
        生成单个药物详细解析表数据

        Args:
            table_name: 表格名称 (e.g., "drug_顺铂")
            table_mapping: 表格映射配置
            excel_data: Excel数据源

        Returns:
            过滤后的药物数据行列表
        """
        # 获取CtDrug数据
        ctdrug_data = excel_data.get_table_data("CtDrug") or []

        # 获取过滤配置
        filter_config = getattr(table_mapping, "filter", None)
        if not filter_config:
            self.logger.warning(f"药物表格 {table_name} 缺少filter配置")
            return []

        filter_column = filter_config.get("column", "药物")
        filter_values = filter_config.get("values", [])

        if not filter_values:
            self.logger.warning(f"药物表格 {table_name} 的filter.values为空")
            return []

        # 过滤数据：只保留匹配指定药物的行
        filtered_rows = []
        for row in ctdrug_data:
            drug_name = row.get(filter_column) or row.get("药物") or row.get("Drug")
            if drug_name and str(drug_name).strip() in filter_values:
                # 映射行数据（保留原始列名）
                mapped_row = table_mapping.map_row(row)
                if mapped_row:
                    self._apply_ctdrug_template_aliases(mapped_row)
                    filtered_rows.append(mapped_row)

        self.logger.debug(
            "药物表格过滤完成",
            table=table_name,
            filter_values=filter_values,
            total_ctdrug=len(ctdrug_data),
            filtered=len(filtered_rows),
        )

        return filtered_rows
