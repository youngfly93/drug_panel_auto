"""
基因知识库加载器

从Excel数据库加载基因诊疗知识，包括：
- 基因简介
- 基因变异解析
- 药物疗效临床解析

Python 3.9 compatible.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import pandas as pd

from .governance import effective_governance
from .mutation_description import MutationDescriptionGenerator


class GeneKnowledgeProvider:
    """
    基因知识库提供者

    从Excel文件加载基因诊疗知识，并提供查询接口。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化基因知识库

        Args:
            config: 配置字典，包含知识库路径和列名映射
        """
        self.config = config or {}
        self._loaded = False

        # Gene-symbol aliases are panel-scoped.  They normalize knowledge
        # lookup and Part-3 variant identity without rewriting the input gene
        # label shown in the report.  This is deliberately not a global alias
        # dictionary: historical panel keys can be ambiguous across assays.
        raw_gene_aliases = self.config.get("gene_symbol_aliases")
        if raw_gene_aliases is None:
            raw_gene_aliases = (self.config.get("gene_knowledge_db") or {}).get(
                "gene_symbol_aliases"
            )
        self._gene_symbol_aliases: Dict[str, str] = {}
        self._gene_aliases_by_canonical: Dict[str, tuple[str, ...]] = {}
        self._configure_gene_symbol_aliases(raw_gene_aliases)

        # 数据缓存
        self._gene_analysis_df: Optional[pd.DataFrame] = None
        self._drug_analysis_df: Optional[pd.DataFrame] = None
        self._gene_transcript_df: Optional[pd.DataFrame] = None
        self._references_df: Optional[pd.DataFrame] = None

        # 索引缓存（基因名 -> 数据行）
        self._gene_intro_cache: Dict[str, str] = {}
        self._gene_analysis_cache: Dict[str, str] = {}
        # Stable protein/domain statements are kept independently from the
        # replaceable gene/variant narrative.  Otherwise a reviewed overlay can
        # silently discard the only copy of fixed structural knowledge.
        self._gene_fixed_domain_cache: Dict[str, str] = {}
        self._reviewed_gene_analysis_cache: Dict[str, Dict[str, str]] = {}
        self._reviewed_gene_section_overrides: Dict[str, Dict[str, str]] = {}
        # gene-level (variant-agnostic) Part-3 overrides; lower precedence than
        # variant-level, higher than the base KB. Keyed by normalized gene.
        self._gene_level_section_overrides: Dict[str, Dict[str, str]] = {}
        self._reviewed_drug_section_overrides: Dict[tuple[str, str], List[Dict[str, str]]] = {}
        # gene-level (variant-agnostic) drug-relation overrides; keyed by
        # (normalized gene, drug_type). Lower precedence than variant-level.
        self._gene_level_drug_overrides: Dict[tuple[str, str], List[Dict[str, str]]] = {}
        self._extra_references: List[str] = []
        self._reference_registry: Dict[str, Dict[str, str]] = {
            "pmid": {},
            "trial": {},
        }
        self._drug_analysis_cache: Dict[str, Dict[str, str]] = {}
        self._drug_full_cache: Dict[str, List[Dict[str, str]]] = {}  # 完整药物信息
        self._gene_transcript_cache: Dict[str, Dict[str, str]] = {}
        self._references_cache: Dict[str, List[str]] = {}  # 基因 -> 参考文献列表

        # 位点描述生成器
        self._mutation_desc_gen = MutationDescriptionGenerator()

    def load(self, base_path: Optional[str] = None) -> bool:
        """
        加载知识库数据

        Args:
            base_path: 基础路径，配置中的相对路径将相对于此

        Returns:
            是否加载成功
        """
        if self._loaded:
            return True

        if not self.config.get("enabled", False):
            return False

        base = Path(base_path) if base_path else Path(".")

        # 加载基因知识库
        gene_kb_config = self.config.get("gene_knowledge_db", {})
        if gene_kb_config.get("enabled", False):
            db_path = base / gene_kb_config.get("path", "")
            if db_path.exists():
                self._load_gene_knowledge_db(db_path, gene_kb_config)
            self._load_reviewed_part3_overlays(base, gene_kb_config)
            self._load_reference_registry(base, gene_kb_config)

        # 加载基因-转录本-染色体信息
        transcript_config = self.config.get("gene_transcript_db", {})
        if transcript_config.get("enabled", False):
            db_path = base / transcript_config.get("path", "")
            if db_path.exists():
                self._load_gene_transcript_db(db_path, transcript_config)

        self._loaded = True
        return True

    def _load_reference_registry(self, base: Path, config: Dict) -> None:
        """Load structured citation titles maintained outside the legacy workbook."""
        raw_path = str(config.get("reference_registry_path") or "").strip()
        if not raw_path:
            return
        path = Path(raw_path)
        if not path.is_absolute():
            path = base / path
        if not path.exists():
            return
        try:
            import yaml

            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return
        for row in data.get("references") or []:
            if not isinstance(row, dict):
                continue
            ref_type = str(row.get("type") or "").strip().lower()
            raw_id = str(row.get("id") or "").strip()
            citation = str(row.get("citation") or "").strip()
            if not citation:
                continue
            if ref_type in {"pubmed", "pmid"}:
                match = re.search(r"0*(\d{5,9})", raw_id)
                if match:
                    self._reference_registry["pmid"].setdefault(
                        str(int(match.group(1))), citation
                    )
            elif ref_type in {"trial", "clinical_trial"}:
                match = re.search(r"(?i)((?:NCT|CTR|ChiCTR)\d+)", raw_id)
                if match:
                    self._reference_registry["trial"].setdefault(
                        match.group(1).upper(), citation
                    )

    def _load_gene_knowledge_db(self, path: Path, config: Dict) -> None:
        """加载基因知识库Excel文件"""
        import logging
        _log = logging.getLogger("reportgen.knowledge")

        try:
            sheets = config.get("sheets", {})
            columns = config.get("columns", {})

            # 确定Excel引擎
            engine = "openpyxl" if str(path).endswith(".xlsx") else "xlrd"

            # 加载基因变异解析sheet
            gene_sheet = sheets.get("gene_analysis", "基因变异解析")
            try:
                self._gene_analysis_df = pd.read_excel(
                    str(path), sheet_name=gene_sheet, engine=engine
                )
                self._build_gene_analysis_cache(columns)
            except Exception as e:
                _log.warning("加载基因变异解析sheet失败: %s (sheet=%s)", e, gene_sheet)

            # 加载用药提示解析sheet
            drug_sheet = sheets.get("drug_analysis", "用药提示解析")
            try:
                self._drug_analysis_df = pd.read_excel(
                    str(path), sheet_name=drug_sheet, engine=engine
                )
                self._build_drug_analysis_cache(columns)
            except Exception as e:
                _log.warning("加载用药提示解析sheet失败: %s (sheet=%s)", e, drug_sheet)

            # 加载参考文献sheet
            ref_sheet = sheets.get("references", "参考文献")
            try:
                self._references_df = pd.read_excel(
                    str(path), sheet_name=ref_sheet, engine=engine
                )
                self._build_references_cache(columns)
            except Exception as e:
                _log.warning("加载参考文献sheet失败: %s (sheet=%s)", e, ref_sheet)

        except Exception as e:
            _log.warning("基因知识库加载失败: %s (path=%s)", e, path)

    def _load_reviewed_part3_overlays(self, base: Path, config: Dict) -> None:
        """Load reviewed Part 3 YAML overlays for final-report wording."""
        import logging

        _log = logging.getLogger("reportgen.knowledge")
        paths: List[str] = []
        for key in (
            "reviewed_part3_overlay_path",
            "reviewed_part3_overrides_path",
            "reviewed_overrides_path",
        ):
            raw = config.get(key)
            if raw:
                paths.append(str(raw))
        for key in ("reviewed_part3_overlay_paths", "reviewed_overrides_paths"):
            raw_list = config.get(key) or []
            if isinstance(raw_list, (list, tuple)):
                paths.extend(str(item) for item in raw_list if item)

        for raw_path in paths:
            path = Path(raw_path)
            if not path.is_absolute():
                path = base / path
            if not path.exists():
                _log.warning("reviewed Part 3 overlay not found: %s", path)
                continue
            try:
                import yaml

                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception as exc:
                _log.warning("reviewed Part 3 overlay load failed: %s (%s)", exc, path)
                continue

            replace_variant_drug_sections = bool(
                data.get("replace_variant_drug_sections", False)
            )
            replaced_drug_groups: set[tuple[str, str]] = set()

            for row in data.get("gene_sections") or []:
                if not isinstance(row, dict):
                    continue
                if not self._reviewed_row_applies_to_panel(row):
                    continue
                if not self._reviewed_row_runtime_enabled(
                    row, data=data, kind="gene"
                ):
                    continue
                section = {
                    k: self._norm_text(v)
                    for k, v in row.items()
                    if k in {"intro", "mutation_analysis", "fixed_domain_text"}
                    and self._norm_text(v)
                }
                if not section:
                    continue
                raw_replace_fields = row.get("replace_fields") or []
                if isinstance(raw_replace_fields, str):
                    raw_replace_fields = [raw_replace_fields]
                replace_fields = {
                    self._norm_text(field)
                    for field in raw_replace_fields
                    if self._norm_text(field)
                    in {"intro", "mutation_analysis"}
                }
                # Gene-level prose normally follows first-writer precedence so
                # an additive overlay cannot silently rewrite reviewed text.
                # A later correction may replace named fields only when it also
                # declares the source entry it supersedes, preserving an
                # explicit audit trail in the YAML rather than editing history.
                if replace_fields and not self._norm_text(row.get("supersedes")):
                    _log.warning(
                        "ignored replace_fields without supersedes: %s (%s)",
                        row.get("gene"),
                        path,
                    )
                    replace_fields = set()
                gene_key = self._hgvs_key(row.get("gene"))
                # Historical reviewed rows often stored a stable protein/domain
                # sentence at the front of a variant-specific analysis.  Treat
                # only that narrowly recognisable sentence as gene-level fixed
                # knowledge; the consequence text remains variant-scoped.
                explicit_fixed = section.get("fixed_domain_text", "")
                derived_fixed = self._extract_fixed_domain_sentence(
                    gene_key,
                    section.get("mutation_analysis", ""),
                    section.get("intro", ""),
                )
                if explicit_fixed:
                    # An explicit reviewed field is the configured source of
                    # truth.  Later overlays intentionally supersede legacy
                    # sentences derived from variant prose instead of appending
                    # a second, potentially conflicting protein description.
                    fixed_domain_text = self._merge_fixed_domain_texts(
                        explicit_fixed
                    )
                    section["fixed_domain_text"] = fixed_domain_text
                    self._gene_fixed_domain_cache[gene_key] = fixed_domain_text
                elif derived_fixed:
                    # Legacy variant prose is only a fill-missing source.  Once
                    # a base or reviewed fixed statement exists, it must not be
                    # promoted again into the variant override and reintroduced
                    # after a later curated replacement.
                    if not self._gene_fixed_domain_cache.get(gene_key):
                        self._gene_fixed_domain_cache[gene_key] = derived_fixed
                    section.pop("fixed_domain_text", None)
                key = self._variant_key(
                    row.get("gene"), row.get("c_hgvs"), row.get("p_hgvs")
                )
                if key:
                    # variant-level override (gene + c_hgvs[+ p_hgvs])
                    self._reviewed_gene_section_overrides[key] = {
                        **self._reviewed_gene_section_overrides.get(key, {}),
                        **section,
                    }
                else:
                    # gene-level override (gene only, no c_hgvs): applies to ANY
                    # variant of this gene. Lets a panel curate cancer-specific
                    # wording (e.g. lung) without listing every variant.
                    if gene_key:
                        existing = self._gene_level_section_overrides.setdefault(
                            gene_key, {}
                        )
                        # Additional overlays may enrich an existing gene row
                        # with an independently governed fixed-domain field. An
                        # explicit correction can replace only the fields named
                        # in ``replace_fields`` and must declare ``supersedes``.
                        for field, value in section.items():
                            if field == "fixed_domain_text" or field in replace_fields:
                                # Fixed-domain overlays are ordered sources of
                                # truth: the later explicit reviewed statement
                                # supersedes an earlier catalog/base statement.
                                # Intro and mutation prose retain first-writer
                                # precedence unless a governed correction opts
                                # into field-level replacement above.
                                existing[field] = value
                            else:
                                existing.setdefault(field, value)

            for row in data.get("drug_sections") or []:
                if not isinstance(row, dict):
                    continue
                if not self._reviewed_row_applies_to_panel(row):
                    continue
                if not self._reviewed_row_runtime_enabled(
                    row, data=data, kind="drug"
                ):
                    continue
                variant_key = self._variant_key(
                    row.get("gene"), row.get("c_hgvs"), row.get("p_hgvs")
                )
                drug_type = self._norm_text(row.get("type")) or "benefit"
                clean_row = {
                    "gene": self._norm_text(row.get("gene")).upper(),
                    "c_hgvs": self._norm_text(row.get("c_hgvs")),
                    "p_hgvs": self._norm_text(row.get("p_hgvs")),
                    "drug_type": drug_type,
                    "drug_type_cn": "慎用药物" if drug_type == "caution" else "潜在获益药物",
                    "header": self._norm_text(row.get("header")),
                    "drug_name": self._norm_text(row.get("drug_name")),
                    "relation": self._norm_text(row.get("relation")),
                    "clinical": self._norm_text(row.get("clinical")),
                    "applicability": self._norm_text(
                        row.get("applicability")
                        or row.get("applies_to")
                        or row.get("variant_applicability")
                    ),
                }
                if variant_key:
                    group_key = (variant_key, drug_type)
                    if (
                        replace_variant_drug_sections
                        and group_key not in replaced_drug_groups
                    ):
                        self._reviewed_drug_section_overrides[group_key] = []
                        replaced_drug_groups.add(group_key)
                    self._reviewed_drug_section_overrides.setdefault(
                        group_key, []
                    ).append(clean_row)
                else:
                    # gene-level drug override (gene only, no c_hgvs): applies to
                    # any variant of the gene (e.g. lung-curated drug relation).
                    gene_key = self._hgvs_key(row.get("gene"))
                    if gene_key:
                        self._gene_level_drug_overrides.setdefault(
                            (gene_key, drug_type), []
                        ).append(clean_row)

            # reviewed override 补充的参考文献全文（如 DNMT3A/FLT3 策展引用），
            # 供 build_reference_lookup 给这些被引 PMID 补上标题。
            for ref in data.get("extra_references") or []:
                ref_text = self._norm_text(ref)
                if ref_text and ref_text not in self._extra_references:
                    self._extra_references.append(ref_text)

    def _reviewed_row_applies_to_panel(self, row: Dict[str, Any]) -> bool:
        """Return whether a reviewed overlay row belongs to this request panel.

        Overlay files may be shared by multiple panel packages.  Unscoped rows
        retain the legacy shared behavior, while an explicit ``panels`` (or
        singular/alias form) prevents a panel-specific exact rule from leaking
        into another panel that happens to reuse the same YAML file.
        """
        panel_id = self._norm_text(
            self.config.get("panel_id")
            or (self.config.get("gene_knowledge_db") or {}).get("panel_id")
        )
        if not panel_id:
            # Keep direct/legacy provider construction backward compatible.
            return True

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
            self._norm_text(value).casefold()
            for value in raw_panels
            if self._norm_text(value)
        }
        return panel_id.casefold() in allowed

    @staticmethod
    def _reviewed_row_runtime_enabled(
        row: Dict[str, Any],
        *,
        data: Optional[Dict[str, Any]] = None,
        kind: str = "gene",
    ) -> bool:
        """Fail closed for entries awaiting secondary medical review.

        Legacy overlay rows without explicit governance fields remain compatible.
        Once a row participates in the structured review workflow, however, it
        must explicitly be runtime-eligible and no longer carry a pending/rejected
        review status before it may override the production base knowledge.
        """
        if data and isinstance(data.get("governance"), dict):
            governance = effective_governance(data, row, kind)
            return bool(governance["runtime_eligible"])
        if row.get("runtime_eligible") is False:
            return False
        status = str(row.get("review_status") or "").strip().lower()
        return status not in {
            "needs_review",
            "pending_review",
            "pending_report_group_review",
            "rejected",
        }

    def _hgvs_key(self, value: Any) -> str:
        return re.sub(r"\s+", "", self._norm_text(value)).upper()

    def _configure_gene_symbol_aliases(self, raw: Any) -> None:
        """Normalize a panel-owned ``alias -> current symbol`` mapping.

        Chained aliases are flattened.  Cycles fail closed because a cyclic
        identity contract would make report deduplication order-dependent.
        """
        if raw in (None, ""):
            return
        if not isinstance(raw, Mapping):
            raise ValueError("gene_symbol_aliases must be a mapping")

        declared: Dict[str, str] = {}
        for raw_alias, raw_canonical in raw.items():
            alias = self._hgvs_key(raw_alias)
            canonical = self._hgvs_key(raw_canonical)
            if not alias or not canonical or alias == canonical:
                continue
            declared[alias] = canonical

        flattened: Dict[str, str] = {}
        for alias, target in declared.items():
            seen = {alias}
            canonical = target
            while canonical in declared:
                if canonical in seen:
                    raise ValueError(
                        f"cyclic gene_symbol_aliases contract at {alias}"
                    )
                seen.add(canonical)
                canonical = declared[canonical]
            flattened[alias] = canonical

        aliases_by_canonical: Dict[str, List[str]] = {}
        for alias, canonical in flattened.items():
            aliases_by_canonical.setdefault(canonical, []).append(alias)
        self._gene_symbol_aliases = flattened
        self._gene_aliases_by_canonical = {
            canonical: tuple(sorted(aliases))
            for canonical, aliases in aliases_by_canonical.items()
        }

    def _canonical_gene_key(self, value: Any) -> str:
        gene_key = self._hgvs_key(value)
        return self._gene_symbol_aliases.get(gene_key, gene_key)

    def _gene_lookup_keys(self, value: Any) -> tuple[str, ...]:
        """Return raw, canonical, then sibling-alias keys without duplicates."""
        raw_key = self._hgvs_key(value)
        if not raw_key:
            return ()
        canonical = self._canonical_gene_key(raw_key)
        ordered = [raw_key, canonical]
        ordered.extend(self._gene_aliases_by_canonical.get(canonical, ()))
        return tuple(dict.fromkeys(key for key in ordered if key))

    def _first_gene_value(self, values: Mapping[str, Any], gene: Any) -> Any:
        for gene_key in self._gene_lookup_keys(gene):
            if gene_key in values:
                return values[gene_key]
        return None

    def _merged_gene_mapping(
        self, values: Mapping[str, Dict[str, str]], gene: Any
    ) -> Dict[str, str]:
        """Merge partial alias rows while keeping the raw input key dominant."""
        merged: Dict[str, str] = {}
        # Apply sibling aliases first, then canonical/raw rows.  This lets a
        # canonical NSD2 fixed-domain row coexist with the governed WHSC1
        # intro/analysis instead of the partial canonical row masking it.
        for gene_key in reversed(self._gene_lookup_keys(gene)):
            candidate = values.get(gene_key)
            if candidate:
                merged.update(candidate)
        return merged

    def _variant_lookup_keys(
        self, gene: Any, c_hgvs: Any, p_hgvs: Any = ""
    ) -> tuple[str, ...]:
        return tuple(
            key
            for gene_key in self._gene_lookup_keys(gene)
            if (key := self._variant_key(gene_key, c_hgvs, p_hgvs))
        )

    def _variant_key(self, gene: Any, c_hgvs: Any, p_hgvs: Any = "") -> str:
        gene_key = self._hgvs_key(gene)
        c_key = self._hgvs_key(c_hgvs)
        p_key = self._hgvs_key(p_hgvs)
        if not gene_key or not c_key:
            return ""
        return f"{gene_key}|{c_key}|{p_key}"

    def _variant_key_from_row(self, row: Dict[str, Any]) -> str:
        return self._variant_key(
            row.get("gene"), row.get("cHGVS") or row.get("c_hgvs"), row.get("pHGVS") or row.get("p_hgvs")
        )

    def variant_identity_key(self, row: Dict[str, Any]) -> str:
        """Return the canonical gene+cHGVS+pHGVS key used for Part 3 dedupe."""
        gene = self._canonical_gene_key(row.get("gene"))
        if not gene:
            return ""
        c_hgvs = self._hgvs_key(row.get("cHGVS") or row.get("c_hgvs"))
        p_hgvs = self._hgvs_key(row.get("pHGVS") or row.get("p_hgvs"))
        if c_hgvs:
            return f"{gene}|{c_hgvs}|{p_hgvs}"
        event = self._hgvs_key(
            row.get("event")
            or row.get("mutation_type")
            or row.get("variant_type")
            or row.get("locus")
        )
        return f"{gene}|{c_hgvs or '<NO_C>'}|{p_hgvs}|{event}"

    def _load_gene_transcript_db(self, path: Path, config: Dict) -> None:
        """加载基因-转录本-染色体信息"""
        import logging
        _log = logging.getLogger("reportgen.knowledge")
        try:
            columns = config.get("columns", {})
            engine = "openpyxl" if str(path).endswith(".xlsx") else "xlrd"

            self._gene_transcript_df = pd.read_excel(str(path), engine=engine)
            self._build_gene_transcript_cache(columns)
        except Exception as e:
            _log.warning("基因转录本数据库加载失败: %s (path=%s)", e, path)

    def _norm_text(self, value: Any) -> str:
        """规范化文本值（委托统一实现）"""
        from reportgen.utils.text_utils import norm_text
        return norm_text(value)

    def _build_gene_analysis_cache(self, columns: Dict) -> None:
        """构建基因分析缓存"""
        if self._gene_analysis_df is None:
            return

        gene_col = columns.get("gene_name", "基因名称")
        intro_col = columns.get("gene_intro", "基因简介")
        analysis_col = columns.get("mutation_analysis", "基因变异解析")

        df = self._gene_analysis_df

        # 检查列是否存在
        if gene_col not in df.columns:
            return

        for _, row in df.iterrows():
            gene = self._norm_text(row.get(gene_col))
            if not gene:
                continue

            gene_upper = gene.upper()

            reviewed = self._extract_reviewed_analysis_fields(row, df.columns)

            # 缓存基因简介。部分处理后的知识库会把稳定的蛋白结构域摘要
            # 拼到简介末尾；将其拆到独立缓存，避免后续 overlay 整段覆盖。
            intro = self._norm_text(row.get(intro_col))
            if intro and gene_upper not in self._gene_intro_cache:
                intro_body, intro_domain_text = self._split_intro_domain_tail(
                    gene_upper, intro
                )
                self._gene_intro_cache[gene_upper] = intro_body or intro

                fixed_domain_text = self._merge_fixed_domain_texts(
                    reviewed.get("domain_text", ""),
                    intro_domain_text,
                )
                # The workbook's structured reviewed column is authoritative
                # when a legacy intro tail cannot be safely reduced to the same
                # single protein statement.  This catches historical row/column
                # drift such as a SMAD4 intro carrying ATM's 3056-aa sentence,
                # while still allowing genuinely complementary KRAS domains to
                # merge into one 189-aa statement.
                if (
                    reviewed.get("domain_text")
                    and len(
                        re.findall(
                            r"编码的蛋白全长", fixed_domain_text
                        )
                    )
                    > 1
                ):
                    fixed_domain_text = self._merge_fixed_domain_texts(
                        reviewed["domain_text"]
                    )
                if fixed_domain_text:
                    self._gene_fixed_domain_cache[gene_upper] = fixed_domain_text

            # 缓存基因变异解析
            analysis = self._norm_text(row.get(analysis_col))
            if analysis and gene_upper not in self._gene_analysis_cache:
                self._gene_analysis_cache[gene_upper] = analysis

            if reviewed and gene_upper not in self._reviewed_gene_analysis_cache:
                self._reviewed_gene_analysis_cache[gene_upper] = reviewed

    def _extract_reviewed_analysis_fields(self, row, columns) -> Dict[str, str]:
        """Extract reviewed report-generation columns from the gene KB.

        The public workbook keeps both generic analysis columns and report-review
        columns. The latter are not named semantically after export (often
        ``Unnamed: 4`` ...), but the first row documents their purpose:
        protein/domain text, expert consequence text, cancer-specific evidence,
        and conclusion/fallback wording.
        """

        def by_name(name: str) -> str:
            return self._norm_text(row.get(name)) if name in columns else ""

        # Prefer explicit names if a future curated workbook adds them; fall
        # back to the current exported column positions.
        fields = {
            "domain_text": by_name("泛癌") or by_name("Unnamed: 4"),
            "expert_text": by_name("需自动化识别(Ⅱ类出具，Ⅲ类 本列不出具)") or by_name("Unnamed: 5"),
            "cancer_text": by_name("肠癌{运营系统调取}") or by_name("Unnamed: 6"),
            "conclusion_text": by_name("需自动化识别") or by_name("Unnamed: 7"),
        }
        return {k: v for k, v in fields.items() if v and v.lower() != "nan"}

    def _split_intro_domain_tail(self, gene: str, intro: str) -> tuple[str, str]:
        lines = [line.strip() for line in str(intro).splitlines() if line.strip()]
        kept: List[str] = []
        fixed: List[str] = []
        for line in lines:
            # Do not require a gene-name prefix: ERBB2's only fixed statement
            # starts with the generic “基因编码…”.
            if "编码的蛋白全长" in line:
                # A few legacy rows use the context-dependent generic subject
                # “基因编码…”.  Once the sentence is moved into an independent
                # fixed-domain block that subject becomes ambiguous, so restore
                # the owning gene name without changing the medical statement.
                if line.startswith("基因编码"):
                    line = f"{gene}{line}"
                fixed.append(line)
                continue
            kept.append(line)
        return "\n".join(kept), "\n".join(fixed)

    def _strip_intro_domain_tail(self, gene: str, intro: str) -> str:
        """Backward-compatible wrapper used by legacy callers/tests."""
        body, _ = self._split_intro_domain_tail(gene, intro)
        return body or intro

    @staticmethod
    def _extract_fixed_domain_sentence(gene: str, *values: str) -> str:
        """Extract only a variant-independent protein/domain sentence.

        Reviewed legacy rows may combine a stable ``GENE基因编码的蛋白全长…``
        sentence with ``该样本检出…`` consequence prose.  Promoting the entire
        paragraph would incorrectly generalise a precise variant interpretation;
        this deliberately narrow extractor promotes only the fixed first sentence.
        """

        gene_key = str(gene or "").strip().upper()
        if not gene_key:
            return ""
        subject = rf"(?:(?:{re.escape(gene_key)})?基因编码的蛋白全长)"
        pattern = re.compile(
            rf"({subject}(?:为)?\s*\d+\s*(?:个|位)?氨基酸[^。\n]*(?:。|$))",
            flags=re.IGNORECASE,
        )
        for value in values:
            match = pattern.search(str(value or ""))
            if not match:
                continue
            sentence = match.group(1).strip()
            if sentence.startswith("基因编码"):
                sentence = f"{gene_key}{sentence}"
            return sentence.rstrip("。.") + "。"
        return ""

    @staticmethod
    def _merge_fixed_domain_texts(*values: str) -> str:
        """Merge complementary stable domain statements without repetition."""
        statements: List[str] = []
        seen: set[str] = set()
        for value in values:
            for line in str(value or "").splitlines():
                text = line.strip()
                key = re.sub(r"[\s，,。.;；]", "", text).casefold()
                if not text or key in seen:
                    continue
                seen.add(key)
                statements.append(text.rstrip("。."))

        if not statements:
            return ""

        pattern = re.compile(
            r"^(.*?编码的蛋白全长(?:为)?\s*\d+\s*(?:个|位)?氨基酸)"
            r"[，,]?\s*主要包含(.+)$"
        )
        parsed = [pattern.match(item) for item in statements]
        if all(parsed):
            prefixes = [
                re.sub(
                    r"(\d+)(?:个|位)氨基酸",
                    r"\1氨基酸",
                    re.sub(
                        r"蛋白全长为?",
                        "蛋白全长",
                        re.sub(r"\s+", "", match.group(1)),
                    ),
                ).casefold()
                for match in parsed
                if match is not None
            ]
            if len(set(prefixes)) == 1:
                tails: List[str] = []
                tail_seen: set[str] = set()
                for match in parsed:
                    assert match is not None
                    # The accumulator may already contain a canonical sentence
                    # joined with Chinese semicolons.  Split it back into
                    # components before merging so repeated overlay rows do not
                    # make the operation order-dependent (A+B)+A -> A+B+A.
                    for raw_tail in re.split(r"[；;]", match.group(2)):
                        tail = raw_tail.strip().rstrip("。.")
                        tail_key = re.sub(
                            r"[\s，,。.;；]", "", tail
                        ).casefold()
                        if tail and tail_key not in tail_seen:
                            tail_seen.add(tail_key)
                            tails.append(tail)
                return f"{parsed[0].group(1)}，主要包含{'；'.join(tails)}。"

        return "\n".join(f"{item}。" for item in statements)

    @staticmethod
    def _compose_fixed_domain_analysis(
        fixed_domain_text: str, mutation_analysis: str
    ) -> str:
        """Make the fixed structural statement survive replace-style overlays."""
        fixed = str(fixed_domain_text or "").strip()
        analysis = str(mutation_analysis or "").strip()
        if not fixed:
            return analysis

        # Replace any older fixed-domain sentence with the canonical merged
        # statement. Variant-specific domain/consequence sentences are kept.
        cleaned = re.sub(
            r"[^。\n]*编码的蛋白全长[^。\n]*(?:。|$)",
            "",
            analysis,
        )
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return f"{fixed}\n{cleaned}" if cleaned else fixed

    def _protein_position(self, p_hgvs: str) -> Optional[int]:
        match = re.search(r"p\.[A-Za-z*]{1,3}(\d+)", str(p_hgvs or ""))
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _domain_for_position(self, domain_text: str, position: Optional[int]) -> str:
        if not position:
            return ""
        pattern = re.compile(
            r"([\u4e00-\u9fffA-Za-z0-9/（）()_\-\s]+?结构域)"
            r"[（(](?:第)?(\d+)[\-－~～](\d+)位氨基酸[)）]"
        )
        for name, start, end in pattern.findall(str(domain_text or "")):
            try:
                if int(start) <= position <= int(end):
                    return name.strip(" ，、。；：")
            except ValueError:
                continue
        return ""

    def _is_splice_variant(self, c_hgvs: str, p_hgvs: str, mutation_type: Optional[str]) -> bool:
        mt = str(mutation_type or "")
        if "Splice" in mt or "剪接" in mt:
            return True
        return bool(re.search(r"c\.\d+[+-]\d+", str(c_hgvs or ""))) and str(p_hgvs or "") in {"", "--", "*"}

    def _is_truncating_variant(self, p_hgvs: str, mutation_type: Optional[str]) -> bool:
        mt = str(mutation_type or "")
        if any(key in mt for key in ("Nonsense", "Frameshift", "Stop_gain", "Stop-loss", "无义", "移码")):
            return True
        p = str(p_hgvs or "")
        return "*" in p or "fs" in p

    def _reviewed_variant_consequence(
        self,
        *,
        c_hgvs: str,
        p_hgvs: str,
        mutation_type: Optional[str],
        domain_text: str,
        expert_text: str,
    ) -> str:
        if self._is_splice_variant(c_hgvs, p_hgvs, mutation_type):
            return (
                f"该样本检出的{c_hgvs}突变位于内含子与外显子交界处，"
                "可能导致mRNA剪接异常，进而导致蛋白功能缺失。"
            )

        if p_hgvs and p_hgvs not in {"--", "*"}:
            if self._is_truncating_variant(p_hgvs, mutation_type):
                return (
                    f"该样本检出的{p_hgvs}突变导致蛋白翻译提前终止，"
                    "产生截短的蛋白，可能导致蛋白功能缺失。"
                )

            position = self._protein_position(p_hgvs)
            domain = self._domain_for_position(domain_text, position)
            if "已知激活突变" in expert_text:
                location = "位于上述结构域之内" if domain else ""
                return f"该样本检出的{p_hgvs}突变{location}，为已知激活突变，对蛋白功能有重要影响。"
            if "蛋白功能缺失" in expert_text:
                if domain:
                    return f"该样本检出的{p_hgvs}突变位于{domain}，可能导致蛋白功能缺失。"
                return f"该样本检出的{p_hgvs}突变可能导致蛋白功能缺失。"
            if domain:
                return f"该样本检出的{p_hgvs}突变位于{domain}，可能会对蛋白功能产生影响。"
            return f"该样本检出的{p_hgvs}突变对蛋白功能的影响有待结合数据库和文献进一步评估。"

        return ""

    def _clean_reviewed_conclusion(self, text: str) -> str:
        text = self._norm_text(text)
        if not text:
            return ""
        # Current workbook stores several alternative fallback endings in one
        # cell. Keep the reviewed leading conclusion when present.
        match = re.search(r"(因此，该样本检出的突变[^。]*。)", text)
        return match.group(1) if match else ""

    def _build_reviewed_mutation_analysis(
        self,
        *,
        gene: str,
        c_hgvs: str,
        p_hgvs: str,
        mutation_type: Optional[str],
        has_drug: bool,
    ) -> str:
        reviewed = self._first_gene_value(
            self._reviewed_gene_analysis_cache, gene
        ) or {}
        if not reviewed:
            return self.get_gene_analysis(gene)

        domain_text = reviewed.get("domain_text", "")
        expert_text = reviewed.get("expert_text", "")
        cancer_text = reviewed.get("cancer_text", "")

        paragraphs: List[str] = []
        if domain_text:
            consequence = self._reviewed_variant_consequence(
                c_hgvs=c_hgvs,
                p_hgvs=p_hgvs,
                mutation_type=mutation_type,
                domain_text=domain_text,
                expert_text=expert_text,
            )
            first = domain_text.rstrip("。")
            if consequence:
                first = f"{first}。{consequence}"
            else:
                first = f"{first}。"
            paragraphs.append(first)

        if cancer_text:
            conclusion = self._clean_reviewed_conclusion(
                reviewed.get("conclusion_text", "")
            )
            if not conclusion:
                mentions_drug = bool(
                    re.search(r"用药|药物|耐药|获益|抑制剂", cancer_text)
                )
                suffix = "及用药" if has_drug and mentions_drug else ""
                conclusion = f"因此，该样本检出的突变可能与疾病的发生发展{suffix}相关。"
            paragraphs.append(f"{cancer_text.rstrip('。')}。{conclusion}")

        if paragraphs:
            return "\n".join(paragraphs)
        return self.get_gene_analysis(gene)

    def _build_drug_analysis_cache(self, columns: Dict) -> None:
        """构建药物分析缓存"""
        if self._drug_analysis_df is None:
            return

        df = self._drug_analysis_df

        # 查找相关列（列名可能带有Unnamed前缀）
        # 用药提示解析表结构:
        # Unnamed: 0=基因名称, Unnamed: 1=变异等级, Unnamed: 2=c_point, Unnamed: 3=p_point,
        # Unnamed: 4=扩增/缺失/融合/胚系/未见突变
        # 潜在获益靶向/免疫药物解析=药物, Unnamed: 6=基因变异与药物关联分析, Unnamed: 7=..., Unnamed: 8=药物疗效临床解析
        # 潜在负相关靶向/免疫药物解析=药物, Unnamed: 10=基因变异与药物关联分析,
        # Unnamed: 11=..., Unnamed: 12=药物疗效临床解析

        gene_col = None
        level_col = None
        c_point_col = None
        p_point_col = None
        benefit_drug_col = None
        benefit_relation_cols = []
        benefit_clinical_col = None
        negative_drug_col = None
        negative_relation_cols = []
        negative_clinical_col = None

        # 解析列位置
        cols = list(df.columns)
        for i, col in enumerate(cols):
            col_str = str(col)
            if "基因名称" in col_str or col == "Unnamed: 0":
                gene_col = col
            elif col == "Unnamed: 1":
                level_col = col
            elif col == "Unnamed: 2":
                c_point_col = col
            elif col == "Unnamed: 3":
                p_point_col = col
            elif "潜在获益靶向/免疫药物解析" in col_str:
                benefit_drug_col = col
                # 后续列：当前工作簿里“基因变异与药物关联分析”可能拆成
                # 变异特异说明 + 药物机制说明两列，临床解析在第三列之后。
                if i + 1 < len(cols):
                    benefit_relation_cols.append(cols[i + 1])
                if i + 2 < len(cols):
                    benefit_relation_cols.append(cols[i + 2])
                if i + 3 < len(cols):
                    benefit_clinical_col = cols[i + 3]
            elif "潜在负相关靶向/免疫药物解析" in col_str:
                negative_drug_col = col
                if i + 1 < len(cols):
                    negative_relation_cols.append(cols[i + 1])
                if i + 2 < len(cols):
                    negative_relation_cols.append(cols[i + 2])
                if i + 3 < len(cols):
                    negative_clinical_col = cols[i + 3]

        # 尝试从第一行获取列名（如果第一行是标题）
        if gene_col is None and len(df) > 0:
            first_row = df.iloc[0]
            for col in df.columns:
                val = str(first_row.get(col, "")).strip()
                if val == "基因名称":
                    gene_col = col
                elif val == "变异等级":
                    level_col = col
                elif val == "c_point":
                    c_point_col = col
                elif val == "p_point":
                    p_point_col = col

        if gene_col is None:
            return

        current_gene = None
        current_level = None
        current_c_point = None
        current_p_point = None

        for _, row in df.iterrows():
            # 获取基因信息（可能在多行中只有第一行有基因名）
            gene = self._norm_text(row.get(gene_col))
            if gene and gene != "基因名称":
                current_gene = gene.upper()
                current_level = self._norm_text(row.get(level_col)) if level_col else ""
                current_c_point = (
                    self._norm_text(row.get(c_point_col)) if c_point_col else ""
                )
                current_p_point = (
                    self._norm_text(row.get(p_point_col)) if p_point_col else ""
                )

            if not current_gene:
                continue

            # 获取获益药物信息
            benefit_drug = (
                self._norm_text(row.get(benefit_drug_col)) if benefit_drug_col else ""
            )
            benefit_relation = "\n".join(
                text
                for text in (
                    self._norm_text(row.get(col)) for col in benefit_relation_cols
                )
                if text
            )
            benefit_clinical = (
                self._norm_text(row.get(benefit_clinical_col))
                if benefit_clinical_col
                else ""
            )

            # 获取负相关药物信息
            negative_drug = (
                self._norm_text(row.get(negative_drug_col)) if negative_drug_col else ""
            )
            negative_relation = "\n".join(
                text
                for text in (
                    self._norm_text(row.get(col)) for col in negative_relation_cols
                )
                if text
            )
            negative_clinical = (
                self._norm_text(row.get(negative_clinical_col))
                if negative_clinical_col
                else ""
            )

            # 初始化缓存
            if current_gene not in self._drug_analysis_cache:
                self._drug_analysis_cache[current_gene] = {}
            if current_gene not in self._drug_full_cache:
                self._drug_full_cache[current_gene] = []

            # 存储获益药物
            if benefit_drug:
                self._drug_analysis_cache[current_gene][benefit_drug] = benefit_clinical
                self._drug_full_cache[current_gene].append(
                    {
                        "type": "benefit",
                        "drug": benefit_drug,
                        "level": current_level,
                        "c_point": current_c_point,
                        "p_point": current_p_point,
                        "relation": benefit_relation,
                        "clinical": benefit_clinical,
                    }
                )

            # 存储负相关药物
            if negative_drug:
                self._drug_analysis_cache[current_gene][
                    f"慎用:{negative_drug}"
                ] = negative_clinical
                self._drug_full_cache[current_gene].append(
                    {
                        "type": "caution",
                        "drug": negative_drug,
                        "level": current_level,
                        "c_point": current_c_point,
                        "p_point": current_p_point,
                        "relation": negative_relation,
                        "clinical": negative_clinical,
                    }
                )

    def _build_references_cache(self, columns: Dict) -> None:
        """构建参考文献缓存"""
        if self._references_df is None:
            return

        df = self._references_df

        # 参考文献表结构: 基因名称, 变异等级, c_point, p_point, 扩增/缺失/融合/胚系/未见突变, 参考文献
        gene_col = None
        ref_col = None

        for col in df.columns:
            col_str = str(col)
            if "基因名称" in col_str:
                gene_col = col
            elif "参考文献" in col_str:
                ref_col = col

        if gene_col is None or ref_col is None:
            return

        current_gene = None

        for _, row in df.iterrows():
            gene = self._norm_text(row.get(gene_col))
            if gene:
                current_gene = gene.upper()

            if not current_gene:
                continue

            ref = self._norm_text(row.get(ref_col))
            if ref:
                if current_gene not in self._references_cache:
                    self._references_cache[current_gene] = []
                # 避免重复
                if ref not in self._references_cache[current_gene]:
                    self._references_cache[current_gene].append(ref)

    def _build_gene_transcript_cache(self, columns: Dict) -> None:
        """构建基因-转录本缓存"""
        if self._gene_transcript_df is None:
            return

        gene_col = columns.get("gene_name", "Genename")
        transcript_col = columns.get("transcript", "Transcriptid")
        chr_col = columns.get("chromosome", "Chr")

        df = self._gene_transcript_df

        for _, row in df.iterrows():
            gene = self._norm_text(row.get(gene_col))
            if not gene:
                continue

            gene_upper = gene.upper()
            if gene_upper in self._gene_transcript_cache:
                continue  # 只保留第一个（避免重复）

            self._gene_transcript_cache[gene_upper] = {
                "name": gene,
                "transcript": self._norm_text(row.get(transcript_col)),
                "chromosome": self._norm_text(row.get(chr_col)).replace("chr", ""),
            }

    def get_gene_intro(self, gene: str) -> str:
        """
        获取基因简介

        Args:
            gene: 基因名称

        Returns:
            基因简介文本，未找到返回空字符串
        """
        if not self._loaded:
            self.load()
        intro = self._first_gene_value(self._gene_intro_cache, gene) or ""
        if not intro:
            # Fallback：未收录基因生成通用描述
            intro = f"{gene}基因与肿瘤的发生发展可能相关，具体功能及临床意义请参考相关文献。"
        return intro

    def get_gene_analysis(self, gene: str) -> str:
        """
        获取基因变异解析

        Args:
            gene: 基因名称

        Returns:
            基因变异解析文本，未找到返回空字符串
        """
        if not self._loaded:
            self.load()
        return self._first_gene_value(self._gene_analysis_cache, gene) or ""

    def get_drug_analysis(self, gene: str, drug: Optional[str] = None) -> str:
        """
        获取药物疗效临床解析

        Args:
            gene: 基因名称
            drug: 药物名称（可选，不指定则返回该基因相关的所有药物分析）

        Returns:
            药物疗效临床解析文本
        """
        if not self._loaded:
            self.load()

        gene_drugs = self._first_gene_value(self._drug_analysis_cache, gene) or {}
        if not gene_drugs:
            return ""

        if drug:
            return gene_drugs.get(drug, "")

        # 返回所有药物分析（合并）
        return "\n\n".join(gene_drugs.values())

    def get_drug_full_info(self, gene: str) -> List[Dict[str, str]]:
        """
        获取基因的完整药物信息列表

        Args:
            gene: 基因名称

        Returns:
            药物信息列表，每个元素包含 type, drug, level, c_point, p_point, relation, clinical
        """
        if not self._loaded:
            self.load()
        return self._first_gene_value(self._drug_full_cache, gene) or []

    def has_reviewed_drug_analysis_contract(
        self, variant: Dict[str, Any]
    ) -> bool:
        """Whether an exact/gene-level reviewed Part-3 drug rule owns a row.

        The legacy workbook contains broad narratives that have not all been
        migrated to exact variant contracts.  Cross-section blocking is safe
        only for reviewed overlay entries whose scope is explicit; otherwise a
        synthetic or legacy Part-2 row can be falsely treated as a missing
        reviewed Part-3 interpretation.
        """
        if not self._loaded:
            self.load()
        variant_keys = self._variant_lookup_keys(
            variant.get("gene"),
            variant.get("cHGVS") or variant.get("c_hgvs"),
            variant.get("pHGVS") or variant.get("p_hgvs"),
        )
        gene_keys = self._gene_lookup_keys(variant.get("gene"))
        for direction in ("benefit", "caution"):
            if any(
                (variant_key, direction)
                in self._reviewed_drug_section_overrides
                for variant_key in variant_keys
            ):
                return True
            if any(
                (gene_key, direction) in self._gene_level_drug_overrides
                for gene_key in gene_keys
            ):
                return True
        return False

    def list_drug_narrative_entries(self) -> List[Dict[str, str]]:
        """List base Part 3 drug-narrative rows with their owning gene."""
        if not self._loaded:
            self.load()
        return [
            {"gene": gene, **dict(row)}
            for gene, rows in self._drug_full_cache.items()
            for row in rows
        ]

    def get_references(self, gene: str) -> List[str]:
        """
        获取基因的参考文献列表

        Args:
            gene: 基因名称

        Returns:
            参考文献列表
        """
        if not self._loaded:
            self.load()
        return self._first_gene_value(self._references_cache, gene) or []

    def build_reference_lookup(self) -> Dict[str, Any]:
        """构建全局"引用标识 → 参考文献全文"映射，供按正文引用重建参考文献。

        返回 ``{"pmid": {号: 全文}, "trial": {NCT/CTR/ChiCTR号: 全文},
        "other": [其它(如会议摘要)全文, ...]}``。号已去前导零并标准化。
        """
        if not self._loaded:
            self.load()
        pmid: Dict[str, str] = {}
        trial: Dict[str, str] = {}
        other: List[str] = []
        seen_other = set()
        ref_sources = list(self._references_cache.values())
        if self._extra_references:
            ref_sources.append(self._extra_references)
        for refs in ref_sources:
            for raw in refs:
                ref = str(raw or "").strip()
                if not ref:
                    continue
                m = re.match(r"PMID\s*[:：]?\s*0*(\d+)", ref, re.I)
                if m:
                    pmid.setdefault(str(int(m.group(1))), ref)
                    continue
                m2 = re.match(r"((?:NCT|CTR|ChiCTR)\d+)", ref, re.I)
                if m2:
                    trial.setdefault(m2.group(1).upper(), ref)
                    continue
                if ref not in seen_other:
                    seen_other.add(ref)
                    other.append(ref)
        # The structured registry fills title gaps but never overrides a
        # panel/workbook citation already bound to the same identifier.
        for identifier, citation in self._reference_registry["pmid"].items():
            pmid.setdefault(identifier, citation)
        for identifier, citation in self._reference_registry["trial"].items():
            trial.setdefault(identifier, citation)
        return {"pmid": pmid, "trial": trial, "other": other}

    def get_gene_transcript_info(self, gene: str) -> Dict[str, str]:
        """
        获取基因的转录本和染色体信息

        Args:
            gene: 基因名称

        Returns:
            包含 name, transcript, chromosome 的字典
        """
        if not self._loaded:
            self.load()
        return self._first_gene_value(self._gene_transcript_cache, gene) or {}

    def generate_mutation_description(
        self,
        gene: str,
        c_hgvs: str,
        p_hgvs: str,
        frequency: float,
        mutation_type: Optional[str] = None,
    ) -> str:
        """
        生成基因变异说明

        Args:
            gene: 基因名称
            c_hgvs: cDNA变异描述
            p_hgvs: 蛋白变异描述
            frequency: 突变频率
            mutation_type: 突变类型

        Returns:
            基因变异说明文本
        """
        # 不精确的突变类型（如"点突变"）设为 None，让生成器自动从 HGVS 推断
        _precise_types = {
            "Missense", "Nonsense", "Frameshift", "Splice", "Inframe",
            "CDS-indel", "Stop_gain", "Stop_loss",
            "错义突变", "无义突变", "移码突变", "剪接突变", "框内突变",
            "Splice-5", "Splice-3",
        }
        if mutation_type and mutation_type not in _precise_types:
            mutation_type = None  # 让生成器自动推断
        return self._mutation_desc_gen.generate(
            gene, c_hgvs, p_hgvs, frequency, mutation_type
        )

    def build_gene_knowledge_section(
        self,
        gene: str,
        c_hgvs: str,
        p_hgvs: str,
        frequency: float,
        mutation_type: Optional[str] = None,
        has_drug: bool = False,
        cancer_type: str = "结直肠癌",
    ) -> Dict[str, str]:
        """
        构建完整的基因诊疗知识章节

        Args:
            gene: 基因名称
            c_hgvs: cDNA变异描述
            p_hgvs: 蛋白变异描述
            frequency: 突变频率
            mutation_type: 突变类型
            has_drug: 是否有相关药物（用于确定标题颜色）
            cancer_type: 癌症类型

        Returns:
            包含 header, intro, mutation_desc, mutation_analysis 等字段的字典
        """
        if not self._loaded:
            self.load()

        # 构建标题
        p_display = p_hgvs if p_hgvs and p_hgvs != "--" else ""
        frequency_display = (
            str(int(frequency)) if float(frequency).is_integer() else f"{frequency:.2f}"
        )
        if p_display:
            header = f"{gene}：{c_hgvs}，{p_display}；{frequency_display}%"
        else:
            header = f"{gene}：{c_hgvs}；{frequency_display}%"

        # 标题颜色（有药物的用红色，否则用蓝色）
        header_color = "FF0000" if has_drug else "0000FF"

        # 获取基因简介
        intro = self.get_gene_intro(gene)

        # 生成变异说明
        mutation_desc = self.generate_mutation_description(
            gene, c_hgvs, p_hgvs, frequency, mutation_type
        )

        # 获取变异解析。优先使用终版报告口径的 reviewed 列组合；
        # 没有 reviewed 数据时回退到通用分析列。
        mutation_analysis = self._build_reviewed_mutation_analysis(
            gene=gene,
            c_hgvs=c_hgvs,
            p_hgvs=p_hgvs,
            mutation_type=mutation_type,
            has_drug=has_drug,
        )
        # gene-level overlay (panel-scoped, variant-agnostic): overrides the
        # base KB for ANY variant of this gene. Lets e.g. lung supply lung
        # wording without enumerating every variant.
        gene_override = self._merged_gene_mapping(
            self._gene_level_section_overrides, gene
        )
        intro = gene_override.get("intro") or intro
        mutation_analysis = gene_override.get("mutation_analysis") or mutation_analysis
        # variant-level overlay has the highest precedence.
        reviewed_override: Dict[str, str] = {}
        for variant_key in self._variant_lookup_keys(gene, c_hgvs, p_hgvs):
            reviewed_override = self._reviewed_gene_section_overrides.get(
                variant_key, {}
            )
            if reviewed_override:
                break
        intro = reviewed_override.get("intro") or intro
        mutation_analysis = (
            reviewed_override.get("mutation_analysis") or mutation_analysis
        )

        fixed_domain_text = self._merge_fixed_domain_texts(
            self._first_gene_value(self._gene_fixed_domain_cache, gene) or "",
            gene_override.get("fixed_domain_text", ""),
            reviewed_override.get("fixed_domain_text", ""),
        )
        mutation_analysis = self._compose_fixed_domain_analysis(
            fixed_domain_text, mutation_analysis
        )

        return {
            "gene": gene,
            "header": header,
            "header_color": header_color,
            "intro": intro,
            "mutation_desc": mutation_desc,
            "mutation_analysis": mutation_analysis,
            "fixed_domain_text": fixed_domain_text,
            "has_drug": has_drug,
        }

    def build_all_gene_knowledge_sections(
        self, variants: List[Dict[str, Any]], cancer_type: str = "结直肠癌"
    ) -> List[Dict[str, str]]:
        """
        为所有变异构建基因诊疗知识章节

        Args:
            variants: 变异列表，每个元素包含 gene, cHGVS, pHGVS, frequency 等字段
            cancer_type: 癌症类型

        Returns:
            基因诊疗知识章节列表
        """
        sections = []
        seen_variants = set()  # 避免重复（同一基因同一位点）

        for v in variants:
            gene = v.get("gene", "")
            c_hgvs = v.get("cHGVS", "")
            p_hgvs = v.get("pHGVS", "")

            # 去重
            variant_key = self.variant_identity_key(v)
            if variant_key in seen_variants:
                continue
            seen_variants.add(variant_key)

            # 解析频率
            freq_str = v.get("frequency", "0")
            try:
                frequency = float(freq_str.replace("%", "")) if freq_str else 0.0
            except (ValueError, TypeError):
                frequency = 0.0

            # 判断是否有药物
            benefit_drugs = v.get("benefit_drugs", "")
            caution_drugs = v.get("caution_drugs", "")
            has_drug = bool(v.get("has_therapy_association")) or (
                benefit_drugs and benefit_drugs != "--" and benefit_drugs != "无"
            ) or (caution_drugs and caution_drugs != "--" and caution_drugs != "无")

            section = self.build_gene_knowledge_section(
                gene=gene,
                c_hgvs=c_hgvs,
                p_hgvs=p_hgvs,
                frequency=frequency,
                mutation_type=v.get("mutation_type"),
                has_drug=has_drug,
                cancer_type=cancer_type,
            )
            section["c_hgvs"] = c_hgvs
            section["p_hgvs"] = p_hgvs
            section["source_variant_key"] = variant_key
            sections.append(section)

        return sections

    @staticmethod
    def build_gene_domain_coverage(
        sections: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Return a fail-closed fixed-domain coverage contract for Part 3.

        The contract is gene-level even when several variants of the same gene
        are rendered.  Missing content is intentionally explicit so report QA
        cannot silently pass a Part-3 section that omitted the fixed structural
        paragraph requested by the report group.
        """

        expected: set[str] = set()
        covered: set[str] = set()
        missing_variant_keys: List[str] = []
        duplicate_genes: set[str] = set()
        duplicate_variant_keys: List[str] = []
        for section in sections:
            gene = str(section.get("gene") or "").strip().upper()
            if not gene:
                continue
            expected.add(gene)
            fixed_domain_text = str(
                section.get("fixed_domain_text") or ""
            ).strip()
            variant_key = str(section.get("source_variant_key") or "").strip()
            if fixed_domain_text:
                covered.add(gene)
                if len(re.findall(r"编码的蛋白全长", fixed_domain_text)) > 1:
                    duplicate_genes.add(gene)
                    if (
                        variant_key
                        and variant_key not in duplicate_variant_keys
                    ):
                        duplicate_variant_keys.append(variant_key)
            else:
                if variant_key and variant_key not in missing_variant_keys:
                    missing_variant_keys.append(variant_key)

        missing = sorted(expected - covered)
        total = len(expected)
        return {
            "status": (
                "PASS" if not missing and not duplicate_genes else "FAIL"
            ),
            "expected_gene_count": total,
            "covered_gene_count": len(expected & covered),
            "coverage_percent": (
                round(100.0 * len(expected & covered) / total, 2)
                if total
                else 100.0
            ),
            "missing_genes": missing,
            "missing_variant_keys": missing_variant_keys,
            "duplicate_fixed_domain_genes": sorted(duplicate_genes),
            "duplicate_fixed_domain_variant_keys": duplicate_variant_keys,
        }

    def build_drug_analysis_sections(
        self,
        variants: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """
        构建用药提示解析章节

        Args:
            variants: 变异列表，每个元素包含 gene, cHGVS, pHGVS, benefit_drugs, caution_drugs 等字段

        Returns:
            用药提示解析章节列表，每个元素包含:
            - gene: 基因名称
            - drug_name: 药物名称
            - drug_type: 药物类型 (benefit/caution)
            - relation: 基因变异与药物关联分析
            - clinical: 药物疗效临床解析
        """
        if not self._loaded:
            self.load()

        import re

        def _extract_drug_keywords(drug_text: str) -> set:
            """从药物文本中提取核心关键词，用于模糊匹配。"""
            if not drug_text or drug_text in ("--", "无"):
                return set()
            # 去掉证据等级标记如 (C)/(A)/(B)/(D)
            cleaned = re.sub(r"[（(][A-Da-d][)）]", "", drug_text)
            # 按分隔符拆分
            parts = re.split(r"[、,\n；;]", cleaned)
            keywords = set()
            for p in parts:
                w = p.strip()
                if w and len(w) > 1:
                    keywords.add(w.lower())
                    # 英文药物名取第一个单词（如 AZD1775+奥拉帕利 → azd1775）
                    first_word = w.split("+")[0].split("（")[0].split("(")[0].strip()
                    if first_word and len(first_word) > 2:
                        keywords.add(first_word.lower())
            return keywords

        def _drug_matches(kb_drug_name: str, variant_drugs: str) -> bool:
            """模糊匹配：知识库药物名和变异表中的药物是否对应。"""
            if not kb_drug_name or not variant_drugs:
                return False
            kb_keywords = _extract_drug_keywords(kb_drug_name)
            variant_keywords = _extract_drug_keywords(variant_drugs)
            # 有交集即匹配
            return bool(kb_keywords & variant_keywords)

        def _split_drug_items(drug_text: str) -> list[str]:
            if not drug_text:
                return []
            return [
                item.strip()
                for item in re.split(r"[、\n；;]", str(drug_text))
                if item.strip()
            ]

        def _filter_drug_name(kb_drug_name: str, variant_drugs: str) -> str:
            """Keep only KB drug items that are present in the final drug table."""
            items = _split_drug_items(kb_drug_name)
            if not items:
                return kb_drug_name
            kept = [item for item in items if _drug_matches(item, variant_drugs)]
            return "、".join(kept) if kept else kb_drug_name

        def _item_keywords(drug_item: str) -> set[str]:
            keywords = set()
            for raw in _extract_drug_keywords(drug_item):
                for piece in re.split(r"[+＋/ ]", raw):
                    piece = piece.strip().lower()
                    if len(piece) > 1:
                        keywords.add(piece)
            return keywords

        def _filter_analysis_text(
            text: str,
            *,
            kb_drug_name: str,
            variant_drugs: str,
        ) -> str:
            """Drop sentences about KB-only drugs not shown in the final table."""
            if not text:
                return ""

            included_items = [
                item
                for item in _split_drug_items(kb_drug_name)
                if _drug_matches(item, variant_drugs)
            ]
            excluded_items = [
                item
                for item in _split_drug_items(kb_drug_name)
                if not _drug_matches(item, variant_drugs)
            ]
            if not excluded_items:
                return text

            included_keywords = set()
            for item in included_items:
                included_keywords.update(_item_keywords(item))
            excluded_keywords = set()
            for item in excluded_items:
                excluded_keywords.update(_item_keywords(item))

            if not excluded_keywords:
                return text

            segments = re.split(r"(?<=[。！？!?])", text)
            kept = []
            for segment in segments:
                low = segment.lower()
                has_excluded = any(k in low for k in excluded_keywords)
                has_included = any(k in low for k in included_keywords)
                if has_excluded and not has_included:
                    continue
                kept.append(segment)
            return "".join(kept).strip()

        def _aa_change(p_hgvs: str) -> tuple[str, Optional[int], str]:
            match = re.search(r"p\.([A-Za-z*]{1,3})(\d+)([A-Za-z*]{1,3})", str(p_hgvs or ""))
            if not match:
                return "", None, ""
            return match.group(1).upper(), int(match.group(2)), match.group(3).upper()

        def _p_point_matches(pattern: str, observed: str) -> bool:
            pattern = str(pattern or "").strip()
            observed = str(observed or "").strip()
            if not pattern:
                return True
            if observed and observed in pattern:
                return True

            from_aa, pos, to_aa = _aa_change(observed)
            if not pos:
                return False

            for item in re.split(r"[、,，]", pattern):
                item = item.strip()
                if not item:
                    continue
                wildcard = re.search(r"p\.([A-Za-z*]{1,3})(\d+)X", item)
                if not wildcard:
                    continue
                item_from = wildcard.group(1).upper()
                item_pos = int(wildcard.group(2))
                if item_from != from_aa or item_pos != pos:
                    continue
                excluded = set()
                excluded_match = re.search(r"除([^外]+)外", item)
                if excluded_match:
                    excluded = {
                        token.strip().upper()
                        for token in re.split(r"[、,，/]", excluded_match.group(1))
                        if token.strip()
                    }
                return to_aa not in excluded
            return False

        def _drug_info_matches_variant(drug_info: Dict[str, str], variant: Dict[str, Any]) -> bool:
            c_point = str(drug_info.get("c_point") or "").strip()
            p_point = str(drug_info.get("p_point") or "").strip()
            c_hgvs = str(variant.get("cHGVS") or "").strip()
            p_hgvs = str(variant.get("pHGVS") or "").strip()
            if c_point and c_hgvs and c_point != c_hgvs:
                return False
            if p_point and not _p_point_matches(p_point, p_hgvs):
                return False
            return True

        sections = []
        seen_drugs = set()

        def _lead_relation(relation_text: str, gene: str, c_hgvs: str, p_hgvs: str) -> str:
            """在“基因变异与药物关联分析”正文前拼接变异描述开头句。

            形如“该样本检出{gene}基因{c}，{p}{类型}突变。”，与终版报告一致；
            正文为空则不加，已含“该样本检出”开头则跳过以避免重复。
            """
            relation_text = relation_text or ""
            if not relation_text.strip():
                return relation_text
            if relation_text.lstrip().startswith("该样本检出"):
                return relation_text
            lead = self._mutation_desc_gen.build_variant_lead(gene, c_hgvs, p_hgvs)
            return f"{lead}{relation_text}" if lead else relation_text

        for v in variants:
            gene = v.get("gene", "").upper()
            benefit_drugs = v.get("benefit_drugs", "")
            caution_drugs = v.get("caution_drugs", "")

            drug_infos = self.get_drug_full_info(gene)

            # 如果没有 drug_infos 但有药物关联，直接为该基因生成所有解析
            if not drug_infos and (
                (benefit_drugs and benefit_drugs != "--")
                or (caution_drugs and caution_drugs != "--")
            ):
                continue

            # 匹配获益药物（模糊匹配）
            if benefit_drugs and benefit_drugs != "--":
                for drug_info in drug_infos:
                    if drug_info["type"] == "benefit":
                        if not _drug_info_matches_variant(drug_info, v):
                            continue
                        drug_name = drug_info["drug"]
                        if _drug_matches(drug_name, benefit_drugs):
                            filtered_drug_name = _filter_drug_name(
                                drug_name, benefit_drugs
                            )
                            key = f"{gene}:{filtered_drug_name}:benefit"
                            if key not in seen_drugs:
                                seen_drugs.add(key)
                                variant_info = f"{v.get('cHGVS', '')}，{v.get('pHGVS', '')}" if v.get('pHGVS') else v.get('cHGVS', '')
                                sections.append(
                                    {
                                        "gene": gene,
                                        "c_hgvs": v.get("cHGVS", ""),
                                        "p_hgvs": v.get("pHGVS", ""),
                                        "variant": variant_info,
                                        "drug_name": filtered_drug_name,
                                        "drug_type": "benefit",
                                        "drug_type_cn": "潜在获益药物",
                                        "relation": _lead_relation(
                                            _filter_analysis_text(
                                                drug_info.get("relation", ""),
                                                kb_drug_name=drug_name,
                                                variant_drugs=benefit_drugs,
                                            ),
                                            gene,
                                            v.get("cHGVS", ""),
                                            v.get("pHGVS", ""),
                                        ),
                                        "clinical": _filter_analysis_text(
                                            drug_info.get("clinical", ""),
                                            kb_drug_name=drug_name,
                                            variant_drugs=benefit_drugs,
                                        ),
                                    }
                                )

            # 匹配慎用药物（模糊匹配）
            if caution_drugs and caution_drugs != "--":
                for drug_info in drug_infos:
                    if drug_info["type"] == "caution":
                        if not _drug_info_matches_variant(drug_info, v):
                            continue
                        drug_name = drug_info["drug"]
                        if _drug_matches(drug_name, caution_drugs):
                            filtered_drug_name = _filter_drug_name(
                                drug_name, caution_drugs
                            )
                            key = f"{gene}:{filtered_drug_name}:caution"
                            if key not in seen_drugs:
                                seen_drugs.add(key)
                                variant_info = f"{v.get('cHGVS', '')}，{v.get('pHGVS', '')}" if v.get('pHGVS') else v.get('cHGVS', '')
                                sections.append(
                                    {
                                        "gene": gene,
                                        "c_hgvs": v.get("cHGVS", ""),
                                        "p_hgvs": v.get("pHGVS", ""),
                                        "variant": variant_info,
                                        "drug_name": filtered_drug_name,
                                        "drug_type": "caution",
                                        "drug_type_cn": "慎用药物",
                                        "relation": _lead_relation(
                                            _filter_analysis_text(
                                                drug_info.get("relation", ""),
                                                kb_drug_name=drug_name,
                                                variant_drugs=caution_drugs,
                                            ),
                                            gene,
                                            v.get("cHGVS", ""),
                                            v.get("pHGVS", ""),
                                        ),
                                        "clinical": _filter_analysis_text(
                                            drug_info.get("clinical", ""),
                                            kb_drug_name=drug_name,
                                            variant_drugs=caution_drugs,
                                        ),
                                    }
                                )

        reviewed_sections = self._apply_reviewed_drug_section_overrides(
            variants, sections
        )
        return self._coalesce_overlapping_drug_sections(reviewed_sections)

    @staticmethod
    def _split_drug_items(value: Any) -> List[str]:
        text = str(value or "").strip()
        if not text or text in {"-", "--", "—", "无", "未检出"}:
            return []
        return [
            item.strip()
            for item in re.split(r"[、\n；;]+", text)
            if item.strip()
        ]

    @staticmethod
    def _canonical_drug_item(value: Any) -> str:
        """Normalize one displayed drug/combination for cross-section QA."""
        text = str(value or "").strip()
        text = re.sub(r"[（(]\s*[A-Da-d]\s*[)）]", "", text)
        # Parenthetical English names are aliases of the adjacent Chinese drug,
        # not additional combination members.
        text = re.sub(r"[（(][^()（）\r\n]+[)）]", "", text)
        text = text.replace("＋", "+")
        components = [
            re.sub(r"[\s_\-]+", "", part).casefold()
            for part in text.split("+")
            if re.sub(r"[\s_\-]+", "", part)
        ]
        # Combination order does not change the semantic drug set.
        return "+".join(sorted(components))

    @classmethod
    def _drug_item_map(cls, value: Any) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for item in cls._split_drug_items(value):
            key = cls._canonical_drug_item(item)
            if key:
                result.setdefault(key, item)
        return result

    @staticmethod
    def _merge_unique_analysis_text(existing: str, addition: str) -> str:
        """Preserve unique evidence sentences while collapsing duplicate blocks."""
        sentences: List[str] = []
        seen: set[str] = set()
        for value in (existing, addition):
            for sentence in re.split(r"(?<=。)\s*|\n+", str(value or "")):
                text = sentence.strip()
                key = re.sub(r"\s+", "", text).casefold()
                if text and key not in seen:
                    seen.add(key)
                    sentences.append(text)
        return "".join(sentences)

    @classmethod
    def _coalesce_overlapping_drug_sections(
        cls, sections: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """Merge strict-subset drug blocks for the same exact variant/direction."""
        rows = [dict(section) for section in sections]
        groups: Dict[tuple[str, str, str, str], List[int]] = {}
        token_sets: Dict[int, set[str]] = {}
        for index, row in enumerate(rows):
            group_key = (
                str(row.get("gene") or "").strip().upper(),
                re.sub(r"\s+", "", str(row.get("c_hgvs") or "")).upper(),
                re.sub(r"\s+", "", str(row.get("p_hgvs") or "")).upper(),
                str(row.get("drug_type") or "benefit").strip().lower(),
            )
            groups.setdefault(group_key, []).append(index)
            token_sets[index] = set(cls._drug_item_map(row.get("drug_name")).keys())

        dropped: set[int] = set()
        for indices in groups.values():
            # Largest reviewed block is the anchor; equal/subset blocks merge
            # their unique evidence into it and disappear as duplicate headings.
            ordered = sorted(indices, key=lambda idx: (-len(token_sets[idx]), idx))
            for source in ordered:
                if source in dropped or not token_sets[source]:
                    continue
                target = next(
                    (
                        candidate
                        for candidate in ordered
                        if candidate != source
                        and candidate not in dropped
                        and token_sets[source] <= token_sets[candidate]
                        and (
                            len(token_sets[source]) < len(token_sets[candidate])
                            or candidate < source
                        )
                    ),
                    None,
                )
                if target is None:
                    continue
                for field in ("relation", "clinical"):
                    rows[target][field] = cls._merge_unique_analysis_text(
                        rows[target].get(field, ""), rows[source].get(field, "")
                    )
                dropped.add(source)

        return [row for index, row in enumerate(rows) if index not in dropped]

    def build_drug_analysis_consistency(
        self,
        variants: List[Dict[str, Any]],
        sections: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Compare every table drug with the exact Part-3 variant/direction."""
        expected: Dict[tuple[str, str], Dict[str, str]] = {}
        labels: Dict[tuple[str, str], Dict[str, str]] = {}
        for variant in variants:
            variant_key = self._variant_key_from_row(variant)
            if not variant_key:
                continue
            for direction, field in (
                ("benefit", "benefit_drugs"),
                ("caution", "caution_drugs"),
            ):
                key = (variant_key, direction)
                source = variant.get(f"{field}_full") or variant.get(field)
                items = self._drug_item_map(source)
                if items:
                    expected[key] = items
                    labels[key] = {
                        "gene": str(variant.get("gene") or "").upper(),
                        "c_hgvs": str(
                            variant.get("cHGVS") or variant.get("c_hgvs") or ""
                        ),
                        "p_hgvs": str(
                            variant.get("pHGVS") or variant.get("p_hgvs") or ""
                        ),
                        "direction": direction,
                    }

        rendered: Dict[tuple[str, str], Dict[str, str]] = {}
        occurrences: Dict[tuple[str, str], Dict[str, int]] = {}
        for section in sections:
            variant_key = self._variant_key(
                section.get("gene"),
                section.get("c_hgvs"),
                section.get("p_hgvs"),
            )
            direction = str(section.get("drug_type") or "benefit").lower()
            key = (variant_key, direction)
            if not variant_key:
                continue
            for token, original in self._drug_item_map(
                section.get("drug_name")
            ).items():
                rendered.setdefault(key, {}).setdefault(token, original)
                counts = occurrences.setdefault(key, {})
                counts[token] = counts.get(token, 0) + 1

        missing: List[Dict[str, Any]] = []
        unexpected: List[Dict[str, Any]] = []
        duplicates: List[Dict[str, Any]] = []
        for key in sorted(set(expected) | set(rendered)):
            expected_items = expected.get(key, {})
            rendered_items = rendered.get(key, {})
            label = labels.get(
                key,
                {"variant_key": key[0], "direction": key[1]},
            )
            missing_tokens = sorted(set(expected_items) - set(rendered_items))
            unexpected_tokens = sorted(set(rendered_items) - set(expected_items))
            duplicate_tokens = sorted(
                token
                for token, count in occurrences.get(key, {}).items()
                if count > 1
            )
            if missing_tokens:
                missing.append(
                    {
                        **label,
                        "drugs": [expected_items[token] for token in missing_tokens],
                    }
                )
            if unexpected_tokens:
                unexpected.append(
                    {
                        **label,
                        "drugs": [rendered_items[token] for token in unexpected_tokens],
                    }
                )
            if duplicate_tokens:
                duplicates.append(
                    {
                        **label,
                        "drugs": [rendered_items[token] for token in duplicate_tokens],
                    }
                )

        return {
            "status": "PASS" if not (missing or unexpected or duplicates) else "FAIL",
            "expected_item_count": sum(len(items) for items in expected.values()),
            "rendered_item_count": sum(len(items) for items in rendered.values()),
            "missing": missing,
            "unexpected": unexpected,
            "duplicates": duplicates,
        }

    def build_drug_analysis_contract_coverage(
        self,
        variants: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Report which Part-2 drug rows have an explicit reviewed contract.

        Runtime Part-2/Part-3 consistency is enforced for every CRC358 drug
        row.  This companion metric keeps the remaining migration debt
        visible without confusing legacy-but-consistent content with a
        content omission.
        """
        rows: Dict[str, Dict[str, str]] = {}
        for variant in variants:
            if not any(
                self._has_drug_text(variant.get(field))
                for field in (
                    "benefit_drugs_full",
                    "benefit_drugs",
                    "caution_drugs_full",
                    "caution_drugs",
                )
            ):
                continue
            variant_key = self._variant_key_from_row(variant)
            if not variant_key:
                continue
            rows.setdefault(
                variant_key,
                {
                    "gene": str(variant.get("gene") or "").upper(),
                    "c_hgvs": str(
                        variant.get("cHGVS") or variant.get("c_hgvs") or ""
                    ),
                    "p_hgvs": str(
                        variant.get("pHGVS") or variant.get("p_hgvs") or ""
                    ),
                    "variant_key": variant_key,
                },
            )

        governed_keys = {
            key
            for key, row in rows.items()
            if self.has_reviewed_drug_analysis_contract(row)
        }
        legacy_rows = [rows[key] for key in sorted(set(rows) - governed_keys)]
        expected_count = len(rows)
        governed_count = len(governed_keys)
        return {
            "status": "PASS" if not legacy_rows else "MIGRATION_PENDING",
            "expected_variant_count": expected_count,
            "governed_variant_count": governed_count,
            "coverage_percent": round(
                100.0 * governed_count / expected_count, 2
            )
            if expected_count
            else 100.0,
            "legacy_uncontracted": legacy_rows,
        }

    def _variant_display_from_row(self, row: Dict[str, Any]) -> str:
        c_hgvs = self._norm_text(row.get("cHGVS") or row.get("c_hgvs"))
        p_hgvs = self._norm_text(row.get("pHGVS") or row.get("p_hgvs"))
        return f"{c_hgvs}，{p_hgvs}" if p_hgvs else c_hgvs

    def _has_drug_text(self, value: Any) -> bool:
        text = self._norm_text(value)
        return bool(text and text not in {"--", "无", "未检出"})

    def _is_loss_of_function_variant(self, variant: Dict[str, Any]) -> bool:
        c_hgvs = self._norm_text(variant.get("cHGVS") or variant.get("c_hgvs"))
        p_hgvs = self._norm_text(variant.get("pHGVS") or variant.get("p_hgvs"))
        if re.search(r"\*", p_hgvs) or re.search(r"fs", p_hgvs, re.I):
            return True
        if re.search(r"c\.\d+[+-]\d+", c_hgvs):
            return True
        return False

    def _drug_override_matches_variant(
        self,
        override: Dict[str, str],
        variant: Dict[str, Any],
    ) -> bool:
        applicability = self._hgvs_key(override.get("applicability"))
        if not applicability or applicability in {"ANY", "ALL", "ANYVARIANT"}:
            return True
        parts = {
            part.strip()
            for part in re.split(r"[,;，；/|]+", applicability)
            if part.strip()
        }
        if parts & {"LOSS_OF_FUNCTION", "LOF", "TRUNCATING"}:
            return self._is_loss_of_function_variant(variant)
        return True

    def _apply_reviewed_drug_section_overrides(
        self,
        variants: List[Dict[str, Any]],
        sections: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        if not self._reviewed_drug_section_overrides and not self._gene_level_drug_overrides:
            return sections

        grouped: Dict[tuple[str, str], List[Dict[str, str]]] = {}
        for section in sections:
            key = self._variant_key(
                section.get("gene"),
                section.get("c_hgvs"),
                section.get("p_hgvs"),
            )
            if not key:
                continue
            grouped.setdefault((key, section.get("drug_type", "benefit")), []).append(
                section
            )

        result: List[Dict[str, str]] = []
        visited: set[tuple[str, str]] = set()
        for variant in variants:
            variant_key = self._variant_key_from_row(variant)
            if not variant_key:
                continue
            for drug_type, source_field in (
                ("benefit", "benefit_drugs"),
                ("caution", "caution_drugs"),
            ):
                key = (variant_key, drug_type)
                visited.add(key)
                overrides = self._reviewed_drug_section_overrides.get(key)
                if not overrides:
                    # fall back to gene-level drug override (variant-agnostic)
                    overrides = self._gene_level_drug_overrides.get(
                        (self._hgvs_key(variant.get("gene")), drug_type)
                    )
                if overrides:
                    overrides = [
                        override
                        for override in overrides
                        if self._drug_override_matches_variant(override, variant)
                    ]
                if overrides and self._has_drug_text(variant.get(source_field)):
                    variant_display = self._variant_display_from_row(variant)
                    current_gene = self._norm_text(variant.get("gene")).upper()
                    current_c_hgvs = self._norm_text(
                        variant.get("cHGVS") or variant.get("c_hgvs")
                    )
                    current_p_hgvs = self._norm_text(
                        variant.get("pHGVS") or variant.get("p_hgvs")
                    )
                    for override in overrides:
                        result.append(
                            {
                                **override,
                                # A gene-level reviewed rule owns its prose,
                                # but the rendered section must retain the
                                # concrete Part-2 row identity.  Otherwise the
                                # cross-section gate sees a gene-only phantom
                                # key and reports the real FANCA/TSC1 variant as
                                # missing.
                                "gene": current_gene,
                                "c_hgvs": current_c_hgvs,
                                "p_hgvs": current_p_hgvs,
                                "variant": variant_display,
                            }
                        )
                    continue
                result.extend(grouped.get(key, []))

        for key, rows in grouped.items():
            if key not in visited:
                result.extend(rows)
        return result

    def build_references(
        self,
        variants: List[Dict[str, Any]],
        max_per_gene: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        构建参考文献列表

        Args:
            variants: 变异列表
            max_per_gene: 每个基因最多返回的参考文献数量

        Returns:
            参考文献列表，每个元素包含:
            - gene: 基因名称
            - references: 该基因的参考文献列表
        """
        if not self._loaded:
            self.load()

        result = []
        seen_genes = set()

        for v in variants:
            gene = v.get("gene", "").upper()
            if gene in seen_genes:
                continue
            seen_genes.add(gene)

            refs = self.get_references(gene)
            if refs:
                result.append(
                    {
                        "gene": gene,
                        "references": refs[:max_per_gene],
                    }
                )

        return result

    def build_all_references_flat(
        self,
        variants: List[Dict[str, Any]],
        max_per_gene: int = 5,
    ) -> List[str]:
        """
        构建扁平化的参考文献列表（去重）

        Args:
            variants: 变异列表
            max_per_gene: 每个基因最多返回的参考文献数量

        Returns:
            参考文献字符串列表（已去重）
        """
        if not self._loaded:
            self.load()

        all_refs = []
        seen_refs = set()
        seen_genes = set()

        for v in variants:
            gene = v.get("gene", "").upper()
            if gene in seen_genes:
                continue
            seen_genes.add(gene)

            refs = self.get_references(gene)
            for ref in refs[:max_per_gene]:
                if ref not in seen_refs:
                    seen_refs.add(ref)
                    all_refs.append(ref)

        return all_refs
