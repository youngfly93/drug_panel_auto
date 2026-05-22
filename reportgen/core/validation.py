"""Shared validation checks for parsed Excel inputs."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Mapping, Optional

from reportgen.models.excel_data import ExcelDataSource

TMB_TABLE_IMMUNO_TIPS = (
    "多项临床研究表明，TMB-H的肿瘤对免疫检查点抑制剂有更强的免疫应答效果\n"
    "常用免疫抑制剂有：#帕博利珠单抗、#纳武利尤单抗、#纳武利尤单抗+伊匹木单抗、"
    "阿替利珠单抗、度伐利尤单抗、特瑞普利单抗、信迪利单抗、卡瑞利珠单抗、"
    "#替雷利珠单抗、#恩沃利单抗、#多塔利单抗、#斯鲁利单抗、#普特利单抗、"
    "派安普利单抗、赛帕利单抗等"
)

TMB_DETAIL_INTERPRETATION_TEXT = (
    "肿瘤突变负荷（Tumor Mutation Burden，TMB）即肿瘤基因组去除胚系突变后的"
    "体细胞突变数量，一般以非同义突变（导致氨基酸改变的核苷酸变异）总数量或"
    "每1Mb（即1百万个碱基对）的突变数量来表示。研究表明，具有较高水平TMB的"
    "肿瘤细胞更容易被免疫系统识别，同时在多项临床研究中已证实，TMB水平较高的"
    "肿瘤对免疫检查点抑制剂有更强的免疫应答效果[1]。2020年6月，FDA批准"
    "帕博利珠单抗用于治疗组织肿瘤突变负荷高且既往治疗后病情进展且无满意替代"
    "治疗方案的不可切除或转移性成年和小儿实体瘤患者[2]。"
)

TMB_DRUG_NOTE_TEXT = (
    "常用的免疫抑制剂有：帕博利珠单抗、纳武利尤单抗、阿替利珠单抗、"
    "度伐利尤单抗、替雷利珠单抗、恩沃利单抗等。"
)

MSI_EDUCATIONAL_TIPS = (
    "研究表明，MSI-H的实体瘤通常具有免疫原性和广泛的T细胞浸润性，"
    "从而对免疫检查点抑制剂的治疗响应较高"
)

MSI_CRC_INTERPRETATION_TEXT = "\n".join(
    [
        (
            "肿瘤组织为MSS（微卫星稳定）/MSI-L（微卫星低度不稳定）的结直肠癌"
            "患者，含5-FU的化疗方案相对敏感，可以正常使用，建议结合临床实际"
            "情况选择治疗方案[1]。"
        ),
        (
            "肿瘤组织为MSI-H（微卫星高度不稳定）的Ⅱ期结直肠癌患者，预后较好，"
            "且不能从5-FU辅助化疗获益，不推荐氟尿嘧啶类药物的单药辅助化疗[1-3]。"
        ),
        "肿瘤组织为MSI-H的转移性结直肠癌患者，可能从PD-1免疫治疗获益[4,5]。",
        (
            "肿瘤组织为MSI-H的结直肠癌患者，患有林奇综合征的风险较高，建议做"
            "进一步的林奇综合征筛查诊断（NCCN指南建议林奇综合征的基因检测应包括："
            "MMR基因MLH1、MSH2、MSH6、PMS2和EPCAM基因）。"
        ),
    ]
)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text in {"-", "--", "*", "NA", "N/A", "nan", "None"}


def _to_float(value: Any) -> Optional[float]:
    if _is_missing(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text_rule(
    text_rules: Optional[Mapping[str, Any]],
    key: str,
    default: str,
) -> str:
    if not text_rules:
        return default
    value = text_rules.get(key)
    if isinstance(value, Mapping):
        value = value.get("text") or value.get("value")
    if value is None:
        return default
    text = str(value)
    return text if text.strip() else default


def tmb_threshold_for_sample(sample_type: Any) -> int:
    """Return the reporting TMB threshold for the sample type."""
    sample_type_text = str(sample_type or "组织")
    return 16 if ("血" in sample_type_text or "blood" in sample_type_text.lower()) else 10


def _sample_type_label(sample_type: Any, threshold: int) -> str:
    text = str(sample_type or "").strip()
    if text:
        return text
    return "血液样本" if threshold == 16 else "组织样本"


def build_tmb_fields(
    tmb_raw: Any,
    *,
    sample_type: Any = "组织",
    text_rules: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize TMB fields for every report-generation path.

    Missing TMB and malformed TMB are intentionally distinct. A malformed value
    must never fall through to TMB-L or an empty summary.
    """
    threshold = tmb_threshold_for_sample(sample_type)
    if _is_missing(tmb_raw):
        return {
            "tmb_value": "未检测",
            "tmb_status": "未检测",
            "tmb_level_cn": "未检测",
            "tmb_reference": "",
            "tmb_summary": "未检测",
            "tmb_detail_sentence": "在本次检测范围内，该样本肿瘤突变负荷未检测。",
            "tmb_detail_interpretation": (
                "本次检测未获得可用于TMB分级的有效结果，免疫治疗获益评估需结合"
                "MSI、PD-L1、免疫相关基因及临床病理信息综合判断。"
            ),
            "tmb_drug_note": "",
        }

    try:
        tmb = float(tmb_raw)
    except (TypeError, ValueError):
        invalid_text = "未检测（格式错误）"
        return {
            "tmb_value": invalid_text,
            "tmb_status": "未检测",
            "tmb_level_cn": "未检测",
            "tmb_reference": "",
            "tmb_summary": invalid_text,
            "tmb_detail_sentence": (
                "在本次检测范围内，该样本肿瘤突变负荷未检测（格式错误）。"
            ),
            "tmb_detail_interpretation": (
                "TMB原始值不是有效数字，不能用于TMB-H/TMB-L分级；免疫治疗获益评估"
                "需结合MSI、PD-L1、免疫相关基因及临床病理信息综合判断。"
            ),
            "tmb_drug_note": "",
        }

    tmb_status = "H" if tmb >= threshold else "L"
    tmb_level_cn = "高" if tmb_status == "H" else "低"
    level = "TMB-H" if tmb_status == "H" else "TMB-L"
    direction = "高于" if tmb_status == "H" else "低于"
    unit = "mutations/Mb"
    detail_sentence = (
        f"在本次检测范围内，该样本肿瘤突变负荷为{tmb:.1f}{unit}，"
        f"TMB水平较{tmb_level_cn}。"
    )
    detail_interpretation = _text_rule(
        text_rules,
        "tmb_detail_interpretation",
        TMB_DETAIL_INTERPRETATION_TEXT,
    )
    drug_note = _text_rule(text_rules, "tmb_drug_note", TMB_DRUG_NOTE_TEXT)

    return {
        "tmb_value": f"{tmb:.1f}",
        "tmb_status": tmb_status,
        "tmb_level_cn": tmb_level_cn,
        "tmb_reference": threshold,
        "tmb_summary": (
            f"{tmb:.1f} {unit}，{level}\n"
            f"(本次检测结果{direction}参考值\n{threshold} mutations/Mb)"
        ),
        "tmb_detail_sentence": detail_sentence,
        "tmb_detail_interpretation": detail_interpretation,
        "tmb_drug_note": drug_note,
    }


def build_msi_fields(
    msi_raw: Any,
    *,
    text_rules: Optional[Mapping[str, Any]] = None,
) -> Dict[str, str]:
    """Normalize MSI fields and patient-specific MSI narrative text."""
    msi_status = str(msi_raw).strip() if msi_raw is not None else ""
    if not msi_status:
        msi_status = "未检测"

    up = msi_status.upper()
    crc_interpretation = _text_rule(
        text_rules,
        "msi_crc_interpretation",
        MSI_CRC_INTERPRETATION_TEXT,
    )
    educational_tips = _text_rule(
        text_rules,
        "msi_educational_tips",
        MSI_EDUCATIONAL_TIPS,
    )
    if up == "MSS":
        msi_status = "MSS"
        msi_status_cn = "微卫星稳定型，MSS"
        msi_summary = "微卫星稳定型，MSS"
        detail_sentence = "依据本次检测结果，该肿瘤样本为微卫星稳定（MSS）型。"
        detail_interpretation = crc_interpretation
        msi_tips = educational_tips
    elif up == "MSI-H":
        msi_status = "MSI-H"
        msi_status_cn = "微卫星高度不稳定，MSI-H"
        msi_summary = "微卫星不稳定型，MSI-H"
        detail_sentence = "依据本次检测结果，该肿瘤样本为微卫星高度不稳定（MSI-H）型。"
        detail_interpretation = crc_interpretation
        msi_tips = educational_tips
    elif up == "MSI-L":
        msi_status = "MSI-L"
        msi_status_cn = "微卫星低度不稳定，MSI-L"
        msi_summary = "微卫星不稳定型，MSI-L"
        detail_sentence = "依据本次检测结果，该肿瘤样本为微卫星低度不稳定（MSI-L）型。"
        detail_interpretation = (
            "MSI-L通常不等同于MSI-H/dMMR免疫治疗获益人群；治疗决策需结合"
            "临床病理、免疫组化及其他检测结果综合判断。"
        )
        msi_tips = educational_tips
    elif up.startswith("MSI"):
        msi_status_cn = msi_status
        msi_summary = f"微卫星不稳定型，{msi_status}"
        detail_sentence = f"依据本次检测结果，该肿瘤样本MSI状态为{msi_status}。"
        detail_interpretation = (
            "该MSI结果未能归入标准MSS/MSI-L/MSI-H展示口径；治疗决策需结合"
            "临床病理、免疫组化及其他检测结果综合判断。"
        )
        msi_tips = (
            "MSI结果需结合具体检测口径解释；是否使用免疫治疗需结合临床病理、"
            "免疫组化及其他检测结果综合判断。"
        )
    elif up in {"未检测", "NOT DETECTED", "NOT_TESTED", "NOT TESTED", "NA", "N/A"}:
        msi_status = "未检测"
        msi_status_cn = "未检测"
        msi_summary = "未检测"
        detail_sentence = "依据本次检测结果，该肿瘤样本MSI状态未检测。"
        detail_interpretation = (
            "本次检测未获得可用于MSI分型的有效结果；免疫治疗获益评估需结合"
            "TMB、PD-L1、免疫相关基因及临床病理信息综合判断。"
        )
        msi_tips = (
            "本次未获得MSI状态结果；是否使用免疫治疗需结合临床病理、免疫组化"
            "及其他检测结果综合判断。"
        )
    else:
        msi_status_cn = msi_status
        msi_summary = msi_status
        detail_sentence = f"依据本次检测结果，该肿瘤样本MSI状态为{msi_status}。"
        detail_interpretation = (
            "该MSI状态需结合具体检测口径解释；治疗决策需结合临床病理、"
            "免疫组化及其他检测结果综合判断。"
        )
        msi_tips = (
            "MSI结果需结合具体检测口径解释；是否使用免疫治疗需结合临床病理、"
            "免疫组化及其他检测结果综合判断。"
        )

    return {
        "msi_status": msi_status,
        "msi_status_cn": msi_status_cn,
        "msi_summary": msi_summary,
        "msi_detail_sentence": detail_sentence,
        "msi_detail_interpretation": detail_interpretation,
        "msi_tips": msi_tips,
    }


def validate_excel_data_common(
    excel_data: ExcelDataSource,
    *,
    today: Optional[date] = None,
) -> List[Dict[str, str]]:
    """Return user-facing warnings/errors shared by upload and batch flows."""
    warnings: List[Dict[str, str]] = []
    sv = excel_data.single_values or {}

    meta_sid = excel_data.metadata.get("sample_id_from_filename")
    if not meta_sid:
        warnings.append(
            {
                "level": "warning",
                "field": "sample_id",
                "message": "文件名中未提取到样本编号，请在临床信息表单中手动填写",
            }
        )

    msi_label = sv.get("MSI状态") or sv.get("msi_status")
    msi_pct_raw = sv.get("MSI百分比") or sv.get("msi_score")
    msi_pct = _to_float(msi_pct_raw)
    if msi_label and msi_pct is not None:
        msi_label_upper = str(msi_label).upper()
        if msi_pct >= 40 and "MSI-H" not in msi_label_upper:
            warnings.append(
                {
                    "level": "warning",
                    "field": "msi_status",
                    "message": (
                        f"MSI 百分比 ({msi_pct:.1f}%) 达到 MSI-H 阈值(≥40%)，"
                        f"但标签为 '{msi_label}'，存在冲突。系统将使用标签值。"
                    ),
                }
            )
        elif 20 <= msi_pct < 40 and "MSI-L" not in msi_label_upper:
            if "MSS" in msi_label_upper or "MSI-H" in msi_label_upper:
                warnings.append(
                    {
                        "level": "warning",
                        "field": "msi_status",
                        "message": (
                            f"MSI 百分比 ({msi_pct:.1f}%) 处于 MSI-L 区间(20-40%)，"
                            f"但标签为 '{msi_label}'，存在冲突。系统将使用标签值。"
                        ),
                    }
                )
        elif msi_pct < 20 and "MSS" not in msi_label_upper:
            warnings.append(
                {
                    "level": "warning",
                    "field": "msi_status",
                    "message": (
                        f"MSI 百分比 ({msi_pct:.1f}%) 低于 MSI-L 阈值(<20%)，"
                        f"但标签为 '{msi_label}'，存在冲突。系统将使用标签值。"
                    ),
                }
            )

    report_date = sv.get("出报告日期") or sv.get("报告日期") or sv.get("report_date")
    if _is_missing(report_date):
        today_text = (today or date.today()).isoformat()
        warnings.append(
            {
                "level": "warning",
                "field": "report_date",
                "message": (
                    f"Excel 中未找到报告日期；系统不会自动回填今天 ({today_text})，"
                    "请在临床信息表单中手动填写。"
                ),
            }
        )

    tmb_raw = sv.get("TMB") or sv.get("tmb_value")
    if not _is_missing(tmb_raw) and _to_float(tmb_raw) is None:
        warnings.append(
            {
                "level": "warning",
                "field": "tmb_value",
                "message": f"TMB 值 '{tmb_raw}' 不是有效数字，报告将显示为未检测（格式错误）。",
            }
        )

    return warnings


def format_validation_warning(warning: Dict[str, str]) -> str:
    level = str(warning.get("level") or "warning")
    field = str(warning.get("field") or "input")
    message = str(warning.get("message") or "")
    return f"{level}:{field}: {message}"
