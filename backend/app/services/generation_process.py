"""Process-isolated report generation with hard timeout protection."""

from __future__ import annotations

import multiprocessing
import os
import signal
import time
import traceback
from multiprocessing.context import BaseContext
from multiprocessing.queues import Queue
from queue import Empty
from typing import Any, Callable

from app.config import settings
from app.services.reportgen_bridge import ReportGenBridge


class GenerationTimeoutError(TimeoutError):
    """Raised when a report-generation child process exceeds its time budget."""


class GenerationProcessError(RuntimeError):
    """Raised when a report-generation child process exits unsuccessfully."""


def _process_context() -> BaseContext:
    try:
        return multiprocessing.get_context("spawn")
    except ValueError:
        return multiprocessing.get_context()


def _join_or_kill(process: multiprocessing.Process, *, grace_seconds: float) -> None:
    if not process.is_alive():
        return
    if os.name == "posix" and process.pid:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            process.terminate()
        except OSError:
            process.terminate()
    else:
        process.terminate()

    process.join(timeout=max(0.1, grace_seconds))
    if process.is_alive():
        if os.name == "posix" and process.pid:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                process.kill()
            except OSError:
                process.kill()
        else:
            process.kill()
        process.join(timeout=max(0.1, grace_seconds))


def _child_entrypoint(
    result_queue: Queue,
    worker: Callable[..., Any],
    args: tuple,
    kwargs: dict[str, Any],
) -> None:
    if os.name == "posix":
        try:
            os.setsid()
        except OSError:
            pass
    try:
        result_queue.put(
            {
                "ok": True,
                "result": worker(*args, **kwargs),
            }
        )
    except BaseException as exc:
        result_queue.put(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback_tail": traceback.format_exc()[-4000:],
            }
        )


def run_callable_with_timeout(
    worker: Callable[..., Any],
    *,
    args: tuple = (),
    kwargs: dict[str, Any] | None = None,
    timeout_seconds: int | float,
    grace_seconds: int | float | None = None,
) -> Any:
    """Run a picklable callable in a child process and terminate on timeout."""
    timeout = max(0.1, float(timeout_seconds))
    grace = (
        float(settings.generation_process_termination_grace_seconds)
        if grace_seconds is None
        else max(0.1, float(grace_seconds))
    )
    ctx = _process_context()
    result_queue = ctx.Queue(maxsize=1)
    process = ctx.Process(
        target=_child_entrypoint,
        args=(result_queue, worker, args, dict(kwargs or {})),
        daemon=False,
    )
    started = time.monotonic()
    process.start()
    process.join(timeout=timeout)

    if process.is_alive():
        _join_or_kill(process, grace_seconds=grace)
        elapsed = time.monotonic() - started
        try:
            result_queue.close()
        except Exception:
            pass
        raise GenerationTimeoutError(
            f"报告生成超过 {timeout:g} 秒，已终止生成子进程。"
            f" elapsed={elapsed:.1f}s"
        )

    try:
        payload = result_queue.get(timeout=1)
    except Empty as exc:
        raise GenerationProcessError(
            f"报告生成子进程未返回结果，exitcode={process.exitcode}。"
        ) from exc
    finally:
        try:
            result_queue.close()
        except Exception:
            pass

    if payload.get("ok"):
        return payload.get("result")
    raise GenerationProcessError(
        f"报告生成子进程失败: {payload.get('error_type')}: {payload.get('error')}"
    )


def _generate_report_in_child(
    *,
    config_dir: str,
    template_dir: str,
    generate_kwargs: dict[str, Any],
) -> dict[str, Any]:
    bridge = ReportGenBridge(config_dir=config_dir, template_dir=template_dir)
    return bridge.generate_report(**generate_kwargs)


def should_isolate_bridge(bridge: Any) -> bool:
    return bool(
        settings.generation_process_isolation
        and isinstance(bridge, ReportGenBridge)
    )


def run_generate_report_with_timeout(
    bridge: Any,
    *,
    timeout_seconds: int | float | None = None,
    force_process: bool | None = None,
    **generate_kwargs,
) -> dict[str, Any]:
    """Generate a report directly or in a killable child process."""
    use_process = should_isolate_bridge(bridge) if force_process is None else force_process
    if not use_process:
        return bridge.generate_report(**generate_kwargs)

    return run_callable_with_timeout(
        _generate_report_in_child,
        kwargs={
            "config_dir": getattr(bridge, "config_dir", settings.upstream_config_dir),
            "template_dir": getattr(bridge, "template_dir", settings.upstream_template_dir),
            "generate_kwargs": generate_kwargs,
        },
        timeout_seconds=timeout_seconds or settings.generation_process_timeout_seconds,
    )
