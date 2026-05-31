#!/usr/bin/env python3
"""
Template Bridge for 358-Gene Colorectal Cancer Reports.

This module bridges the gap between the existing reportgen data layer
and the Jinja2 template requirements for the 358-gene panel.

Key responsibilities:
1. Fix ExistIn552 filtering (numeric 1/0 vs Chinese labels)
2. Generate 'variants' table with template-expected columns
3. Generate 'summary_variants' table
4. Generate 'undetected_genes' table
5. Add MSI/TMB summary fields

Python 3.9 compatible.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import yaml

from reportgen.knowledge import GeneKnowledgeProvider
from reportgen.core.validation import build_msi_fields, build_tmb_fields
from reportgen.models.excel_data import ExcelDataSource
from reportgen.models.report_data import ReportData
from reportgen.utils.hgvs_utils import infer_variant_type_cn
from reportgen.utils.text_utils import norm_text as _norm_text

# Panel gene definitions for 358-gene colorectal cancer panel.
#
# Defaults are kept in-code for backwards compatibility. For production, keep
# the rule sets in `panels/<panel_id>/rules/crc.yaml` so that medical "口径"
# updates do not require a code release.
_DEFAULT_CLASS_I_GENES = {
    "KRAS",
    "NRAS",
    "BRAF",
    "PIK3CA",
    "ERBB2",
    "HER2",
    "MLH1",
    "MSH2",
    "MSH6",
    "PMS2",
    "EPCAM",
}

_DEFAULT_CLASS_II_GENES = {
    "APC",
    "TP53",
    "SMAD4",
    "PTEN",
    "STK11",
    "FBXW7",
}

_DEFAULT_CRC_IMPORTANT_GENES = {
    "KRAS",
    "NRAS",
    "BRAF",
    "MLH1",
    "MSH2",
    "MSH6",
    "PMS2",
    "HER2",
    "NTRK1",
    "NTRK2",
    "NTRK3",
    "TP53",
    "APC",
    "PIK3CA",
    "SMAD4",
    "FBXW7",
    "RNF43",
    "CTNNB1",
    "KMT2D",
    "ACVR2A",
    "TCF7L2",
    "ATM",
    "FAT4",
    "KMT2C",
    "ARID1A",
    "LRP1B",
    "PTEN",
    "FAT1",
    "ZFHX3",
    "AMER1",
    "GNAS",
    "ERBB3",
    "PTPRT",
    "NF1",
    "MUTYH",
    "ERBB2",
    "SETD2",
}

_DEFAULT_IMMUNE_POSITIVE_GENES = {
    "MLH1",
    "MSH2",
    "MSH6",
    "PMS2",
    "POLE",
    "POLD1",
    "CD274",
    "PDCD1LG2",
    "TET1",
    "PMS1",
    "ERCC2",
    "ERCC3",
    "ERCC4",
    "ERCC5",
    "BRCA1",
    "MRE11A",
    "NBN",
    "RAD50",
    "RAD51",
    "RAD51B",
    "RAD51D",
    "RAD52",
    "RAD54L",
    "BRCA2",
    "BRIP1",
    "FANCA",
    "FANCC",
    "PALB2",
    "RAD51C",
    "BLM",
    "ATM",
    "ATR",
    "CHEK1",
    "CHEK2",
    "MDC1",
    "MUTYH",
    "PARP1",
    "RECQL4",
    "ARID1A",
    "ATRX",
    "FANCM",
    "PRKDC",
    "CDK12",
    "MLH3",
    "MSH3",
    "FANCI",
    "ARID1B",
    "ARID2",
    "KRAS",
    "SERPINB3",
    "SERPINB4",
    "PBRM1",
    "TP53",
}

_DEFAULT_IMMUNE_NEGATIVE_GENES = {
    "PTEN",
    "JAK1",
    "JAK2",
    "B2M",
    "CTNNB1",
    "KEAP1",
    "EGFR",
    "ALK",
    "MET",
    "STK11",
    "IFNGR1",
    "IFNGR2",
}

_DEFAULT_IMMUNE_HYPERPROGRESSION_GENES = {
    "MDM2",
    "MDM4",
    "DNMT3A",
    "EGFR",
    "CCND1",
    "FGF3",
    "FGF4",
    "FGF19",
}

_DEFAULT_IMMUNE_POSITIVE_ROWS = [
    {"key": "MLH1", "genes": ["MLH1"], "mode": "direct"},
    {"key": "MSH2", "genes": ["MSH2"], "mode": "direct"},
    {"key": "MSH6", "genes": ["MSH6"], "mode": "direct"},
    {"key": "PMS2", "genes": ["PMS2"], "mode": "direct"},
    {"key": "POLE", "genes": ["POLE"], "mode": "direct"},
    {"key": "POLD1", "genes": ["POLD1"], "mode": "direct"},
    {"key": "CD274", "genes": ["CD274"], "mode": "direct"},
    {"key": "PDCD1LG2", "genes": ["PDCD1LG2"], "mode": "direct"},
    {"key": "PBRM1", "genes": ["PBRM1"], "mode": "direct"},
    {"key": "KRAS", "genes": ["KRAS"], "mode": "direct"},
    {"key": "KRAS_TP53", "genes": ["TP53", "KRAS"], "mode": "co_mutation"},
    {"key": "TET1", "genes": ["TET1"], "mode": "direct"},
    {"key": "SERPINB3", "genes": ["SERPINB3"], "mode": "direct"},
    {"key": "SERPINB4", "genes": ["SERPINB4"], "mode": "direct"},
    {
        "key": "DDR",
        "genes": [
            "ATM",
            "ATR",
            "BRCA1",
            "BRCA2",
            "PALB2",
            "CHEK2",
            "ARID1A",
            "ATRX",
            "CDK12",
            "FANCI",
            "FANCM",
            "MRE11A",
            "NBN",
            "RAD50",
            "RAD51",
        ],
        "mode": "gene_group",
    },
]

_DEFAULT_IMMUNE_NEGATIVE_ROWS = [
    {"key": "PTEN", "genes": ["PTEN"], "mode": "direct"},
    {"key": "JAK1", "genes": ["JAK1"], "mode": "direct"},
    {"key": "JAK2", "genes": ["JAK2"], "mode": "direct"},
    {"key": "B2M", "genes": ["B2M"], "mode": "direct"},
    {"key": "CTNNB1", "genes": ["CTNNB1"], "mode": "direct"},
    {
        "key": "EGFR_L858R",
        "genes": ["EGFR"],
        "mode": "variant_pattern",
        "patterns": ["L858R", "EX19"],
    },
    {"key": "ALK", "genes": ["ALK"], "mode": "direct"},
    {"key": "MET", "genes": ["MET"], "mode": "direct"},
    {"key": "STK11", "genes": ["STK11"], "mode": "direct"},
    {"key": "KRAS_STK11", "genes": ["KRAS", "STK11"], "mode": "co_mutation"},
    {"key": "KEAP1", "genes": ["KEAP1"], "mode": "direct"},
    {"key": "IFNGR12", "genes": ["IFNGR1", "IFNGR2"], "mode": "gene_group"},
]

_DEFAULT_IMMUNE_HYPERPROGRESSION_ROWS = [
    {"key": "MDM2", "genes": ["MDM2"], "mode": "direct"},
    {"key": "MDM4", "genes": ["MDM4"], "mode": "direct"},
    {"key": "DNMT3A", "genes": ["DNMT3A"], "mode": "direct"},
    {"key": "EGFR_AMP", "genes": ["EGFR"], "mode": "cnv_amp", "match": "扩增"},
    {"key": "CCND1", "genes": ["CCND1"], "mode": "direct"},
    {"key": "FGF3", "genes": ["FGF3"], "mode": "direct"},
    {"key": "FGF4", "genes": ["FGF4"], "mode": "direct"},
    {"key": "FGF19", "genes": ["FGF19"], "mode": "direct"},
]

_DEFAULT_PANEL_DISPLAY_GENES = [
    {"name": "BRAF", "transcript": "NM_004333.4", "chromosome": "7"},
    {"name": "ERBB2", "transcript": "NM_004448.4", "chromosome": "17"},
    {"name": "NRAS", "transcript": "NM_002524.5", "chromosome": "1"},
    {"name": "PIK3CA", "transcript": "NM_006218.4", "chromosome": "3"},
    {"name": "SMAD4", "transcript": "NM_005359.6", "chromosome": "18"},
    {"name": "MLH1", "transcript": "NM_000249.4", "chromosome": "3"},
    {"name": "MSH2", "transcript": "NM_000251.3", "chromosome": "2"},
    {"name": "MSH6", "transcript": "NM_000179.3", "chromosome": "2"},
    {"name": "PMS2", "transcript": "NM_000535.7", "chromosome": "7"},
    {"name": "PTEN", "transcript": "NM_000314.8", "chromosome": "10"},
    {"name": "AKT1", "transcript": "NM_001014431.2", "chromosome": "14"},
    {"name": "EGFR", "transcript": "NM_005228.5", "chromosome": "7"},
    {"name": "MET", "transcript": "NM_000245.4", "chromosome": "7"},
    {"name": "RET", "transcript": "NM_020975.6", "chromosome": "10"},
    {"name": "ROS1", "transcript": "NM_002944.2", "chromosome": "6"},
    {"name": "ALK", "transcript": "NM_004304.5", "chromosome": "2"},
    {"name": "KRAS", "transcript": "NM_033360.4", "chromosome": "12"},
    {"name": "APC", "transcript": "NM_000038.6", "chromosome": "5"},
    {"name": "TP53", "transcript": "NM_000546.6", "chromosome": "17"},
]

_DEFAULT_NCCN_RESULT_ROWS = [
    {"key": "EGFR_EX18", "genes": ["EGFR"], "match": "外显子18"},
    {"key": "EGFR_EX19", "genes": ["EGFR"], "match": "外显子19"},
    {"key": "EGFR_EX20", "genes": ["EGFR"], "match": "外显子20"},
    {"key": "EGFR_EX21", "genes": ["EGFR"], "match": "外显子21"},
    {"key": "KRAS_EX2", "genes": ["KRAS"], "match": "外显子2"},
    {"key": "KRAS_EX3", "genes": ["KRAS"], "match": "外显子3"},
    {"key": "KRAS_EX4", "genes": ["KRAS"], "match": "外显子4"},
    {"key": "ALK_FUSION", "genes": ["ALK"], "match": "融合"},
    {"key": "ROS1_FUSION", "genes": ["ROS1"], "match": "融合"},
    {"key": "RET_FUSION", "genes": ["RET"], "match": "融合"},
    {"key": "ERBB2_MUT", "genes": ["ERBB2"], "match": "突变"},
    {"key": "ERBB2_AMP", "genes": ["ERBB2"], "match": "扩增"},
    {"key": "PIK3CA_EX10", "genes": ["PIK3CA"], "match": "外显子10"},
    {"key": "PIK3CA_EX21", "genes": ["PIK3CA"], "match": "外显子21"},
    {"key": "MET_EX14SKIP", "genes": ["MET"], "match": "外显子14跳跃"},
    {"key": "MET_AMP", "genes": ["MET"], "match": "扩增"},
    {"key": "NRAS_EX2", "genes": ["NRAS"], "match": "外显子2"},
    {"key": "NRAS_EX3", "genes": ["NRAS"], "match": "外显子3"},
    {"key": "NRAS_EX4", "genes": ["NRAS"], "match": "外显子4"},
    {"key": "BRAF_V600", "genes": ["BRAF"], "match": "密码子600"},
    {"key": "FGFR123_MUT", "genes": ["FGFR1", "FGFR2", "FGFR3"], "match": "突变"},
    {
        "key": "FGFR123_FUSION",
        "genes": ["FGFR1", "FGFR2", "FGFR3"],
        "match": "融合",
    },
    {"key": "NTRK123_FUSION", "genes": ["NTRK1", "NTRK2", "NTRK3"], "match": "融合"},
    {"key": "KIT_EX9", "genes": ["KIT"], "match": "外显子9"},
    {"key": "KIT_EX11", "genes": ["KIT"], "match": "外显子11"},
    {"key": "KIT_EX13", "genes": ["KIT"], "match": "外显子13"},
    {"key": "KIT_EX17", "genes": ["KIT"], "match": "外显子17"},
    {"key": "PDGFRA_EX12", "genes": ["PDGFRA"], "match": "外显子12"},
    {"key": "PDGFRA_EX14", "genes": ["PDGFRA"], "match": "外显子14"},
    {"key": "PDGFRA_EX18", "genes": ["PDGFRA"], "match": "外显子18"},
    {"key": "BRCA12_MUT", "genes": ["BRCA1", "BRCA2"], "match": "突变"},
    {"key": "IDH12_MUT", "genes": ["IDH1", "IDH2"], "match": "突变"},
]

# ---------------------------------------------------------------------------
# PanelConfig: immutable, instance-based gene classification container
# ---------------------------------------------------------------------------

@dataclass
class PanelConfig:
    """Encapsulates gene classification sets for a specific panel.

    Replaces the legacy module-level global variables, enabling thread-safe
    and multi-panel usage.
    """

    class_i_genes: Set[str] = field(
        default_factory=lambda: set(_DEFAULT_CLASS_I_GENES)
    )
    class_ii_genes: Set[str] = field(
        default_factory=lambda: set(_DEFAULT_CLASS_II_GENES)
    )
    crc_important_genes: Set[str] = field(
        default_factory=lambda: set(_DEFAULT_CRC_IMPORTANT_GENES)
    )
    immune_positive_genes: Set[str] = field(
        default_factory=lambda: set(_DEFAULT_IMMUNE_POSITIVE_GENES)
    )
    immune_negative_genes: Set[str] = field(
        default_factory=lambda: set(_DEFAULT_IMMUNE_NEGATIVE_GENES)
    )
    immune_hyperprogression_genes: Set[str] = field(
        default_factory=lambda: set(_DEFAULT_IMMUNE_HYPERPROGRESSION_GENES)
    )
    immune_positive_rows: List[Dict[str, Any]] = field(
        default_factory=lambda: [dict(x) for x in _DEFAULT_IMMUNE_POSITIVE_ROWS]
    )
    immune_negative_rows: List[Dict[str, Any]] = field(
        default_factory=lambda: [dict(x) for x in _DEFAULT_IMMUNE_NEGATIVE_ROWS]
    )
    immune_hyperprogression_rows: List[Dict[str, Any]] = field(
        default_factory=lambda: [
            dict(x) for x in _DEFAULT_IMMUNE_HYPERPROGRESSION_ROWS
        ]
    )
    panel_display_genes: List[Dict[str, str]] = field(
        default_factory=lambda: [dict(x) for x in _DEFAULT_PANEL_DISPLAY_GENES]
    )
    reviewed_variant_overrides: List[Dict[str, Any]] = field(default_factory=list)
    approved_drug_rows: List[Dict[str, str]] = field(default_factory=list)
    nccn_result_rows: List[Dict[str, Any]] = field(
        default_factory=lambda: [dict(x) for x in _DEFAULT_NCCN_RESULT_ROWS]
    )

    @property
    def all_immune_genes(self) -> Set[str]:
        return (
            self.immune_positive_genes
            | self.immune_negative_genes
            | self.immune_hyperprogression_genes
        )


def _resolve_config_path(
    base_path: Optional[str] = None,
    *,
    panel_id: Optional[str] = None,
    config_path: Optional[str] = None,
) -> Optional[Path]:
    """Find the CRC panel config file, preferring panel-package rules."""
    candidates: List[Path] = []
    if config_path:
        candidates.append(Path(str(config_path)).expanduser())

    panel_ids = [str(panel_id or "").strip()]
    if "crc_358_msi" not in panel_ids:
        panel_ids.append("crc_358_msi")

    if base_path:
        bp = Path(str(base_path)).expanduser().resolve()
        for pid in panel_ids:
            if pid:
                candidates.append(bp / "panels" / pid / "rules" / "crc.yaml")
        candidates.append(bp / "config" / "panels" / "crc_358.yaml")
    project_root = Path(__file__).resolve().parents[2]
    for pid in panel_ids:
        if pid:
            candidates.append(project_root / "panels" / pid / "rules" / "crc.yaml")
            candidates.append(Path("panels") / pid / "rules" / "crc.yaml")
    candidates.append(Path("config") / "panels" / "crc_358.yaml")
    candidates.append(project_root / "config" / "panels" / "crc_358.yaml")
    for p in candidates:
        if p.exists() and p.is_file():
            return p.resolve()
    return None


def _resolve_guideline_tables_path(
    base_path: Optional[str] = None,
    *,
    panel_id: Optional[str] = None,
    config_path: Optional[Path] = None,
) -> Optional[Path]:
    """Find the guideline table rule file next to a panel package."""
    candidates: List[Path] = []
    if config_path is not None:
        candidates.append(config_path.parent / "guideline_tables.yaml")

    panel_ids = [str(panel_id or "").strip()]
    if "crc_358_msi" not in panel_ids:
        panel_ids.append("crc_358_msi")

    if base_path:
        bp = Path(str(base_path)).expanduser().resolve()
        for pid in panel_ids:
            if pid:
                candidates.append(bp / "panels" / pid / "rules" / "guideline_tables.yaml")

    project_root = Path(__file__).resolve().parents[2]
    for pid in panel_ids:
        if pid:
            candidates.append(project_root / "panels" / pid / "rules" / "guideline_tables.yaml")
            candidates.append(Path("panels") / pid / "rules" / "guideline_tables.yaml")

    for path in candidates:
        if path.exists() and path.is_file():
            return path.resolve()
    return None


def _load_guideline_tables_rule(
    *,
    base_path: Optional[str],
    panel_id: Optional[str],
    config_path: Optional[Path],
) -> Dict[str, Any]:
    path = _resolve_guideline_tables_path(
        base_path,
        panel_id=panel_id,
        config_path=config_path,
    )
    if path is None:
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _resolve_drugs_rule_path(
    base_path: Optional[str] = None,
    *,
    panel_id: Optional[str] = None,
    config_path: Optional[Path] = None,
) -> Optional[Path]:
    """Find the drug-display rule file next to a panel package."""
    candidates: List[Path] = []
    if config_path is not None:
        candidates.append(config_path.parent / "drugs.yaml")

    panel_ids = [str(panel_id or "").strip()]
    if "crc_358_msi" not in panel_ids:
        panel_ids.append("crc_358_msi")

    if base_path:
        bp = Path(str(base_path)).expanduser().resolve()
        for pid in panel_ids:
            if pid:
                candidates.append(bp / "panels" / pid / "rules" / "drugs.yaml")

    project_root = Path(__file__).resolve().parents[2]
    for pid in panel_ids:
        if pid:
            candidates.append(project_root / "panels" / pid / "rules" / "drugs.yaml")
            candidates.append(Path("panels") / pid / "rules" / "drugs.yaml")

    for path in candidates:
        if path.exists() and path.is_file():
            return path.resolve()
    return None


def _load_drugs_rule(
    *,
    base_path: Optional[str],
    panel_id: Optional[str],
    config_path: Optional[Path],
) -> Dict[str, Any]:
    path = _resolve_drugs_rule_path(
        base_path,
        panel_id=panel_id,
        config_path=config_path,
    )
    if path is None:
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _resolve_biomarkers_rule_path(
    base_path: Optional[str] = None,
    *,
    panel_id: Optional[str] = None,
    config_path: Optional[Path] = None,
) -> Optional[Path]:
    """Find the biomarker rule file next to a panel package."""
    candidates: List[Path] = []
    if config_path is not None:
        candidates.append(config_path.parent / "biomarkers.yaml")

    panel_ids = [str(panel_id or "").strip()]
    if "crc_358_msi" not in panel_ids:
        panel_ids.append("crc_358_msi")

    if base_path:
        bp = Path(str(base_path)).expanduser().resolve()
        for pid in panel_ids:
            if pid:
                candidates.append(bp / "panels" / pid / "rules" / "biomarkers.yaml")

    project_root = Path(__file__).resolve().parents[2]
    for pid in panel_ids:
        if pid:
            candidates.append(project_root / "panels" / pid / "rules" / "biomarkers.yaml")
            candidates.append(Path("panels") / pid / "rules" / "biomarkers.yaml")

    for path in candidates:
        if path.exists() and path.is_file():
            return path.resolve()
    return None


def _load_biomarkers_rule(
    *,
    base_path: Optional[str],
    panel_id: Optional[str],
    config_path: Optional[Path],
) -> Dict[str, Any]:
    path = _resolve_biomarkers_rule_path(
        base_path,
        panel_id=panel_id,
        config_path=config_path,
    )
    if path is None:
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _as_upper_gene_list(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(x).strip().upper() for x in value if str(x).strip()]


def _extract_immune_gene_tables(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    biomarkers = raw.get("biomarkers")
    if not isinstance(biomarkers, dict):
        return {}
    tables = biomarkers.get("immune_gene_tables")
    return tables if isinstance(tables, dict) else {}


def _normalize_immune_rows(tables: Dict[str, Any], category: str) -> List[Dict[str, Any]]:
    section = tables.get(category)
    if not isinstance(section, dict):
        return []
    rows = section.get("rows")
    if not isinstance(rows, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        genes = _as_upper_gene_list(row.get("genes"))
        if not key or not genes:
            continue
        item: Dict[str, Any] = {
            "key": key,
            "genes": genes,
            "mode": str(row.get("mode") or "direct").strip() or "direct",
        }
        if row.get("display") is not None:
            item["display"] = str(row.get("display") or "").strip()
        if row.get("interpretation") is not None:
            item["interpretation"] = str(row.get("interpretation") or "").strip()
        if row.get("match") is not None:
            item["match"] = str(row.get("match") or "").strip()
        patterns = row.get("patterns")
        if isinstance(patterns, str):
            patterns = [patterns]
        if isinstance(patterns, list):
            item["patterns"] = [str(x).strip() for x in patterns if str(x).strip()]
        normalized.append(item)
    return normalized


def _normalize_immune_gene_sets(tables: Dict[str, Any]) -> Dict[str, Set[str]]:
    normalized: Dict[str, Set[str]] = {}
    for category in ("positive", "negative", "hyperprogression"):
        section = tables.get(category)
        if not isinstance(section, dict):
            continue
        genes = _as_upper_gene_list(section.get("genes"))
        if genes:
            normalized[category] = set(genes)
    return normalized


def _normalize_approved_drug_rows(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    rows = raw.get("approved_drug_rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _normalize_nccn_result_rows(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    tables = raw.get("guideline_tables")
    if not isinstance(tables, dict):
        return []
    nccn = tables.get("nccn_results")
    if not isinstance(nccn, dict):
        return []
    rows = nccn.get("rows")
    if not isinstance(rows, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        genes = row.get("genes")
        match = str(row.get("match") or row.get("exon_filter") or "").strip()
        if isinstance(genes, str):
            genes = [genes]
        if not key or not isinstance(genes, list):
            continue
        clean_genes = [str(g).strip().upper() for g in genes if str(g).strip()]
        if not clean_genes:
            continue
        item = {"key": key, "genes": clean_genes, "match": match}
        if row.get("display") is not None:
            item["display"] = str(row.get("display") or "").strip()
        normalized.append(item)
    return normalized


def load_panel_config(
    *,
    base_path: Optional[str] = None,
    panel_id: Optional[str] = None,
    config_path: Optional[str] = None,
) -> PanelConfig:
    """Load a PanelConfig instance from the panel package or legacy config.

    Returns a *new* PanelConfig every call — no global mutation.
    Falls back to defaults when the config file is missing or invalid.
    """
    cfg_path = _resolve_config_path(
        base_path,
        panel_id=panel_id,
        config_path=config_path,
    )
    if cfg_path is None:
        return PanelConfig()

    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return PanelConfig()

    if not isinstance(raw, dict):
        return PanelConfig()

    def as_gene_set(key: str, default_set: Set[str]) -> Set[str]:
        if key not in raw:
            return default_set
        value = raw.get(key)
        if value is None:
            return default_set
        if isinstance(value, (list, tuple, set)):
            return {str(x).strip().upper() for x in value if str(x).strip()}
        return default_set

    panel_display = None
    if "panel_display_genes" in raw and raw.get("panel_display_genes") is not None:
        value = raw.get("panel_display_genes")
        if isinstance(value, list):
            items: List[Dict[str, str]] = []
            for row in value:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "").strip()
                if not name:
                    continue
                items.append(
                    {
                        "name": str(name).strip().upper(),
                        "transcript": str(row.get("transcript") or "").strip(),
                        "chromosome": str(row.get("chromosome") or "").strip(),
                    }
                )
            panel_display = items

    def as_dict_list(key: str) -> List[Dict[str, Any]]:
        value = raw.get(key)
        if not isinstance(value, list):
            return []
        return [dict(row) for row in value if isinstance(row, dict)]

    guideline_rule = _load_guideline_tables_rule(
        base_path=base_path,
        panel_id=panel_id,
        config_path=cfg_path,
    )
    nccn_rows = _normalize_nccn_result_rows(guideline_rule)
    drugs_rule = _load_drugs_rule(
        base_path=base_path,
        panel_id=panel_id,
        config_path=cfg_path,
    )
    approved_drug_rows = _normalize_approved_drug_rows(drugs_rule)
    biomarkers_rule = _load_biomarkers_rule(
        base_path=base_path,
        panel_id=panel_id,
        config_path=cfg_path,
    )
    immune_tables = _extract_immune_gene_tables(biomarkers_rule)
    immune_gene_sets = _normalize_immune_gene_sets(immune_tables)
    immune_positive_rows = _normalize_immune_rows(immune_tables, "positive")
    immune_negative_rows = _normalize_immune_rows(immune_tables, "negative")
    immune_hyperprogression_rows = _normalize_immune_rows(
        immune_tables,
        "hyperprogression",
    )

    pc = PanelConfig(
        class_i_genes=as_gene_set("class_i_genes", set(_DEFAULT_CLASS_I_GENES)),
        class_ii_genes=as_gene_set("class_ii_genes", set(_DEFAULT_CLASS_II_GENES)),
        crc_important_genes=as_gene_set("crc_important_genes", set(_DEFAULT_CRC_IMPORTANT_GENES)),
        immune_positive_genes=immune_gene_sets.get("positive")
        or as_gene_set("immune_positive_genes", set(_DEFAULT_IMMUNE_POSITIVE_GENES)),
        immune_negative_genes=immune_gene_sets.get("negative")
        or as_gene_set("immune_negative_genes", set(_DEFAULT_IMMUNE_NEGATIVE_GENES)),
        immune_hyperprogression_genes=immune_gene_sets.get("hyperprogression")
        or as_gene_set(
            "immune_hyperprogression_genes",
            set(_DEFAULT_IMMUNE_HYPERPROGRESSION_GENES),
        ),
        immune_positive_rows=immune_positive_rows
        or [dict(x) for x in _DEFAULT_IMMUNE_POSITIVE_ROWS],
        immune_negative_rows=immune_negative_rows
        or [dict(x) for x in _DEFAULT_IMMUNE_NEGATIVE_ROWS],
        immune_hyperprogression_rows=immune_hyperprogression_rows
        or [dict(x) for x in _DEFAULT_IMMUNE_HYPERPROGRESSION_ROWS],
        reviewed_variant_overrides=as_dict_list("reviewed_variant_overrides"),
        approved_drug_rows=approved_drug_rows or as_dict_list("crc_approved_drugs"),
        nccn_result_rows=nccn_rows or [dict(x) for x in _DEFAULT_NCCN_RESULT_ROWS],
    )
    if panel_display is not None:
        pc.panel_display_genes = panel_display
    return pc


# Lazy default singleton
_default_panel_config: Optional[PanelConfig] = None
_default_panel_config_base_path: Optional[str] = None


def get_default_panel_config(
    base_path: Optional[str] = None,
    *,
    panel_id: Optional[str] = None,
    config_path: Optional[str] = None,
) -> PanelConfig:
    """Return a lazily-initialised default PanelConfig.

    Reloads if *base_path* changes from the previously cached value.
    """
    global _default_panel_config, _default_panel_config_base_path
    cache_key = "|".join(str(x or "") for x in (base_path, panel_id, config_path))
    if _default_panel_config is None or cache_key != _default_panel_config_base_path:
        _default_panel_config = load_panel_config(
            base_path=base_path,
            panel_id=panel_id,
            config_path=config_path,
        )
        _default_panel_config_base_path = cache_key
    return _default_panel_config


# ---------------------------------------------------------------------------
# Backward-compatible module-level globals (synced from PanelConfig)
# ---------------------------------------------------------------------------
# Kept so that any external code reading ``bridge.CLASS_I_GENES`` still works.

CLASS_I_GENES = set(_DEFAULT_CLASS_I_GENES)
CLASS_II_GENES = set(_DEFAULT_CLASS_II_GENES)
CRC_IMPORTANT_GENES = set(_DEFAULT_CRC_IMPORTANT_GENES)
IMMUNE_POSITIVE_GENES = set(_DEFAULT_IMMUNE_POSITIVE_GENES)
IMMUNE_NEGATIVE_GENES = set(_DEFAULT_IMMUNE_NEGATIVE_GENES)
IMMUNE_HYPERPROGRESSION_GENES = set(_DEFAULT_IMMUNE_HYPERPROGRESSION_GENES)
ALL_IMMUNE_GENES = (
    IMMUNE_POSITIVE_GENES | IMMUNE_NEGATIVE_GENES | IMMUNE_HYPERPROGRESSION_GENES
)
PANEL_DISPLAY_GENES = [dict(x) for x in _DEFAULT_PANEL_DISPLAY_GENES]

_LOADED_CRC_358_CONFIG_PATH: Optional[Path] = None


def _sync_globals_from_config(pc: PanelConfig) -> None:
    """Sync module-level globals from a PanelConfig (backward compat)."""
    global CLASS_I_GENES, CLASS_II_GENES, CRC_IMPORTANT_GENES
    global IMMUNE_POSITIVE_GENES, IMMUNE_NEGATIVE_GENES, IMMUNE_HYPERPROGRESSION_GENES
    global ALL_IMMUNE_GENES, PANEL_DISPLAY_GENES
    CLASS_I_GENES = pc.class_i_genes
    CLASS_II_GENES = pc.class_ii_genes
    CRC_IMPORTANT_GENES = pc.crc_important_genes
    IMMUNE_POSITIVE_GENES = pc.immune_positive_genes
    IMMUNE_NEGATIVE_GENES = pc.immune_negative_genes
    IMMUNE_HYPERPROGRESSION_GENES = pc.immune_hyperprogression_genes
    ALL_IMMUNE_GENES = pc.all_immune_genes
    PANEL_DISPLAY_GENES = pc.panel_display_genes


def load_crc_358_panel_config(*, base_path: Optional[str] = None) -> Optional[Path]:
    """Legacy wrapper: load config and sync to module globals.

    Kept for backward compatibility. Prefer ``load_panel_config()`` for new code.
    """
    global _LOADED_CRC_358_CONFIG_PATH, _default_panel_config

    cfg_path = _resolve_config_path(base_path, panel_id="crc_358_msi")
    if cfg_path is None:
        return None
    if _LOADED_CRC_358_CONFIG_PATH == cfg_path:
        return cfg_path

    pc = load_panel_config(base_path=base_path, panel_id="crc_358_msi")
    _sync_globals_from_config(pc)
    _default_panel_config = pc
    _LOADED_CRC_358_CONFIG_PATH = cfg_path
    return cfg_path

EXPLICIT_GENE_CLASS_LABELS = {"Ⅰ类", "Ⅱ类", "Ⅲ类"}

# Mutation type translation
MUTATION_TYPE_MAP = {
    "Missense": "错义突变",
    "Nonsense": "无义突变",
    "CDS-indel": "移码突变",
    "Frameshift": "移码突变",
    "Splice-5": "剪接突变",
    "Splice-3": "剪接突变",
    "Splice": "剪接突变",
    "Inframe": "框内突变",
    "Stop_gain": "无义突变",
    "Stop_loss": "终止密码子丢失",
}

def _explicit_gene_class(value: Any) -> str:
    """Return the reviewed I/II/III label from a raw class cell, if present."""
    val = _norm_text(value)
    return val if val in EXPLICIT_GENE_CLASS_LABELS else ""


def _has_explicit_gene_class_labels(
    rows: List[Dict[str, Any]],
    class_column: str = "ExistIn552",
) -> bool:
    """Whether this sheet contains reviewed Chinese class labels.

    Some legacy workbooks use numeric 1/0 in ``ExistIn552`` as panel-membership
    flags. Once any row contains an explicit I/II/III label, numeric values in
    that same column must be treated as non-reviewed flags, not as classes.
    """
    return any(_explicit_gene_class(row.get(class_column)) for row in rows)


def _get_gene_class(
    gene: str,
    exist_in_552: Any,
    panel_config: Optional[PanelConfig] = None,
    *,
    allow_gene_fallback: bool = True,
) -> str:
    """
    Determine gene class based on gene name and ExistIn552 value.

    Args:
        gene: Gene symbol
        exist_in_552: ExistIn552 column value (1, 0, or Chinese labels)
        allow_gene_fallback: For legacy numeric-only workbooks, infer I/II/III
            from the panel config. For reviewed workbooks with explicit labels,
            set False so numeric 1 remains only a panel-membership flag.

    Returns:
        Gene class string: "Ⅰ类", "Ⅱ类", "Ⅲ类", or "" when no reviewed class
        can be resolved.
    """
    if panel_config is None:
        panel_config = get_default_panel_config()

    val = _norm_text(exist_in_552)
    if val in EXPLICIT_GENE_CLASS_LABELS:
        return val
    if val in ("0", "0.0", "False", "false"):
        return ""
    if not allow_gene_fallback:
        return ""

    # Legacy fallback: old workbooks used numeric flags, so derive class from
    # reviewed panel config rather than from a patient-specific value.
    gene_upper = gene.upper()
    if gene_upper in panel_config.class_i_genes:
        return "Ⅰ类"
    if gene_upper in panel_config.class_ii_genes:
        return "Ⅱ类"

    # Numeric legacy rows that are panel members but not in I/II config remain
    # III class; reviewed mixed-label sheets are handled by allow_gene_fallback.
    return "Ⅲ类"


def _get_mutation_type(function: Any) -> str:
    """Translate mutation function to Chinese (legacy fallback)."""
    func = _norm_text(function)
    return MUTATION_TYPE_MAP.get(func, func or "")


def _extract_exon(exin_id: Any) -> str:
    """Extract exon number from ExIn_ID (e.g., 'EX16' -> '16')."""
    s = _norm_text(exin_id)
    if not s:
        return ""
    match = re.search(r"(?i)(?:EX|EXON|IN)(\d+)", s)
    return match.group(1) if match else s


def _extract_chromosome(chr_val: Any) -> str:
    """Extract chromosome number (remove 'chr' prefix)."""
    s = _norm_text(chr_val)
    if not s:
        return ""
    return re.sub(r"(?i)^chr", "", s).strip()


def _format_frequency(freq: Any) -> str:
    """Format frequency value."""
    val = _norm_text(freq)
    if not val:
        return "--"
    try:
        return f"{float(val):.2f}"
    except (ValueError, TypeError):
        return val


def _as_text_list(value: Any) -> List[str]:
    """Normalize YAML scalar/list values to a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _join_text_value(value: Any) -> str:
    return "\n".join(_as_text_list(value))


def _override_gene_values(override: Dict[str, Any]) -> Set[str]:
    values = _as_text_list(override.get("gene") or override.get("genes"))
    return {value.upper() for value in values}


def _variant_override_matches(
    override: Dict[str, Any],
    gene: str,
    c_hgvs: str = "",
    p_hgvs: str = "",
    locus: str = "",
) -> bool:
    """Match a variant row against a reviewed YAML override rule."""
    gene_norm = _norm_text(gene).upper()
    if not gene_norm:
        return False

    override_genes = _override_gene_values(override)
    if override_genes and gene_norm not in override_genes:
        return False

    c_values = set(_as_text_list(override.get("c_hgvs") or override.get("cHGVS")))
    p_values = set(_as_text_list(override.get("p_hgvs") or override.get("pHGVS")))
    c_norm = _norm_text(c_hgvs)
    p_norm = _norm_text(p_hgvs)
    locus_norm = _norm_text(locus)

    if c_values and c_norm not in c_values and not any(c in locus_norm for c in c_values):
        return False
    if p_values and p_norm not in p_values and not any(p in locus_norm for p in p_values):
        return False

    return bool(c_values or p_values or override_genes)


def _find_reviewed_variant_override(
    panel_config: PanelConfig,
    gene: str,
    c_hgvs: str = "",
    p_hgvs: str = "",
    locus: str = "",
) -> Optional[Dict[str, Any]]:
    for override in panel_config.reviewed_variant_overrides:
        if _variant_override_matches(override, gene, c_hgvs, p_hgvs, locus):
            return override
    return None


def _drugs_from_override(override: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    if not override:
        return "", ""
    return (
        _join_text_value(override.get("benefit_drugs")),
        _join_text_value(override.get("caution_drugs")),
    )


def build_variants_for_template(
    excel_data: ExcelDataSource,
    filter_column: str = "ExistInsmall358",
    filter_class_i_ii_only: bool = True,
    important_genes_only: bool = True,
    drug_lookup: Optional[Callable[[str, str, str, str], Tuple[str, str]]] = None,
    panel_config: Optional[PanelConfig] = None,
) -> List[Dict[str, str]]:
    """
    Build variants table matching the Jinja2 template format.

    Columns: gene, transcript, chromosome, exon, cHGVS, pHGVS,
             mutation_type, frequency, gene_class, clinical_significance,
             benefit_drugs, caution_drugs

    Args:
        excel_data: Parsed Excel data
        filter_column: Column to filter by (default: ExistInsmall358)
        filter_class_i_ii_only: If True, only include Ⅰ类 and Ⅱ类 (批注#3)
        important_genes_only: If True, only include genes in CRC_IMPORTANT_GENES
        drug_lookup: Optional callable to lookup (benefit_drugs, caution_drugs) by
            (gene, c_hgvs, p_hgvs, gene_class).

    Returns:
        List of variant dictionaries
    """
    if panel_config is None:
        panel_config = get_default_panel_config()

    variations = excel_data.get_table_data("Variations") or []
    allow_gene_fallback = not _has_explicit_gene_class_labels(variations)
    variants = []

    for row in variations:
        # Filter: only include variants in the active CRC panel
        filter_val = row.get(filter_column)
        if filter_val not in (1, "1", True):
            continue

        gene = _norm_text(row.get("Gene_Symbol") or row.get("Gene"))
        if not gene:
            continue

        # 验证cHGVS格式：必须以"c."开头才是真正的变异
        c_hgvs = _norm_text(row.get("cHGVS"))
        if not c_hgvs or not c_hgvs.startswith("c."):
            continue  # 跳过非变异行（如注释、参考数据等）

        # 批注#3: 只显示重要基因列表中的基因
        if important_genes_only and gene.upper() not in panel_config.crc_important_genes:
            continue

        # Get gene class
        gene_class = _get_gene_class(
            gene,
            row.get("ExistIn552"),
            panel_config=panel_config,
            allow_gene_fallback=allow_gene_fallback,
        )
        if not gene_class:
            continue

        # 批注#3: 只显示Ⅰ类和Ⅱ类基因
        if filter_class_i_ii_only and gene_class == "Ⅲ类":
            continue

        # Get pHGVS notation (cHGVS already extracted above)
        p_hgvs = _norm_text(row.get("pHGVS_S") or row.get("pHGVS_A"))
        if not p_hgvs or p_hgvs == "*":
            p_hgvs = "--"
        reviewed_override = _find_reviewed_variant_override(
            panel_config,
            gene,
            c_hgvs,
            "" if p_hgvs in {"--", "*"} else p_hgvs,
        )

        # Get clinical significance. Missing CLNSIG is not evidence of pathogenicity;
        # keep it explicit so downstream drug/immune summaries do not overstate it.
        clnsig = _norm_text(row.get("CLNSIG"))
        if clnsig and clnsig not in ("*", "-"):
            clinical_significance = clnsig
        else:
            clinical_significance = "临床意义未明"
        if reviewed_override:
            clinical_significance = (
                _norm_text(reviewed_override.get("clinical_significance"))
                or clinical_significance
            )

        # Get drug associations (批注#5：来自自建数据库/既往报告口径)
        benefit_drugs = "--"
        caution_drugs = "--"
        if drug_lookup is not None and gene_class in {"Ⅰ类", "Ⅱ类"}:
            try:
                p_for_lookup = "" if p_hgvs in {"--", "*"} else p_hgvs
                benefit_drugs, caution_drugs = drug_lookup(
                    gene, c_hgvs, p_for_lookup, gene_class
                )
            except Exception:
                benefit_drugs, caution_drugs = "--", "--"
        else:
            drug = _norm_text(row.get("Drug"))
            benefit_drugs = drug if drug and drug not in ("*", "-") else "--"
            caution_drugs = "--"
        override_benefit, override_caution = _drugs_from_override(reviewed_override)
        if override_benefit or override_caution:
            benefit_drugs = override_benefit or "--"
            caution_drugs = override_caution or "--"

        variant = {
            "gene": gene,
            "transcript": _norm_text(row.get("Transcript")),
            "chromosome": _extract_chromosome(row.get("Chr")),
            "exon": _extract_exon(row.get("ExIn_ID")),
            "cHGVS": c_hgvs,
            "pHGVS": p_hgvs,
            # 批注#16：突变类型依据 c.HGVS 的 del/dup/ins/delins 判定
            "mutation_type": infer_variant_type_cn(c_hgvs)
            or _get_mutation_type(row.get("Function"))
            or "点突变",
            "frequency": _format_frequency(row.get("Freq(%)")),
            "gene_class": gene_class,
            "clinical_significance": clinical_significance,
            "benefit_drugs": benefit_drugs,
            "caution_drugs": caution_drugs,
        }
        variants.append(variant)

    return variants


def build_all_variants_for_template(
    excel_data: ExcelDataSource,
    filter_column: str = "ExistInsmall358",
    drug_lookup: Optional[Callable[[str, str, str, str], Tuple[str, str]]] = None,
    panel_config: Optional[PanelConfig] = None,
) -> List[Dict[str, str]]:
    """
    Build ALL variants table (including Ⅲ类) for summary section.

    This is used for the full variants list and summary tables that need
    to show Ⅲ类 genes with "(意义未明突变)" annotation.

    Args:
        excel_data: Parsed Excel data
        filter_column: Column to filter by (default: ExistInsmall358)

    Returns:
        List of variant dictionaries (all classes)
    """
    return build_variants_for_template(
        excel_data,
        filter_column=filter_column,
        filter_class_i_ii_only=False,
        important_genes_only=False,
        drug_lookup=drug_lookup,
        panel_config=panel_config,
    )


def build_summary_variants(
    variants: List[Dict[str, str]], add_class_iii_annotation: bool = True
) -> List[Dict[str, str]]:
    """
    Build summary variants table (simplified format for summary section).

    Columns: gene, transcript, chromosome, exon, cHGVS, pHGVS,
             mutation_type, frequency, clinical_significance,
             benefit_drugs, caution_drugs

    Args:
        variants: Full variants list
        add_class_iii_annotation: If True, add "(意义未明突变)" for Ⅲ类 (批注#19)

    Returns:
        List of summary variant dictionaries
    """
    summary_variants = []
    for v in variants:
        # 批注#19: Ⅲ类需要加上"（意义未明突变）"
        clinical_significance = v.get("clinical_significance", "临床意义未明")
        gene_class = v.get("gene_class", "")
        if add_class_iii_annotation and gene_class == "Ⅲ类":
            if "意义未明" not in clinical_significance:
                clinical_significance = f"{clinical_significance}（意义未明突变）"

        summary = {
            "gene": v["gene"],
            "transcript": v["transcript"],
            "chromosome": v["chromosome"],
            "exon": v["exon"],
            "cHGVS": v["cHGVS"],
            "pHGVS": v["pHGVS"],
            # 批注#16：突变类型依据 c.HGVS 的 del/dup/ins/delins 判定
            "mutation_type": infer_variant_type_cn(v.get("cHGVS")) or "点突变",
            "frequency": v["frequency"],
            "gene_class": gene_class,
            "clinical_significance": clinical_significance,
            "benefit_drugs": v["benefit_drugs"],
            "caution_drugs": v["caution_drugs"],
        }
        summary_variants.append(summary)
    return summary_variants


def build_immune_variants(
    excel_data: ExcelDataSource,
    filter_column: str = "ExistInsmall358",
    filter_class_i_ii_only: bool = True,
    drug_lookup: Optional[Callable[[str, str, str, str], Tuple[str, str]]] = None,
    panel_config: Optional[PanelConfig] = None,
) -> Dict[str, List[Dict[str, str]]]:
    """
    Build immune-related variants tables (批注#12).

    Separates variants into:
    - positive: 正相关基因 (IMMUNE_POSITIVE_GENES)
    - negative: 负相关基因 (IMMUNE_NEGATIVE_GENES)
    - hyperprogression: 超进展相关基因 (IMMUNE_HYPERPROGRESSION_GENES)

    Args:
        excel_data: Parsed Excel data
        filter_class_i_ii_only: If True, only include Ⅰ类 and Ⅱ类 genes

    Returns:
        Dict with 'positive', 'negative', 'hyperprogression' variant lists
    """
    if panel_config is None:
        panel_config = get_default_panel_config()

    # Get all 358 panel variants first (without class/important gene filtering)
    all_variants = build_variants_for_template(
        excel_data,
        filter_column=filter_column,
        filter_class_i_ii_only=False,
        important_genes_only=False,
        drug_lookup=drug_lookup,
        panel_config=panel_config,
    )

    positive_variants = []
    negative_variants = []
    hyperprogression_variants = []

    # 免疫摘要与 3.3 详表口径保持一致：仅按 Ⅰ/Ⅱ 类过滤，不再叠加 CLNSIG
    # 致病性白名单。早前的致病性二次过滤会把 CLNSIG 为空的 Ⅰ/Ⅱ 类移码变异
    # （如 PMS2 c.1273delT、ATR c.1291delA）从前面的汇总中漏掉，使汇总表的
    # 变异数少于后面 3.3 详表（报告解读反馈的问题）。详表用的是
    # _immune_eligible_variants（仅 Ⅰ/Ⅱ 类），此处与之对齐。
    for v in all_variants:
        gene = v["gene"].upper()
        gene_class = v.get("gene_class", "")

        # 批注#12: 只显示Ⅰ类和Ⅱ类
        if filter_class_i_ii_only and gene_class == "Ⅲ类":
            continue

        # Add "(意义未明突变)" annotation for Ⅲ类 if not filtered out
        clinical_sig = v.get("clinical_significance", "临床意义未明")
        if gene_class == "Ⅲ类" and "意义未明" not in clinical_sig:
            v = v.copy()
            v["clinical_significance"] = f"{clinical_sig}（意义未明突变）"

        if gene in panel_config.immune_positive_genes:
            positive_variants.append(v)
        if gene in panel_config.immune_negative_genes:
            negative_variants.append(v)
        if gene in panel_config.immune_hyperprogression_genes:
            hyperprogression_variants.append(v)

    return {
        "positive": positive_variants,
        "negative": negative_variants,
        "hyperprogression": hyperprogression_variants,
    }


def build_undetected_genes(
    detected_genes: Set[str],
    panel_genes: Optional[List[Dict]] = None,
    panel_config: Optional[PanelConfig] = None,
) -> List[Dict[str, str]]:
    """
    Build undetected genes table.

    Columns: name, transcript, chromosome

    Args:
        detected_genes: Set of gene symbols that have detected variants
        panel_genes: Optional list of panel gene definitions
        panel_config: Optional PanelConfig instance

    Returns:
        List of undetected gene dictionaries
    """
    if panel_genes is None:
        if panel_config is not None:
            panel_genes = panel_config.panel_display_genes
        else:
            panel_genes = get_default_panel_config().panel_display_genes

    undetected = []
    for gene_info in panel_genes:
        if gene_info["name"] not in detected_genes:
            undetected.append(
                {
                    "name": gene_info["name"],
                    "transcript": gene_info["transcript"],
                    "chromosome": gene_info["chromosome"],
                }
            )
    return undetected


def build_msi_summary(excel_data: ExcelDataSource) -> Dict[str, str]:
    """
    Build MSI summary fields.

    Returns dict with: msi_status, msi_status_cn, msi_summary and dynamic
    narrative fields for the Word template.
    """
    # 优先使用ExcelReader已抽取的单值（Msisensor解析）
    return build_msi_fields(excel_data.single_values.get("MSI状态"))


def build_tmb_summary(excel_data: ExcelDataSource) -> Dict[str, str]:
    """
    Build TMB summary fields.

    Returns dict with: tmb_value, tmb_status, tmb_level_cn, tmb_reference, tmb_summary
    """
    return build_tmb_fields(
        excel_data.single_values.get("TMB"),
        sample_type=excel_data.single_values.get("样本类型") or "组织",
    )


def format_immune_positive_result(
    variants: List[Dict[str, str]],
) -> str:
    """
    Format immune positive variants as display text.

    Format: "检出（N个）
    GENE1：cHGVS，pHGVS
    GENE2：cHGVS，pHGVS
    ..."

    If no variants, returns "未检出".
    """
    if not variants:
        return "未检出"

    count = len(variants)
    lines = [f"检出（{count}个）"]

    for v in variants:
        gene = v.get("gene", "")
        c_hgvs = v.get("cHGVS", "")
        p_hgvs = v.get("pHGVS", "")

        if p_hgvs and p_hgvs not in ("--", "*", ""):
            line = f"{gene}：{c_hgvs}，{p_hgvs}"
        else:
            line = f"{gene}：{c_hgvs}"
        lines.append(line)

    return "\n".join(lines)


def format_immune_result(
    variants: List[Dict[str, str]],
    result_type: str = "negative",
) -> str:
    """
    Format immune variants as display text.

    For negative/hyperprogression: returns "未检出" if empty,
    or formatted list of detected variants.

    Args:
        variants: List of variant dictionaries
        result_type: "negative" or "hyperprogression"

    Returns:
        Formatted string
    """
    if not variants:
        return "未检出"

    lines = [f"检出（{len(variants)}个）"]
    for v in variants:
        gene = v.get("gene", "")
        c_hgvs = v.get("cHGVS", "")
        p_hgvs = v.get("pHGVS", "")

        if p_hgvs and p_hgvs not in ("--", "*", ""):
            line = f"{gene}：{c_hgvs}，{p_hgvs}"
        else:
            line = f"{gene}：{c_hgvs}"
        lines.append(line)

    return "\n".join(lines)


def count_drug_related_variants(
    variants: List[Dict[str, str]],
) -> int:
    """
    Count variants that have drug associations.

    A variant is drug-related if benefit_drugs or caution_drugs is not empty/--
    """
    count = 0
    for v in variants:
        benefit = v.get("benefit_drugs", "--")
        caution = v.get("caution_drugs", "--")
        if (benefit and benefit != "--") or (caution and caution != "--"):
            count += 1
    return count


def _build_nccn_and_immune_fields(
    report_data: ReportData,
    all_variants: List[Dict[str, str]],
    excel_data: ExcelDataSource,
    *,
    panel_config: Optional[PanelConfig] = None,
) -> None:
    """为 T[5] NCCN 检测基因表和 T[6-8] 免疫基因表生成动态填充变量。

    逻辑：遍历 all_variants，按基因+外显子/检测内容匹配，
    检出时填入 cHGVS，pHGVS；未检出时填"未检出"/"未检出有害变异"。
    """
    pc = panel_config or PanelConfig()
    nccn_rows = pc.nccn_result_rows or [dict(x) for x in _DEFAULT_NCCN_RESULT_ROWS]
    imm_pos_rows = pc.immune_positive_rows or [
        dict(x) for x in _DEFAULT_IMMUNE_POSITIVE_ROWS
    ]
    imm_neg_rows = pc.immune_negative_rows or [
        dict(x) for x in _DEFAULT_IMMUNE_NEGATIVE_ROWS
    ]
    imm_hyper_rows = pc.immune_hyperprogression_rows or [
        dict(x) for x in _DEFAULT_IMMUNE_HYPERPROGRESSION_ROWS
    ]

    # 先打固定默认值，避免 2.3/3.3 因任何解析缺口出现空白单元格。
    for row in nccn_rows:
        key = str(row.get("key") or "").strip()
        if key:
            report_data.set_field(f"nccn_{key}", "未检出")
    for row in imm_pos_rows:
        key = str(row.get("key") or "").strip()
        if key:
            report_data.set_field(f"imm_pos_{key}", "未检出有害变异")
    for row in imm_neg_rows:
        key = str(row.get("key") or "").strip()
        if key:
            report_data.set_field(f"imm_neg_{key}", "未检出有害变异")
    for row in imm_hyper_rows:
        key = str(row.get("key") or "").strip()
        if key:
            report_data.set_field(f"imm_hyper_{key}", "未检出有害变异")

    # Legacy templates may still contain these fields even if a custom rule omits
    # them, so keep defaults available until template contracts are panel-scoped.
    for row in _DEFAULT_IMMUNE_POSITIVE_ROWS:
        key = str(row.get("key") or "").strip()
        if key and report_data.get_field(f"imm_pos_{key}") is None:
            report_data.set_field(f"imm_pos_{key}", "未检出有害变异")
    for row in _DEFAULT_IMMUNE_NEGATIVE_ROWS:
        key = str(row.get("key") or "").strip()
        if key and report_data.get_field(f"imm_neg_{key}") is None:
            report_data.set_field(f"imm_neg_{key}", "未检出有害变异")
    for row in _DEFAULT_IMMUNE_HYPERPROGRESSION_ROWS:
        key = str(row.get("key") or "").strip()
        if key and report_data.get_field(f"imm_hyper_{key}") is None:
            report_data.set_field(f"imm_hyper_{key}", "未检出有害变异")

    # 构建基因→变异映射（同一基因可能有多个变异）
    gene_variants: Dict[str, List[Dict[str, str]]] = {}
    for v in all_variants:
        g = v.get("gene", "").upper()
        if g:
            gene_variants.setdefault(g, []).append(v)

    # 从原始 Variations 补充（all_variants 可能被 ExistInsmall358 过滤）
    raw_variations = excel_data.get_table_data("Variations") or []
    allow_gene_fallback = not _has_explicit_gene_class_labels(raw_variations)
    for r in raw_variations:
        g = _norm_text(r.get("Gene_Symbol") or r.get("Gene"))
        if not g:
            continue
        gene_class = _get_gene_class(
            g,
            r.get("ExistIn552"),
            panel_config=panel_config,
            allow_gene_fallback=allow_gene_fallback,
        )
        if not gene_class:
            continue
        c = _norm_text(r.get("cHGVS"))
        if not c or not c.startswith("c."):
            continue
        g_upper = g.upper()
        # 检查是否已在 all_variants 中
        existing = gene_variants.get(g_upper, [])
        already = any(ev.get("cHGVS") == c for ev in existing)
        if not already:
            p = _norm_text(r.get("pHGVS_S") or r.get("pHGVS_A"))
            gene_variants.setdefault(g_upper, []).append({
                "gene": g, "cHGVS": c, "pHGVS": p or "",
                "exon": _norm_text(r.get("ExIn_ID")),
                "gene_class": gene_class,
            })

    # 合并 CNV 数据（NCCN 表需要检测 ERBB2 扩增等）
    cnv_data = excel_data.get_table_data("Cnv") or []
    for r in cnv_data:
        g = _norm_text(r.get("Gene") or r.get("gene"))
        if not g:
            continue
        status = _norm_text(r.get("Cnvkit") or r.get("Status") or r.get("status"))
        if status:
            gene_variants.setdefault(g.upper(), []).append({
                "gene": g, "cHGVS": f"CNV:{status}", "pHGVS": "",
                "exon": "", "cnv_type": status,
            })

    # 合并 Fusion 数据（NCCN 表需要检测 ALK/RET/NTRK/ROS1 融合等）
    fusion_data = excel_data.get_table_data("Fusion") or []
    for r in fusion_data:
        g1 = _norm_text(r.get("Gene1") or r.get("gene1"))
        g2 = _norm_text(r.get("Gene2") or r.get("gene2"))
        for g in [g1, g2]:
            if g:
                gene_variants.setdefault(g.upper(), []).append({
                    "gene": g, "cHGVS": f"融合:{g1}-{g2}", "pHGVS": "",
                    "exon": "融合",
                })

    def _format_result(gene_key: str, exon_filter: str = "") -> str:
        """格式化检测结果：检出时返回 cHGVS，pHGVS；未检出时返回标准文本。"""
        variants = gene_variants.get(gene_key.upper(), [])
        if not variants:
            return "未检出"

        if exon_filter:
            # 按外显子过滤
            ef = exon_filter.lower()
            filtered = []
            for v in variants:
                exon = str(v.get("exon", "")).lower()
                c_hgvs = v.get("cHGVS", "")
                c_hgvs_norm = str(c_hgvs or "")
                c_hgvs_upper = c_hgvs_norm.upper()
                c_hgvs_lower = c_hgvs_norm.lower()
                is_fusion = "融合" in c_hgvs_norm or "融合" in exon or "fusion" in c_hgvs_lower
                is_cnv = (
                    c_hgvs_upper.startswith("CNV:")
                    or "扩增" in c_hgvs_norm
                    or "amp" in c_hgvs_lower
                )
                # 匹配外显子号或特殊类型
                if ef.startswith("ex") or ef.startswith("外显子"):
                    exon_num = re.search(r"\d+", ef)
                    if exon_num and exon_num.group() in exon:
                        filtered.append(v)
                elif "融合" in ef or "fusion" in ef:
                    # 只匹配融合类型的条目
                    if "融合" in c_hgvs or "融合" in exon:
                        filtered.append(v)
                elif "扩增" in ef or "amp" in ef:
                    # 只匹配 CNV 扩增类型的条目
                    if is_cnv:
                        filtered.append(v)
                elif "突变" in ef or "mut" in ef:
                    # "突变"行只展示 SNV/indel 等序列变异，避免混入同基因 CNV/Fusion。
                    if not is_cnv and not is_fusion:
                        filtered.append(v)
                elif "密码子" in ef:
                    # 特殊：BRAF 密码子600 → 检查 p.V600
                    if "600" in ef and "V600" in (v.get("pHGVS", "") or c_hgvs):
                        filtered.append(v)
                elif "跳跃" in ef:
                    filtered.append(v)
            variants = filtered

        if not variants:
            return "未检出"

        # 格式化为 cHGVS，pHGVS
        parts = []
        for v in variants:
            c = v.get("cHGVS", "")
            p = v.get("pHGVS", "")
            if not c:
                continue
            if p and p not in ("--", "*", ""):
                parts.append(f"{c}，{p}")
            else:
                parts.append(c)
        return "\n".join(parts) if parts else "未检出"

    def _immune_eligible_variants(gene_key: str) -> List[Dict[str, str]]:
        """Return immune-table variants after I/II class filtering."""
        return [
            v for v in gene_variants.get(gene_key.upper(), [])
            if v.get("gene_class") in {"Ⅰ类", "Ⅱ类"}
        ]

    def _immune_result(gene_key: str) -> str:
        """免疫基因检测结果：检出时返回变异详情；未检出时返回标准文本。"""
        variants = _immune_eligible_variants(gene_key)
        if not variants:
            return "未检出有害变异"
        parts = []
        for v in variants:
            c = v.get("cHGVS", "")
            p = v.get("pHGVS", "")
            if not c:
                continue
            if p and p not in ("--", "*", ""):
                parts.append(f"{c}，{p}")
            else:
                parts.append(c)
        return "\n".join(parts) if parts else "未检出有害变异"

    def _genes_from_row(row: Dict[str, Any]) -> List[str]:
        return _as_upper_gene_list(row.get("genes"))

    def _display_label(row: Dict[str, Any]) -> str:
        explicit = (
            row.get("display")
            or row.get("display_gene")
            or row.get("display_genes")
            or row.get("label")
        )
        if explicit:
            return _norm_text(explicit)
        return "/".join(_genes_from_row(row))

    def _table_row(
        *,
        key: str,
        gene: str,
        result: str,
        content: str = "",
        interpretation: str = "",
    ) -> Dict[str, str]:
        row = {
            "key": key,
            "gene": gene,
            "genes": gene,
            "content": content,
            "match": content,
            "result": result,
            "interpretation": interpretation,
        }
        row.update(
            {
                "检测基因": gene,
                "检测内容": content,
                "检测结果": result,
                "基因": gene,
                "临床解读": interpretation,
            }
        )
        return row

    def _format_gene_prefixed_variants(
        variants: List[Dict[str, str]],
    ) -> str:
        found = []
        for v in variants:
            c = v.get("cHGVS", "")
            p = v.get("pHGVS", "")
            g = v.get("gene", "")
            if p and p not in ("--", "*", ""):
                found.append(f"{g}：{c}，{p}")
            elif c:
                found.append(f"{g}：{c}")
        return "\n".join(found) if found else "未检出有害变异"

    def _immune_variants_for_genes(genes: List[str]) -> List[Dict[str, str]]:
        variants: List[Dict[str, str]] = []
        for gene in genes:
            variants.extend(_immune_eligible_variants(gene))
        return variants

    def _immune_row_result(row: Dict[str, Any]) -> str:
        genes = _genes_from_row(row)
        mode = str(row.get("mode") or "direct").strip() or "direct"
        if not genes:
            return "未检出有害变异"

        if mode == "co_mutation":
            grouped = [_immune_eligible_variants(gene) for gene in genes]
            if not grouped or any(not variants for variants in grouped):
                return "未检出有害变异"
            return _format_gene_prefixed_variants(
                [variant for variants in grouped for variant in variants]
            )

        if mode == "gene_group":
            return _format_gene_prefixed_variants(_immune_variants_for_genes(genes))

        if mode == "variant_pattern":
            patterns = [str(x) for x in row.get("patterns") or [] if str(x)]
            matched = []
            for gene in genes:
                for variant in gene_variants.get(gene.upper(), []):
                    haystack = " ".join(
                        str(variant.get(key) or "")
                        for key in ("cHGVS", "pHGVS", "exon")
                    )
                    if any(pattern in haystack for pattern in patterns):
                        matched.append(variant)
            return (
                "\n".join(str(v.get("cHGVS") or "") for v in matched if v.get("cHGVS"))
                or "未检出有害变异"
            )

        if mode == "cnv_amp":
            val = _format_result(genes[0], str(row.get("match") or "扩增"))
            return "未检出有害变异" if val == "未检出" else val

        if len(genes) == 1:
            return _immune_result(genes[0])
        return _format_gene_prefixed_variants(_immune_variants_for_genes(genes))

    def _first_detected(results: List[str], default: str) -> str:
        for result in results:
            value = str(result or "").strip()
            if value and value not in {"--", default}:
                return value
        return default

    # ===== T[5] NCCN 检测基因表 =====
    nccn_table_rows: List[Dict[str, str]] = []
    for row in nccn_rows:
        key = str(row.get("key") or "").strip()
        genes = row.get("genes") or []
        match = str(row.get("match") or "").strip()
        if not key:
            continue
        if isinstance(genes, str):
            genes = [genes]
        results = [_format_result(str(g), match) for g in genes if str(g).strip()]
        val = _first_detected(results, "未检出")
        report_data.set_field(f"nccn_{key}", val)
        nccn_table_rows.append(
            _table_row(
                key=key,
                gene=_display_label(row),
                content=match,
                result=val,
            )
        )
    report_data.set_table("nccn_results", nccn_table_rows)

    # ===== T[6] 免疫正相关基因 =====
    immune_positive_table_rows: List[Dict[str, str]] = []
    for row in imm_pos_rows:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        val = _immune_row_result(row)
        report_data.set_field(f"imm_pos_{key}", val)
        immune_positive_table_rows.append(
            _table_row(
                key=key,
                gene=_display_label(row),
                result=val,
                interpretation=str(row.get("interpretation") or "检出有害变异时可能疗效较好。"),
            )
        )
    report_data.set_table("immune_positive_results", immune_positive_table_rows)

    # ===== T[7] 免疫负相关基因 =====
    immune_negative_table_rows: List[Dict[str, str]] = []
    for row in imm_neg_rows:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        val = _immune_row_result(row)
        report_data.set_field(f"imm_neg_{key}", val)
        immune_negative_table_rows.append(
            _table_row(
                key=key,
                gene=_display_label(row),
                result=val,
                interpretation=str(row.get("interpretation") or "检出有害变异时可能耐药/疗效不佳。"),
            )
        )
    report_data.set_table("immune_negative_results", immune_negative_table_rows)

    # ===== T[8] 免疫超进展基因 =====
    immune_hyper_table_rows: List[Dict[str, str]] = []
    for row in imm_hyper_rows:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        val = _immune_row_result(row)
        report_data.set_field(f"imm_hyper_{key}", val)
        immune_hyper_table_rows.append(
            _table_row(
                key=key,
                gene=_display_label(row),
                result=val,
                interpretation=str(row.get("interpretation") or "检出有害变异时可能与超进展相关。"),
            )
        )
    report_data.set_table("immune_hyperprogression_results", immune_hyper_table_rows)


def _resolve_crc_filter_column(excel_data: ExcelDataSource) -> Optional[str]:
    """Pick the active panel membership column for CRC 358/301 Excel layouts."""
    variations_data = excel_data.get_table_data("Variations") or []
    if not variations_data:
        return "ExistInsmall358"
    first_row_keys = set(variations_data[0].keys()) if variations_data[0] else set()
    for candidate in ("ExistInsmall358", "ExistInsmall301"):
        if candidate in first_row_keys:
            return candidate
    return None


def _build_crc_approved_drugs(panel_config: PanelConfig) -> List[Dict[str, str]]:
    """Build the CRC 2.2 approved/backup targeted-drug table from YAML config."""
    rows: List[Dict[str, str]] = []
    for row in panel_config.approved_drug_rows:
        drug = _join_text_value(row.get("drug") or row.get("Drug"))
        gene = _join_text_value(row.get("gene") or row.get("Gene"))
        indication = _norm_text(
            row.get("indication")
            or row.get("药物适应情况")
            or row.get("recommendation")
        )
        if not drug and not gene and not indication:
            continue
        rows.append(
            {
                "Drug": drug,
                "Gene": gene,
                "药物适应情况": indication,
            }
        )
    return rows


def _load_drug_brand_map(*, base_path: Optional[str] = None) -> Dict[str, str]:
    """Load marketed drug brand names from config/drug_brands.yaml."""
    candidates: List[Path] = []
    if base_path:
        root = Path(str(base_path)).expanduser().resolve()
        candidates.append(root / "config" / "drug_brands.yaml")
    candidates.append(Path("config") / "drug_brands.yaml")
    candidates.append(Path(__file__).resolve().parents[2] / "config" / "drug_brands.yaml")

    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        brands = raw.get("brands") if isinstance(raw, dict) else None
        if not isinstance(brands, dict):
            continue
        return {
            str(drug).strip(): str(brand).strip()
            for drug, brand in brands.items()
            if str(drug).strip() and str(brand).strip()
        }
    return {}


def build_targeted_drug_brand_summary(
    variants: List[Dict[str, str]],
    *,
    base_path: Optional[str] = None,
) -> str:
    """Build marketed-drug brand summary from final displayed drug columns.

    The source is the already-filtered 2.1 variants table, so III/hidden rows
    cannot leak into the brand summary. The brand map is maintained in config.
    """
    brand_map = _load_drug_brand_map(base_path=base_path)
    if not brand_map:
        return ""

    seen: Set[str] = set()
    brand_names = sorted(brand_map, key=len, reverse=True)

    for row in variants:
        text = "\n".join(
            str(row.get(key) or "")
            for key in ("benefit_drugs", "caution_drugs")
        )
        if not text or text.strip() in {"--", "-"}:
            continue

        matches: List[Tuple[int, str]] = []
        for drug in brand_names:
            start = text.find(drug)
            while start >= 0:
                matches.append((start, drug))
                start = text.find(drug, start + len(drug))
        for _, drug in sorted(matches, key=lambda x: x[0]):
            if drug in seen:
                continue
            seen.add(drug)

    if not seen:
        return ""

    drugs = [drug for drug in brand_map if drug in seen]
    return "、".join(f"{drug}[{brand_map[drug]}]" for drug in drugs) + "。"


def _override_has_detected_variant(
    override: Dict[str, Any],
    report_data: ReportData,
) -> bool:
    """Return True only when this sample contains the reviewed variant.

    Reviewed overrides can add/replace drug text, but they must never create a
    variant that was not actually detected in the current Excel result.
    """
    candidate_tables = ("variants", "summary_variants", "variants_2_1")
    for table_name in candidate_tables:
        for row in report_data.get_table(table_name) or []:
            gene = _norm_text(row.get("gene") or row.get("Gene"))
            c_hgvs = _norm_text(row.get("cHGVS") or row.get("c_hgvs"))
            p_hgvs = _norm_text(row.get("pHGVS") or row.get("p_hgvs"))
            locus = _norm_text(row.get("locus") or row.get("variant_site"))
            if _variant_override_matches(override, gene, c_hgvs, p_hgvs, locus):
                return True
    return False


def _patch_reviewed_variant_override_rows(
    report_data: ReportData,
    panel_config: PanelConfig,
) -> None:
    """Apply reviewed YAML variant overrides to rendered 2.1 and summary tables."""
    overrides = panel_config.reviewed_variant_overrides
    if not overrides:
        return

    rows = report_data.get_table("variants_2_1") or []
    changed = False
    for row in rows:
        gene = _norm_text(row.get("gene")).upper()
        locus = _norm_text(row.get("locus"))
        override = _find_reviewed_variant_override(panel_config, gene, locus=locus)
        if not override:
            continue
        benefit, caution = _drugs_from_override(override)
        if benefit or caution:
            row["benefit_drugs"] = benefit or "--"
            row["caution_drugs"] = caution or "--"
            changed = True
    if changed:
        report_data.set_table("variants_2_1", rows)

    tips = list(report_data.get_table("targeted_drug_tips") or [])
    for override in overrides:
        benefit, caution = _drugs_from_override(override)
        if not (benefit or caution):
            continue
        if not _override_has_detected_variant(override, report_data):
            continue
        genes = sorted(_override_gene_values(override))
        if not genes:
            continue
        c_values = _as_text_list(override.get("c_hgvs") or override.get("cHGVS"))
        p_values = _as_text_list(override.get("p_hgvs") or override.get("pHGVS"))
        gene = genes[0]
        variant_site = _norm_text(override.get("variant_site"))
        if not variant_site:
            site_parts = []
            if c_values:
                site_parts.append(c_values[0])
            if p_values:
                site_parts.append(p_values[0])
            variant_site = ",\n".join(site_parts)
        if not variant_site:
            continue
        has_tip = False
        for row in tips:
            if not _variant_override_matches(
                override,
                _norm_text(row.get("gene")),
                locus=_norm_text(row.get("variant_site")),
            ):
                continue
            row["variant_site"] = variant_site
            row["benefit_drugs"] = benefit or "--"
            row["caution_drugs"] = caution or "--"
            has_tip = True
            changed = True
            break
        if has_tip:
            continue
        tips.append(
            {
                "gene": gene,
                "variant_site": variant_site,
                "benefit_drugs": benefit or "--",
                "caution_drugs": caution or "--",
            }
        )
    report_data.set_table("targeted_drug_tips", tips)


def enhance_report_data(
    report_data: ReportData,
    excel_data: ExcelDataSource,
    *,
    field_mapper: Optional[Any] = None,
    gene_knowledge_provider: Optional[GeneKnowledgeProvider] = None,
    base_path: Optional[str] = None,
    panel_id: Optional[str] = None,
    panel_config_path: Optional[str] = None,
) -> ReportData:
    """
    Enhance ReportData with template-specific fields for 358-gene panel.

    Adds:
    - variants (主表：只含重要基因的Ⅰ类、Ⅱ类 - 批注#3)
    - all_variants (全部变异，含Ⅲ类)
    - summary_variants (汇总表：含Ⅲ类但加标注 - 批注#19)
    - immune_positive_variants (免疫正相关 - 批注#12)
    - immune_negative_variants (免疫负相关)
    - immune_hyperprogression_variants (超进展相关)
    - undetected_genes
    - gene_knowledge_sections (基因诊疗知识章节 - 批注#20-35)
    - MSI summary fields
    - TMB summary fields

    Args:
        report_data: Existing ReportData from FieldMapper
        excel_data: Original Excel data
        field_mapper: Optional FieldMapper for drug lookup
        gene_knowledge_provider: Optional GeneKnowledgeProvider for gene knowledge
        base_path: Base path for loading knowledge databases

    Returns:
        Enhanced ReportData
    """
    # Load panel config (instance-based, no global mutation)
    pc = load_panel_config(
        base_path=base_path,
        panel_id=panel_id,
        config_path=panel_config_path,
    )
    # Also sync globals for backward compatibility
    _sync_globals_from_config(pc)

    # Optional: leverage FieldMapper's knowledge base (targeted_drug_db) for drug tips
    drug_lookup: Optional[Callable[[str, str, str, str], Tuple[str, str]]] = None
    if field_mapper is not None:
        try:
            lookup_fn = getattr(
                field_mapper, "_lookup_targeted_drugs_for_variant", None
            )
        except Exception:
            lookup_fn = None

        if callable(lookup_fn):

            def _drug_lookup(
                gene: str, c_hgvs: str, p_hgvs: str, gene_class: str
            ) -> Tuple[str, str]:
                try:
                    benefit, caution, _ = lookup_fn(
                        gene, c_point=c_hgvs, p_point=p_hgvs, variant_level=gene_class
                    )
                    return (benefit or "--", caution or "--")
                except Exception:
                    return ("--", "--")

            drug_lookup = _drug_lookup

    # Panel 前置校验：CRC-358 使用 ExistInsmall358，CRC-301 使用 ExistInsmall301。
    # 两者都不存在时才跳过，避免把非 CRC panel 强行套用 CRC 口径。
    filter_column = _resolve_crc_filter_column(excel_data)
    if not filter_column:
        import logging
        logging.getLogger("reportgen").warning(
            "Variations 表缺少 ExistInsmall358/ExistInsmall301 列，跳过 CRC panel 增强逻辑"
        )
        return report_data

    # Build main variants table (批注#3: 只含重要基因的Ⅰ类、Ⅱ类)
    variants = build_variants_for_template(
        excel_data,
        filter_column=filter_column,
        drug_lookup=drug_lookup,
        panel_config=pc,
    )
    report_data.set_table("variants", variants)
    report_data.set_field(
        "targeted_drug_brand_summary",
        build_targeted_drug_brand_summary(variants, base_path=base_path),
    )

    # Build all variants for summary (含Ⅲ类)
    all_variants = build_all_variants_for_template(
        excel_data,
        filter_column=filter_column,
        drug_lookup=drug_lookup,
        panel_config=pc,
    )
    report_data.set_table("all_variants", all_variants)

    # Build summary variants (批注#19: Ⅲ类加"意义未明突变"标注)
    summary_variants = build_summary_variants(all_variants)
    report_data.set_table("summary_variants", summary_variants)

    # Build immune variants — reviewed final reports only use I/II class
    # variants for immune positive/negative summaries. III/unknown rows may
    # remain in full variant lists, but they must not trigger immune benefit
    # or resistance summaries.
    immune_variants = build_immune_variants(
        excel_data,
        filter_column=filter_column,
        filter_class_i_ii_only=True,
        drug_lookup=drug_lookup,
        panel_config=pc,
    )
    report_data.set_table("immune_positive_variants", immune_variants["positive"])
    report_data.set_table("immune_negative_variants", immune_variants["negative"])
    report_data.set_table(
        "immune_hyperprogression_variants", immune_variants["hyperprogression"]
    )

    # Generate formatted immune result strings for template (v8 template variables)
    # immune_positive_count: 正相关基因数量
    report_data.set_field("immune_positive_count", len(immune_variants["positive"]))

    # immune_positive_result: 正相关基因完整显示文本
    # Format: "检出（N个）\nGENE1：cHGVS，pHGVS\n..."
    report_data.set_field(
        "immune_positive_result",
        format_immune_positive_result(immune_variants["positive"]),
    )

    # immune_positive_genes: 仅基因变异列表（不含"检出（N个）"前缀）
    # Format: "GENE1：cHGVS，pHGVS\nGENE2：cHGVS，pHGVS\n..."
    if immune_variants["positive"]:
        positive_genes_lines = []
        for v in immune_variants["positive"]:
            gene = v.get("gene", "")
            c_hgvs = v.get("cHGVS", "")
            p_hgvs = v.get("pHGVS", "")
            if p_hgvs and p_hgvs not in ("--", "*", ""):
                positive_genes_lines.append(f"{gene}：{c_hgvs}，{p_hgvs}")
            else:
                positive_genes_lines.append(f"{gene}：{c_hgvs}")
        pos_text = "\n".join(positive_genes_lines)
        report_data.set_field("immune_positive_genes", pos_text)
        # 同步到 FieldMapper 的变量名（模板使用 immuno_ 前缀）
        report_data.set_field(
            "immuno_positive_genes",
            f"检出（{len(immune_variants['positive'])}个）\n{pos_text}",
        )
    else:
        report_data.set_field("immune_positive_genes", "")
        report_data.set_field("immuno_positive_genes", "未检出")

    # immune_negative_result: 负相关基因结果 ("未检出" 或检出列表)
    neg_text = format_immune_result(immune_variants["negative"], "negative")
    report_data.set_field("immune_negative_result", neg_text)
    report_data.set_field("immuno_negative_genes", neg_text)

    # immune_hyperprogression_result: 超进展相关基因结果 ("未检出" 或检出列表)
    hyper_text = format_immune_result(immune_variants["hyperprogression"], "hyperprogression")
    report_data.set_field("immune_hyperprogression_result", hyper_text)
    report_data.set_field("immuno_hyperprogression_genes", hyper_text)

    # Statistics fields (v8 template variables)
    # total_variants_count: 总变异数（all_variants包含Ⅰ/Ⅱ/Ⅲ类）
    report_data.set_field("total_variants_count", len(all_variants))

    # drug_related_count: 药物相关变异数。
    # 必须与读者实际看到的 2.1 表(variants_2_1)同源计数，否则脚注"与靶向药物
    # 用药相关的变异 X 个"会与 2.1 表里带药的行数对不上（审计"变异计数一致"
    # 不通过）。2.1 表由 FieldMapper 经 _lookup_targeted_drugs_for_variant 生成，
    # 与此处旧的 build_variants_for_template 列表口径不同（曾出现脚注 4、表格 6
    # 的偏差）。优先用 variants_2_1，缺失时回退旧列表。
    variants_2_1_rows = report_data.get_table("variants_2_1")
    drug_related_source = variants_2_1_rows if variants_2_1_rows else variants
    report_data.set_field(
        "drug_related_count", count_drug_related_variants(drug_related_source)
    )

    # Build undetected genes
    detected_genes = {v["gene"] for v in all_variants}
    undetected_genes = build_undetected_genes(detected_genes, panel_config=pc)
    report_data.set_table("undetected_genes", undetected_genes)

    # ====== T[5] NCCN 检测基因表 + T[6-8] 免疫基因表 动态填充 ======
    _build_nccn_and_immune_fields(
        report_data,
        all_variants,
        excel_data,
        panel_config=pc,
    )

    # 2.1/摘要表中的人工复核变异覆盖口径由 panel YAML 配置驱动。
    _patch_reviewed_variant_override_rows(report_data, pc)

    # 2.2 是 CRC 适应症固定药物表，不来自 CtDrug 全量药敏表。
    if not report_data.get_table("chemotherapy"):
        report_data.set_table("chemotherapy", _build_crc_approved_drugs(pc))

    # MSI/TMB 字段由 FieldMapper 生成（终版口径）；此处仅做缺失兜底，避免覆盖
    for key, value in build_msi_summary(excel_data).items():
        cur = report_data.get_field(key)
        if cur is None or str(cur).strip() in {"", "--"}:
            report_data.set_field(key, value)

    # 对 MSI 必检项目（358/301基因+MSI），msi_status 为"未检测"时发出警告
    msi_val = str(report_data.get_field("msi_status") or "").strip()
    if msi_val in ("未检测", ""):
        import logging
        logging.getLogger("reportgen").warning(
            "msi_status 为 '%s'，但 358/301 基因+MSI 项目中 MSI 是必检项，"
            "请检查 Excel 中 Msisensor sheet 或 MSI状态 字段是否缺失",
            msi_val,
        )

    for key, value in build_tmb_summary(excel_data).items():
        cur = report_data.get_field(key)
        if cur is None or str(cur).strip() in {"", "--"}:
            report_data.set_field(key, value)

    # 若 CtDrug 汇总为空，但主表存在药物关联，回填 targeted_drug_tips（4列）
    try:
        existing_tips = report_data.get_table("targeted_drug_tips") or []
        if not existing_tips:
            backfilled = _fallback_targeted_drug_tips_from_variants(variants)
            if backfilled:
                report_data.set_table("targeted_drug_tips", backfilled)
    except Exception as e:
        import logging
        logging.getLogger("reportgen").warning(
            "靶向药物提示回填失败: %s", e
        )

    report_content_cfg = report_data.get_field("report_content")
    report_content_cfg = report_content_cfg if isinstance(report_content_cfg, dict) else {}

    def _select_part3_variants(scope: str, default_variants: List[Dict[str, str]]) -> List[Dict[str, str]]:
        scope_key = str(scope or "").strip().lower()
        if scope_key in {"summary", "summary_variants"}:
            return summary_variants
        if scope_key in {"all", "all_variants"}:
            return all_variants
        if scope_key in {"visible", "variants", "part2", "part2_variants"}:
            return variants
        return default_variants

    # Build gene knowledge sections (批注#20-35: 基因诊疗知识)
    if gene_knowledge_provider is not None:
        try:
            # Load knowledge base if not already loaded
            gene_knowledge_provider.load(base_path)

            # 第三部分解析范围由 settings.report_content 控制。默认仍支持只解析
            # 2.1 主表变异；本次 reviewed CRC 口径使用 summary_variants，包含
            # 第二维度汇总中展示的 III 类/非用药变异，但不扩展到全 panel。
            part3_variants = _select_part3_variants(
                report_content_cfg.get("part3_variant_scope", "variants"),
                variants,
            )
            reference_variants = _select_part3_variants(
                report_content_cfg.get("part3_reference_variant_scope", "variants"),
                part3_variants,
            )
            gene_knowledge_sections = (
                gene_knowledge_provider.build_all_gene_knowledge_sections(
                    variants=part3_variants, cancer_type="结直肠癌"
                )
            )
            report_data.set_table("gene_knowledge_sections", gene_knowledge_sections)

            # Build drug analysis sections (用药提示解析)
            # Use variants (主表) which contains drug information
            drug_analysis_sections = (
                gene_knowledge_provider.build_drug_analysis_sections(variants=variants)
            )
            report_data.set_table("drug_analysis_sections", drug_analysis_sections)

            # 拆分为获益/负相关两组（模板中分别循环）
            drug_benefit_sections = [
                ds for ds in drug_analysis_sections if ds.get("drug_type") == "benefit"
            ]
            drug_caution_sections = [
                ds for ds in drug_analysis_sections if ds.get("drug_type") == "caution"
            ]
            report_data.set_table("drug_benefit_sections", drug_benefit_sections)
            report_data.set_table("drug_caution_sections", drug_caution_sections)

            # Build references (参考文献) — follows configured Part 3 scope.
            references = gene_knowledge_provider.build_all_references_flat(
                variants=reference_variants, max_per_gene=5
            )
            report_data.set_table("references", references)
            report_data.set_table("gene_references", references)  # 模板中引用名

            # 全局"引用标识→文献全文"映射：供 rebuild_references 处理器按正文
            # 实际引用（含静态附录章节）重建 5.参考文献，确保每个被引 PMID/NCT
            # 都有对应文献条目。
            try:
                report_data.set_field(
                    "reference_lookup",
                    gene_knowledge_provider.build_reference_lookup(),
                )
            except Exception as _ref_err:  # pragma: no cover - defensive
                import logging

                logging.getLogger("reportgen").warning(
                    "构建参考文献映射失败（不阻断）: %s", _ref_err
                )

            # Also provide grouped references by gene
            references_by_gene = gene_knowledge_provider.build_references(
                variants=reference_variants, max_per_gene=5
            )
            report_data.set_table("references_by_gene", references_by_gene)

        except Exception as e:
            import logging
            logging.getLogger("reportgen").warning(
                "基因知识章节构建失败（不阻断报告生成）: %s", e
            )

    return report_data


def _fallback_targeted_drug_tips_from_variants(
    variants: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Build 4-column targeted drug tips from variants table as a fallback.

    Mapping expects columns: gene, variant_site, benefit_drugs, caution_drugs.
    We'll derive them from variant entries prepared for the aligned template.
    """
    rows: List[Dict[str, str]] = []
    for v in variants:
        gene = (v.get("gene") or v.get("Gene") or "").strip()
        c_hgvs = (v.get("cHGVS") or v.get("locus") or v.get("variant") or "").strip()
        benefit = v.get("benefit_drugs") or "--"
        caution = v.get("caution_drugs") or "--"
        # 仅在存在任一药物关联时输出（避免空行）
        if (
            gene
            and c_hgvs
            and ((benefit and benefit != "--") or (caution and caution != "--"))
        ):
            rows.append(
                {
                    "gene": str(gene),
                    "variant_site": str(c_hgvs),
                    "benefit_drugs": str(benefit),
                    "caution_drugs": str(caution),
                }
            )
    return rows
