"""Non-mutating product views of superset NGS workbooks.

The Excel remains the evidence source. Membership flags do not encode variant
classification, PD-L1 testing, or a positive CNV result.
"""

from __future__ import annotations

import copy
import re
from typing import Any


def scope_panel_excel(excel_data: Any, panel_package: Any) -> Any:
    contract = (getattr(panel_package, "raw", None) or {}).get("derived_input") or {}
    column = str(contract.get("membership_column") or "").strip()
    if not column:
        return excel_data
    genes = {str(gene).strip().upper() for gene in contract.get("genes") or []}
    if not genes:
        raise ValueError("Panel membership contract has no gene list")
    view = copy.copy(excel_data)
    view.table_data = dict(excel_data.table_data)
    view.metadata = dict(excel_data.metadata)
    counts = {}
    for table in ("Variations", "Hereditary_tumor"):
        rows = excel_data.get_table_data(table) or []
        # ExcelReader omits blank cells from individual row dictionaries. A
        # blank membership cell is an ordinary non-member, not a missing
        # worksheet column; the recorded header also covers all-blank flags.
        declared_columns = (excel_data.metadata.get("table_columns") or {}).get(table)
        columns = (
            set(declared_columns)
            if declared_columns is not None
            else {key for row in rows for key in row}
        )
        if (rows or declared_columns is not None) and column not in columns:
            raise ValueError(
                f"{table}: required product membership column is missing: {column}"
            )
        selected = [
            row
            for row in rows
            if row.get(column) in (1, "1", True)
            and str(row.get("Gene_Symbol") or "").strip().upper() in genes
        ]
        if table == "Variations":
            # A numeric membership 1 is never an ACMG/AMP class. The legacy
            # mapper's gene-based fallback must not classify annotation rows.
            from reportgen.core.template_bridge_358 import _explicit_gene_class

            selected = [
                row for row in selected if _explicit_gene_class(row.get("ExistIn552"))
            ]
        view.table_data[table] = selected
        counts[table] = {"source_rows": len(rows), "member_rows": len(selected)}
    # CNV/fusion have different laboratory flags. Scope their observations by
    # assayed genes without modifying ExistIn137, calls, copy numbers or values.
    for table in ("Cnv", "Fusion", "Hotspot"):
        if table not in view.table_data:
            continue
        selected = []
        for row in excel_data.get_table_data(table) or []:
            symbols = set()
            for key in (
                "Gene_Symbol",
                "Gene",
                "gene",
                "Gene1",
                "Gene2",
                "gene1",
                "gene2",
                "Gene_Name",
                "Fusion_Gene",
                "基因",
                "基因1",
                "基因2",
                "融合基因1",
                "融合基因2",
            ):
                symbols.update(
                    re.findall(r"[A-Z][A-Z0-9]+", str(row.get(key) or "").upper())
                )
            if symbols & genes:
                selected.append(row)
        view.table_data[table] = selected
    view.metadata["panel_input_scope"] = {
        "panel_id": panel_package.panel_id,
        "membership_column": column,
        "tables": counts,
    }
    return view
