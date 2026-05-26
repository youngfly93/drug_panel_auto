#!/usr/bin/env python3
"""Replace a DOCX body block with a single marker paragraph.

This is used during golden-template authoring to remove reviewed-report
case-specific narrative sections while preserving the surrounding layout.
The script does not print removed text.
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def visible_text(element) -> str:
    return "".join(
        text.text or "" for text in element.xpath(".//w:t", namespaces=NS)
    ).strip()


def make_marker_paragraph(marker: str):
    paragraph = etree.Element(f"{{{W_NS}}}p")
    run = etree.SubElement(paragraph, f"{{{W_NS}}}r")
    text = etree.SubElement(run, f"{{{W_NS}}}t")
    text.text = marker
    return paragraph


def replace_block(
    source: Path,
    output: Path,
    *,
    start_heading: str,
    end_heading: str,
    marker: str,
) -> dict[str, int | str]:
    if source.suffix.lower() != ".docx":
        raise ValueError(f"source must be .docx: {source}")
    if output.suffix.lower() != ".docx":
        raise ValueError(f"output must be .docx: {output}")

    with zipfile.ZipFile(source) as archive:
        document_xml = archive.read("word/document.xml")

    parser = etree.XMLParser(resolve_entities=False, recover=True)
    root = etree.fromstring(document_xml, parser=parser)
    body = root.find("w:body", namespaces=NS)
    if body is None:
        raise ValueError("word/document.xml has no body")

    children = list(body)
    start_idx = None
    end_idx = None
    for idx, child in enumerate(children):
        text = visible_text(child)
        if start_idx is None and start_heading in text:
            start_idx = idx
            continue
        if start_idx is not None and end_heading in text:
            end_idx = idx
            break

    if start_idx is None:
        raise ValueError(f"start heading not found: {start_heading!r}")
    if end_idx is None:
        raise ValueError(f"end heading not found after start: {end_heading!r}")
    if end_idx <= start_idx:
        raise ValueError("end heading must appear after start heading")

    remove_start = start_idx + 1
    remove_end = end_idx
    removed_count = remove_end - remove_start
    for child in children[remove_start:remove_end]:
        body.remove(child)

    start_element = body[start_idx]
    start_element.addnext(make_marker_paragraph(marker))

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        tmp_path = Path(tmp.name)

    try:
        with zipfile.ZipFile(source) as src, zipfile.ZipFile(
            tmp_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "word/document.xml":
                    data = etree.tostring(
                        root,
                        xml_declaration=True,
                        encoding="UTF-8",
                        standalone=True,
                    )
                dst.writestr(item, data)
        shutil.copyfile(tmp_path, output)
    finally:
        tmp_path.unlink(missing_ok=True)

    return {
        "source": str(source),
        "output": str(output),
        "removed_body_elements": removed_count,
        "marker": marker,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--start-heading", required=True)
    parser.add_argument("--end-heading", required=True)
    parser.add_argument("--marker", default="__PART3_MARKER__")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = replace_block(
        args.source,
        args.output,
        start_heading=args.start_heading,
        end_heading=args.end_heading,
        marker=args.marker,
    )
    print(
        "removed_body_elements={removed_body_elements} marker={marker}".format(
            **result
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
