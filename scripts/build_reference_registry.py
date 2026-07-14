#!/usr/bin/env python3
"""Build the structured PMID title registry used by final-report citations."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reportgen.knowledge.quality import (  # noqa: E402
    SENTINEL_C_HGVS,
    SENTINEL_P_HGVS,
    build_panel_gene_provider,
    extract_reference_identifiers,
)
from reportgen.knowledge.release_gate import DEFAULT_PANELS  # noqa: E402
from reportgen.panels.loader import PanelPackageLoader  # noqa: E402


def _declared_genes(package) -> list[str]:
    path = package.resolve_rule_file("knowledge_coverage")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return sorted(
        {
            str(value).strip().upper()
            for value in raw.get("reportable_genes") or []
            if str(value).strip()
        }
    )


def _cited_pmids(root: Path, panel_ids: list[str]) -> set[str]:
    loader = PanelPackageLoader(project_root=root)
    pmids: set[str] = set()
    for panel_id in panel_ids:
        package = loader.load(panel_id)
        provider = build_panel_gene_provider(root, package)
        texts: list[str] = []
        for gene in _declared_genes(package):
            section = provider.build_gene_knowledge_section(
                gene=gene,
                c_hgvs=SENTINEL_C_HGVS,
                p_hgvs=SENTINEL_P_HGVS,
                frequency=10.0,
                mutation_type="Missense",
                has_drug=False,
            )
            texts.extend(
                [
                    str(section.get("intro") or ""),
                    str(section.get("mutation_analysis") or ""),
                ]
            )
        pmids.update(extract_reference_identifiers(texts)["pmid"])
    return pmids


def _fetch_pubmed_summaries(pmids: list[str]) -> dict[str, dict]:
    summaries: dict[str, dict] = {}
    for start in range(0, len(pmids), 100):
        batch = pmids[start : start + 100]
        query = urllib.parse.urlencode(
            {"db": "pubmed", "id": ",".join(batch), "retmode": "json"}
        )
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + query
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ReportGen-reference-registry/1.0"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload.get("result") or {}
        for uid in result.get("uids") or []:
            row = result.get(str(uid))
            if isinstance(row, dict):
                summaries[str(uid)] = row
        if start + 100 < len(pmids):
            time.sleep(0.4)
    return summaries


def _citation(pmid: str, row: dict) -> str:
    title = str(row.get("title") or "").strip().rstrip(".")
    journal = str(row.get("fulljournalname") or row.get("source") or "").strip()
    pubdate = str(row.get("pubdate") or "").strip()
    parts = [f"PMID:{pmid} {title}." if title else f"PMID:{pmid}"]
    if journal:
        parts.append(journal.rstrip(".") + ".")
    if pubdate:
        parts.append(pubdate.rstrip(".") + ".")
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--panels", nargs="+", default=list(DEFAULT_PANELS))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/knowledge_bases/processed/reference_registry.yaml"),
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    pmids = sorted(_cited_pmids(root, list(args.panels)), key=int)
    summaries = _fetch_pubmed_summaries(pmids)
    missing = sorted(set(pmids) - set(summaries), key=int)
    payload = {
        "schema_version": "1.0",
        "registry_id": "reportgen_pubmed_title_registry_v1",
        "generated_on": date.today().isoformat(),
        "source": {
            "type": "ncbi_pubmed_esummary",
            "url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            "panel_scope": list(args.panels),
        },
        "references": [
            {
                "type": "pubmed",
                "id": f"PMID:{pmid}",
                "title": str(summaries[pmid].get("title") or "").strip(),
                "citation": _citation(pmid, summaries[pmid]),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "retrieved_on": date.today().isoformat(),
            }
            for pmid in pmids
            if pmid in summaries
        ],
        "unresolved_pmids": missing,
    }
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(
        f"references={len(payload['references'])} unresolved={len(missing)} "
        f"output={output}"
    )
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
