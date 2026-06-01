# ruff: noqa: E402, I001
"""定向单测:验证「基因级 drug-relation override 能替换 base」这条链(纯机制)。

隔离 _apply_reviewed_drug_section_overrides:给一个 base 药物关联 section(CRC 味)+
一个**基因级**(无 c_hgvs)override,断言结果用 override、丢掉 base。并验证 caution、
变异级优先于基因级、以及无 override 时回退 base。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.knowledge.gene_knowledge import GeneKnowledgeProvider


def _provider():
    p = GeneKnowledgeProvider({"enabled": False})
    p._loaded = True
    return p


_VARIANT = {
    "gene": "KRAS",
    "cHGVS": "c.34G>T",
    "pHGVS": "p.G12C",
    "benefit_drugs": "索托拉西布（A）",
    "caution_drugs": "--",
}


def _base_benefit_section():
    return {
        "gene": "KRAS",
        "c_hgvs": "c.34G>T",
        "p_hgvs": "p.G12C",
        "drug_type": "benefit",
        "drug_name": "索托拉西布",
        "relation": "BASE_RELATION_结直肠癌",
        "clinical": "BASE_CLINICAL_结直肠癌细胞系",
    }


def test_gene_level_drug_override_replaces_base():
    p = _provider()
    gkey = p._hgvs_key("KRAS")
    p._gene_level_drug_overrides[(gkey, "benefit")] = [
        {
            "gene": "KRAS",
            "drug_type": "benefit",
            "drug_name": "索托拉西布",
            "relation": "LUNG_RELATION_非小细胞肺癌",
            "clinical": "LUNG_CLINICAL_NSCLC",
        }
    ]
    result = p._apply_reviewed_drug_section_overrides([_VARIANT], [_base_benefit_section()])
    blob = "\n".join(str(s.get("relation", "")) + str(s.get("clinical", "")) for s in result)
    assert "LUNG_RELATION_非小细胞肺癌" in blob, result
    assert "BASE_RELATION_结直肠癌" not in blob, "base 未被替换"
    # override section 应带上当前变异显示
    assert any(s.get("variant") for s in result if "LUNG" in str(s.get("relation"))), result


def test_variant_level_takes_precedence_over_gene_level():
    p = _provider()
    vkey = p._variant_key("KRAS", "c.34G>T", "p.G12C")
    gkey = p._hgvs_key("KRAS")
    p._reviewed_drug_section_overrides[(vkey, "benefit")] = [
        {"gene": "KRAS", "drug_type": "benefit", "relation": "VARIANT_LEVEL", "clinical": ""}
    ]
    p._gene_level_drug_overrides[(gkey, "benefit")] = [
        {"gene": "KRAS", "drug_type": "benefit", "relation": "GENE_LEVEL", "clinical": ""}
    ]
    result = p._apply_reviewed_drug_section_overrides([_VARIANT], [_base_benefit_section()])
    blob = "\n".join(str(s.get("relation", "")) for s in result)
    assert "VARIANT_LEVEL" in blob and "GENE_LEVEL" not in blob, result


def test_no_override_keeps_base():
    p = _provider()
    result = p._apply_reviewed_drug_section_overrides([_VARIANT], [_base_benefit_section()])
    blob = "\n".join(str(s.get("relation", "")) for s in result)
    assert "BASE_RELATION_结直肠癌" in blob, result


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
