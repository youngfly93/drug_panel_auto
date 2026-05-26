#!/usr/bin/env python3
"""Select sanitized CRC small MSI candidate reports for pilot migration.

The committed summary is aggregate-only. The optional local manifest contains
source paths and heading text for developer use, so it must stay under tmp/.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_panel_report_inventory import (
    normalize_product_text,
    summarize_docx,
)


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DEFAULT_ROOT = Path("各癌种基因报告近年汇总")
DEFAULT_PRODUCTS = ("结直肠癌35基因+msi", "结直肠癌20基因+msi")


def visible_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    paragraphs: list[str] = []
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        text = "".join(
            node.text or ""
            for node in paragraph.xpath(".//w:t", namespaces=NS)
        ).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def heading_like_text(paragraphs: list[str], *, limit: int = 80) -> list[str]:
    patterns = [
        r"^第[一二三四五六七八九十]+部分",
        r"^\d+(?:\.\d+)*[、.．]?\s*[^。]{2,40}$",
        r"检测结果",
        r"检测内容",
        r"患者及样本信息",
        r"检测结果说明",
        r"阅读说明",
        r"参考文献",
    ]
    headings: list[str] = []
    for text in paragraphs:
        compact = re.sub(r"\s+", "", text)
        if len(compact) > 60:
            continue
        if any(re.search(pattern, compact) for pattern in patterns):
            if compact not in headings:
                headings.append(compact)
        if len(headings) >= limit:
            break
    return headings


def collect_product_docs(root: Path, products: set[str]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for path in root.rglob("*.docx"):
        if path.name.startswith("._"):
            continue
        product = normalize_product_text(path)
        if product not in products:
            continue
        try:
            summary = summarize_docx(path)
        except Exception:
            continue
        docs.append({"source_path": str(path.resolve()), "product": product, **summary})
    return docs


def select_representatives(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not docs:
        return []
    table_counts = [int(doc["table_count"]) for doc in docs]
    median_tables = statistics.median(table_counts)
    ranked = sorted(
        docs,
        key=lambda doc: (
            abs(int(doc["table_count"]) - median_tables),
            int(doc["paragraph_count"]),
        ),
    )
    low = sorted(docs, key=lambda doc: (int(doc["table_count"]), int(doc["paragraph_count"])))[0]
    high = sorted(
        docs,
        key=lambda doc: (-int(doc["table_count"]), -int(doc["paragraph_count"])),
    )[0]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, doc in (("median", ranked[0]), ("low_tables", low), ("high_tables", high)):
        key = doc["source_path"]
        if key in seen:
            continue
        seen.add(key)
        selected.append({"selection": label, **doc})
    return selected


def summarize_product(product: str, docs: list[dict[str, Any]]) -> dict[str, Any]:
    table_counts = [int(doc["table_count"]) for doc in docs]
    paragraph_counts = [int(doc["paragraph_count"]) for doc in docs]
    schema_counts: dict[str, int] = {}
    feature_counts: dict[str, int] = {}
    for doc in docs:
        schema_counts[str(doc["schema"])] = schema_counts.get(str(doc["schema"]), 0) + 1
        for key, present in (doc.get("features") or {}).items():
            if present:
                feature_counts[key] = feature_counts.get(key, 0) + 1
    threshold = max(1, round(len(docs) * 0.6))
    return {
        "product": product,
        "docx_count": len(docs),
        "schema_counts": dict(
            sorted(schema_counts.items(), key=lambda item: item[1], reverse=True)
        ),
        "table_count": {
            "min": min(table_counts) if table_counts else 0,
            "median": statistics.median(table_counts) if table_counts else 0,
            "max": max(table_counts) if table_counts else 0,
        },
        "paragraph_count": {
            "min": min(paragraph_counts) if paragraph_counts else 0,
            "median": statistics.median(paragraph_counts) if paragraph_counts else 0,
            "max": max(paragraph_counts) if paragraph_counts else 0,
        },
        "common_features_60pct": sorted(
            key for key, count in feature_counts.items() if count >= threshold
        ),
    }


def build_payload(root: Path, products: tuple[str, ...]) -> tuple[dict[str, Any], dict[str, Any]]:
    product_set = set(products)
    docs = collect_product_docs(root, product_set)
    summary_products: list[dict[str, Any]] = []
    local_products: dict[str, Any] = {}
    for product in products:
        product_docs = [doc for doc in docs if doc["product"] == product]
        selected = select_representatives(product_docs)
        summary_products.append(summarize_product(product, product_docs))
        local_products[product] = {
            "docx_count": len(product_docs),
            "selected": [
                {
                    "selection": item["selection"],
                    "source_path": item["source_path"],
                    "table_count": item["table_count"],
                    "paragraph_count": item["paragraph_count"],
                    "schema": item["schema"],
                    "features": [
                        key for key, present in (item.get("features") or {}).items() if present
                    ],
                    "heading_like_text_local_only": heading_like_text(
                        visible_paragraphs(Path(item["source_path"]))
                    ),
                }
                for item in selected
            ],
        }
    summary = {
        "privacy": {
            "sanitized": True,
            "no_source_filenames": True,
            "no_source_paths": True,
            "no_visible_text_samples": True,
        },
        "source_root_name": root.name,
        "products": summary_products,
        "decision": {
            "first_panel": "crc_35_msi",
            "crc20_shared_template": False,
            "reason": (
                "CRC35+MSI and CRC20+MSI share the MSI/targeted concept but "
                "have materially different table counts and section numbering."
            ),
        },
    }
    local = {
        "privacy": (
            "local ignored manifest; contains source paths and heading text; "
            "do not commit"
        ),
        "source_root": str(root.resolve()),
        "products": local_products,
    }
    return summary, local


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--product",
        action="append",
        default=[],
        help="Product key to include. Defaults to CRC35+MSI and CRC20+MSI.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("tmp/panel_inventory/crc_small_candidate_summary.json"),
    )
    parser.add_argument(
        "--local-manifest-output",
        type=Path,
        default=Path("tmp/panel_inventory/crc_small_candidate_manifest.local.json"),
    )
    args = parser.parse_args()

    products = tuple(args.product or DEFAULT_PRODUCTS)
    summary, local = build_payload(args.root, products)
    write_json(args.summary_output, summary)
    write_json(args.local_manifest_output, local)
    print(
        json.dumps(
            {
                "summary_output": str(args.summary_output),
                "local_manifest_output": str(args.local_manifest_output),
                "products": [
                    {
                        "product": item["product"],
                        "docx_count": item["docx_count"],
                        "median_tables": item["table_count"]["median"],
                    }
                    for item in summary["products"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
