"""
Excel读取器

负责读取Excel文件并提取数据。
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from reportgen.config.loader import ConfigLoader
from reportgen.models.excel_data import ExcelDataSource
from reportgen.utils.logger import get_logger
from reportgen.utils.validators import validate_excel_file


class ExcelReader:
    """
    Excel读取器

    使用pandas读取Excel文件，提取单值字段和表格数据。
    """

    def __init__(
        self,
        config_dir: str = "config",
        log_file: Optional[str] = None,
        log_level: str = "INFO",
    ):
        """
        初始化Excel读取器

        Args:
            config_dir: 配置目录路径（用于加载skip_rows等配置）
            log_file: 日志文件路径
            log_level: 日志级别
        """
        self.logger = get_logger(log_file=log_file, level=log_level)
        self.config_dir = config_dir
        self.config_loader = ConfigLoader(
            config_dir=config_dir, log_file=log_file, log_level=log_level
        )

        self.mapping_config = self.config_loader.load_mapping_config()
        self.skip_rows_config = self._load_skip_rows_config()

        # settings.yaml 可选：控制是否关闭dtype推断（全部读为字符串，避免ID前导0丢失）
        self.dtype_inference = bool(
            self.config_loader.get_setting("data.excel.dtype_inference", True)
        )
        self.keep_default_na = bool(
            self.config_loader.get_setting("data.excel.keep_default_na", True)
        )
        self.na_values = self.config_loader.get_setting("data.excel.na_values", None)

        # MSI 状态推断阈值（从 settings.yaml 加载，支持临床方案调整）
        self._msi_h_threshold = float(
            self.config_loader.get_setting("data.msi.thresholds.msi_h", 40)
        )
        self._msi_l_threshold = float(
            self.config_loader.get_setting("data.msi.thresholds.msi_l", 20)
        )

        # 只读取mapping中声明的sheet（若存在未声明sheet_name的表格，则回退读取全部）
        self._table_sheet_names, self._need_all_sheets = self._collect_needed_sheets()

    def _collect_needed_sheets(self) -> tuple[set[str], bool]:
        table_data = (
            self.mapping_config.get("table_data", {}) if self.mapping_config else {}
        )
        sheet_names: set[str] = set()
        need_all = False

        for _, table_config in table_data.items():
            sheet_name = table_config.get("sheet_name")
            if sheet_name:
                sheet_names.add(str(sheet_name))
            else:
                need_all = True

        return sheet_names, need_all

    def _parse_sheet(
        self,
        excel_file: pd.ExcelFile,
        sheet_name: str,
        sheet_cache: Dict[tuple, pd.DataFrame],
        *,
        skip_rows: int = 0,
        header: Optional[int] = 0,
    ) -> pd.DataFrame:
        cache_key = (sheet_name, skip_rows, header)
        if cache_key in sheet_cache:
            return sheet_cache[cache_key]

        parse_kwargs: Dict[str, Any] = {"sheet_name": sheet_name, "header": header}
        if skip_rows:
            parse_kwargs["skiprows"] = skip_rows

        if not self.dtype_inference:
            parse_kwargs["dtype"] = str
        if self.na_values is not None:
            parse_kwargs["na_values"] = self.na_values
        parse_kwargs["keep_default_na"] = self.keep_default_na

        try:
            df = excel_file.parse(**parse_kwargs)
        except TypeError:
            # 兼容不同pandas版本：逐步移除可选参数
            parse_kwargs.pop("dtype", None)
            try:
                df = excel_file.parse(**parse_kwargs)
            except TypeError:
                parse_kwargs.pop("na_values", None)
                parse_kwargs.pop("keep_default_na", None)
                df = excel_file.parse(**parse_kwargs)

        sheet_cache[cache_key] = df
        return df

    def _get_df_cell_value(self, df: pd.DataFrame, row: int, col: int) -> Optional[Any]:
        if df is None or df.empty:
            return None
        if row >= df.shape[0] or col >= df.shape[1]:
            return None
        value = df.iloc[row, col]
        if pd.isna(value):
            return None
        return value

    def _extract_tmb_value(self, df: pd.DataFrame) -> Optional[float]:
        """从TMB sheet中尽量提取与报告一致的TMB值。

        真实业务Excel里常见多个TMB计算块（all cosmic / de cosmic50 / TCGA fit 等）。
        本项目终版报告通常使用“TCGA fit”块的TMB（更接近6.x这类值）。
        """
        if df is None or df.empty:
            return None

        # 将整张表按“行”扫描，尽量容错各种空行/不同header布局
        values = df.to_numpy()

        def is_empty_row(row) -> bool:
            for v in row:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    continue
                if str(v).strip() != "":
                    return False
            return True

        def row_has_token(row, token: str) -> bool:
            t = token.lower()
            for v in row:
                if isinstance(v, str) and t in v.lower():
                    return True
            return False

        def try_float(v) -> Optional[float]:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            try:
                return float(v)
            except Exception:
                return None

        # 1) 优先：定位“TCGA fit”块，读取其数据行的 TMB 列
        tcga_row = None
        for i, row in enumerate(values):
            if row_has_token(row, "TCGA") and row_has_token(row, "fit"):
                tcga_row = i
                break

        if tcga_row is not None:
            # 找到header行（包含 TMB 字样）
            header_idx = None
            for i in range(tcga_row + 1, min(tcga_row + 10, len(values))):
                if is_empty_row(values[i]):
                    continue
                if row_has_token(values[i], "TMB"):
                    header_idx = i
                    break

            if header_idx is not None:
                header = [
                    str(x).strip() if x is not None else "" for x in values[header_idx]
                ]
                tmb_col = next(
                    (j for j, h in enumerate(header) if h.upper() == "TMB"), None
                )
                sampletp_col = next(
                    (j for j, h in enumerate(header) if h.lower() == "sampletp"), None
                )

                candidates: list[tuple[int, float, str]] = []
                for i in range(header_idx + 1, len(values)):
                    if is_empty_row(values[i]):
                        break
                    # 新块标题（通常只有第1列非空）
                    if (
                        isinstance(values[i][0], str)
                        and values[i][0].strip()
                        and try_float(values[i][0]) is None
                    ):
                        if (
                            sum(
                                1
                                for v in values[i]
                                if v is not None
                                and not (isinstance(v, float) and pd.isna(v))
                                and str(v).strip()
                            )
                            == 1
                        ):
                            break

                    if tmb_col is None or tmb_col >= len(values[i]):
                        continue
                    tmb_val = try_float(values[i][tmb_col])
                    if tmb_val is None:
                        continue

                    sampletp = ""
                    if sampletp_col is not None and sampletp_col < len(values[i]):
                        sampletp = str(values[i][sampletp_col] or "").strip().lower()
                    candidates.append((i, tmb_val, sampletp))

                if candidates:
                    # 默认优先 tissue，其次取第一个
                    candidates.sort(key=lambda x: (0 if x[2] == "tissue" else 1, x[0]))
                    return float(candidates[0][1])

        # 2) 回退：若只有一个明显的TMB数值块（Var_num/Bed_size/TMB），取其首个数值
        for i in range(len(values)):
            if row_has_token(values[i], "Var_num") and row_has_token(values[i], "TMB"):
                # 下一行一般是数值行：[..., ..., <TMB>]
                for j in range(i + 1, min(i + 5, len(values))):
                    if is_empty_row(values[j]):
                        continue
                    # 取该行最后一个可转float的值作为TMB
                    row_len = values[j].shape[0] if hasattr(values[j], 'shape') and values[j].ndim > 0 else 1
                    for k in range(row_len - 1, -1, -1):
                        v = try_float(values[j][k])
                        if v is not None:
                            return float(v)

        return None

    def _load_skip_rows_config(self) -> Dict[str, int]:
        """
        从mapping配置中加载skip_rows设置

        Returns:
            字典 {sheet_name: skip_rows数量}
        """
        skip_rows_map = {}

        try:
            # 遍历table_data配置，提取skip_rows设置
            table_data = (
                self.mapping_config.get("table_data", {}) if self.mapping_config else {}
            )
            for table_name, table_config in table_data.items():
                sheet_name = table_config.get("sheet_name")
                skip_rows = table_config.get("skip_rows")

                if sheet_name and skip_rows is not None:
                    skip_rows_map[str(sheet_name)] = int(skip_rows)
                    self.logger.debug(
                        "加载skip_rows配置", sheet=sheet_name, skip_rows=skip_rows
                    )

            self.logger.info("skip_rows配置加载完成", count=len(skip_rows_map))

        except Exception as e:
            self.logger.warning("加载skip_rows配置失败", error=str(e))

        return skip_rows_map

    def read(self, file_path: str, include_tables: bool = True) -> ExcelDataSource:
        """
        读取Excel文件

        Args:
            file_path: Excel文件路径

        Returns:
            ExcelDataSource对象

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式错误
        """
        # 验证文件
        is_valid, error = validate_excel_file(file_path)
        if not is_valid:
            self.logger.error("Excel文件验证失败", file=file_path, error=error)
            raise ValueError(error)

        self.logger.info("开始读取Excel文件", file=file_path)

        excel_file = None
        try:
            # 读取所有sheets（仅打开一次，后续复用parse）
            excel_file = pd.ExcelFile(file_path, engine="openpyxl")
            sheet_names = excel_file.sheet_names
            sheet_cache: Dict[tuple, pd.DataFrame] = {}

            # 从文件名提取样本编号
            sample_id = self._extract_sample_id_from_filename(file_path)

            self.logger.debug(
                "Excel文件信息",
                file=file_path,
                sheets=sheet_names,
                sheet_count=len(sheet_names),
                sample_id=sample_id,
            )

            # 创建数据源对象
            data_source = ExcelDataSource(
                file_path=file_path,
                sheet_names=sheet_names,
                metadata={
                    "file_size": Path(file_path).stat().st_size,
                    "sheet_count": len(sheet_names),
                    "sample_id_from_filename": sample_id,  # ✅ 添加样本编号
                },
            )

            # 读取第一个sheet作为主数据源
            if sheet_names:
                main_df = self._parse_sheet(
                    excel_file, sheet_names[0], sheet_cache, skip_rows=0, header=0
                )
                self._extract_single_values(main_df, data_source)

            # 优先解析Meta/BasicInfo/基本信息表，覆盖/补充单值字段
            for meta_sheet in ("Meta", "BasicInfo", "基本信息"):
                if meta_sheet in sheet_names:
                    try:
                        meta_df = self._parse_sheet(
                            excel_file, meta_sheet, sheet_cache, skip_rows=0, header=0
                        )
                        self._extract_meta_values(meta_sheet, meta_df, data_source)
                    except Exception as e:
                        self.logger.warning(
                            "读取Meta信息失败", sheet=meta_sheet, error=str(e)
                        )

            # ✅ 提取TMB值（如果TMB sheet存在）
            if "TMB" in sheet_names:
                # 以 header=None 读取整表，便于在多个“块”里定位正确的TMB来源
                tmb_df = self._parse_sheet(
                    excel_file, "TMB", sheet_cache, skip_rows=0, header=None
                )
                tmb_value = self._extract_tmb_value(tmb_df)
                if tmb_value is not None:
                    data_source.single_values["TMB"] = tmb_value
                    self.logger.info("提取TMB值成功", tmb_value=tmb_value)

            # ✅ 提取MSI状态（如果Msisensor sheet存在）
            if "Msisensor" in sheet_names:
                msi_df = self._parse_sheet(
                    excel_file, "Msisensor", sheet_cache, skip_rows=0, header=0
                )
                msi_status = self._get_df_cell_value(msi_df, row=1, col=4)
                if msi_status is not None:
                    data_source.single_values["MSI状态"] = msi_status
                    self.logger.info("提取MSI状态成功", msi_status=msi_status)
                else:
                    # 如果第5列没有状态，尝试从百分比判定
                    msi_percentage = self._get_df_cell_value(msi_df, row=1, col=3)
                    if msi_percentage is not None:
                        try:
                            pct = float(msi_percentage)
                            # 阈值由 settings.yaml data.msi.thresholds 配置
                            if pct >= self._msi_h_threshold:
                                status = "MSI-H"
                            elif pct >= self._msi_l_threshold:
                                status = "MSI-L"
                            else:
                                status = "MSS"
                            data_source.single_values["MSI状态"] = status
                            self.logger.info(
                                "根据百分比判定MSI状态", percentage=pct, status=status
                            )
                        except (ValueError, TypeError):
                            self.logger.warning(
                                "无法解析MSI百分比", value=msi_percentage
                            )

            # ---- 提取 QC 指标 (Q30, 覆盖度, 平均深度等) ----
            # QC sheet 是双 block 布局：
            #   Block 1 (col 0-2): metric_name | case_value | control_value
            #   Block 2 (col 11-12): Quality | Value (Q30/MappingRate/insert 等摘要)
            if "QC" in sheet_names:
                try:
                    qc_df = self._parse_sheet(
                        excel_file, "QC", sheet_cache, skip_rows=0, header=None
                    )
                    if qc_df is not None and len(qc_df) > 0:
                        def _match_metric(metric: str, value):
                            """匹配常见 QC 指标名并写入 single_values。"""
                            if value is None or (isinstance(value, float) and value != value):
                                return

                            # Strip trailing % from string values so float parsing works
                            def _num(v):
                                s = str(v).strip().rstrip('%').rstrip('X').rstrip('x')
                                try:
                                    return float(s)
                                except (ValueError, TypeError):
                                    return v  # keep original if can't parse

                            m_lower = metric.lower()
                            # Q30
                            if m_lower == "q30" or "q30" in m_lower:
                                data_source.single_values["Q30"] = _num(value)
                                self.logger.info("提取Q30成功", value=str(value)[:30])
                            # 覆盖度 / Coverage (only real "coverage", not mapping rate)
                            elif "coverage" in m_lower or "覆盖" in metric:
                                data_source.single_values["覆盖度"] = _num(value)
                                self.logger.info("提取覆盖度成功", value=str(value)[:30])
                            # 平均深度 / Average depth
                            elif (("average" in m_lower and "depth" in m_lower)
                                  or "平均深度" in metric
                                  or "average sequencing depth" in m_lower):
                                data_source.single_values["平均深度"] = _num(value)
                                self.logger.info("提取平均深度成功", value=str(value)[:30])
                            # 插入片段
                            elif m_lower == "insert" or "insert size" in m_lower:
                                data_source.single_values["插入片段"] = value

                        n_cols = qc_df.shape[1]
                        for _, row in qc_df.iterrows():
                            # Block 1: col 0 metric → col 1 value
                            metric_b1 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
                            val_b1 = row.iloc[1] if n_cols > 1 and pd.notna(row.iloc[1]) else None
                            if metric_b1 and val_b1 is not None:
                                _match_metric(metric_b1, val_b1)

                            # Block 2: col 11 metric → col 12 value (Quality/Value)
                            if n_cols > 12:
                                metric_b2 = str(row.iloc[11]).strip() if pd.notna(row.iloc[11]) else ""
                                val_b2 = row.iloc[12] if pd.notna(row.iloc[12]) else None
                                if metric_b2 and val_b2 is not None and metric_b2.lower() not in ("quality", "value"):
                                    _match_metric(metric_b2, val_b2)
                except Exception as e:
                    self.logger.warning("QC指标提取失败", error=str(e))

            if not include_tables:
                self.logger.info(
                    "Excel单值字段读取完成（未读取表格数据）",
                    file=file_path,
                    single_values=len(data_source.single_values),
                )
                return data_source

            # 读取所有sheets作为潜在的表格数据
            if self._need_all_sheets:
                sheets_to_read = sheet_names
            else:
                sheets_to_read = [
                    s for s in sheet_names if s in self._table_sheet_names or s == "HLA"
                ]

            for sheet_name in sheets_to_read:
                # 特殊处理HLA sheet（使用专用解析器）
                if sheet_name == "HLA":
                    df_raw = self._parse_sheet(
                        excel_file, "HLA", sheet_cache, skip_rows=0, header=None
                    )
                    self._extract_hla_data(file_path, data_source, df_raw=df_raw)
                    continue

                # 检查是否需要跳过行
                skip_rows = self.skip_rows_config.get(sheet_name, 0)
                if skip_rows > 0:
                    df = self._parse_sheet(
                        excel_file,
                        sheet_name,
                        sheet_cache,
                        skip_rows=skip_rows,
                        header=0,
                    )
                    self.logger.debug(
                        "读取Sheet（跳过行）",
                        sheet=sheet_name,
                        skip_rows=skip_rows,
                        rows=len(df),
                    )
                else:
                    df = self._parse_sheet(
                        excel_file, sheet_name, sheet_cache, skip_rows=0, header=0
                    )
                self._extract_table_data(sheet_name, df, data_source)

            self.logger.info(
                "Excel文件读取成功",
                file=file_path,
                single_values=len(data_source.single_values),
                tables=len(data_source.table_data),
            )

            return data_source

        except Exception as e:
            self.logger.error("Excel文件读取失败", file=file_path, error=str(e))
            raise ValueError(f"无法读取Excel文件: {e}")
        finally:
            if excel_file is not None:
                excel_file.close()

    def _extract_meta_values(
        self, sheet_name: str, df: pd.DataFrame, data_source: ExcelDataSource
    ) -> None:
        """
        从 Meta/BasicInfo/基本信息 sheet 提取单值字段。

        支持三种常见格式：
        1) 首行即字段列，只有1行数据（横向展开）
        2) 两列表头为 Key/Value（或 字段/值），多行纵向排列
        3) 两列但无明确表头，默认第一列为字段，第二列为值
        """
        if df is None or df.empty:
            return

        # 情况1：只有1行，按横向字段解析
        if len(df) == 1:
            row = df.iloc[0]
            for column_name, value in row.items():
                if pd.isna(value):
                    continue
                data_source.add_single_value(
                    str(column_name), self._convert_to_python_type(value)
                )
            self.logger.info(
                "从Meta表(横向)提取单值字段", sheet=sheet_name, count=len(df.columns)
            )
            return

        # 统一列名小写去空格，便于识别
        cols = [str(c).strip().lower() for c in df.columns]

        def col_index(names):
            for n in names:
                if n in cols:
                    return cols.index(n)
            return None

        key_idx = col_index(["key", "field", "name", "变量", "字段", "项目", "名称"])
        val_idx = col_index(["value", "值", "数据", "content", "内容"])

        # 情况2：存在Key/Value风格表头
        if key_idx is not None and val_idx is not None and key_idx != val_idx:
            cnt = 0
            for _, r in df.iterrows():
                k = r.iloc[key_idx]
                v = r.iloc[val_idx]
                if pd.isna(k) or (isinstance(k, str) and not k.strip()):
                    continue
                data_source.add_single_value(
                    str(k).strip(), self._convert_to_python_type(v)
                )
                cnt += 1
            self.logger.info(
                "从Meta表(Key/Value)提取单值字段", sheet=sheet_name, count=cnt
            )
            return

        # 情况3：两列但无表头，按第一列为key，第二列为value处理
        if df.shape[1] == 2:
            cnt = 0
            for _, r in df.iterrows():
                k = r.iloc[0]
                v = r.iloc[1]
                if pd.isna(k) or (isinstance(k, str) and not k.strip()):
                    continue
                data_source.add_single_value(
                    str(k).strip(), self._convert_to_python_type(v)
                )
                cnt += 1
            self.logger.info(
                "从Meta表(两列无表头)提取单值字段", sheet=sheet_name, count=cnt
            )
            return

    def _extract_single_values(
        self, df: pd.DataFrame, data_source: ExcelDataSource
    ) -> None:
        """
        从DataFrame提取单值字段（第一行数据）

        Args:
            df: DataFrame
            data_source: 数据源对象
        """
        if df.empty:
            return

        # 提取第一行作为单值字段
        first_row = df.iloc[0]

        for column_name, value in first_row.items():
            # 跳过NaN值
            if pd.isna(value):
                continue

            # 转换为Python原生类型
            python_value = self._convert_to_python_type(value)
            data_source.add_single_value(str(column_name), python_value)

        self.logger.debug(
            "提取单值字段", count=len([v for v in first_row if not pd.isna(v)])
        )

    def _extract_hla_data(
        self,
        file_path: str,
        data_source: ExcelDataSource,
        *,
        df_raw: Optional[pd.DataFrame] = None,
    ) -> None:
        """
        使用专用解析器提取HLA数据

        HLA数据格式特殊，每个位点（A/B/C）占据独立section：
        Row N: HLA-A, HET
        Row N+1: (空行)
        Row N+2: [Type 1], allele1, EX3_xxx_xxx, EX2_xxx_xxx, EX4_xxx_xxx, EX5_xxx_xxx
        Row N+3: [Type 2], allele2, EX3_xxx_xxx, EX2_xxx_xxx, EX4_xxx_xxx, EX5_xxx_xxx

        质量控制数据格式: EXN_coverage_percentage

        Args:
            file_path: Excel文件路径
            data_source: 数据源对象
        """

        def _parse_exon_qc(qc_str: str) -> dict:
            """
            解析exon质量控制字符串

            Args:
                qc_str: 如 "EX3_132.091_100"

            Returns:
                {"exon": "EX3", "coverage": 132.091, "percentage": 100}
            """
            if not qc_str or qc_str == "nan":
                return None

            try:
                parts = str(qc_str).split("_")
                if len(parts) >= 3:
                    return {
                        "exon": parts[0],
                        "coverage": float(parts[1]),
                        "percentage": float(parts[2]),
                    }
            except (ValueError, IndexError):
                pass

            return None

        try:
            # 读取原始数据（不指定header）
            if df_raw is None:
                df_raw = pd.read_excel(
                    file_path, sheet_name="HLA", header=None, engine="openpyxl"
                )

            if df_raw.empty:
                self.logger.debug("HLA sheet为空")
                return

            hla_data = []
            current_locus = None
            current_item = None
            type1_qc = None
            type2_qc = None

            for i in range(len(df_raw)):
                first_col = (
                    str(df_raw.iloc[i, 0]) if pd.notna(df_raw.iloc[i, 0]) else ""
                )
                second_col = (
                    str(df_raw.iloc[i, 1]) if pd.notna(df_raw.iloc[i, 1]) else ""
                )

                # 检测HLA位点开始
                if first_col.startswith("HLA-"):
                    # 保存前一个位点（如果有）
                    if current_item:
                        # 🔥 NEW: 添加QC数据
                        if type1_qc or type2_qc:
                            current_item["QC"] = {"Type1": type1_qc, "Type2": type2_qc}
                        hla_data.append(current_item)

                    # 开始新位点
                    current_locus = first_col
                    current_item = {
                        "Locus": current_locus,
                        "Zygosity": second_col if second_col != "nan" else None,
                    }
                    type1_qc = None
                    type2_qc = None
                    self.logger.debug(
                        "发现HLA位点", locus=current_locus, zygosity=second_col
                    )

                # 检测Type 1
                elif "[Type 1]" in first_col:
                    if current_item:
                        current_item["Type1"] = (
                            second_col if second_col != "nan" else None
                        )

                        # 🔥 NEW: 提取Type 1的QC数据（列2-5）
                        type1_qc = {}
                        for col_idx in range(2, min(6, len(df_raw.columns))):
                            qc_str = (
                                str(df_raw.iloc[i, col_idx])
                                if pd.notna(df_raw.iloc[i, col_idx])
                                else ""
                            )
                            qc_data = _parse_exon_qc(qc_str)
                            if qc_data:
                                type1_qc[qc_data["exon"]] = {
                                    "coverage": qc_data["coverage"],
                                    "percentage": qc_data["percentage"],
                                }

                        self.logger.debug(
                            "发现Type 1",
                            locus=current_locus,
                            allele=second_col,
                            qc_exons=list(type1_qc.keys()),
                        )

                # 检测Type 2
                elif "[Type 2]" in first_col:
                    if current_item:
                        current_item["Type2"] = (
                            second_col if second_col != "nan" else None
                        )

                        # 🔥 NEW: 提取Type 2的QC数据（列2-5）
                        type2_qc = {}
                        for col_idx in range(2, min(6, len(df_raw.columns))):
                            qc_str = (
                                str(df_raw.iloc[i, col_idx])
                                if pd.notna(df_raw.iloc[i, col_idx])
                                else ""
                            )
                            qc_data = _parse_exon_qc(qc_str)
                            if qc_data:
                                type2_qc[qc_data["exon"]] = {
                                    "coverage": qc_data["coverage"],
                                    "percentage": qc_data["percentage"],
                                }

                        self.logger.debug(
                            "发现Type 2",
                            locus=current_locus,
                            allele=second_col,
                            qc_exons=list(type2_qc.keys()),
                        )

            # 保存最后一个位点
            if current_item:
                # 🔥 NEW: 添加QC数据
                if type1_qc or type2_qc:
                    current_item["QC"] = {"Type1": type1_qc, "Type2": type2_qc}
                hla_data.append(current_item)

            if hla_data:
                data_source.table_data["HLA"] = hla_data
                self.logger.info(
                    "HLA数据提取成功（专用解析器）",
                    loci=len(hla_data),
                    positions=[item["Locus"] for item in hla_data],
                )
            else:
                self.logger.warning("HLA sheet未解析到任何数据")

        except Exception as e:
            self.logger.error("HLA数据提取失败", error=str(e))

    def _extract_table_data(
        self, sheet_name: str, df: pd.DataFrame, data_source: ExcelDataSource
    ) -> None:
        """
        从DataFrame提取表格数据

        Args:
            sheet_name: Sheet名称
            df: DataFrame
            data_source: 数据源对象
        """
        if df.empty:
            return

        # 跳过只有一行的表格（可能是单值数据），
        # 但如果该 sheet 在 mapping 中有明确的 table_data 定义，则不跳过
        if len(df) <= 1 and sheet_name not in self._table_sheet_names:
            return

        # 将DataFrame转换为行字典列表
        rows = []
        for _, row in df.iterrows():
            row_dict = {}
            has_data = False

            for column_name, value in row.items():
                # 跳过NaN值
                if pd.isna(value):
                    continue

                has_data = True
                python_value = self._convert_to_python_type(value)
                row_dict[str(column_name)] = python_value

            # 只添加包含数据的行
            if has_data:
                rows.append(row_dict)

        if rows:
            data_source.table_data[sheet_name] = rows
            self.logger.debug("提取表格数据", sheet=sheet_name, rows=len(rows))

    def _convert_to_python_type(self, value: Any) -> Any:
        """
        将pandas类型转换为Python原生类型

        Args:
            value: pandas值

        Returns:
            Python原生类型值
        """
        # NaN转为None
        if pd.isna(value):
            return None

        # 字符串形式的NaN/None
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "":
                return None
            if stripped.lower() in {"nan", "none", "null"}:
                return None

        # Timestamp转为字符串
        if isinstance(value, pd.Timestamp):
            return value.strftime("%Y-%m-%d")

        # numpy类型转为Python类型
        if hasattr(value, "item"):
            return value.item()

        return value

    def get_cell_value(
        self, file_path: str, sheet_name: str, row: int, col: int
    ) -> Optional[Any]:
        """
        从Excel中读取指定单元格的值

        Args:
            file_path: Excel文件路径
            sheet_name: Sheet名称
            row: 行号（从0开始）
            col: 列号（从0开始）

        Returns:
            单元格的值，如果读取失败返回None
        """
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")

            if row >= df.shape[0] or col >= df.shape[1]:
                self.logger.warning(
                    "单元格位置超出范围",
                    sheet=sheet_name,
                    row=row,
                    col=col,
                    shape=df.shape,
                )
                return None

            value = df.iloc[row, col]

            # 处理NaN值
            if pd.isna(value):
                return None

            self.logger.debug(
                "读取单元格成功",
                sheet=sheet_name,
                row=row,
                col=col,
                value=value,
            )

            return value

        except Exception as e:
            self.logger.error(
                "读取单元格失败",
                sheet=sheet_name,
                row=row,
                col=col,
                error=str(e),
            )
            return None

    def read_sheet(self, file_path: str, sheet_name: str) -> pd.DataFrame:
        """
        读取指定sheet（会自动应用skip_rows配置）

        Args:
            file_path: Excel文件路径
            sheet_name: Sheet名称

        Returns:
            DataFrame

        Raises:
            ValueError: Sheet不存在
        """
        try:
            # 检查是否需要跳过行
            skip_rows = self.skip_rows_config.get(sheet_name, 0)
            if skip_rows > 0:
                df = pd.read_excel(
                    file_path,
                    sheet_name=sheet_name,
                    engine="openpyxl",
                    skiprows=skip_rows,
                )
                self.logger.debug(
                    "读取Sheet（跳过行）",
                    file=file_path,
                    sheet=sheet_name,
                    skip_rows=skip_rows,
                    rows=len(df),
                )
            else:
                df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
                self.logger.debug(
                    "读取Sheet", file=file_path, sheet=sheet_name, rows=len(df)
                )
            return df
        except Exception as e:
            self.logger.error(
                "读取Sheet失败", file=file_path, sheet=sheet_name, error=str(e)
            )
            raise ValueError(f"无法读取Sheet '{sheet_name}': {e}")

    def get_sheet_names(self, file_path: str) -> List[str]:
        """
        获取Excel文件的所有sheet名称

        Args:
            file_path: Excel文件路径

        Returns:
            Sheet名称列表
        """
        try:
            excel_file = pd.ExcelFile(file_path, engine="openpyxl")
            return excel_file.sheet_names
        except Exception as e:
            self.logger.error("获取Sheet名称失败", file=file_path, error=str(e))
            return []

    def _extract_sample_id_from_filename(self, file_path: str) -> Optional[str]:
        """
        从文件名提取样本编号

        支持的格式:
        - MLF2509307001T_MLB2509307001.result.xlsx -> MLB2509307001
        - SAMPLE123_TEST.xlsx -> SAMPLE123

        Args:
            file_path: Excel文件路径

        Returns:
            样本编号，如果无法提取返回None
        """
        import re

        # 获取文件名（不含路径和扩展名）
        filename = Path(file_path).stem

        # 移除常见后缀
        filename = filename.replace(".result", "").replace(".final", "")

        # 尝试提取样本编号的几种常见模式
        patterns = [
            r"MLB\d+",  # MLB开头的编号
            r"MLF\d+[A-Z]?",  # MLF开头的编号
            r"MLJY-LZ\d+",  # MLJY-LZ格式
            r"[A-Z]{2,}\d{6,}",  # 通用模式：2+字母+6+数字
        ]

        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                sample_id = match.group(0)
                self.logger.debug(
                    "从文件名提取样本编号", filename=filename, sample_id=sample_id
                )
                return sample_id

        # 不再使用宽泛的"首段长度>=6"兜底，避免把普通文件名前缀误判为样本号
        self.logger.warning("无法从文件名提取样本编号", filename=filename)
        return None
