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
    def _infer_crc(cancer_type: str, *, crc_keywords: list[str]) -> bool:
        s = str(cancer_type or "").strip().lower()
        if not s or s in {"-", "--"}:
            return False
        return any(str(k).strip().lower() in s for k in crc_keywords if str(k).strip())

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
        c_point = self._norm_text(c_point)
        p_point = self._norm_text(p_point)
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
        crc_keywords = (
            cancer_cfg.get(
                "crc_keywords",
                [
                    "结直肠",
                    "结肠",
                    "直肠",
                    "乙状结肠",
                    "sigmoid",
                    "colon",
                    "rectal",
                    "colorectal",
                ],
            )
            if isinstance(cancer_cfg, dict)
            else []
        )
        is_crc = self._infer_crc(
            cancer_type,
            crc_keywords=crc_keywords if isinstance(crc_keywords, list) else [],
        )
        cgi_allowed_tumor_types = set(
            str(x).strip().upper()
            for x in (
                (
                    cancer_cfg.get("cgi_allowed_primary_tumor_types", ["COREAD"])
                    if isinstance(cancer_cfg, dict)
                    else ["COREAD"]
                )
                or ["COREAD"]
            )
            if str(x).strip()
        )
        civic_disease_keywords = [
            str(x).strip().lower()
            for x in (
                (
                    cancer_cfg.get(
                        "civic_disease_keywords", ["colorectal", "colon", "rectal"]
                    )
                    if isinstance(cancer_cfg, dict)
                    else []
                )
                or []
            )
            if str(x).strip()
        ]
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

            # 生产筛选：按癌种过滤（当前仅对"结直肠癌/CRC"启用分组逻辑；其他癌种默认不做过滤）
            if should_filter and cancer_filter_enabled:
                if not cancer_type or str(cancer_type).strip() in {"-", "--"}:
                    if missing_patient_cancer_action == "reject":
                        continue
                elif is_crc:
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
        for r in variations:
            level = self._norm_text(r.get("ExistIn552"))
            # 兼容数字格式：1=在面板内，需按基因名判断分级
            if level in ("1", "1.0"):
                gene_tmp = get_gene_from_row(r)
                if gene_tmp:
                    from reportgen.core.template_bridge_358 import _get_gene_class
                    level = _get_gene_class(gene_tmp, level)
                else:
                    continue
            elif level in ("0", "0.0"):
                continue
            # 终版报告：靶向药物提示表仅展示Ⅰ/Ⅱ类
            if level not in {"Ⅰ类", "Ⅱ类"}:
                continue
            gene = get_gene_from_row(r)
            c = self._norm_text(r.get("cHGVS"))
            p = self._norm_text(r.get("pHGVS_S") or r.get("pHGVS_A"))
            # 必须是真正的 cHGVS 格式（以 c. 开头），跳过知识库脏数据
            if not gene or not c or not c.startswith("c."):
                continue
            site = format_variant_site(c, p) or c
            gene_to_sites.setdefault(gene, []).append(
                {"c": c, "p": p, "level": level, "site": site}
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
                    }
                )

        # 保持与 Variations 中出现顺序一致
        order: list[str] = []
        seen: set[str] = set()
        for r in variations:
            g = get_gene_from_row(r)
            if g and g in gene_to_sites and g not in seen:
                order.append(g)
                seen.add(g)
        results.sort(
            key=lambda x: order.index(x["gene"]) if x["gene"] in order else 9999
        )
        return results
