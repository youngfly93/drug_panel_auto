#!/usr/bin/env python3
"""Build a local scrubbed CRC35+MSI seed from a selected reviewed DOCX.

This script reads a local ignored candidate manifest or an explicit source
path, extracts known scalar patient/sample tokens, and writes the scrubbed seed
under tmp/. It does not print extracted PHI values.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_golden_template_seed import build_seed  # noqa: E402


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DEFAULT_MANIFEST = Path("tmp/panel_inventory/crc_small_candidate_manifest.local.json")
DEFAULT_OUTPUT = Path("tmp/golden_template_seed/crc_35_msi_seed.docx")


def text(element) -> str:
    return "".join(
        node.text or "" for node in element.xpath(".//w:t", namespaces=NS)
    ).strip()


def load_source_from_manifest(manifest: Path, product: str, selection: str) -> Path:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    try:
        selected = data["products"][product]["selected"]
    except KeyError as exc:
        raise KeyError(f"product not found in local manifest: {product}") from exc
    for item in selected:
        if item.get("selection") == selection:
            return Path(item["source_path"])
    raise KeyError(f"selection not found for {product}: {selection}")


def read_document_root(path: Path):
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read("word/document.xml"))


def extract_replacements(root) -> dict[str, str]:
    replacements: dict[str, str] = {}
    tables = root.xpath(".//w:tbl", namespaces=NS)
    if not tables:
        raise ValueError("source DOCX has no tables")

    rows = tables[0].xpath("./w:tr", namespaces=NS)
    cell_texts = [
        [text(cell) for cell in row.xpath("./w:tc", namespaces=NS)]
        for row in rows
    ]
    position_vars = {
        (0, 1): "{{ patient_name }}",
        (0, 3): "{{ gender }}",
        (1, 1): "{{ age }}",
        (1, 3): "{{ sample_type }}",
        (2, 1): "{{ clinical_diagnosis }}",
    }
    for (row, col), placeholder in position_vars.items():
        try:
            value = cell_texts[row][col].strip()
        except IndexError:
            continue
        if value:
            replacements[value] = placeholder

    visible = "\n".join(
        text(element)
        for element in root.xpath(".//w:p|.//w:tc", namespaces=NS)
        if text(element)
    )
    report_numbers = sorted(
        set(re.findall(r"(?i)MLJY[-_ ]?[A-Z]{1,3}\d{5,}", visible))
    )
    sample_ids = sorted(
        set(re.findall(r"(?i)(?:LZ|LW|LB|LC|LG|LM)\d{5,}", visible))
    )
    if report_numbers:
        replacements[report_numbers[0]] = "{{ report_number }}"
    if sample_ids:
        replacements[sample_ids[0]] = "{{ sample_id }}"

    for paragraph in [text(p) for p in root.xpath(".//w:p", namespaces=NS)]:
        if "报告日期" not in paragraph and "送检日期" not in paragraph:
            continue
        for date in re.findall(
            r"\d{4}[./-]\d{1,2}[./-]\d{1,2}|\d{4}年\d{1,2}月\d{1,2}日",
            paragraph,
        ):
            replacements[date] = "{{ report_date }}"

    if len(replacements) < 5:
        raise ValueError("too few replacements were extracted from CRC35 seed source")
    return replacements


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--product", default="结直肠癌35基因+msi")
    parser.add_argument("--selection", default="median")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    source = args.source or load_source_from_manifest(
        args.manifest,
        args.product,
        args.selection,
    )
    root = read_document_root(source)
    replacements = extract_replacements(root)
    result = build_seed(
        source=source,
        output=args.output,
        replacements=replacements,
        protected_tokens=tuple(replacements.keys()),
        allow_commit_output=False,
        allow_residual=False,
        project_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "output": result["output"],
                "manifest": result["manifest"],
                "success": result["success"],
                "replacement_count": len(replacements),
                "residual_total": sum(
                    result["protected_token_residual_counts"].values()
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
