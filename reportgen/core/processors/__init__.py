"""Composable DOCX post-render processors."""

from reportgen.core.processors.base import (
    ProcessorContext,
    ProcessorResult,
    RenderProcessor,
    run_processors,
)
from reportgen.core.processors.docx import build_default_docx_processors

__all__ = [
    "ProcessorContext",
    "ProcessorResult",
    "RenderProcessor",
    "build_default_docx_processors",
    "run_processors",
]
