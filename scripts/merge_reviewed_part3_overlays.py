#!/usr/bin/env python3
"""Merge a base reviewed Part 3 overlay with an additive draft overlay."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import yaml


DEFAULT_BASE = Path("panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml")
DEFAULT_ADDITIVE = Path("tmp/knowledge_buildout/reviewed_part3_knowledge_machine_preapproved_v0.1.yaml")
DEFAULT_OUTPUT = Path("tmp/knowledge_buildout/reviewed_part3_knowledge_merged_machine_preapproved_v0.1.yaml")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def gene_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("gene") or "").upper(),
        str(row.get("c_hgvs") or ""),
        str(row.get("p_hgvs") or ""),
    )


def drug_key(row: dict) -> tuple[str, str, str, str, str, str]:
    return (
        str(row.get("gene") or "").upper(),
        str(row.get("c_hgvs") or ""),
        str(row.get("p_hgvs") or ""),
        str(row.get("type") or "benefit"),
        str(row.get("drug_name") or ""),
        str(row.get("header") or ""),
    )


def merge(base: dict, additive: dict) -> dict:
    merged = dict(base)
    source = dict(base.get("source") or {})
    source["merged_with"] = str((additive.get("source") or {}).get("source_type") or "additive_overlay")
    source["merged_at"] = datetime.now(timezone.utc).isoformat()
    source["merge_policy"] = "base reviewed overlay wins; additive rows append only when key is absent"
    merged["source"] = source

    gene_rows = list(base.get("gene_sections") or [])
    seen_genes = {gene_key(row) for row in gene_rows}
    for row in additive.get("gene_sections") or []:
        key = gene_key(row)
        if key not in seen_genes:
            gene_rows.append(row)
            seen_genes.add(key)

    drug_rows = list(base.get("drug_sections") or [])
    seen_drugs = {drug_key(row) for row in drug_rows}
    for row in additive.get("drug_sections") or []:
        key = drug_key(row)
        if key not in seen_drugs:
            drug_rows.append(row)
            seen_drugs.add(key)

    merged["gene_sections"] = gene_rows
    merged["drug_sections"] = drug_rows

    extra_refs = list(base.get("extra_references") or [])
    seen_refs = set(extra_refs)
    for ref in additive.get("extra_references") or []:
        if ref not in seen_refs:
            extra_refs.append(ref)
            seen_refs.add(ref)
    if extra_refs:
        merged["extra_references"] = extra_refs
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--additive", type=Path, default=DEFAULT_ADDITIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    base = load_yaml(args.base)
    additive = load_yaml(args.additive)
    merged = merge(base, additive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(merged, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"base_gene={len(base.get('gene_sections') or [])} additive_gene={len(additive.get('gene_sections') or [])} merged_gene={len(merged.get('gene_sections') or [])}")
    print(f"base_drug={len(base.get('drug_sections') or [])} additive_drug={len(additive.get('drug_sections') or [])} merged_drug={len(merged.get('drug_sections') or [])}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
