# ruff: noqa: E402, I001
"""守护靶向药物按癌种过滤的泛化（match_keywords 驱动，去 is_crc 硬编码）。

运行时用的是 web 仓库自带的 reportgen 副本，本测试针对该副本。
"""

import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.core.field_mapper import FieldMapper


def _make_mapper(tmp_path, settings: dict) -> FieldMapper:
    mapping = {"schema_version": "1.0", "single_values": {}, "table_data": {}}
    (tmp_path / "mapping.yaml").write_text(
        yaml.safe_dump(mapping, allow_unicode=True), encoding="utf-8"
    )
    (tmp_path / "settings.yaml").write_text(
        yaml.safe_dump(settings, allow_unicode=True), encoding="utf-8"
    )
    return FieldMapper(config_dir=str(tmp_path))


def _attach_db(mapper: FieldMapper, df: pd.DataFrame) -> None:
    mapper._targeted_drug_db_loaded = True
    mapper._targeted_drug_db = df
    mapper._targeted_drug_db_cols = {
        "gene": "基因名称",
        "level": "变异等级",
        "c": "c_point",
        "p": "p_point",
        "benefit": "潜在获益靶向药物（证据等级）",
        "caution": "可能耐药或慎重药物（证据等级）",
    }


def _lung_settings() -> dict:
    return {
        "knowledge_bases": {
            "targeted_drug_db": {
                "enabled": True,
                "filters": {
                    "enabled": True,
                    "apply_to_sources": ["CGI"],
                    "require_position_match": True,
                    "cancer_type": {
                        "enabled": True,
                        "match_keywords": ["肺", "lung", "nsclc", "sclc"],
                        "cgi_allowed_primary_tumor_types": [
                            "LUAD",
                            "LUSC",
                            "NSCLC",
                            "SCLC",
                        ],
                    },
                    "evidence": {"enabled": False},
                },
            }
        }
    }


def test_cancer_filter_generalizes_to_lung(tmp_path):
    """肺癌患者：保留肺癌（NSCLC）药物、过滤掉结直肠（COREAD）药物。

    证明按癌种过滤不再写死 CRC 分支，可由 match_keywords 配置任意癌种。
    """
    mapper = _make_mapper(tmp_path, _lung_settings())
    df = pd.DataFrame(
        [
            {
                "基因名称": "EGFR",
                "变异等级": "",
                "c_point": "",
                "p_point": "p.L858R",
                "潜在获益靶向药物（证据等级）": "DrugLungKeep",
                "可能耐药或慎重药物（证据等级）": "--",
                "source_db": "CGI",
                "cgi_primary_tumor_type": "NSCLC",
            },
            {
                "基因名称": "EGFR",
                "变异等级": "",
                "c_point": "",
                "p_point": "p.L858R",
                "潜在获益靶向药物（证据等级）": "DrugCrcDrop",
                "可能耐药或慎重药物（证据等级）": "--",
                "source_db": "CGI",
                "cgi_primary_tumor_type": "COREAD",
            },
        ]
    )
    _attach_db(mapper, df)

    benefit, _caution, score = mapper._lookup_targeted_drugs_for_variant(
        "EGFR",
        c_point="c.2573T>G",
        p_point="p.L858R",
        variant_level="Ⅱ类",
        cancer_type="肺腺癌",
    )
    assert "DrugLungKeep" in benefit
    assert "DrugCrcDrop" not in benefit
    assert score > 0


def _profiles_settings() -> dict:
    """单份配置内用 profiles 列表同时声明 CRC 与肺癌（Option C）。"""
    return {
        "knowledge_bases": {
            "targeted_drug_db": {
                "enabled": True,
                "filters": {
                    "enabled": True,
                    "apply_to_sources": ["CGI"],
                    "require_position_match": True,
                    "cancer_type": {
                        "enabled": True,
                        "profiles": [
                            {
                                "match_keywords": ["结直肠", "colon", "rectal"],
                                "cgi_allowed_primary_tumor_types": ["COREAD"],
                            },
                            {
                                "match_keywords": ["肺", "lung", "nsclc", "sclc"],
                                "cgi_allowed_primary_tumor_types": [
                                    "LUAD",
                                    "LUSC",
                                    "NSCLC",
                                    "SCLC",
                                ],
                            },
                        ],
                    },
                    "evidence": {"enabled": False},
                },
            }
        }
    }


def _two_cancer_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "基因名称": "EGFR",
                "变异等级": "",
                "c_point": "",
                "p_point": "p.L858R",
                "潜在获益靶向药物（证据等级）": "LungDrug",
                "可能耐药或慎重药物（证据等级）": "--",
                "source_db": "CGI",
                "cgi_primary_tumor_type": "NSCLC",
            },
            {
                "基因名称": "EGFR",
                "变异等级": "",
                "c_point": "",
                "p_point": "p.L858R",
                "潜在获益靶向药物（证据等级）": "CrcDrug",
                "可能耐药或慎重药物（证据等级）": "--",
                "source_db": "CGI",
                "cgi_primary_tumor_type": "COREAD",
            },
        ]
    )


def test_cancer_profiles_lung_patient_picks_lung_profile(tmp_path):
    """profiles 列表：肺癌患者命中肺 profile，只保留肺癌药物。"""
    mapper = _make_mapper(tmp_path, _profiles_settings())
    _attach_db(mapper, _two_cancer_rows())
    benefit, _caution, score = mapper._lookup_targeted_drugs_for_variant(
        "EGFR",
        c_point="c.2573T>G",
        p_point="p.L858R",
        variant_level="Ⅱ类",
        cancer_type="肺腺癌",
    )
    assert "LungDrug" in benefit
    assert "CrcDrug" not in benefit
    assert score > 0


def test_cancer_profiles_crc_patient_picks_crc_profile(tmp_path):
    """profiles 列表：同一份配置，结直肠患者命中 CRC profile，只保留结直肠药物。"""
    mapper = _make_mapper(tmp_path, _profiles_settings())
    _attach_db(mapper, _two_cancer_rows())
    benefit, _caution, score = mapper._lookup_targeted_drugs_for_variant(
        "EGFR",
        c_point="c.2573T>G",
        p_point="p.L858R",
        variant_level="Ⅱ类",
        cancer_type="结直肠癌",
    )
    assert "CrcDrug" in benefit
    assert "LungDrug" not in benefit
    assert score > 0


def test_cancer_profiles_unmatched_patient_no_cancer_filter(tmp_path):
    """profiles 已配但患者癌种无命中 → 不按癌种过滤（放行），仅靠其它过滤项。"""
    mapper = _make_mapper(tmp_path, _profiles_settings())
    _attach_db(mapper, _two_cancer_rows())
    benefit, _caution, score = mapper._lookup_targeted_drugs_for_variant(
        "EGFR",
        c_point="c.2573T>G",
        p_point="p.L858R",
        variant_level="Ⅱ类",
        cancer_type="胰腺癌",
    )
    # 两行都未被癌种过滤掉，应有命中（择优返回其一）
    assert benefit and benefit != "--"
    assert score > 0


def test_cancer_filter_crc_keywords_backward_compatible(tmp_path):
    """向后兼容：仅配 crc_keywords（无 match_keywords）时，CRC 过滤行为不变。"""
    settings = {
        "knowledge_bases": {
            "targeted_drug_db": {
                "enabled": True,
                "filters": {
                    "enabled": True,
                    "apply_to_sources": ["CGI"],
                    "require_position_match": True,
                    "cancer_type": {
                        "enabled": True,
                        "crc_keywords": ["结直肠"],
                        "cgi_allowed_primary_tumor_types": ["COREAD"],
                    },
                    "evidence": {"enabled": False},
                },
            }
        }
    }
    mapper = _make_mapper(tmp_path, settings)
    df = pd.DataFrame(
        [
            {
                "基因名称": "BRAF",
                "变异等级": "",
                "c_point": "",
                "p_point": "p.V600E",
                "潜在获益靶向药物（证据等级）": "DrugWrongCancer",
                "可能耐药或慎重药物（证据等级）": "--",
                "source_db": "CGI",
                "cgi_primary_tumor_type": "NSCLC",
            }
        ]
    )
    _attach_db(mapper, df)

    benefit, _caution, score = mapper._lookup_targeted_drugs_for_variant(
        "BRAF",
        c_point="c.1799T>A",
        p_point="p.V600E",
        variant_level="Ⅱ类",
        cancer_type="结直肠癌",
    )
    assert benefit == "--"
    assert score == 0.0
