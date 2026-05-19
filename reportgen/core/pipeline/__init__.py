"""Generation pipeline primitives."""

from reportgen.core.pipeline.context import GenerationContext
from reportgen.core.pipeline.result import StageIssue, StageResult
from reportgen.core.pipeline.runner import GenerationPipeline, StageHandle
from reportgen.core.pipeline.summary import summarize_stage_results

__all__ = [
    "GenerationContext",
    "GenerationPipeline",
    "StageHandle",
    "StageIssue",
    "StageResult",
    "summarize_stage_results",
]
