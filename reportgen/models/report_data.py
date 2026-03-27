"""
报告数据模型

表示已映射和清洗后的报告数据，可直接用于模板渲染。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class ReportData:
    """
    报告数据

    经过字段映射和数据清洗后的报告数据，可直接传递给模板引擎。
    """

    context: Dict[str, Any] = field(default_factory=dict)
    """模板上下文数据，包含所有单值字段和表格数据"""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """元数据，如生成时间、源文件等"""

    validation_errors: List[str] = field(default_factory=list)
    """验证错误列表"""

    def __post_init__(self):
        """初始化后处理"""
        # 确保metadata包含基本信息
        if "generated_at" not in self.metadata:
            self.metadata["generated_at"] = datetime.now().isoformat()

    def set_field(self, field_name: str, value: Any) -> None:
        """
        设置字段值

        Args:
            field_name: 字段名
            value: 字段值
        """
        self.context[field_name] = value

    def get_field(self, field_name: str, default: Any = None) -> Any:
        """
        获取字段值

        Args:
            field_name: 字段名
            default: 默认值

        Returns:
            字段值
        """
        return self.context.get(field_name, default)

    def has_field(self, field_name: str) -> bool:
        """
        检查是否包含字段

        Args:
            field_name: 字段名

        Returns:
            True如果包含
        """
        return field_name in self.context

    def set_table(self, table_name: str, table_data: List[Dict[str, Any]]) -> None:
        """
        设置表格数据

        Args:
            table_name: 表格名
            table_data: 表格数据（行列表）
        """
        self.context[table_name] = table_data

    def get_table(self, table_name: str) -> List[Dict[str, Any]]:
        """
        获取表格数据

        Args:
            table_name: 表格名

        Returns:
            表格数据（行列表）
        """
        return self.context.get(table_name, [])

    def has_table(self, table_name: str) -> bool:
        """
        检查是否包含表格

        Args:
            table_name: 表格名

        Returns:
            True如果包含
        """
        return table_name in self.context and isinstance(self.context[table_name], list)

    def add_validation_error(self, error: str) -> None:
        """
        添加验证错误

        Args:
            error: 错误消息
        """
        if error and error not in self.validation_errors:
            self.validation_errors.append(error)

    def is_valid(self) -> bool:
        """
        检查数据是否有效（无验证错误）

        Returns:
            True如果有效
        """
        return len(self.validation_errors) == 0

    def get_validation_summary(self) -> str:
        """
        获取验证摘要

        Returns:
            验证摘要字符串
        """
        if self.is_valid():
            return "数据验证通过"

        return f"发现{len(self.validation_errors)}个验证错误:\n" + "\n".join(
            f"- {error}" for error in self.validation_errors
        )

    def merge_context(self, other_context: Dict[str, Any]) -> None:
        """
        合并其他上下文数据

        Args:
            other_context: 其他上下文数据
        """
        self.context.update(other_context)

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典

        Returns:
            字典表示
        """
        return {
            "context": self.context,
            "metadata": self.metadata,
            "validation_errors": self.validation_errors,
        }

    def get_template_context(self) -> Dict[str, Any]:
        """
        获取模板上下文（仅context数据，不包含元数据）

        Returns:
            模板上下文字典
        """
        return self.context

    def __repr__(self) -> str:
        """字符串表示"""
        fields_count = len(
            [k for k, v in self.context.items() if not isinstance(v, list)]
        )
        tables_count = len([k for k, v in self.context.items() if isinstance(v, list)])
        return (
            f"ReportData(fields={fields_count}, "
            f"tables={tables_count}, "
            f"valid={self.is_valid()})"
        )
