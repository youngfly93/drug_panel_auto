from scripts.build_crc358_knowledge_buildout import (
    classify_product_family,
    dedupe_candidates,
    extract_candidates_from_paragraphs,
    parse_variant_heading,
)
from scripts.preapprove_crc358_candidates import should_preapprove
from scripts.promote_crc358_reviewed_candidates import build_overlay
from scripts.merge_reviewed_part3_overlays import merge
from scripts.build_crc358_targeted_priority_pack import (
    build_drug_override_snippet,
    build_part3_overlay,
)
from scripts.prepare_crc358_targeted_priority_promotion import (
    merge_crc_rules,
    merge_part3,
)


def test_classify_crc358_msi_final_report_name():
    product, label, has_msi, is_final = classify_product_family(
        "苏雨起-乙状结肠癌-结直肠癌358基因+msi-mljy-lz258792-终版.docx"
    )
    assert product == "crc_358_msi"
    assert label == "结直肠癌358基因+MSI"
    assert has_msi is True
    assert is_final is True


def test_parse_variant_heading_extracts_gene_hgvs_and_frequency():
    ctx = parse_variant_heading("u TP53：c.821T>A，p.V274D；35.08%")
    assert ctx is not None
    assert ctx.gene == "TP53"
    assert ctx.c_hgvs == "c.821T>A"
    assert ctx.p_hgvs == "p.V274D"
    assert ctx.frequency == "35.08%"


def test_extract_part3_gene_and_drug_candidates_from_paragraphs():
    paragraphs = [
        "封面",
        "第三部分：基因变异及相应靶向/免疫药物解析",
        "基因变异解析",
        "u TP53：c.821T>A，p.V274D；35.08%",
        "基因简介：",
        "TP53基因是重要的抑癌基因之一，参与细胞周期调控。",
        "基因变异说明：",
        "该样本检出TP53基因c.821T>A错义突变，突变丰度为35.08%。",
        "基因变异解析：",
        "TP53突变在结直肠癌中较常见，可能与疾病发生发展相关。",
        "靶向药物/免疫用药提示解析",
        "潜在获益靶向/免疫药物解析",
        "TP53：c.821T>A，p.V274D突变相应靶向药物",
        "AZD1775",
        "基因变异与药物关联分析：",
        "TP53缺失肿瘤细胞可能对WEE1抑制剂敏感。",
        "药物疗效临床解析：",
        "一项临床研究显示AZD1775在实体瘤中具有潜在活性[27601554]。",
        "第四部分：附录",
    ]
    rows = extract_candidates_from_paragraphs(paragraphs, "hash1", "crc_358_msi")
    content_types = {row.content_type for row in rows}
    assert {"gene_intro", "variant_description", "mutation_analysis", "drug_relation", "drug_clinical"} <= content_types
    drug = next(row for row in rows if row.content_type == "drug_relation")
    assert drug.gene == "TP53"
    assert drug.drug_name == "AZD1775"
    assert drug.drug_type == "benefit"


def test_dedupe_candidates_counts_distinct_sources():
    paragraphs = [
        "第三部分：基因变异及相应靶向/免疫药物解析",
        "基因变异解析",
        "u TP53：c.821T>A，p.V274D；35.08%",
        "基因简介：",
        "TP53基因是重要的抑癌基因之一，参与细胞周期调控。",
        "第四部分：附录",
    ]
    a = extract_candidates_from_paragraphs(paragraphs, "hash1", "crc_358_msi")
    b = extract_candidates_from_paragraphs(paragraphs, "hash2", "crc_358_msi")
    rows = dedupe_candidates(a + b)
    assert len(rows) == 1
    assert rows[0].source_count == 2
    assert rows[0].confidence == "中"


def test_machine_preapprove_only_allows_conservative_historical_rows():
    row = {
        "source_type": "historical_final_report",
        "confidence": "高",
        "content_type": "mutation_analysis",
        "current_reviewed_status": "暂无reviewed覆盖",
        "gene": "TSC1",
        "c_hgvs": "c.1963C>T",
        "p_hgvs": "p.Q655*",
        "candidate_text": "TSC1突变可能影响mTOR信号通路。",
    }
    ok, _ = should_preapprove(row)
    assert ok is True

    row["source_type"] = "public_civic_candidate"
    ok, reason = should_preapprove(row)
    assert ok is False
    assert "非历史终版来源" in reason


def test_promote_gene_intro_as_gene_level_overlay():
    overlay = build_overlay(
        [
            {
                "gene": "TSC1",
                "c_hgvs": "c.1963C>T",
                "p_hgvs": "p.Q655*",
                "content_type": "gene_intro",
                "final_text": "TSC1 gene intro",
            }
        ]
    )
    assert overlay["gene_sections"] == [{"gene": "TSC1", "intro": "TSC1 gene intro"}]


def test_merge_overlay_keeps_base_precedence_and_appends_absent_keys():
    base = {
        "source": {"panel": "crc_358_msi"},
        "gene_sections": [{"gene": "TP53", "intro": "base"}],
        "drug_sections": [{"gene": "KRAS", "type": "caution", "drug_name": "DrugA", "relation": "base"}],
    }
    additive = {
        "source": {"source_type": "machine"},
        "gene_sections": [{"gene": "TP53", "intro": "new"}, {"gene": "TSC1", "intro": "added"}],
        "drug_sections": [
            {"gene": "KRAS", "type": "caution", "drug_name": "DrugA", "relation": "new"},
            {"gene": "TSC1", "type": "benefit", "drug_name": "DrugB", "relation": "added"},
        ],
    }
    merged = merge(base, additive)
    assert merged["gene_sections"] == [
        {"gene": "TP53", "intro": "base"},
        {"gene": "TSC1", "intro": "added"},
    ]
    assert merged["drug_sections"] == [
        {"gene": "KRAS", "type": "caution", "drug_name": "DrugA", "relation": "base"},
        {"gene": "TSC1", "type": "benefit", "drug_name": "DrugB", "relation": "added"},
    ]


def test_targeted_priority_part3_overlay_limits_tsc1_drug_to_lof():
    overlay = build_part3_overlay(
        [
            {
                "gene": "FGFR1",
                "candidate_text": "FGFR1 intro",
            }
        ]
    )
    assert overlay["gene_sections"] == [{"gene": "FGFR1", "intro": "FGFR1 intro"}]
    tsc1 = overlay["drug_sections"][0]
    assert tsc1["gene"] == "TSC1"
    assert tsc1["applicability"] == "loss_of_function"
    assert "依维莫司" in tsc1["drug_name"]


def test_targeted_priority_drug_override_snippet_is_conditioned():
    snippet = build_drug_override_snippet()
    row = snippet["reviewed_variant_overrides"][0]
    assert row["gene"] == "TSC1"
    assert row["applicability"] == "loss_of_function"
    assert "依维莫司（C）" in row["benefit_drugs"]


def test_prepare_promotion_appends_only_absent_part3_rows():
    base = {
        "source": {"panel": "crc_358_msi"},
        "gene_sections": [{"gene": "FGFR1", "intro": "base"}],
        "drug_sections": [],
    }
    additive = {
        "gene_sections": [{"gene": "FGFR1", "intro": "new"}, {"gene": "TSC1", "intro": "added"}],
        "drug_sections": [
            {
                "gene": "TSC1",
                "type": "benefit",
                "applicability": "loss_of_function",
                "drug_name": "依维莫司",
            }
        ],
    }
    merged, added = merge_part3(base, additive)
    assert merged["gene_sections"] == [
        {"gene": "FGFR1", "intro": "base"},
        {"gene": "TSC1", "intro": "added"},
    ]
    assert len(merged["drug_sections"]) == 1
    assert len(added) == 2


def test_prepare_promotion_appends_only_absent_crc_rule_rows():
    existing = {
        "reviewed_variant_overrides": [
            {
                "gene": "TSC1",
                "applicability": "loss_of_function",
                "benefit_drugs": ["依维莫司（C）"],
                "caution_drugs": "--",
            }
        ]
    }
    additive = {
        "reviewed_variant_overrides": [
            {
                "gene": "TSC1",
                "applicability": "loss_of_function",
                "benefit_drugs": ["依维莫司（C）"],
                "caution_drugs": "--",
            },
            {
                "gene": "TSC1",
                "applicability": "loss_of_function",
                "benefit_drugs": ["Sapanisertib（C）"],
                "caution_drugs": "--",
            },
        ]
    }
    merged, added = merge_crc_rules(existing, additive)
    assert len(merged["reviewed_variant_overrides"]) == 2
    assert added == [
        {
            "file": "crc.yaml",
            "section": "reviewed_variant_overrides",
            "gene": "TSC1",
            "detail": "loss_of_function / Sapanisertib（C）",
        }
    ]
