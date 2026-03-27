"""
数据验证模块

提供文件路径、字段值等的验证函数。
"""

import os
import re
from pathlib import Path
from typing import Any, Optional


def validate_file_path(
    file_path: str, must_exist: bool = True, file_extensions: Optional[list] = None
) -> tuple[bool, Optional[str]]:
    """
    验证文件路径

    Args:
        file_path: 文件路径
        must_exist: 文件是否必须存在
        file_extensions: 允许的文件扩展名列表（如 ['.xlsx', '.xls']）

    Returns:
        (是否有效, 错误消息)
    """
    if not file_path:
        return False, "文件路径不能为空"

    path = Path(file_path)

    # 检查路径遍历攻击
    try:
        path.resolve()
    except (OSError, RuntimeError) as e:
        return False, f"无效的文件路径: {e}"

    # 检查文件是否存在
    if must_exist and not path.exists():
        return False, f"文件不存在: {file_path}"

    # 检查是否是文件（不是目录）
    if must_exist and not path.is_file():
        return False, f"路径不是文件: {file_path}"

    # 检查文件扩展名
    if file_extensions:
        if path.suffix.lower() not in [ext.lower() for ext in file_extensions]:
            return False, f"不支持的文件格式，仅支持: {', '.join(file_extensions)}"

    return True, None


def validate_excel_file(file_path: str) -> tuple[bool, Optional[str]]:
    """
    验证Excel文件

    Args:
        file_path: Excel文件路径

    Returns:
        (是否有效, 错误消息)
    """
    # 验证基本路径和扩展名
    is_valid, error = validate_file_path(
        file_path, must_exist=True, file_extensions=[".xlsx"]
    )
    if not is_valid:
        return False, error

    # 检查文件大小（< 100MB）
    file_size = os.path.getsize(file_path)
    max_size = 100 * 1024 * 1024  # 100MB
    if file_size > max_size:
        return False, f"Excel文件过大 ({file_size / 1024 / 1024:.1f}MB)，最大支持100MB"

    if file_size == 0:
        return False, "Excel文件为空"

    return True, None


def validate_docx_file(
    file_path: str, must_exist: bool = True
) -> tuple[bool, Optional[str]]:
    """
    验证Docx文件

    Args:
        file_path: Docx文件路径
        must_exist: 文件是否必须存在

    Returns:
        (是否有效, 错误消息)
    """
    return validate_file_path(
        file_path, must_exist=must_exist, file_extensions=[".docx"]
    )


def validate_field_value(
    value: Any,
    field_name: str,
    data_type: str,
    required: bool = False,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> tuple[bool, Optional[str]]:
    """
    验证字段值

    Args:
        value: 字段值
        field_name: 字段名称
        data_type: 数据类型 (string/int/float/date/bool)
        required: 是否必填
        min_value: 最小值（用于数值类型）
        max_value: 最大值（用于数值类型）

    Returns:
        (是否有效, 错误消息)
    """
    # 检查必填
    if required and (value is None or value == ""):
        return False, f"缺失必填字段: {field_name}"

    # 如果非必填且为空，跳过类型验证
    if not required and (value is None or value == ""):
        return True, None

    # 类型验证
    if data_type == "string":
        if not isinstance(value, str):
            return False, f"字段 {field_name} 必须是字符串类型"
        if len(value) > 500:
            return False, f"字段 {field_name} 长度超过限制（最大500字符）"

    elif data_type == "int":
        try:
            int_value = int(value)
            if min_value is not None and int_value < min_value:
                return False, f"字段 {field_name} 值 {int_value} 小于最小值 {min_value}"
            if max_value is not None and int_value > max_value:
                return False, f"字段 {field_name} 值 {int_value} 大于最大值 {max_value}"
        except (ValueError, TypeError):
            return False, f"字段 {field_name} 必须是整数类型"

    elif data_type == "float":
        try:
            float_value = float(value)
            if min_value is not None and float_value < min_value:
                return (
                    False,
                    f"字段 {field_name} 值 {float_value} 小于最小值 {min_value}",
                )
            if max_value is not None and float_value > max_value:
                return (
                    False,
                    f"字段 {field_name} 值 {float_value} 大于最大值 {max_value}",
                )
        except (ValueError, TypeError):
            return False, f"字段 {field_name} 必须是数值类型"

    elif data_type == "date":
        # 简单的日期格式验证（YYYY-MM-DD）
        date_pattern = r"^\d{4}-\d{2}-\d{2}$"
        if not isinstance(value, str) or not re.match(date_pattern, value):
            return False, f"字段 {field_name} 日期格式必须为 YYYY-MM-DD"

    elif data_type == "bool":
        if not isinstance(value, bool):
            return False, f"字段 {field_name} 必须是布尔类型"

    return True, None


def validate_directory_writable(directory: str) -> tuple[bool, Optional[str]]:
    """
    验证目录是否可写

    Args:
        directory: 目录路径

    Returns:
        (是否可写, 错误消息)
    """
    dir_path = Path(directory)

    # 检查目录是否存在
    if not dir_path.exists():
        return False, f"目录不存在: {directory}"

    # 检查是否是目录
    if not dir_path.is_dir():
        return False, f"路径不是目录: {directory}"

    # 检查写权限
    if not os.access(directory, os.W_OK):
        return False, f"目录没有写权限: {directory}"

    return True, None


def validate_patient_name(name: str) -> tuple[bool, Optional[str]]:
    """
    验证患者姓名

    Args:
        name: 患者姓名

    Returns:
        (是否有效, 错误消息)
    """
    if not name or not name.strip():
        return False, "患者姓名不能为空"

    if len(name) > 50:
        return False, "患者姓名过长（最大50字符）"

    return True, None


def validate_sample_id(sample_id: str) -> tuple[bool, Optional[str]]:
    """
    验证样本编号

    Args:
        sample_id: 样本编号

    Returns:
        (是否有效, 错误消息)
    """
    if not sample_id or not sample_id.strip():
        return False, "样本编号不能为空"

    if len(sample_id) > 100:
        return False, "样本编号过长（最大100字符）"

    return True, None
