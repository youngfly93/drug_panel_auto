"""Regression tests for the lung Part-3 cross-cancer safety boundary."""

from reportgen.core.qa_report import _build_business_checks
from reportgen.models.report_data import ReportData
from reportgen.rules.part3 import apply_part3_cross_cancer_policy

POLICY = {
    "cross_cancer_residual_scan": {
        "enabled": True,
        "scan_scope": "part3",
        "runtime_action": "suppress_unsafe_fields",
        "terms": ["结直肠癌", "colorectal"],
        "suppressed_text": "肺癌专属内容待报告组复核。",
    }
}


def test_part3_policy_suppresses_only_patient_visible_unsafe_fields():
    data = ReportData()
    data.set_table(
        "gene_knowledge_sections",
        [
            {
                "gene": "TP53",
                "variant_site": "c.1A>G",
                "intro": "该基因在结直肠癌中的历史说明。",
                "fixed_domain_text": "安全结构域。",
                "mutation_narrative": "肺癌专属变异说明。",
                "mutation_analysis": "安全结构域。肺癌专属变异说明。",
            },
            {
                "gene": "KRAS",
                "variant_site": "c.35G>A",
                "intro": "安全基因说明。",
                "fixed_domain_text": "安全结构域。",
                "mutation_narrative": "Historical colorectal narrative.",
                "mutation_analysis": "安全结构域。Historical colorectal narrative.",
            },
            {
                "gene": "ALK",
                "variant_site": "EML4-ALK",
                "intro": "安全基因说明。",
                "fixed_domain_text": "结直肠癌历史结构域说明。",
                "mutation_narrative": "肺癌专属融合说明。",
                "mutation_analysis": "结直肠癌历史结构域说明。肺癌专属融合说明。",
            },
        ],
    )
    data.set_table(
        "drug_analysis_sections",
        [
            {
                "gene": "KRAS",
                "variant_site": "c.35G>A",
                "drug": "SYNTHETIC-DRUG",
                "drug_type": "benefit",
                "relation": "结直肠癌历史药物关系。",
                "clinical": "肺癌专属临床说明。",
            }
        ],
    )

    result = apply_part3_cross_cancer_policy(data, POLICY)

    genes = data.get_table("gene_knowledge_sections")
    drugs = data.get_table("drug_analysis_sections")
    assert genes[0]["intro"] == "肺癌专属内容待报告组复核。"
    assert genes[0]["mutation_analysis"] == "安全结构域。肺癌专属变异说明。"
    assert genes[1]["mutation_analysis"] == "安全结构域。\n肺癌专属内容待报告组复核。"
    assert genes[1]["variant_site"] == "c.35G>A"
    assert genes[2]["fixed_domain_text"] == ""
    assert genes[2]["mutation_narrative"] == "肺癌专属融合说明。"
    assert genes[2]["mutation_analysis"] == (
        "肺癌专属内容待报告组复核。\n肺癌专属融合说明。"
    )
    assert drugs[0]["relation"] == "肺癌专属内容待报告组复核。"
    assert drugs[0]["clinical"] == "肺癌专属临床说明。"
    assert drugs[0]["drug"] == "SYNTHETIC-DRUG"
    assert data.get_table("drug_benefit_sections") == drugs
    assert result["suppressed_field_count"] == 6
    assert result["suppressed_row_count"] == 4


def test_part3_policy_leaves_safe_lung_narratives_unchanged():
    data = ReportData()
    original = {
        "gene": "EGFR",
        "intro": "EGFR是肺癌重要驱动基因。",
        "mutation_analysis": "该变异需结合肺癌临床背景复核。",
    }
    data.set_table("gene_knowledge_sections", [original])

    result = apply_part3_cross_cancer_policy(data, POLICY)

    assert data.get_table("gene_knowledge_sections") == [original]
    assert result["suppressed_field_count"] == 0


def test_cross_cancer_qa_scan_is_limited_to_rendered_part3():
    context = POLICY["cross_cancer_residual_scan"]
    report_context = {"part3_cross_cancer_residual_scan": context}

    appendix_only = _build_business_checks(
        "第三部分肺癌安全内容第四部分附录结直肠癌历史参考",
        report_context,
        "lung_588_pdl1",
        part3_compact_text="第三部分肺癌安全内容",
    )
    assert appendix_only["part3_cross_cancer_residuals"]["status"] == "PASS"

    actual_part3_leak = _build_business_checks(
        "第三部分结直肠癌历史内容",
        report_context,
        "lung_588_pdl1",
        part3_compact_text="第三部分结直肠癌历史内容",
    )
    assert actual_part3_leak["part3_cross_cancer_residuals"]["status"] == "WARN"
