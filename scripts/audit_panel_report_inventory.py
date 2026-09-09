#!/usr/bin/env python3
"""Create a sanitized structural inventory for historical panel reports.

The script intentionally reports only aggregate counts and structural features.
It never emits source DOCX filenames, sample IDs, patient names, report dates, or
visible paragraph text from individual reports.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from lxml import etree


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DEFAULT_ROOT = Path("各癌种基因报告近年汇总")
DEFAULT_GOLDEN = Path(
    "panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx"
)


PRODUCT_PATTERNS = (
    r"子宫内膜癌分子分型29基因检测",
    r"结直肠癌\d+基因(?:\+msi)?(?:\+pd)?(?:\+hla)?",
    r"肺癌\d+基因(?:\+msi)?(?:\+pd)?(?:\+hla)?",
    r"胃癌\d+基因(?:\+msi)?(?:\+pd)?(?:\+hla)?",
    r"泛癌种\d+基因(?:\+msi)?(?:\+pd)?(?:\+hla)?",
    r"胆管、胆囊癌\d+基因(?:\+msi)?(?:\+pd)?",
    r"胰腺癌\d+基因(?:\+msi)?(?:\+pd)?",
    r"肝癌\d+基因(?:\+msi)?(?:\+pd)?",
    r"卵巢癌\d+基因(?:\+msi)?(?:\+pd)?",
    r"乳腺癌\d+基因(?:\+msi)?(?:\+pd)?",
    r"外阴癌\d+基因(?:\+msi)?(?:\+pd)?",
    r"食管癌\d+基因(?:\+msi)?(?:\+pd)?",
    r"黑色素瘤\d+基因(?:\+msi)?(?:\+pd)?",
    r"神经内分泌癌\d+基因(?:\+msi)?(?:\+pd)?",
    r"膀胱癌\d+基因(?:\+msi)?(?:\+pd)?",
    r"头颈癌\d+基因(?:\+msi)?(?:\+pd)?",
)


def normalize_product_text(path: Path) -> str:
    text = (
        path.stem.lower()
        .replace("＋", "+")
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
    )
    for pattern in PRODUCT_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return "<unparsed>"


def sanitized_product_key(path: Path, root: Path) -> str:
    product = normalize_product_text(path)
    if product != "<unparsed>":
        return product
    try:
        top_dir = path.relative_to(root).parts[0]
    except Exception:
        top_dir = "unknown"
    return f"<unparsed:{top_dir}>"


def read_docx_root(path: Path):
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read("word/document.xml"))


def paragraph_text(paragraph) -> str:
    return "".join(
        text_node.text or ""
        for text_node in paragraph.xpath(".//w:t", namespaces=NS)
    ).strip()


def table_shape(table) -> tuple[int, int]:
    rows = table.xpath("./w:tr", namespaces=NS)
    max_cols = 0
    for row in rows:
        max_cols = max(max_cols, len(row.xpath("./w:tc", namespaces=NS)))
    return len(rows), max_cols


def feature_map(text: str) -> dict[str, bool]:
    def has(pattern: str) -> bool:
        return bool(re.search(pattern, text, flags=re.IGNORECASE))

    return {
        "patient_info": has(r"基本信息|患者及样本信息"),
        "test_content": has(r"检测内容"),
        "qc": has(r"质控信息"),
        "variant_table": has(r"基因变异检测结果|重要基因变异"),
        "drug_tips": has(r"潜在获益|靶向药物|用药提示"),
        "guideline": has(r"NCCN|CSCO|已获批临床常规"),
        "tmb": has(r"肿瘤突变负荷|TMB"),
        "msi": has(r"微卫星不稳定性|MSI"),
        "pd_l1": has(r"PD-L1表达检测|PDL1表达检测"),
        "immune": has(r"免疫治疗|免疫药物|免疫相关"),
        "chemotherapy": has(r"临床常用化疗药物|化疗药物"),
        "molecular_typing": has(r"分子分型"),
        "hereditary_risk": has(r"遗传性肿瘤风险|遗传风险提示"),
        "gene_drug_interpretation": has(
            r"基因变异及相应|靶向用药提示解析|用药提示解析|重要基因变异解析"
        ),
        "pgx": has(r"药物代谢|基因多态性"),
    }


def schema_label(features: dict[str, bool]) -> str:
    if features.get("molecular_typing"):
        return "molecular_typing"
    if features.get("pd_l1") and features.get("tmb") and features.get("msi"):
        return "large_with_pd_tmb_msi"
    if features.get("pd_l1"):
        return "pd_l1_panel"
    if features.get("tmb") and features.get("msi") and features.get("immune"):
        return "tmb_msi_immune"
    if features.get("msi") and features.get("drug_tips"):
        return "msi_targeted"
    if features.get("drug_tips"):
        return "small_targeted"
    return "other"


def summarize_docx(path: Path) -> dict[str, Any]:
    root = read_docx_root(path)
    paragraphs = [
        paragraph_text(paragraph)
        for paragraph in root.xpath(".//w:p", namespaces=NS)
    ]
    visible_paragraphs = [text for text in paragraphs if text]
    tables = root.xpath(".//w:tbl", namespaces=NS)
    text = "\n".join(visible_paragraphs)
    features = feature_map(text)
    return {
        "paragraph_count": len(visible_paragraphs),
        "table_count": len(tables),
        "table_shapes": [table_shape(table) for table in tables],
        "features": features,
        "schema": schema_label(features),
    }


def summarize_counts(values: list[int]) -> dict[str, int | float]:
    if not values:
        return {"min": 0, "median": 0, "max": 0}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def collect_inventory(root: Path, golden: Path | None = None) -> dict[str, Any]:
    if not root.exists():
        raise FileNotFoundError(f"report root not found: {root}")

    real_files = [
        path
        for path in root.rglob("*")
        if path.is_file() and not path.name.startswith("._")
    ]
    metadata_files = [
        path for path in root.rglob("*") if path.is_file() and path.name.startswith("._")
    ]

    ext_counts = Counter(path.suffix.lower() or "<none>" for path in real_files)
    cancer_dir_counts = Counter(
        path.relative_to(root).parts[0] for path in real_files if path.relative_to(root).parts
    )

    product_docs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors: Counter[str] = Counter()
    for path in real_files:
        if path.suffix.lower() != ".docx":
            continue
        try:
            summary = summarize_docx(path)
        except Exception as exc:  # pragma: no cover - corpus-dependent guardrail
            errors[type(exc).__name__] += 1
            continue
        product_docs[sanitized_product_key(path, root)].append(summary)

    products = []
    for product, docs in sorted(
        product_docs.items(), key=lambda item: len(item[1]), reverse=True
    ):
        table_counts = [doc["table_count"] for doc in docs]
        paragraph_counts = [doc["paragraph_count"] for doc in docs]
        schema_counts = Counter(doc["schema"] for doc in docs)
        feature_counts: Counter[str] = Counter()
        for doc in docs:
            feature_counts.update(
                key for key, present in doc["features"].items() if present
            )
        common_threshold = max(1, round(len(docs) * 0.6))
        common_features = sorted(
            key for key, count in feature_counts.items() if count >= common_threshold
        )
        products.append(
            {
                "product": product,
                "docx_count": len(docs),
                "schema_counts": dict(schema_counts.most_common()),
                "table_count": summarize_counts(table_counts),
                "paragraph_count": summarize_counts(paragraph_counts),
                "common_features_60pct": common_features,
            }
        )

    payload: dict[str, Any] = {
        "privacy": {
            "sanitized": True,
            "no_source_filenames": True,
            "no_visible_text_samples": True,
        },
        "source_root_name": root.name,
        "file_counts": {
            "real_files": len(real_files),
            "mac_metadata_files": len(metadata_files),
            "extensions": dict(ext_counts.most_common()),
            "docx_readable": sum(item["docx_count"] for item in products),
            "docx_errors": dict(errors.most_common()),
        },
        "cancer_dir_counts": dict(cancer_dir_counts.most_common()),
        "products": products,
    }

    if golden and golden.exists():
        golden_summary = summarize_docx(golden)
        payload["golden_baseline"] = {
            "path_hint": "panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx",
            "table_count": golden_summary["table_count"],
            "paragraph_count": golden_summary["paragraph_count"],
            "features": sorted(
                key for key, present in golden_summary["features"].items() if present
            ),
        }

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanitized structural inventory for historical DOCX reports."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    payload = collect_inventory(args.root, args.golden)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
