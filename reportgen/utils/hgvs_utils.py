"""
HGVS-related helpers.

This module contains small, dependency-free utilities used across the project
to format HGVS loci and infer simplified variant types for reporting.
"""

from __future__ import annotations

from typing import Any

from reportgen.utils.text_utils import norm_text as _norm_text


def infer_variant_type_cn(c_hgvs: Any) -> str:
    """Infer a simplified Chinese variant type from c.HGVS text.

    Rules (per report annotations):
    - delins -> 缺失插入
    - del    -> 缺失
    - dup    -> 重复
    - ins    -> 插入
    - else   -> 点突变
    """
    s = _norm_text(c_hgvs)
    if not s:
        return ""

    low = s.lower()
    if "delins" in low:
        return "缺失插入"
    if "dup" in low:
        return "重复"
    if "ins" in low:
        return "插入"
    if "del" in low:
        return "缺失"
    return "点突变"


def format_variant_site(c_hgvs: Any, p_hgvs: Any, *, sep: str = ",\n") -> str:
    """Format a locus text by combining c.HGVS and p.HGVS (comma + newline)."""
    c = _norm_text(c_hgvs)
    p = _norm_text(p_hgvs)
    if c and p:
        return f"{c}{sep}{p}"
    return c or p
