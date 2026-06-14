"""
Targeted drug knowledge base helpers for FieldMapper.

We keep method names as FieldMapper "private" methods for backward compatibility
with existing unit tests (which access these internals).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from reportgen.models.excel_data import ExcelDataSource
from reportgen.models.report_data import ReportData
from reportgen.utils.hgvs_utils import format_variant_site


class TargetedDrugMixin:
    # -------------------- targeted drug knowledge base --------------------
    @staticmethod
    def _normalize_drug_evidence_label(value: Any) -> Any:
        """Collapse a baked-in CIViC/CGI evidence tag to a clean grade.

        e.g. "Erlotinib（CIViC:Tier I - Level A）" -> "Erlotinib（A）".
        Display-only: keeps the drug name and the evidence GRADE letter, only
        tidying the label so every panel shows consistent "（A/B/C/D）".
        Idempotent (already-clean "（A）" is left untouched).
        """
        if not isinstance(value, str) or not value:
            return value
        import re

        return re.sub(
            r"[（(]\s*(?:CIViC|CGI)[^）)]*?Level\s*([A-Da-d])[^）)]*[)）]",
            lambda m: f"（{m.group(1).upper()}）",
            value,
        )

    def _load_targeted_drug_db(self) -> None:
        if self._targeted_drug_db_loaded:
            return
        self._targeted_drug_db_loaded = True

        cfg = (
            self.config_loader.get_setting("knowledge_bases.targeted_drug_db", {}) or {}
        )
        if not isinstance(cfg, dict):
            return
        if not bool(cfg.get("enabled", False)):
            return

        path = cfg.get("path")
        if not path:
            return

        db_path = self.config_loader.resolve_path(str(path))
        if not db_path.exists():
            self.logger.warning("靶向药物数据库文件不存在", path=str(db_path))
            return

        xl = None
        try:
            xl = pd.ExcelFile(str(db_path), engine="openpyxl")
        except Exception as e:
            self.logger.warning(
                "打开靶向药物数据库失败", path=str(db_path), error=str(e)
            )
            return

        def find_col(
            cols: list[Any],
            *,
            exact: Optional[str] = None,
            contains: Optional[str] = None,
        ):
            for c in cols:
                s = str(c).strip()
                if exact is not None and s == exact:
                    return c
                if contains is not None and contains in s:
                    return c
            return None

        for sheet in xl.sheet_names:
            try:
                df = xl.parse(sheet)
            except Exception:
                continue

            cols = list(df.columns)
            gene_col = find_col(cols, exact="基因名称")
            level_col = find_col(cols, exact="变异等级")
            c_col = find_col(cols, exact="c_point")
            p_col = find_col(cols, exact="p_point")
            benefit_col = find_col(cols, contains="潜在获益靶向药物")
            caution_col = find_col(cols, contains="可能耐药") or find_col(
                cols, contains="慎重"
            )

            if gene_col is None or benefit_col is None or caution_col is None:
                continue

            # 显示归一化：库里部分条目写死了 CIViC/CGI 原始证据标签，例如
            # "Erlotinib（CIViC:Tier I - Level A）"。收敛成干净的证据等级
            # "Erlotinib（A）"。纯显示层——保留药名与等级、不改医学内容，只让各
            # panel 的药物标签格式一致（修复 EGFR 等条目的标签外漏）。
            for _col in (benefit_col, caution_col):
                try:
                    df[_col] = df[_col].map(self._normalize_drug_evidence_label)
                except Exception:
                    pass

            self._targeted_drug_db = df
            self._targeted_drug_db_cols = {
                "gene": str(gene_col),
                "level": str(level_col) if level_col is not None else "",
                "c": str(c_col) if c_col is not None else "",
                "p": str(p_col) if p_col is not None else "",
                "benefit": str(benefit_col),
                "caution": str(caution_col),
            }
            self.logger.info(
                "加载靶向药物数据库成功",
                path=str(db_path),
                sheet=sheet,
                rows=int(len(df)),
            )
            xl.close()
            return

        self.logger.warning("未在靶向药物数据库中找到可用sheet", path=str(db_path))
        if xl is not None:
            xl.close()

    def _get_targeted_drug_overrides(self) -> dict[str, dict[str, str]]:
        cfg = (
            self.config_loader.get_setting(
                "knowledge_bases.targeted_drug_db.overrides", {}
            )
            or {}
        )
        if not isinstance(cfg, dict):
            return {}
        out: dict[str, dict[str, str]] = {}
        for k, v in cfg.items():
            if not isinstance(v, dict):
                continue
            key = str(k).strip().upper()
            out[key] = {str(kk): str(vv) for kk, vv in v.items() if vv is not None}
        return out

    def _get_reviewed_variant_overrides(self) -> list[dict[str, Any]]:
        """Load reviewed per-variant overrides from CRC panel package rules."""
        project_root = Path(getattr(self.config_loader, "project_root", "."))
        candidates = [
            project_root / "panels" / "crc_358_msi" / "rules" / "crc.yaml",
            Path(self.config_loader.config_dir) / "panels" / "crc_358.yaml",
        ]
        cfg = {}
        for cfg_path in candidates:
            try:
                if cfg_path.exists():
                    cfg = self.config_loader.load_yaml(str(cfg_path))
                    break
            except Exception:
                cfg = {}
        rows = cfg.get("reviewed_variant_overrides", []) if isinstance(cfg, dict) else []
        if not isinstance(rows, list):
            return []
        return [dict(row) for row in rows if isinstance(row, dict)]

    @staticmethod
    def _as_text_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    def _lookup_reviewed_variant_override_drugs(
        self,
        gene: str,
        c_point: str,
        p_point: str,
    ) -> Optional[tuple[str, str]]:
        gene_norm = str(gene or "").strip().upper()
        c_norm = self._norm_text(c_point)
        p_norm = self._norm_text(p_point)
        for override in self._get_reviewed_variant_overrides():
            genes = {
                item.upper()
                for item in self._as_text_list(
                    override.get("gene") or override.get("genes")
                )
            }
            if genes and gene_norm not in genes:
                continue
            if not self._reviewed_variant_override_applicable(
                override.get("applicability")
                or override.get("applies_to")
                or override.get("variant_applicability"),
                c_norm,
                p_norm,
            ):
                continue
            c_values = set(
                self._as_text_list(override.get("c_hgvs") or override.get("cHGVS"))
            )
            p_values = set(
                self._as_text_list(override.get("p_hgvs") or override.get("pHGVS"))
            )
            if c_values and c_norm not in c_values:
                continue
            if p_values and p_norm not in p_values:
                continue
            benefit = "\n".join(self._as_text_list(override.get("benefit_drugs")))
            caution = "\n".join(self._as_text_list(override.get("caution_drugs")))
            if benefit or caution:
                return benefit or "--", caution or "--"
        return None

    @staticmethod
    def _reviewed_variant_override_applicable(
        applicability: Any,
        c_point: str,
        p_point: str,
    ) -> bool:
        text = str(applicability or "").strip().upper()
        if not text or text in {"ANY", "ALL", "ANYVARIANT"}:
            return True
        parts = {
            part.strip()
            for part in re.split(r"[,;，；/|]+", text)
            if part.strip()
        }
        if parts & {"LOSS_OF_FUNCTION", "LOF", "TRUNCATING"}:
            return bool(
                re.search(r"\*", p_point)
                or re.search(r"fs", p_point, re.I)
                or re.search(r"c\.\d+[+-]\d+", c_point)
            )
        return True

    def _get_targeted_drug_db_filters(self) -> dict[str, Any]:
        cfg = (
            self.config_loader.get_setting(
                "knowledge_bases.targeted_drug_db.filters", {}
            )
            or {}
        )
        return cfg if isinstance(cfg, dict) else {}

    @staticmethod
    def _cgi_evidence_rank(evidence: str) -> int:
        """Map CGI evidence level to a comparable rank (higher is stronger)."""
        mapping = {
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
        s = str(evidence or "").strip()
        if not s:
            return -1
        parts = [p.strip().lower() for p in re.split(r"[;,]", s) if p.strip()]
        ranks = [mapping.get(p, -1) for p in parts] or [-1]
        return max(ranks)

    @staticmethod
    def _civic_amp_rank(amp_category: str) -> int:
        """Map CIViC AMP/ASCO/CAP category to a comparable rank (higher is stronger)."""
        s = str(amp_category or "").strip().lower()
        if not s:
            return -1
        if "tier i" in s:
            if "level a" in s:
                return 5
            if "level b" in s:
                return 4
            return 4
        if "tier ii" in s:
            if "level c" in s:
                return 3
            if "level d" in s:
                return 2
            return 2
        if "tier iii" in s:
            return 1
        if "tier iv" in s:
            return 0
        return -1

    @staticmethod
    def _cancer_type_matches(cancer_type: str, *, keywords: list[str]) -> bool:
        """患者癌种是否命中本 panel 配置的癌种关键词（命中才启用按癌种过滤）。

        癌种无关：CRC 传结直肠关键词，肺癌传肺癌关键词，逻辑相同。
        """
        s = str(cancer_type or "").strip().lower()
        if not s or s in {"-", "--"}:
            return False
        return any(str(k).strip().lower() in s for k in keywords if str(k).strip())

    @classmethod
    def _infer_crc(cls, cancer_type: str, *, crc_keywords: list[str]) -> bool:
        """向后兼容别名（历史 CRC 专用命名）；新代码请用 _cancer_type_matches。"""
        return cls._cancer_type_matches(cancer_type, keywords=crc_keywords)

    @staticmethod
    def _norm_keyword_list(value: Any, default: list[str]) -> list[str]:
        """规范化关键词列表；value 为空/非列表时回退 default。"""
        src = value if isinstance(value, list) and value else default
        return [str(x).strip() for x in src if str(x).strip()]

    # CRC 单组配置的历史默认（向后兼容）
    _DEFAULT_CRC_MATCH_KEYWORDS = [
        "结直肠",
        "结肠",
        "直肠",
        "乙状结肠",
        "sigmoid",
        "colon",
        "rectal",
        "colorectal",
    ]

    def _resolve_cancer_profile(
        self, cancer_cfg: Any, cancer_type: str
    ) -> tuple[bool, set[str], list[str]]:
        """按患者癌种选出适用的过滤参数。

        返回 (cancer_matches, cgi_allowed_tumor_types, civic_disease_keywords)。

        支持两种配置形态：
        - ``profiles`` 列表（多癌种）：取首个 ``match_keywords`` 命中患者癌种的
          profile，用其 cgi/civic。配了 profiles 但无命中 → 不按癌种过滤。
        - 单组（历史/向后兼容）：``match_keywords|crc_keywords`` +
          ``cgi_allowed_primary_tumor_types`` + ``civic_disease_keywords``。
        """
        if not isinstance(cancer_cfg, dict):
            return False, set(), []

        def _cgi(value: Any, default: list[str]) -> set[str]:
            return {s.upper() for s in self._norm_keyword_list(value, default)}

        def _civic(value: Any, default: list[str]) -> list[str]:
            return [s.lower() for s in self._norm_keyword_list(value, default)]

        profiles = cancer_cfg.get("profiles")
        if isinstance(profiles, list) and profiles:
            for prof in profiles:
                if not isinstance(prof, dict):
                    continue
                kws = self._norm_keyword_list(
                    prof.get("match_keywords") or prof.get("crc_keywords"), []
                )
                if self._cancer_type_matches(cancer_type, keywords=kws):
                    return (
                        True,
                        _cgi(prof.get("cgi_allowed_primary_tumor_types"), []),
                        _civic(prof.get("civic_disease_keywords"), []),
                    )
            # profiles 已配但患者癌种无命中 → 不按癌种过滤（放行）
            return False, set(), []

        # 单组（向后兼容，CRC 默认）
        match_keywords = self._norm_keyword_list(
            cancer_cfg.get("match_keywords") or cancer_cfg.get("crc_keywords"),
            self._DEFAULT_CRC_MATCH_KEYWORDS,
        )
        cancer_matches = self._cancer_type_matches(
            cancer_type, keywords=match_keywords
        )
        return (
            cancer_matches,
            _cgi(cancer_cfg.get("cgi_allowed_primary_tumor_types"), ["COREAD"]),
            _civic(
                cancer_cfg.get("civic_disease_keywords"),
                ["colorectal", "colon", "rectal"],
            ),
        )

    @classmethod
    def _p_point_matches(cls, db_p: str, patient_p: str) -> bool:
        """判断数据库 p_point 是否能匹配样本 pHGVS_S（支持 p.G12X 这类写法）。"""
        db = cls._norm_text(db_p)
        p = cls._norm_text(patient_p)
        if not db or not p:
            return False

        # 直接包含：覆盖精确列举（如 "... p.G12C ..."）
        if p in db:
            return True

        m = re.match(r"^p\.([A-Za-z])(\d+)([A-Za-z\*])$", p)
        if not m:
            return False
        aa, pos, var = m.group(1).upper(), m.group(2), m.group(3).upper()

        # 识别 X 通配：p.G12X / p.Q61X 等
        for xm in re.finditer(r"p\.([A-Za-z])(\d+)X", db):
            aa2, pos2 = xm.group(1).upper(), xm.group(2)
            if aa2 != aa or pos2 != pos:
                continue

            # 仅在该pattern附近解析"除C、D外"这类排除条件
            segment = db[xm.start() : xm.start() + 120]
            if ")" in segment:
                segment = segment.split(")", 1)[0]
            excl: set[str] = set()
            em = re.search(r"除([^外]{0,40})外", segment)
            if em:
                excl = {x.upper() for x in re.findall(r"[A-Za-z\*]", em.group(1))}
            if var in excl:
                continue

            return True

        return False

    def _lookup_targeted_drugs_for_variant(
        self,
        gene: str,
        *,
        c_point: str,
        p_point: str,
        variant_level: str = "",
        cancer_type: str = "",
    ) -> tuple[str, str, float]:
        """查询单个变异对应的药物提示（获益/慎重）并返回匹配分数。"""
        gene_norm = str(gene).strip().upper()
        c_norm = self._norm_text(c_point)
        p_norm = self._norm_text(p_point)

        reviewed_override = self._lookup_reviewed_variant_override_drugs(
            gene_norm,
            c_norm,
            p_norm,
        )
        if reviewed_override:
            benefit, caution = reviewed_override
            return benefit, caution, 100.0

        overrides = self._get_targeted_drug_overrides()
        if gene_norm in overrides:
            ov = overrides[gene_norm]
            benefit = str(ov.get("benefit_drugs", "")).strip() or "--"
            caution = str(ov.get("caution_drugs", "")).strip() or "--"
            return benefit, caution, 100.0

        self._load_targeted_drug_db()
        if self._targeted_drug_db is None:
            return "--", "--", 0.0

        cols = self._targeted_drug_db_cols
        gene_col = cols.get("gene")
        benefit_col = cols.get("benefit")
        caution_col = cols.get("caution")
        c_col = cols.get("c") or None
        p_col = cols.get("p") or None
        level_col = cols.get("level") or None

        df = self._targeted_drug_db
        if not gene_col or gene_col not in df.columns:
            return "--", "--", 0.0

        sub = df[df[gene_col].astype(str).str.strip().str.upper() == gene_norm]
        if sub.empty:
            return "--", "--", 0.0

        best_score = 0.0
        best_benefit = "--"
        best_caution = "--"
        c_point = c_norm
        p_point = p_norm
        variant_level = self._norm_text(variant_level)

        filters_cfg = self._get_targeted_drug_db_filters()
        filters_enabled = bool(filters_cfg.get("enabled", False))
        apply_sources = {
            str(x).strip().upper()
            for x in (filters_cfg.get("apply_to_sources") or ["CGI", "CIVIC"])
            if str(x).strip()
        }
        require_position_match = bool(filters_cfg.get("require_position_match", False))

        cancer_cfg = filters_cfg.get("cancer_type", {}) or {}
        cancer_filter_enabled = (
            bool(cancer_cfg.get("enabled", False)) and filters_enabled
        )
        # 按患者癌种解析过滤参数：支持 profiles 多癌种列表，回退单组（CRC 向后兼容）。
        (
            cancer_matches,
            cgi_allowed_tumor_types,
            civic_disease_keywords,
        ) = self._resolve_cancer_profile(cancer_cfg, cancer_type)
        missing_patient_cancer_action = (
            str(
                (
                    cancer_cfg.get("if_missing_patient_cancer", "allow")
                    if isinstance(cancer_cfg, dict)
                    else "allow"
                )
            )
            .strip()
            .lower()
        )

        evidence_cfg = filters_cfg.get("evidence", {}) or {}
        evidence_filter_enabled = (
            bool(evidence_cfg.get("enabled", False)) and filters_enabled
        )
        try:
            cgi_min_rank = (
                int(evidence_cfg.get("cgi_min_rank", 0))
                if isinstance(evidence_cfg, dict)
                else 0
            )
        except Exception:
            cgi_min_rank = 0
        try:
            civic_min_rank = (
                int(evidence_cfg.get("civic_min_rank", 0))
                if isinstance(evidence_cfg, dict)
                else 0
            )
        except Exception:
            civic_min_rank = 0
        missing_evidence_action = (
            str(
                (
                    evidence_cfg.get("if_missing_evidence", "allow")
                    if isinstance(evidence_cfg, dict)
                    else "allow"
                )
            )
            .strip()
            .lower()
        )

        for _, row in sub.iterrows():
            db_c = self._norm_text(row.get(c_col)) if c_col else ""
            db_p = self._norm_text(row.get(p_col)) if p_col else ""
            db_level = self._norm_text(row.get(level_col)) if level_col else ""

            if db_c:
                if not c_point or db_c != c_point:
                    continue
            if db_p:
                if not p_point or not self._p_point_matches(db_p, p_point):
                    continue

            source_db = self._norm_text(row.get("source_db")).strip().upper()
            should_filter = filters_enabled and (source_db in apply_sources)

            # 生产筛选：必须位点匹配（防止公共库"仅基因级别"条目误入输出）
            if should_filter and require_position_match and not (db_c or db_p):
                continue

            # 生产筛选：按癌种过滤（panel 配置 match_keywords + cgi_allowed_primary_tumor_types /
            # civic_disease_keywords 驱动；患者癌种命中关键词时才过滤，否则放行）
            if should_filter and cancer_filter_enabled:
                if not cancer_type or str(cancer_type).strip() in {"-", "--"}:
                    if missing_patient_cancer_action == "reject":
                        continue
                elif cancer_matches:
                    if source_db == "CGI":
                        tt = self._norm_text(row.get("cgi_primary_tumor_type"))
                        if tt:
                            row_types = {
                                x.strip().upper() for x in tt.split(";") if x.strip()
                            }
                            if row_types and not (row_types & cgi_allowed_tumor_types):
                                continue
                        elif missing_patient_cancer_action == "reject":
                            continue
                    elif source_db == "CIVIC":
                        disease = self._norm_text(row.get("civic_disease")).lower()
                        if disease:
                            if civic_disease_keywords and not any(
                                k in disease for k in civic_disease_keywords
                            ):
                                continue
                        elif missing_patient_cancer_action == "reject":
                            continue

            # 生产筛选：按证据等级过滤
            if should_filter and evidence_filter_enabled:
                if source_db == "CGI":
                    e = self._norm_text(row.get("cgi_evidence_level"))
                    rank = self._cgi_evidence_rank(e)
                    if rank < 0:
                        if missing_evidence_action == "reject":
                            continue
                    elif rank < cgi_min_rank:
                        continue
                elif source_db == "CIVIC":
                    amp = self._norm_text(row.get("civic_amp_category"))
                    rank = self._civic_amp_rank(amp)
                    if rank < 0:
                        if missing_evidence_action == "reject":
                            continue
                    elif rank < civic_min_rank:
                        continue

            benefit = self._norm_text(row.get(benefit_col)) if benefit_col else ""
            caution = self._norm_text(row.get(caution_col)) if caution_col else ""

            # 评分：优先匹配更具体的位点；同分优先匹配等级；再优先有内容的行
            score = 1.0
            if db_c:
                score += 2.0
            if db_p:
                score += 2.0
            if variant_level and db_level and variant_level == db_level:
                score += 0.2
            if benefit or caution:
                score += 0.1

            if score > best_score:
                best_score = score
                best_benefit = benefit.strip() or "--"
                best_caution = caution.strip() or "--"

        return best_benefit, best_caution, best_score

    def _build_targeted_drug_tips(
        self, excel_data: ExcelDataSource, report_data: ReportData
    ) -> list[dict]:
        """
        靶向药物提示（四列表）。

        - 优先使用 settings.yaml:knowledge_bases.targeted_drug_db（自建数据库）进行匹配；
        - 若未配置/加载失败，则回退为旧逻辑（Variations x CtDrug）。

        输出列：gene, variant_site, benefit_drugs, caution_drugs
        """

        def get_gene_from_row(row: dict) -> Optional[str]:
            for k in ("Gene_Symbol", "基因", "Gene", "检测基因"):
                v = row.get(k)
                if v not in (None, "", "NaN"):
                    return str(v).strip()
            return None

        variations = excel_data.get_table_data("Variations") or []
        report_cancer_type = self._norm_text(report_data.get_field("cancer_type"))
        gene_to_sites: dict[str, list[dict[str, str]]] = {}
        from reportgen.core.template_bridge_358 import (
            _get_gene_class,
            _has_explicit_gene_class_labels,
        )

        allow_gene_fallback = not _has_explicit_gene_class_labels(variations)
        for r in variations:
            level = self._norm_text(r.get("ExistIn552"))
            gene_tmp = get_gene_from_row(r)
            if not gene_tmp:
                continue
            level = _get_gene_class(
                gene_tmp,
                level,
                allow_gene_fallback=allow_gene_fallback,
            )
            if not level:
                continue
            # 终版报告：靶向药物提示表仅展示Ⅰ/Ⅱ类
            if level not in {"Ⅰ类", "Ⅱ类"}:
                continue
            gene = gene_tmp
            c = self._norm_text(r.get("cHGVS"))
            p = self._norm_text(r.get("pHGVS_S") or r.get("pHGVS_A"))
            # 必须是真正的 cHGVS 格式（以 c. 开头），跳过知识库脏数据
            if not gene or not c or not c.startswith("c."):
                continue
            site = format_variant_site(c, p) or c
            gene_to_sites.setdefault(gene, []).append(
                {
                    "c": c,
                    "p": p,
                    "level": level,
                    "site": site,
                    "af": self._norm_text(r.get("Freq(%)") or r.get("AF")),
                }
            )

        if not gene_to_sites:
            return []

        overrides = self._get_targeted_drug_overrides()
        self._load_targeted_drug_db()
        has_kb = self._targeted_drug_db is not None

        # 2) 按位点逐行决策来源：override > KB > CtDrug 回退
        #    每个基因/位点独立判断，不再整体切换模式
        ct = excel_data.get_table_data("CtDrug") or []

        # CtDrug 辅助函数
        def get_ct_gene(row: dict) -> Optional[str]:
            for k in ("检测基因", "Gene", "基因"):
                v = row.get(k)
                if v not in (None, "", "NaN"):
                    return str(v).strip()
            return None

        def get_ct_drug(row: dict) -> Optional[str]:
            for k in ("药物", "Drug", "药物名称"):
                v = row.get(k)
                if v not in (None, "", "NaN"):
                    return str(v).strip()
            return None

        def get_ct_level(row: dict) -> Optional[str]:
            for k in ("等级", "证据等级"):
                v = row.get(k)
                if v not in (None, "", "NaN"):
                    return str(v).strip()
            return None

        def get_ct_tip(row: dict) -> str:
            for k in ("用药提示（仅供参考）", "用药详细描述"):
                v = row.get(k)
                if v not in (None, "", "NaN"):
                    return str(v)
            return ""

        neg_cn = [
            "耐药", "慎重", "不敏感", "无效", "禁用", "风险", "较差", "较低",
            "不推荐", "避免", "禁忌", "谨慎", "疗效差", "疗效较差", "无获益",
            "获益较低", "毒性", "毒副", "副作用", "不良反应增加",
        ]
        neg_en = [
            "toxic", "toxicity", "resist", "resistance", "decrease",
            "decreased", "worse", "contraindicated", "avoid",
        ]

        def _ctdrug_lookup_for_gene(gene: str) -> tuple:
            """从 CtDrug 表中为指定基因提取获益/慎用药物列表。"""
            benefit_list: list[str] = []
            caution_list: list[str] = []
            seen_b: set[str] = set()
            seen_c: set[str] = set()
            for row in ct:
                g = get_ct_gene(row)
                if g != gene:
                    continue
                name = get_ct_drug(row)
                if not name:
                    continue
                level = get_ct_level(row)
                tip = get_ct_tip(row)
                item = f"{name}{'(' + level + ')' if level else ''}"
                tip_l = (tip or "").lower()
                is_caution = any(k in (tip or "") for k in neg_cn) or any(
                    k in tip_l for k in neg_en
                )
                if is_caution:
                    if item not in seen_c:
                        seen_c.add(item)
                        caution_list.append(item)
                else:
                    if item not in seen_b:
                        seen_b.add(item)
                        benefit_list.append(item)
            return (
                "\n".join(benefit_list) if benefit_list else "--",
                "\n".join(caution_list) if caution_list else "--",
            )

        results: list[dict] = []

        for gene, sites in gene_to_sites.items():
            gene_upper = gene.upper()

            for s in sites:
                b, c = "--", "--"
                source = "none"

                # 优先级 1: override（手动审核的固定规则）
                if overrides and gene_upper in overrides:
                    ov = overrides[gene_upper]
                    b = ov.get("benefit_drugs", "--")
                    c = ov.get("caution_drugs", "--")
                    source = "override"

                # 优先级 2: KB 数据库（位点级匹配）
                elif has_kb:
                    kb_b, kb_c, score = self._lookup_targeted_drugs_for_variant(
                        gene,
                        c_point=s["c"],
                        p_point=s["p"],
                        variant_level=s["level"],
                        cancer_type=report_cancer_type,
                    )
                    if score > 0:
                        b = kb_b or "--"
                        c = kb_c or "--"
                        source = "kb"

                # 优先级 3: CtDrug 表回退（基因级）
                if source == "none" or (b == "--" and c == "--" and source != "override"):
                    ct_b, ct_c = _ctdrug_lookup_for_gene(gene)
                    if ct_b != "--" or ct_c != "--":
                        b, c = ct_b, ct_c

                # 摘要页口径：只保留真正有药物关联的位点
                if b == "--" and c == "--":
                    continue

                results.append(
                    {
                        "gene": gene,
                        "variant_site": s["site"],
                        "benefit_drugs": b,
                        "caution_drugs": c,
                        "af": s.get("af", ""),
                    }
                )

        # 按频率从高到低排序，与 2.1 明细表保持一致：基因按其最高频率降序，
        # 基因内部按位点频率降序；同基因相邻。频率相同/缺失时，以基因在
        # Variations 中的首次出现顺序作为稳定兜底。
        def _af_value(value) -> float:
            text = self._norm_text(value).replace("%", "").strip()
            try:
                return float(text)
            except (TypeError, ValueError):
                return float("-inf")

        gene_max_af: dict[str, float] = {}
        gene_first_index: dict[str, int] = {}
        for index, r in enumerate(variations):
            g = get_gene_from_row(r)
            if not g or g not in gene_to_sites:
                continue
            af = _af_value(r.get("Freq(%)") or r.get("AF"))
            if g not in gene_max_af or af > gene_max_af[g]:
                gene_max_af[g] = af
            gene_first_index.setdefault(g, index)

        results.sort(
            key=lambda x: (
                -gene_max_af.get(x["gene"], float("-inf")),
                gene_first_index.get(x["gene"], 9999),
                -_af_value(x.get("af")),
            )
        )
        # 移除仅用于排序的临时频率字段，保持输出列与模板一致。
        for x in results:
            x.pop("af", None)
        return results
