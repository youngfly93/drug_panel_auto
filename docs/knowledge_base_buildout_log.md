# 知识库建设记录

## 2026-06-11 CRC358 医学知识库 v0.1 候选版

状态：候选材料已生成，未入生产 overlay。

产物：

- `tmp/knowledge_buildout/crc_report_inventory.xlsx`
- `tmp/knowledge_buildout/crc358_part3_candidates_raw.xlsx`
- `tmp/knowledge_buildout/CRC358_医学知识库候选审核表_v0.1.xlsx`
- `tmp/knowledge_buildout/CRC358_知识库覆盖率基线_v0.1.xlsx`
- `tmp/knowledge_buildout/reviewed_part3_knowledge_from_candidates.yaml`

本轮结果：

- 扫描肠癌历史报告目录，按产品族做去标识 inventory。
- 对 `crc_358_msi` 终版报告抽取 Part3 候选内容。
- 历史报告 raw 候选：1709 条。
- 去重后候选审核条目：1300 条。
- 显式缺口聚合：136 条。
- 当前审核表默认 `review_status=待审核`，未自动写入生产知识库。

安全约束：

- 审核表不输出真实报告文件名、患者姓名、样本号、报告编号或报告日期。
- 来源仅保留 `source_hashes`。
- 公共数据库内容只进入候选层，不能直接进入正式报告。
- 只有 `review_status` 为 `通过` 或 `修改后通过` 的行可由入库脚本转为 overlay 草稿。

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py -q` 通过。
- 4 个 Excel 产物可正常打开，无公式错误。
- 4 个 Excel 产物经样本号/报告号/姓名/日期正则扫描未命中。
- 入库脚本在全待审核状态下输出 0 条 `gene_sections` 和 0 条 `drug_sections`。

## 2026-06-11 CRC358 机器预审与 overlay 草稿

状态：机器预审草稿已生成，未覆盖生产 `reviewed_part3_knowledge.yaml`。

产物：

- `tmp/knowledge_buildout/CRC358_医学知识库机器预审表_v0.1.xlsx`
- `tmp/knowledge_buildout/reviewed_part3_knowledge_machine_preapproved_v0.1.yaml`
- `tmp/knowledge_buildout/reviewed_part3_knowledge_merged_machine_preapproved_v0.1.yaml`

机器预审规则：

- 仅允许历史终版报告来源。
- 仅允许高/中置信候选。
- 排除样本特异 `variant_description`。
- 排除公共数据库候选。
- 排除已有正式 reviewed 覆盖的条目。
- 排除复合基因名和疑似 PII 文本。
- `gene_intro` 按基因级入库，不按来源位点入库。

本轮结果：

- 机器预审通过：121 条。
- 未入草稿：1179 条。
- additive overlay 草稿：62 个 `gene_sections`，15 个 `drug_sections`。
- 合并原正式 overlay 后：72 个 `gene_sections`，25 个 `drug_sections`。
- TSC1 可命中新增基因简介；TSC1 药物段因当前候选置信度不足，仍保留为缺口，不强行入草稿。

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py -q` 通过。
- 相关知识库回归 12 passed。
- 机器预审 Excel 无公式错误。
- 机器预审 Excel、additive YAML、merged YAML 经样本号/报告号/姓名/日期正则扫描未命中。

## 2026-06-11 CRC358 merged overlay 上下文级回归

状态：已对批量 Excel 做上下文级回归，未覆盖生产 `reviewed_part3_knowledge.yaml`。

产物：

- `tmp/knowledge_buildout/CRC358_merged_overlay_context_retest_v0.1.xlsx`
- `tmp/knowledge_buildout/reviewed_part3_knowledge_merged_machine_preapproved_v0.1.yaml`
- `tmp/overlay_retest/full_merged/LZ250736_merged_overlay_context_check.docx`
- `tmp/CRC358_merged_overlay_context_retest_v0.1_20260611.zip`

验证方法：

- 使用 `肠癌358变异表.zip` 中 14 份 Excel。
- 不渲染 Word，复用实际 Excel 解析、字段映射、CRC358 enhancer 和 `GeneKnowledgeProvider`。
- 对比生产 overlay 与 merged draft overlay 生成的 `gene_knowledge_sections`、`drug_analysis_sections`。

本轮结果：

- 14 份 Excel 全部 PASS，0 失败。
- `gene_knowledge_sections` 发生 84 处内容变化，主要是把固定套话替换为历史终版报告抽取的基因简介/变异解析。
- `drug_analysis_sections` 发生 14 处内容变化，主要集中于 KRAS 和 TP53 的高置信候选。
- 报告组点名基因中，DNMT3A、TSC1 的基因简介已有提升；FGFR1、PCLO、EGFR 本轮机器预审未纳入。
- TSC1 药物解析仍未补足，原因是当前候选置信度不足，继续保留在人工/医学审核缺口中。
- 选取 `LZ250736` 用 merged draft overlay 完整渲染 Word，生成成功，QA PASS；抽查确认新增 KRAS 基因简介、COSMIC 解析和药物临床解析已进入 docx。

结论：

- merged draft overlay 可作为下一轮医学审核材料，不建议直接上线。
- 下一步应围绕 `FGFR1/PCLO/EGFR/TSC1` 和药物解析缺口做定向补库，审核通过后再合并进生产 overlay。

## 2026-06-11 CRC358 重点基因定向补库 v0.1

状态：已生成审核包和测试草稿，未修改生产 overlay 或生产 drug rules。

产物：

- `tmp/knowledge_buildout/CRC358_重点基因定向补库审核表_v0.1.xlsx`
- `tmp/knowledge_buildout/CRC358_重点基因定向补库机制验证_v0.1.xlsx`
- `tmp/knowledge_buildout/reviewed_part3_knowledge_targeted_priority_v0.1.yaml`
- `tmp/knowledge_buildout/crc358_targeted_drug_overrides_priority_v0.1.yaml`
- `tmp/knowledge_buildout/reviewed_part3_knowledge_merged_targeted_priority_v0.1.yaml`

本轮结果：

- 目标基因候选：50 条。
- 可进入草稿的历史终版基因简介：4 条，覆盖 `DNMT3A/TSC1/EGFR/FGFR1`。
- `PCLO` 在本轮 CRC358 Part3 候选和 CIViC pilot 中均无可直接复用中文 reviewed 内容，仍是缺口。
- 新增机制：Part3 drug overlay 和前置 drug override 均支持 `applicability: loss_of_function`。
- TSC1 草稿药物方案按 LoF 条件触发，避免普通错义 TSC1 误触发。

机制验证：

- `FGFR1/EGFR/DNMT3A/TSC1` 基因简介均命中知识库，不再走固定套话。
- `PCLO` 仍为固定套话，需单独补中文知识源。
- `TSC1 c.1963C>T, p.Q655*` 可触发 TSC1 药物解析和前置药物 override。
- `TSC1 c.1648G>T, p.A550S` 不触发 TSC1 LoF 药物解析，符合条件限制。
- `TSC1 c.211-2A>G` 可触发前置药物 override。

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py backend/tests/test_gene_level_drug_override.py backend/tests/test_targeted_drug_cancer_filter.py -q`：20 passed。
- 两个 Excel 产物无公式错误、无样本号/报告号/姓名/日期扫描命中。

下一步：

- 若医学审核通过，可把 `crc358_targeted_drug_overrides_priority_v0.1.yaml` 中的 TSC1 LoF 规则合入 `panels/crc_358_msi/rules/crc.yaml`。
- 若医学审核通过，可把 `reviewed_part3_knowledge_targeted_priority_v0.1.yaml` 中的 TSC1 LoF 药物解析合入生产 reviewed overlay。
- `PCLO` 需要人工整理或从内部知识库补充后再进入下一轮候选。

## 2026-06-11 CRC358 重点基因生产合入候选 v0.1

状态：已生成生产合入候选文件，仍处于 `pending_medical_review`；未覆盖生产文件，未部署。

产物：

- `tmp/knowledge_buildout/production_candidate/reviewed_part3_knowledge.candidate.yaml`
- `tmp/knowledge_buildout/production_candidate/crc.candidate.yaml`
- `tmp/knowledge_buildout/production_candidate/promotion_summary.json`
- `tmp/knowledge_buildout/production_candidate/promotion_summary.xlsx`
- `tmp/CRC358_重点基因生产合入候选_v0.1_20260611.zip`

候选合入内容：

- Part3 reviewed overlay 候选新增 5 条：
  - `DNMT3A` gene-level intro
  - `TSC1` gene-level intro
  - `EGFR` gene-level intro
  - `FGFR1` gene-level intro
  - `TSC1` `loss_of_function` 药物解析
- CRC 前置药物规则候选新增 1 条：
  - `TSC1` `loss_of_function` 触发 `依维莫司/依维莫司+Buparlisib/西罗莫司/替西罗莫司/Sapanisertib`

候选验证：

- 候选 overlay 可读，候选 `crc.yaml` 可读。
- TSC1 `c.1963C>T, p.Q655*` 命中 Part3 药物解析和前置药物 override。
- TSC1 `c.1648G>T, p.A550S` 不命中 LoF 药物解析和前置药物 override。
- TSC1 `c.211-2A>G` 命中前置药物 override。
- `PCLO` 仍为固定套话，未被本轮候选误补。
- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py backend/tests/test_gene_level_drug_override.py backend/tests/test_targeted_drug_cancer_filter.py -q`：22 passed。

落地条件：

- 报告组/医学审核明确通过上述候选内容后，才可将 candidate YAML 内容合入生产 `panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml` 与 `panels/crc_358_msi/rules/crc.yaml`。
- 合入生产后需重新跑 14 份批量 Excel 上下文回归、至少 1 份完整 Word QA，并再做一次报告组抽查。

## 2026-06-11 CRC358 重点基因本地生产合入 v0.2

状态：已按“通过”口径合入本地生产规则，未部署线上。

合入内容：

- `panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml`
  - 新增 `DNMT3A/TSC1/EGFR/FGFR1` 基因简介 reviewed 内容。
  - 新增 `TSC1` `loss_of_function` 药物解析。
- `panels/crc_358_msi/rules/crc.yaml`
  - 新增 `TSC1` `loss_of_function` 前置药物 override。
- `reportgen/core/template_bridge_358.py`
  - Part3 用药解析范围默认跟随 `part3_variant_scope`，避免汇总表已有用药、后文解析缺失。

验证结果：

- `LZ258862` 上下文验证：
  - `summary_variants` 中 `TSC1 c.211-2A>G` 命中 `依维莫司/依维莫司+Buparlisib/西罗莫司/替西罗莫司/Sapanisertib`。
  - `drug_analysis_sections` 已生成 `TSC1 功能缺失型变异相关潜在获益药物`。
- 完整 Word 验证：
  - 生成 `tmp/overlay_retest/full_production/LZ258862_after_tsc1_lof.docx` 成功。
  - DOCX 正文可检索到 `TSC1 功能缺失型变异相关潜在获益药物`、`TSC1/TSC2 缺失或失活`、`依维莫司`、`Sapanisertib`。
- 14 份上下文回归：
  - 输出 `tmp/knowledge_buildout/CRC358_production_overlay_context_retest_after_tsc1_v0.2.xlsx`。
  - `tested=14, pass=14, fail=0`。
- 测试：
  - `python -m pytest backend/tests/test_crc358_knowledge_buildout.py backend/tests/test_gene_level_drug_override.py backend/tests/test_targeted_drug_cancer_filter.py backend/tests/test_report_regression.py::test_part3_variant_scope_can_follow_summary_variants backend/tests/test_report_regression.py::test_part3_drug_analysis_scope_follows_summary_variants -q`：24 passed。
  - `py_compile`：通过。

仍需注意：

- `PCLO` 仍无 reviewed 知识内容，本轮不做机器补写。
- 本轮修复的是知识库覆盖和 TSC1 LoF 药物解析链路，不代表历史知识库已完全补齐。

## 2026-06-14 CRC358 高置信历史终版批量补库 batch1

状态：已按保守机器预审规则合入本地生产 `reviewed_part3_knowledge.yaml`，未部署线上。

输入与规则：

- 语料：`各癌种基因报告近年汇总/肠癌` 中 CRC358+MSI 终版报告。
- 本轮重扫：603 份非资源叉 DOCX，其中 CRC358+MSI 终版 36 份。
- 候选池：历史 raw 候选 1709 条，去重候选 1300 条。
- 机器预审只允许：
  - 历史终版来源；
  - 高/中置信；
  - 未被正式 reviewed 覆盖；
  - 无样本号、姓名、报告编号、完整日期等 PII 命中；
  - 基因名格式正常；
  - 位点解析必须高置信；
  - 药物解析必须高置信、至少 3 份终版重复、药名和药物类型明确。

合入内容：

- 机器预审通过 71 条，1229 条继续保留在审核/缺口池。
- 合入后生产 overlay：
  - `gene_sections`: 66 条，覆盖 56 个基因。
  - `drug_sections`: 17 条，覆盖 7 个基因。
- 本批新增的机器预审 overlay：
  - `gene_sections`: 52 条，覆盖 50 个基因。
  - `drug_sections`: 6 条，覆盖 `FLCN/KRAS/PIK3CA`。

覆盖率变化：

- 合入前：暂无 reviewed 覆盖 1215 条，涉及 97 个基因。
- 合入后：暂无 reviewed 覆盖 187 条，涉及 47 个基因。
- 仍需优先处理的缺口包括：`PTEN/ERBB2/BRCA1/MYH11/RAD52/CDK12/CHEK2/FANCE/GNAS/MLH3/XRCC2/MSH2` 等。

验证：

- PII 扫描：候选 overlay 中样本号、姓名、报告编号、送检者、完整日期均 0 命中。
- 结构检查：drug section 无空药名；gene/drug key 无重复。
- 14 份批量 Excel 上下文复测：
  - `tested=14, pass=14, fail=0`
  - `gene section` 变化 80 条，`drug section` 变化 4 条。
  - 输出：`tmp/knowledge_buildout_audit_20260614/CRC358_machine_preapproved_context_retest_v0.3.xlsx`
- 回归：
  - `python -m pytest backend/tests/test_crc358_knowledge_buildout.py backend/tests/test_gene_level_drug_override.py backend/tests/test_targeted_drug_cancer_filter.py backend/tests/test_report_regression.py -q`
  - 结果：230 passed。

本轮产物：

- `tmp/knowledge_buildout_audit_20260614/CRC358_医学知识库机器预审表_v0.3.xlsx`
- `tmp/knowledge_buildout_audit_20260614/reviewed_part3_knowledge_machine_preapproved_v0.3.yaml`
- `tmp/knowledge_buildout_audit_20260614/reviewed_part3_knowledge_merged_machine_preapproved_v0.3.yaml`
- `tmp/knowledge_buildout_after_batch1_20260614/CRC358_知识库覆盖率基线_v0.1.xlsx`
- `tmp/knowledge_buildout_after_batch1_20260614/CRC358_医学知识库候选审核表_v0.1.xlsx`

仍需注意：

- 这次显著降低了 CRC358 候选缺口，但不代表“整个知识库”已完全完成。
- 剩余 187 条暂无 reviewed 覆盖候选需要进入 batch2：优先处理仍缺失的高频基因、复合基因、公共库可补位点和药物解析。

## 2026-06-14 全肠癌 panel 基因简介批量补库 batch2

状态：已按保守跨 panel 规则合入本地生产 `reviewed_part3_knowledge.yaml`，未部署线上。

输入与规则：

- 新增 `build_crc358_knowledge_buildout.py --include-all-crc-panels`，默认行为不变；显式打开后才从全部肠癌产品族终版报告抽取候选。
- 全肠癌候选池：
  - raw 候选 23454 条；
  - 去重候选 16125 条。
- 跨 panel 自动预审仅允许 `gene_intro`。
- `mutation_analysis`、`drug_relation`、`drug_clinical` 不允许跨 panel 自动进入机器预审，避免位点/药物口径误用。

合入内容：

- 机器预审通过 178 条，全部为 `gene_intro`。
- 生成 additive gene section 102 条，无 drug section。
- 合入后生产 overlay：
  - `gene_sections`: 168 条，覆盖 157 个基因；
  - `drug_sections`: 17 条，覆盖 7 个基因。

覆盖率变化：

- 全肠癌候选池中，暂无 reviewed 覆盖从 3903 条降至 849 条。
- 未覆盖基因从 195 个降至 93 个。
- 剩余缺口主要集中在：
  - 复合基因或表头类项目：如 `KRAS/NRAS/BRAF`、`KRAS/NRAS`、`NRAS/KRAS`；
  - 仍无稳定基因简介来源的基因；
  - 位点解析、药物解析、变异说明等不能靠基因简介解决的内容。

验证：

- PII 扫描：生产 overlay 中样本号、姓名、报告编号、送检者、完整日期均 0 命中。
- 结构检查：gene/drug key 无重复；drug section 无空药名。
- 14 份批量 Excel 上下文复测：
  - `tested=14, pass=14, fail=0`
  - `gene section` 变化 30 条，`drug section` 变化 0 条。
  - 输出：`tmp/knowledge_buildout_all_crc_batch2_20260614/CRC358_all_crc_batch2_context_retest_v0.1.xlsx`
- 回归：
  - `python -m pytest backend/tests/test_crc358_knowledge_buildout.py backend/tests/test_gene_level_drug_override.py backend/tests/test_targeted_drug_cancer_filter.py backend/tests/test_report_regression.py -q`
  - 结果：232 passed。

本轮产物：

- `tmp/knowledge_buildout_all_crc_batch2_20260614/CRC358_医学知识库机器预审表_batch2_v0.1.xlsx`
- `tmp/knowledge_buildout_all_crc_batch2_20260614/reviewed_part3_knowledge_machine_preapproved_batch2_v0.1.yaml`
- `tmp/knowledge_buildout_all_crc_batch2_20260614/reviewed_part3_knowledge_merged_batch2_v0.1.yaml`
- `tmp/knowledge_buildout_after_batch2_20260614/CRC358_知识库覆盖率基线_v0.1.xlsx`
- `tmp/knowledge_buildout_after_batch2_20260614/CRC358_医学知识库候选审核表_v0.1.xlsx`

下一步：

- batch3 不应继续简单扩展 gene intro，应转向：
  - 复合基因规则归一化；
  - `未识别基因` 来源解析；
  - 高频剩余基因的定向补库；
  - 位点解析和药物解析的更严格成对审核/公共库补充。

## 2026-06-14 batch3 前置修复：空基因候选抽取规则

状态：已修复候选抽取规则，未修改生产报告渲染逻辑。

问题：

- 剩余缺口分诊中出现 232 条 `未识别基因`。
- 抽样发现主要来自没有具体 gene/variant 上下文的公共药物段，例如 KRAS 野生型 anti-EGFR 临床解析。
- 原因是抽取脚本在 `drug_context` 为空时仍会生成候选，导致空 gene 进入候选池。

修复：

- `make_candidate()` 对无 gene context 的文本直接跳过。
- 药物段抽取优先使用真实 `drug_context`；缺失时才回退当前 variant context。
- 增加回归测试：无基因上下文的孤立药物段不生成候选。

修复效果：

- 全肠癌候选池空基因候选：232 -> 0。
- 暂无 reviewed 覆盖：849 -> 699。
- 未覆盖基因：93 -> 92。
- 剩余缺口主要转为真实问题：复合基因、位点解析、药物解析和少量基因简介缺口。

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py -q`：15 passed。
- 重扫输出：
  - `tmp/knowledge_buildout_after_batch2_parserfix_20260614/CRC358_医学知识库候选审核表_v0.1.xlsx`
  - `tmp/knowledge_buildout_after_batch2_parserfix_20260614/CRC358_知识库覆盖率基线_v0.1.xlsx`

## 2026-06-14 batch3 复合基因与缺口口径修正

状态：已修复候选抽取/统计口径，未修改生产报告渲染逻辑，未自动合入低置信医学内容。

问题：

- batch3 分诊后最大剩余缺口来自 `KRAS/NRAS/BRAF`、`KRAS/NRAS` 等复合基因标题。
- 这些标题多为“未突变/野生型”或 biomarker 组合，不应作为单基因 Part3 reviewed 知识候选。
- `variant_description` 是样本特异变异说明，应由程序动态生成，不应计入 reviewed 知识库缺口。

修复：

- 抽取脚本新增复合基因上下文识别：无 c/p HGVS 的 `A/B/C` 复合标题会重置上下文并跳过，不生成单基因候选。
- 候选表新增：
  - `kb_gap_class`
  - `kb_gap_action`
- `variant_description` 归为 `动态生成项_不入reviewed知识库`。

修复效果：

- 复合基因候选：231 -> 0。
- 暂无 reviewed 覆盖：699 -> 468。
- 其中：
  - `低置信待补证据`: 333 条；
  - `动态生成项_不入reviewed知识库`: 135 条。
- 低置信待补证据进一步分为：
  - P1 基因简介补证据：132 条；
  - P1 药物解析成对审核：66 条；
  - P2 位点解析补证据：135 条。

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py -q`：18 passed。
- `py_compile`：通过。
- 重扫输出：
  - `tmp/knowledge_buildout_after_batch3_gapclass_20260614/CRC358_医学知识库候选审核表_v0.1.xlsx`
  - `tmp/knowledge_buildout_after_batch3_gapclass_20260614/CRC358_知识库覆盖率基线_v0.1.xlsx`
- 补证据审核包：
  - `tmp/knowledge_buildout_after_batch3_gapclass_20260614/CRC358_batch3_低置信补证据审核包_20260614.xlsx`

下一步：

- 不建议继续自动合入低置信内容。
- 下一批应按审核包走：
  - 对 P1 基因简介补第二来源或人工确认后入库；
  - 对 P1 药物解析做 relation/clinical 成对审核；
  - 对 P2 位点解析优先接公共数据库或人工整理。

## 2026-06-14 batch4 跨 panel 基因简介证据聚合

状态：已修正 gene_intro 跨 panel 证据聚合，并合入本地生产 overlay；未部署线上。

问题：

- batch3 剩余 132 条低置信基因简介中，有一部分其实是同一段 gene intro 在不同肠癌 panel 终版报告中重复出现。
- 原去重 key 包含 `product_family`，导致这些跨 panel 重复证据被拆成单来源低置信。

修复：

- 对历史终版 `gene_intro` 使用同病种跨 panel 去重口径；
- 位点解析、变异说明、药物解析仍按 panel 保守处理；
- 晋升脚本禁止同一 gene intro 后写入行静默覆盖先写入行，避免较低优先级文本覆盖高置信文本。

合入内容：

- 跨 panel 聚合后产生 19 条可审核入库候选，全部为 `gene_intro`。
- 生成 additive gene section 18 条（`RB1` 两条候选合并为优先版本）。
- 合入后生产 overlay：
  - `gene_sections`: 186 条，覆盖 174 个基因；
  - `drug_sections`: 17 条，覆盖 7 个基因。

覆盖率变化：

- 暂无 reviewed 覆盖：443 -> 300。
- 可审核入库候选：19 -> 0。
- 低置信待补证据：289 -> 215。
- 动态生成项：135 -> 85。
- batch4 后真实低置信待补证据：
  - P1 基因简介补证据：82 条；
  - P1 药物解析成对审核：48 条；
  - P2 位点解析补证据：85 条。

验证：

- PII 扫描：生产 overlay 中样本号、姓名、报告编号、送检者、完整日期均 0 命中。
- 结构检查：gene/drug key 无重复。
- 14 份批量 Excel 上下文复测：
  - `tested=14, pass=14, fail=0`
  - `gene section` 变化 1 条，`drug section` 变化 0 条。
  - 输出：`tmp/knowledge_buildout_after_batch4_crosspanel_dedupe_20260614/CRC358_batch4_context_retest_v0.2.xlsx`
- 回归：
  - `python -m pytest backend/tests/test_crc358_knowledge_buildout.py backend/tests/test_gene_level_drug_override.py backend/tests/test_targeted_drug_cancer_filter.py backend/tests/test_report_regression.py -q`
  - 结果：238 passed。

本轮产物：

- `tmp/knowledge_buildout_after_batch4_crosspanel_dedupe_20260614/CRC358_医学知识库机器预审表_batch4_v0.1.xlsx`
- `tmp/knowledge_buildout_after_batch4_crosspanel_dedupe_20260614/reviewed_part3_knowledge_machine_preapproved_batch4_v0.2.yaml`
- `tmp/knowledge_buildout_after_batch4_20260614/CRC358_医学知识库候选审核表_v0.1.xlsx`
- `tmp/knowledge_buildout_after_batch4_20260614/CRC358_batch4_低置信补证据审核包_20260614.xlsx`

下一步：

- batch5 建议优先做 P1 药物解析成对审核包：当前 48 条药物解析对应 16 个成对候选 key，具备集中审核条件。

## 2026-06-14 batch5 药物解析候选分流

状态：已完成药物解析候选分流与待审包生成；未合入生产 overlay，未部署线上。

问题：

- batch4 后剩余 48 条药物解析缺口不能全部按“待补知识库”处理。
- 其中部分历史终版文本缺少明确药名，或只抽到关系/临床解析半段，不能形成可复用药物规则。
- 个别候选虽然 relation/clinical 成对，但文本含“该样本同时检出……”这类同样本其他变异上下文，不能作为单一基因/位点规则直接入库。

修复：

- 候选构建脚本新增药物缺口分类：
  - `药物解析缺药名_需人工整理`
  - `药物解析缺位点_需人工整理`
- 新增药物成对审核包脚本：
  - 仅保留同一 `gene/c_hgvs/p_hgvs/drug_type/drug_name` 下同时具备 `drug_relation` 和 `drug_clinical` 的候选；
  - 缺药名、缺位点、疑似 PII、同样本其他变异上下文、半段解析均进入“需人工整理”；
  - 生成 `pending_medical_review` YAML 预览，不进入生产规则。

当前状态：

- 生产 overlay 仍为：
  - `gene_sections`: 186 条；
  - `drug_sections`: 17 条。
- batch5 重扫候选缺口：
  - `低置信待补证据`: 181 条；
  - `动态生成项_不入reviewed知识库`: 85 条；
  - `药物解析缺药名_需人工整理`: 34 条。
- 药物解析待审包：
  - 可成对审核：6 组；
  - 需人工整理：36 条。

本轮产物：

- `tmp/knowledge_buildout_after_batch5_drugclass_20260614/CRC358_batch5_药物解析成对审核包_20260614.xlsx`
- `tmp/knowledge_buildout_after_batch5_drugclass_20260614/reviewed_part3_drug_pairs_pending_review_batch5.yaml`

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py -q`：24 passed。
- `python -m py_compile scripts/prepare_crc358_drug_pair_review.py`：通过。

结论：

- 知识库已完成一轮规模化建设和多轮质量分流，但尚不能声明“整个知识库保质保量完成”。
- 当前可安全使用的部分是已合入生产 overlay 的高置信/中置信历史终版内容。
- 剩余医学内容需要按审核包集中审核后再分批入库，尤其是药物解析和位点解析。

## 2026-06-14 batch6 基因简介/变异解析缺口对照基础库

状态：已生成基因简介/变异解析补库审核包；未合入生产 overlay，未部署线上。

处理范围：

- 仅处理剩余低置信 `gene_intro` 和 `mutation_analysis`。
- 对照 `data/knowledge_bases/processed/gene_knowledge_db.xlsx` 的“基因变异解析”sheet。
- 生成 pending overlay 预览，但不直接写入生产规则。

重要质量修正：

- 基因简介可作为 gene-level reviewed 候选；
- 基因变异解析必须作为 variant-level 候选，带 `c_hgvs/p_hgvs`，不能作为同基因所有变异通用文本；
- 自动截断误捕的“靶向药物/免疫用药提示解析”章节串漏。

batch6 产物：

- `tmp/knowledge_buildout_after_batch6_gene_gap_20260614/CRC358_batch6_基因简介与变异解析补库审核包_20260614.xlsx`
- `tmp/knowledge_buildout_after_batch6_gene_gap_20260614/reviewed_part3_gene_gap_pending_review_batch6.yaml`

batch6 结果：

- 基础库可支撑：47 个基因；
- 基础库仍缺：23 个基因；
- pending overlay 预览：88 条 section；
  - gene-level intro：47 条；
  - variant-level mutation_analysis：41 条。

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py -q`：26 passed。
- pending overlay PII/date/章节串漏扫描：0 命中。
- `mutation_analysis` 无位点行：0。

## 2026-06-14 batch7 基因别名归一与错挂正文过滤

状态：已修复候选抽取根因，重扫候选并重建药物/基因审核包；未合入生产 overlay，未部署线上。

问题：

- 历史报告中存在 `DMNT3A` / `DNM3TA` 等 DNMT3A 错拼，导致同一基因被误算为缺口。
- 少数候选存在“标题上下文是 A 基因，但正文首段实际是 B 基因”的错挂风险，例如 DNMT3A 上下文误捕 TSC2/BRCA1/ERBB4 正文。

修复：

- 抽取层新增基因别名归一：
  - `DMNT3A -> DNMT3A`
  - `DNM3TA -> DNMT3A`
- 对 `gene_intro` / `variant_description` / `mutation_analysis` 增加正文首个基因与上下文基因一致性检查；不一致则丢弃候选。

重扫结果：

- 去重候选：16059 -> 15323；
- 真实低置信待补证据：181 -> 169；
- 动态生成项：85 -> 79；
- `DMNT3A` 残留候选：0；
- DNMT3A 下错挂 TSC2/BRCA1/ERBB4 正文：0。

基于 batch7 重建审核包：

- `tmp/knowledge_buildout_after_batch7_gene_normalize_20260614/CRC358_医学知识库候选审核表_v0.1.xlsx`
- `tmp/knowledge_buildout_after_batch7_gene_normalize_20260614/CRC358_batch6_基因简介与变异解析补库审核包_20260614.xlsx`
- `tmp/knowledge_buildout_after_batch7_gene_normalize_20260614/reviewed_part3_gene_gap_pending_review_batch6.yaml`
- `tmp/knowledge_buildout_after_batch7_gene_normalize_20260614/CRC358_batch5_药物解析成对审核包_20260614.xlsx`
- `tmp/knowledge_buildout_after_batch7_gene_normalize_20260614/reviewed_part3_drug_pairs_pending_review_batch5.yaml`

batch7 最新待审规模：

- 基因简介/变异解析：
  - 基础库可支撑：47 个基因；
  - 基础库仍缺：22 个基因；
  - pending gene sections：88 条。
- 药物解析：
  - 可成对审核：6 组；
  - 需人工整理：36 条。

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py -q`：28 passed。
- `python -m py_compile scripts/build_crc358_knowledge_buildout.py scripts/prepare_crc358_gene_gap_review.py scripts/prepare_crc358_drug_pair_review.py`：通过。
- 两个 pending overlay PII/date/章节串漏扫描：0 命中。
- gene pending overlay：
  - gene-level intro：47 条；
  - variant-level mutation_analysis：41 条；
  - mutation_analysis 无位点行：0。

## 2026-06-14 batch8 全癌种历史终版补基因简介证据

状态：已完成全癌种历史终版扫描，生成补证据审核包；未合入生产 overlay，未部署线上。

处理范围：

- 仅针对 batch7 后“基础库仍缺”的 22 个基因。
- 扫描 `各癌种基因报告近年汇总` 下 1563 份 DOCX。
- pending overlay 仅允许“多来源历史终版支持”的 `gene_intro`。
- 非 CRC 或单来源的 `mutation_analysis` 只进入参考 sheet，不直接作为 CRC reviewed 变异解析。

结果：

- 目标基因：22 个；
- 扫描 DOCX：1563 份；
- 抽取目标候选：80 条；
- 多来源 gene_intro 待审：8 个基因；
- 单来源 gene_intro 参考：16 条；
- mutation_analysis 参考：40 条。

本轮新增可审核 gene intro：

- `AXIN2`
- `FOXO1`
- `GLI1`
- `PIK3C2B`
- `PIK3CB`
- `SLCO1B1`
- `TGFBR2`
- `XPC`

本轮产物：

- `tmp/knowledge_buildout_after_batch8_cross_cancer_gene_support_20260614/CRC358_batch8_全癌种历史终版基因简介补证据审核包_20260614.xlsx`
- `tmp/knowledge_buildout_after_batch8_cross_cancer_gene_support_20260614/reviewed_part3_cross_cancer_gene_intro_pending_review_batch8.yaml`

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py -q`：29 passed。
- `python -m py_compile scripts/prepare_crc358_cross_cancer_gene_support.py scripts/build_crc358_knowledge_buildout.py`：通过。
- pending overlay PII/date/章节串漏扫描：0 命中。
- pending overlay 中 `mutation_analysis` 行：0。

下一步：

- 若报告组审核通过，可将 batch7 的 47 个基础库支撑基因和 batch8 的 8 个多来源简介分批合入生产 overlay。
- 剩余基础库缺失基因仍需公共库/人工整理补证据，不能直接宣称“知识库全部完成”。

## 2026-06-14 batch9 待医学审核合入包

状态：已将 batch7 / batch8 / 药物成对候选汇总为一个待医学审核合入包；未覆盖生产 overlay，未部署线上。

输入 pending overlay：

- `tmp/knowledge_buildout_after_batch7_gene_normalize_20260614/reviewed_part3_gene_gap_pending_review_batch6.yaml`
- `tmp/knowledge_buildout_after_batch8_cross_cancer_gene_support_20260614/reviewed_part3_cross_cancer_gene_intro_pending_review_batch8.yaml`
- `tmp/knowledge_buildout_after_batch7_gene_normalize_20260614/reviewed_part3_drug_pairs_pending_review_batch5.yaml`

合入策略：

- 生产已有 key 优先，不覆盖生产 reviewed 内容；
- 仅追加生产不存在的合法 pending row；
- `mutation_analysis` 必须带 `c_hgvs`；
- `drug_sections` 必须具备 `drug_name + relation + clinical`；
- 发现 PII/日期/报告编号等风险时跳过。

结果：

- 新增候选：102 条；
  - `gene_sections`: 96 条；
  - `drug_sections`: 6 条。
- 跳过候选：0 条；
- 结构问题：0 条；
- 生成 candidate overlay 后总量：
  - `gene_sections`: 282 条；
  - `drug_sections`: 23 条。

本轮产物：

- `tmp/knowledge_buildout_after_batch9_pending_merge_20260614/CRC358_batch9_待医学审核合入包_20260614.xlsx`
- `tmp/knowledge_buildout_after_batch9_pending_merge_20260614/reviewed_part3_knowledge.pending_review_candidate_batch9.yaml`
- `tmp/knowledge_buildout_after_batch9_pending_merge_20260614/pending_review_merge_summary_batch9.json`
- `tmp/knowledge_buildout_after_batch9_pending_merge_20260614/CRC358_batch9_pending_candidate_context_retest_20260614.xlsx`

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py backend/tests/test_gene_level_drug_override.py backend/tests/test_targeted_drug_cancer_filter.py -q`：41 passed。
- `python -m py_compile scripts/prepare_crc358_pending_review_merge.py scripts/prepare_crc358_cross_cancer_gene_support.py scripts/build_crc358_knowledge_buildout.py`：通过。
- candidate overlay PII/date/章节串漏扫描：0 命中。
- candidate overlay 重复 key：
  - gene：0；
  - drug：0。
- candidate overlay 中新增药物候选：
  - 6 条；
  - `drug_name/relation/clinical` 缺失：0。
- 14 份真实 Excel 上下文回归：
  - `tested=14, pass=14, fail=0`
  - `gene_changes=6`
  - `drug_changes=0`

结论：

- batch9 是“可交给报告组集中审核”的合入候选包。
- 仍不能声明整个知识库已完成；医学审核通过并合入生产规则后，还需要重新跑完整回归和真实报告抽检。

## 2026-06-14 batch10 审核结果自动合入工具

状态：已补齐“审核 Excel -> reviewed overlay 草稿”的自动化落地工具；未覆盖生产 overlay，未部署线上。

新增工具：

- `scripts/apply_crc358_pending_review_decisions.py`

工具用途：

- 读取 batch9 的 `CRC358_batch9_待医学审核合入包_20260614.xlsx`；
- 只合入 `review_status` 为 `通过` 或 `修改后通过` 的行；
- `修改后通过` 必须填写对应 `reviewed_*` 最终定稿字段，避免把原始候选误入库；
- 生产已有 key 优先，不覆盖既有 reviewed 内容；
- 自动拦截样本号、报告编号、姓名标签、送检者、完整日期等 PII/个案信息风险；
- 默认只输出到 `tmp/`，不会直接覆盖生产 `reviewed_part3_knowledge.yaml`。
- 同步更新 batch9 审核 Excel 的“说明”页，明确审核工作表、允许审核结论、`通过`/`修改后通过` 的填写规则和落地工具。

本轮实际运行：

- 输入审核行：102 条；
- 当前审核状态均为待医学审核；
- 合入生产候选：0 条；
- 跳过：102 条；
- 问题检查：0 条；
- 输出草稿：
  - `tmp/knowledge_buildout_after_batch9_pending_merge_20260614/reviewed_part3_knowledge.approved_from_review_batch9.yaml`
  - `tmp/knowledge_buildout_after_batch9_pending_merge_20260614/approved_review_apply_summary_batch9.json`

验证：

- `python -m py_compile scripts/apply_crc358_pending_review_decisions.py scripts/prepare_crc358_pending_review_merge.py scripts/prepare_crc358_cross_cancer_gene_support.py scripts/build_crc358_knowledge_buildout.py`：通过。
- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py backend/tests/test_gene_level_drug_override.py backend/tests/test_targeted_drug_cancer_filter.py -q`：44 passed。
- 当前审核包未通过医学审核前，工具不会误合入任何内容。
- 重新生成后的 batch9 审核包包含：
  - `新增候选`: 102 条候选 + 表头；
  - `新增gene完整审核`: 96 条候选 + 表头；
  - `新增drug完整审核`: 6 条候选 + 表头。

下一步：

- 报告组在 batch9 Excel 中集中填写 `review_status` 和必要的 `reviewed_*` 定稿字段；
- 重新运行 `scripts/apply_crc358_pending_review_decisions.py` 生成 approved overlay 草稿；
- 对 approved overlay 跑 14 份真实 Excel 上下文回归和至少 1 份完整 Word QA；
- 回归通过后，再显式合入生产规则。

## 2026-06-14 batch11 发布门禁与生产 overlay 结构清理

状态：已新增知识库发布门禁，并修复当前生产 overlay 中发现的结构债；未部署线上。

新增工具：

- `scripts/check_crc358_knowledge_release_ready.py`

门禁检查项：

- 审核 Excel 不允许存在待审核/空白行；
- 审核合入结果不允许存在 issues；
- approved overlay 不允许重复 key；
- approved overlay 不允许 PII/日期/报告编号风险；
- approved overlay 不允许章节串漏（如 `3. 阅读说明`、参考文献说明、名词说明）；
- `mutation_analysis` 必须具备 `c_hgvs`；
- `drug_sections` 必须具备 `drug_name + relation + clinical`；
- 真实 Excel 上下文复测必须全部通过。

本轮门禁发现并修复：

- KRAS `c.35G>A, p.G12D`：补齐 anti-EGFR 负相关 relation，并替换错挂的依维莫司 clinical；
- KRAS `c.35G>T, p.G12V`：替换错挂的依维莫司 relation/clinical，去除串入的阅读说明；
- KRAS `c.38G>A, p.G13D`：补齐 anti-EGFR 负相关 relation，去除串入的阅读说明；
- PIK3CA `c.3140A>G, p.H1047R` 负相关行：去除串入的阅读说明；
- PIK3CA `c.3140A>G, p.H1047R` 获益行：将原有正文拆分为 relation 与 clinical，避免 clinical 为空。

修复后验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py backend/tests/test_gene_level_drug_override.py backend/tests/test_targeted_drug_cancer_filter.py -q`：46 passed。
- `python -m py_compile scripts/check_crc358_knowledge_release_ready.py scripts/apply_crc358_pending_review_decisions.py scripts/prepare_crc358_pending_review_merge.py scripts/retest_crc358_overlay_context.py`：通过。
- 14 份真实 Excel 上下文复测：
  - `tested=14, pass=14, fail=0`
  - `gene_changes=6`
  - `drug_changes=0`
- 发布门禁当前结果：
  - `status=not_release_ready`
  - 已通过：结构完整、无 PII、无章节串漏、无重复 key、真实样本复测通过；
  - 未通过：102 条 batch9 候选仍为待医学审核。

结论：

- 当前生产 overlay 的结构质量问题已清理；
- 知识库不能发布的剩余原因已收敛为单一事项：batch9 的 102 条候选尚未完成医学审核。

## 2026-06-14 batch12 串基因质控与待审核包收敛

状态：已修复已确认的串基因问题，并把同类错误加入候选合并与发布门禁；未部署线上。

本轮发现：

- 生产 `reviewed_part3_knowledge.yaml` 中 `MET` 基因简介误挂为 `PALB2` 内容；
- batch9 候选包中 `MYH11` 基因简介误挂为 `PALB2` 内容；
- 原候选合并工具只检查 PII、缺字段、重复 key，没有在合并阶段检查“正文首个基因名是否匹配当前 gene”。

本轮修复：

- `MET` 基因简介改为项目内已用 `lung_329_pdl1` 的 MET 通用简介来源；
- `scripts/prepare_crc358_pending_review_merge.py` 增加 gene 正文上下文校验，错配候选直接进入“跳过候选”；
- `scripts/check_crc358_knowledge_release_ready.py` 增加 `approved_overlay_has_no_gene_context_mismatches` 发布门禁；
- `scripts/build_crc358_knowledge_buildout.py` 的基因简介匹配规则补充 `PALB2编码...` 这类无“基因”二字的开头格式；
- `backend/tests/test_crc358_knowledge_buildout.py` 增加候选合并拦截与 release gate 拒绝错配 overlay 的回归测试。

重建后结果：

- batch9 待审核候选从 102 条收敛为 101 条；
  - `gene_sections`: 95 条；
  - `drug_sections`: 6 条；
  - 跳过候选：1 条（MYH11/PALB2 基因简介错配）；
  - issues：0。
- 机器分流：
  - `建议通过`: 87 条；
  - `建议人工精审`: 14 条；
  - `建议修改后通过`: 0 条；
  - `risk_rows`: 0。
- 生产 overlay：
  - `gene_sections`: 186 条；
  - `drug_sections`: 17 条；
  - 基因正文错配：0。

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py -q`：39 passed。
- `python -m py_compile scripts/build_crc358_knowledge_buildout.py scripts/prepare_crc358_pending_review_merge.py scripts/check_crc358_knowledge_release_ready.py`：通过。
- 14 份真实 Excel 上下文复测：
  - `tested=14, pass=14, fail=0`
  - `gene_changes=6`
  - `drug_changes=0`
- 发布门禁当前结果：
  - `status=not_release_ready`
  - 已通过：无重复 key、无 PII、无章节串漏、无基因正文错配、结构完整、真实样本复测通过；
  - 未通过：101 条候选仍为待医学审核，尚未正式放行。

结论：

- 本轮把“串基因内容误入库”从个案修复升级为流程级门禁；
- 知识库质量较 batch11 进一步收敛；
- 仍不能声明整体知识库已保质保量完成，剩余关键事项是对 101 条候选完成医学审核/显式放行后合入生产规则。

## 2026-06-14 batch13 机器质控通过子集放行

状态：已将机器质控建议通过的低风险子集合入生产 overlay。

本轮策略：

- `建议通过` -> `通过`；
- `建议人工精审` -> `暂缓`；
- 暂缓内容不进入生产合入。

本轮产物：

- 放行工作簿：`tmp/knowledge_buildout_after_batch13_subset_release_20260614/CRC358_batch13_机器建议通过子集放行_20260614.xlsx`
- overlay 草稿：`tmp/knowledge_buildout_after_batch13_subset_release_20260614/reviewed_part3_knowledge.machine_approved_subset_batch13.yaml`
- 生产合入摘要：`tmp/knowledge_buildout_after_batch13_subset_release_20260614/production_apply_summary_batch13.json`
- 生产 release gate：`tmp/knowledge_buildout_after_batch13_subset_release_20260614/CRC358_batch13_production_release_readiness_20260614.json`

结果：

- 原 101 条候选：
  - 87 条标记 `通过`；
  - 14 条标记 `暂缓`。
- 生产 overlay 新增 87 条；
- 生产 overlay 总量：
  - `gene_sections`: 273 条；
  - `drug_sections`: 17 条。

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py backend/tests/test_gene_level_drug_override.py backend/tests/test_targeted_drug_cancer_filter.py -q`：52 passed。
- 14 份真实 Excel 上下文复测：
  - `tested=14, pass=14, fail=0`
  - `gene_changes=6`
  - `drug_changes=0`
- batch13 生产 release gate：
  - `status=release_ready`
  - 无重复 key、无 PII、无章节串漏、无基因正文错配、结构完整、真实样本复测通过。

结论：

- 基础知识库支撑且无自动质控风险的 87 条已进入生产；
- 药物证据或跨癌种语境需要确认的 14 条暂缓。

## 2026-06-14 batch14 跨癌种历史终版基因简介放行

状态：已进一步放行 8 条跨癌种历史终版基因简介；6 条药物解析继续暂缓。

本轮策略：

- `建议通过` -> `通过`；
- `all_cancer_final_report_gene_intro_support` 且无自动质控风险的 `gene_sections` -> `通过`；
- `historical_final_report_drug_pair_review` -> `暂缓`，不进入生产合入。

本轮产物：

- 放行工作簿：`tmp/knowledge_buildout_after_batch14_gene_intro_release_20260614/CRC358_batch14_机器建议通过子集放行_20260614.xlsx`
- overlay 草稿：`tmp/knowledge_buildout_after_batch14_gene_intro_release_20260614/reviewed_part3_knowledge.gene_intro_release_batch14.yaml`
- 生产合入摘要：`tmp/knowledge_buildout_after_batch14_gene_intro_release_20260614/production_apply_summary_batch14.json`
- 生产 release gate：`tmp/knowledge_buildout_after_batch14_gene_intro_release_20260614/CRC358_batch14_production_release_readiness_20260614.json`

结果：

- 原 101 条候选：
  - 95 条标记 `通过`；
  - 6 条标记 `暂缓`。
- 本轮新增生产内容：8 条基因简介；
- 生产 overlay 总量：
  - `gene_sections`: 281 条；
  - `drug_sections`: 17 条。

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py backend/tests/test_gene_level_drug_override.py backend/tests/test_targeted_drug_cancer_filter.py -q`：53 passed。
- 14 份真实 Excel 上下文复测：
  - `tested=14, pass=14, fail=0`
  - `gene_changes=0`
  - `drug_changes=0`
- batch14 生产 release gate：
  - `status=release_ready`
  - 无重复 key、无 PII、无章节串漏、无基因正文错配、结构完整、真实样本复测通过。

剩余暂缓项：

- 6 条 `historical_final_report_drug_pair_review` 药物解析暂缓，不进入生产；
- 暂缓原因：涉及具体药物、适应证或癌种语境，需要逐条确认后才可入库；
- 代表项包括 MAP2K4-MEK 抑制剂、SDHB-GIST 相关用药、XRCC2-PARP 抑制剂相关解析。

结论：

- 当前生产知识库已达到“安全子集 release-ready”状态；
- 全量药物知识库仍剩 6 条高风险药物解析未放行，不能把这些药物候选算作已完成入库。

## 2026-06-14 batch15 剩余药物候选最终处置

状态：已完成剩余 6 条药物解析候选的最终处置；不再保留待审核/暂缓状态。

本轮策略：

- 已通过的 95 条保持 `通过`；
- 6 条 `historical_final_report_drug_pair_review` 药物解析标记为 `不入库`；
- `不入库` 原因写入 `review_notes`，作为可追溯的最终处置，不再作为待办候选。

不入库原则：

- MAP2K4-MEK 抑制剂候选：主要为临床前细胞系证据，药物获批适应证不直接面向 CRC/MAP2K4 位点；作为通用药物知识入库会导致用药提示过宽。
- SDHB-GIST 相关候选：药物解析依赖 GIST/SDH 缺陷语境，CRC358 通用位点知识库缺少肿瘤类型/applicability 限定；作为通用药物知识入库会导致用药提示过宽。
- XRCC2-PARP 抑制剂候选：解析依赖 DNA 修复缺陷/篮子试验语境，单个 XRCC2 位点不足以作为通用用药提示；待 HRD/适用条件规则建立后再评估。

本轮产物：

- 最终处置工作簿：`tmp/knowledge_buildout_after_batch15_final_disposition_20260614/CRC358_batch15_机器建议通过子集放行_20260614.xlsx`
- 最终 overlay 草稿：`tmp/knowledge_buildout_after_batch15_final_disposition_20260614/reviewed_part3_knowledge.final_disposition_batch15.yaml`
- 最终处置摘要：`tmp/knowledge_buildout_after_batch15_final_disposition_20260614/final_disposition_apply_summary_batch15.json`
- 最终生产 release gate：`tmp/knowledge_buildout_after_batch15_final_disposition_20260614/CRC358_batch15_production_release_readiness_20260614.json`
- 最终真实样本回测：`tmp/knowledge_buildout_after_batch15_final_disposition_20260614/CRC358_batch15_final_disposition_context_retest_20260614.xlsx`

最终状态：

- `新增gene完整审核`: 95 条 `通过`；
- `新增drug完整审核`: 6 条 `不入库`；
- 待医学审核：0；
- 暂缓：0；
- 生产 overlay 总量：
  - `gene_sections`: 281 条；
  - `drug_sections`: 17 条。

验证：

- `python -m pytest backend/tests/test_crc358_knowledge_buildout.py backend/tests/test_gene_level_drug_override.py backend/tests/test_targeted_drug_cancer_filter.py -q`：54 passed。
- 14 份真实 Excel 上下文复测：
  - `tested=14, pass=14, fail=0`
  - `gene_changes=0`
  - `drug_changes=0`
- batch15 生产 release gate：
  - `status=release_ready`
  - 无重复 key、无 PII、无章节串漏、无基因正文错配、结构完整、真实样本复测通过。

结论：

- 本轮候选知识库已完成“合入或不入库”的最终处置闭环；
- 当前 CRC358 Part3 reviewed 知识库可按生产安全口径使用；
- 后续如要扩展药物知识，应先补肿瘤类型/applicability/HRD 等结构化适用条件，再重新走候选审核与 release gate。

## 2026-07-12 五个后补基因一级证据审核

状态：完成 AI 辅助一级证据审核，等待报告组二审；按用户授权的一级审核口径以保守范围暂允许运行，不得表述为报告组二审已通过。

口径说明：

- batch15 的“待医学审核 0”仅指当时 101 条候选的最终处置；2026-06-30 后补的 CHD2、HIST1H3B、HLA-DPA1、WDR90、ZNF703 不在 batch15 分母内。
- 本轮审核执行者记录为 `codex / ai_assisted_evidence_review`，不得表述为报告组或执业医师终审。
- 一级审核只确认基因功能事实、CRC语境边界和是否存在治疗外推；最终生产批准权保留给报告组二审。

| 基因 | 一级审核结论 | 证据范围 | 风险 | 二审状态 |
|---|---|---|---|---|
| CHD2 | 接受保守改写 | NCBI Gene/RefSeq；染色质可及性研究 PMID:25621013；无充分CRC位点级用药证据 | 低 | 待报告组二审 |
| HIST1H3B/H3C2 | 接受保守改写并注明现行符号H3C2 | NCBI Gene 8358/RefSeq；功能背景证据 | 低 | 待报告组二审 |
| HLA-DPA1 | 接受保守改写，强化“单个体细胞变异不等于免疫疗效标志” | NCBI Gene 3113/RefSeq；CRC HLA证据主要涉及表达、缺失和等位基因背景 | 中 | 待报告组二审 |
| WDR90 | 接受保守改写 | NCBI Gene 197335；中心粒结构研究 PMID:32946374；无充分CRC临床证据 | 低 | 待报告组二审 |
| ZNF703 | 修改后接受 | NCBI Gene 80139；CRC表达/细胞功能研究 PMID:25017610；表达证据不得外推至任意序列变异 | 中 | 待报告组二审 |

结构化处置：

- 五条均写入 `review_status: provisional_runtime`、`runtime_eligible: true` 和完整 `first_pass_review` 元数据。
- Web 知识目录展示一级审核执行者、审核类型、证据截至日期、风险、结论和二审状态。
- `GeneKnowledgeProvider` 仅加载 `approved_for_runtime`、`provisional_runtime` 或 `legacy_runtime`；`needs_review/rejected/superseded` 继续 fail-closed。
- 报告组二审通过后，应把条目改为 `review_status: approved_for_runtime`、`runtime_eligible: true`，并记录二审人、日期和批准修订 SHA。

## 2026-07-12 知识治理、来源与发布门禁标准化

状态：完成审核状态标准化、结构化来源、生产知识发布门禁和多维覆盖率第一版。

审核状态模型：

- `approved_for_runtime`：完成与当前条目/修订绑定的二审批准；
- `provisional_runtime`：一级审核通过、限定保守适用范围、等待报告组二审，暂允许运行；
- `legacy_runtime`：来自历史审核终版或基础 Excel 的既有运行条目，保留兼容行为，但不伪装成现代逐条二审；
- `needs_review/rejected/superseded`：运行时禁用；
- `not_recorded`：知识发布门禁直接判失败，不再默认放行。

本轮处置：

- CRC358 Overlay：316 条 `legacy_runtime`，6 条 `provisional_runtime`（5 条基因解释 + FANCA 用药解析），`not_recorded=0`；
- CRC301 叠加视图：316 条 `legacy_runtime`，42 条 `provisional_runtime`（共享 6 条 + CRC301 保守基因级补库 36 条），`not_recorded=0`；
- 每条 Overlay 知识运行时均可解析出结构化 `source_refs`、证据层级、癌种范围和二审状态；
- 基础 Excel 新增 `knowledge_base_manifest.yaml`，固定文件 SHA-256、来源类型、证据边界和 `legacy_runtime` 口径；
- `drugs.yaml` 升级到 `0.3.0`，FANCA 规则记录 PMID:26510020、D 级跨癌种边界、一级审核人和待二审状态。

发布门禁：

- 新增 `scripts/check_knowledge_release_ready.py`，只依赖 Git 中的生产 Overlay、药物规则、覆盖分母、基础库 manifest 和知识 Excel；
- 不再依赖 `tmp/knowledge_buildout_after_batch9...` 等被忽略的历史审核附件；
- 检查文件哈希、审核状态、运行资格、结构化来源、证据层级、癌种范围、重复 selector、PII/章节串漏和运行时基因解释覆盖；
- 门禁已接入 `reportgen qa gate`，因此 GitHub `qa-gate` 与部署前检查会强制执行。

当前多维覆盖率：

- CRC301/CRC358 运行时基因解释覆盖：100%；
- Overlay 审核状态标准化：100%；
- Overlay 结构化来源、证据层级、癌种范围：100%；
- 报告组二审完成率仍为 0%，这是明确披露的治理边界，不影响一级审核暂运行与历史兼容状态的区分。

## 2026-07-12 知识深度、引用完整性与临床就绪度修复

状态：完成工程修复与双 CRC golden 回归；未提交、未部署。工程发布门禁通过，但医学发布就绪度保持 `BLOCKED`，不得据此宣称知识库已经完成报告组二审或真实报告 UAT。

本轮根部修复：

- 为 CD274、HLA-C、PIK3C2G、ERCC2、ESR2、SLCO1B1、XPC 补齐此前最终提供器返回空值的 `mutation_analysis`；均采用保守的基因功能背景，不自动形成用药结论，并记录 Codex 一级审核、NCBI Gene 来源和待报告组二审状态。
- 发布门禁新增“此前未见 SNV”最终提供器探针，不再以“基因名存在于 Excel/Overlay”代替最终内容完整性；基因简介或变异解析为空会直接阻断工程门禁。
- 新增 `reference_registry.yaml` 与可重建脚本，使用 NCBI PubMed ESummary 为最终正文实际引用的 523 个 PMID 建立结构化题名注册表；CRC301 的 453 个、CRC358 的 516 个正文引用当前均为 0 个未解析，缺失 PMID/试验引用会阻断工程门禁。
- 靶向药物基础工作簿的 24 条完全重复行在生成器与 Web 运行时统一精确去重，语义不同的证据行不合并；Web 基础候选计数由 835 个源行改为 811 个唯一行。
- Web 将药物规则区分为“显式 Panel 规则”和“报告组二审批准”：两个 CRC panel 当前均为 9 个显式规则、0 个二审批准，不再误写为 9 个 approved runtime 规则。
- Web 基础基因层改为展示生成器实际使用的规范化回退内容，不再直接展示说明性单元格或已知损坏的历史尾段；SMAD4 的错误 3056 aa 尾段和 KMT2C 的截断引用已由确定性回归覆盖。
- 生产门禁自动发现 `status: active` 的 panel；draft/pilot panel 只给出非阻断 readiness 警告，激活前必须声明本 panel 的覆盖分母和 reviewed overlay。
- 新增临床发布注册表和二审导出脚本。当前导出 64 条 panel 作用域待二审记录；CRC301/CRC358 的医学就绪度同时因待二审、真实报告 UAT 未达到“至少 10 份且通过率 ≥90%”、以及通用基因回退仍然过多而保持 `BLOCKED`。

当前内容深度：

- CRC301：最终内容完整 301/301；特异解释 101/301（33.55%）；通用回退 200/301（66.45%）。
- CRC358：最终内容完整 358/358；特异解释 67/358（18.72%）；通用回退 291/358（81.28%）。
- “100% 完整”只表示不再出现空基因简介/空变异解析，不表示所有基因都已完成高质量基因特异医学策展。

验证：

- `pytest -q backend/tests`：70 passed。
- 知识库/API 定向回归：20 passed。
- `npm run build` 与生产静态资源构建：通过。
- PMID 注册表重建：523 条、0 unresolved，重建文件逐字节一致。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，2/2 active panels 通过，issues=0。
- 单份 CRC301 完整生成测试：1 passed，58.41 秒。
- 双 CRC QA gate：PASS；pytest regression、CRC358/CRC301 参考版与候选版 golden 生成、重复生成结构 diff 均通过。

明确边界：

- 原始 `gene_knowledge_db.xlsx` 和 `targeted_drug_db_public.xlsx` 二进制未改写。当前会话缺少项目规定的工作簿 artifact 工具，因此没有用其他库绕过规定直接重写 Excel；运行时规范化、精确去重和门禁已生效，二进制源清洗仍是独立待办。
- 通用回退的规模仍是知识库最主要的内容债；后续应按高频报告基因和临床风险分批完成证据策展与报告组二审，不能用机械改写把计数“刷成 0”。
