"""
字段映射模型

定义Excel字段到模板变量的映射规则。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FieldMapping:
    """
    字段映射配置

    定义如何将Excel中的字段映射到docx模板变量。
    """

    variable_name: str
    """模板变量名（如 'patient_name'）"""

    synonyms: List[str] = field(default_factory=list)
    """同义词列表（如 ['患者姓名', '姓名', 'Patient Name']）"""

    data_type: str = "string"
    """数据类型：string/int/float/date/bool"""

    required: bool = False
    """是否必填"""

    default_value: Any = None
    """默认值"""

    format_template: Optional[str] = None
    """格式化模板（如 '{:.2f}' 或 '%Y-%m-%d'）"""

    description: str = ""
    """字段描述"""

    def __post_init__(self):
        """初始化后验证"""
        if not self.variable_name:
            raise ValueError("variable_name不能为空")

        # 确保synonyms是列表
        if not isinstance(self.synonyms, list):
            raise ValueError("synonyms必须是列表")

        # 验证数据类型
        valid_types = {"string", "int", "float", "date", "bool"}
        if self.data_type not in valid_types:
            raise ValueError(
                f"不支持的数据类型: {self.data_type}, 必须是: {valid_types}"
            )

    def matches_column_name(self, column_name: str) -> bool:
        """
        检查列名是否匹配此映射（不区分大小写）

        Args:
            column_name: 列名

        Returns:
            True如果匹配
        """
        if not column_name:
            return False

        column_lower = column_name.lower().strip()

        # 检查是否在同义词列表中
        for synonym in self.synonyms:
            if synonym.lower().strip() == column_lower:
                return True

        return False

    def get_matched_synonym(self, column_name: str) -> Optional[str]:
        """
        获取匹配的同义词

        Args:
            column_name: 列名

        Returns:
            匹配的同义词，如果没有匹配则返回None
        """
        if not column_name:
            return None

        column_lower = column_name.lower().strip()

        for synonym in self.synonyms:
            if synonym.lower().strip() == column_lower:
                return synonym

        return None

    def format_value(self, value: Any) -> Any:
        """
        格式化值

        Args:
            value: 原始值

        Returns:
            格式化后的值
        """
        if value is None:
            return self.default_value

        # 如果没有格式化模板，直接返回
        if not self.format_template:
            return value

        # 根据数据类型格式化
        try:
            if self.data_type == "float":
                # 浮点数格式化：{:.2f}
                return self.format_template.format(float(value))
            elif self.data_type == "int":
                return int(value)
            elif self.data_type == "date":
                # 日期格式化在DataCleaner中处理
                return value
            else:
                return str(value)
        except (ValueError, TypeError):
            return self.default_value

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典

        Returns:
            字典表示
        """
        return {
            "variable_name": self.variable_name,
            "synonyms": self.synonyms,
            "data_type": self.data_type,
            "required": self.required,
            "default_value": self.default_value,
            "format_template": self.format_template,
            "description": self.description,
        }

    def __repr__(self) -> str:
        """字符串表示"""
        return (
            f"FieldMapping(variable_name='{self.variable_name}', "
            f"synonyms={self.synonyms[:2]}..., "
            f"type={self.data_type}, "
            f"required={self.required})"
        )


@dataclass
class TableMapping:
    """
    表格映射配置

    定义如何将Excel表格映射到模板表格。
    """

    table_name: str
    """表格名称（如 'variants'）"""

    sheet_name: str = ""
    """Excel中的sheet名称"""

    column_mappings: Dict[str, FieldMapping] = field(default_factory=dict)
    """列映射，key为变量名，value为FieldMapping"""

    required: bool = False
    """表格是否必需"""

    empty_behavior: str = "show_placeholder"
    """空表格行为：show_placeholder/hide_section/error"""

    filter: Optional[Dict[str, Any]] = None
    """数据过滤配置，用于药物表格等需要按条件筛选数据的场景"""

    def __post_init__(self):
        """初始化后验证"""
        if not self.table_name:
            raise ValueError("table_name不能为空")

        valid_behaviors = {"show_placeholder", "hide_section", "error"}
        if self.empty_behavior not in valid_behaviors:
            raise ValueError(f"不支持的empty_behavior: {self.empty_behavior}")

    def get_column_mapping(self, column_name: str) -> Optional[FieldMapping]:
        """
        根据列名查找映射

        Args:
            column_name: 列名

        Returns:
            FieldMapping或None
        """
        for mapping in self.column_mappings.values():
            if mapping.matches_column_name(column_name):
                return mapping

        return None

    def map_row(self, row_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        映射行数据

        Args:
            row_data: 原始行数据（Excel列名为key）

        Returns:
            映射后的行数据：
            - 保留原始列名（兼容旧模板的 row.Gene_Symbol / row['Freq(%)'] 等写法）
            - 同时提供标准化字段名（如 row.gene / row.variant），以便模板与Excel列名解耦
        """
        mapped_row: Dict[str, Any] = dict(row_data)

        # 先基于同义词为每个标准列变量选择一个源列，并进行格式化
        for var_name, mapping in self.column_mappings.items():
            matched_column = None
            raw_value = None

            for column_name, value in row_data.items():
                if mapping.matches_column_name(column_name):
                    matched_column = column_name
                    raw_value = value
                    break

            formatted_value = mapping.format_value(raw_value)

            # 提供标准化键
            mapped_row[var_name] = formatted_value

            # 兼容：若命中某个源列，同时把源列的值也替换为格式化后的值
            if matched_column is not None:
                mapped_row[matched_column] = formatted_value

        return mapped_row

    def __repr__(self) -> str:
        """字符串表示"""
        return (
            f"TableMapping(table_name='{self.table_name}', "
            f"sheet='{self.sheet_name}', "
            f"columns={len(self.column_mappings)})"
        )
