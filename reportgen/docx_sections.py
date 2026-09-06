"""Shared, dependency-light helpers for semantic DOCX section lookup."""

from __future__ import annotations

import re
from typing import Any, Optional, Sequence


_REFERENCE_HEADING_RE = re.compile(
    r"(?:5\s*[\.．、]?\s*参考文献\s*[：:]?|参考文献)"
)

_REFERENCE_END_RE = tuple(
    re.compile(pattern)
    for pattern in (
        r"本次检测质控结果",
        r"高通量测序检测方法说明",
        r"高通量测序局限性",
        r"脉络医学检验简介",
        r"第[一二三四五六七八九十]+部分\s*[：:]?\s*附录",
        r"\d+\s*[.．、]\s*附录",
        r"补充检测结果\s*[：:]\s*TMB[、/]\s*MSI\s*与化疗药物基因组学",
        r"肺癌相关重要基因变异及药物提示",
    )
)


def _paragraph_text(value: Any) -> str:
    text = getattr(value, "text", value)
    return str(text or "").strip()


def find_reference_section_bounds(
    paragraphs: Sequence[Any],
) -> tuple[Optional[int], int]:
    """Return heading and exclusive end indexes for the main reference list."""

    texts = [_paragraph_text(paragraph) for paragraph in paragraphs]
    start: Optional[int] = None
    for index, text in enumerate(texts):
        if _REFERENCE_HEADING_RE.fullmatch(text):
            start = index

    if start is None:
        return None, len(texts)

    end = len(texts)
    for index in range(start + 1, len(texts)):
        text = texts[index]
        if text and any(pattern.fullmatch(text) for pattern in _REFERENCE_END_RE):
            end = index
            break
    return start, end


def find_standalone_marker_indices(
    paragraphs: Sequence[Any],
    marker: str,
) -> tuple[int, ...]:
    """Locate a structural marker only when it is its own body paragraph."""

    target = str(marker or "").strip()
    if not target:
        return ()
    return tuple(
        index
        for index, paragraph in enumerate(paragraphs)
        if _paragraph_text(paragraph) == target
    )


def inspect_structural_marker(
    document: Any,
    marker: str,
) -> tuple[tuple[int, ...], int]:
    """Return valid body-paragraph positions and all DOCX text occurrences."""

    target = str(marker or "").strip()
    if not target:
        return (), 0
    body_paragraphs = list(getattr(document, "paragraphs", ()) or ())
    valid_indices = find_standalone_marker_indices(body_paragraphs, target)
    total = sum((getattr(p, "text", "") or "").count(target) for p in body_paragraphs)
    total += sum(
        (getattr(cell, "text", "") or "").count(target)
        for table in (getattr(document, "tables", ()) or ())
        for row in table.rows
        for cell in row.cells
    )
    for section in (getattr(document, "sections", ()) or ()):
        total += sum(
            (getattr(p, "text", "") or "").count(target)
            for p in section.header.paragraphs
        )
        total += sum(
            (getattr(p, "text", "") or "").count(target)
            for p in section.footer.paragraphs
        )
    return valid_indices, total
