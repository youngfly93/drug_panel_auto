#!/usr/bin/env python3
"""Render a .docx with the production engine and flag blank / near-blank pages.

Floating text boxes and stray empty paragraphs look fine in Word but render as
big white gaps under LibreOffice headless (the production engine). This check
renders the docx to page PNGs and reports any page whose non-white pixel ratio
falls below a threshold.

A trailing blank page (last page only) is common and usually harmless, so by
default it is reported but not failed; use ``--strict-trailing`` to fail on it.
A blank page in the *middle* of the document is a real defect and always fails.

If LibreOffice is unavailable, the check degrades gracefully: it prints a SKIP
warning and exits 0 (so it never blocks a machine without LO), unless
``--require-render`` is given.

Usage::

    python scripts/render_blank_page_check.py panels/<panel>/templates/<tpl>.docx
    python scripts/render_blank_page_check.py report.docx --dpi 150 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.utils.docx_render import DocxRenderError, render_docx_to_pngs  # noqa: E402


def page_nonwhite_ratio(png_path: Path) -> float:
    """Fraction of pixels that are meaningfully non-white."""
    with Image.open(png_path) as image:
        gray = image.convert("L")
        white = Image.new("L", gray.size, 255)
        diff = ImageChops.difference(gray, white)
        width, height = gray.size
        total = width * height
        nonwhite = sum(1 for value in diff.getdata() if value > 12)
    return nonwhite / total if total else 0.0


def _page_number(png_path: Path) -> int:
    import re

    match = re.search(r"-(\d+)\.png$", png_path.name)
    return int(match.group(1)) if match else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("docx", type=Path, help="The .docx to render and check")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument(
        "--blank-threshold",
        type=float,
        default=0.003,
        help="Pages with non-white ratio below this are near-blank (default 0.003).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tmp/blank_page_check"),
        help="Where to write rendered PNGs/PDF.",
    )
    parser.add_argument(
        "--strict-trailing",
        action="store_true",
        help="Also fail when only the trailing page is blank.",
    )
    parser.add_argument(
        "--require-render",
        action="store_true",
        help="Fail (instead of SKIP) when LibreOffice is unavailable.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--include-automatic-blank-pages", action="store_true",
        help="Include LibreOffice's automatically inserted section-parity blank pages.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.docx.exists():
        print(f"❌ not found: {args.docx}", file=sys.stderr)
        return 2

    output_dir = (ROOT / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        pngs = render_docx_to_pngs(
            args.docx,
            output_dir=output_dir,
            dpi=args.dpi,
            keep_pdf=True,
            timeout_seconds=180,
            include_automatic_blank_pages=args.include_automatic_blank_pages,
        )
    except DocxRenderError as exc:
        msg = f"LibreOffice render unavailable: {exc}"
        if args.require_render:
            print(f"❌ {msg}", file=sys.stderr)
            return 2
        print(f"⏭️  SKIP (render not run): {msg}")
        if args.json:
            print(json.dumps({"status": "SKIP", "reason": str(exc)}, ensure_ascii=False))
        return 0

    pages = sorted(
        ({"page": _page_number(p), "file": str(p), "nonwhite_ratio": round(page_nonwhite_ratio(p), 6)} for p in pngs),
        key=lambda d: d["page"],
    )
    for page in pages:
        page["near_blank"] = page["nonwhite_ratio"] < args.blank_threshold

    total = len(pages)
    near_blank = [p["page"] for p in pages if p["near_blank"]]
    trailing_only = bool(near_blank) and near_blank == [total]
    mid_blank = [p for p in near_blank if p != total]

    fail = bool(mid_blank) or (bool(near_blank) and args.strict_trailing)

    if args.json:
        print(json.dumps(
            {
                "status": "FAIL" if fail else "PASS",
                "docx": str(args.docx),
                "page_count": total,
                "near_blank_pages": near_blank,
                "mid_document_blank_pages": mid_blank,
                "pages": pages,
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        name = args.docx.name
        if not near_blank:
            print(f"✅ {name}: {total} pages rendered, 0 near-blank.")
        else:
            print(f"{'❌' if fail else '🟡'} {name}: {total} pages, near-blank={near_blank}")
            if mid_blank:
                print(f"   ❌ mid-document blank pages (real defect): {mid_blank}")
            if trailing_only:
                tag = "❌ failing (strict-trailing)" if args.strict_trailing else "🟡 trailing blank (tolerated)"
                print(f"   {tag}: page {total}")
            for p in pages:
                if p["near_blank"]:
                    print(f"      page {p['page']}: nonwhite_ratio={p['nonwhite_ratio']}")

    return 2 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
