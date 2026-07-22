"""
Knowledge base service: wraps upstream GeneKnowledgeProvider
for web browsing of gene knowledge, drug mappings, and immune gene lists.
"""

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import yaml

from app.config import settings
from app.schemas.knowledge import KnowledgeEntry, PanelKnowledgeSummary

_upstream = Path(str(settings.upstream_root)).resolve()
if str(_upstream) not in sys.path:
    sys.path.insert(0, str(_upstream))

from reportgen.knowledge import GeneKnowledgeProvider  # noqa: E402
from reportgen.knowledge.governance import (  # noqa: E402
    effective_governance,
    governance_defaults,
    structured_source_refs,
)
from reportgen.knowledge.quality import profile_panel_runtime_content  # noqa: E402
from reportgen.knowledge.release_gate import (  # noqa: E402
    _clinical_readiness,
    _clinical_release_registry,
    _secondary_review_receipt,
)
from reportgen.panels.loader import PanelPackageLoader  # noqa: E402
from reportgen.rules.targeted_drugs import (  # noqa: E402
    load_targeted_drug_rule_context,
)

# No hardcoded paths — upstream root comes from settings

# Cached DataFrames with mtime tracking for auto-refresh
_gene_kb_df: Optional[dict[str, pd.DataFrame]] = None
_gene_kb_mtime: float = 0.0
_drug_db_df: Optional[pd.DataFrame] = None
_drug_db_mtime: float = 0.0
_immune_df: Optional[pd.DataFrame] = None
_immune_mtime: float = 0.0
_overlay_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_base_gene_provider: Optional[GeneKnowledgeProvider] = None
_base_gene_provider_mtime: float = 0.0


def _kb_base_path() -> Path:
    return Path(settings.upstream_root) / "data" / "knowledge_bases" / "processed"


def _file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _load_gene_kb() -> dict[str, pd.DataFrame]:
    global _gene_kb_df, _gene_kb_mtime

    path = _kb_base_path() / "gene_knowledge_db.xlsx"
    current_mtime = _file_mtime(path)

    # Return cache if still valid
    if _gene_kb_df is not None and current_mtime == _gene_kb_mtime:
        return _gene_kb_df

    if not path.exists():
        _gene_kb_df = {}
        _gene_kb_mtime = 0.0
        return _gene_kb_df

    try:
        xls = pd.ExcelFile(path)
        _gene_kb_df = {}
        for sheet in xls.sheet_names:
            _gene_kb_df[sheet] = pd.read_excel(xls, sheet_name=sheet, dtype=str).fillna("")
        _gene_kb_mtime = current_mtime
    except Exception:
        _gene_kb_df = {}
    return _gene_kb_df


def _gene_analysis_sheet() -> tuple[str, Optional[pd.DataFrame]]:
    """Return only the runtime gene-analysis sheet, never staffing/meta sheets."""
    kb = _load_gene_kb()
    for sheet_name, df in kb.items():
        if "基因变异解析" in sheet_name:
            return sheet_name, df
    for sheet_name, df in kb.items():
        if "变异解析" in sheet_name or "gene" in sheet_name.lower():
            return sheet_name, df
    return "", None


def _gene_column(df: Optional[pd.DataFrame]) -> Optional[str]:
    if df is None:
        return None
    for column in df.columns:
        text = str(column)
        if text == "基因名称" or "gene" in text.lower():
            return text
    return None


def _load_base_gene_provider() -> Optional[GeneKnowledgeProvider]:
    """Load the same base Part 3 provider used by Word, without any overlay."""
    global _base_gene_provider, _base_gene_provider_mtime

    path = _kb_base_path() / "gene_knowledge_db.xlsx"
    current_mtime = _file_mtime(path)
    if (
        _base_gene_provider is not None
        and current_mtime == _base_gene_provider_mtime
    ):
        return _base_gene_provider
    if not path.exists():
        _base_gene_provider = None
        _base_gene_provider_mtime = 0.0
        return None

    try:
        relative_path = path.resolve().relative_to(_project_root())
        provider = GeneKnowledgeProvider(
            {
                "enabled": True,
                "gene_knowledge_db": {
                    "enabled": True,
                    "path": str(relative_path),
                    "reviewed_part3_overlay_path": "",
                    "sheets": {
                        "gene_analysis": "基因变异解析",
                        "drug_analysis": "用药提示解析",
                        "references": "参考文献",
                    },
                    "columns": {
                        "gene_name": "基因名称",
                        "gene_intro": "基因简介",
                        "mutation_analysis": "基因变异解析",
                    },
                },
            }
        )
        provider.load(str(_project_root()))
    except Exception:
        _base_gene_provider = None
        _base_gene_provider_mtime = 0.0
        return None
    _base_gene_provider = provider
    _base_gene_provider_mtime = current_mtime
    return provider


def _load_drug_db() -> Optional[pd.DataFrame]:
    global _drug_db_df, _drug_db_mtime

    path = _kb_base_path() / "targeted_drug_db_public.xlsx"
    current_mtime = _file_mtime(path)

    if _drug_db_df is not None and current_mtime == _drug_db_mtime:
        return _drug_db_df

    if not path.exists():
        return None

    try:
        # The legacy workbook contains exact duplicate candidate rows.  Keep the
        # binary source immutable in this runtime, but expose and count each
        # semantic candidate once in the Web catalog.
        _drug_db_df = (
            pd.read_excel(path, dtype=str)
            .fillna("")
            .drop_duplicates()
            .reset_index(drop=True)
        )
        _drug_db_mtime = current_mtime
    except Exception:
        pass
    return _drug_db_df


def _load_immune_genes() -> Optional[pd.DataFrame]:
    global _immune_df, _immune_mtime

    path = _kb_base_path() / "immune_gene_list_public.xlsx"
    current_mtime = _file_mtime(path)

    if _immune_df is not None and current_mtime == _immune_mtime:
        return _immune_df

    if not path.exists():
        return None

    try:
        _immune_df = pd.read_excel(path, dtype=str).fillna("")
        _immune_mtime = current_mtime
    except Exception:
        pass
    return _immune_df


def _df_to_records(df: pd.DataFrame, page: int = 1, page_size: int = 50, search: str = "") -> dict:
    """Convert DataFrame to paginated records with optional search."""
    if search:
        mask = df.apply(
            lambda row: row.astype(str)
            .str.contains(search, case=False, na=False, regex=False)
            .any(),
            axis=1,
        )
        df = df[mask]

    total = len(df)
    start = (page - 1) * page_size
    end = start + page_size
    page_df = df.iloc[start:end]

    return {
        "columns": list(df.columns),
        "rows": page_df.to_dict(orient="records"),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_gene_list(page: int = 1, page_size: int = 50, search: str = "") -> dict:
    """Get paginated gene knowledge list."""
    _sheet_name, df = _gene_analysis_sheet()
    if df is not None:
        return _df_to_records(df, page, page_size, search)

    return {"columns": [], "rows": [], "total": 0, "page": page, "page_size": page_size}


def get_gene_detail(gene_name: str) -> dict[str, Any]:
    """Get detailed info for a specific gene across all KB sheets."""
    kb = _load_gene_kb()
    result: dict[str, Any] = {"gene": gene_name, "sheets": {}}

    for sheet_name, df in kb.items():
        # Search for gene in any column that might contain gene names
        for col in df.columns:
            if "基因" in col or "gene" in col.lower() or "Gene" in col:
                matches = df[df[col].str.upper() == gene_name.upper()]
                if len(matches) > 0:
                    result["sheets"][sheet_name] = matches.to_dict(orient="records")
                    break

    return result


def get_drug_list(page: int = 1, page_size: int = 50, search: str = "") -> dict:
    """Get paginated drug mapping list."""
    df = _load_drug_db()
    if df is None:
        return {"columns": [], "rows": [], "total": 0, "page": page, "page_size": page_size}
    return _df_to_records(df, page, page_size, search)


def get_immune_genes() -> dict:
    """Get immune gene classification lists."""
    df = _load_immune_genes()
    if df is None:
        return {"columns": [], "rows": [], "total": 0}
    return {
        "columns": list(df.columns),
        "rows": df.to_dict(orient="records"),
        "total": len(df),
    }


def get_stats() -> dict:
    """Get summary statistics for all knowledge bases."""
    kb = _load_gene_kb()
    drug_df = _load_drug_db()
    immune_df = _load_immune_genes()

    _sheet_name, gene_df = _gene_analysis_sheet()
    gene_col = _gene_column(gene_df)
    source_rows = len(gene_df) if gene_df is not None else 0
    valid_genes: list[str] = []
    if gene_df is not None and gene_col:
        valid_genes = [
            str(value).strip().upper()
            for value in gene_df[gene_col].tolist()
            if str(value).strip() and str(value).strip().upper() != "基因"
        ]

    return {
        "gene_knowledge": {
            "sheets": len(kb),
            "total_rows": len(valid_genes),
            "source_rows": source_rows,
            "unique_genes": len(set(valid_genes)),
        },
        "drug_mappings": {"total_rows": len(drug_df) if drug_df is not None else 0},
        "immune_genes": {"total_rows": len(immune_df) if immune_df is not None else 0},
    }


# ---------------------------------------------------------------------------
# Panel Knowledge Catalog (new read-only API; legacy table endpoints above stay
# available for backward compatibility).
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    return Path(settings.upstream_root).resolve()


def _panel_packages() -> dict[str, Any]:
    loader = PanelPackageLoader(project_root=_project_root())
    packages: dict[str, Any] = {}
    for panel_yaml in sorted(loader.panels_dir.glob("*/panel.yaml")):
        try:
            package = loader.load_file(panel_yaml)
        except Exception:
            continue
        packages[package.panel_id] = package
    return packages


def _get_panel_package(panel_id: str) -> Any:
    package = _panel_packages().get(str(panel_id or "").strip())
    if package is None:
        raise KeyError(f"Unknown panel: {panel_id}")
    return package


def _sha256_revision(path: Path) -> str:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        digest = "unavailable"
    return f"sha256:{digest}"


def _updated_at(path: Path) -> str:
    try:
        timestamp = path.stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def _load_overlay_file(path: Path) -> dict[str, Any]:
    key = str(path.resolve())
    mtime = _file_mtime(path)
    cached = _overlay_cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("reviewed overlay must be a mapping")
    _overlay_cache[key] = (mtime, raw)
    return raw


def _resolve_overlay(package: Any) -> tuple[Optional[Path], Optional[dict], str]:
    declared = (getattr(package, "raw", None) or {}).get(
        "reviewed_part3_overlay"
    )
    if not declared:
        return None, None, "Panel 未声明 reviewed overlay。"
    try:
        path = package._resolve_path(str(declared)).resolve()
        panels_root = (_project_root() / "panels").resolve()
        path.relative_to(panels_root)
    except Exception:
        return None, None, "Reviewed overlay 路径不在受控 panels 目录内。"
    if not path.exists():
        return path, None, "Reviewed overlay 文件不存在。"
    try:
        primary = _load_overlay_file(path)
    except Exception:
        # Parser and IO exceptions can contain absolute paths. Keep Web-facing
        # warnings useful without exposing the host filesystem layout.
        return path, None, "Reviewed overlay 文件格式无效或无法读取。"

    combined = dict(primary)
    combined["gene_sections"] = []
    combined["drug_sections"] = []

    def row_applies_to_panel(row: dict[str, Any]) -> bool:
        raw_panels = row.get("panels")
        if raw_panels is None:
            raw_panels = row.get("panel_ids")
        if raw_panels is None:
            raw_panels = row.get("panel_id")
        if raw_panels is None:
            return True
        if isinstance(raw_panels, str):
            raw_panels = [raw_panels]
        if not isinstance(raw_panels, (list, tuple, set)):
            return False
        allowed = {
            str(value).strip().casefold()
            for value in raw_panels
            if str(value).strip()
        }
        return str(package.panel_id).strip().casefold() in allowed

    def append_rows(data: dict[str, Any], source_path: Path) -> None:
        source = data.get("source") if isinstance(data.get("source"), dict) else {}
        origin_panel_id = str(source.get("panel") or package.panel_id)
        revision = _sha256_revision(source_path)
        for section in ("gene_sections", "drug_sections"):
            kind = "gene" if section == "gene_sections" else "drug"
            defaults = governance_defaults(data, kind)
            for row in data.get(section) or []:
                if not isinstance(row, dict):
                    continue
                if not row_applies_to_panel(row):
                    continue
                tagged = dict(row)
                tagged["_origin_panel_id"] = origin_panel_id
                tagged["_source_path"] = str(source_path)
                tagged["_source_revision"] = revision
                tagged["_source_type"] = str(
                    source.get("source_type") or "panel_reviewed_overlay"
                )
                tagged["_governance_defaults"] = defaults
                combined[section].append(tagged)

    append_rows(primary, path)
    additions = (getattr(package, "raw", None) or {}).get(
        "reviewed_part3_overlay_additions"
    ) or []
    if isinstance(additions, str):
        additions = [additions]
    try:
        panels_root = (_project_root() / "panels").resolve()
        for declared_addition in additions if isinstance(additions, list) else []:
            addition_path = package._resolve_path(str(declared_addition)).resolve()
            addition_path.relative_to(panels_root)
            if not addition_path.exists():
                return path, None, "Panel 附加 reviewed overlay 文件不存在。"
            append_rows(_load_overlay_file(addition_path), addition_path)
    except Exception:
        return path, None, "Panel 附加 reviewed overlay 格式无效或路径不受控。"
    return path, combined, ""


def _overlay_review_status(
    data: Optional[dict[str, Any]],
    revision: str = "",
) -> tuple[str, str, str]:
    if not data:
        return "not_recorded", "overlay_file", "overlay_unavailable"
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    purpose = str(source.get("purpose") or "")
    approved_revision = str(
        source.get("approved_revision")
        or source.get("approved_sha256")
        or ""
    ).lower().removeprefix("sha256:")
    current_revision = str(revision or "").lower().removeprefix("sha256:")
    if (
        approved_revision
        and current_revision
        and (
            current_revision.startswith(approved_revision)
            or approved_revision.startswith(current_revision)
        )
    ):
        return (
            "approved_for_runtime",
            "overlay_file",
            "approved_current_revision",
        )
    if "NEEDS" in purpose.upper() or "需医学审核" in purpose:
        return "needs_review", "overlay_file", "source_declares_review_needed"
    if source.get("approved_review_policy") or source.get(
        "approved_review_applied_at"
    ):
        return (
            "not_recorded",
            "overlay_file",
            "current_revision_not_approved",
        )
    return "not_recorded", "overlay_file", "no_explicit_review_record"


def _entry_review(
    data: Optional[dict[str, Any]],
    row: Optional[dict[str, Any]] = None,
    revision: str = "",
) -> dict[str, Any]:
    kind = "drug" if (row or {}).get("drug_name") else "gene"
    if isinstance((data or {}).get("governance"), dict) or isinstance(
        (row or {}).get("_governance_defaults"), dict
    ):
        governance = effective_governance(data, row or {}, kind)
        return {
            "status": governance["status"],
            "scope": "entry_governance",
            "basis": governance["review_basis"] or "structured_governance",
            "runtime_eligible": governance["runtime_eligible"],
            "reviewer": governance["reviewer"],
            "reviewer_type": governance["reviewer_type"],
            "reviewed_at": governance["reviewed_at"],
            "evidence_as_of": governance["evidence_as_of"],
            "secondary_review_status": governance["secondary_review_status"],
            "risk_level": governance["risk_level"],
        }
    explicit_status = str((row or {}).get("review_status") or "").strip().lower()
    first_pass = (row or {}).get("first_pass_review")
    if explicit_status in {"approved_for_runtime", "needs_review", "not_recorded"}:
        if (
            explicit_status == "needs_review"
            and isinstance(first_pass, dict)
            and str(first_pass.get("status") or "").strip().lower() == "completed"
        ):
            return {
                "status": "needs_review",
                "scope": "entry_note",
                "basis": "first_pass_complete_pending_secondary_review",
                "runtime_eligible": False,
            }
        return {
            "status": explicit_status,
            "scope": "entry_note",
            "basis": "explicit_entry_review_status",
            "runtime_eligible": (row or {}).get("runtime_eligible") is not False
            and explicit_status == "approved_for_runtime",
        }
    source_note = str((row or {}).get("source_note") or "")
    if "需医学审核" in source_note or "NEEDS" in source_note.upper():
        return {
            "status": "needs_review",
            "scope": "entry_note",
            "basis": "entry_source_note_requires_review",
            "runtime_eligible": False,
        }
    status, scope, basis = _overlay_review_status(data, revision)
    return {
        "status": status,
        "scope": scope,
        "basis": basis,
        "runtime_eligible": status == "approved_for_runtime",
    }


def _panel_summary(package: Any) -> dict[str, Any]:
    path, data, warning = _resolve_overlay(package)
    source = data.get("source") if data and isinstance(data.get("source"), dict) else {}
    origin_panel_id = str(source.get("panel") or package.panel_id)
    revision = _sha256_revision(path) if path and data else ""
    review_status, _scope, _basis = _overlay_review_status(data, revision)
    overlay_rows = (
        list(data.get("gene_sections") or [])
        + list(data.get("drug_sections") or [])
        if data
        else []
    )
    row_statuses = {
        _entry_review(data, row, revision)["status"]
        for row in overlay_rows
        if isinstance(row, dict)
    }
    for candidate in (
        "needs_review",
        "rejected",
        "provisional_runtime",
        "approved_for_runtime",
        "legacy_runtime",
    ):
        if candidate in row_statuses:
            review_status = candidate
            break
    return PanelKnowledgeSummary(
        panel_id=package.panel_id,
        display_name=package.display_name,
        status=str((getattr(package, "raw", None) or {}).get("status") or ""),
        overlay_available=bool(path and data),
        overlay_origin_panel_id=origin_panel_id if data else None,
        shared_overlay=bool(data and origin_panel_id != package.panel_id),
        review_status=review_status,
        warning=warning or None,
    ).model_dump()


def get_catalog_panels() -> dict[str, Any]:
    panels = [
        _panel_summary(package)
        for package in sorted(_panel_packages().values(), key=lambda item: item.panel_id)
    ]
    return {"panels": panels, "total": len(panels)}


def _stable_entry_id(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _row_value(row: Any, *aliases: str) -> str:
    for alias in aliases:
        if alias in row:
            return _clean_value(row.get(alias))
    compact_aliases = {re.sub(r"\s+", "", alias) for alias in aliases}
    for column in getattr(row, "index", []):
        if re.sub(r"\s+", "", str(column)) in compact_aliases:
            return _clean_value(row.get(column))
    return ""


def _safe_source_ref(source_db: str, raw: Any) -> str:
    source = str(source_db or "").strip()
    text = _clean_value(raw)
    if source.lower() == "internal":
        return "internal_curated_source"
    if not text:
        return ""
    safe_parts: list[str] = []
    for part in re.split(r"[;；]", text):
        token = part.strip()
        if not token:
            continue
        if re.search(r"(?:^|[/\\])[^/\\]+\.(?:xlsx?|csv|tsv|docx?)$", token, re.I):
            continue
        if (
            re.match(r"^https?://", token, re.I)
            or re.match(r"^(?:PMID|NCT|CTR|ChiCTR|DOI)[:\s]", token, re.I)
            or token.upper() in {"FDA", "NCCN"}
        ):
            safe_parts.append(token[:500])
    return ";".join(safe_parts)


def _match_scope(c_hgvs: str, p_hgvs: str, event: str = "") -> str:
    if c_hgvs or p_hgvs:
        return "variant"
    if event:
        return "event"
    return "gene"


def _base_gene_entries(panel_id: str) -> list[dict[str, Any]]:
    sheet, df = _gene_analysis_sheet()
    gene_col = _gene_column(df)
    if df is None or not gene_col:
        return []
    path = _kb_base_path() / "gene_knowledge_db.xlsx"
    revision = _sha256_revision(path)
    updated_at = _updated_at(path)
    provider = _load_base_gene_provider()
    entries: list[dict[str, Any]] = []
    for position, (_, row) in enumerate(df.iterrows(), start=2):
        gene = _row_value(row, gene_col).upper()
        if not gene or gene == "基因":
            continue
        effective_section = (
            provider.build_gene_knowledge_section(
                gene=gene,
                c_hgvs="c.999999A>G",
                p_hgvs="p.X999999Y",
                frequency=10.0,
                mutation_type="Missense",
                has_drug=False,
            )
            if provider is not None
            else {}
        )
        entry = KnowledgeEntry(
            entry_id=_stable_entry_id("base_gene", position, gene),
            kind="gene",
            layer="base",
            panel_id=panel_id,
            gene=gene,
            match_scope="gene",
            runtime_behavior="fallback_when_no_reviewed_match",
            review={
                "status": "legacy_runtime",
                "scope": "source_row",
                "basis": "base_excel_legacy_runtime_source_row",
                "runtime_eligible": True,
                "secondary_review_status": "historical_not_row_bound",
            },
            provenance={
                "source_id": "gene_knowledge_db",
                "source_type": "base_excel",
                "sheet": sheet,
                "row_number": position,
                "source_refs": [
                    {
                        "type": "workbook_row",
                        "id": f"gene_knowledge_db:{sheet}:{position}",
                    }
                ],
                "revision": revision,
                "updated_at": updated_at,
            },
            content={
                # Show the same normalized fallback content the generator uses,
                # rather than raw instruction columns or malformed legacy tails.
                "content_profile": "此前未见位点的基础回退预览",
                "intro": _clean_value(effective_section.get("intro"))
                or _row_value(row, "基因简介"),
                "mutation_analysis": _clean_value(
                    effective_section.get("mutation_analysis")
                )
                or _row_value(row, "基因变异解析"),
            },
        )
        entries.append(entry.model_dump())
    return entries


def _base_drug_narrative_entries(panel_id: str) -> list[dict[str, Any]]:
    provider = _load_base_gene_provider()
    if provider is None:
        return []
    path = _kb_base_path() / "gene_knowledge_db.xlsx"
    revision = _sha256_revision(path)
    updated_at = _updated_at(path)
    entries: list[dict[str, Any]] = []
    for row in provider.list_drug_narrative_entries():
        gene = _clean_value(row.get("gene")).upper()
        if not gene:
            continue
        c_hgvs = _clean_value(row.get("c_point"))
        p_hgvs = _clean_value(row.get("p_point"))
        drug_type = _clean_value(row.get("type")) or "benefit"
        drug_name = _clean_value(row.get("drug"))
        entry = KnowledgeEntry(
            entry_id=_stable_entry_id(
                "base_drug_narrative",
                gene,
                c_hgvs,
                p_hgvs,
                drug_type,
                drug_name,
                row.get("relation"),
            ),
            kind="drug",
            layer="base",
            panel_id=panel_id,
            gene=gene,
            c_hgvs=c_hgvs,
            p_hgvs=p_hgvs,
            match_scope=_match_scope(c_hgvs, p_hgvs),
            runtime_behavior="base_part3_drug_narrative_fallback",
            review={
                "status": "legacy_runtime",
                "scope": "source_row",
                "basis": "base_excel_legacy_runtime_source_row",
                "runtime_eligible": True,
                "secondary_review_status": "historical_not_row_bound",
            },
            provenance={
                "source_id": "gene_knowledge_db_drug_narrative",
                "source_type": "base_excel",
                "sheet": "用药提示解析",
                "source_refs": [
                    {
                        "type": "workbook_sheet",
                        "id": "gene_knowledge_db:用药提示解析",
                    }
                ],
                "revision": revision,
                "updated_at": updated_at,
            },
            content={
                "drug_type": drug_type,
                "drug_name": drug_name,
                "variant_level": _clean_value(row.get("level")),
                "relation": _clean_value(row.get("relation")),
                "clinical": _clean_value(row.get("clinical")),
            },
        )
        entries.append(entry.model_dump())
    return entries


def _base_targeted_drug_entries(
    panel_id: str,
    targeted_drug_rules: Optional[dict[str, Any]],
) -> list[dict[str, Any]]:
    df = _load_drug_db()
    if df is None:
        return []
    path = _kb_base_path() / "targeted_drug_db_public.xlsx"
    revision = _sha256_revision(path)
    updated_at = _updated_at(path)
    entries: list[dict[str, Any]] = []
    for position, (_, row) in enumerate(df.iterrows(), start=2):
        gene = _row_value(row, "基因名称").upper()
        if not gene or gene == "基因":
            continue
        c_hgvs = _row_value(row, "c_point")
        p_hgvs = _row_value(row, "p_point")
        event = _row_value(row, "扩增/缺失/融合/胚系/未见突变")
        source_db = _row_value(row, "source_db")
        entry = KnowledgeEntry(
            entry_id=_stable_entry_id(
                "base_drug", position, gene, c_hgvs, p_hgvs, event
            ),
            kind="targeted_drug",
            layer="base",
            panel_id=panel_id,
            gene=gene,
            c_hgvs=c_hgvs,
            p_hgvs=p_hgvs,
            match_scope=_match_scope(c_hgvs, p_hgvs, event),
            runtime_behavior=(
                "candidate_filtered_by_panel_policy"
                if targeted_drug_rules and targeted_drug_rules.get("enabled")
                else "disabled_by_panel_policy"
            ),
            review={
                "status": "legacy_runtime",
                "scope": "source_row",
                "basis": "base_excel_legacy_runtime_candidate",
                "runtime_eligible": True,
                "secondary_review_status": "governed_by_runtime_filters",
            },
            provenance={
                "source_id": "targeted_drug_db_public",
                "source_type": "base_excel",
                "source_db": source_db or None,
                "source_ref": _safe_source_ref(
                    source_db, _row_value(row, "source_ref")
                )
                or None,
                "sheet": "targeted_drug_tips",
                "row_number": position,
                "source_refs": [
                    {
                        "type": "workbook_row",
                        "id": f"targeted_drug_db_public:targeted_drug_tips:{position}",
                    }
                ],
                "revision": revision,
                "updated_at": updated_at,
            },
            content={
                "variant_level": _row_value(row, "变异等级"),
                "event": event,
                "benefit_drugs": _row_value(
                    row, "潜在获益靶向药物（证据等级）"
                ),
                "caution_drugs": _row_value(
                    row, "可能耐药或慎重药物（证据等级）"
                ),
                "cgi_evidence_level": _row_value(row, "cgi_evidence_level"),
                "civic_amp_category": _row_value(row, "civic_amp_category"),
                "cancer_context": _row_value(
                    row,
                    "cgi_primary_tumor_type_full_name",
                    "civic_disease",
                ),
            },
        )
        entries.append(entry.model_dump())
    return entries


def _overlay_entries(package: Any, kind: str) -> tuple[list[dict[str, Any]], list[str]]:
    path, data, warning = _resolve_overlay(package)
    if not path or not data:
        return [], [warning] if warning else []
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    origin_panel_id = str(source.get("panel") or package.panel_id)
    revision = _sha256_revision(path)
    source_type = str(source.get("source_type") or "panel_reviewed_overlay")
    rows = data.get("gene_sections" if kind == "gene" else "drug_sections") or []
    entries: list[dict[str, Any]] = []
    for index, raw_row in enumerate(rows, start=1):
        if not isinstance(raw_row, dict):
            continue
        gene = _clean_value(raw_row.get("gene")).upper()
        if not gene:
            continue
        c_hgvs = _clean_value(raw_row.get("c_hgvs"))
        p_hgvs = _clean_value(raw_row.get("p_hgvs"))
        applicability = _clean_value(raw_row.get("applicability"))
        content: dict[str, Any]
        if kind == "gene":
            first_pass = raw_row.get("first_pass_review")
            first_pass = first_pass if isinstance(first_pass, dict) else {}
            content = {
                "intro": _clean_value(raw_row.get("intro")),
                "mutation_description": _clean_value(
                    raw_row.get("mutation_description")
                    or raw_row.get("mutation_desc")
                ),
                "mutation_analysis": _clean_value(
                    raw_row.get("mutation_analysis")
                ),
                "refinement_note": _clean_value(raw_row.get("refinement_note")),
                "source_note": _clean_value(raw_row.get("source_note")),
                "source_url": _clean_value(raw_row.get("source_url")),
                "evidence_level": _clean_value(raw_row.get("evidence_level")),
                "cancer_scope": _clean_value(raw_row.get("cancer_scope")),
                "runtime_eligible": raw_row.get("runtime_eligible"),
                "first_pass_status": _clean_value(first_pass.get("status")),
                "first_pass_reviewer": _clean_value(first_pass.get("reviewer")),
                "first_pass_reviewer_type": _clean_value(
                    first_pass.get("reviewer_type")
                ),
                "first_pass_reviewed_at": _clean_value(
                    first_pass.get("reviewed_at")
                ),
                "first_pass_evidence_as_of": _clean_value(
                    first_pass.get("evidence_as_of")
                ),
                "first_pass_decision": _clean_value(first_pass.get("decision")),
                "first_pass_risk_level": _clean_value(
                    first_pass.get("risk_level")
                ),
                "secondary_review_status": _clean_value(
                    first_pass.get("secondary_review_status")
                ),
            }
        else:
            content = {
                "drug_type": _clean_value(raw_row.get("type")),
                "drug_name": _clean_value(raw_row.get("drug_name")),
                "header": _clean_value(raw_row.get("header")),
                "relation": _clean_value(raw_row.get("relation")),
                "clinical": _clean_value(raw_row.get("clinical")),
                "applicability": applicability,
            }
        row_origin_panel_id = _clean_value(raw_row.get("_origin_panel_id")) or origin_panel_id
        row_source_path = Path(_clean_value(raw_row.get("_source_path")) or str(path))
        row_revision = _clean_value(raw_row.get("_source_revision")) or revision
        review = _entry_review(data, raw_row, row_revision)
        effective = effective_governance(data, raw_row, kind)
        runtime_eligible = bool(effective["runtime_eligible"])
        content.update(
            {
                "evidence_level": effective["evidence_level"],
                "cancer_scope": effective["cancer_scope"],
                "runtime_eligible": runtime_eligible,
                "secondary_review_status": effective[
                    "secondary_review_status"
                ],
            }
        )
        entry = KnowledgeEntry(
            entry_id=_stable_entry_id(
                "overlay",
                row_origin_panel_id,
                kind,
                index,
                gene,
                c_hgvs,
                p_hgvs,
            ),
            kind=kind,
            layer="reviewed_overlay",
            panel_id=package.panel_id,
            gene=gene,
            c_hgvs=c_hgvs,
            p_hgvs=p_hgvs,
            match_scope=_match_scope(c_hgvs, p_hgvs, applicability),
            runtime_behavior=(
                "override_base_on_match"
                if runtime_eligible
                else "pending_secondary_review_not_loaded"
            ),
            review=review,
            provenance={
                "source_id": "panel_reviewed_part3_overlay",
                "source_type": _clean_value(raw_row.get("_source_type")) or source_type,
                "source_refs": structured_source_refs(data, raw_row, kind),
                "origin_panel_id": row_origin_panel_id,
                "shared_overlay": row_origin_panel_id != package.panel_id,
                "revision": row_revision,
                "updated_at": _updated_at(row_source_path),
            },
            content=content,
        )
        entries.append(entry.model_dump())
    return entries, []


def _targeted_drug_rule_entries(
    package: Any,
    context: Optional[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not context or not context.get("enabled"):
        return []
    origin_panel_id = str(context.get("source_panel_id") or package.panel_id)
    origin_package = _get_panel_package(origin_panel_id)
    path = origin_package.resolve_rule_file("drugs")
    try:
        rule_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        rule_data = {}
    revision = _sha256_revision(path)
    updated_at = _updated_at(path)
    shared = origin_panel_id != package.panel_id
    rows: list[dict[str, Any]] = []

    def _rule_text(value: Any) -> str:
        if isinstance(value, list):
            return " / ".join(_clean_value(item) for item in value if _clean_value(item))
        return _clean_value(value)

    def _append(raw: dict[str, Any], *, source_key: str, position: int) -> None:
        gene = _clean_value(raw.get("gene")).upper()
        if not gene:
            return
        c_hgvs = _rule_text(raw.get("c_hgvs"))
        p_hgvs = _rule_text(raw.get("p_hgvs"))
        applicability = _clean_value(raw.get("applicability"))
        governance = effective_governance(rule_data, raw, "targeted_drug")
        entry = KnowledgeEntry(
            entry_id=_stable_entry_id(
                "targeted_drug_rule",
                origin_panel_id,
                source_key,
                position,
                gene,
                c_hgvs,
                p_hgvs,
            ),
            kind="targeted_drug",
            layer="reviewed_overlay",
            panel_id=package.panel_id,
            gene=gene,
            c_hgvs=c_hgvs,
            p_hgvs=p_hgvs,
            match_scope=_match_scope(c_hgvs, p_hgvs, applicability),
            runtime_behavior=(
                "panel_targeted_drug_override"
                if governance["runtime_eligible"]
                else "governance_blocked_not_loaded"
            ),
            review={
                "status": governance["status"],
                "scope": "panel_rule_governance",
                "basis": governance["review_basis"],
                "runtime_eligible": governance["runtime_eligible"],
                "reviewer": governance["reviewer"],
                "reviewer_type": governance["reviewer_type"],
                "reviewed_at": governance["reviewed_at"],
                "evidence_as_of": governance["evidence_as_of"],
                "secondary_review_status": governance[
                    "secondary_review_status"
                ],
                "risk_level": governance["risk_level"],
            },
            provenance={
                "source_id": "panel_targeted_drug_rules",
                "source_type": "panel_rule_yaml",
                "origin_panel_id": origin_panel_id,
                "shared_overlay": shared,
                "source_refs": governance["source_refs"],
                "revision": revision,
                "updated_at": updated_at,
            },
            content={
                "variant_level": raw.get("variant_level") or "",
                "applicability": applicability,
                "benefit_drugs": raw.get("benefit_drugs") or "",
                "caution_drugs": raw.get("caution_drugs") or "",
                "clinical_significance": raw.get("clinical_significance") or "",
                "evidence_level": governance["evidence_level"],
                "cancer_scope": governance["cancer_scope"],
                "runtime_eligible": governance["runtime_eligible"],
                "secondary_review_status": governance[
                    "secondary_review_status"
                ],
            },
        )
        rows.append(entry.model_dump())

    for position, (gene, rule) in enumerate(
        sorted((context.get("overrides") or {}).items()),
        start=1,
    ):
        _append({"gene": gene, **dict(rule)}, source_key="gene_override", position=position)
    for position, rule in enumerate(
        context.get("reviewed_variant_overrides") or [],
        start=1,
    ):
        if isinstance(rule, dict):
            _append(rule, source_key="variant_override", position=position)
    return rows


def _entry_search_blob(entry: dict[str, Any]) -> str:
    searchable = {
        "gene": entry.get("gene"),
        "c_hgvs": entry.get("c_hgvs"),
        "p_hgvs": entry.get("p_hgvs"),
        "content": entry.get("content"),
        "source_db": (entry.get("provenance") or {}).get("source_db"),
    }
    return json.dumps(searchable, ensure_ascii=False, sort_keys=True).casefold()


def get_catalog_entries(
    *,
    panel_id: str,
    kind: str,
    layer: str = "all",
    search: str = "",
    gene: str = "",
    review_status: str = "all",
    match_scope: str = "all",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    if kind not in {"gene", "drug", "targeted_drug"}:
        raise ValueError("kind must be gene, drug, or targeted_drug")
    if layer not in {"all", "base", "reviewed_overlay"}:
        raise ValueError("invalid knowledge layer")
    if review_status not in {
        "all",
        "approved_for_runtime",
        "provisional_runtime",
        "legacy_runtime",
        "needs_review",
        "rejected",
        "superseded",
        "not_recorded",
    }:
        raise ValueError("invalid review status")
    if match_scope not in {"all", "gene", "variant", "event"}:
        raise ValueError("invalid match scope")
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError("page must be >= 1 and page_size must be between 1 and 100")
    if len(search) > 100:
        raise ValueError("search must be at most 100 characters")
    package = _get_panel_package(panel_id)
    targeted_context = load_targeted_drug_rule_context(package)
    if kind == "gene":
        base_entries = _base_gene_entries(package.panel_id)
        overlay_entries, warnings = _overlay_entries(package, kind)
    elif kind == "drug":
        base_entries = _base_drug_narrative_entries(package.panel_id)
        overlay_entries, warnings = _overlay_entries(package, kind)
    else:
        base_entries = _base_targeted_drug_entries(
            package.panel_id,
            targeted_context,
        )
        overlay_entries = _targeted_drug_rule_entries(
            package,
            targeted_context,
        )
        warnings = []
    entries = base_entries + overlay_entries

    gene_norm = gene.strip().upper()
    needle = search.strip().casefold()
    filtered: list[dict[str, Any]] = []
    for entry in entries:
        if layer != "all" and entry["layer"] != layer:
            continue
        if gene_norm and entry["gene"] != gene_norm:
            continue
        if review_status != "all" and entry["review"]["status"] != review_status:
            continue
        if match_scope != "all" and entry["match_scope"] != match_scope:
            continue
        if needle and needle not in _entry_search_blob(entry):
            continue
        filtered.append(entry)

    layer_priority = {"reviewed_overlay": 0, "base": 1}
    filtered.sort(
        key=lambda entry: (
            entry["gene"],
            layer_priority.get(entry["layer"], 9),
            entry.get("c_hgvs") or "",
            entry.get("p_hgvs") or "",
            entry["entry_id"],
        )
    )
    total = len(filtered)
    start = (page - 1) * page_size
    page_rows = filtered[start : start + page_size]

    return {
        "panel": _panel_summary(package),
        "kind": kind,
        "rows": page_rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "facets": {
            "layers": dict(Counter(row["layer"] for row in filtered)),
            "review_statuses": dict(
                Counter(row["review"]["status"] for row in filtered)
            ),
            "match_scopes": dict(
                Counter(row["match_scope"] for row in filtered)
            ),
        },
        "warnings": [warning for warning in warnings if warning],
    }


def _important_gene_denominator(package: Any) -> tuple[str, set[str]]:
    try:
        coverage_path = package.resolve_rule_file("knowledge_coverage")
        coverage_raw = yaml.safe_load(coverage_path.read_text(encoding="utf-8")) or {}
        reportable = coverage_raw.get("reportable_genes")
        if isinstance(reportable, list):
            genes = {
                str(value).strip().upper()
                for value in reportable
                if str(value).strip()
            }
            if genes:
                return "reportable_genes", genes
    except Exception:
        pass
    try:
        raw = yaml.safe_load(
            package.resolve_rule_file("panel_rules").read_text(encoding="utf-8")
        ) or {}
    except Exception:
        return "", set()
    values = raw.get("crc_important_genes") if isinstance(raw, dict) else None
    # Lung/endometrial pilots currently reuse a legacy CRC rule file for their
    # renderer. That reuse is not a declaration of their Panel gene universe,
    # so it must never become a misleading coverage denominator in the UI.
    if str(package.panel_id).startswith("crc_") and isinstance(values, list):
        return "crc_important_genes", {
            str(value).strip().upper() for value in values if str(value).strip()
        }
    return "", set()


def _drug_candidate_disposition(
    package: Any,
    drug_df: Optional[pd.DataFrame],
    targeted_context: Optional[dict[str, Any]],
    denominator: set[str],
) -> dict[str, Any]:
    """Classify DB candidates by the same production safety dimensions.

    This is a catalog/audit view, not a second drug decision engine. It makes
    clear that a public DB gene absent from a curated override is usually
    governed by position/cancer/evidence filters, rather than "not migrated".
    """
    if drug_df is None:
        return {}
    settings_path = _project_root() / "config" / "settings.yaml"
    try:
        raw_settings = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
        knowledge_bases = raw_settings.get("knowledge_bases") or {}
        targeted_drug_db = knowledge_bases.get("targeted_drug_db") or {}
        filters = targeted_drug_db.get("filters") or {}
    except Exception:
        filters = {}
    evidence = filters.get("evidence") or {}
    cgi_min = int(evidence.get("cgi_min_rank", 0) or 0)
    civic_min = int(evidence.get("civic_min_rank", 0) or 0)
    require_position = bool(filters.get("require_position_match", False))
    allowed_sources = {
        str(value).strip().upper()
        for value in ((targeted_context or {}).get("allowed_source_dbs") or [])
        if str(value).strip()
    }
    allow_internal = bool((targeted_context or {}).get("allow_internal_rows", False))
    generic_internal_reject: set[str] = set()
    reject_all_positionless_internal = False
    for rule in (targeted_context or {}).get("applicability_rules") or []:
        if not isinstance(rule, dict) or not rule.get("reject_when_db_position_missing"):
            continue
        sources = {str(value).strip().upper() for value in rule.get("sources") or []}
        if "INTERNAL" in sources:
            scoped_genes = {
                str(value).strip().upper()
                for value in rule.get("genes") or []
                if str(value).strip()
            }
            if scoped_genes:
                generic_internal_reject.update(scoped_genes)
            else:
                reject_all_positionless_internal = True

    cgi_rank_map = {
        "fda guidelines": 5,
        "nccn guidelines": 5,
        "nccn/cap guidelines": 5,
        "cpic guidelines": 5,
        "european leukemianet guidelines": 5,
        "late trials": 4,
        "clinical trials": 3,
        "early trials": 2,
        "case report": 1,
        "pre-clinical": 0,
    }

    def cgi_rank(value: Any) -> int:
        parts = [
            part.strip().lower()
            for part in re.split(r"[;,]", str(value or ""))
            if part.strip()
        ]
        return max((cgi_rank_map.get(part, -1) for part in parts), default=-1)

    def civic_rank(value: Any) -> int:
        text = str(value or "").strip().lower()
        if "tier i" in text:
            return 5 if "level a" in text else 4
        if "tier ii" in text:
            return 3 if "level c" in text else 2
        if "tier iii" in text:
            return 1
        if "tier iv" in text:
            return 0
        return -1

    row_counts: Counter[str] = Counter()
    genes_by_status: dict[str, set[str]] = {}
    all_genes: set[str] = set()
    for _, row in drug_df.iterrows():
        gene = _clean_value(row.get("基因名称")).upper()
        if not gene or (denominator and gene not in denominator):
            continue
        all_genes.add(gene)
        source = _clean_value(row.get("source_db")).upper()
        c_hgvs = _clean_value(row.get("c_point"))
        p_hgvs = _clean_value(row.get("p_point"))
        status = "runtime_eligible"
        if allowed_sources and source not in allowed_sources:
            status = "filtered_source"
        elif source == "INTERNAL":
            if not allow_internal:
                status = "filtered_source"
            elif (
                reject_all_positionless_internal or gene in generic_internal_reject
            ) and not (c_hgvs or p_hgvs):
                status = "filtered_internal_generic"
        elif source in {"CGI", "CIVIC"}:
            if require_position and not (c_hgvs or p_hgvs):
                status = "filtered_missing_position"
            elif source == "CGI":
                tumor_types = {
                    value.strip().upper()
                    for value in _clean_value(row.get("cgi_primary_tumor_type")).split(";")
                    if value.strip()
                }
                if tumor_types and "COREAD" not in tumor_types:
                    status = "filtered_cancer_mismatch"
                else:
                    rank = cgi_rank(row.get("cgi_evidence_level"))
                    if rank >= 0 and rank < cgi_min:
                        status = "filtered_low_evidence"
            else:
                disease = _clean_value(row.get("civic_disease")).lower()
                if disease and not any(
                    keyword in disease for keyword in ("colorectal", "colon", "rectal")
                ):
                    status = "filtered_cancer_mismatch"
                else:
                    rank = civic_rank(row.get("civic_amp_category"))
                    if rank >= 0 and rank < civic_min:
                        status = "filtered_low_evidence"
        row_counts[status] += 1
        genes_by_status.setdefault(status, set()).add(gene)

    eligible_genes = genes_by_status.get("runtime_eligible", set())
    filtered_only = all_genes - eligible_genes
    try:
        coverage_rule = yaml.safe_load(
            package.resolve_rule_file("knowledge_coverage").read_text(encoding="utf-8")
        ) or {}
    except Exception:
        coverage_rule = {}
    review_disposition = coverage_rule.get("drug_review_disposition") or {}
    return {
        "database_candidate_genes": len(all_genes),
        "runtime_eligible_database_genes": len(eligible_genes),
        "runtime_eligible_database_gene_list": sorted(eligible_genes),
        "database_only_filtered_genes": len(filtered_only),
        "database_only_filtered_gene_list": sorted(filtered_only),
        "filter_reason_row_counts": dict(row_counts),
        "historical_review": dict(review_disposition),
        "pending_medical_review_rows": int(review_disposition.get("pending_rows", 0) or 0),
        "pending_medical_review_genes": [],
    }


def get_catalog_coverage(panel_id: str) -> dict[str, Any]:
    package = _get_panel_package(panel_id)
    panel = _panel_summary(package)
    _sheet, gene_df = _gene_analysis_sheet()
    gene_col = _gene_column(gene_df)
    base_gene_source_rows = len(gene_df) if gene_df is not None else 0
    base_genes = {
        str(value).strip().upper()
        for value in (gene_df[gene_col].tolist() if gene_df is not None and gene_col else [])
        if str(value).strip() and str(value).strip().upper() != "基因"
    }
    drug_df = _load_drug_db()
    targeted_drug_genes = {
        str(value).strip().upper()
        for value in (
            drug_df["基因名称"].tolist()
            if drug_df is not None and "基因名称" in drug_df.columns
            else []
        )
        if str(value).strip() and str(value).strip().upper() != "基因"
    }
    provider = _load_base_gene_provider()
    base_drug_narratives = (
        provider.list_drug_narrative_entries() if provider is not None else []
    )
    base_drug_narrative_genes = {
        str(row.get("gene") or "").strip().upper()
        for row in base_drug_narratives
        if str(row.get("gene") or "").strip()
    }
    targeted_context = load_targeted_drug_rule_context(package)
    targeted_rule_entries = _targeted_drug_rule_entries(
        package,
        targeted_context,
    )

    overlay_path, overlay, warning = _resolve_overlay(package)
    overlay_revision = (
        _sha256_revision(overlay_path) if overlay_path and overlay else ""
    )
    gene_rows = [
        row
        for row in ((overlay or {}).get("gene_sections") or [])
        if isinstance(row, dict) and str(row.get("gene") or "").strip()
    ]
    drug_rows = [
        row
        for row in ((overlay or {}).get("drug_sections") or [])
        if isinstance(row, dict) and str(row.get("gene") or "").strip()
    ]
    overlay_genes = {str(row["gene"]).strip().upper() for row in gene_rows}
    overlay_drug_genes = {str(row["gene"]).strip().upper() for row in drug_rows}
    gene_governance = [
        effective_governance(overlay, row, "gene") for row in gene_rows
    ]
    drug_governance = [
        effective_governance(overlay, row, "drug") for row in drug_rows
    ]
    runtime_overlay_genes = {
        str(row["gene"]).strip().upper()
        for row, governance in zip(gene_rows, gene_governance)
        if governance["runtime_eligible"]
    }
    gene_level_rows = sum(
        not (_clean_value(row.get("c_hgvs")) or _clean_value(row.get("p_hgvs")))
        for row in gene_rows
    )
    variant_level_rows = len(gene_rows) - gene_level_rows
    denominator_name, denominator = _important_gene_denominator(package)
    either = base_genes | runtime_overlay_genes
    covered = len(denominator & either) if denominator else 0
    review_counts = Counter(
        _entry_review(overlay, row, overlay_revision)["status"]
        for row in gene_rows + drug_rows
    )
    all_governance = gene_governance + drug_governance
    structured_source_rows = sum(
        bool(item["source_refs"]) for item in all_governance
    )
    evidence_level_rows = sum(
        bool(item["evidence_level"]) for item in all_governance
    )
    cancer_scope_rows = sum(
        bool(item["cancer_scope"]) for item in all_governance
    )
    secondary_complete_rows = sum(
        item["secondary_review_status"]
        in {"completed", "approved", "report_group_approved"}
        for item in all_governance
    )
    runtime_overlay_drug_genes = {
        str(row["gene"]).strip().upper()
        for row, governance in zip(drug_rows, drug_governance)
        if governance["runtime_eligible"]
    }
    pending_review_genes = {
        str(row["gene"]).strip().upper()
        for row, governance in zip(
            gene_rows + drug_rows,
            all_governance,
        )
        if governance["status"] in {"provisional_runtime", "needs_review"}
    }
    panel_rule_genes = {
        str(row.get("gene") or "").strip().upper()
        for row in targeted_rule_entries
        if str(row.get("gene") or "").strip()
    }
    approved_panel_rule_genes = {
        str(row.get("gene") or "").strip().upper()
        for row in targeted_rule_entries
        if str(row.get("gene") or "").strip()
        and (row.get("review") or {}).get("status") == "approved_for_runtime"
    }
    panel_rule_status_counts = Counter(
        str((row.get("review") or {}).get("status") or "not_recorded")
        for row in targeted_rule_entries
    )
    runtime_drug_genes = (
        runtime_overlay_drug_genes
        | panel_rule_genes
        | base_drug_narrative_genes
    )
    candidate_disposition = _drug_candidate_disposition(
        package,
        drug_df,
        targeted_context,
        denominator,
    )
    gene_explanation_missing = denominator - either if denominator else set()
    runtime_content_quality = (
        profile_panel_runtime_content(_project_root(), package, denominator)
        if denominator
        else None
    )
    clinical_status_counts = Counter(review_counts)
    clinical_status_counts.update(panel_rule_status_counts)
    clinical_registry = _clinical_release_registry(_project_root())
    clinical_release_readiness = _clinical_readiness(
        clinical_registry,
        panel_id,
        clinical_status_counts,
        _secondary_review_receipt(
            _project_root(),
            clinical_registry,
            panel_id,
        ),
    )
    if runtime_content_quality and runtime_content_quality["generic_fallback_count"]:
        clinical_release_readiness["status"] = "BLOCKED"
        clinical_release_readiness["blocking_reasons"].append(
            "generic_gene_fallback_requires_content_review"
        )
        clinical_release_readiness["content_depth"] = {
            "generic_fallback_count": runtime_content_quality[
                "generic_fallback_count"
            ],
            "specific_explanation_percent": runtime_content_quality[
                "specific_explanation_percent"
            ],
        }

    return {
        "panel": panel,
        "base": {
            "gene_source_rows": base_gene_source_rows,
            "gene_entries": len(base_genes),
            "unique_genes": len(base_genes),
            "drug_rows": len(base_drug_narratives),
            "drug_unique_genes": len(base_drug_narrative_genes),
            "targeted_drug_rows": len(drug_df) if drug_df is not None else 0,
            "targeted_drug_unique_genes": len(targeted_drug_genes),
        },
        "reviewed_overlay": {
            "available": bool(overlay),
            "gene_rows": len(gene_rows),
            "unique_genes": len(overlay_genes),
            "gene_level_rows": gene_level_rows,
            "variant_level_rows": variant_level_rows,
            "drug_rows": len(drug_rows),
            "drug_unique_genes": len(overlay_drug_genes),
            "targeted_drug_rule_rows": len(targeted_rule_entries),
            "targeted_drug_rule_unique_genes": len(
                {row["gene"] for row in targeted_rule_entries}
            ),
            "targeted_drug_applicability_rule_rows": len(
                (targeted_context or {}).get("applicability_rules") or []
            ),
            "extra_reference_rows": len((overlay or {}).get("extra_references") or []),
            "review_status_counts": dict(review_counts),
        },
        "overlap": {
            "genes_in_both": len(base_genes & overlay_genes),
            "overlay_only_genes": len(overlay_genes - base_genes),
        },
        "declared_gene_coverage": {
            "denominator_name": denominator_name,
            "total": len(denominator),
            "base_covered": len(denominator & base_genes),
            "overlay_covered": len(denominator & runtime_overlay_genes),
            "either_covered": covered,
            "percent": round(100.0 * covered / len(denominator), 2)
            if denominator
            else None,
            "label": (
                f"{denominator_name} 覆盖率" if denominator_name else "未声明覆盖分母"
            ),
        },
        "knowledge_coverage_contract": {
            "denominator_name": denominator_name,
            "total_genes": len(denominator),
            "gene_explanation_complete": not gene_explanation_missing,
            "gene_explanation_missing_count": len(gene_explanation_missing),
            "gene_explanation_missing_genes": sorted(gene_explanation_missing),
            "runtime_drug_genes": len(denominator & runtime_drug_genes),
            "explicitly_approved_drug_genes": len(
                denominator & approved_panel_rule_genes
            ),
            "explicit_panel_rule_genes": len(denominator & panel_rule_genes),
            "panel_rule_status_counts": dict(panel_rule_status_counts),
            "runtime_content_quality": runtime_content_quality,
            "clinical_release_readiness": clinical_release_readiness,
            "multidimensional_coverage": {
                "gene_explanation": {
                    "total": len(denominator),
                    "covered": covered,
                    "percent": round(100.0 * covered / len(denominator), 2)
                    if denominator
                    else None,
                },
                "review_governance": {
                    "total_overlay_rows": len(all_governance),
                    "status_counts": dict(review_counts),
                    "standardized_rows": len(all_governance)
                    - review_counts.get("not_recorded", 0),
                    "standardized_percent": round(
                        100.0
                        * (
                            len(all_governance)
                            - review_counts.get("not_recorded", 0)
                        )
                        / len(all_governance),
                        2,
                    )
                    if all_governance
                    else 100.0,
                    "secondary_review_complete_rows": secondary_complete_rows,
                    "secondary_review_complete_percent": round(
                        100.0 * secondary_complete_rows / len(all_governance), 2
                    )
                    if all_governance
                    else 100.0,
                    "pending_secondary_review_genes": sorted(
                        pending_review_genes
                    ),
                },
                "source_provenance": {
                    "structured_source_rows": structured_source_rows,
                    "structured_source_percent": round(
                        100.0 * structured_source_rows / len(all_governance), 2
                    )
                    if all_governance
                    else 100.0,
                    "evidence_level_rows": evidence_level_rows,
                    "evidence_level_percent": round(
                        100.0 * evidence_level_rows / len(all_governance), 2
                    )
                    if all_governance
                    else 100.0,
                    "cancer_scope_rows": cancer_scope_rows,
                    "cancer_scope_percent": round(
                        100.0 * cancer_scope_rows / len(all_governance), 2
                    )
                    if all_governance
                    else 100.0,
                },
                "specificity": {
                    "gene_level_rows": gene_level_rows,
                    "variant_level_rows": variant_level_rows,
                    "event_scoped_drug_rows": sum(
                        bool(_clean_value(row.get("applicability")))
                        for row in drug_rows
                    ),
                },
                "drug_actionability": {
                    "runtime_drug_genes": len(
                        denominator & runtime_drug_genes
                    ),
                    "panel_rule_genes": len(
                        denominator & panel_rule_genes
                    ),
                    "runtime_database_genes": int(
                        candidate_disposition.get(
                            "runtime_eligible_database_genes", 0
                        )
                        or 0
                    ),
                    "filtered_database_genes": int(
                        candidate_disposition.get(
                            "database_only_filtered_genes", 0
                        )
                        or 0
                    ),
                },
            },
            "drug_candidate_disposition": candidate_disposition,
            "status_definitions": {
                "runtime_drug": "生成器可使用基础库药物解析、Panel drug section 或 variant rule",
                "runtime_eligible_database": (
                    "公共/内部库行满足生产位点、癌种、证据与来源门槛；"
                    "仅在实际变异匹配时输出"
                ),
                "database_only_filtered": "候选行全部被生产安全规则排除，不是待迁移用药结论",
                "no_candidate_evidence": "当前候选库未提供药物关联；不等同于知识迁移失败",
            },
        },
        "warnings": [warning] if warning else [],
    }


def reload_all() -> None:
    """Force invalidate all caches so next access re-reads from disk."""
    global _gene_kb_df, _gene_kb_mtime, _drug_db_df, _drug_db_mtime
    global _immune_df, _immune_mtime, _overlay_cache
    global _base_gene_provider, _base_gene_provider_mtime
    _gene_kb_df = None
    _gene_kb_mtime = 0.0
    _drug_db_df = None
    _drug_db_mtime = 0.0
    _immune_df = None
    _immune_mtime = 0.0
    _overlay_cache = {}
    _base_gene_provider = None
    _base_gene_provider_mtime = 0.0
