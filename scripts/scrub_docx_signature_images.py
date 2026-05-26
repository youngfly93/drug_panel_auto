#!/usr/bin/env python3
"""Replace small handwritten-signature-like DOCX media with blank placeholders."""

from __future__ import annotations

import argparse
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from PIL import Image


SIGNATURE_SUFFIXES = {".png", ".jpg", ".jpeg"}
CORE_PROPS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>CRC35+MSI pilot template</dc:title>
  <dc:creator>ReportGen</dc:creator>
  <cp:lastModifiedBy>ReportGen</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-05-26T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-05-26T00:00:00Z</dcterms:modified>
</cp:coreProperties>
"""
APP_PROPS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>ReportGen</Application>
  <DocSecurity>0</DocSecurity>
  <ScaleCrop>false</ScaleCrop>
  <Company></Company>
  <LinksUpToDate>false</LinksUpToDate>
  <SharedDoc>false</SharedDoc>
  <HyperlinksChanged>false</HyperlinksChanged>
  <AppVersion>1.0</AppVersion>
</Properties>
"""
CUSTOM_PROPS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"/>
"""


def is_signature_like(width: int, height: int) -> bool:
    if width <= 0 or height <= 0:
        return False
    ratio = width / height
    return width <= 320 and height <= 140 and ratio >= 1.3


def blank_image_bytes(width: int, height: int, suffix: str) -> bytes:
    buffer = io.BytesIO()
    if suffix == ".png":
        image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        image.save(buffer, format="PNG")
    else:
        image = Image.new("RGB", (width, height), (255, 255, 255))
        image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def scrub_docx(source: Path, output: Path) -> dict:
    if source.suffix.lower() != ".docx":
        raise ValueError(f"source must be .docx: {source}")
    if output.suffix.lower() != ".docx":
        raise ValueError(f"output must be .docx: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    replaced: list[dict] = []
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        tmp_path = Path(tmp.name)

    try:
        with zipfile.ZipFile(source) as src, zipfile.ZipFile(
            tmp_path, "w", zipfile.ZIP_DEFLATED
        ) as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                name = item.filename
                suffix = Path(name).suffix.lower()
                if name == "docProps/core.xml":
                    data = CORE_PROPS.encode("utf-8")
                elif name == "docProps/app.xml":
                    data = APP_PROPS.encode("utf-8")
                elif name == "docProps/custom.xml":
                    data = CUSTOM_PROPS.encode("utf-8")
                if name.startswith("word/media/") and suffix in SIGNATURE_SUFFIXES:
                    try:
                        image = Image.open(io.BytesIO(data))
                        width, height = image.size
                    except Exception:
                        width = height = 0
                    if is_signature_like(width, height):
                        data = blank_image_bytes(width, height, suffix)
                        replaced.append(
                            {
                                "name": Path(name).name,
                                "width": width,
                                "height": height,
                            }
                        )
                dst.writestr(item, data)
        shutil.copyfile(tmp_path, output)
    finally:
        tmp_path.unlink(missing_ok=True)

    return {
        "source": str(source),
        "output": str(output),
        "replaced_count": len(replaced),
        "replaced": replaced,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = scrub_docx(args.source, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
