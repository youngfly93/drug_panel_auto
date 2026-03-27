"""
Batch highlight runner for generated DOCX reports.

This reads a validation report (validation_report.json) produced by the batch
pipeline and generates highlighted copies of each output DOCX.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from reportgen.utils.docx_highlighter import highlight_rendered_docx
from reportgen.utils.docx_render import render_docx_to_pngs


def find_latest_validation_report(*, root: Path) -> Path:
    candidates: List[Path] = []
    for d in sorted(root.glob("batch_validate_*")):
        if not d.is_dir():
            continue
        report = d / "validation_report.json"
        if report.exists():
            candidates.append(report)

    if not candidates:
        raise FileNotFoundError(f"No validation_report.json found under: {root}")

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _safe_name(path_str: str) -> str:
    try:
        return Path(path_str).name
    except Exception:
        return str(path_str)


@dataclass(frozen=True)
class BatchHighlightOptions:
    report: Optional[str] = None
    batch_root: str = "data/output"
    output_root: str = "output/doc/highlighted"
    color: str = "D9EAF7"
    skip_empty: bool = True
    only_ok: bool = False
    max_files: Optional[int] = None
    render: str = "none"  # none|first|all
    render_dpi: int = 120
    show_paths: bool = False


@dataclass(frozen=True)
class BatchHighlightRun:
    report: Dict[str, Any]
    output_root: Path


def run_batch_highlight_latest(
    opts: BatchHighlightOptions,
    *,
    progress: Optional[Callable[[str], None]] = None,
) -> BatchHighlightRun:
    batch_root = Path(opts.batch_root).resolve()
    report_path = (
        Path(opts.report).resolve()
        if opts.report
        else find_latest_validation_report(root=batch_root)
    )

    report_obj = json.loads(report_path.read_text(encoding="utf-8"))
    results = report_obj.get("results") or []

    batch_dir = report_path.parent.name
    out_root = Path(opts.output_root).resolve() / batch_dir
    out_root.mkdir(parents=True, exist_ok=True)

    processed = 0
    skipped = 0
    failed = 0
    items: List[Dict[str, Any]] = []

    for job in results:
        if opts.max_files is not None and processed >= int(opts.max_files):
            break

        if opts.only_ok and not job.get("ok", False):
            skipped += 1
            continue

        template = job.get("template")
        input_docx = job.get("output_docx")
        if not template or not input_docx:
            skipped += 1
            continue
        if _safe_name(str(input_docx)).startswith("._"):
            skipped += 1
            continue

        input_path = Path(str(input_docx)).resolve()
        template_path = Path(str(template)).resolve()
        if not input_path.exists() or not template_path.exists():
            failed += 1
            items.append(
                {
                    "index": job.get("index"),
                    "ok": False,
                    "input_docx": str(input_path),
                    "template": str(template_path),
                    "error": "missing_input_or_template",
                }
            )
            continue

        output_path = out_root / f"{input_path.stem}_highlighted.docx"

        try:
            summary = highlight_rendered_docx(
                template_path=str(template_path),
                input_docx_path=str(input_path),
                output_docx_path=str(output_path),
                color=opts.color,
                skip_empty=bool(opts.skip_empty),
            )

            rendered_pages: List[str] = []
            if opts.render != "none":
                pages_dir = (
                    out_root / "pages" / f"{int(job.get('index', 0)):03d}"
                ).resolve()
                pages_dir.mkdir(parents=True, exist_ok=True)

                first_page = 1 if opts.render == "first" else None
                last_page = 1 if opts.render == "first" else None
                pngs = render_docx_to_pngs(
                    Path(output_path),
                    output_dir=pages_dir,
                    dpi=int(opts.render_dpi),
                    keep_pdf=False,
                    first_page=first_page,
                    last_page=last_page,
                )
                rendered_pages = [p.name for p in pngs if not p.name.startswith("._")]

            item = {
                "index": job.get("index"),
                "ok": True,
                "input_docx": str(input_path),
                "template": str(template_path),
                "output_docx": str(output_path),
                "summary": summary.__dict__,
                "rendered_pages": rendered_pages,
            }
            items.append(item)
            processed += 1

            if progress:
                if opts.show_paths:
                    progress(
                        f"[{processed}] ok template={template_path} input={input_path} "
                        f"output={output_path}"
                    )
                else:
                    progress(
                        f"[{processed}] ok output={output_path.name} "
                        f"highlighted_runs={summary.highlighted_runs}"
                    )

        except Exception as e:
            failed += 1
            items.append(
                {
                    "index": job.get("index"),
                    "ok": False,
                    "input_docx": str(input_path),
                    "template": str(template_path),
                    "output_docx": str(output_path),
                    "error": str(e),
                }
            )
            if progress:
                if opts.show_paths:
                    progress(
                        f"[{processed+failed}] failed input={input_path} error={e}"
                    )
                else:
                    progress(
                        f"[{processed+failed}] failed output={output_path.name} "
                        f"error={e}"
                    )

    out_report = {
        "generated_at": datetime.now().isoformat(),
        "source_validation_report": str(report_path),
        "batch_dir": batch_dir,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "output_root": str(out_root),
        "items": items,
    }
    (out_root / "highlight_summary.json").write_text(
        json.dumps(out_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return BatchHighlightRun(report=out_report, output_root=out_root)
