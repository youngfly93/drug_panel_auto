#!/usr/bin/env python3
"""Build the CRC301 golden-template v1 candidate from v0.

This keeps v0 immutable and applies only the reviewed layout delta needed for
the next pilot: a detector/reviewer/date signature block before Part 3.
"""

from __future__ import annotations

import argparse
import copy
import os
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "panels" / "crc_301_msi" / "templates"
SOURCE = TEMPLATE_DIR / "crc_301_msi_golden_template_v0.docx"
OUTPUT = TEMPLATE_DIR / "crc_301_msi_golden_template_v1.docx"
SIGNATURE_SOURCE = (
    ROOT
    / "panels"
    / "crc_358_msi"
    / "templates"
    / "crc_358_msi_golden_template_v0.docx"
)

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def paragraph_text(paragraph: etree._Element) -> str:
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))


def first_paragraph(root: etree._Element, needle: str) -> etree._Element:
    for paragraph in root.xpath(".//w:body/w:p", namespaces=NS):
        if needle in paragraph_text(paragraph):
            return paragraph
    raise ValueError(f"paragraph not found: {needle}")


def signature_paragraph() -> etree._Element:
    with ZipFile(SIGNATURE_SOURCE, "r") as zf:
        root = etree.fromstring(zf.read("word/document.xml"))
    paragraph = first_paragraph(root, "检测者：")
    text = paragraph_text(paragraph)
    if "审核者" not in text or "report_date_dot" not in text:
        raise ValueError("CRC358 signature paragraph shape is unexpected")
    return copy.deepcopy(paragraph)


def blank_paragraph() -> etree._Element:
    return etree.Element(f"{{{NS['w']}}}p")


def build(source: Path = SOURCE, output: Path = OUTPUT) -> Path:
    with ZipFile(source, "r") as zin:
        document_info = zin.getinfo("word/document.xml")
        document_xml = zin.read("word/document.xml")
        entries = [
            (info, zin.read(info.filename))
            for info in zin.infolist()
            if info.filename != "word/document.xml"
        ]

    root = etree.fromstring(document_xml)
    target = first_paragraph(root, "5. 检测结果说明")

    previous = target.getprevious()
    if previous is not None and "检测者" in paragraph_text(previous):
        patched_xml = document_xml
    else:
        for item in [
            blank_paragraph(),
            signature_paragraph(),
            blank_paragraph(),
            blank_paragraph(),
        ]:
            target.addprevious(item)
        patched_xml = etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone="yes",
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(suffix=".docx", dir=str(output.parent))
    os.close(fd)
    try:
        with ZipFile(tmp_name, "w", compression=ZIP_DEFLATED) as zout:
            zout.writestr(document_info, patched_xml)
            for info, data in entries:
                zout.writestr(info, data)
        shutil.move(tmp_name, output)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(build(args.source, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
