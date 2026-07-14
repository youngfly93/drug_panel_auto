"""
HGVS-related helpers.

This module contains small, dependency-free utilities used across the project
to format HGVS loci and infer simplified variant types for reporting.
"""

from __future__ import annotations

import re
from typing import Any

from reportgen.utils.text_utils import norm_text as _norm_text


_VERBOSE_DEL_DUP_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?P<prefix>c\.\d+(?:[+-]\d+)?(?:_\d+(?:[+-]\d+)?)?)"
    r"(?P<event>del|dup)(?P<sequence>[ACGT]+)"
    r"(?![A-Za-z])",
    flags=re.IGNORECASE,
)


def normalize_c_hgvs_display_text(value: Any) -> str:
    """Use concise HGVS deletion/duplication notation in report-facing text.

    Matching and provenance retain the source value (for example
    ``c.1291delA``); only presentation is canonicalized to ``c.1291del``.
    ``delins`` and non-HGVS prose are intentionally untouched.
    """
    text = str(value) if value is not None else ""
    return _VERBOSE_DEL_DUP_RE.sub(
        lambda match: f"{match.group('prefix')}{match.group('event').lower()}",
        text,
    )


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
