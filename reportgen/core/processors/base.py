"""Base types and runner for DOCX post-render processors."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence
from zipfile import ZipFile


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
    # 可观测性：该处理器是否真的改动了文档，以及粗粒度增减量。
    # changed=False + status=OK 往往是"锚点没匹配上/被覆盖"的静默失效信号。
    changed: bool = False
    deltas: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 3),
            "error": self.error,
            "warning_message": self.warning_message,
            "changed": self.changed,
            "deltas": self.deltas,
        }


def _docx_fingerprint(path: str) -> dict[str, int]:
    """轻量文档指纹：只读 word/document.xml 字节做子串计数，不全解析。

    用于在处理器前后对比，判断该处理器是否真的改动了文档。
    """
    try:
        with ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
    except Exception:
        return {}
    return {
        "xml_bytes": len(xml),
        "paragraphs": xml.count(b"<w:p>") + xml.count(b"<w:p "),
        "tables": xml.count(b"<w:tbl>"),
        "drawings": xml.count(b"<w:drawing") + xml.count(b"<w:pict"),
        "images": xml.count(b"<a:blip"),
    }


def _fingerprint_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    keys = set(before) | set(after)
    delta = {k: after.get(k, 0) - before.get(k, 0) for k in keys}
    return {k: v for k, v in sorted(delta.items()) if v != 0}


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

            before = _docx_fingerprint(ctx.output_path)
            processor.run(ctx)
            after = _docx_fingerprint(ctx.output_path)
            deltas = _fingerprint_delta(before, after)
            results.append(
                ProcessorResult(
                    name=processor.name,
                    status="OK",
                    duration_ms=(time.perf_counter() - start) * 1000,
                    warning_message=warning_message,
                    changed=bool(deltas),
                    deltas=deltas,
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

    # 可观测性：每个处理器的 changed/deltas 始终写入 ProcessorResult（落到生成结果
    # 的 post_processors 侧车，随时可查）。设 REPORTGEN_TRACE_PROCESSORS=1 时，额外把
    # 完整逐处理器轨迹打到 WARNING 级（server.log 可见），用于现场调试"某处理器是否
    # 真生效"——OK 但 changed=False 往往是锚点没匹配上/被后续步骤覆盖的静默失效。
    import os

    if os.environ.get("REPORTGEN_TRACE_PROCESSORS") == "1":
        for r in results:
            try:
                ctx.logger.warning(
                    "post_processor_trace",
                    name=r.name,
                    status=r.status,
                    changed=r.changed,
                    deltas=r.deltas,
                    ms=round(r.duration_ms, 1),
                )
            except Exception:
                pass

    return results
