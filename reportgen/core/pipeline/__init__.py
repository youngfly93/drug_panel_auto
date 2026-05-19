"""Generation pipeline primitives."""

from reportgen.core.pipeline.context import GenerationContext
from reportgen.core.pipeline.result import StageIssue, StageResult
from reportgen.core.pipeline.runner import GenerationPipeline, StageHandle

__all__ = [
    "GenerationContext",
    "GenerationPipeline",
    "StageHandle",
    "StageIssue",
    "StageResult",
]
