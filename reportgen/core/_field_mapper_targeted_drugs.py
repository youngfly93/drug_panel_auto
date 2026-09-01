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
from reportgen.rules.targeted_drugs import (
    reviewed_variant_transcript_matches,
    select_reviewed_variant_rule,
)
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

        normalized = re.sub(
            r"[（(]\s*(?:CIViC|CGI)[^）)]*?Level\s*([A-Da-d])[^）)]*[)）]",
            lambda m: f"（{m.group(1).upper()}）",
            value,
        )
        # Some historical workbook cells concatenate adjacent drug items with
        # no delimiter (for example ``NXP800（C）Tuvusertib+Peposertib（C）``).
        # An evidence-grade close marker is an unambiguous item boundary in
        # these display-only columns. Restore the missing line break once at
        # ingestion so Part 2, Part 3, summaries, and consistency QA all see
        # the same item list.
        return re.sub(
            r"([（(]\s*[A-Da-d]\s*[)）])(?=[^\s、，,；;\r\n])",
            r"\1\n",
            normalized,
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

        configured_sheet = str(cfg.get("sheet") or "").strip()
        if configured_sheet:
            if configured_sheet in xl.sheet_names:
                candidate_sheets = [configured_sheet]
            else:
                self.logger.warning(
                    "靶向药物数据库指定sheet不存在，将回退自动查找",
                    path=str(db_path),
                    sheet=configured_sheet,
                    available_sheets=xl.sheet_names,
                )
                candidate_sheets = xl.sheet_names
        else:
            candidate_sheets = xl.sheet_names

        for sheet in candidate_sheets:
            try:
                df = xl.parse(sheet)
            except Exception:
                continue

            cols = list(df.columns)
            gene_col = find_col(cols, exact="基因名称")
            level_col = find_col(cols, exact="变异等级")
            c_col = find_col(cols, exact="c_point")
            p_col = find_col(cols, exact="p_point")
            variant_type_col = find_col(cols, exact="扩增/缺失/融合/胚系/未见突变")
            benefit_col = find_col(cols, contains="潜在获益靶向药物")
            caution_col = find_col(cols, contains="可能耐药") or find_col(
                cols, contains="慎重"
            )

            if gene_col is None or benefit_col is None or caution_col is None:
                continue

            source_rows = int(len(df))
            # Exact duplicates must not create repeated drug decisions.  This
            # is intentionally conservative: rows that differ in evidence,
            # cancer context or selector remain separate.
            df = df.drop_duplicates().reset_index(drop=True)
            duplicate_rows_removed = source_rows - int(len(df))

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
                "variant_type": str(variant_type_col)
                if variant_type_col is not None
                else "",
                "benefit": str(benefit_col),
                "caution": str(caution_col),
            }
            self.logger.info(
                "加载靶向药物数据库成功",
                path=str(db_path),
                sheet=sheet,
                rows=int(len(df)),
                source_rows=source_rows,
                exact_duplicate_rows_removed=duplicate_rows_removed,
            )
            xl.close()
            return

        self.logger.warning("未在靶向药物数据库中找到可用sheet", path=str(db_path))
        if xl is not None:
            xl.close()

    def _get_targeted_drug_overrides(
        self,
        targeted_drug_rules: Optional[dict[str, Any]] = None,
    ) -> dict[str, dict[str, str]]:
        if targeted_drug_rules is not None:
            cfg = (
                targeted_drug_rules.get("overrides", {})
                if targeted_drug_rules.get("enabled")
                else {}
            )
        else:
            # Backward compatibility for direct FieldMapper callers that do not
            # resolve a panel package. Production ReportGenerator/Web paths pass
            # an explicit request-scoped rule context.
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

    def _get_reviewed_variant_overrides(
        self,
        targeted_drug_rules: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Load reviewed per-variant overrides for this request's panel."""
        if targeted_drug_rules is not None:
            if not targeted_drug_rules.get("enabled"):
                return []
            rows = targeted_drug_rules.get("reviewed_variant_overrides", [])
            return [dict(row) for row in rows if isinstance(row, dict)]

        # Backward compatibility for direct callers without a panel package.
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
    def _get_blocked_reviewed_variant_overrides(
        targeted_drug_rules: Optional[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return governed selectors that must block lower-priority fallbacks."""
        if not targeted_drug_rules or not targeted_drug_rules.get("enabled"):
            return []
        rows = targeted_drug_rules.get("blocked_reviewed_variant_overrides", [])
        return [dict(row) for row in rows if isinstance(row, dict)]

    def _get_targeted_drug_applicability_rules(
        self,
        targeted_drug_rules: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Load guardrails for broad targeted-drug DB rows.

        These rules are intentionally narrower than reviewed_variant_overrides:
        they do not create drug conclusions. They only reject over-broad KB rows
        such as internal gene-level rows for genes whose drug interpretation must
        be variant-/event-specific.
        """
        if targeted_drug_rules is not None:
            if not targeted_drug_rules.get("enabled"):
                return []
            rows = targeted_drug_rules.get("applicability_rules", [])
            return [dict(row) for row in rows if isinstance(row, dict)]

        # Backward compatibility for direct callers without a panel package.
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
        rows = (
            cfg.get("targeted_drug_applicability_rules", [])
            if isinstance(cfg, dict)
            else []
        )
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
        variant_level: str = "",
        transcript: str = "",
        *,
        targeted_drug_rules: Optional[dict[str, Any]] = None,
    ) -> Optional[tuple[str, str]]:
        gene_norm = str(gene or "").strip().upper()
        c_norm = self._norm_text(c_point)
        p_norm = self._norm_text(p_point)
        level_norm = self._norm_text(variant_level)
        overrides = (
            self._get_reviewed_variant_overrides()
            if targeted_drug_rules is None
            else self._get_reviewed_variant_overrides(targeted_drug_rules)
        )

        def matches(override: dict[str, Any]) -> bool:
            genes = {
                item.upper()
                for item in self._as_text_list(
                    override.get("gene") or override.get("genes")
                )
            }
            if genes and gene_norm not in genes:
                return False
            if not reviewed_variant_transcript_matches(override, transcript):
                return False
            level_values = self._as_text_list(
                override.get("variant_level")
                or override.get("variant_levels")
                or override.get("level")
                or override.get("levels")
            )
            if level_values and not self._variant_level_matches(
                level_norm, level_values
            ):
                return False
            if not self._reviewed_variant_override_applicable(
                override.get("applicability")
                or override.get("applies_to")
                or override.get("variant_applicability"),
                c_norm,
                p_norm,
            ):
                return False
            c_values = set(
                self._as_text_list(override.get("c_hgvs") or override.get("cHGVS"))
            )
            p_values = set(
                self._as_text_list(override.get("p_hgvs") or override.get("pHGVS"))
            )
            if c_values and c_norm not in c_values:
                return False
            if p_values and p_norm not in p_values:
                return False
            return True

        blocked = self._get_blocked_reviewed_variant_overrides(
            targeted_drug_rules
        )
        selected, selected_is_blocked = select_reviewed_variant_rule(
            overrides,
            blocked,
            matches=matches,
        )
        # A pending selector suppresses lower-priority fallbacks, but it must
        # not shadow a more-specific approved exact-variant rule. Equal
        # specificity remains fail-closed.
        if selected_is_blocked:
            return "--", "--"
        if selected is not None:
            benefit = "\n".join(self._as_text_list(selected.get("benefit_drugs")))
            caution = "\n".join(self._as_text_list(selected.get("caution_drugs")))
            if benefit or caution:
                notices: list[str] = []
                clinical_notice = str(
                    selected.get("_clinical_context_display_notice") or ""
                ).strip()
                if clinical_notice:
                    notices.append(clinical_notice)

                review_display = (
                    (targeted_drug_rules or {}).get("review_status_display") or {}
                )
                if isinstance(review_display, dict) and str(
                    review_display.get("mode") or ""
                ).strip().lower() == "show_with_notice":
                    configured_statuses = {
                        str(value).strip().lower()
                        for value in review_display.get("visible_statuses") or []
                        if str(value).strip()
                    }
                    row_statuses = {
                        str(value).strip().lower()
                        for value in (
                            selected.get("review_status"),
                            selected.get("secondary_review_status"),
                            (selected.get("review_metadata") or {}).get(
                                "secondary_review_status"
                            )
                            if isinstance(selected.get("review_metadata"), dict)
                            else "",
                        )
                        if str(value or "").strip()
                    }
                    if not configured_statuses or row_statuses & configured_statuses:
                        review_notice = str(
                            review_display.get("notice") or ""
                        ).strip()
                        if review_notice and review_notice not in notices:
                            notices.append(review_notice)

                if notices:
                    suffix = "\n".join(f"【{notice}】" for notice in notices)
                    if benefit and benefit != "--":
                        benefit = f"{benefit}\n{suffix}"
                    elif caution and caution != "--":
                        caution = f"{caution}\n{suffix}"
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

    @classmethod
    def _variant_level_aliases(cls, value: Any) -> set[str]:
        text = cls._norm_text(value).upper().replace(" ", "")
        if not text:
            return set()
        if text in {"1", "I", "Ⅰ", "一类", "1类", "I类", "Ⅰ类"}:
            return {"Ⅰ类", "1类", "I类", "一类"}
        if text in {"2", "II", "Ⅱ", "二类", "2类", "II类", "Ⅱ类"}:
            return {"Ⅱ类", "2类", "II类", "二类"}
        if text in {"3", "III", "Ⅲ", "三类", "3类", "III类", "Ⅲ类"}:
            return {"Ⅲ类", "3类", "III类", "三类"}
        return {text}

    @classmethod
    def _variant_level_matches(cls, candidate: Any, allowed_values: list[str]) -> bool:
        candidate_aliases = cls._variant_level_aliases(candidate)
        if not candidate_aliases:
            return False
        for allowed in allowed_values:
            if candidate_aliases & cls._variant_level_aliases(allowed):
                return True
        return False

    def _get_targeted_drug_db_filters(self) -> dict[str, Any]:
        cfg = (
            self.config_loader.get_setting(
                "knowledge_bases.targeted_drug_db.filters", {}
            )
            or {}
        )
        return cfg if isinstance(cfg, dict) else {}

    @classmethod
    def _source_matches_rule(cls, source_db: str, sources: Any) -> bool:
        values = {str(x).strip().upper() for x in cls._as_text_list(sources)}
        return not values or str(source_db or "").strip().upper() in values

    def _targeted_drug_db_row_applicable(
        self,
        *,
        gene: str,
        source_db: str,
        db_c: str,
        db_p: str,
        db_variant_type: str,
        targeted_drug_rules: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Return whether a DB row may be used for this patient variant.

        Reviewed overrides are checked before the DB lookup and bypass this
        guardrail. This function only prevents broad KB rows from being treated
        as variant-specific evidence.
        """
        gene_norm = str(gene or "").strip().upper()
        source_norm = str(source_db or "").strip().upper()
        variant_type_norm = str(db_variant_type or "").strip().upper()

        rules = (
            self._get_targeted_drug_applicability_rules()
            if targeted_drug_rules is None
            else self._get_targeted_drug_applicability_rules(targeted_drug_rules)
        )
        for rule in rules:
            genes = {
                item.upper()
                for item in self._as_text_list(rule.get("gene") or rule.get("genes"))
            }
            if genes and gene_norm not in genes:
                continue

            sources = (
                rule.get("source_db")
                or rule.get("source_dbs")
                or rule.get("sources")
                or rule.get("apply_to_sources")
            )
            if not self._source_matches_rule(source_norm, sources):
                continue

            if bool(rule.get("reject_when_db_position_missing", False)) and not (
                db_c or db_p
            ):
                return False

            required_types = {
                item.strip().upper()
                for item in self._as_text_list(
                    rule.get("required_variant_type")
                    or rule.get("required_variant_types")
                )
            }
            if required_types and variant_type_norm not in required_types:
                return False

        return True

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
        transcript: str = "",
        cancer_type: str = "",
        targeted_drug_rules: Optional[dict[str, Any]] = None,
    ) -> tuple[str, str, float]:
        """查询单个变异对应的药物提示（获益/慎重）并返回匹配分数。"""
        gene_norm = str(gene).strip().upper()
        c_norm = self._norm_text(c_point)
        p_norm = self._norm_text(p_point)

        # An explicit disabled Panel policy is fail-closed: no override, base
        # database row, or legacy CtDrug decision may leak in from another
        # cancer Panel. Only no-panel legacy callers retain historical behavior.
        if targeted_drug_rules is not None and not targeted_drug_rules.get(
            "enabled", False
        ):
            return "--", "--", 0.0

        reviewed_override = self._lookup_reviewed_variant_override_drugs(
            gene_norm,
            c_norm,
            p_norm,
            variant_level=variant_level,
            transcript=transcript,
            targeted_drug_rules=targeted_drug_rules,
        )
        if reviewed_override:
            benefit, caution = reviewed_override
            return benefit, caution, 100.0

        overrides = self._get_targeted_drug_overrides(targeted_drug_rules)
        if gene_norm in overrides:
            ov = overrides[gene_norm]
            benefit = str(ov.get("benefit_drugs", "")).strip() or "--"
            caution = str(ov.get("caution_drugs", "")).strip() or "--"
            return benefit, caution, 100.0

        if targeted_drug_rules is not None and not targeted_drug_rules.get(
            "base_db_enabled", False
        ):
            return "--", "--", 0.0

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
        variant_type_col = cols.get("variant_type") or None

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
        if targeted_drug_rules is not None and targeted_drug_rules.get(
            "require_cancer_profile_match", False
        ):
            if (
                not cancer_type
                or str(cancer_type).strip() in {"-", "--"}
                or not cancer_matches
            ):
                return "--", "--", 0.0

        allowed_source_dbs = (
            {
                str(source).strip().upper()
                for source in targeted_drug_rules.get("allowed_source_dbs", [])
                if str(source).strip()
            }
            if targeted_drug_rules is not None
            else set()
        )
        allow_internal_rows = bool(
            targeted_drug_rules.get("allow_internal_rows", False)
        ) if targeted_drug_rules is not None else True

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
            db_variant_type = (
                self._norm_text(row.get(variant_type_col))
                if variant_type_col
                else ""
            )

            if db_c:
                if not c_point or db_c != c_point:
                    continue
            if db_p:
                if not p_point or not self._p_point_matches(db_p, p_point):
                    continue

            source_db = self._norm_text(row.get("source_db")).strip().upper()
            if targeted_drug_rules is not None:
                if source_db not in allowed_source_dbs:
                    continue
                if source_db == "INTERNAL" and not allow_internal_rows:
                    continue
            if not self._targeted_drug_db_row_applicable(
                gene=gene_norm,
                source_db=source_db,
                db_c=db_c,
                db_p=db_p,
                db_variant_type=db_variant_type,
                targeted_drug_rules=targeted_drug_rules,
            ):
                continue
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
        self,
        excel_data: ExcelDataSource,
        report_data: ReportData,
        *,
        targeted_drug_rules: Optional[dict[str, Any]] = None,
    ) -> list[dict]:
        """
        靶向药物提示（四列表）。

        - 优先使用 settings.yaml:knowledge_bases.targeted_drug_db（自建数据库）进行匹配；
        - 若未配置/加载失败，则回退为旧逻辑（Variations x CtDrug）。

        输出列：gene, variant_site, benefit_drugs, caution_drugs
        """

        if targeted_drug_rules is not None and not targeted_drug_rules.get(
            "enabled", False
        ):
            return []

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

        display_scope = str(
            (targeted_drug_rules or {}).get(
                "summary_display_scope", "drug_matched_variants"
            )
        ).strip().lower()
        display_all_reportable = display_scope == "all_reportable_variants"
        configured_display_levels = {
            self._norm_text(level)
            for level in (targeted_drug_rules or {}).get(
                "summary_display_variant_levels", ["Ⅰ类", "Ⅱ类"]
            )
            if self._norm_text(level)
        }
        if not configured_display_levels:
            configured_display_levels = {"Ⅰ类", "Ⅱ类"}

        panel_id = str((targeted_drug_rules or {}).get("panel_id") or "").strip()
        panel_filter_column = {
            "crc_358_msi": "ExistInsmall358",
            "crc_301_msi": "ExistInsmall301",
        }.get(panel_id)

        allow_gene_fallback = not _has_explicit_gene_class_labels(variations)
        for r in variations:
            if panel_filter_column and panel_filter_column in r and r.get(
                panel_filter_column
            ) not in (1, "1", True):
                continue
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
            # 默认沿用历史口径，只处理Ⅰ/Ⅱ类。CRC 报告组确认的
            # all_reportable_variants 口径允许Ⅰ/Ⅱ/Ⅲ类全部进入小结，但Ⅲ类
            # 仍不参与药物推断，药物列固定显示“--”。
            if level not in configured_display_levels:
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
                    "transcript": self._norm_text(r.get("Transcript")),
                    "site": site,
                    "af": self._norm_text(r.get("Freq(%)") or r.get("AF")),
                }
            )

        if not gene_to_sites:
            return []

        overrides = self._get_targeted_drug_overrides(targeted_drug_rules)
        base_db_enabled = targeted_drug_rules is None or bool(
            targeted_drug_rules.get("base_db_enabled", False)
        )
        if base_db_enabled:
            self._load_targeted_drug_db()
        has_kb = self._targeted_drug_db is not None
        # CtDrug is a legacy, gene-level fallback. An explicit Panel package is
        # governed even when its optional base database is unavailable, so it
        # must fail closed instead of silently reopening historical rows.
        allow_ctdrug_fallback = targeted_drug_rules is None and not has_kb

        # 2) 按位点逐行决策来源：override > KB > CtDrug 回退。
        #    生产配置中 KB 正常加载时，禁止再用 CtDrug 兜底。CtDrug 可能包含
        #    化疗药物/其它治疗提示，不能污染“靶向药物相关体细胞变异用药提示”。
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
                drug_rule_eligible = s["level"] in {"Ⅰ类", "Ⅱ类"}

                # 优先级 1: override（手动审核的固定规则）
                if drug_rule_eligible and overrides and gene_upper in overrides:
                    ov = overrides[gene_upper]
                    b = ov.get("benefit_drugs", "--")
                    c = ov.get("caution_drugs", "--")
                    source = "override"

                # 优先级 2: Panel精确审核规则 / KB数据库（位点级匹配）。
                # 显式Panel即使禁用或缺失base DB，也必须执行精确规则查询。
                elif drug_rule_eligible and (
                    targeted_drug_rules is not None or has_kb
                ):
                    kb_b, kb_c, score = self._lookup_targeted_drugs_for_variant(
                        gene,
                        c_point=s["c"],
                        p_point=s["p"],
                        variant_level=s["level"],
                        transcript=s["transcript"],
                        cancer_type=report_cancer_type,
                        targeted_drug_rules=targeted_drug_rules,
                    )
                    if score > 0:
                        b = kb_b or "--"
                        c = kb_c or "--"
                        source = "kb"

                # 优先级 3: CtDrug 表回退（仅旧无Panel调用且KB不可用时启用）
                if drug_rule_eligible and allow_ctdrug_fallback and (
                    source == "none"
                    or (b == "--" and c == "--" and source != "override")
                ):
                    ct_b, ct_c = _ctdrug_lookup_for_gene(gene)
                    if ct_b != "--" or ct_c != "--":
                        b, c = ct_b, ct_c

                # 默认只保留真正有药物关联的位点；报告组确认需要完整小结的
                # panel 则保留无药物结论行，并明确显示“--”。
                if b == "--" and c == "--" and not display_all_reportable:
                    continue

                results.append(
                    {
                        "gene": gene,
                        "variant_site": s["site"],
                        "transcript": s["transcript"],
                        "gene_class": s["level"],
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
