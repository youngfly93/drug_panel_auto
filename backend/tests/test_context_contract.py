import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from reportgen.core.context_contract import (  # noqa: E402
    assert_context_contract,
    check_context_contract,
    load_context_contract,
    write_context_contract_report,
)
from reportgen.panels.loader import load_panel_package  # noqa: E402
from reportgen.panels.validation import validate_panel_package  # noqa: E402


def _reviewed_low_tmb_context():
    return {
        "total_variants_count": 8,
        "drug_related_count": 4,
        "tmb_value": "6.5",
        "tmb_status": "L",
        "tmb_summary": "6.5mutations/Mb，TMB-L\n(本次检测结果低于参考值\n10 mutations/Mb)",
        "tmb_detail_sentence": "在本次检测范围内，该样本肿瘤突变负荷为6.5 mutations/Mb，TMB水平较低。",
        "tmb_detail_interpretation": (
            "肿瘤突变负荷（Tumor Mutation Burden，TMB）即肿瘤基因组去除胚系突变后的"
            "体细胞突变数量。2020年6月，FDA批准帕博利珠单抗用于治疗组织肿瘤突变"
            "负荷高且既往治疗后病情进展且无满意替代治疗方案的实体瘤患者。"
        ),
        "tmb_drug_note": "常用的免疫抑制剂有：帕博利珠单抗、纳武利尤单抗等。",
        "msi_status": "MSS",
        "msi_summary": "微卫星稳定型，MSS",
        "immuno_tips": "多项临床研究表明，TMB-H的肿瘤对免疫检查点抑制剂有更强的免疫应答效果\n常用免疫抑制剂有：#帕博利珠单抗等",
        "msi_tips": "研究表明，MSI-H的实体瘤通常具有免疫原性和广泛的T细胞浸润性，从而对免疫检查点抑制剂的治疗响应较高",
        "nccn_KRAS_EX2": "c.34G>A，p.G12S",
        "nccn_FGFR123_MUT": "未检出",
        "imm_pos_KRAS": "c.34G>A，p.G12S",
        "imm_pos_POLE": "未检出有害变异",
        "imm_neg_ALK": "未检出有害变异",
        "imm_pos_DDR": "ATM：c.6874C>T，p.Q2292*",
        "variants": [{"gene": f"GENE{i}"} for i in range(8)],
        "chemotherapy": [{"Drug": f"drug{i}"} for i in range(7)],
        "targeted_drug_tips": [
            {"gene": "TP53"},
            {"gene": "KRAS"},
            {"gene": "SETD2"},
            {"gene": "ATM"},
        ],
        "variants_2_1": [
            {"gene": "TP53", "locus": "c.844C>T,\np.R282W"},
            {"gene": "KRAS", "locus": "c.34G>A,\np.G12S"},
            {"gene": "APC", "locus": "c.4348C>T,\np.R1450*"},
            {"gene": "APC", "locus": "c.2387_2388del,\np.Y796Wfs*2"},
            {"gene": "SETD2", "locus": "c.4930G>T,\np.G1644*"},
            {"gene": "ATM", "locus": "c.6874C>T,\np.Q2292*"},
            {"gene": "BRAF", "locus": "未见突变"},
            {"gene": "FBXW7", "locus": "未见突变"},
        ],
        "nccn_results": [
            {"key": "KRAS_EX2", "gene": "KRAS", "result": "c.34G>A，p.G12S"},
            {"key": "FGFR123_MUT", "gene": "FGFR1/FGFR2/FGFR3", "result": "未检出"},
            *[
                {"key": f"NCCN_FILLER_{i}", "gene": f"GENE{i}", "result": "未检出"}
                for i in range(30)
            ],
        ],
        "immune_positive_results": [
            {"key": "KRAS", "gene": "KRAS", "result": "c.34G>A，p.G12S"},
            {"key": "DDR", "gene": "DDR相关基因", "result": "ATM：c.6874C>T，p.Q2292*"},
            *[
                {"key": f"IMM_POS_FILLER_{i}", "gene": f"GENE{i}", "result": "未检出有害变异"}
                for i in range(13)
            ],
        ],
        "immune_negative_results": [
            {"key": "ALK", "gene": "ALK", "result": "未检出有害变异"},
            *[
                {"key": f"IMM_NEG_FILLER_{i}", "gene": f"GENE{i}", "result": "未检出有害变异"}
                for i in range(11)
            ],
        ],
        "immune_hyperprogression_results": [
            {"key": f"IMM_HYPER_FILLER_{i}", "gene": f"GENE{i}", "result": "未检出有害变异"}
            for i in range(8)
        ],
    }


def test_context_contract_checks_fields_and_rows():
    contract = {
        "severity_default": "fail",
        "fields": {
            "total_variants_count": {"equals": 8},
            "tmb_summary": {
                "contains": ["6.5", "TMB-L"],
                "not_contains": "13.5",
            },
        },
        "tables": {
            "targeted_drug_tips": {
                "row_count": 4,
                "forbid_rows": [{"match": {"gene": {"equals": "FBXW7"}}}],
            },
            "variants_2_1": {
                "rows": [
                    {
                        "id": "kras",
                        "match": {"gene": {"equals": "KRAS"}},
                        "contains": {"locus": ["c.34G>A", "p.G12S"]},
                    }
                ]
            },
        },
    }

    report = check_context_contract(_reviewed_low_tmb_context(), contract)

    assert report["status"] == "PASS"
    assert report["summary"]["fail"] == 0


def test_context_contract_fails_on_known_crc358_regressions():
    package = load_panel_package("crc_358_msi", project_root=ROOT)
    contract_path = package.resolve_context_contract_file("reviewed_low_tmb_mss")
    contract = load_context_contract(contract_path)
    context = _reviewed_low_tmb_context()
    context["tmb_summary"] = "13.5 mutations/Mb，TMB-H"
    context["nccn_FGFR123_MUT"] = "c.788C>T，p.P263L"
    context["targeted_drug_tips"].append({"gene": "FBXW7"})

    report = check_context_contract(context, contract, contract_path=contract_path)
    failed_ids = {item["id"] for item in report["checks"] if item["status"] == "FAIL"}

    assert report["status"] == "FAIL"
    assert "field:tmb_summary" in failed_ids
    assert "field:nccn_FGFR123_MUT" in failed_ids
    assert "table:targeted_drug_tips:forbid_row:fbxw7_class_iii_must_not_trigger_drug" in failed_ids


def test_crc358_context_contract_is_declared_and_passes_synthetic_context(tmp_path):
    package = load_panel_package("crc_358_msi", project_root=ROOT)
    contract_path = package.resolve_context_contract_file("reviewed_low_tmb_mss")
    contract = load_context_contract(contract_path)

    report = assert_context_contract(
        _reviewed_low_tmb_context(),
        contract,
        contract_path=contract_path,
    )
    output = tmp_path / "context_contract_report.json"
    write_context_contract_report(report, output)

    assert report["status"] == "PASS"
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "PASS"

    validation = validate_panel_package("crc_358_msi", project_root=ROOT)
    assert validation.ok, validation.to_dict()
