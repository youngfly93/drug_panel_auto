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
