"""
位点描述自动生成器

根据c.HGVS和p.HGVS格式自动生成基因变异说明文本。
支持的突变类型：
- 错义突变 (Missense): c.844C>T, p.R282W
- 无义突变 (Nonsense): c.4348C>T, p.R1450*
- 移码突变 (Frameshift): c.2387_2388del, p.Y796Wfs*2
- 剪接突变 (Splice): c.153+2T>C
- 框内缺失/插入 (Inframe): c.2235_2249del, p.E746_A750del

Python 3.9 compatible.
"""

import re
from typing import Any, Dict, Optional, Tuple

# 氨基酸单字母到中文名称映射
AMINO_ACID_NAMES: Dict[str, str] = {
    "A": "丙氨酸",
    "R": "精氨酸",
    "N": "天冬酰胺",
    "D": "天冬氨酸",
    "C": "半胱氨酸",
    "E": "谷氨酸",
    "Q": "谷氨酰胺",
    "G": "甘氨酸",
    "H": "组氨酸",
    "I": "异亮氨酸",
    "L": "亮氨酸",
    "K": "赖氨酸",
    "M": "甲硫氨酸",
    "F": "苯丙氨酸",
    "P": "脯氨酸",
    "S": "丝氨酸",
    "T": "苏氨酸",
    "W": "色氨酸",
    "Y": "酪氨酸",
    "V": "缬氨酸",
    "*": "终止密码子",
    "X": "未知氨基酸",
}

# 核苷酸中文名称
NUCLEOTIDE_NAMES: Dict[str, str] = {
    "A": "A",
    "T": "T",
    "C": "C",
    "G": "G",
}


class MutationDescriptionGenerator:
    """位点描述自动生成器"""

    def __init__(self):
        """初始化生成器"""
        pass

    def generate(
        self,
        gene: str,
        c_hgvs: str,
        p_hgvs: str,
        frequency: float,
        mutation_type: Optional[str] = None,
    ) -> str:
        """
        生成基因变异说明文本。

        Args:
            gene: 基因名称
            c_hgvs: cDNA变异描述 (如 c.844C>T)
            p_hgvs: 蛋白变异描述 (如 p.R282W)
            frequency: 突变频率 (%)
            mutation_type: 突变类型 (可选，如 Missense, Nonsense等)

        Returns:
            中文变异说明文本
        """
        if not c_hgvs:
            return ""

        # 确保 frequency 是 float
        if frequency is not None and not isinstance(frequency, (int, float)):
            try:
                frequency = float(frequency)
            except (ValueError, TypeError):
                frequency = 0.0

        # 自动推断突变类型
        if not mutation_type:
            mutation_type = self._infer_mutation_type(c_hgvs, p_hgvs)

        # 根据突变类型生成描述
        if mutation_type in ("Missense", "错义突变"):
            return self._generate_missense_desc(gene, c_hgvs, p_hgvs, frequency)
        elif mutation_type in ("Nonsense", "无义突变", "Stop_gain"):
            return self._generate_nonsense_desc(gene, c_hgvs, p_hgvs, frequency)
        elif mutation_type in ("Frameshift", "CDS-indel", "移码突变"):
            return self._generate_frameshift_desc(gene, c_hgvs, p_hgvs, frequency)
        elif mutation_type in ("Splice-5", "Splice-3", "Splice", "剪接突变"):
            return self._generate_splice_desc(gene, c_hgvs, frequency)
        elif mutation_type in ("Inframe", "框内突变"):
            return self._generate_inframe_desc(gene, c_hgvs, p_hgvs, frequency)
        else:
            # 默认：通用描述
            return self._generate_generic_desc(gene, c_hgvs, p_hgvs, frequency)

    def _infer_mutation_type(self, c_hgvs: str, p_hgvs: str) -> str:
        """根据HGVS格式推断突变类型"""
        c = c_hgvs.lower() if c_hgvs else ""
        p = p_hgvs if p_hgvs else ""

        # 剪接突变: c.153+2T>C 或 c.154-1G>A
        if re.search(r"[+-]\d+[ATCG]>[ATCG]", c_hgvs, re.I):
            return "Splice"

        # 无义突变: p.R1450* (终止密码子)
        if p.endswith("*") and "fs" not in p.lower():
            return "Nonsense"

        # 移码突变: p.Y796Wfs*2 (包含fs)
        if "fs" in p.lower():
            return "Frameshift"

        # 缺失或插入
        if "del" in c and "ins" in c:
            return "Frameshift" if "fs" in p.lower() else "Inframe"
        if "del" in c or "ins" in c or "dup" in c:
            if "fs" in p.lower():
                return "Frameshift"
            return "Inframe"

        # 点突变（替换）
        if ">" in c_hgvs:
            if p.endswith("*"):
                return "Nonsense"
            return "Missense"

        return "Unknown"

    def _parse_c_hgvs(self, c_hgvs: str) -> Dict[str, Any]:
        """解析 c.HGVS，供测试/调试使用（内部方法）。

        兼容常见格式：
          - 替换: c.844C>T
          - 缺失: c.1234delA, c.2235_2249del
          - 插入: c.1234_1235insATG
          - 重复: c.1234dupA
          - delins: c.1234_1236delinsATG
        """
        s = (c_hgvs or "").strip()
        if not s:
            return {"position": "", "variant_type": "unknown"}

        # substitution: c.844C>T
        m = re.match(r"c\.(\d+)([ATCG])>([ATCG])$", s, re.I)
        if m:
            return {
                "position": m.group(1),
                "ref": m.group(2).upper(),
                "alt": m.group(3).upper(),
                "variant_type": "substitution",
            }

        # delins: c.1234_1236delinsATG
        m = re.match(r"c\.(\d+)_(\d+)delins([ATCG]+)$", s, re.I)
        if m:
            return {
                "position": f"{m.group(1)}_{m.group(2)}",
                "alt": m.group(3).upper(),
                "variant_type": "delins",
            }

        # insertion: c.1234_1235insATG
        m = re.match(r"c\.(\d+)_(\d+)ins([ATCG]+)$", s, re.I)
        if m:
            return {
                "position": f"{m.group(1)}_{m.group(2)}",
                "alt": m.group(3).upper(),
                "variant_type": "insertion",
            }

        # deletion: c.1234delA or c.2235_2249del
        m = re.match(r"c\.(\d+)(?:_(\d+))?del([ATCG]+)?$", s, re.I)
        if m:
            pos = m.group(1) if not m.group(2) else f"{m.group(1)}_{m.group(2)}"
            return {
                "position": pos if "_" not in pos else m.group(1),
                "variant_type": "deletion",
            }

        # duplication: c.1234dupA
        m = re.match(r"c\.(\d+)(?:_(\d+))?dup([ATCG]+)?$", s, re.I)
        if m:
            pos = m.group(1) if not m.group(2) else f"{m.group(1)}_{m.group(2)}"
            return {
                "position": pos if "_" not in pos else m.group(1),
                "variant_type": "duplication",
            }

        return {"position": "", "variant_type": "unknown"}

    def _parse_p_hgvs(self, p_hgvs: str) -> Dict[str, Any]:
        """解析 p.HGVS，供测试/调试使用（内部方法）。"""
        s = (p_hgvs or "").strip()
        if not s:
            return {"position": "", "mutation_type": "unknown"}

        # frameshift: p.L300fs / p.Leu300fs
        m = re.match(r"p\.([A-Z])(\d+)fs", s, re.I)
        if m:
            return {
                "position": m.group(2),
                "ref_aa": m.group(1).upper(),
                "alt_aa": "",
                "mutation_type": "frameshift",
            }

        # missense/nonsense: p.R282W / p.R282*
        parsed = self._parse_p_hgvs_substitution(s)
        if parsed:
            ref, pos, alt = parsed
            mutation_type = "nonsense" if alt == "*" else "missense"
            return {
                "position": str(pos),
                "ref_aa": ref,
                "alt_aa": alt,
                "mutation_type": mutation_type,
            }

        return {"position": "", "mutation_type": "unknown"}

    def _parse_c_hgvs_substitution(self, c_hgvs: str) -> Optional[Tuple[int, str, str]]:
        """
        解析cDNA替换变异: c.844C>T

        Returns:
            (位置, 原始核苷酸, 突变核苷酸) 或 None
        """
        # 匹配 c.844C>T 格式
        match = re.match(r"c\.(\d+)([ATCG])>([ATCG])", c_hgvs, re.I)
        if match:
            pos = int(match.group(1))
            ref = match.group(2).upper()
            alt = match.group(3).upper()
            return (pos, ref, alt)
        return None

    def _parse_p_hgvs_substitution(self, p_hgvs: str) -> Optional[Tuple[str, int, str]]:
        """
        解析蛋白替换变异: p.R282W

        Returns:
            (原始氨基酸, 位置, 突变氨基酸) 或 None
        """
        # 匹配 p.R282W 或 p.Arg282Trp 格式
        match = re.match(r"p\.([A-Z\*])(\d+)([A-Z\*])", p_hgvs, re.I)
        if match:
            ref = match.group(1).upper()
            pos = int(match.group(2))
            alt = match.group(3).upper()
            return (ref, pos, alt)

        # 尝试匹配三字母格式: p.Arg282Trp
        match = re.match(r"p\.([A-Za-z]{3})(\d+)([A-Za-z]{3}|\*)", p_hgvs)
        if match:
            ref = self._three_to_one(match.group(1))
            pos = int(match.group(2))
            alt = self._three_to_one(match.group(3))
            if ref and alt:
                return (ref, pos, alt)

        return None

    def _three_to_one(self, three_letter: str) -> Optional[str]:
        """三字母氨基酸代码转单字母"""
        mapping = {
            "Ala": "A",
            "Arg": "R",
            "Asn": "N",
            "Asp": "D",
            "Cys": "C",
            "Glu": "E",
            "Gln": "Q",
            "Gly": "G",
            "His": "H",
            "Ile": "I",
            "Leu": "L",
            "Lys": "K",
            "Met": "M",
            "Phe": "F",
            "Pro": "P",
            "Ser": "S",
            "Thr": "T",
            "Trp": "W",
            "Tyr": "Y",
            "Val": "V",
            "Ter": "*",
            "*": "*",
        }
        return mapping.get(three_letter.capitalize())

    def _get_aa_name(self, code: str) -> str:
        """获取氨基酸中文名称"""
        return AMINO_ACID_NAMES.get(code.upper(), code)

    def _generate_missense_desc(
        self, gene: str, c_hgvs: str, p_hgvs: str, frequency: float
    ) -> str:
        """生成错义突变描述"""
        c_parsed = self._parse_c_hgvs_substitution(c_hgvs)
        p_parsed = self._parse_p_hgvs_substitution(p_hgvs)

        if c_parsed and p_parsed:
            c_pos, c_ref, c_alt = c_parsed
            p_ref, p_pos, p_alt = p_parsed
            ref_aa_name = self._get_aa_name(p_ref)
            alt_aa_name = self._get_aa_name(p_alt)

            return (
                f"该样本检出{gene}基因{c_hgvs}，{p_hgvs}错义突变，"
                f"第{c_pos}位核苷酸由{c_ref}突变为{c_alt}，"
                f"导致相应蛋白序列中第{p_pos}位氨基酸由{ref_aa_name}突变为{alt_aa_name}，"
                f"此突变在样本中的突变丰度为{frequency:.2f}%。"
            )

        # 回退到通用格式
        return self._generate_generic_desc(gene, c_hgvs, p_hgvs, frequency)

    def _generate_nonsense_desc(
        self, gene: str, c_hgvs: str, p_hgvs: str, frequency: float
    ) -> str:
        """生成无义突变描述"""
        c_parsed = self._parse_c_hgvs_substitution(c_hgvs)
        p_parsed = self._parse_p_hgvs_substitution(p_hgvs)

        if c_parsed and p_parsed:
            c_pos, c_ref, c_alt = c_parsed
            p_ref, p_pos, p_alt = p_parsed
            ref_aa_name = self._get_aa_name(p_ref)

            return (
                f"该样本检出{gene}基因{c_hgvs}，{p_hgvs}无义突变，"
                f"第{c_pos}位核苷酸由{c_ref}突变为{c_alt}，"
                f"导致相应蛋白序列中第{p_pos}位氨基酸由{ref_aa_name}突变为终止密码子，"
                f"此突变在样本中的突变丰度为{frequency:.2f}%。"
            )

        return self._generate_generic_desc(gene, c_hgvs, p_hgvs, frequency)

    def _generate_frameshift_desc(
        self, gene: str, c_hgvs: str, p_hgvs: str, frequency: float
    ) -> str:
        """生成移码突变描述"""
        # 解析 c.2387_2388del 格式
        del_match = re.match(r"c\.(\d+)_(\d+)del", c_hgvs, re.I)
        ins_match = re.match(r"c\.(\d+)_(\d+)ins([ATCG]+)", c_hgvs, re.I)
        dup_match = re.match(r"c\.(\d+)(?:_(\d+))?dup", c_hgvs, re.I)

        # 解析 p.Y796Wfs*2 格式
        fs_match = re.match(r"p\.([A-Z])(\d+)([A-Z])fs\*(\d+)", p_hgvs, re.I)
        # 解析更简化的 p.L300fs / p.L1795fs 格式（无终止位点信息）
        fs_simple_match = re.match(r"p\.([A-Z])(\d+)fs", p_hgvs, re.I)

        if del_match and fs_match:
            c_start, c_end = int(del_match.group(1)), int(del_match.group(2))
            p_ref, p_pos, p_alt, fs_len = (
                fs_match.group(1).upper(),
                int(fs_match.group(2)),
                fs_match.group(3).upper(),
                int(fs_match.group(4)),
            )
            ref_aa_name = self._get_aa_name(p_ref)
            alt_aa_name = self._get_aa_name(p_alt)

            return (
                f"该样本检出{gene}基因{c_hgvs}，{p_hgvs}碱基缺失引起的移码突变，"
                f"第{c_start}位至第{c_end}位核苷酸缺失，"
                f"导致相应蛋白序列中第{p_pos}位氨基酸由{ref_aa_name}突变为{alt_aa_name}，"
                f"并开始发生移码，于此后第{fs_len}位氨基酸处翻译终止，"
                f"此突变在样本中的突变丰度为{frequency:.2f}%。"
            )

        if ins_match and fs_match:
            c_start, c_end = int(ins_match.group(1)), int(ins_match.group(2))
            inserted = ins_match.group(3)
            p_ref, p_pos, p_alt, fs_len = (
                fs_match.group(1).upper(),
                int(fs_match.group(2)),
                fs_match.group(3).upper(),
                int(fs_match.group(4)),
            )
            ref_aa_name = self._get_aa_name(p_ref)
            alt_aa_name = self._get_aa_name(p_alt)

            return (
                f"该样本检出{gene}基因{c_hgvs}，{p_hgvs}碱基插入引起的移码突变，"
                f"第{c_start}位与第{c_end}位核苷酸之间插入{inserted}，"
                f"导致相应蛋白序列中第{p_pos}位氨基酸由{ref_aa_name}突变为{alt_aa_name}，"
                f"并开始发生移码，于此后第{fs_len}位氨基酸处翻译终止，"
                f"此突变在样本中的突变丰度为{frequency:.2f}%。"
            )

        if dup_match and fs_match:
            c_start = int(dup_match.group(1))
            c_end = int(dup_match.group(2)) if dup_match.group(2) else c_start
            p_ref, p_pos, p_alt, fs_len = (
                fs_match.group(1).upper(),
                int(fs_match.group(2)),
                fs_match.group(3).upper(),
                int(fs_match.group(4)),
            )
            ref_aa_name = self._get_aa_name(p_ref)
            alt_aa_name = self._get_aa_name(p_alt)

            return (
                f"该样本检出{gene}基因{c_hgvs}，{p_hgvs}碱基重复引起的移码突变，"
                f"第{c_start}位至第{c_end}位核苷酸发生重复，"
                f"导致相应蛋白序列中第{p_pos}位氨基酸由{ref_aa_name}突变为{alt_aa_name}，"
                f"并开始发生移码，于此后第{fs_len}位氨基酸处翻译终止，"
                f"此突变在样本中的突变丰度为{frequency:.2f}%。"
            )

        if fs_simple_match:
            # 仅保证“移码”语义存在，详细机制信息不足时用通用描述。
            return (
                f"该样本检出{gene}基因{c_hgvs}，{p_hgvs}移码突变，"
                f"此突变在样本中的突变丰度为{frequency:.2f}%。"
            )

        return self._generate_generic_desc(gene, c_hgvs, p_hgvs, frequency)

    def _generate_splice_desc(self, gene: str, c_hgvs: str, frequency: float) -> str:
        """生成剪接突变描述"""
        # 解析 c.153+2T>C 或 c.154-1G>A 格式
        match = re.match(r"c\.(\d+)([+-])(\d+)([ATCG])>([ATCG])", c_hgvs, re.I)

        if match:
            exon_pos = int(match.group(1))
            direction = match.group(2)
            offset = int(match.group(3))
            ref = match.group(4).upper()
            alt = match.group(5).upper()

            if direction == "+":
                position_desc = f"第{exon_pos}位核苷酸下游第{offset}位"
            else:
                position_desc = f"第{exon_pos}位核苷酸上游第{offset}位"

            return (
                f"该样本检出{gene}基因{c_hgvs}剪接突变，"
                f"{position_desc}核苷酸由{ref}突变为{alt}，"
                f"此突变在样本中的突变丰度为{frequency:.2f}%。"
            )

        return f"该样本检出{gene}基因{c_hgvs}剪接突变，此突变在样本中的突变丰度为{frequency:.2f}%。"

    def _generate_inframe_desc(
        self, gene: str, c_hgvs: str, p_hgvs: str, frequency: float
    ) -> str:
        """生成框内突变描述"""
        # 解析 c.2235_2249del, p.E746_A750del 格式
        c_del_match = re.match(r"c\.(\d+)_(\d+)del", c_hgvs, re.I)
        p_del_match = re.match(r"p\.([A-Z])(\d+)_([A-Z])(\d+)del", p_hgvs, re.I)

        if c_del_match and p_del_match:
            c_start, c_end = int(c_del_match.group(1)), int(c_del_match.group(2))
            p_ref1, p_pos1 = p_del_match.group(1).upper(), int(p_del_match.group(2))
            p_ref2, p_pos2 = p_del_match.group(3).upper(), int(p_del_match.group(4))
            ref1_name = self._get_aa_name(p_ref1)
            ref2_name = self._get_aa_name(p_ref2)
            del_count = p_pos2 - p_pos1 + 1

            return (
                f"该样本检出{gene}基因{c_hgvs}，{p_hgvs}框内缺失突变，"
                f"第{c_start}位至第{c_end}位核苷酸缺失，"
                f"导致相应蛋白序列中第{p_pos1}位{ref1_name}至第{p_pos2}位{ref2_name}"
                f"共{del_count}个氨基酸缺失，"
                f"此突变在样本中的突变丰度为{frequency:.2f}%。"
            )

        return self._generate_generic_desc(gene, c_hgvs, p_hgvs, frequency)

    def _generate_generic_desc(
        self, gene: str, c_hgvs: str, p_hgvs: str, frequency: float
    ) -> str:
        """生成通用变异描述"""
        if p_hgvs and p_hgvs != "--" and p_hgvs != "*":
            return (
                f"该样本检出{gene}基因{c_hgvs}，{p_hgvs}突变，"
                f"此突变在样本中的突变丰度为{frequency:.2f}%。"
            )
        return (
            f"该样本检出{gene}基因{c_hgvs}突变，"
            f"此突变在样本中的突变丰度为{frequency:.2f}%。"
        )
