"""
文件操作工具模块

提供文件和目录操作的辅助函数。
"""

import os
from pathlib import Path


def ensure_directory_exists(directory: str) -> Path:
    """
    确保目录存在，如果不存在则创建

    Args:
        directory: 目录路径

    Returns:
        Path对象

    Raises:
        OSError: 如果无法创建目录
    """
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def get_file_size(file_path: str) -> int:
    """
    获取文件大小（字节）

    Args:
        file_path: 文件路径

    Returns:
        文件大小（字节）

    Raises:
        FileNotFoundError: 如果文件不存在
    """
    return os.path.getsize(file_path)


def get_file_size_mb(file_path: str) -> float:
    """
    获取文件大小（MB）

    Args:
        file_path: 文件路径

    Returns:
        文件大小（MB）
    """
    size_bytes = get_file_size(file_path)
    return size_bytes / (1024 * 1024)


def is_file_readable(file_path: str) -> bool:
    """
    检查文件是否可读

    Args:
        file_path: 文件路径

    Returns:
        True如果文件存在且可读
    """
    return os.path.isfile(file_path) and os.access(file_path, os.R_OK)


def is_directory_writable(directory: str) -> bool:
    """
    检查目录是否可写

    Args:
        directory: 目录路径

    Returns:
        True如果目录存在且可写
    """
    return os.path.isdir(directory) and os.access(directory, os.W_OK)


def safe_filename(filename: str, max_length: int = 200, replacement: str = "_") -> str:
    """
    清理文件名，移除非法字符

    Args:
        filename: 原始文件名
        max_length: 最大文件名长度

    Returns:
        安全的文件名
    """
    # Windows和Linux都不允许的字符
    illegal_chars = r'<>:"/\|?*'

    # 替换非法字符
    safe_name = filename
    for char in illegal_chars:
        safe_name = safe_name.replace(char, replacement)

    # 去除首尾空格和点号
    safe_name = safe_name.strip(". ")

    # 限制长度
    if len(safe_name) > max_length:
        # 保留扩展名
        path = Path(safe_name)
        stem = path.stem[: max_length - len(path.suffix) - 1]
        safe_name = stem + path.suffix

    return safe_name


def get_unique_filename(directory: str, filename: str) -> str:
    """
    如果文件名已存在，生成唯一文件名（添加数字后缀）

    Args:
        directory: 目录路径
        filename: 文件名

    Returns:
        唯一的文件名
    """
    dir_path = Path(directory)
    file_path = dir_path / filename

    if not file_path.exists():
        return filename

    # 分离文件名和扩展名
    path = Path(filename)
    stem = path.stem
    suffix = path.suffix

    # 添加数字后缀直到找到不存在的文件名
    counter = 1
    while True:
        new_filename = f"{stem}_{counter}{suffix}"
        new_path = dir_path / new_filename
        if not new_path.exists():
            return new_filename
        counter += 1


def list_files_with_extension(
    directory: str, extension: str, recursive: bool = False
) -> list[Path]:
    """
    列出目录中指定扩展名的文件

    Args:
        directory: 目录路径
        extension: 文件扩展名（如 '.xlsx'）
        recursive: 是否递归搜索子目录

    Returns:
        文件路径列表
    """
    dir_path = Path(directory)

    if not dir_path.exists() or not dir_path.is_dir():
        return []

    if recursive:
        pattern = f"**/*{extension}"
        return sorted(dir_path.glob(pattern))
    else:
        pattern = f"*{extension}"
        return sorted(dir_path.glob(pattern))


def get_directory_size(directory: str) -> int:
    """
    计算目录总大小（字节）

    Args:
        directory: 目录路径

    Returns:
        目录总大小（字节）
    """
    total_size = 0
    dir_path = Path(directory)

    if not dir_path.exists() or not dir_path.is_dir():
        return 0

    for file_path in dir_path.rglob("*"):
        if file_path.is_file():
            total_size += file_path.stat().st_size

    return total_size


def check_disk_space(directory: str, required_mb: float) -> tuple[bool, float]:
    """
    检查磁盘空间是否足够

    Args:
        directory: 目录路径
        required_mb: 所需空间（MB）

    Returns:
        (是否足够, 可用空间MB)
    """
    try:
        stat = os.statvfs(directory)
        # 可用空间 = 块大小 * 可用块数
        available_bytes = stat.f_bavail * stat.f_frsize
        available_mb = available_bytes / (1024 * 1024)

        return available_mb >= required_mb, available_mb
    except (OSError, AttributeError):
        # Windows系统或其他错误，假设空间足够
        return True, float("inf")
