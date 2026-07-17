"""
Immune-related gene list helpers for FieldMapper.

Separated from field_mapper.py to keep FieldMapper focused on orchestration.
We keep method names as FieldMapper internals for backward compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from reportgen.models.excel_data import ExcelDataSource
from reportgen.rules.schema import load_rule_yaml


class ImmuneGeneMixin:
    def _load_panel_immune_gene_sets(
        self,
        panel_package: Any,
    ) -> dict[str, set[str]] | None:
        """Load the authoritative immune sets declared by one Panel package.

        ``None`` means that the package does not declare a biomarkers rule and
        the legacy public XLSX may be used as a compatibility fallback.  Once a
        package declares ``rules.biomarkers``, its immune table is authoritative:
        a missing/malformed table raises instead of silently changing medical
        semantics by falling back to the global list.
        """
        if panel_package is None:
            return None

        rules = getattr(panel_package, "rules", {}) or {}
        if not isinstance(rules, Mapping) or "biomarkers" not in rules:
            return None

        rule_path = panel_package.resolve_rule_file("biomarkers")
        raw = load_rule_yaml(rule_path)
        biomarkers = raw.get("biomarkers")
        if not isinstance(biomarkers, Mapping):
            raise ValueError(
                f"Panel biomarker rule has no biomarkers mapping: {rule_path}"
            )
        tables = biomarkers.get("immune_gene_tables")
        if not isinstance(tables, Mapping):
            raise ValueError(
                f"Panel biomarker rule has no immune_gene_tables mapping: {rule_path}"
            )

        def collect(category: str) -> set[str]:
            section = tables.get(category)
            if not isinstance(section, Mapping):
                return set()
            values = section.get("genes") or []
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, (list, tuple, set)):
                raise ValueError(
                    f"Panel immune genes must be a list: {rule_path}#{category}"
                )
            return {
                str(value).strip().upper()
                for value in values
                if str(value).strip()
            }

        gene_sets = {
            "pos": collect("positive"),
            "neg": collect("negative"),
            "hyper": collect("hyperprogression"),
        }
        self.logger.info(
            "使用Panel免疫基因规则",
            panel_id=str(getattr(panel_package, "panel_id", "") or ""),
            path=str(rule_path),
            pos=len(gene_sets["pos"]),
            neg=len(gene_sets["neg"]),
            hyper=len(gene_sets["hyper"]),
        )
        return gene_sets

    @staticmethod
    def _panel_variant_membership_columns(panel_package: Any) -> tuple[str, ...]:
        """Return panel-membership columns declared for ``Variations`` rows."""
        if panel_package is None:
            return ()
        contract = getattr(panel_package, "input_contract", {}) or {}
        if not isinstance(contract, Mapping):
            return ()
        required = contract.get("required_columns") or {}
        if not isinstance(required, Mapping):
            return ()
        columns = required.get("Variations") or []
        if isinstance(columns, str):
            columns = [columns]
        if not isinstance(columns, (list, tuple, set)):
            return ()
        return tuple(
            str(column).strip()
            for column in columns
            if str(column).strip().lower().startswith("existinsmall")
        )

    def _load_immune_gene_sets(
        self,
        panel_package: Any = None,
    ) -> dict[str, set[str]]:
        """加载免疫相关基因列表（正相关/负相关/超进展相关）。

        Panel包声明的 ``rules/biomarkers.yaml`` 是运行时单一真源；只有
        未声明该规则的旧项目才回退到公共xlsx。

        期望的xlsx结构示例见 `2025.12.12/1-免疫治疗相关基因.xlsx`：
        - 前3列：免疫治疗正相关基因（可能跨多列排版）
        - 中间3列：免疫治疗负相关基因
        - 后2列：免疫超进展相关基因（可能带备注列）
        """
        panel_gene_sets = self._load_panel_immune_gene_sets(panel_package)
        if panel_gene_sets is not None:
            return panel_gene_sets

        if self._immune_gene_list_loaded:
            return self._immune_gene_sets
        self._immune_gene_list_loaded = True

        cfg = (
            self.config_loader.get_setting("knowledge_bases.immune_gene_list", {}) or {}
        )
        if not isinstance(cfg, dict) or not bool(cfg.get("enabled", False)):
            self._immune_gene_sets = {}
            return self._immune_gene_sets

        path = cfg.get("path")
        if not path:
            self._immune_gene_sets = {}
            return self._immune_gene_sets

        xlsx_path = self.config_loader.resolve_path(str(path))
        if not xlsx_path.exists():
            self.logger.warning("免疫相关基因列表文件不存在", path=str(xlsx_path))
            self._immune_gene_sets = {}
            return self._immune_gene_sets

        try:
            df = pd.read_excel(str(xlsx_path), sheet_name=0, engine="openpyxl")
        except Exception as e:
            self.logger.warning(
                "读取免疫相关基因列表失败", path=str(xlsx_path), error=str(e)
            )
            self._immune_gene_sets = {}
            return self._immune_gene_sets

        def collect(cols: list[str]) -> set[str]:
            genes: set[str] = set()
            for col in cols:
                if col not in df.columns:
                    continue
                for v in df[col].tolist():
                    s = self._norm_text(v)
                    if not s or s in {"基因", "又名"}:
                        continue
                    # 去掉可能的备注（如 "EGFR 只要扩增"）
                    s = s.split()[0].strip()
                    if s:
                        genes.add(s.upper())
            return genes

        pos_cols = ["免疫治疗正相关基因", "Unnamed: 1", "Unnamed: 2"]
        neg_cols = ["免疫治疗负相关基因", "Unnamed: 4", "Unnamed: 5"]
        hyper_cols = ["免疫超进展相关基因", "Unnamed: 7"]

        pos = collect(pos_cols)
        neg = collect(neg_cols)
        hyper = collect(hyper_cols)

        extra_pos = cfg.get("extra_positive_genes", []) or []
        if isinstance(extra_pos, list):
            pos |= {str(x).strip().upper() for x in extra_pos if str(x).strip()}

        self._immune_gene_sets = {"pos": pos, "neg": neg, "hyper": hyper}
        self.logger.info(
            "加载免疫相关基因列表成功",
            path=str(xlsx_path),
            pos=len(pos),
            neg=len(neg),
            hyper=len(hyper),
        )
        return self._immune_gene_sets

    def _build_immuno_gene_summary(
        self,
        excel_data: ExcelDataSource,
        *,
        panel_package: Any = None,
    ) -> dict[str, str]:
        """生成免疫相关基因检出摘要（用于模板表格）。"""
        gene_sets = self._load_immune_gene_sets(panel_package=panel_package)
        if not gene_sets:
            return {
                "pos": "未检出",
                "neg": "未检出",
                "hyper": "未检出",
            }

        variations = excel_data.get_table_data("Variations") or []
        cnv_rows = excel_data.get_table_data("Cnv") or []
        membership_columns = self._panel_variant_membership_columns(panel_package)

        def belongs_to_panel(row: dict) -> bool:
            if not membership_columns:
                return True
            return any(row.get(column) in (1, "1", True) for column in membership_columns)

        def egfr_negative_match(row: dict) -> bool:
            haystack = " ".join(
                self._norm_text(row.get(key))
                for key in ("cHGVS", "pHGVS_S", "pHGVS_A", "pHGVS", "ExIn_ID")
            ).upper()
            return "L858R" in haystack or "EX19" in haystack or "19DEL" in haystack

        def egfr_amp_lines() -> list[str]:
            lines: list[str] = []
            for row in cnv_rows:
                gene = self._norm_text(row.get("Gene") or row.get("gene")).upper()
                if gene != "EGFR":
                    continue
                status = self._norm_text(
                    row.get("Cnvkit") or row.get("Status") or row.get("status")
                )
                if "扩增" in status or "AMP" in status.upper():
                    lines.append(f"EGFR：CNV:{status}")
            return lines

        def build(group: str) -> str:
            wanted = gene_sets.get(group, set())
            lines: list[str] = []
            seen: set[str] = set()
            for r in variations:
                if not belongs_to_panel(r):
                    continue
                level = self._norm_text(r.get("ExistIn552"))
                # 终版：仅使用Ⅰ/Ⅱ类突变进入免疫相关基因汇总
                if level not in {"Ⅰ类", "Ⅱ类"}:
                    continue
                gene = self._norm_text(
                    r.get("Gene_Symbol") or r.get("基因") or r.get("Gene")
                ).upper()
                if not gene or gene not in wanted or gene in seen:
                    continue
                if group == "neg" and gene == "EGFR" and not egfr_negative_match(r):
                    continue
                if group == "hyper" and gene == "EGFR":
                    continue
                c = self._norm_text(r.get("cHGVS"))
                p = self._norm_text(r.get("pHGVS_S") or r.get("pHGVS_A"))
                if not c:
                    continue
                line = f"{gene}：{c}，{p}" if p else f"{gene}：{c}"
                lines.append(line)
                seen.add(gene)

            if group == "hyper" and "EGFR" in wanted:
                for line in egfr_amp_lines():
                    if "EGFR" not in seen:
                        lines.append(line)
                        seen.add("EGFR")

            if not lines:
                return "未检出"
            return f"检出（{len(lines)}个）\n" + "\n".join(lines)

        return {"pos": build("pos"), "neg": build("neg"), "hyper": build("hyper")}
