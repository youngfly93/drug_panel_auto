# ruff: noqa: E402, I001
"""子宫内膜癌分子分型29基因 panel（B-track MVP）冒烟 + PII 防回归。
模板是从一份真实终版报告变量化/中和而来。本测试守护两件事：
1. 模板 PII-clean——绝不能含源病人(于雪梅/lz250091/送检报告日期)任何标识；
2. panel 注册 + docxtpl 可渲染（端到端管路对子宫内膜29成立）。
注：MVP 阶段模板只变量化了高置信标量（身份/年龄/样本类型/诊断/MSI结果）；
per-variant 解析 / 药物表 / 遗传性肿瘤(胚系)段 / 逐变异叙述等留作可编辑样板，
全自动化(MSI-only 生物标志物、体细胞/胚系拆分、林奇综合征段、29基因列表)为 A-track。
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
    / "endometrial_29"
    / "templates"
    / "endometrial_29_golden_template_v0.docx"
)

# 源病人禁忌 token——模板/产物里出现任何一个都视为 PII 泄漏
_BANNED_PII_TOKENS = [
    "于雪梅",
    "250091",
    "LZ250091",
    "lz250091",
    "Lz250091",
    "20250611",  # 送检日期
    "20250624",  # 报告日期
]

# B-track MVP 变量化的标量（与 golden_template_v0_variables.yaml + seed 步对应）
_MVP_SCALARS = [
    "patient_name",
    "report_number",
    "receive_date",
    "report_date",
    "age",
    "sample_type",
    "clinical_diagnosis",
    "msi_result",
]


def test_endometrial29_template_exists():
    assert TEMPLATE.exists(), f"子宫内膜29模板缺失: {TEMPLATE}"


def test_endometrial29_template_is_pii_clean():
    """跨所有 xml 部件（含 customXml/页眉页脚）扫描，禁忌 token 必须零出现。"""
    with zipfile.ZipFile(TEMPLATE) as z:
        parts = [n for n in z.namelist() if n.endswith((".xml", ".rels"))]
        blob = "\n".join(z.read(n).decode("utf-8", "ignore") for n in parts)
    found = {tok: blob.count(tok) for tok in _BANNED_PII_TOKENS if tok in blob}
    assert not found, f"模板含源病人 PII: {found}"


def test_endometrial29_panel_registers():
    from reportgen.core.enhancer_registry import get_panel_registry

    reg = get_panel_registry()
    assert reg.get("endometrial_29") is not None, "endometrial_29 未注册"


def test_endometrial29_project_detection():
    """panel 的 project_detector_rules 关键词应让检测器命中 endometrial_29。"""
    from reportgen.core.project_detector import ProjectDetector

    det = ProjectDetector(config_dir=str(ROOT / "config"))
    res = det.detect("某患者-子宫内膜癌分子分型29基因检测-终版.xlsx", None)
    assert res.get("project_type") == "endometrial_29", res


def test_endometrial29_template_renders_with_scalars():
    """docxtpl 用 MVP 标量 context 渲染，不报错且产物仍 PII-clean。"""
    from docxtpl import DocxTemplate

    tpl = DocxTemplate(str(TEMPLATE))
    # 用不含尖括号的哨兵值（避免被 XML 去标签正则误删）
    ctx = {k: f"SENTINEL_{k}_VAL" for k in _MVP_SCALARS}
    tpl.render(ctx)

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
    assert "SENTINEL_msi_result_VAL" in visible


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
