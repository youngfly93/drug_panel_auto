"""
Task manager: ProcessPoolExecutor for CPU-bound report generation
with multiprocessing.Queue → WebSocket progress bridge.
"""

import asyncio
import json
import multiprocessing
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.config import settings

# Module-level executor (initialized lazily)
_executor: Optional[ProcessPoolExecutor] = None
_progress_queues: dict[str, multiprocessing.Queue] = {}


def _get_executor() -> ProcessPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ProcessPoolExecutor(max_workers=settings.max_workers)
    return _executor


def _run_batch_in_process(
    inputs: list[str],
    output_root: str,
    config_dir: str,
    template: Optional[str],
    template_contract: str,
    highlight: bool,
    task_id: str,
    queue_id: str,
) -> dict[str, Any]:
    """
    Worker function that runs in a child process.
    Sends progress messages via multiprocessing.Queue.
    """
    import sys

    # Ensure upstream is importable in child process
    upstream_root = str(Path(config_dir).parent)
    if upstream_root not in sys.path:
        sys.path.insert(0, upstream_root)

    from reportgen.core.batch_runner import (
        BatchValidateOptions,
        run_batch_generate_validate,
    )

    # Reconstruct the queue from the manager
    # We can't pass Queue directly, use a global registry
    import multiprocessing as mp

    opts = BatchValidateOptions(
        inputs=inputs,
        config_dir=config_dir,
        template=template,
        output_root=output_root,
        template_contract=template_contract,
        highlight=highlight,
        log_level="WARNING",
        render="none",
        emit_context=True,
        emit_meta=True,
    )

    # Progress callback that writes to stdout-based progress
    # (we'll capture this in the parent via queue)
    progress_messages: list[str] = []

    def progress_callback(msg: str):
        progress_messages.append(msg)

    try:
        result = run_batch_generate_validate(opts, progress=progress_callback)
        return {
            "success": True,
            "report": result.report,
            "report_path": str(result.report_path),
            "output_root": str(result.output_root),
            "progress_messages": progress_messages,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "progress_messages": progress_messages,
        }


async def submit_batch_task(
    task_id: str,
    inputs: list[str],
    output_root: str,
    config_dir: str,
    template: Optional[str] = None,
    template_contract: str = "warn",
    highlight: bool = False,
    on_complete=None,
) -> None:
    """
    Submit a batch generation task to the process pool.
    Runs in background, calls on_complete when done.
    """
    loop = asyncio.get_event_loop()
    executor = _get_executor()

    future = loop.run_in_executor(
        executor,
        _run_batch_in_process,
        inputs,
        output_root,
        config_dir,
        template,
        template_contract,
        highlight,
        task_id,
        "",
    )

    result = await future

    if on_complete:
        await on_complete(task_id, result)

    return result


def shutdown():
    """Shutdown the process pool gracefully."""
    global _executor
    if _executor:
        _executor.shutdown(wait=False)
        _executor = None
