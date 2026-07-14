# 总审计单 · 待二审知识逐行裁决

- audited_commit: `4545e0b` · kb_hash: `292c386db6a0904e` · auditor: Claude(AI一审,独立于 drafter codex) · 2026-07-14
- **条目计数(修正 codex 指出的口径)**: 队列 **64 运行行** = 60 gene 行 + 4 FANCA 药物行;
  但**独立知识**更少 —— gene 行仅 **48 个独立基因解释**(12 个在 CRC301/358 复用),FANCA 为 1 基因×2 panel×2 kind。故"64"是运行行数,非 64 条独立知识。
- 裁决口径: `通过(治理级)`=措辞无越权、可入二审(**非医学放行**) / `有条件·暂缓runtime`=证据真但需医学决定+交付层门禁
- 每行附「已核限定语」= 该行实际措辞关键否定句(逐行已读,无空证据);完整14字段机读表见 `knowledge_review_worksheet.tsv`

## CRC301（50 运行行：48 gene + FANCA drug + FANCA targeted；独立基因见上）

| # | gene | kind | ev | 裁决 | 已核限定语 / 依据 |
|---|---|---|---|---|---|
| 1 | ERCC2 | gene | functional_background_only | ✅通过 | 不能仅因检出ERCC2变异就在结直肠癌中外推铂类或其他DNA损伤药物敏感性 |
| 2 | HLA-C | gene | functional_background_only | ✅通过 | 需结合HLA表达或缺失、MSI/TMB和癌种证据 |
| 3 | ESR2 | gene | functional_background_only | ✅通过 | 结直肠癌中的单个位点需结合功能证据和变异分级，不能独立形成治疗结论 |
| 4 | PIK3C2G | gene | functional_background_only | ✅通过 | 具体意义需结合位点功能、拷贝数和变异分级 |
| 5 | CD274 | gene | functional_background_only | ✅通过 | 报告解读需结合PD-L1IHC、MSI/TMB、变异分级及癌种证据 |
| 6 | SLCO1B1 | gene | functional_background_only | ✅通过 | 需结合样本来源、胚系确认及相应药物指南 |
| 7 | XPC | gene | functional_background_only | ✅通过 | 在结直肠癌中不能据此单独推断DNA损伤药物敏感性或免疫治疗获益 |
| 8 | CHD2 | gene | functional_background_only | ✅通过 | 检出变异时仅作染色质重塑相关背景说明，并结合变异类型、分级、共突变和临床资料综合判断，不单独形成治疗结论 |
| 9 | HIST1H3B | gene | functional_background_only | ✅通过 | 检出变异时应结合具体氨基酸位点、变异分级和肿瘤分子背景谨慎解释，不单独形成治疗结论 |
| 10 | HLA-DPA1 | gene | functional_background_only | ✅通过 | 检出时应结合变异功能、HLA表达或缺失、MSI/TMB及肿瘤免疫背景综合评估，不单独形成用药结论 |
| 11 | WDR90 | gene | functional_background_only | ✅通过 | 检出变异时仅作中心粒/纤毛相关功能背景说明，并结合变异类型、分级和其他明确驱动变异综合判断，不单独形成治疗结论 |
| 12 | ZNF703 | gene | exploratory_crc_expression_evidence | ✅通过 | 当前缺少将任意ZNF703体细胞序列变异作为结直肠癌用药标志的充分证据，因此仅作转录调控相关背景说明，不单独形成治疗结论 |
| 13 | ABCB1 | gene | functional_background_only | ✅通过 | 任意体细胞变异不能直接解释为化疗耐药 |
| 14 | ALDH1A1 | gene | functional_background_only | ✅通过 | ALDH1A1表达或功能变化可能影响醛类代谢，但单个位点在结直肠癌中的治疗意义通常不明确，需结合变异类型和功能证据 |
| 15 | AREG | gene | functional_background_only | ✅通过 | DNA序列变异不能替代表达水平或配体水平检测，也不能单独预测抗EGFR药物疗效 |
| 16 | C8ORF34 | gene | functional_background_only | ✅通过 | 其他变异不直接形成毒性或剂量结论 |
| 17 | CBR3 | gene | functional_background_only | ✅通过 | CBR3变异可能影响特定药物代谢，但必须按具体等位基因和药物证据解释，不能由任意变异推导疗效或毒性 |
| 18 | CDA | gene | functional_background_only | ✅通过 | 只有经验证的功能等位基因及对应药物证据可用于药物提示 |
| 19 | CEP72 | gene | functional_background_only | ✅通过 | 其他变异不作同等外推 |
| 20 | CTLA4 | gene | functional_background_only | ✅通过 | CTLA4基因变异、表达和免疫治疗反应并非等价指标 |
| 21 | CXCL12 | gene | functional_background_only | ✅通过 | CXCL12变异通常不足以单独形成治疗结论，需结合通路状态、表达、变异功能及癌种证据综合评估 |
| 22 | CYP19A1 | gene | functional_background_only | ✅通过 | 结直肠癌体细胞变异不自动提示内分泌治疗 |
| 23 | CYP2D6 | gene | functional_background_only | ✅通过 | CYP2D6必须基于规范星号等位基因、拷贝数和表型翻译进行药物基因组学解释，单个未分相变异不能直接判定代谢型 |
| 24 | CYP2E1 | gene | functional_background_only | ✅通过 | 无明确指南关联的位点不形成剂量或疗效建议 |
| 25 | DCK | gene | functional_background_only | ✅通过 | DCK活性可能影响核苷类似物敏感性，但基因变异需有具体功能和临床药物证据后才能形成用药结论 |
| 26 | DOK5 | gene | functional_background_only | ✅通过 | DOK5在结直肠癌中的位点级临床证据有限，检出变异时以通路背景解释，不单独给出药物结论 |
| 27 | DPYD | gene | functional_background_only | ✅通过 | 高风险等位基因可关联氟嘧啶严重毒性，但任意体细胞变异不能直接套用 |
| 28 | DYNC2H1 | gene | functional_background_only | ✅通过 | DYNC2H1体细胞变异在结直肠癌中的直接临床意义通常有限，需结合变异致病性和功能证据谨慎解释 |
| 29 | ERCC1 | gene | functional_background_only | ✅通过 | 单个变异不能直接预测铂类敏感性，需结合功能、双等位状态及临床证据 |
| 30 | GALNT14 | gene | functional_background_only | ✅通过 | 其他变异仅作功能背景说明 |
| 31 | GGH | gene | functional_background_only | ✅通过 | GGH变异可能影响叶酸/抗叶酸代谢，但临床解释必须结合具体等位基因和药物证据，不能由任意变异推断疗效 |
| 32 | GSTM1 | gene | functional_background_only | ✅通过 | 不以单一体细胞变异直接判断化疗反应 |
| 33 | GSTP1 | gene | functional_background_only | ✅通过 | 其他变异不直接形成耐药或毒性结论 |
| 34 | MTHFR | gene | functional_background_only | ✅通过 | MTHFR常见胚系多态性可影响叶酸代谢，但不能脱离基因型组合、叶酸状态和具体药物证据推导剂量或疗效 |
| 35 | MTRR | gene | functional_background_only | ✅通过 | 普通体细胞变异通常不形成用药结论 |
| 36 | NQO1 | gene | functional_background_only | ✅通过 | NQO1变异与药物或毒性关联具有底物和人群特异性，仅解释经验证的功能等位基因 |
| 37 | NT5C3A | gene | functional_background_only | ✅通过 | NT5C3A功能可能影响嘧啶核苷酸代谢，但变异需有明确功能和药物证据后才可用于临床提示 |
| 38 | RRM1 | gene | functional_background_only | ✅通过 | 单个变异不足以直接预测吉西他滨等药物疗效 |
| 39 | SEMA3C | gene | functional_background_only | ✅通过 | SEMA3C位点级临床证据有限，检出变异时以功能和通路背景解释，不直接形成治疗建议 |
| 40 | SLC19A1 | gene | functional_background_only | ✅通过 | SLC19A1变异可能影响叶酸或抗叶酸药物转运，但需限定具体等位基因、药物和临床证据 |
| 41 | SLC22A12 | gene | functional_background_only | ✅通过 | 在肿瘤用药中的意义需有特定药物和等位基因证据，不能由任意变异外推 |
| 42 | SLC28A3 | gene | functional_background_only | ✅通过 | 其他变异不直接提示疗效或毒性 |
| 43 | SLC29A1 | gene | functional_background_only | ✅通过 | 单个变异不能直接预测核苷类似物疗效 |
| 44 | SOD2 | gene | functional_background_only | ✅通过 | SOD2变异可能影响氧化应激能力，但其药物或预后意义需限定具体位点、人群和功能证据 |
| 45 | UGT1A1 | gene | functional_background_only | ✅通过 | 低活性等位基因可关联伊立替康毒性，但单个未分相变异或体细胞变异不能直接判定风险 |
| 46 | UMPS | gene | functional_background_only | ✅通过 | UMPS功能与嘧啶代谢相关，但序列变异用于药物解释前需具备具体功能和临床证据。 |
| 47 | XRCC1 | gene | functional_background_only | ✅通过 | 单个变异不能直接预测放疗或DNA损伤药物敏感性 |
| 48 | XRCC3 | gene | functional_background_only | ✅通过 | XRCC3变异需结合致病性、双等位状态和同源重组缺陷背景评估，不能由任意错义变异直接推导PARP抑制剂获益 |
| 49 | FANCA | drug | cross_cancer_level_d | ⚠️有条件·暂缓runtime | PMID:26510020 属实、限LoF/Ⅱ类;provisional 却 runtime-live → BPI-KB-01 |
| 50 | FANCA | targeted_drug | cross_cancer_level_d | ⚠️有条件·暂缓runtime | PMID:26510020 属实、限LoF/Ⅱ类;provisional 却 runtime-live → BPI-KB-01 |

## CRC358（14 运行行：12 gene + FANCA drug + FANCA targeted）

| # | gene | kind | ev | 裁决 | 已核限定语 / 依据 |
|---|---|---|---|---|---|
| 1 | ERCC2 | gene | functional_background_only | ✅通过 | 不能仅因检出ERCC2变异就在结直肠癌中外推铂类或其他DNA损伤药物敏感性 |
| 2 | HLA-C | gene | functional_background_only | ✅通过 | 需结合HLA表达或缺失、MSI/TMB和癌种证据 |
| 3 | ESR2 | gene | functional_background_only | ✅通过 | 结直肠癌中的单个位点需结合功能证据和变异分级，不能独立形成治疗结论 |
| 4 | PIK3C2G | gene | functional_background_only | ✅通过 | 具体意义需结合位点功能、拷贝数和变异分级 |
| 5 | CD274 | gene | functional_background_only | ✅通过 | 报告解读需结合PD-L1IHC、MSI/TMB、变异分级及癌种证据 |
| 6 | SLCO1B1 | gene | functional_background_only | ✅通过 | 需结合样本来源、胚系确认及相应药物指南 |
| 7 | XPC | gene | functional_background_only | ✅通过 | 在结直肠癌中不能据此单独推断DNA损伤药物敏感性或免疫治疗获益 |
| 8 | CHD2 | gene | functional_background_only | ✅通过 | 检出变异时仅作染色质重塑相关背景说明，并结合变异类型、分级、共突变和临床资料综合判断，不单独形成治疗结论 |
| 9 | HIST1H3B | gene | functional_background_only | ✅通过 | 检出变异时应结合具体氨基酸位点、变异分级和肿瘤分子背景谨慎解释，不单独形成治疗结论 |
| 10 | HLA-DPA1 | gene | functional_background_only | ✅通过 | 检出时应结合变异功能、HLA表达或缺失、MSI/TMB及肿瘤免疫背景综合评估，不单独形成用药结论 |
| 11 | WDR90 | gene | functional_background_only | ✅通过 | 检出变异时仅作中心粒/纤毛相关功能背景说明，并结合变异类型、分级和其他明确驱动变异综合判断，不单独形成治疗结论 |
| 12 | ZNF703 | gene | exploratory_crc_expression_evidence | ✅通过 | 当前缺少将任意ZNF703体细胞序列变异作为结直肠癌用药标志的充分证据，因此仅作转录调控相关背景说明，不单独形成治疗结论 |
| 13 | FANCA | drug | cross_cancer_level_d | ⚠️有条件·暂缓runtime | PMID:26510020 属实、限LoF/Ⅱ类;provisional 却 runtime-live → BPI-KB-01 |
| 14 | FANCA | targeted_drug | cross_cancer_level_d | ⚠️有条件·暂缓runtime | PMID:26510020 属实、限LoF/Ⅱ类;provisional 却 runtime-live → BPI-KB-01 |

## 跨行观察(非阻塞)

1. **胚系 vs 体细胞**:DPYD/UGT1A1/CYP2D6/SLCO1B1 等 PGx 基因真实证据是胚系星号等位基因,本 panel 是体细胞;各条已正确声明"体细胞不替代胚系分型"。建议报告组统一确认这批 PGx 在体细胞报告"仅背景、不给剂量结论"策略。
2. **措辞确认**:gene 行均否定/背景句,建议抽检 3~5 行后批量确认。
3. **唯一治疗关联**:仅 FANCA 做药物获益关联,风险集中于此(BPI-KB-01);其余基因均无药物结论。
