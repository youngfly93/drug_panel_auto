#!/usr/bin/env python3
"""Scan a variableized template .docx for residual per-case hardcoded literals.

A properly variableized golden template must contain **zero** patient/case
literals: every per-case value should be a ``{{ variable }}`` or live inside a
``{%tr %}`` loop. This scanner reads the template's visible text and flags
left-over literals that look like real case data.

Two tiers (mirrors the project's bio-ai-clean HARD/SOFT discipline):

- **HARD** (exit non-zero): variant notation (cHGVS ``c.34G>A`` / pHGVS
  ``p.G12C``) and any explicit ``--token`` (a known patient name / sample id).
  These are unambiguous patient data — a hit means the template was not fully
  variableized.
- **SOFT** (reported, exit 0 unless ``--strict``): decimal percentages that look
  like allele frequency / abundance (``46.29%``) and concrete dates. These can
  be legitimate static text (clinical thresholds, guideline dates), so they are
  flagged for human review rather than auto-failing.

Usage::

    python scripts/scan_hardcoded_literals.py panels/<panel>/templates/<tpl>.docx
    python scripts/scan_hardcoded_literals.py <tpl>.docx --token 张三 --token NGS2024001
    python scripts/scan_hardcoded_literals.py <tpl>.docx --strict --json

Read-only: never modifies the input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from lxml import etree

# Parts whose visible text we scan. document.xml is the body; headers/footers
# can also carry copied case data.
SCAN_PART_PREFIXES = (
    "word/document.xml",
    "word/header",
    "word/footer",
    "word/footnotes.xml",
    "word/endnotes.xml",
)

# --- HARD patterns: unambiguous patient variant data / template junk -----------
# cHGVS: position + a mutation operator (>, del/ins/dup). Requiring the operator
# keeps this from matching a bare jinja placeholder like ``{{ c_hgvs }}``.
RE_CHGVS = re.compile(
    r"c\.\d+(?:[_+\-]\d+)?(?:[ACGTN]>[ACGTN]|del\w*|ins\w*|dup\w*)"
)
# pHGVS: ``p.`` + 1-3 amino-acid letters + a residue number (p.G12C, p.Gly12Ser).
RE_PHGVS = re.compile(r"p\.[A-Z][a-zA-Z]{0,2}\d+")
# Debug fill markers (``33333333…``) copied from upstream reviewed reports. They
# are not content, render as a near-blank page under LibreOffice, and must never
# survive into a template. (Same pattern build_golden_template_seed.py strips.)
RE_DEBUG = re.compile(r"3{8,}")

# --- SOFT patterns: review manually (may be legitimate static text) ------------
# Allele-frequency / abundance: a decimal percentage (46.29%). Integer
# percentages (50%, 1%) are usually clinical thresholds, so we require a decimal.
RE_AF_PCT = re.compile(r"\d{1,3}\.\d{1,2}\s*%")
# Concrete dates: 2024-03-15, 2024/03/15, 2024年3月15日.
RE_DATE = re.compile(r"\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}")


@dataclass
class Match:
    tier: str          # "HARD" | "SOFT"
    kind: str          # pattern name
    value: str         # the matched literal
    part: str          # docx part the hit came from
    context: str       # surrounding paragraph text (trimmed)


@dataclass
class ScanResult:
    path: str
    matches: list[Match] = field(default_factory=list)

    @property
    def hard(self) -> list[Match]:
        return [m for m in self.matches if m.tier == "HARD"]

    @property
    def soft(self) -> list[Match]:
        return [m for m in self.matches if m.tier == "SOFT"]


def _paragraph_texts(xml: bytes) -> list[str]:
    """Return visible text per paragraph, joining runs split within a paragraph.

    Word frequently splits a token like ``c.34G>A`` across several ``w:r``/``w:t``
    nodes inside one paragraph. Joining a paragraph's ``w:t`` nodes reconstructs
    the literal without creating cross-paragraph false joins.
    """
    parser = etree.XMLParser(resolve_entities=False, recover=True)
    try:
        root = etree.fromstring(xml, parser=parser)
    except Exception:
        return []
    paragraphs: list[str] = []
    for para in root.iter("{*}p"):
        texts = [str(t.text or "") for t in para.iter("{*}t")]
        joined = "".join(texts)
        if joined.strip():
            paragraphs.append(joined)
    return paragraphs


def _trim(text: str, value: str, *, width: int = 40) -> str:
    idx = text.find(value)
    if idx < 0:
        return text[:width].strip()
    start = max(0, idx - width // 2)
    end = min(len(text), idx + len(value) + width // 2)
    snippet = text[start:end].strip()
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")


def _scan_text(part: str, paragraphs: Iterable[str], tokens: list[str]) -> list[Match]:
    matches: list[Match] = []
    for para in paragraphs:
        for kind, regex in (("cHGVS", RE_CHGVS), ("pHGVS", RE_PHGVS), ("debug_marker", RE_DEBUG)):
            for hit in regex.findall(para):
                matches.append(Match("HARD", kind, hit, part, _trim(para, hit)))
        for tok in tokens:
            if tok and tok in para:
                matches.append(Match("HARD", "token", tok, part, _trim(para, tok)))
        for kind, regex in (("af_pct", RE_AF_PCT), ("date", RE_DATE)):
            for hit in regex.findall(para):
                matches.append(Match("SOFT", kind, hit.strip(), part, _trim(para, hit.strip())))
    return matches


def scan_docx(path: Path, tokens: list[str]) -> ScanResult:
    result = ScanResult(path=str(path))
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith(SCAN_PART_PREFIXES) or not name.endswith(".xml"):
                continue
            paragraphs = _paragraph_texts(zf.read(name))
            result.matches.extend(_scan_text(name, paragraphs, tokens))
    return result


def _print_report(result: ScanResult, *, strict: bool) -> None:
    name = Path(result.path).name
    if not result.matches:
        print(f"✅ {name}: 0 hardcoded literals")
        return
    print(f"⚠️  {name}: {len(result.hard)} HARD, {len(result.soft)} SOFT")
    for m in result.hard:
        print(f"   ❌ HARD [{m.kind}] {m.value!r}  ({m.part})  …{m.context}")
    soft_label = "❌" if strict else "🟡"
    for m in result.soft:
        print(f"   {soft_label} SOFT [{m.kind}] {m.value!r}  ({m.part})  …{m.context}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", type=Path, help="Template .docx file(s) to scan")
    parser.add_argument(
        "--token",
        action="append",
        default=[],
        help="Explicit patient string that must NOT appear (name/sample id). Repeatable. Treated as HARD.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also fail on SOFT hits (af%%/dates), not only HARD.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results: list[ScanResult] = []
    for path in args.paths:
        if not path.exists():
            print(f"❌ not found: {path}", file=sys.stderr)
            return 2
        if path.suffix.lower() != ".docx":
            print(f"❌ not a .docx: {path}", file=sys.stderr)
            return 2
        results.append(scan_docx(path, args.token))

    failed = False
    if args.json:
        payload = [
            {
                "path": r.path,
                "hard": [vars(m) for m in r.hard],
                "soft": [vars(m) for m in r.soft],
            }
            for r in results
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    for result in results:
        if not args.json:
            _print_report(result, strict=args.strict)
        if result.hard or (args.strict and result.soft):
            failed = True

    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
