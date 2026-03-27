"""
Excel数据源模型

表示从Excel文件读取的原始数据。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class ExcelDataSource:
    """
    Excel数据源

    存储从Excel文件读取的所有数据，包括单值字段和表格数据。
    """

    file_path: str
    """Excel文件路径"""

    single_values: Dict[str, Any] = field(default_factory=dict)
    """单值数据字典，key为字段名（如 '患者姓名'），value为字段值"""

    table_data: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    """表格数据字典，key为表名（如 '变异明细'），value为行数据列表"""

    sheet_names: List[str] = field(default_factory=list)
    """Excel中的所有sheet名称"""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """元数据，如文件大小、读取时间等"""

    def __post_init__(self):
        """初始化后处理"""
        if not self.file_path:
            raise ValueError("file_path不能为空")

        # 验证文件存在
        if not Path(self.file_path).exists():
            raise FileNotFoundError(f"Excel文件不存在: {self.file_path}")

    def get_single_value(self, field_name: str, default: Any = None) -> Any:
        """
        获取单值字段

        Args:
            field_name: 字段名
            default: 默认值

        Returns:
            字段值
        """
        return self.single_values.get(field_name, default)

    def get_table_data(self, table_name: str) -> List[Dict[str, Any]]:
        """
        获取表格数据

        Args:
            table_name: 表名

        Returns:
            表格数据（行列表）
        """
        return self.table_data.get(table_name, [])

    def has_table(self, table_name: str) -> bool:
        """
        检查是否包含指定表格

        Args:
            table_name: 表名

        Returns:
            True如果包含
        """
        return table_name in self.table_data

    def get_table_row_count(self, table_name: str) -> int:
        """
        获取表格行数

        Args:
            table_name: 表名

        Returns:
            行数
        """
        return len(self.get_table_data(table_name))

    def add_single_value(self, field_name: str, value: Any) -> None:
        """
        添加单值字段

        Args:
            field_name: 字段名
            value: 字段值
        """
        self.single_values[field_name] = value

    def add_table_row(self, table_name: str, row_data: Dict[str, Any]) -> None:
        """
        向表格添加一行

        Args:
            table_name: 表名
            row_data: 行数据
        """
        if table_name not in self.table_data:
            self.table_data[table_name] = []

        self.table_data[table_name].append(row_data)

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典

        Returns:
            字典表示
        """
        return {
            "file_path": self.file_path,
            "single_values": self.single_values,
            "table_data": self.table_data,
            "sheet_names": self.sheet_names,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        """字符串表示"""
        return (
            f"ExcelDataSource(file_path='{self.file_path}', "
            f"single_values={len(self.single_values)}, "
            f"tables={len(self.table_data)}, "
            f"sheets={len(self.sheet_names)})"
        )
