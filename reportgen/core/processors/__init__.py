"""Composable DOCX post-render processors."""

from reportgen.core.processors.base import (
    ProcessorContext,
    ProcessorResult,
    RenderProcessor,
    run_processors,
)
from reportgen.core.processors.docx import build_default_docx_processors
from reportgen.core.processors.registry import (
    CRITICAL_DOCX_PROCESSOR_NAMES,
    build_docx_processors,
    critical_docx_processor_names,
    default_docx_processor_names,
    known_docx_processor_names,
    validate_docx_processor_sequence,
)

__all__ = [
    "ProcessorContext",
    "ProcessorResult",
    "RenderProcessor",
    "CRITICAL_DOCX_PROCESSOR_NAMES",
    "critical_docx_processor_names",
    "build_default_docx_processors",
    "build_docx_processors",
    "default_docx_processor_names",
    "known_docx_processor_names",
    "run_processors",
    "validate_docx_processor_sequence",
]
