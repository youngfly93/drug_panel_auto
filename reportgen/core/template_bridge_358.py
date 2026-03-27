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
from reportgen.models.excel_data import ExcelDataSource
from reportgen.models.report_data import ReportData
from reportgen.utils.hgvs_utils import infer_variant_type_cn

# Panel gene definitions for 358-gene colorectal cancer panel.
#
# Defaults are kept in-code for backwards compatibility. For production, keep
# the rule sets in `config/panels/crc_358.yaml` so that medical "口径" updates
# do not require a code release.
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
    panel_display_genes: List[Dict[str, str]] = field(
        default_factory=lambda: [dict(x) for x in _DEFAULT_PANEL_DISPLAY_GENES]
    )

    @property
    def all_immune_genes(self) -> Set[str]:
        return (
            self.immune_positive_genes
            | self.immune_negative_genes
            | self.immune_hyperprogression_genes
        )


def _resolve_config_path(base_path: Optional[str] = None) -> Optional[Path]:
    """Find the crc_358.yaml config file."""
    candidates: List[Path] = []
    if base_path:
        bp = Path(str(base_path)).expanduser().resolve()
        candidates.append(bp / "config" / "panels" / "crc_358.yaml")
    candidates.append(Path("config") / "panels" / "crc_358.yaml")
    candidates.append(
        Path(__file__).resolve().parents[2] / "config" / "panels" / "crc_358.yaml"
    )
    for p in candidates:
        if p.exists() and p.is_file():
            return p.resolve()
    return None


def load_panel_config(*, base_path: Optional[str] = None) -> PanelConfig:
    """Load a PanelConfig instance from ``config/panels/crc_358.yaml``.

    Returns a *new* PanelConfig every call — no global mutation.
    Falls back to defaults when the config file is missing or invalid.
    """
    cfg_path = _resolve_config_path(base_path)
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

    pc = PanelConfig(
        class_i_genes=as_gene_set("class_i_genes", set(_DEFAULT_CLASS_I_GENES)),
        class_ii_genes=as_gene_set("class_ii_genes", set(_DEFAULT_CLASS_II_GENES)),
        crc_important_genes=as_gene_set("crc_important_genes", set(_DEFAULT_CRC_IMPORTANT_GENES)),
        immune_positive_genes=as_gene_set("immune_positive_genes", set(_DEFAULT_IMMUNE_POSITIVE_GENES)),
        immune_negative_genes=as_gene_set("immune_negative_genes", set(_DEFAULT_IMMUNE_NEGATIVE_GENES)),
        immune_hyperprogression_genes=as_gene_set(
            "immune_hyperprogression_genes", set(_DEFAULT_IMMUNE_HYPERPROGRESSION_GENES)
        ),
    )
    if panel_display is not None:
        pc.panel_display_genes = panel_display
    return pc


# Lazy default singleton
_default_panel_config: Optional[PanelConfig] = None
_default_panel_config_base_path: Optional[str] = None


def get_default_panel_config(base_path: Optional[str] = None) -> PanelConfig:
    """Return a lazily-initialised default PanelConfig.

    Reloads if *base_path* changes from the previously cached value.
    """
    global _default_panel_config, _default_panel_config_base_path
    if _default_panel_config is None or base_path != _default_panel_config_base_path:
        _default_panel_config = load_panel_config(base_path=base_path)
        _default_panel_config_base_path = base_path
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

    cfg_path = _resolve_config_path(base_path)
    if cfg_path is None:
        return None
    if _LOADED_CRC_358_CONFIG_PATH == cfg_path:
        return cfg_path

    pc = load_panel_config(base_path=base_path)
    _sync_globals_from_config(pc)
    _default_panel_config = pc
    _LOADED_CRC_358_CONFIG_PATH = cfg_path
    return cfg_path

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


from reportgen.utils.text_utils import norm_text as _norm_text  # unified implementation


def _get_gene_class(gene: str, exist_in_552: Any, panel_config: Optional[PanelConfig] = None) -> str:
    """
    Determine gene class based on gene name and ExistIn552 value.

    Args:
        gene: Gene symbol
        exist_in_552: ExistIn552 column value (1, 0, or Chinese labels)

    Returns:
        Gene class string: "Ⅰ类", "Ⅱ类", or "Ⅲ类"
    """
    if panel_config is None:
        panel_config = get_default_panel_config()
    # First check by gene name
    gene_upper = gene.upper()
    if gene_upper in panel_config.class_i_genes:
        return "Ⅰ类"
    if gene_upper in panel_config.class_ii_genes:
        return "Ⅱ类"

    # If not in known classes, check ExistIn552
    val = _norm_text(exist_in_552)
    if val in ("Ⅰ类", "Ⅱ类", "Ⅲ类"):
        return val

    # Numeric mapping (if exists)
    # For now, default to Ⅲ类 for unknown genes
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
    variants = []

    for row in variations:
        # Filter: only include variants with ExistInsmall358 == 1
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
        gene_class = _get_gene_class(gene, row.get("ExistIn552"), panel_config=panel_config)

        # 批注#3: 只显示Ⅰ类和Ⅱ类基因
        if filter_class_i_ii_only and gene_class == "Ⅲ类":
            continue

        # Get pHGVS notation (cHGVS already extracted above)
        p_hgvs = _norm_text(row.get("pHGVS_S") or row.get("pHGVS_A"))
        if not p_hgvs or p_hgvs == "*":
            p_hgvs = "--"

        # Get clinical significance
        clnsig = _norm_text(row.get("CLNSIG"))
        if clnsig and clnsig not in ("*", "-"):
            clinical_significance = clnsig
        else:
            clinical_significance = "致病"  # Default for detected variants

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
        clinical_significance = v.get("clinical_significance", "致病")
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
        filter_class_i_ii_only=False,
        important_genes_only=False,
        drug_lookup=drug_lookup,
        panel_config=panel_config,
    )

    positive_variants = []
    negative_variants = []
    hyperprogression_variants = []

    # 构建 CLNSIG 快速查找（从原始 Variations）
    _raw_variations = excel_data.get_table_data("Variations") or []
    _clnsig_map: Dict[str, str] = {}
    for r in _raw_variations:
        g = _norm_text(r.get("Gene_Symbol") or r.get("Gene"))
        c = _norm_text(r.get("cHGVS"))
        clnsig = _norm_text(r.get("CLNSIG"))
        if g and c:
            _clnsig_map[f"{g.upper()}:{c}"] = clnsig

    # Pathogenicity 白名单：免疫摘要只包含致病性/可能致病性变异
    _pathogenic_keywords = {"pathogenic", "likely_pathogenic", "致病", "可能致病"}

    def _is_pathogenic(gene: str, chgvs: str) -> bool:
        clnsig = _clnsig_map.get(f"{gene.upper()}:{chgvs}", "").lower()
        if not clnsig or clnsig in ("*", "-", ""):
            return True  # 无 CLNSIG 数据时默认放行
        return any(kw in clnsig for kw in _pathogenic_keywords)

    for v in all_variants:
        gene = v["gene"].upper()
        gene_class = v.get("gene_class", "")

        # 批注#12: 只显示Ⅰ类和Ⅱ类
        if filter_class_i_ii_only and gene_class == "Ⅲ类":
            continue

        # 免疫摘要二次过滤：排除 Benign/Likely_benign/Uncertain_significance
        chgvs = v.get("cHGVS", "")
        if not _is_pathogenic(v.get("gene", ""), chgvs):
            continue

        # Add "(意义未明突变)" annotation for Ⅲ类 if not filtered out
        clinical_sig = v.get("clinical_significance", "致病")
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

    Returns dict with: msi_status, msi_status_cn, msi_summary
    """
    # 优先使用ExcelReader已抽取的单值（Msisensor解析）
    raw_status = excel_data.single_values.get("MSI状态")
    msi_status = str(raw_status).strip() if raw_status is not None else ""
    if not msi_status:
        msi_status = "MSS"

    up = msi_status.upper()
    if up == "MSS":
        msi_status = "MSS"
        msi_status_cn = "微卫星稳定型，MSS"
        msi_summary = "微卫星稳定型，MSS"
    elif up == "MSI-H":
        msi_status = "MSI-H"
        msi_status_cn = "微卫星高度不稳定，MSI-H"
        msi_summary = "微卫星不稳定型，MSI-H"
    elif up == "MSI-L":
        msi_status = "MSI-L"
        msi_status_cn = "微卫星低度不稳定，MSI-L"
        msi_summary = "微卫星不稳定型，MSI-L"
    elif up.startswith("MSI"):
        # 兜底：保持原始值
        msi_status_cn = msi_status
        msi_summary = f"微卫星不稳定型，{msi_status}"
    else:
        msi_status_cn = msi_status
        msi_summary = msi_status

    return {
        "msi_status": msi_status,
        "msi_status_cn": msi_status_cn,
        "msi_summary": msi_summary,
    }


def build_tmb_summary(excel_data: ExcelDataSource) -> Dict[str, str]:
    """
    Build TMB summary fields.

    Returns dict with: tmb_value, tmb_status, tmb_level_cn, tmb_reference, tmb_summary
    """
    # Get TMB from single values
    tmb_val = excel_data.single_values.get("TMB")

    if tmb_val is None:
        return {
            "tmb_value": "--",
            "tmb_status": "L",
            "tmb_level_cn": "低",
            "tmb_reference": 10,
            "tmb_summary": "",
        }

    try:
        tmb = float(tmb_val)
        # 样本类型决定参考值：组织10；血液16
        sample_type = str(excel_data.single_values.get("样本类型") or "组织")
        threshold = (
            16 if ("血" in sample_type or "blood" in sample_type.lower()) else 10
        )

        tmb_status = "H" if tmb >= threshold else "L"
        tmb_level_cn = "高" if tmb_status == "H" else "低"
        level = "TMB-H" if tmb_status == "H" else "TMB-L"
        direction = "高于" if tmb_status == "H" else "低于"
        unit = "mutations/Mb"

        return {
            "tmb_value": f"{tmb:.1f}",
            "tmb_status": tmb_status,
            "tmb_level_cn": tmb_level_cn,
            "tmb_reference": threshold,
            "tmb_summary": (
                f"{tmb:.1f}{unit}，{level}\n"
                f"(本次检测结果{direction}参考值\n{threshold} mutations/Mb)"
            ),
        }
    except (ValueError, TypeError):
        return {
            "tmb_value": str(tmb_val),
            "tmb_status": "L",
            "tmb_level_cn": "低",
            "tmb_reference": 10,
            "tmb_summary": str(tmb_val),
        }


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

    # Format as list of gene:mutation pairs
    lines = []
    for v in variants:
        gene = v.get("gene", "")
        c_hgvs = v.get("cHGVS", "")
        p_hgvs = v.get("pHGVS", "")

        if p_hgvs and p_hgvs not in ("--", "*", ""):
            line = f"{gene}：{c_hgvs}，{p_hgvs}"
        else:
            line = f"{gene}：{c_hgvs}"
        lines.append(line)

    return "检出：" + "；".join(lines)


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
) -> None:
    """为 T[5] NCCN 检测基因表和 T[6-8] 免疫基因表生成动态填充变量。

    逻辑：遍历 all_variants，按基因+外显子/检测内容匹配，
    检出时填入 cHGVS，pHGVS；未检出时填"未检出"/"未检出有害变异"。
    """
    # 构建基因→变异映射（同一基因可能有多个变异）
    gene_variants: Dict[str, List[Dict[str, str]]] = {}
    for v in all_variants:
        g = v.get("gene", "").upper()
        if g:
            gene_variants.setdefault(g, []).append(v)

    # 从原始 Variations 补充（all_variants 可能被 ExistInsmall358 过滤）
    raw_variations = excel_data.get_table_data("Variations") or []
    for r in raw_variations:
        g = _norm_text(r.get("Gene_Symbol") or r.get("Gene"))
        if not g:
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
                    if "CNV" in c_hgvs or "扩增" in c_hgvs or "amp" in c_hgvs.lower():
                        filtered.append(v)
                elif "突变" in ef or "mut" in ef:
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
            if p and p not in ("--", "*", ""):
                parts.append(f"{c}，{p}")
            else:
                parts.append(c)
        return "\n".join(parts)

    def _immune_result(gene_key: str) -> str:
        """免疫基因检测结果：检出时返回变异详情；未检出时返回标准文本。"""
        variants = gene_variants.get(gene_key.upper(), [])
        if not variants:
            return "未检出有害变异"
        parts = []
        for v in variants:
            c = v.get("cHGVS", "")
            p = v.get("pHGVS", "")
            if p and p not in ("--", "*", ""):
                parts.append(f"{c}，{p}")
            else:
                parts.append(c)
        return "\n".join(parts)

    # ===== T[5] NCCN 检测基因表 =====
    nccn_map = {
        "EGFR_EX18": ("EGFR", "外显子18"), "EGFR_EX19": ("EGFR", "外显子19"),
        "EGFR_EX20": ("EGFR", "外显子20"), "EGFR_EX21": ("EGFR", "外显子21"),
        "KRAS_EX2": ("KRAS", "外显子2"), "KRAS_EX3": ("KRAS", "外显子3"),
        "KRAS_EX4": ("KRAS", "外显子4"),
        "ALK_FUSION": ("ALK", "融合"), "ROS1_FUSION": ("ROS1", "融合"),
        "RET_FUSION": ("RET", "融合"),
        "ERBB2_MUT": ("ERBB2", "突变"), "ERBB2_AMP": ("ERBB2", "扩增"),
        "PIK3CA_EX10": ("PIK3CA", "外显子10"), "PIK3CA_EX21": ("PIK3CA", "外显子21"),
        "MET_EX14SKIP": ("MET", "外显子14跳跃"), "MET_AMP": ("MET", "扩增"),
        "NRAS_EX2": ("NRAS", "外显子2"), "NRAS_EX3": ("NRAS", "外显子3"),
        "NRAS_EX4": ("NRAS", "外显子4"),
        "BRAF_V600": ("BRAF", "密码子600"),
        "FGFR123_MUT": ("FGFR1", "突变"), "FGFR123_FUSION": ("FGFR1", "融合"),
        "NTRK123_FUSION": ("NTRK1", "融合"),
        "KIT_EX9": ("KIT", "外显子9"), "KIT_EX11": ("KIT", "外显子11"),
        "KIT_EX13": ("KIT", "外显子13"), "KIT_EX17": ("KIT", "外显子17"),
        "PDGFRA_EX12": ("PDGFRA", "外显子12"), "PDGFRA_EX14": ("PDGFRA", "外显子14"),
        "PDGFRA_EX18": ("PDGFRA", "外显子18"),
        "BRCA12_MUT": ("BRCA1", "突变"), "IDH12_MUT": ("IDH1", "突变"),
    }
    for key, (gene, exon_filter) in nccn_map.items():
        # FGFR1/2/3 和 NTRK1/2/3 需要合并多个基因
        if key == "FGFR123_MUT":
            results = [_format_result(g, "突变") for g in ("FGFR1", "FGFR2", "FGFR3")]
            val = next((r for r in results if r != "未检出"), "未检出")
        elif key == "FGFR123_FUSION":
            results = [_format_result(g, "融合") for g in ("FGFR1", "FGFR2", "FGFR3")]
            val = next((r for r in results if r != "未检出"), "未检出")
        elif key == "NTRK123_FUSION":
            results = [_format_result(g, "融合") for g in ("NTRK1", "NTRK2", "NTRK3")]
            val = next((r for r in results if r != "未检出"), "未检出")
        elif key == "BRCA12_MUT":
            results = [_format_result(g, "突变") for g in ("BRCA1", "BRCA2")]
            val = next((r for r in results if r != "未检出"), "未检出")
        elif key == "IDH12_MUT":
            results = [_format_result(g, "突变") for g in ("IDH1", "IDH2")]
            val = next((r for r in results if r != "未检出"), "未检出")
        else:
            val = _format_result(gene, exon_filter)
        report_data.set_field(f"nccn_{key}", val)

    # ===== T[6] 免疫正相关基因 =====
    imm_pos_keys = [
        "MLH1", "MSH2", "MSH6", "PMS2", "POLE", "POLD1",
        "CD274", "PDCD1LG2", "PBRM1", "KRAS", "KRAS_TP53",
        "TET1", "SERPINB3", "SERPINB4", "DDR",
    ]
    for key in imm_pos_keys:
        if key == "KRAS_TP53":
            # 共突变：两者都检出才算
            k_var = gene_variants.get("KRAS", [])
            t_var = gene_variants.get("TP53", [])
            if k_var and t_var:
                val = "检出共突变"
            else:
                val = "未检出有害变异"
        elif key == "DDR":
            # DDR 基因组（多个 DNA 损伤修复基因合并）
            ddr_genes = [
                "ATM", "ATR", "BRCA1", "BRCA2", "PALB2", "CHEK2",
                "ARID1A", "ATRX", "CDK12", "FANCI", "FANCM",
                "MRE11A", "NBN", "RAD50", "RAD51",
            ]
            found = []
            for dg in ddr_genes:
                vs = gene_variants.get(dg.upper(), [])
                for v in vs:
                    c = v.get("cHGVS", "")
                    p = v.get("pHGVS", "")
                    if p and p not in ("--", "*", ""):
                        found.append(f"{dg}：{c}，{p}")
                    elif c:
                        found.append(f"{dg}：{c}")
            val = "\n".join(found) if found else "未检出有害变异"
        else:
            val = _immune_result(key)
        report_data.set_field(f"imm_pos_{key}", val)

    # ===== T[7] 免疫负相关基因 =====
    imm_neg_keys = [
        "PTEN", "JAK1", "JAK2", "B2M", "CTNNB1",
        "EGFR_L858R", "ALK", "MET", "STK11", "KRAS_STK11",
        "KEAP1", "IFNGR12",
    ]
    for key in imm_neg_keys:
        if key == "EGFR_L858R":
            # EGFR L858R 或 EX19del 特定突变
            vs = gene_variants.get("EGFR", [])
            found = [v for v in vs if "L858R" in (v.get("pHGVS", "") or "") or "EX19" in (v.get("cHGVS", "") or "")]
            val = "\n".join(f"{v.get('cHGVS','')}" for v in found) if found else "未检出有害变异"
        elif key == "KRAS_STK11":
            k_var = gene_variants.get("KRAS", [])
            s_var = gene_variants.get("STK11", [])
            val = "检出共突变" if (k_var and s_var) else "未检出有害变异"
        elif key == "IFNGR12":
            r1 = gene_variants.get("IFNGR1", [])
            r2 = gene_variants.get("IFNGR2", [])
            found = []
            for v in r1 + r2:
                c = v.get("cHGVS", "")
                p = v.get("pHGVS", "")
                g = v.get("gene", "")
                if p and p not in ("--", "*", ""):
                    found.append(f"{g}：{c}，{p}")
                elif c:
                    found.append(f"{g}：{c}")
            val = "\n".join(found) if found else "未检出有害变异"
        else:
            val = _immune_result(key)
        report_data.set_field(f"imm_neg_{key}", val)

    # ===== T[8] 免疫超进展基因 =====
    imm_hyper_keys = [
        "MDM2", "MDM4", "DNMT3A", "EGFR_AMP",
        "CCND1", "FGF3", "FGF4", "FGF19",
    ]
    for key in imm_hyper_keys:
        if key == "EGFR_AMP":
            val = _immune_result("EGFR")  # 扩增检测
        else:
            val = _immune_result(key)
        report_data.set_field(f"imm_hyper_{key}", val)


def enhance_report_data(
    report_data: ReportData,
    excel_data: ExcelDataSource,
    *,
    field_mapper: Optional[Any] = None,
    gene_knowledge_provider: Optional[GeneKnowledgeProvider] = None,
    base_path: Optional[str] = None,
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
    pc = load_panel_config(base_path=base_path)
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

    # Panel 前置校验：检查 Variations 表是否包含 CRC panel 必需列（ExistInsmall358）
    # 如果不包含，说明数据不是 CRC panel 格式，跳过增强逻辑避免错误覆盖
    variations_data = excel_data.get_table_data("Variations") or []
    if variations_data:
        first_row_keys = set(variations_data[0].keys()) if variations_data[0] else set()
        if "ExistInsmall358" not in first_row_keys:
            import logging
            logging.getLogger("reportgen").warning(
                "Variations 表缺少 ExistInsmall358 列，跳过 CRC-358 panel 增强逻辑"
            )
            return report_data

    # Build main variants table (批注#3: 只含重要基因的Ⅰ类、Ⅱ类)
    variants = build_variants_for_template(excel_data, drug_lookup=drug_lookup, panel_config=pc)
    report_data.set_table("variants", variants)

    # Build all variants for summary (含Ⅲ类)
    all_variants = build_all_variants_for_template(excel_data, drug_lookup=drug_lookup, panel_config=pc)
    report_data.set_table("all_variants", all_variants)

    # Build summary variants (批注#19: Ⅲ类加"意义未明突变"标注)
    summary_variants = build_summary_variants(all_variants)
    report_data.set_table("summary_variants", summary_variants)

    # Build immune variants — 按免疫基因集筛选，不按 CRC Ⅰ/Ⅱ类硬裁
    # 确保 JAK1 等 Ⅲ类但属于免疫相关的变异能正确出现在免疫摘要中
    immune_variants = build_immune_variants(
        excel_data, filter_class_i_ii_only=False, drug_lookup=drug_lookup, panel_config=pc
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

    # drug_related_count: 药物相关变异数
    report_data.set_field("drug_related_count", count_drug_related_variants(variants))

    # Build undetected genes
    detected_genes = {v["gene"] for v in all_variants}
    undetected_genes = build_undetected_genes(detected_genes, panel_config=pc)
    report_data.set_table("undetected_genes", undetected_genes)

    # ====== T[5] NCCN 检测基因表 + T[6-8] 免疫基因表 动态填充 ======
    _build_nccn_and_immune_fields(report_data, all_variants, excel_data)

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

    # Build gene knowledge sections (批注#20-35: 基因诊疗知识)
    if gene_knowledge_provider is not None:
        try:
            # Load knowledge base if not already loaded
            gene_knowledge_provider.load(base_path)

            # Build knowledge sections only for Part 2 visible variants
            # 第三部分口径：只解析第二部分已上屏的变异（variants = Ⅰ/Ⅱ类重要基因）
            # 避免用 all_variants (58个) 导致报告膨胀到 100+ 页
            part2_variants = variants  # Ⅰ/Ⅱ类重要基因变异
            gene_knowledge_sections = (
                gene_knowledge_provider.build_all_gene_knowledge_sections(
                    variants=part2_variants, cancer_type="结直肠癌"
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

            # Build references (参考文献) — 同样只覆盖第二部分上屏的变异
            references = gene_knowledge_provider.build_all_references_flat(
                variants=part2_variants, max_per_gene=5
            )
            report_data.set_table("references", references)
            report_data.set_table("gene_references", references)  # 模板中引用名

            # Also provide grouped references by gene
            references_by_gene = gene_knowledge_provider.build_references(
                variants=part2_variants, max_per_gene=5
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
