"""Base types and runner for DOCX post-render processors."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ProcessorContext:
    renderer: Any
    output_path: str
    template_path: str
    template_context: Mapping[str, Any]
    logger: Any


@dataclass(frozen=True)
class ProcessorResult:
    name: str
    status: str
    duration_ms: float
    error: str | None = None
    warning_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 3),
            "error": self.error,
            "warning_message": self.warning_message,
        }


class RenderProcessor(Protocol):
    name: str
    warning_message: str

    def enabled(self, ctx: ProcessorContext) -> bool: ...

    def run(self, ctx: ProcessorContext) -> None: ...


def run_processors(
    processors: Sequence[RenderProcessor],
    ctx: ProcessorContext,
    *,
    fail_fast: bool = False,
) -> list[ProcessorResult]:
    """Run processors in order and collect execution metadata."""
    results: list[ProcessorResult] = []

    for processor in processors:
        start = time.perf_counter()
        warning_message = getattr(processor, "warning_message", None)
        try:
            if not processor.enabled(ctx):
                results.append(
                    ProcessorResult(
                        name=processor.name,
                        status="SKIPPED",
                        duration_ms=(time.perf_counter() - start) * 1000,
                        warning_message=warning_message,
                    )
                )
                continue

            processor.run(ctx)
            results.append(
                ProcessorResult(
                    name=processor.name,
                    status="OK",
                    duration_ms=(time.perf_counter() - start) * 1000,
                    warning_message=warning_message,
                )
            )
        except Exception as exc:
            message = warning_message or f"{processor.name} failed"
            try:
                ctx.logger.warning(message, error=str(exc))
            except Exception:
                pass
            results.append(
                ProcessorResult(
                    name=processor.name,
                    status="ERROR",
                    duration_ms=(time.perf_counter() - start) * 1000,
                    error=str(exc),
                    warning_message=warning_message,
                )
            )
            if fail_fast:
                raise

    return results
