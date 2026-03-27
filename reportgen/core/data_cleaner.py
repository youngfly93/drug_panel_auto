"""
数据清洗器

负责清洗和标准化报告数据。
"""

import re
from datetime import datetime
from typing import Any, Optional

from dateutil import parser as date_parser

from reportgen.models.report_data import ReportData
from reportgen.utils.logger import get_logger


class DataCleaner:
    """
    数据清洗器

    清洗和标准化报告数据，包括：
    - 移除多余空格
    - 标准化日期格式
    - 处理缺失值
    - 数值格式化
    """

    def __init__(self, log_file: Optional[str] = None, log_level: str = "INFO"):
        """
        初始化数据清洗器

        Args:
            log_file: 日志文件路径
            log_level: 日志级别
        """
        self.logger = get_logger(log_file=log_file, level=log_level)

    def clean(self, report_data: ReportData) -> ReportData:
        """
        清洗报告数据

        Args:
            report_data: 原始报告数据

        Returns:
            清洗后的报告数据（同一对象）
        """
        self.logger.info("开始数据清洗")

        # 清洗单值字段
        cleaned_count = 0
        for field_name, value in list(report_data.context.items()):
            if isinstance(value, list):
                # 表格数据
                cleaned_rows = []
                for row in value:
                    cleaned_row = {k: self._clean_value(v) for k, v in row.items()}
                    cleaned_rows.append(cleaned_row)
                report_data.context[field_name] = cleaned_rows
                cleaned_count += len(cleaned_rows)
            else:
                # 单值字段
                report_data.context[field_name] = self._clean_value(value)
                cleaned_count += 1

        self.logger.info("数据清洗完成", cleaned_items=cleaned_count)
        return report_data

    def _clean_value(self, value: Any) -> Any:
        """
        清洗单个值

        Args:
            value: 原始值

        Returns:
            清洗后的值
        """
        # None值保持不变
        if value is None:
            return None

        # 字符串清洗
        if isinstance(value, str):
            return self._clean_string(value)

        # 数值类型保持不变
        if isinstance(value, (int, float, bool)):
            return value

        # 其他类型转为字符串
        return str(value)

    def _clean_string(self, text: str) -> str:
        """
        清洗字符串

        Args:
            text: 原始字符串

        Returns:
            清洗后的字符串
        """
        if not text:
            return text

        # 移除首尾空格
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()

        # 统一空格/制表符，但保留换行符（用于列表/多行描述等）
        text = re.sub(r"[ \t]+", " ", text)

        # 过多连续空行压缩为最多2行
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 移除不可见字符（保留换行符）
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

        return text

    def normalize_date(
        self, date_value: Any, output_format: str = "%Y-%m-%d"
    ) -> Optional[str]:
        """
        标准化日期格式

        Args:
            date_value: 日期值（字符串或datetime对象）
            output_format: 输出格式

        Returns:
            格式化后的日期字符串，如果无法解析返回None
        """
        if date_value is None:
            return None

        try:
            # 如果已经是datetime对象
            if isinstance(date_value, datetime):
                return date_value.strftime(output_format)

            # 尝试解析字符串
            if isinstance(date_value, str):
                # 移除空格
                date_str = date_value.strip()

                # 尝试使用dateutil解析
                dt = date_parser.parse(date_str, fuzzy=True)
                return dt.strftime(output_format)

            return None

        except Exception as e:
            self.logger.warning("日期解析失败", value=str(date_value), error=str(e))
            return None

    def format_number(
        self, number_value: Any, decimal_places: int = 2, unit: str = ""
    ) -> str:
        """
        格式化数值

        Args:
            number_value: 数值
            decimal_places: 小数位数
            unit: 单位（如 '%', 'X'）

        Returns:
            格式化后的字符串
        """
        if number_value is None:
            return "-"

        try:
            num = float(number_value)
            formatted = f"{num:.{decimal_places}f}"

            if unit:
                formatted += unit

            return formatted

        except (ValueError, TypeError):
            self.logger.warning("数值格式化失败", value=str(number_value))
            return str(number_value)

    def clean_patient_name(self, name: str) -> str:
        """
        清洗患者姓名（脱敏处理）

        Args:
            name: 原始姓名

        Returns:
            清洗后的姓名
        """
        if not name:
            return name

        # 移除空格
        name = self._clean_string(name)

        # TODO: 如需脱敏，可以在这里实现
        # 例如：将姓名中间字符替换为*

        return name

    def clean_sample_id(self, sample_id: str) -> str:
        """
        清洗样本编号

        Args:
            sample_id: 原始样本编号

        Returns:
            清洗后的样本编号
        """
        if not sample_id:
            return sample_id

        # 移除空格并转为大写
        sample_id = self._clean_string(sample_id).upper()

        # 移除非法字符（只保留字母、数字、连字符、下划线）
        sample_id = re.sub(r"[^A-Z0-9\-_]", "", sample_id)

        return sample_id

    # 已知日期字段（医疗报告中日期字段稳定且有限）
    _KNOWN_DATE_FIELDS = frozenset([
        "report_date", "collection_date", "receive_date",
    ])

    _ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    _CHINESE_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?")

    def _normalize_dates(self, report_data: ReportData) -> None:
        """
        标准化已知日期字段为 YYYY-MM-DD 格式

        Args:
            report_data: 报告数据
        """
        for field_name in self._KNOWN_DATE_FIELDS:
            value = report_data.get_field(field_name)
            if value is None:
                continue
            if not isinstance(value, str):
                # datetime 对象等由 normalize_date 处理
                normalized = self.normalize_date(value)
                if normalized is not None:
                    report_data.set_field(field_name, normalized)
                continue
            # 已经是标准格式的跳过
            stripped = value.strip()
            if self._ISO_DATE_RE.match(stripped):
                continue
            # 预处理中文日期格式（dateutil fuzzy 对中文支持不佳）
            cn_match = self._CHINESE_DATE_RE.search(stripped)
            if cn_match:
                normalized = f"{cn_match.group(1)}-{int(cn_match.group(2)):02d}-{int(cn_match.group(3)):02d}"
                report_data.set_field(field_name, normalized)
                self.logger.debug(
                    "中文日期格式标准化", field=field_name, original=value, normalized=normalized
                )
                continue
            # 尝试标准化
            normalized = self.normalize_date(value)
            if normalized is not None:
                report_data.set_field(field_name, normalized)
                self.logger.debug(
                    "日期格式标准化", field=field_name, original=value, normalized=normalized
                )

    def validate_and_clean(self, report_data: ReportData) -> ReportData:
        """
        验证并清洗报告数据

        Args:
            report_data: 报告数据

        Returns:
            清洗后的报告数据
        """
        # 先清洗
        self.clean(report_data)

        # 标准化日期字段
        self._normalize_dates(report_data)

        # 验证关键字段
        self._validate_required_fields(report_data)

        return report_data

    def _validate_required_fields(self, report_data: ReportData) -> None:
        """
        验证必填字段

        Args:
            report_data: 报告数据
        """
        # 定义必填字段列表（可以从配置读取）
        required_fields = ["sample_id", "report_date"]

        for field_name in required_fields:
            value = report_data.get_field(field_name)
            # ✅ 修复：只在真正为None或空字符串时才报错，不要覆盖已有的有效值
            if value is None or (isinstance(value, str) and value == ""):
                # 不要在验证失败时覆盖字段值，只记录错误
                self.logger.warning(
                    "必填字段缺失或为空", field=field_name, current_value=value
                )
                report_data.add_validation_error(f"缺失必填字段: {field_name}")
