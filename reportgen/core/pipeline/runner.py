"""Small runner for recording report generation stages."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional

from reportgen.core.pipeline.context import GenerationContext
from reportgen.core.pipeline.result import StageResult


class StageHandle:
    """Mutable handle exposed while a stage is running."""

    def __init__(self, result: StageResult):
        self.result = result

    @property
    def metrics(self) -> Dict[str, Any]:
        return self.result.metrics

    @property
    def artifacts(self) -> Dict[str, Any]:
        return self.result.artifacts

    def warn(
        self,
        code: str,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.result.status == "PASS":
            self.result.status = "WARN"
        self.result.add_issue(
            level="WARNING",
            code=code,
            message=message,
            details=details,
        )

    def fail(
        self,
        code: str,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.result.status = "FAIL"
        self.result.add_issue(
            level="ERROR",
            code=code,
            message=message,
            details=details,
        )

    def skip(self, code: str = "STAGE_SKIPPED", message: str = "") -> None:
        self.result.status = "SKIPPED"
        if message:
            self.result.add_issue(level="INFO", code=code, message=message)


class GenerationPipeline:
    """Records stage outcomes for one generation request.

    The runner intentionally does not own report generation yet. It provides a
    thin compatibility layer so M6 can make the legacy flow observable before
    later milestones migrate logic into independent stage classes.
    """

    def __init__(self, context: Optional[GenerationContext] = None):
        self.context = context or GenerationContext()
        self._stage_results: List[StageResult] = []

    @contextmanager
    def stage(self, name: str) -> Iterator[StageHandle]:
        result = StageResult(name=name)
        handle = StageHandle(result)
        start = time.perf_counter()
        try:
            yield handle
        except Exception as exc:
            result.status = "FAIL"
            result.add_issue(
                level="ERROR",
                code="STAGE_EXCEPTION",
                message=str(exc),
                details={"exception_type": exc.__class__.__name__},
            )
            raise
        finally:
            result.duration_ms = round((time.perf_counter() - start) * 1000, 3)
            self._stage_results.append(result)

    def to_list(self) -> List[Dict[str, Any]]:
        return [result.to_dict() for result in self._stage_results]

    def run_step(
        self,
        name: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Run one named stage and record its result."""
        with self.stage(name) as stage:
            return func(stage, *args, **kwargs)
