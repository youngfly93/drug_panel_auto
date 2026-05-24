#!/usr/bin/env python3
"""Build a scrubbed golden-template seed from a local reviewed DOCX.

The reviewed report can contain patient data, reviewer comments, and tracked
changes. This tool is intentionally conservative:

- default output is under ``tmp/golden_template_seed``;
- patient/sample tokens are replaced from explicit ``--replace TOKEN=VALUE`` values;
- comments and common tracked-change wrappers are removed;
- a manifest records input/output hashes and residual checks;
- writing into a commit-able path requires ``--allow-commit-output``.

This is a seed builder, not a full table-loop template authoring tool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

from lxml import etree


DEFAULT_REPLACEMENTS: dict[str, str] = {}

DEFAULT_PROTECTED_TOKENS = tuple(DEFAULT_REPLACEMENTS)

XML_PART_PREFIXES = (
    "word/document.xml",
    "word/header",
    "word/footer",
    "word/footnotes.xml",
    "word/endnotes.xml",
    "word/comments",
    "word/textbox",
)

COMMENT_PARTS = {
    "word/comments.xml",
    "word/commentsExtended.xml",
    "word/commentsIds.xml",
    "word/people.xml",
}
DEBUG_TEXT_RE = re.compile(r"^\s*3{8,}\s*$")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_replacement(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("replacement must be TOKEN=VALUE")
    token, replacement = value.split("=", 1)
    token = token.strip()
    if not token:
        raise argparse.ArgumentTypeError("replacement token cannot be empty")
    return token, replacement


def is_safe_default_output(path: Path, project_root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return True
    return bool(rel.parts and rel.parts[0] in {"tmp", "output"})


def should_text_process(name: str) -> bool:
    if not name.endswith(".xml") and not name.endswith(".rels"):
        return False
    return name.startswith(XML_PART_PREFIXES) or name in {
        "[Content_Types].xml",
        "word/_rels/document.xml.rels",
    }


def remove_comment_rels(xml: str) -> str:
    xml = re.sub(
        r'<Relationship\b[^>]*(?:comments|commentsExtended|commentsIds|people)\.xml[^>]*/>',
        "",
        xml,
    )
    xml = re.sub(
        r'<Override\b[^>]*(?:comments|commentsExtended|commentsIds|people)\.xml[^>]*/>',
        "",
        xml,
    )
    return xml


def remove_review_markup(xml: str) -> str:
    xml = re.sub(r"<w:commentRangeStart\b[^>]*/>", "", xml)
    xml = re.sub(r"<w:commentRangeEnd\b[^>]*/>", "", xml)
    xml = re.sub(
        r"<w:r\b[^>]*>[^<]*(?:<w:rPr>.*?</w:rPr>)?<w:commentReference\b[^>]*/>.*?</w:r>",
        "",
        xml,
        flags=re.S,
    )
    xml = re.sub(r"</?w:ins\b[^>]*>", "", xml)
    xml = re.sub(r"<w:del\b.*?</w:del>", "", xml, flags=re.S)
    xml = re.sub(r"<w:moveFrom\b.*?</w:moveFrom>", "", xml, flags=re.S)
    xml = re.sub(r"</?w:moveTo\b[^>]*>", "", xml)
    return xml


def replace_tokens(xml: str, replacements: dict[str, str]) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for token, replacement in sorted(
        replacements.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        count = xml.count(token)
        if count:
            xml = xml.replace(token, replacement)
        counts[token] = count
    return xml, counts


def iter_visible_text_elements(root) -> list:
    return root.xpath(
        ".//*[local-name()='t' or local-name()='instrText']"
    )


def parse_xml_text(xml: str):
    parser = etree.XMLParser(resolve_entities=False, recover=True)
    return etree.fromstring(xml.encode("utf-8"), parser=parser)


def xml_visible_text(xml: str) -> str:
    try:
        root = parse_xml_text(xml)
    except Exception:
        return ""
    return "".join(str(el.text or "") for el in iter_visible_text_elements(root))


def build_text_index(elements: list) -> tuple[str, list[tuple[int, int, object]]]:
    parts: list[str] = []
    spans: list[tuple[int, int, object]] = []
    cursor = 0
    for element in elements:
        text = str(element.text or "")
        start = cursor
        cursor += len(text)
        parts.append(text)
        spans.append((start, cursor, element))
    return "".join(parts), spans


def locate_text_offset(
    spans: list[tuple[int, int, object]],
    position: int,
) -> tuple[int, int]:
    for index, (start, end, _element) in enumerate(spans):
        if start <= position < end:
            return index, position - start
    if spans and position == spans[-1][1]:
        start, end, _element = spans[-1]
        return len(spans) - 1, end - start
    raise ValueError(f"Text position out of range: {position}")


def locate_text_end_offset(
    spans: list[tuple[int, int, object]],
    position: int,
) -> tuple[int, int]:
    """Locate an exclusive end offset without consuming the next text node."""
    for index, (start, end, _element) in enumerate(spans):
        if start < position <= end:
            return index, position - start
    if position == 0 and spans:
        return 0, 0
    raise ValueError(f"Text end position out of range: {position}")


def preserve_space_if_needed(element) -> None:
    text = str(element.text or "")
    if text.startswith((" ", "\t", "\n")) or text.endswith((" ", "\t", "\n")):
        element.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def replace_token_across_text_elements(
    elements: list,
    token: str,
    replacement: str,
) -> int:
    """Replace a token even when Word split it across several ``w:t`` nodes."""
    if not token:
        return 0
    count = 0
    while True:
        full_text, spans = build_text_index(elements)
        start = full_text.find(token)
        if start < 0:
            break
        end = start + len(token)
        start_index, start_offset = locate_text_offset(spans, start)
        end_index, end_offset = locate_text_end_offset(spans, end)
        start_el = spans[start_index][2]
        end_el = spans[end_index][2]
        start_text = str(start_el.text or "")
        end_text = str(end_el.text or "")

        if start_index == end_index:
            start_el.text = (
                start_text[:start_offset] + replacement + start_text[end_offset:]
            )
            preserve_space_if_needed(start_el)
        else:
            start_el.text = (
                start_text[:start_offset] + replacement + end_text[end_offset:]
            )
            preserve_space_if_needed(start_el)
            for index in range(start_index + 1, end_index + 1):
                spans[index][2].text = ""
        count += 1
    return count


def replace_tokens_in_xml_text(
    xml: str,
    replacements: dict[str, str],
) -> tuple[str, dict[str, int]]:
    """Replace tokens in DOCX XML visible text, including split Word runs."""
    counts = {token: 0 for token in replacements}
    try:
        root = parse_xml_text(xml)
    except Exception:
        return replace_tokens(xml, replacements)

    elements = iter_visible_text_elements(root)
    if not elements:
        return replace_tokens(xml, replacements)

    for token, replacement in sorted(
        replacements.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        counts[token] = replace_token_across_text_elements(
            elements,
            token,
            replacement,
        )

    return (
        etree.tostring(root, encoding="unicode", xml_declaration=False),
        counts,
    )


def remove_debug_text_markers(xml: str) -> tuple[str, int]:
    """Remove obvious non-report debug markers copied from reviewed sources."""
    try:
        root = parse_xml_text(xml)
    except Exception:
        return xml, 0
    count = 0
    for element in iter_visible_text_elements(root):
        if DEBUG_TEXT_RE.match(str(element.text or "")):
            element.text = ""
            count += 1
    if not count:
        return xml, 0
    return etree.tostring(root, encoding="unicode", xml_declaration=False), count


def count_tokens_in_zip(path: Path, tokens: Iterable[str]) -> dict[str, int]:
    counts = {token: 0 for token in tokens}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not should_text_process(name):
                continue
            try:
                text = zf.read(name).decode("utf-8", errors="ignore")
            except Exception:
                continue
            visible_text = xml_visible_text(text) if name.endswith(".xml") else ""
            count_text = visible_text or text
            for token in tokens:
                counts[token] += count_text.count(token)
    return counts


def build_seed(
    source: Path,
    output: Path,
    *,
    replacements: dict[str, str],
    protected_tokens: tuple[str, ...],
    allow_commit_output: bool,
    allow_residual: bool,
    project_root: Path,
) -> dict:
    if not source.exists():
        raise FileNotFoundError(source)
    if source.suffix.lower() != ".docx":
        raise ValueError(f"source must be .docx: {source}")
    if output.suffix.lower() != ".docx":
        raise ValueError(f"output must be .docx: {output}")
    if not allow_commit_output and not is_safe_default_output(output, project_root):
        raise ValueError(
            "Refusing to write a scrubbed seed outside tmp/ or output/ without "
            "--allow-commit-output"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    replacement_counts = {token: 0 for token in replacements}
    removed_parts: list[str] = []
    removed_debug_markers = 0

    with tempfile.TemporaryDirectory(prefix="golden_seed_") as tmpdir:
        tmp_path = Path(tmpdir) / "seed.docx"
        with zipfile.ZipFile(source) as zin, zipfile.ZipFile(
            tmp_path, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                name = item.filename
                if name in COMMENT_PARTS:
                    removed_parts.append(name)
                    continue
                data = zin.read(item)
                if should_text_process(name):
                    text = data.decode("utf-8", errors="ignore")
                    text = remove_comment_rels(text)
                    text = remove_review_markup(text)
                    if name.endswith(".xml"):
                        text, counts = replace_tokens_in_xml_text(text, replacements)
                        text, debug_count = remove_debug_text_markers(text)
                        removed_debug_markers += debug_count
                    else:
                        text, counts = replace_tokens(text, replacements)
                    for token, count in counts.items():
                        replacement_counts[token] += count
                    data = text.encode("utf-8")
                zout.writestr(item, data)
        shutil.copyfile(tmp_path, output)

    residual_counts = count_tokens_in_zip(output, protected_tokens)
    has_residual = any(count > 0 for count in residual_counts.values())
    if has_residual and not allow_residual:
        success = False
    else:
        success = True

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "output": str(output),
        "source_sha256": sha256_file(source),
        "output_sha256": sha256_file(output),
        "replacement_counts": replacement_counts,
        "protected_token_residual_counts": residual_counts,
        "removed_parts": removed_parts,
        "removed_debug_markers": removed_debug_markers,
        "success": success,
        "notes": [
            "This seed has scalar patient/sample tokens scrubbed.",
            "Loop table authoring still requires manual/template-tool work before production use.",
        ],
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest["manifest"] = str(manifest_path)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Local reviewed/golden DOCX")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tmp/golden_template_seed/crc_358_msi_golden_seed.docx"),
        help="Scrubbed output DOCX path",
    )
    parser.add_argument(
        "--replace",
        action="append",
        default=[],
        type=parse_replacement,
        metavar="TOKEN=VALUE",
        help="Additional token replacement. Can be repeated.",
    )
    parser.add_argument(
        "--protected-token",
        action="append",
        default=[],
        help="Additional token that must not remain in the output.",
    )
    parser.add_argument(
        "--allow-commit-output",
        action="store_true",
        help="Allow writing output outside tmp/ or output/.",
    )
    parser.add_argument(
        "--allow-residual",
        action="store_true",
        help="Do not exit non-zero when protected tokens remain.",
    )
    parser.add_argument(
        "--allow-empty-replacements",
        action="store_true",
        help="Allow running without any --replace values. Intended only for debugging.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = Path.cwd().resolve()
    replacements = dict(DEFAULT_REPLACEMENTS)
    replacements.update(dict(args.replace))
    if not replacements and not args.allow_empty_replacements:
        parser.error(
            "At least one --replace TOKEN=VALUE is required so patient/sample "
            "tokens are scrubbed explicitly."
        )
    protected_tokens = tuple(
        dict.fromkeys(
            [
                *DEFAULT_PROTECTED_TOKENS,
                *replacements.keys(),
                *args.protected_token,
            ]
        )
    )
    manifest = build_seed(
        args.source.resolve(),
        args.output,
        replacements=replacements,
        protected_tokens=protected_tokens,
        allow_commit_output=args.allow_commit_output,
        allow_residual=args.allow_residual,
        project_root=project_root,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
