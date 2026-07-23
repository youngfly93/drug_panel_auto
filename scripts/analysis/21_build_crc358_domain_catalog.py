# 步骤: 21_build_panel_domain_catalog
# 上游: panels/<panel_id>/rules/knowledge_coverage.yaml + 当前运行时基因知识 + UniProt/InterPro 官方 API
# 输出: panels/<panel_id>/rules/reviewed_part3_domain_catalog.yaml + .work/<panel_id>_domain_catalog/build_receipt.json
# 种子: 无（确定性排序；网络响应按 accession/区间归一化）
"""Build governed panel fixed-domain candidates from official protein records.

Only genes that remain missing after the actual panel-scoped provider is loaded
are queried.  A row is emitted only when an official reviewed UniProt entry can
be resolved and at least one bounded structural feature is available from
UniProt or InterPro.  Unresolved and featureless genes remain explicit in the
receipt and therefore continue to fail the release gate; they are never hidden
behind generic prose.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reportgen.knowledge.quality import profile_panel_runtime_content  # noqa: E402
from reportgen.panels.loader import PanelPackageLoader  # noqa: E402


UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
INTERPRO_PROTEIN_URL = (
    "https://www.ebi.ac.uk/interpro/api/entry/interpro/protein/uniprot/{accession}/"
)
UNIPROT_FIELDS = ",".join(
    (
        "accession",
        "gene_names",
        "length",
        "protein_name",
        "ft_domain",
        "ft_region",
        "ft_repeat",
        "ft_coiled",
        "ft_transmem",
        "ft_signal",
    )
)
PRIMARY_FEATURE_TYPES = {"Domain", "Repeat"}
FALLBACK_FEATURE_TYPES = {"Coiled coil", "Transmembrane", "Signal", "Region"}
GENE_QUERY_ALIASES = {
    # Deprecated symbols retained by the historical panel contract.
    "HIST1H3C": "H3C3",
    "LBP1B": "UBP1",
}
ACCESSION_OVERRIDES = {
    # GNAS and RBM10 each encode more than one reviewed protein product.  The
    # report contract refers to the canonical somatic-testing protein product,
    # not the alternative ALEX/XLAS/NESP55 or MINAS-60 products.
    "GNAS": "P63092",
    "RBM10": "P98175",
}
NON_PROTEIN_GENES = {
    "TERC": {
        "fixed_domain_text": (
            "TERC为端粒酶RNA组分基因，编码端粒酶复合体所需的非编码RNA模板，"
            "不编码蛋白，因此不适用蛋白全长及蛋白结构域描述。"
        ),
        "annotation_status": "not_applicable_noncoding_rna",
        "source_refs": [
            {
                "type": "ncbi_gene",
                "id": "NCBI Gene:7012",
                "url": "https://www.ncbi.nlm.nih.gov/gene/7012",
            }
        ],
    }
}
UNINFORMATIVE_REGION = re.compile(
    r"(?i)^(?:disordered|interaction with|compositionally biased|"
    r"required for|necessary for|sufficient for|mediates |involved in )"
)


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _reportable_genes(package: Any) -> set[str]:
    coverage_path = package.resolve_rule_file("knowledge_coverage")
    declared = yaml.safe_load(coverage_path.read_text(encoding="utf-8")) or {}
    return {
        str(value).strip().upper()
        for value in declared.get("reportable_genes") or []
        if str(value).strip()
    }


def _declared_path_candidates(
    project_root: Path, package: Any, declared_path: str
) -> set[Path]:
    path = Path(str(declared_path)).expanduser()
    if path.is_absolute():
        return {path.resolve()}
    return {
        (package.root_dir / path).resolve(),
        (project_root / path).resolve(),
    }


def _catalog_consumer_gene_sets(
    project_root: Path,
    loader: PanelPackageLoader,
    output: Path,
    primary_package: Any,
) -> dict[str, set[str]]:
    """Return declared gene sets for every panel that consumes this catalog.

    A physical overlay file can be listed by more than one panel package.  The
    file is shared, but its rows are not automatically valid for every consumer:
    each row must carry the exact panel membership derived from the packages'
    governed ``reportable_genes`` contracts.  Resolve both panel-relative and
    project-relative candidates so discovery also works before the output file
    exists.
    """

    output = output.resolve()
    consumers: dict[str, set[str]] = {
        primary_package.panel_id: _reportable_genes(primary_package)
    }
    for package in loader.load_all():
        additions = (package.raw or {}).get(
            "reviewed_part3_overlay_additions"
        ) or []
        if isinstance(additions, str):
            additions = [additions]
        if not isinstance(additions, list):
            continue
        if any(
            output
            in _declared_path_candidates(project_root, package, str(declared))
            for declared in additions
        ):
            consumers[package.panel_id] = _reportable_genes(package)
    return dict(sorted(consumers.items()))


def _row_panel_memberships(
    gene: str, consumer_gene_sets: dict[str, set[str]]
) -> list[str]:
    normalized = str(gene or "").strip().upper()
    return sorted(
        panel_id
        for panel_id, genes in consumer_gene_sets.items()
        if normalized in genes
    )


def rescope_existing_catalog(
    project_root: Path,
    output: Path,
    *,
    panel_id: str,
) -> dict[str, Any]:
    """Add deterministic per-row panel scopes to an existing official catalog."""

    loader = PanelPackageLoader(project_root=project_root)
    package = loader.load(panel_id)
    consumer_gene_sets = _catalog_consumer_gene_sets(
        project_root, loader, output, package
    )
    catalog = yaml.safe_load(output.read_text(encoding="utf-8")) or {}
    rows = catalog.get("gene_sections") or []
    if not isinstance(rows, list):
        raise ValueError("domain catalog gene_sections must be a list")
    unscoped: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        memberships = _row_panel_memberships(row.get("gene", ""), consumer_gene_sets)
        if not memberships:
            unscoped.append(str(row.get("gene") or ""))
            continue
        row["panels"] = memberships
    if unscoped:
        raise ValueError(
            "domain catalog contains genes outside every consuming panel: "
            + ", ".join(sorted(unscoped))
        )
    source = catalog.setdefault("source", {})
    if isinstance(source, dict):
        source["consumer_panels"] = sorted(consumer_gene_sets)
    output.write_text(
        yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False, width=240),
        encoding="utf-8",
    )
    return {
        "schema_version": "1.0",
        "panel_id": panel_id,
        "consumer_panels": sorted(consumer_gene_sets),
        "rows_rescoped": len(rows),
        "output": str(output.relative_to(project_root)),
    }


def _request_json(url: str, *, attempts: int = 4) -> tuple[dict[str, Any], dict[str, str]]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "ReportGen-domain-catalog/1.0",
                },
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.load(response)
                headers = {
                    "uniprot_release": response.headers.get("x-uniprot-release", ""),
                    "uniprot_release_date": response.headers.get(
                        "x-uniprot-release-date", ""
                    ),
                }
                return payload, headers
        except Exception as exc:  # pragma: no cover - network retry path
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _cached_json(url: str, cache_path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return dict(cached.get("payload") or {}), dict(cached.get("headers") or {})
    payload, headers = _request_json(url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {"url": url, "headers": headers, "payload": payload},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return payload, headers


def _all_gene_names(result: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for row in result.get("genes") or []:
        for key in ("geneName",):
            value = (row.get(key) or {}).get("value")
            if value:
                values.append(str(value).upper())
        for key in ("synonyms", "orderedLocusNames", "orfNames"):
            for item in row.get(key) or []:
                value = item.get("value")
                if value:
                    values.append(str(value).upper())
    return values


def _primary_gene_name(result: dict[str, Any]) -> str:
    genes = result.get("genes") or []
    if not genes:
        return ""
    return str(((genes[0].get("geneName") or {}).get("value")) or "").upper()


def _resolve_results(
    requested: list[str], results: list[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[str], list[dict[str, Any]]]:
    resolved: dict[str, dict[str, Any]] = {}
    ambiguous: list[dict[str, Any]] = []
    for gene in requested:
        accepted_names = {gene, GENE_QUERY_ALIASES.get(gene, gene)}
        candidates_by_accession = {
            str(row.get("primaryAccession") or ""): row
            for row in results
            if accepted_names & set(_all_gene_names(row))
        }
        candidates = list(candidates_by_accession.values())
        if not candidates:
            continue
        candidates.sort(
            key=lambda row: (
                0
                if str(row.get("primaryAccession") or "")
                == ACCESSION_OVERRIDES.get(gene, "")
                else 1,
                0 if _primary_gene_name(row) == gene else 1,
                str(row.get("primaryAccession") or ""),
            )
        )
        resolved[gene] = candidates[0]
        if len(candidates) > 1:
            ambiguous.append(
                {
                    "gene": gene,
                    "selected": candidates[0].get("primaryAccession"),
                    "candidates": [row.get("primaryAccession") for row in candidates],
                }
            )
    return resolved, sorted(set(requested) - set(resolved)), ambiguous


def _location(feature: dict[str, Any]) -> tuple[int, int] | None:
    location = feature.get("location") or {}
    start = (location.get("start") or {}).get("value")
    end = (location.get("end") or {}).get("value")
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    return start, end


def _uniprot_features(result: dict[str, Any]) -> list[dict[str, Any]]:
    primary: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    for feature in result.get("features") or []:
        feature_type = str(feature.get("type") or "")
        location = _location(feature)
        description = str(feature.get("description") or feature_type).strip()
        if not location or not description:
            continue
        item = {
            "name": description,
            "type": feature_type,
            "start": location[0],
            "end": location[1],
            "source": "uniprot",
        }
        if feature_type in PRIMARY_FEATURE_TYPES:
            primary.append(item)
        elif feature_type in FALLBACK_FEATURE_TYPES:
            if feature_type == "Region" and UNINFORMATIVE_REGION.search(description):
                continue
            fallback.append(item)
    return primary or fallback


def _interpro_features(payload: dict[str, Any], accession: str) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    family_features: list[dict[str, Any]] = []
    for result in payload.get("results") or []:
        metadata = result.get("metadata") or {}
        entry_type = str(metadata.get("type") or "").lower()
        if entry_type not in {
            "domain",
            "repeat",
            "homologous_superfamily",
            "family",
        }:
            continue
        name = str(metadata.get("name") or "").strip()
        entry_id = str(metadata.get("accession") or "").strip()
        for protein in result.get("proteins") or []:
            if str(protein.get("accession") or "").upper() != accession.upper():
                continue
            for location in protein.get("entry_protein_locations") or []:
                for fragment in location.get("fragments") or []:
                    start = fragment.get("start")
                    end = fragment.get("end")
                    if isinstance(start, int) and isinstance(end, int):
                        item = {
                            "name": name,
                            "type": entry_type.title(),
                            "start": start,
                            "end": end,
                            "source": "interpro",
                            "entry_id": entry_id,
                        }
                        if entry_type == "family":
                            family_features.append(item)
                        else:
                            features.append(item)
    return features or family_features


def _normalize_feature_name(name: str, feature_type: str) -> str:
    text = re.sub(r"\s+", " ", str(name or "")).strip(" .")
    text = re.sub(r"(?i)\s+domain$", "", text).strip()
    if feature_type.lower() == "repeat":
        return text if "重复" in text else f"{text}重复区"
    if feature_type == "Coiled coil":
        return "卷曲螺旋区域"
    if feature_type == "Transmembrane":
        return "跨膜区域"
    if feature_type == "Signal":
        return "信号肽区域"
    if feature_type == "Region":
        return text if text.endswith(("区", "区域")) else f"{text}区域"
    if feature_type == "Family":
        return text if "家族" in text else f"{text}家族区域"
    if feature_type == "Homologous_Superfamily":
        text = re.sub(r"(?i),?\s*domain superfamily$", "", text).strip()
        return text if "结构域" in text else f"{text}结构域"
    return text if "结构域" in text else f"{text}结构域"


def _dedupe_features(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        features,
        key=lambda item: (
            int(item["start"]),
            int(item["end"]),
            str(item["name"]).casefold(),
        ),
    )
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for item in ordered:
        display = _normalize_feature_name(str(item["name"]), str(item["type"]))
        key = (
            re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", display.casefold()),
            int(item["start"]),
            int(item["end"]),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append({**item, "display_name": display})
    return output[:12]


def _domain_text(gene: str, length: int, features: list[dict[str, Any]]) -> str:
    rendered = [
        f"{item['display_name']}（{item['start']}-{item['end']}位氨基酸）"
        for item in features
    ]
    return (
        f"{gene}基因编码的蛋白全长为{length}个氨基酸，"
        f"UniProt/InterPro注释的主要结构区域包括{'、'.join(rendered)}。"
    )


def _interpro_for_accession(
    accession: str, cache_dir: Path
) -> tuple[str, dict[str, Any]]:
    url = INTERPRO_PROTEIN_URL.format(accession=accession) + "?page_size=200"
    payload, _ = _cached_json(url, cache_dir / "interpro" / f"{accession}.json")
    return accession, payload


def build_catalog(
    project_root: Path,
    output: Path,
    cache_dir: Path,
    *,
    panel_id: str = "crc_358_msi",
    candidate_only: bool = False,
) -> dict[str, Any]:
    loader = PanelPackageLoader(project_root=project_root)
    package = loader.load(panel_id)
    coverage_path = package.resolve_rule_file("knowledge_coverage")
    declared = yaml.safe_load(coverage_path.read_text(encoding="utf-8")) or {}
    reportable = sorted(
        {str(value).strip().upper() for value in declared.get("reportable_genes") or []}
    )
    current = profile_panel_runtime_content(project_root, package, reportable)
    requested = list(current["missing_fixed_domain_genes"])

    all_results: list[dict[str, Any]] = []
    release_headers: dict[str, str] = {}
    protein_requested = [gene for gene in requested if gene not in NON_PROTEIN_GENES]
    for genes in _chunks(protein_requested, 15):
        query_names = [GENE_QUERY_ALIASES.get(gene, gene) for gene in genes]
        query = "(" + " OR ".join(
            f"gene_exact:{gene}" for gene in query_names
        ) + ")"
        query += " AND (organism_id:9606) AND (reviewed:true)"
        params = {
            "query": query,
            "format": "json",
            "fields": UNIPROT_FIELDS,
            "size": "500",
        }
        url = UNIPROT_SEARCH_URL + "?" + urllib.parse.urlencode(params)
        cache_name = hashlib.sha256(url.encode()).hexdigest()[:16]
        payload, headers = _cached_json(
            url, cache_dir / "uniprot" / f"batch-{cache_name}.json"
        )
        all_results.extend(payload.get("results") or [])
        release_headers.update({key: value for key, value in headers.items() if value})

    resolved, unresolved, ambiguous = _resolve_results(
        protein_requested, all_results
    )
    ambiguity_by_gene = {
        str(row["gene"]): dict(row)
        for row in ambiguous
    }
    fallback_accessions = sorted(
        {
            str(row.get("primaryAccession") or "")
            for row in resolved.values()
            if not _uniprot_features(row)
        }
        - {""}
    )
    interpro_payloads: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(_interpro_for_accession, accession, cache_dir): accession
            for accession in fallback_accessions
        }
        for future in as_completed(futures):
            accession = futures[future]
            try:
                key, payload = future.result()
                interpro_payloads[key] = payload
            except Exception as exc:  # pragma: no cover - network failure receipt
                interpro_payloads[accession] = {"_error": str(exc), "results": []}

    rows: list[dict[str, Any]] = [
        {"gene": gene, **dict(content)}
        for gene, content in NON_PROTEIN_GENES.items()
        if gene in requested
    ]
    featureless: list[dict[str, Any]] = []
    for gene in protein_requested:
        result = resolved.get(gene)
        if not result:
            continue
        accession = str(result.get("primaryAccession") or "")
        length = int((result.get("sequence") or {}).get("length") or 0)
        features = _uniprot_features(result)
        if not features:
            features = _interpro_features(
                interpro_payloads.get(accession) or {}, accession
            )
        features = _dedupe_features(features)
        if not length or not features:
            featureless.append(
                {
                    "gene": gene,
                    "accession": accession,
                    "length": length,
                    "interpro_error": (
                        interpro_payloads.get(accession) or {}
                    ).get("_error", ""),
                }
            )
            continue
        interpro_ids = sorted(
            {
                str(item.get("entry_id") or "")
                for item in features
                if item.get("entry_id")
            }
        )
        row = {
            "gene": gene,
            "fixed_domain_text": _domain_text(gene, length, features),
            "annotation_status": "official_feature_annotated",
            "uniprot_accession": accession,
            "interpro_entries": interpro_ids,
            "source_refs": [
                {
                    "type": "uniprot",
                    "id": accession,
                    "url": f"https://www.uniprot.org/uniprotkb/{accession}/entry",
                },
                *(
                    [
                        {
                            "type": "interpro",
                            "id": accession,
                            "url": INTERPRO_PROTEIN_URL.format(
                                accession=accession
                            )
                            + "?page_size=200",
                        }
                    ]
                    if any(item["source"] == "interpro" for item in features)
                    else []
                ),
            ],
        }
        ambiguity = ambiguity_by_gene.get(gene)
        if ambiguity:
            candidate_rows = [
                item
                for item in all_results
                if str(item.get("primaryAccession") or "")
                in set(ambiguity["candidates"])
            ]
            exact_primary_candidates = sorted(
                str(item.get("primaryAccession") or "")
                for item in candidate_rows
                if _primary_gene_name(item) == gene
            )
            row["accession_selection"] = {
                "status": "pending_secondary_mapping_review",
                "selected": accession,
                "alternatives": [
                    value
                    for value in ambiguity["candidates"]
                    if value != accession
                ],
                "selection_basis": (
                    "explicit_accession_override"
                    if ACCESSION_OVERRIDES.get(gene) == accession
                    else (
                        "exact_primary_gene_name_preferred_over_synonym_collision"
                        if len(exact_primary_candidates) == 1
                        else (
                            "deterministic_accession_order_pending_"
                            "transcript_product_review"
                        )
                    )
                ),
                "exact_primary_gene_accessions": exact_primary_candidates,
                "requires_transcript_product_review": (
                    len(exact_primary_candidates) > 1
                ),
            }
        rows.append(row)

    consumer_gene_sets = _catalog_consumer_gene_sets(
        project_root, loader, output, package
    )
    for row in rows:
        memberships = _row_panel_memberships(row.get("gene", ""), consumer_gene_sets)
        if not memberships:
            raise ValueError(
                f"generated domain row is outside every consumer panel: {row.get('gene')}"
            )
        row["panels"] = memberships

    today = date.today().isoformat()
    catalog = {
        "schema_version": 1,
        "source": {
            "panel": panel_id,
            "purpose": "Panel-wide fixed protein/domain first-review catalog.",
            "source_type": "official_reviewed_protein_annotation",
            "curated_at": today,
            "uniprot_release": release_headers.get("uniprot_release", ""),
            "uniprot_release_date": release_headers.get(
                "uniprot_release_date", ""
            ),
            "scope": "pan_cancer_protein_structure_only",
            "activation_mode": (
                "candidate_only_pending_secondary_review"
                if candidate_only
                else "provisional_runtime"
            ),
            "consumer_panels": sorted(consumer_gene_sets),
            "privacy": "No patient or sample identifiers are stored.",
        },
        "governance": {
            "schema_version": "1.0",
            "policy_id": f"{panel_id}_fixed_domain_catalog_first_review",
            "defaults": {
                "gene": {
                    "review_status": (
                        "needs_review"
                        if candidate_only
                        else "provisional_runtime"
                    ),
                    "runtime_eligible": not candidate_only,
                    "review_basis": "codex_first_review_official_protein_annotation",
                    "reviewer": "codex",
                    "reviewer_type": "ai_assisted_evidence_review",
                    "reviewed_at": today,
                    "evidence_as_of": today,
                    "evidence_level": "curated_protein_structure",
                    "cancer_scope": "pan_cancer_protein_structure_only",
                    "secondary_review_status": "pending_report_group_review",
                    "risk_level": "content_requires_secondary_review",
                }
            },
        },
        "gene_sections": sorted(rows, key=lambda row: row["gene"]),
        "drug_sections": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.safe_dump(
            catalog,
            allow_unicode=True,
            sort_keys=False,
            width=240,
        ),
        encoding="utf-8",
    )

    receipt = {
        "schema_version": "1.0",
        "panel_id": panel_id,
        "generated_at": today,
        "input": {
            "reportable_genes": len(reportable),
            "previously_covered_genes": current["fixed_domain_covered_genes"],
            "requested_missing_genes": len(requested),
        },
        "source_release": release_headers,
        "consumer_panels": sorted(consumer_gene_sets),
        "resolved_uniprot_genes": len(resolved),
        "generated_rows": len(rows),
        "unresolved_genes": unresolved,
        "featureless_genes": featureless,
        "ambiguous_gene_mappings": ambiguous,
        "candidate_only": candidate_only,
        "output": str(output.relative_to(project_root)),
    }
    receipt_path = cache_dir / "build_receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--panel-id", default="crc_358_msi")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--rescope-existing",
        action="store_true",
        help=(
            "Do not query source APIs; add deterministic per-row panel scopes "
            "to the existing output catalog."
        ),
    )
    parser.add_argument(
        "--candidate-only",
        action="store_true",
        help=(
            "Emit fully sourced review candidates with runtime_eligible=false "
            "until an attributed secondary review is recorded."
        ),
    )
    args = parser.parse_args()
    root = args.project_root.resolve()
    output_arg = args.output or Path(
        f"panels/{args.panel_id}/rules/reviewed_part3_domain_catalog.yaml"
    )
    output = output_arg if output_arg.is_absolute() else root / output_arg
    cache_arg = args.cache_dir or Path(f".work/{args.panel_id}_domain_catalog")
    cache_dir = (
        cache_arg if cache_arg.is_absolute() else root / cache_arg
    )
    if args.rescope_existing:
        receipt = rescope_existing_catalog(
            root,
            output,
            panel_id=str(args.panel_id),
        )
    else:
        receipt = build_catalog(
            root,
            output,
            cache_dir,
            panel_id=str(args.panel_id),
            candidate_only=bool(args.candidate_only),
        )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if args.rescope_existing:
        return 0
    return 0 if not receipt["unresolved_genes"] and not receipt["featureless_genes"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
