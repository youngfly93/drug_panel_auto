# ruff: noqa: E402, I001
"""子宫内膜癌29 端到端崩溃测试(B-track draft)。

证明:用一份合成 Excel 走完整 ReportGenerator.generate(project_type=endometrial_29)
——核心生成链 + post-processor + QA sidecar 都不炸,产物 PII-clean,且换一个与
源病人(于雪梅:PTEN/CTNNB1/PIK3CA)完全不同的病例(TP53/ARID1A)时,产物里**不会
串出源病人的逐变异叙述**(中和有效)。

注:这是 draft 验证,不要求 qa_status=PASS(MSI 结论 / 第三部分叙述 / 表2列表行
仍需人工或 A-track 接线)。这是一个较慢的端到端测试(~30s,需 LibreOffice)。
"""
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 源病人禁忌:身份 + 阳性逐变异叙述(于雪梅 panel 的变异)
_BANNED = [
    "于雪梅", "250091", "LZ250091", "20250611", "20250624",
    "该样本检出PTEN", "该样本检出CTNNB1", "该样本检出PIK3CA",
    "c.900del", "c.98C>T", "c.1624G>A",
]


def _build_synthetic_excel(path: Path) -> Path:
    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    panel = "子宫内膜癌分子分型29基因检测"
    meta = pd.DataFrame([{
        "患者姓名": "端到端测试患者", "样本编号": "LZ888029", "报告编号": "MLJY-LZ888029",
        "性别": "女", "年龄": 61, "临床诊断": "子宫内膜癌", "肿瘤类型": "子宫内膜癌",
        "样本类型": "组织", "取材手段": "手术", "取材部位": "子宫", "项目名称": panel,
        "检测项目": panel, "送检日期": "2026-02-01", "报告日期": "2026-02-09",
        "检测方法": "NGS高通量测序"}])
    # 与源病人完全不同的基因 → 验证不串 seed
    variations = pd.DataFrame([
        {"Gene_Symbol": "TP53", "Transcript": "NM_000546.6", "Chr": "17", "ExIn_ID": "EX5",
         "cHGVS": "c.524G>A", "pHGVS_S": "p.R175H", "Freq(%)": 44.1, "Function": "Missense",
         "ExistIn552": "Ⅱ类", "CLNSIG": "Pathogenic"},
        {"Gene_Symbol": "ARID1A", "Transcript": "NM_006015.6", "Chr": "1", "ExIn_ID": "EX20",
         "cHGVS": "c.6139del", "pHGVS_S": "p.D2047fs", "Freq(%)": 33.3, "Function": "Frameshift",
         "ExistIn552": "Ⅱ类", "CLNSIG": "Pathogenic"}])
    msisensor = pd.DataFrame(
        [["control", 1000, 3, 0.3, "MSS"], ["tumor", 1000, 220, 22.0, "MSI-H"]],
        columns=["Sample", "Total", "Unstable", "Percent", "Status"])
    qc = pd.DataFrame([["Q30", 96.0], ["Coverage", 99.0],
                       ["Average sequencing depth", 1500], ["Insert", 180]])
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        meta.to_excel(w, sheet_name="Meta", index=False)
        variations.to_excel(w, sheet_name="Variations", index=False)
        msisensor.to_excel(w, sheet_name="Msisensor", index=False)
        qc.to_excel(w, sheet_name="QC", index=False, header=False)
    return path


@pytest.mark.slow
def test_endometrial29_end_to_end_generation(tmp_path):
    from reportgen.core.report_generator import ReportGenerator

    panel = "子宫内膜癌分子分型29基因检测"
    xlsx = _build_synthetic_excel(tmp_path / "endo_synth.xlsx")
    template = (
        ROOT / "panels" / "endometrial_29" / "templates"
        / "endometrial_29_golden_template_v0.docx"
    )
    out_dir = tmp_path / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    gen = ReportGenerator(
        config_dir=str(ROOT / "config"), template_dir=str(ROOT / "templates"),
        log_level="ERROR",
    )
    # 不抛异常即"管路不炸"。strict_mode/contract=warn 以容忍 draft 未接线区。
    result = gen.generate(
        excel_file=str(xlsx), template_file=str(template), output_dir=str(out_dir),
        output_filename="endo_e2e.docx", strict_mode=False, return_context=True,
        template_contract_mode="warn", project_type="endometrial_29", project_name=panel,
    )

    out_file = result.get("output_file")
    assert out_file and Path(out_file).exists(), f"未产出 docx: {result.get('errors')}"

    with zipfile.ZipFile(out_file) as z:
        blob = "\n".join(
            z.read(n).decode("utf-8", "ignore")
            for n in z.namelist() if n.endswith((".xml", ".rels"))
        )
    leaked = {tok: blob.count(tok) for tok in _BANNED if tok in blob}
    assert not leaked, f"端到端产物泄漏源病人内容: {leaked}"
    # 合成病人标量确实进入产物(标量链路通)
    assert "端到端测试患者" in blob


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
