#!/usr/bin/env python3
"""Two-case zero-leak test for a variableized template.

The #1 hardcoding failure mode is a template that secretly carries case-A data:
it renders fine for case A (the one it was variableized from) but leaks A's
name / sample id / variant into **every** report. This test catches that by
checking a report generated from a *different* case (case B):

- every ``--seed-token`` (a case-A literal) must be **absent**;
- every ``--expect`` (a case-B literal) must be **present**.

You provide the already-generated case-B report; this script does not run the
pipeline (keeps it fast and dependency-light). Generate case B first, e.g. via
``scripts/diff_golden_report.py`` or the web form, then point ``--other`` at it.

Usage::

    python scripts/two_case_leak_test.py \
        --other tmp/case_b/report.docx \
        --seed-token 张三 --seed-token NGS2024001 --seed-token "c.34G>A" \
        --expect 李四 --expect NGS2024099

Exit non-zero if any seed-token leaked or any expected token is missing.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

from lxml import etree

SCAN_PART_PREFIXES = (
    "word/document.xml",
    "word/header",
    "word/footer",
    "word/footnotes.xml",
    "word/endnotes.xml",
)


def docx_visible_text(path: Path) -> str:
    """Concatenate all visible text, run-split tolerant.

    Returns a single blob with paragraphs newline-joined PLUS a separator-free
    concatenation appended, so substring checks catch tokens regardless of how
    Word split runs within a paragraph.
    """
    parser = etree.XMLParser(resolve_entities=False, recover=True)
    para_texts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith(SCAN_PART_PREFIXES) or not name.endswith(".xml"):
                continue
            try:
                root = etree.fromstring(zf.read(name), parser=parser)
            except Exception:
                continue
            for para in root.iter("{*}p"):
                joined = "".join(str(t.text or "") for t in para.iter("{*}t"))
                if joined.strip():
                    para_texts.append(joined)
    newline_joined = "\n".join(para_texts)
    no_sep = "".join(para_texts)
    return newline_joined + "\n" + no_sep


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--other", required=True, type=Path, help="Case-B generated report .docx")
    parser.add_argument(
        "--seed-token",
        action="append",
        default=[],
        required=True,
        help="Case-A literal that must be ABSENT from the case-B report. Repeatable.",
    )
    parser.add_argument(
        "--expect",
        action="append",
        default=[],
        help="Case-B literal that must be PRESENT in the case-B report. Repeatable.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = args.other
    if not path.exists():
        print(f"❌ not found: {path}", file=sys.stderr)
        return 2
    if path.suffix.lower() != ".docx":
        print(f"❌ not a .docx: {path}", file=sys.stderr)
        return 2

    text = docx_visible_text(path)

    leaks = [tok for tok in args.seed_token if tok and tok in text]
    missing = [tok for tok in args.expect if tok and tok not in text]

    name = path.name
    print(f"two-case leak test: {name}")
    print(f"  seed-tokens (must be absent): {len(args.seed_token)} checked")
    for tok in args.seed_token:
        mark = "❌ LEAKED" if tok in text else "✅ absent"
        print(f"    {mark}  {tok!r}")
    if args.expect:
        print(f"  expect-tokens (must be present): {len(args.expect)} checked")
        for tok in args.expect:
            mark = "✅ present" if tok in text else "❌ MISSING"
            print(f"    {mark}  {tok!r}")

    if leaks:
        print(f"\n❌ FAIL: {len(leaks)} case-A token(s) leaked into case-B report → template carries hardcoded case-A data.")
    if missing:
        print(f"\n❌ FAIL: {len(missing)} expected case-B token(s) missing → report did not render case-B values.")
    if not leaks and not missing:
        print("\n✅ PASS: zero leak, all expected tokens present.")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
