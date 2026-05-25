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
from typing import Any, Dict, List, Optional

import pandas as pd

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

        # 数据缓存
        self._gene_analysis_df: Optional[pd.DataFrame] = None
        self._drug_analysis_df: Optional[pd.DataFrame] = None
        self._gene_transcript_df: Optional[pd.DataFrame] = None
        self._references_df: Optional[pd.DataFrame] = None

        # 索引缓存（基因名 -> 数据行）
        self._gene_intro_cache: Dict[str, str] = {}
        self._gene_analysis_cache: Dict[str, str] = {}
        self._reviewed_gene_analysis_cache: Dict[str, Dict[str, str]] = {}
        self._reviewed_gene_section_overrides: Dict[str, Dict[str, str]] = {}
        self._reviewed_drug_section_overrides: Dict[tuple[str, str], List[Dict[str, str]]] = {}
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

        # 加载基因-转录本-染色体信息
        transcript_config = self.config.get("gene_transcript_db", {})
        if transcript_config.get("enabled", False):
            db_path = base / transcript_config.get("path", "")
            if db_path.exists():
                self._load_gene_transcript_db(db_path, transcript_config)

        self._loaded = True
        return True

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

            for row in data.get("gene_sections") or []:
                if not isinstance(row, dict):
                    continue
                key = self._variant_key(
                    row.get("gene"), row.get("c_hgvs"), row.get("p_hgvs")
                )
                if key:
                    self._reviewed_gene_section_overrides[key] = {
                        k: self._norm_text(v)
                        for k, v in row.items()
                        if k in {"intro", "mutation_analysis"}
                        and self._norm_text(v)
                    }

            for row in data.get("drug_sections") or []:
                if not isinstance(row, dict):
                    continue
                variant_key = self._variant_key(
                    row.get("gene"), row.get("c_hgvs"), row.get("p_hgvs")
                )
                drug_type = self._norm_text(row.get("type")) or "benefit"
                if not variant_key:
                    continue
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
                }
                self._reviewed_drug_section_overrides.setdefault(
                    (variant_key, drug_type), []
                ).append(clean_row)

    def _hgvs_key(self, value: Any) -> str:
        return re.sub(r"\s+", "", self._norm_text(value)).upper()

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

            # 缓存基因简介。部分处理后的知识库会把“蛋白结构域”自动摘要
            # 拼到简介末尾；终版报告把这类内容放在“基因变异解析”段。
            intro = self._norm_text(row.get(intro_col))
            if intro and gene_upper not in self._gene_intro_cache:
                self._gene_intro_cache[gene_upper] = self._strip_intro_domain_tail(
                    gene_upper, intro
                )

            # 缓存基因变异解析
            analysis = self._norm_text(row.get(analysis_col))
            if analysis and gene_upper not in self._gene_analysis_cache:
                self._gene_analysis_cache[gene_upper] = analysis

            reviewed = self._extract_reviewed_analysis_fields(row, df.columns)
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

    def _strip_intro_domain_tail(self, gene: str, intro: str) -> str:
        lines = [line.strip() for line in str(intro).splitlines() if line.strip()]
        if len(lines) <= 1:
            return intro
        kept = []
        for line in lines:
            if (
                line.upper().startswith(f"{gene}基因".upper())
                and "编码的蛋白全长" in line
            ):
                continue
            kept.append(line)
        return "\n".join(kept) if kept else intro

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
        reviewed = self._reviewed_gene_analysis_cache.get(gene.upper(), {})
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
        intro = self._gene_intro_cache.get(gene.upper(), "")
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
        return self._gene_analysis_cache.get(gene.upper(), "")

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

        gene_drugs = self._drug_analysis_cache.get(gene.upper(), {})
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
        return self._drug_full_cache.get(gene.upper(), [])

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
        return self._references_cache.get(gene.upper(), [])

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
        return self._gene_transcript_cache.get(gene.upper(), {})

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
        if p_display:
            header = f"{gene}：{c_hgvs}，{p_display}；{frequency:.2f}%"
        else:
            header = f"{gene}：{c_hgvs}；{frequency:.2f}%"

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
        reviewed_override = self._reviewed_gene_section_overrides.get(
            self._variant_key(gene, c_hgvs, p_hgvs),
            {},
        )
        intro = reviewed_override.get("intro") or intro
        mutation_analysis = (
            reviewed_override.get("mutation_analysis") or mutation_analysis
        )

        return {
            "gene": gene,
            "header": header,
            "header_color": header_color,
            "intro": intro,
            "mutation_desc": mutation_desc,
            "mutation_analysis": mutation_analysis,
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
            variant_key = f"{gene}:{c_hgvs}:{p_hgvs}"
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
            has_drug = (
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
            sections.append(section)

        return sections

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
                                        "relation": _filter_analysis_text(
                                            drug_info.get("relation", ""),
                                            kb_drug_name=drug_name,
                                            variant_drugs=benefit_drugs,
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
                                        "relation": _filter_analysis_text(
                                            drug_info.get("relation", ""),
                                            kb_drug_name=drug_name,
                                            variant_drugs=caution_drugs,
                                        ),
                                        "clinical": _filter_analysis_text(
                                            drug_info.get("clinical", ""),
                                            kb_drug_name=drug_name,
                                            variant_drugs=caution_drugs,
                                        ),
                                    }
                                )

        return self._apply_reviewed_drug_section_overrides(variants, sections)

    def _variant_display_from_row(self, row: Dict[str, Any]) -> str:
        c_hgvs = self._norm_text(row.get("cHGVS") or row.get("c_hgvs"))
        p_hgvs = self._norm_text(row.get("pHGVS") or row.get("p_hgvs"))
        return f"{c_hgvs}，{p_hgvs}" if p_hgvs else c_hgvs

    def _has_drug_text(self, value: Any) -> bool:
        text = self._norm_text(value)
        return bool(text and text not in {"--", "无", "未检出"})

    def _apply_reviewed_drug_section_overrides(
        self,
        variants: List[Dict[str, Any]],
        sections: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        if not self._reviewed_drug_section_overrides:
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
                if overrides and self._has_drug_text(variant.get(source_field)):
                    variant_display = self._variant_display_from_row(variant)
                    for override in overrides:
                        result.append(
                            {
                                **override,
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
