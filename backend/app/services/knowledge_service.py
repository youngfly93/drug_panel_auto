"""
Knowledge base service: wraps upstream GeneKnowledgeProvider
for web browsing of gene knowledge, drug mappings, and immune gene lists.
"""

import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.config import settings

# No hardcoded paths — upstream root comes from settings

# Cached DataFrames with mtime tracking for auto-refresh
_gene_kb_df: Optional[dict[str, pd.DataFrame]] = None
_gene_kb_mtime: float = 0.0
_drug_db_df: Optional[pd.DataFrame] = None
_drug_db_mtime: float = 0.0
_immune_df: Optional[pd.DataFrame] = None
_immune_mtime: float = 0.0


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


def _load_drug_db() -> Optional[pd.DataFrame]:
    global _drug_db_df, _drug_db_mtime

    path = _kb_base_path() / "targeted_drug_db_public.xlsx"
    current_mtime = _file_mtime(path)

    if _drug_db_df is not None and current_mtime == _drug_db_mtime:
        return _drug_db_df

    if not path.exists():
        return None

    try:
        _drug_db_df = pd.read_excel(path, dtype=str).fillna("")
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
        mask = df.apply(lambda row: row.astype(str).str.contains(search, case=False, na=False).any(), axis=1)
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
    kb = _load_gene_kb()
    # Try to find the gene analysis sheet
    for sheet_name in kb:
        if "变异解析" in sheet_name or "gene" in sheet_name.lower():
            return _df_to_records(kb[sheet_name], page, page_size, search)

    # Fallback: use first sheet
    if kb:
        first_key = next(iter(kb))
        return _df_to_records(kb[first_key], page, page_size, search)

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

    gene_count = 0
    for df in kb.values():
        gene_count = max(gene_count, len(df))

    return {
        "gene_knowledge": {"sheets": len(kb), "total_rows": gene_count},
        "drug_mappings": {"total_rows": len(drug_df) if drug_df is not None else 0},
        "immune_genes": {"total_rows": len(immune_df) if immune_df is not None else 0},
    }


def reload_all() -> None:
    """Force invalidate all caches so next access re-reads from disk."""
    global _gene_kb_df, _gene_kb_mtime, _drug_db_df, _drug_db_mtime, _immune_df, _immune_mtime
    _gene_kb_df = None
    _gene_kb_mtime = 0.0
    _drug_db_df = None
    _drug_db_mtime = 0.0
    _immune_df = None
    _immune_mtime = 0.0
