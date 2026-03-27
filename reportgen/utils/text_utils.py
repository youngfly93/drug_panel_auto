"""
统一的文本规范化工具。

所有模块应使用此处的 norm_text() 而非各自的 _norm_text()，
确保对边界值（None, NaN, "-", "*", "none" 等）的处理一致。
"""

from typing import Any


def norm_text(value: Any) -> str:
    """规范化文本值，将各种空值/占位符统一转为空字符串。

    处理的值：None, float NaN, "nan", "none", "null", "", "-", "--", "*"
    """
    if value is None:
        return ""
    # 处理 float NaN（不依赖 pandas/numpy）
    if isinstance(value, float):
        try:
            import math
            if math.isnan(value):
                return ""
        except (TypeError, ValueError):
            pass
    s = str(value).strip()
    if s.lower() in ("nan", "none", "null", ""):
        return ""
    if s in ("-", "--", "*"):
        return ""
    return s
