# ruff: noqa: E402, I001
"""肺癌329+PD-L1 panel（Phase C-alpha MVP）冒烟 + PII 防回归。

模板是从一份真实终版报告变量化/中和而来。本测试守护两件事：
1. 模板 PII-clean——绝不能含源病人(曹淑珍/lz240779)任何标识；
2. panel 注册 + docxtpl 可渲染（端到端管路对肺329 成立）。

注：MVP 阶段模板只变量化了高置信标量；per-variant 解析 / PGx / 复用表循环
等留到 C-beta，当前为"中和留空"。
"""

import re
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEMPLATE = (
    ROOT
    / "panels"
    / "lung_329_pdl1"
    / "templates"
    / "lung_329_pdl1_golden_template_v0.docx"
)

# 源病人禁忌 token——模板里出现任何一个都视为 PII 泄漏
_BANNED_PII_TOKENS = ["曹淑珍", "240779", "LZ240779", "lz240779", "Lz240779"]

_MVP_SCALARS = [
    "patient_name",
    "sample_id",
    "gender",
    "age",
    "clinical_diagnosis",
    "sample_type",
    "sampling_method",
    "sample_site",
    "tmb_summary",
    "msi_summary",
    "pdl1_tps",
    "pdl1_cps",
    "pdl1_result",
    "immune_positive_result",
    "immune_negative_result",
    "immune_hyperprogression_result",
]


def test_lung329_template_exists():
    assert TEMPLATE.exists(), f"肺329模板缺失: {TEMPLATE}"


def test_lung329_template_is_pii_clean():
    """跨所有 xml 部件（含 customXml/页眉页脚）扫描，禁忌 token 必须零出现。"""
    with zipfile.ZipFile(TEMPLATE) as z:
        parts = [n for n in z.namelist() if n.endswith((".xml", ".rels"))]
        blob = "\n".join(z.read(n).decode("utf-8", "ignore") for n in parts)
    found = {tok: blob.count(tok) for tok in _BANNED_PII_TOKENS if tok in blob}
    assert not found, f"模板含源病人 PII: {found}"


def test_lung329_panel_registers():
    from reportgen.core.enhancer_registry import get_panel_registry

    reg = get_panel_registry()
    assert reg.get("lung_329_pdl1") is not None, "lung_329_pdl1 未注册"


def test_lung329_template_renders_with_scalars():
    """docxtpl 用 MVP 标量 context 渲染，不报错且产物仍 PII-clean。"""
    from docxtpl import DocxTemplate

    tpl = DocxTemplate(str(TEMPLATE))
    # 用不含尖括号的哨兵值（避免被 XML 去标签正则误删）
    ctx = {k: f"SENTINEL_{k}_VAL" for k in _MVP_SCALARS}
    tpl.render(ctx)

    # 渲染产物落盘到内存并复扫 PII
    import io

    buf = io.BytesIO()
    tpl.save(buf)
    buf.seek(0)
    with zipfile.ZipFile(buf) as z:
        doc = z.read("word/document.xml").decode("utf-8", "ignore")
    visible = re.sub(r"<[^>]+>", "", doc)
    for tok in _BANNED_PII_TOKENS:
        assert tok not in visible, f"渲染产物含 PII: {tok}"
    # 绑定值确实进入了文档
    assert "SENTINEL_patient_name_VAL" in visible
    assert "SENTINEL_pdl1_result_VAL" in visible
