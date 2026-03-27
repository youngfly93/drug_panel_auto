"""
Immune-related gene list helpers for FieldMapper.

Separated from field_mapper.py to keep FieldMapper focused on orchestration.
We keep method names as FieldMapper internals for backward compatibility.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from reportgen.models.excel_data import ExcelDataSource


class ImmuneGeneMixin:
    def _load_immune_gene_sets(self) -> dict[str, set[str]]:
        """加载免疫相关基因列表（正相关/负相关/超进展相关）。

        期望的xlsx结构示例见 `2025.12.12/1-免疫治疗相关基因.xlsx`：
        - 前3列：免疫治疗正相关基因（可能跨多列排版）
        - 中间3列：免疫治疗负相关基因
        - 后2列：免疫超进展相关基因（可能带备注列）
        """
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
                    if not s or s == "基因":
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

    def _build_immuno_gene_summary(self, excel_data: ExcelDataSource) -> dict[str, str]:
        """生成免疫相关基因检出摘要（用于模板表格）。"""
        gene_sets = self._load_immune_gene_sets()
        if not gene_sets:
            return {
                "pos": "未检出",
                "neg": "未检出",
                "hyper": "未检出",
            }

        variations = excel_data.get_table_data("Variations") or []

        def build(group: str) -> str:
            wanted = gene_sets.get(group, set())
            lines: list[str] = []
            seen: set[str] = set()
            for r in variations:
                level = self._norm_text(r.get("ExistIn552"))
                # 终版：仅使用Ⅰ/Ⅱ类突变进入免疫相关基因汇总
                if level not in {"Ⅰ类", "Ⅱ类"}:
                    continue
                gene = self._norm_text(
                    r.get("Gene_Symbol") or r.get("基因") or r.get("Gene")
                ).upper()
                if not gene or gene not in wanted or gene in seen:
                    continue
                c = self._norm_text(r.get("cHGVS"))
                p = self._norm_text(r.get("pHGVS_S") or r.get("pHGVS_A"))
                if not c:
                    continue
                line = f"{gene}：{c}，{p}" if p else f"{gene}：{c}"
                lines.append(line)
                seen.add(gene)

            if not lines:
                return "未检出"
            return f"检出（{len(lines)}个）\n" + "\n".join(lines)

        return {"pos": build("pos"), "neg": build("neg"), "hyper": build("hyper")}
