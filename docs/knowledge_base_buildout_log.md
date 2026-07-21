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

## 2026-07-21 CRC 医学知识深度分批完善：P0 第一批

状态：完成 P0 一级医学审核候选与运行时接入；工程门禁通过，仍等待报告组二审和病例 UAT，不得称为整个知识库医学完成。

本轮方法：

- 新增 `scripts/analysis/22_profile_crc_medical_knowledge.py`，直接加载 Panel 实际运行时提供器，对此前未见 SNV 的最终正文做内容深度分析；输出位于 `.work/crc_medical_knowledge/knowledge_depth_inventory.json`。
- 剩余通用解释按固定优先级排队：P0=报告展示面或精确用药规则相关基因，P1=CRC 重要基因，P2=基础药物候选库涉及基因，P3=其余 Panel 基因；分类按 P0→P1→P2→P3 排他执行。
- 本轮 P0 九基因为 AKT1、ALK、EGFR、ERBB2、FLT3、MET、RET、ROS1、SETD2。每条只补“稳定基因功能＋事件类型边界”，不新增获益、耐药、证据等级或药物匹配。
- 证据采用 NCBI Gene/RefSeq 官方基因记录，并以 CAP/ASCP/AMP/ASCO 结直肠癌分子标志物指南约束癌种和预测性标志物边界。
- 所有条目为 `provisional_runtime`，审核执行者为 `codex / ai_assisted_evidence_review`，二审状态为 `pending_report_group_review`，风险为 `high_requires_secondary_review`。
- 精确位点规则保持最高优先级；FLT3 p.G846D、EGFR p.G796D、SETD2 p.G1644* 的现有逐位点解释回归通过。本层 `drug_sections: []`，不得由基因名称直接推导用药。

量化变化：

- CRC301：特异解释由 101/301（33.55%）提高到 110/301（36.54%）；通用回退由 200 降到 191，P0 剩余 0，P1/P2/P3 剩余分别为 5/52/134。
- CRC358：特异解释由 67/358（18.72%）提高到 76/358（21.23%）；通用回退由 291 降到 282，P0 剩余 0，P1/P2/P3 剩余分别为 10/54/218。
- 固定蛋白/结构域覆盖仍为 CRC301 301/301、CRC358 358/358；运行时引用完整性仍为 0 个未解析 PMID/试验标识。

验证：

- P0 Overlay 治理校验：9/9 行通过，结构化来源、证据层级、癌种范围和审核元数据完整，二审完成行数为 0。
- 知识治理、Web 目录/API 与语义回归：43 passed。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，CRC301/358 均 issues=0。
- 医学发布状态仍为 `BLOCKED`：CRC301 仍有 191 个通用回退，CRC358 仍有 282 个；报告组二审完成率 0%，两 Panel UAT 均为 0/10。

下一批：

- CRC301 P1：ERBB3、FAT1、GNAS、LRP1B、ZFHX3。
- CRC358 P1：ACVR2A、AMER1、ERBB3、FAT1、FAT4、GNAS、LRP1B、MUTYH、PTPRT、ZFHX3。
- P1 完成后再进入 P2；任何药物方向、适应证或位点外推仍必须拆成独立证据规则，不随基因级正文批量放行。

## 2026-07-21 CRC 医学知识深度分批完善：P1 第一批

状态：完成 P1 一级医学审核候选与运行时接入；P0/P1 运行时通用回退均已清零。条目仍为待报告组二审，病例 UAT 尚未开始，因此医学发布状态继续保持 `BLOCKED`。

本轮范围：

- CRC301：ERBB3、FAT1、GNAS、LRP1B、ZFHX3。
- CRC358：在上述共享基因之外，补充 ACVR2A、AMER1、FAT4、MUTYH、PTPRT。
- 每条仅陈述稳定的基因功能、事件类型和适用边界；本层 `drug_sections: []`，不由基因名或普通错义变异自动推导用药、疗效或预后。
- MUTYH 明确区分单个肿瘤体细胞变异与胚系/双等位致病状态；ERBB3、FAT1/FAT4、LRP1B 等明确区分表达、扩增、功能缺失与普通序列变异，避免跨事件外推。
- 来源采用 NCBI Gene/RefSeq 官方记录，并以 CAP/ASCP/AMP/ASCO 结直肠癌分子标志物指南约束 CRC 预测性结论边界；所有条目均记录 `codex / ai_assisted_evidence_review`、证据截至日期和 `pending_report_group_review`。

量化变化：

- CRC301：特异解释提高到 115/301（38.21%）；通用回退降到 186，P0/P1/P2/P3 剩余分别为 0/0/52/134。
- CRC358：特异解释提高到 86/358（24.02%）；通用回退降到 272，P0/P1/P2/P3 剩余分别为 0/0/54/218。
- 固定蛋白/结构域覆盖保持 CRC301 301/301、CRC358 358/358；精确位点知识仍优先于基因级回退。

验证：

- P1 Overlay 治理校验：10/10 行通过，结构化来源、证据层级、癌种范围和审核元数据完整，二审完成行数为 0。
- CRC301/358 Panel 作用域验证通过：CRC358 专属 5 条未进入 CRC301；共享 5 条在两个 Panel 均生效。
- ACVR2A p.R438Efs*19、AMER1 p.R497*、FLT3 p.G846D、EGFR p.G796D、GNAS p.E344K、LRP1B p.D663N、SETD2 p.G1644* 的既有精确位点正文优先级回归通过。
- P0/P1 定向知识治理、Web 目录/API 与语义回归：59 passed。
- `pytest -q backend/tests` 全量回归：588 passed、4 skipped；无失败。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，CRC301/358 均 issues=0；医学发布状态仍按上述边界保持 `BLOCKED`。

剩余边界：

- 下一批为 P2：CRC301 52 个、CRC358 54 个基础药物候选库涉及但仍使用通用回退的基因；候选存在不等于可进入用药规则。
- P3 仍有 CRC301 134 个、CRC358 218 个其他 Panel 基因需要分批策展。
- 报告组二审完成率仍为 0%，CRC301/358 真实报告 UAT 仍为 0/10；在这两项完成前，不得称为“整个知识库医学审核完成”。

## 2026-07-21 CRC 医学知识深度分批完善：P2 完成

状态：完成 CRC301 的 52 个、CRC358 的 54 个基础药物候选库相关通用回退策展；P0/P1/P2 运行时残余均为 0。候选库成员身份未被升级为生产药物规则，全部条目仍等待报告组二审。

分批边界：

- P2-A：18 个激酶、受体和信号基因，重点区分融合、重排、扩增、激活热点与普通 SNV；其中 AKT3、CSF3R 仅适用于 CRC358。
- P2-B：16 个表达、扩增、配体轴和细胞周期基因，重点阻止表达/CNV/融合和普通序列变异相互替代；其中 ESR1 仅适用于 CRC301。
- P2-C：21 个抑癌、DNA 修复、遗传易感、表观遗传或血液肿瘤语境基因，重点阻止单个体细胞位点被扩展为胚系状态、双等位失活、HRD、遗传综合征或药物标志物；其中 BCOR 仅适用于 CRC358。
- 三个 Overlay 合计覆盖 55 个唯一基因，均为 `provisional_runtime`、`pending_report_group_review`，且 `drug_sections: []`。
- 稳定基因功能来自逐基因 NCBI Gene/RefSeq 官方记录；CAP/ASCP/AMP/ASCO CRC 分子标志物指南用于约束癌种和预测性标志物外推边界。

量化变化：

- CRC301：特异解释由 115/301（38.21%）提高到 167/301（55.48%）；通用回退降到 134，P0/P1/P2/P3 剩余为 0/0/0/134。
- CRC358：特异解释由 86/358（24.02%）提高到 140/358（39.11%）；通用回退降到 218，P0/P1/P2/P3 剩余为 0/0/0/218。
- P2 清零只表示所有基础药物候选相关基因已有保守的基因级事件边界，不表示这些候选获得药物匹配、证据等级或报告组批准。

回归保护：

- EPHA2、DDR2、FGFR1、BCL2、CCND1、CCND2、FGF4、HIF1A、NRG1、PDGFB、FLCN、EZH2、MYD88、NPM1 等既有精确位点正文保持更高优先级。
- 三批 Panel 作用域均有正反例；CRC301 不加载 AKT3、CSF3R、BCOR，CRC358 不加载 ESR1。
- 知识治理、Web 目录/API、事件边界和精确位点优先级定向回归：62 passed。
- `pytest -q backend/tests` 全量回归：591 passed、4 skipped；无失败。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，CRC301/358 来源、审核字段和运行时覆盖均为 100%，issues=0。

剩余边界：

- P3 仍有 CRC301 134 个、CRC358 218 个其他 Panel 基因需要按功能类别继续策展。
- 现有 legacy 精确位点正文和历史药物证据仍需独立做证据归因审计；基因级 fallback 完善不能替代对旧位点结论的逐条复核。
- 报告组二审和真实病例 UAT 尚未开始，因此医学发布状态继续保持 `BLOCKED`。

## 2026-07-21 CRC 医学知识深度分批完善：P3-A DNA 修复与遗传易感

状态：完成 P3 第一批 26 个共享基因的一级医学策展，并同步纠正 6 条历史精确位点中的跨癌种/跨事件外推和段落串漏；未新增药物规则，仍等待报告组二审。

本轮范围：

- 基因级 fallback：ATRX、BLM、BMPR1A、FAM175A/ABRAXAS1、FANCE、FANCF、FANCG、FANCI、FH、GALNT12、HNF1A、HOXB13、MRE11A/MRE11、MSH3、NBN、PMS1、POLD1、RAD51、RAD52、RAD54B、RECQL4、SDHC、TERC、TMEM127、TP53BP1、XRCC2。
- 统一边界：肿瘤单个位点不自动建立胚系来源、双等位失活、遗传综合征、MMR/HRD 表型或药物敏感性；MSI/MMR 和用药仍必须由独立验证结果与精确规则判断。
- 现行符号迁移显式披露：FAM175A 对应 ABRAXAS1，MRE11A 对应 MRE11；运行键仍保留 Panel 历史符号以兼容输入。
- 来源为逐基因 NCBI Gene/RefSeq 官方记录，并以 AMP/ASCO/CAP 体细胞变异解释规范和 CAP CRC 分子标志物指南约束临床外推。

精确位点根部纠正：

- FANCI p.R960Q：删除由 FANCI 功能缺失、其他位点或其他癌种研究外推的 PARP/免疫治疗结论。
- ATRX p.R1093Gfs*25：保留潜在功能缺失解释，删除其他癌种模型向本位点 PARP 敏感性的外推及非结构化引用。
- GALNT12 p.R198C：由“位于结构域可能影响功能”改为缺少位点级功能和临床证据的保守结论，并区分肿瘤与胚系易感。
- HOXB13 p.W195Gfs*84：删除由甲基化/表达研究推导序列变异致癌性的跨事件结论。
- RAD52 p.A161T：移除正文末尾串入的 `CHEK2` 位点残句，并禁止由单个未证实位点推导 HRD/PARP。
- XRCC2 c.121+2T>C：保留剪接影响预测，同时明确需要 RNA/功能验证，不能自动证明双等位失活或 HRD。

量化变化：

- CRC301：特异解释由 167/301（55.48%）提高到 193/301（64.12%）；通用回退由 134 降至 108。
- CRC358：特异解释由 140/358（39.11%）提高到 166/358（46.37%）；通用回退由 218 降至 192。
- P0/P1/P2 继续保持 0；P3 剩余为 CRC301 108、CRC358 192。

验证：

- P3-A fallback 26/26、精确纠正 6/6 治理校验通过；两层均为 `provisional_runtime`、`pending_report_group_review`，且 `drug_sections: []`。
- 26/26 个 NCBI Gene 编号与现行官方符号核对一致，包括两个历史符号映射。
- 两个 Panel 的未知位点正例和 6 个精确纠正负例均通过；RAD52 运行时正文不再包含 `CHEK2` 或历史项目符号残留。
- 知识治理、Web 目录/API、事件边界与精确纠正定向回归：64 passed。
- `pytest -q backend/tests` 全量回归：593 passed、4 skipped；无失败。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，CRC301/358 均 issues=0，运行覆盖、来源和治理字段保持 100%。
- 临床发布状态继续为 `BLOCKED`：CRC301/358 分别仍有 108/192 个通用解释；待报告组二审运行条目分别为 506/427，真实报告 UAT 均为 0/10。工程门禁通过不等于医学审核完成。

下一批：

- P3-B 优先处理 B2M、HLA-A/B/DPB1/DQA1/DQB1/DRB1/DRB5/G、IFNGR1/2、PDCD1LG2 等免疫相关基因，重点禁止由单个序列变异直接推导免疫治疗获益或耐药。
- 对剩余 legacy 精确位点继续执行“发现即纠正”，不再以保持旧金标为由保留明确的串漏或证据错配。

## 2026-07-21 CRC 医学知识深度分批完善：P3-B 免疫相关基因

状态：完成 12 个共享免疫相关基因的一级医学策展，并修复免疫汇总规则把普通Ⅰ/Ⅱ类序列变异直接映射为获益/耐药方向的问题；工程门禁通过，规则行为变更仍等待报告组二审和病例 UAT。

本轮范围：

- 抗原呈递：B2M、HLA-A、HLA-B、HLA-DPB1、HLA-DQA1、HLA-DQB1、HLA-DRB1、HLA-DRB5、HLA-G。
- IFN-γ 受体：IFNGR1、IFNGR2。
- PD-1 配体：PDCD1LG2（PD-L2）。
- 12 个基因在基础 `gene_knowledge_db.xlsx` 中原本均为模板化通用句；旧 reviewed 层只为其中 6 个补了简介，没有说明事件类型和免疫治疗外推边界。
- 新层同时补稳定基因功能和运行边界，所有条目均为 `provisional_runtime`、`pending_report_group_review`，且 `drug_sections: []`。
- 证据采用逐基因 NCBI Gene/RefSeq 官方记录；AMP/ASCO/CAP 体细胞变异规范约束位点解释，CAP MSI/MMR 指南用于区分经验证的免疫治疗生物标志物与未经验证的单基因序列外推。

免疫规则根部修复：

- `PDCD1LG2` 从普通 `direct` 序列变异命中改为 `non_sequence_biomarker`：PD-L2 表达、拷贝数或重排不能由普通 SNV 替代。
- `B2M` 和 `IFNGR1/2` 改为 `confirmed_functional_loss`：只有未来接入经确认的双等位/蛋白或通路功能缺失证据后才能形成研究性耐药线索；普通Ⅰ/Ⅱ类序列变异不再直接触发。
- 两个 CRC Panel 使用相同边界；相关表格行仍保留，未满足证据条件时显示标准未检出文本。MLH1 等原有直接规则保持不变。
- B2M 研究提示完整功能缺失与免疫逃逸存在机制关联，但不同模型和肿瘤背景并非绝对一致，因此本系统不把任意 B2M 位点解释为确定耐药。

量化变化：

- CRC301：特异解释由 193/301（64.12%）提高到 205/301（68.11%）；通用回退由 108 降至 96。
- CRC358：特异解释由 166/358（46.37%）提高到 178/358（49.72%）；通用回退由 192 降至 180。
- P0/P1/P2 继续保持 0；P3 剩余为 CRC301 96、CRC358 180。

验证：

- P3-B Overlay 12/12 行治理校验通过，12/12 个 NCBI Gene 编号与官方符号一致，新增文件 PII 扫描 0 命中。
- 双 Panel 语义正反例通过：即使普通 B2M、IFNGR1/2、PDCD1LG2 SNV 被标为Ⅱ类且 `CLNSIG=Pathogenic`，也不进入免疫正/负相关变异列表；MLH1 阳性对照仍正常命中。
- 知识治理、Web 目录/API、免疫规则与报告语义组合回归：343 passed、2 skipped。
- `pytest -q backend/tests` 全量回归：595 passed、4 skipped；无失败。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，CRC301/358 均 issues=0。
- 临床发布状态继续为 `BLOCKED`：待报告组二审运行条目分别为 CRC301 518、CRC358 439；真实报告 UAT 均为 0/10，且仍有 96/180 个通用解释。

下一批：

- P3-C 建议优先处理染色质、组蛋白与转录调控基因，包括 H3F3A、HIST1H1/H2/H3/H4 家族、KAT6A、KDM6A、KMT2A、EP300、CREBBP、ARID/SMARCA/STAG 等；重点区分普通序列变异、融合/重排、热点事件和表达/表观遗传状态。
- 免疫规则的本轮变更属于医学合同变更，部署前需报告组二审确认，并使用包含 B2M/IFNGR/PDCD1LG2 正反例的脱敏病例或合成病例完成 UAT。

## 2026-07-21 CRC 医学知识深度分批完善：P3-C 染色质、转录与剪接调控

状态：完成 26 个双 Panel 共享基因的一级医学策展，并纠正 4 条历史精确位点的跨事件/跨癌种或血液肿瘤语境外推；不新增药物规则，工程门禁通过，仍等待报告组二审和真实报告 UAT。

本轮范围：

- 染色质和组蛋白调控：ASXL1、BRD4、CREBBP、DEK、EP300、EP400、H3F3A、KAT6A、KDM6A、KMT2A、SMARCA1、SMARCA2、TET1、WHSC1、WHSC1L1。
- 转录、cohesin 和剪接调控：CIC、JUN、MED12、RARA、RBM10、RUNX1、SF3B1、STAG1、STAG2、U2AF1、ZRSR2。
- 统一事件边界：普通肿瘤序列变异不等于融合/重排、扩增/表达表型、复发热点、双等位或蛋白水平功能缺失、胚系综合征、血液肿瘤分子分类，也不自动建立药物敏感性。
- 现行符号迁移显式披露：H3F3A 对应 H3-3A、WHSC1 对应 NSD2、WHSC1L1 对应 NSD3；运行键保留 Panel 历史符号以兼容既有输入。
- 证据采用逐基因 NCBI Gene/RefSeq 官方记录；临床外推由 AMP/ASCO/CAP 体细胞变异解释规范和 CAP CRC 分子标志物指南约束。全部条目为 `provisional_runtime`、`pending_report_group_review`，且 `drug_sections: []`。

精确位点根部纠正：

- DEK p.E41D：删除由 DEK 过表达、乳腺癌预后和数据库出现次数向本位点致病性/驱动性的外推。
- EP400 p.Q2748dup：明确其为框内单氨基酸重复；其他癌种检出和数据库收录不能证明染色质重塑缺陷、结直肠癌驱动或治疗敏感性。
- JUN p.N30Tfs*5：保留早期移码和潜在功能影响，增加转录本/NMD/蛋白验证边界，删除由 JUN/AP-1 通用功能直接推导本位点驱动性的逻辑。
- ZRSR2 p.R446Q：区分肿瘤体细胞错义位点、髓系肿瘤中的截短/功能缺失事件及个案胚系变异，不再互相替代。
- KMT2A p.K1317Sfs*7 和 p.S2950G 两条既有保守精确解释保持原样并继续优先于新基因级 fallback。

量化变化：

- CRC301：特异解释由 205/301（68.11%）提高到 231/301（76.74%）；通用回退由 96 降至 70。
- CRC358：特异解释由 178/358（49.72%）提高到 204/358（56.98%）；通用回退由 180 降至 154。
- P0/P1/P2 继续保持 0；剩余 70/154 个缺口全部位于 P3 长尾。
- Web 知识目录同步包含新增条目：CRC301 reviewed overlay 为 720 行，CRC358 为 742 行；基因级、精确位点级和审核状态统计已分别更新并有 API 回归保护。

验证：

- P3-C fallback 26/26、精确纠正 4/4 治理校验通过；所有条目来源结构化、二审状态显式、无药物段，PII/章节串漏校验 0 命中。
- 26/26 个 NCBI Gene 编号与现行官方符号核对一致；三个历史符号迁移关系已在运行文案和来源中披露。
- 双 Panel 未知位点正例、4 个精确纠正负例及 KMT2A 两个精确优先级正例通过；DEK/EP400/JUN/ZRSR2 运行时不再返回旧跨语境段落。
- P3-C 语义和 Web 目录/API 定向回归：21 passed；`pytest -q backend/tests` 全量回归：597 passed、4 skipped、0 failed。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，CRC301/358 均 issues=0，基因解释、治理字段和结构化来源均为 100%。
- 临床发布状态继续为 `BLOCKED`：待报告组二审运行条目分别为 CRC301 548、CRC358 469；真实报告 UAT 均为 0/10，且仍有 70/154 个通用解释。工程 PASS 不代表医学签发完成。

下一批：

- P3-D 优先处理两个 Panel 共享的 HIST1H1/H2/H3/H4、HIST3H3 等历史组蛋白符号，先建立“旧符号→现行 HGNC/NCBI 符号→蛋白亚型”的可追溯映射，再策展热点/非热点边界，避免不同组蛋白拷贝之间串位点。
- 随后处理 CRC358 特有的 ARID、CHD、HDAC、KDM/KMT、NSD、NCOR 等染色质长尾，以及两个 Panel 共享的其余信号和转录调控基因；继续坚持基因级 fallback 不创建药物结论、发现历史精确正文错配即单独纠正。

## 2026-07-21 CRC 医学知识深度分批完善：P3-D 历史组蛋白符号与热点边界

状态：完成 23 个双 Panel 共享历史组蛋白基因的一级医学策展，建立可执行的旧符号身份映射，并按组蛋白家族阻断跨拷贝、跨蛋白亚型、跨事件和跨癌种外推；不新增药物规则，工程门禁通过，仍等待报告组二审和真实报告 UAT。

本轮范围：

- 连接组蛋白 H1：HIST1H1B、HIST1H1C、HIST1H1D、HIST1H1E。
- 核心组蛋白 H2：HIST1H2AL、HIST1H2AM、HIST1H2BC、HIST1H2BD、HIST1H2BG、HIST1H2BJ、HIST1H2BK、HIST1H2BO。
- 核心组蛋白 H3/H4：HIST1H3A、HIST1H3C、HIST1H3D、HIST1H3E、HIST1H3F、HIST1H3G、HIST1H3H、HIST1H3I、HIST1H3J、HIST1H4I、HIST3H3。
- 23 个基因在基础 `gene_knowledge_db.xlsx` 中均为模板化通用句，历史 reviewed 层也没有可复用的精确位点条目；本轮仅补稳定功能与证据边界，所有条目均为 `provisional_runtime`、`pending_report_group_review`，且 `drug_sections: []`。
- 新 Overlay 内置结构化 `legacy_symbol_map`，记录“Panel 历史符号→现行 NCBI 符号→NCBI Gene ID→蛋白亚型”。运行键继续使用历史 Panel 符号以兼容既有 Excel，同时在报告文案和来源中披露现行身份。
- 特别处理 H2B 历史别名歧义：以 NCBI Gene ID 锁定 HIST1H2BC→H2BC4/8347、HIST1H2BD→H2BC5/3017、HIST1H2BG→H2BC8/8339，禁止使用别名搜索的首条结果自动映射。

医学边界：

- H1 家族：滤泡性淋巴瘤中的复发性连接组蛋白事件不能直接外推到结直肠癌普通序列变异；表达、翻译后修饰、胚系事件和肿瘤体细胞位点不得互相替代。
- H2A/H2B/H4 家族：组蛋白修饰、表达或核小体状态证据不等于编码序列变异证据；一个拷贝的位点或功能结论不得迁移到另一个同源拷贝。
- H3 家族：必须同时匹配确切基因、氨基酸位点、组蛋白亚型与肿瘤背景。H3C3 p.K27M 的中枢神经系统弥漫性中线胶质瘤语境不代表任意 H3C3 或结直肠癌位点，也不得迁移到其他 H3C 拷贝；H3.3 与 H3.1 热点同样不得仅凭蛋白家族名称互换。
- 证据使用 NCBI Gene 官方身份记录、滤泡性淋巴瘤 H1 原始研究 PMID 24435047、H3 K27M 原始研究 PMID 26517431/34759345，并由 AMP/ASCO/CAP 体细胞变异规范约束临床外推。

量化变化：

- CRC301：特异解释由 231/301（76.74%）提高到 254/301（84.39%）；通用回退由 70 降至 47。
- CRC358：特异解释由 204/358（56.98%）提高到 227/358（63.41%）；通用回退由 154 降至 131。
- P0/P1/P2 继续保持 0；剩余缺口全部位于 P3 长尾。
- Web 知识目录同步包含新增条目：CRC301 reviewed overlay 为 743 行，CRC358 为 765 行；审核状态、匹配范围和 provisional 统计已同步更新并有 API 回归保护。

验证：

- 历史符号映射 23/23 与 NCBI Gene 身份核对一致；现行符号与 Gene ID 均唯一，治理校验 issues=0。
- 23/23 条 fallback 均为非通用的家族特异文案，且无药物段；跨 H1/H2/H3/H4 拷贝、跨翻译后修饰/表达/序列事件及跨肿瘤语境边界均有自动回归保护。
- P3-D 语义和 Web 目录/API 定向回归：21 passed；`pytest -q backend/tests` 全量回归：599 passed、4 skipped、0 failed。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，CRC301/358 均 issues=0，基因解释、治理字段和结构化来源均为 100%。
- 临床发布状态继续为 `BLOCKED`：待报告组二审运行条目分别为 CRC301 571、CRC358 492；真实报告 UAT 均为 0/10，且仍有 47/131 个通用解释。工程 PASS 不代表医学签发完成。

下一批：

- P3-E 先对 47 个双 Panel 共享剩余基因做身份审计，再逐条策展，以优先收口 CRC301；`LBP1B` 等疑似无效或录入错误的符号必须先查明来源，不能直接生成医学正文，历史符号也必须先锁定到唯一的现行实体。
- CRC358 额外的 84 个 Panel 特有长尾随后单列处理。所有新层继续坚持“基因级 fallback 不创建药物结论”，并在报告组二审和每个 Panel 至少 10 份脱敏真实病例 UAT 完成前保持临床发布阻断。

## 2026-07-21 CRC 医学知识深度分批完善：P3-E 共享长尾身份审计与解释收口

状态：完成 CRC301 剩余 47 个共享长尾基因的身份审计和一级医学策展；CRC301 运行时通用解释降至 0，CRC358 同步吸收其中 46 个原有缺口。另修正 7 条历史精确位点中的静态数据库计数、跨事件/跨癌种外推和仅凭结构域位置推断；不新增药物规则，工程门禁通过，仍等待报告组二审和真实报告 UAT。

身份审计：

- 47/47 个 Panel 键均锁定到唯一 NCBI Gene ID，Gene ID 无重复；45 个仍为现行官方符号。
- `LBP1B` 不是独立现行基因符号，而是 UBP1（NCBI Gene 7342）编码蛋白的 LBP-1b 亚型/历史别名。运行键保留 `LBP1B` 以兼容历史 Excel，但正文显式披露 UBP1，并要求先核对转录本和蛋白亚型。
- `ZNF278` 是 PATZ1（NCBI Gene 23598）的历史符号。运行键继续兼容 `ZNF278`，但普通序列位点不得套用 EWSR1-PATZ1 等融合事件证据。
- 身份与稳定功能采用逐基因 NCBI Gene/RefSeq 官方记录；临床外推由 AMP/ASCO/CAP 体细胞变异解释规范和 CAP CRC 分子标志物指南约束。

医学事件边界：

- RTK/MAPK/PI3K 轴：区分普通序列位点与融合/重排、扩增、蛋白磷酸化、表达或特定激活热点；KDR、PDGFRB、SRC、YES1、MAP2K2、MAPK1/3、PIK3R1 等未知位点不自动建立通路激活或用药结论。
- 细胞周期、凋亡与转录调控：CCNE1、MYCN、MDM4、ZNF217 等扩增/过表达证据不得迁移到编码区错义位点；BCL2L11 表达、缺失和多态性不能替代肿瘤体细胞位点功能证据。
- 血液/免疫谱系：CARD11、CD79B、JAK3、MPL、PIM1、SYK、TNFAIP3 的血液肿瘤事件或胚系免疫/造血疾病证据不能迁移到结直肠癌普通位点。
- 胚系、组织和检测类型：KEL 血型等位基因、FOXL2/TSHR/TEK 的特定组织或胚系语境、EPAS1 缺氧表达、SERPINB3/B4 蛋白表达、SLIT2 甲基化及 YAP1 核定位均与普通肿瘤序列变异分开解释。
- 全部 47 条为 `provisional_runtime`、`pending_report_group_review`，且 `drug_sections: []`。

历史精确位点纠正：

- CARD11 p.A687T、CDH11 p.K487T、MDM4 p.A376V、RAD21 p.Q132R、SYK p.W284L、TEK p.M383I、TSHR p.N372K 均改为位点级保守解释。
- 删除静态 COSMIC 次数及“未收录即无影响”等隐含推断；结构域内/外位置只作为定位信息，不再单独证明功能受损或正常。
- 其他癌种表达、血液肿瘤、血管畸形、甲状腺疾病、扩增/融合等证据不再无痕迁移到当前结直肠癌错义位点；7 条仍等待报告组二审。

量化变化：

- CRC301：特异解释由 254/301（84.39%）提高到 301/301（100%）；通用回退由 47 降至 0，已移除 `generic_gene_fallback_requires_content_review` 临床阻断原因。
- CRC358：特异解释由 227/358（63.41%）提高到 273/358（76.26%）；通用回退由 131 降至 85。47 个 CRC301 缺口中 GATA3 在 CRC358 原已具备针对性解释，因此 CRC358 净减少 46 个缺口。
- P0/P1/P2 继续保持 0；CRC358 剩余 85 个缺口全部位于 Panel 特有 P3 长尾。
- Web reviewed overlay 同步为 CRC301 797 行、CRC358 819 行；新增 47 条基因级 fallback 和 7 条精确位点纠正均可按来源、审核状态和匹配范围查询。

验证：

- 两份 P3-E Overlay 在双 Panel 上分别以 47/47 和 7/7 行通过治理校验；结构化来源、证据等级和癌种范围均为 100%，重复选择器为 0，药物行均为 0。
- 47 个身份映射、两处历史别名、未知位点事件边界以及 7 条精确位点优先级均有自动正反例保护；P3-E 语义和 Web 目录/API 定向回归：22 passed。
- `pytest -q backend/tests` 全量回归：602 passed、4 skipped、0 failed。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，CRC301/358 均 issues=0，运行解释、治理字段和结构化来源均保持 100%。
- 临床发布状态继续为 `BLOCKED`：待报告组二审运行条目分别为 CRC301 625、CRC358 546，真实报告 UAT 均为 0/10；CRC358 另有 85 个通用解释。CRC301 内容深度达到 100% 不等于 625 条条目已获报告组签发。

下一批：

- P3-F 处理 CRC358 独有的 85 个剩余长尾。先重新做身份和事件类型审计，再按 RTK/PI3K/MAPK、染色质/转录、磷酸酶/黏附及血液谱系等小批次策展，避免一次性大段补文掩盖符号或事件错误。
- 医学二审可并行启动 CRC301：以本轮 301/301 针对性正文为底稿，逐条记录“通过、修改后通过、不通过、暂缓”，并同步完成至少 10 份脱敏真实病例 UAT；在此之前不改变临床发布阻断状态。

## 2026-07-21 CRC 医学知识深度分批完善：P3-F1 CRC358 信号通路长尾

状态：完成 CRC358 独有长尾中的第一批 31 个信号通路基因一级医学策展，并纠正 4 条历史精确位点中的静态数据库计数、结构域位置和跨语境外推；CRC301 不加载本批规则，不新增药物规则，仍等待报告组二审和真实报告 UAT。

身份审计与范围：

- 先对 P3-E 后剩余的 85 个 CRC358 Panel 键逐一核对 NCBI Gene；85/85 均可锁定到现行官方符号和唯一 Gene ID。
- 发现 Panel 级实体重复风险：剩余键 `NSD2` 是现行官方符号，而 Panel 中已有历史键 `WHSC1`；两者都指向 NCBI Gene 7468。为保持既有 358 键输入合同，本轮不擅自删除任何键，也不以复制两份正文掩盖问题；后续必须以显式别名归一化和报告展示去重合同单独处理。
- 受体/非受体激酶：ABL2、ACVR1B、AXL、DDR1、EPHA3、EPHB1、FLT4、INSR。
- PI3K-mTOR、Hippo 和 MAPK 信号：INPP4A、INPPL1、LATS1、LATS2、MAP2K7、MAP3K13、MAP3K4、MAP3K6、PASK、PIK3CD、PIK3CG、PREX2、RICTOR、RPTOR、SMAD3、SOS1。
- 磷酸酶和信号衔接：PTPRB、PTPRC、PTPRD、PTPRK、PTPRS、VAV1、VAV2。
- 31 个基因仅适用于 `crc_358_msi`，全部为 `provisional_runtime`、`pending_report_group_review`、高风险需二审，且 `drug_sections: []`。稳定身份和功能采用逐基因 NCBI Gene 官方记录；ABL2 融合边界另参考 ETV6-ABL2 原始研究 PMID 12406085，临床外推由 AMP/ASCO/CAP 体细胞变异规范和 CAP CRC 分子标志物指南约束。

医学事件边界：

- 普通编码区序列变异不等于融合/重排、扩增或缺失、表达或甲基化、配体依赖和蛋白磷酸化；结构域内外位置也不能单独证明功能改变。
- 血液/免疫或胚系疾病语境不得迁移到结直肠癌体细胞位点：包括 ETV6-ABL2 融合、PIK3CD 免疫缺陷、FLT4 淋巴水肿、INSR 严重胰岛素抵抗、SOS1 Noonan 综合征、VAV1 血液肿瘤事件和 PTPRC 免疫细胞谱系信号。
- 近邻或同家族证据不得互相替代：ABL1/ABL2、ACVR1B/ACVR2A/TGFBR1、LATS1/LATS2、PIK3CA/PIK3CD/PIK3CG、INPP4A/INPPL1/PTEN、RICTOR-mTORC2/RPTOR-mTORC1、VAV1/VAV2 以及各受体型 PTP 成员均有显式边界。
- 未知位点不因“位于通路中”自动获得驱动、抑癌、免疫治疗或靶向药物结论；本批只补针对性的基因功能和事件边界，不改变第二部分药物规则。

历史精确位点纠正：

- DDR1 p.R658Q：保留激酶区域定位，删除由静态数据库、胃癌 EMT 或肾脏表达研究推导本位点激活、驱动或治疗敏感性的逻辑。
- EPHB1 p.R883W：删除由静态 COSMIC 次数及位于激酶/SAM 区域之外推导良性、致病或治疗意义的逻辑。
- PTPRB p.G1567V：删除“数据库未收录/位于主要催化区域之外即可证明无影响”的隐含推断，不再自动推导血管生成或抑癌功能缺失。
- PTPRS p.V1025I：受体型 PTP 家族通用功能和其他成员事件不再替代本位点的磷酸酶、黏附或结直肠癌证据。

量化变化：

- CRC301 保持 301/301（100%）针对性解释、通用回退 0；其 Panel manifest、Web 条目和运行时行为均未接入 P3-F1。
- CRC358 特异解释由 273/358（76.26%）提高到 304/358（84.92%）；通用回退由 85 降至 54，剩余均为 P3 长尾。
- CRC358 Web reviewed overlay 由 819 增至 854 行，其中基因级 750、精确位点级 104；CRC301 保持 797 行。Web 目录的 CRC358 provisional 基因条目为 551，来源、审核状态和匹配范围均可查询。
- 待报告组二审的运行条目为 CRC301 625、CRC358 581；真实报告 UAT 仍为 0/10。覆盖率提升不改变医学发布状态。

验证：

- P3-F1 fallback 31/31、精确纠正 4/4 通过治理校验；结构化来源、证据等级和癌种范围均为 100%，重复选择器 0，药物行 0。
- 31/31 个未知位点均命中非通用的基因专属正文；融合/CNV/表达/磷酸化/胚系/免疫谱系/旁系同源边界及 4 个精确位点优先级均有自动回归保护。CRC301 manifest 负例证明本批未跨 Panel 泄漏。
- P3-F1 语义和 Web/API 定向回归：9 passed；Ruff：PASS。
- `pytest -q backend/tests` 全量回归：605 passed、4 skipped、0 failed。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，CRC301/358 均 issues=0，运行解释、治理字段和结构化来源均保持 100%。
- 临床发布状态继续为 `BLOCKED`：CRC358 尚有 54 个通用解释，两个 Panel 均未完成报告组二审和 10 份真实报告 UAT。工程 PASS 不代表医学签发完成。

下一批：

- P3-F2 优先处理剩余 54 个基因中的染色质、转录和谱系调控组，包括 ARID1B/2/4A、ASXL2、BACH2、BCL11A、BCORL1、CHD4、DNMT1/3B、HDAC4/7/9、HIRA、KDM2B/4C/5A、KMT2B、NCOR1/2、NSD1、SETD5、TET2、TRRAP 等；继续区分普通位点与融合、表达、甲基化、热点、双等位失活和血液肿瘤语境。
- `NSD2`/`WHSC1` 先建立唯一实体与双历史输入键的归一化/展示去重合同，再决定如何计入 358 键覆盖；在合同冻结前不得简单复制或删除条目。

## 2026-07-21 CRC 医学知识深度分批完善：P3-F2 CRC358 染色质与表观遗传长尾

状态：完成 CRC358 独有长尾中的 24 个染色质重塑、DNA/组蛋白修饰、转录共抑制及谱系调控基因一级医学策展，并纠正 6 条历史精确位点正文；新增显式、可追溯的基因级字段替代机制。CRC301 不加载本批规则，不新增药物规则，仍等待报告组二审和真实报告 UAT。

本轮范围与身份：

- SWI/SNF、NuRD 和其他染色质调控：ARID1B、ARID2、ARID4A、ASXL2、CHD4、HIRA、TRRAP。
- DNA/组蛋白修饰：DNMT1、DNMT3B、HDAC4、HDAC7、HDAC9、KDM2B、KDM4C、KDM5A、KMT2B、NSD1、SETD5、TET2。
- 转录与谱系共调控：BACH2、BCL11A、BCORL1、NCOR1、NCOR2。
- 24/24 个 Panel 键均核对为现行 NCBI Gene 官方符号并锁定唯一 Gene ID；全部仅适用于 `crc_358_msi`，状态为 `provisional_runtime`、`pending_report_group_review`，且 `drug_sections: []`。
- 稳定功能以逐基因 NCBI Gene/RefSeq 为主；ARID 家族 MSI 结直肠癌队列采用 PMID 24382590，DNMT3B 表达模型采用 PMID 32552060，HDAC9 小鼠 Treg/结肠炎模型采用 PMID 19879272，TET2/实体瘤样本克隆性造血误归因边界采用 PMID 29866652 和 29872864。上述研究只用于界定“不能外推”的边界，不把模型或队列观察升级为位点临床证据。

根部机制修复：

- 历史 reviewed 基因级正文原本采用“第一写入者优先”，可防普通追加层无痕覆盖，但也使后续受治理纠正无法替换 ARID1B、DNMT3B、HDAC7、HDAC9、KMT2B 等过时简介。
- `GeneKnowledgeProvider` 现支持条目显式声明 `replace_fields`，但只有同时存在非空 `supersedes` 时才允许替换 `intro` 或 `mutation_analysis`；缺少替代来源时记录警告并继续保持第一写入者优先。
- 本批 24 条均明确记录替代对象，因此运行时使用新的官方功能与保守边界；精确位点仍保持最高优先级，固定蛋白/结构域字段仍由独立目录管理。
- 自动回归同时验证“无 `supersedes` 的替换被拒绝”和“有替代链的纠正生效”，避免该机制变成任意覆盖后门。

医学事件边界：

- 普通序列位点不等于融合/重排、扩增/缺失、表达/甲基化、蛋白复合物状态、组蛋白标记变化、双等位失活或药物反应；结构域内外位置和数据库是否收录均不能单独确定功能。
- 胚系或血液肿瘤语境与 CRC 体细胞位点分开：包括 ARID/CHD/SETD5 神经发育综合征、DNMT3B ICF、KMT2B 肌张力障碍、NSD1 Sotos/Weaver、NUP98-NSD1 融合、BACH2/BCL11A/BCORL1 免疫或造血谱系事件。
- TET2 在实体瘤样本中增加克隆性造血来源边界：需结合样本来源、肿瘤纯度、VAF及必要时配对血液，不能把单个位点自动解释为 CRC 细胞驱动、双等位失活、免疫标志物或药物靶点。
- 近邻成员不得互相替代：ARID1A/1B/2/4A、ASXL1/2、BCOR/BCORL1、DNMT1/3B、HDAC4/7/9、KDM/NSD/KMT2 家族以及 NCOR1/2 均有显式跨成员边界。
- SETD5 正文保留官方不确定性：不能仅凭 SET 区域名称断言其具有某一特定组蛋白甲基转移酶活性。

历史精确位点纠正：

- ARID1B p.Q207_Q214del：明确为框内缺失；删除由 COSMIC 未收录、结构域外定位及 ARID 家族 MSI 队列频率推导双等位失活、SWI/SNF 缺陷或治疗敏感性的逻辑。
- DNMT3B p.G509delinsVD：明确为框内插入缺失；miR-124 下调 DNMT3B 表达的细胞研究不再替代本位点的酶学和甲基化组证据。
- HDAC7 p.K205N：删除“数据库未收录/结构域外即可判断功能”的逻辑，并区分表达、磷酸化、核质定位、泛 HDAC 抑制和序列位点。
- HDAC9 p.S277V：小鼠 Treg/结肠炎中的敲除或抑制结果不再外推为 CRC 位点、免疫治疗或 HDAC 抑制剂结论。
- KMT2B p.R1055Q：删除 COSMIC、结构域外和 GeneCards 泛化肿瘤描述对本位点功能的替代。
- KMT2B p.P561S：同时纠正旧精确简介和变异解析；不再以“染色质通路长尾”或其他肿瘤基因级检出代替位点证据。

`NSD2`/`WHSC1` 身份合同：

- NCBI Gene 7468 的现行官方符号为 `NSD2`，`WHSC1` 是其历史别名；CRC358 覆盖分母却同时包含两个键，属于已确认的同一生物实体碰撞。
- 本轮新增机器可读 `identity_collision_contract`，固定 Gene ID、两个 Panel 键、兼容性和覆盖口径；没有复制 `WHSC1` 正文给 `NSD2`，也没有删除任何历史键。
- 截至 P3-F2 结束时状态仍为 `pending_explicit_alias_and_dedup_implementation`：当时运行时别名归一化、同一位点跨别名去重和报告标题展示合同尚未实现，因此 `NSD2` 继续计入剩余通用解释；后续完成状态见 P3-F3 记录。

量化变化：

- CRC301 保持 301/301（100%）针对性解释、通用回退 0，Web reviewed overlay 保持 797 行。
- CRC358 特异解释由 304/358（84.92%）提高到 328/358（91.62%）；通用回退由 54 降至 30。
- CRC358 Web reviewed overlay 由 854 增至 884 行，其中基因级 774、精确位点级 110；Web 目录 provisional 基因条目由 551 增至 581。
- 待报告组二审的运行条目为 CRC301 625、CRC358 611；真实报告 UAT 仍为 0/10。

验证：

- P3-F2 fallback 24/24、精确纠正 6/6 通过治理校验；结构化来源、证据等级和癌种范围均为 100%，重复选择器 0，药物行 0。
- 24/24 个未知位点均命中非通用专属正文；旧跨癌种/表达/疾病数据库简介已被显式纠正，6 条精确位点继续优先且不再出现旧推断。
- Panel 正反例证明新增层仅进入 CRC358；CRC301 manifest 和运行时均未泄漏本批内容。
- P3-F2 语义、替代机制和 Web/API 定向回归：9 passed；Ruff：PASS。
- `pytest -q backend/tests` 全量回归：609 passed、4 skipped、0 failed。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，CRC301/358 均 issues=0，运行解释、治理字段和结构化来源均保持 100%。
- 临床发布状态继续为 `BLOCKED`：CRC358 尚有 30 个通用解释，两个 Panel 均未完成报告组二审和 10 份真实报告 UAT。

下一批：

- P3-F3 优先处理剩余 30 个中的谱系和转录调控组：CUX1、ETV1、FLI1、FOXP1、FUBP1、MAX、MGA、MYB、PAX5、RUNX1T1、RUNX2、SOX9、TCF12、TCF3、TCF4、TLE3、TLE4、NCOA4；重点阻断融合/重排、表达、胚系和血液肿瘤语境向普通 CRC 位点迁移。
- `NSD2`/`WHSC1` 进入单独的运行时别名与去重子任务；其余结构/黏附/大分子长尾 ATXN2、CLTCL1、DNM2、FAT3、MAGI2、MGAM、MUC1、MYH11、PCLO、PDE4DIP、PRSS1 在后续 P3-F4 收口。

## 2026-07-21 CRC 医学知识深度分批完善：P3-F3 CRC358 谱系与转录调控长尾

状态：完成 CRC358 独有长尾中的 18 个谱系/转录调控基因一级医学策展，纠正 2 条历史精确位点正文，并完成 `NSD2`/`WHSC1` 的面板级运行时身份归一化和同位点去重。CRC301 不加载本批规则或别名映射，不新增药物规则；仍等待报告组二审和真实报告 UAT。

本轮范围与身份：

- 18 个基因：CUX1、ETV1、FLI1、FOXP1、FUBP1、MAX、MGA、MYB、PAX5、RUNX1T1、RUNX2、SOX9、TCF12、TCF3、TCF4、TLE3、TLE4、NCOA4。
- 18/18 个 Panel 键均以 NCBI Gene/RefSeq 核对现行官方符号和唯一 Gene ID；全部仅适用于 `crc_358_msi`，状态为 `provisional_runtime`、`pending_report_group_review`，且 `drug_sections: []`。
- TCF4 单独登记符号歧义合同：本 Panel 的 `TCF4` 固定为 NCBI Gene 6925（bHLH 转录因子）；不得因 TCF7L2（Gene 6934）历史上也使用 `TCF4/TCF-4` 别名而迁移 Wnt/TCF7L2 证据。
- 稳定功能以逐基因 NCBI Gene/RefSeq 为主；TCF12 的 CRC 表达/转移研究采用 PMID 22130667，少突胶质瘤变异语境采用 PMID 26068201，RUNX2 其他癌种表达/功能语境采用 PMID 36510562 和 36328501。这些研究只用于划定“表达/癌种证据不能替代当前位点”的边界，不升级为位点临床证据。

医学事件边界：

- ETV1、FLI1、RUNX1T1、TCF3、NCOA4 的融合/重排证据与普通 SNV/小 indel 分开；不得用融合伙伴、易位或重排生物学解释普通位点。
- MYB、PAX5、TCF3、RUNX1T1、FLI1 等造血/淋系事件与 CRC 上皮肿瘤分开；肿瘤组织检出需结合样本来源，不能自动形成血液肿瘤诊断或治疗结论。
- MAX 的胚系嗜铬细胞瘤/副神经节瘤、RUNX2/SOX9/TCF4 的胚系发育疾病或重复扩增，与 CRC 体细胞普通位点分开。
- ETV1、FOXP1、MYB、SOX9、TCF12、TLE3 等表达/预后观察不再作为序列位点证据；CUX1/FUBP1/MGA/TLE4 的明确失活、拷贝数或复合物状态也不等同于未知错义位点。
- 家族/伙伴证据不迁移：CUX1/CUX2、FOX 家族、MAX-MYC-MXD-MGA、TCF3/4/12、TLE 家族均保留独立基因和事件边界。

历史精确位点纠正：

- RUNX2 p.Q71del：明确为框内单个氨基酸缺失；删除由 COSMIC 未收录、预测卷曲螺旋位置、肺癌表达/凋亡和肾癌表达/侵袭研究推导当前位点功能、驱动或治疗意义的逻辑。
- TCF12 p.P191L：明确为错义变异；“位于主要 bHLH 区域之外”不能证明无功能影响，CRC 中的 TCF12 过表达/转移观察和少突胶质瘤中的 bHLH/截短变异均不能替代本位点证据。

`NSD2`/`WHSC1` 根部身份修复：

- CRC358 `panel.yaml` 新增面板级 `gene_symbol_aliases: {WHSC1: NSD2}`；该映射不进入 CRC301 或非 CRC Panel。
- 知识查询顺序为“原始输入键 → 现行官方键 → 同一官方实体的历史键”，可让 `NSD2` 输入复用既有受治理的 `WHSC1` 正文，同时优先保留 `NSD2` 自身固定结构域字段。
- 报告标题和正文 `gene` 字段保留首个输入符号，不强行改写历史 Excel；同一 c.HGVS/p.HGVS 在 `WHSC1` 与 `NSD2` 下按 Gene 7468 归一为一个 Part 3 身份，不重复渲染；不同位点仍分别保留。
- Panel 配置校验和 Provider 均拒绝循环别名，避免错误映射导致顺序依赖或静默合并。P3-F2 的身份合同状态由 pending 更新为 `active_panel_scoped_alias_lookup_and_variant_dedup`。

量化变化：

- CRC301 保持 301/301（100%）针对性解释、通用回退 0，Web reviewed overlay 保持 797 行。
- CRC358 特异解释由 328/358（91.62%）提高到 347/358（96.93%）：18 个 P3-F3 基因加上通过别名合同闭环的 NSD2；通用回退由 30 降至 11。
- CRC358 Web reviewed overlay 由 884 增至 904 行，其中基因级由 774 增至 792、精确位点级由 110 增至 112；Web 目录 provisional 基因条目由 581 增至 601。
- 待报告组二审的运行条目为 CRC301 625、CRC358 631；真实报告 UAT 仍为 0/10。

验证：

- P3-F3 fallback 18/18、精确纠正 2/2 通过治理校验；结构化来源、证据等级和癌种范围均为 100%，药物行 0。
- 18/18 个未知位点均命中非通用专属正文；TCF4/TCF7L2 歧义、融合/表达/胚系/造血谱系/旁系同源边界和 2 个精确位点优先级均有自动回归保护。
- `NSD2`/`WHSC1` 正反例验证：相同位点去重、不同位点不合并、首个输入符号保留、CRC301 不继承别名；循环映射被配置和运行时双层拒绝。
- P3-F3、Web/API、Panel 配置和身份合同定向回归：10 passed；Ruff：PASS。
- `pytest -q backend/tests` 全量回归：615 passed、4 skipped、0 failed。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，CRC301/358 均 issues=0；Panel 包 5/5 PASS、0 errors、0 warnings。
- 临床发布状态继续为 `BLOCKED`：CRC358 尚有 11 个通用解释，两个 Panel 均未完成报告组二审和 10 份真实报告 UAT。工程 PASS 不代表医学签发完成。

下一批：

- P3-F4 收口剩余 11 个结构、黏附和大分子长尾：ATXN2、CLTCL1、DNM2、FAT3、MAGI2、MGAM、MUC1、MYH11、PCLO、PDE4DIP、PRSS1。
- P3-F4 后重新运行全部覆盖、Web/API、严格知识发布门禁和真实报告 UAT；即使通用回退降为 0，报告组二审与至少 10 份真实报告 UAT 仍是临床发布阻断项。

## 2026-07-21 CRC 医学知识深度分批完善：P3-F4 CRC358 最终结构/黏附长尾收口

状态：完成 CRC358 最后 11 个通用回退基因的一级医学策展，并纠正其中 4 条历史精确位点正文。CRC301 不加载本批规则，本批不新增药物规则；运行时专属解释覆盖已达到 358/358，但全部新条目仍为 `provisional_runtime`、`pending_report_group_review`，不能表述为医学审核或临床发布已经完成。

本轮范围与身份：

- 11 个基因：ATXN2、CLTCL1、DNM2、FAT3、MAGI2、MGAM、MUC1、MYH11、PCLO、PDE4DIP、PRSS1。
- 11/11 个 Panel 键均通过 NCBI Gene E-utilities 核对现行官方符号和唯一 Gene ID；全部仅适用于 `crc_358_msi`，且 `drug_sections: []`。
- 稳定功能以 NCBI Gene/RefSeq 为主；固定结构沿用既有 UniProt/InterPro 目录。FAT3 和 MYH11 的旧结构句另以现行 reviewed UniProt 记录重新核对：FAT3 使用 Q8TDW7（4557 aa），MYH11 使用 P35749（1972 aa）。

医学事件边界：

- ATXN2 的 CAG/多聚谷氨酰胺重复扩增与普通 SNV/小 indel 分开；神经退行性疾病证据不迁移为 CRC 位点结论。
- CLTCL1、DNM2、MAGI2、PCLO、PDE4DIP 的膜运输、支架、表达、融合/重排或其他谱系事件与普通序列位点分开；CLTC、DNM1/3、MAGI1/3、PDE4D 等家族或互作伙伴证据不跨基因迁移。
- FAT3 的结构域位置、FAT 家族和其他癌种基因级观察不能证明未知位点导致黏附功能缺失；截短、双等位、CNV、表达和普通错义位点分别解释。
- MGAM 的消化酶/肠上皮表达语境，MUC1 的 VNTR、表达、定位、糖基化和抗原状态，均不等同于普通编码区位点；抗原相关治疗不能由 MUC1 单个位点反推。
- MYH11 的 CBFB::MYH11 髓系融合与主动脉/内脏平滑肌胚系疾病均不迁移为 CRC 体细胞位点结论；PRSS1 的遗传性胰腺炎、PRSS 家族及高度相似位点证据同样分开。

历史精确位点纠正：

- FAT3 p.Q1541L：保留现行 UniProt 的 Cadherin 14 定位，但明确“位于结构域”不能证明功能影响；删除静态数据库和跨癌种/家族外推。
- FAT3 p.G3981S：保留 Laminin G-like 定位，但删除“按黏附/迁移长尾变异解释”的无直接证据结论。
- MYH11 p.N1030Tfs*6：改为移码、提前终止及 NMD/实际蛋白产物仍需核验的保守解释；删除主动脉胚系机制外推，并清除旧条目误混入的 `PALB2：c.2056del，p.R686Gfs*23；0.6%` 病例结果片段。
- PCLO p.H3908N：明确结构域外位置不能证明无功能影响，也不能因大型神经支架蛋白身份形成驱动、预后或治疗结论。

量化变化：

- CRC301 保持 301/301（100%）针对性解释、通用回退 0；Web reviewed overlay 保持 797 行。
- CRC358 针对性解释由 347/358（96.93%）提高到 358/358（100%），通用回退由 11 降至 0；P0/P1/P2/P3 剩余队列均为空。
- CRC358 Web reviewed overlay 由 904 增至 919 行，其中基因级由 792 增至 803、精确位点级由 112 增至 116；Web 目录 provisional 基因条目由 601 增至 616。
- 待报告组二审的运行条目为 CRC301 625、CRC358 646；真实报告 UAT 仍为 0/10。

验证：

- P3-F4 fallback 11/11、精确纠正 4/4 通过治理校验；结构化来源、证据等级和癌种范围均为 100%，药物行 0。
- 11/11 个未知位点均命中非通用专属正文；重复扩增、融合/重排、胚系病、表达/糖基化/抗原状态、家族/互作伙伴和跨谱系边界均有负例回归保护。
- 4 条精确位点优先级、FAT3/MYH11 固定结构替换、MYH11 跨条目污染清除和 CRC301 不继承本批 overlay 均有自动回归保护。
- `scripts/analysis/22_profile_crc_medical_knowledge.py` 最终清单：`.work/crc_medical_knowledge_p3f4/final_inventory.json`。
- `scripts/check_knowledge_release_ready.py --strict`：工程状态 PASS，CRC301/358 均 issues=0；Panel 包 5/5 PASS、0 errors、0 warnings。
- P3-F4 语义、Web/API、覆盖率和治理定向回归：88 passed；Ruff：PASS。
- `pytest -q backend/tests` 全量回归：618 passed、4 skipped、0 failed。
- 临床发布状态继续为 `BLOCKED`：通用解释阻断项已消失，但两个 Panel 均未完成报告组逐条二审和至少 10 份真实报告 UAT。358/358 专属正文只表示运行时不再使用通用套话，不表示 358 个基因已经由报告组医学签发。

下一阶段：

- 冻结同一 commit 和知识哈希后，导出报告组二审包；优先审核本轮 15 条及前序全部 `provisional_runtime` 条目，记录通过、修改后通过、不通过或暂缓，不做无痕批量批准。
- CRC301/358 各完成不少于 10 份脱敏真实报告 UAT，覆盖无药、多位点、Ⅱ/Ⅲ类、SNV/indel/CNV/融合、MSI/TMB 和跨病例残留负例；临床发布门禁只由二审与 UAT 证据解除。
