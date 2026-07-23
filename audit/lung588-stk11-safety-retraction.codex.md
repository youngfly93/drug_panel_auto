---
module: lung588-stk11-safety-retraction
agent: codex
identity_kind: git_commit
identity_value: 81d60cbdaf4328bfaf8b423cc98ae9f298f53ba8
---

# 肺癌588 STK11安全撤回审计（Codex）

本审计只覆盖冻结业务提交
`81d60cbdaf4328bfaf8b423cc98ae9f298f53ba8`。审计目标是确认肺588
历史知识中的错误引用、跨癌种背景和超出证据边界的免疫疗效预测已从运行时
精确撤回，同时确认系统没有趁撤回自动加入新的医学结论。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-stk11-safety-retraction-01 | P0 | PMID 25980754 支持“KRAS/STK11共突变可能预测肺癌免疫治疗不良反应”。 | `panels/lung_588_pdl1/rules/knowledge_redactions.yaml:22-30` 记录该文献实际为疑似 Lynch 综合征人群的胚系多基因检测研究，并明确不支持该肺癌疗效声明。 | REFUTED |
| lung588-stk11-safety-retraction-02 | P0 | 可以把历史 STK11 结直肠癌和胚系背景原样带入肺癌体细胞报告。 | `knowledge_redactions.yaml:40-59` 以两条面板级精确字面撤回删除胚系/结直肠癌背景和结直肠癌频率声明。 | REFUTED |
| lung588-stk11-safety-retraction-03 | P0 | 任一 STK11 变异均可预测任一肺癌亚型、分期和免疫方案耐药。 | `knowledge_redactions.yaml:31-38,61-69` 明确 PMID 29773717 的队列边界，并撤回无事件、组织学、分期和方案限定的基因级外推。 | REFUTED |
| lung588-stk11-safety-retraction-04 | P0 | 撤回旧文本时可以直接写入一段替代医学结论。 | `reportgen/knowledge/redactions.py:54-63,92-112` 强制精确字面、仅删除、禁止新增和禁止替代文本；违规合同加载即失败。 | REFUTED |
| lung588-stk11-safety-retraction-05 | P0 | 配置了撤回规则就算成功，不必验证运行时是否命中。 | `reportgen/knowledge/gene_knowledge.py:531-571` 记录逐规则命中数；`reportgen/knowledge/release_gate.py:720-731` 对未命中规则发出 `RUNTIME_KNOWLEDGE_REDACTION_UNMATCHED` 阻断。固定提交复测4条均命中1次。 | REFUTED |
| lung588-stk11-safety-retraction-06 | P1 | 建议 PMID 29773717 已自动成为患者可见运行知识。 | `knowledge_redactions.yaml:31-38` 只登记支持/不支持边界；`scripts/analysis/24_build_lung588_p0_event_review.py` 仍把替代来源留在报告组二审队列，患者可见解释和药物结论均为 false。 | REFUTED |
| lung588-stk11-safety-retraction-07 | P1 | STK11修复使肺588知识门禁整体通过。 | 固定提交 strict gate 仍按预期 FAIL，仅剩247个运行解释缺口、247个未知位点解析缺口和551个固定结构域缺口。 | REFUTED |
| lung588-stk11-safety-retraction-08 | P1 | 本提交已部署到 iyun129。 | 本阶段仅在隔离工作树冻结、验证和审计；未切换生产 release，肺588仍为工程草案。 | REFUTED |

## 方法保真与边界

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-stk11-safety-retraction-M01 | 错引应先阻断患者可见输出，不能等待替代措辞完成后再处理 | 四条已确认不适用文字通过面板级精确撤回立即移除；替代措辞独立待二审 | FAITHFUL | `knowledge_redactions.yaml:40-79` |
| lung588-stk11-safety-retraction-M02 | 安全撤回不得变成新的隐性知识入口 | loader只接受`remove_exact_literal`，并强制`adds_medical_claim: false`和`replacement_status: pending_report_group_review` | FAITHFUL | `reportgen/knowledge/redactions.py:21,54-63,92-124` |
| lung588-stk11-safety-retraction-M03 | 撤回应在基础库与reviewed overlay合成后生效 | provider在最终`intro`、`fixed_domain_text`和`mutation_analysis`上执行受控撤回并记录命中 | FAITHFUL | `reportgen/knowledge/gene_knowledge.py:531-571,1620-1634` |
| lung588-stk11-safety-retraction-M04 | 规则必须归属单一Panel，不能污染CRC | loader核对规则`panel_id`与package一致；固定SHA release-check中CRC301/358参考、候选和重复diff均PASS | FAITHFUL | `reportgen/knowledge/redactions.py:40-52`；固定提交QA报告 |
| lung588-stk11-safety-retraction-M05 | 工程PASS与肺癌医学发布必须分开 | 活动生产Panel release-check PASS；肺588 strict gate仍FAIL，且PD-L1二审、知识二审和病例UAT未完成 | HONEST_BOUNDARY | 固定提交release-check与strict gate收据 |

## 冻结凭据

- 被审业务提交：
  `81d60cbdaf4328bfaf8b423cc98ae9f298f53ba8`；开审时工作树干净。
- 知识撤回规则 SHA256：
  `727413513b2dafff75430f820e19f2311381e44073a2eaf188fdfe2051bc2cb5`。
- 固定提交本地 release-check：PASS；16项工程检查PASS、1项legacy跳过，
  GitHub远端检查按声明未执行。QA报告 SHA256：
  `7412dc9fd99231e4b5e3a88f5a2dedfc42fe843ba55a7d303f08a90e80dbde85`。
- release-check中的固定回归子集：
  `291 passed, 2 skipped, 0 failed`；CRC358、CRC301及肺部甲基化金标准
  参考/候选/重复diff均PASS。
- STK11聚焦治理复测：`15 passed, 0 failed`。
- 肺588 strict gate：按预期FAIL，恰有3类问题；不再含
  `RUNTIME_CITATION_SOURCE_MISMATCH`或
  `RUNTIME_KNOWLEDGE_REDACTION_UNMATCHED`。收据 SHA256：
  `d0d21e0f8f3d66a6ca185a07ab5609ea72b272fe35892551fca102ba5a8e664e`。
- 固定提交P0事件包：28个审查单元；STK11单元记录
  `runtime_claim_retracted: true`，并列出精确撤回ID；患者可见第三部分和
  药物结论均不允许。JSON SHA256：
  `83a8246115f7b06a78eb0ef2a40b52b4d19a29d044beec4530817401531da344`。
- 本阶段是文本知识安全治理，不声称完成Linux分页视觉验收；未执行正式病例
  医学UAT、iyun129部署或部署后活实例验收。

## 分层裁决

- PMID 25980754错引撤回：**PASS（工程与来源边界一审）**。
- 结直肠癌/胚系上下文从肺癌体细胞报告撤回：**PASS**。
- 无边界STK11免疫耐药外推撤回：**PASS**。
- 替代来源PMID 29773717及正式患者可见措辞：**PENDING（二审）**。
- 肺588知识完善：**BLOCKED（247/247/551）**。
- 肺588PD-L1产品二审及正式病例UAT：**BLOCKED**。
- iyun129生产部署：**NOT READY / NOT DEPLOYED**。

下一阶段应先把247/247/551按“固定结构域、基因级功能、变异级叙述、候选病例
实际检出、来源状态”拆分，优先治理真实病例会触达且具有诊疗意义的条目。不得
用泛化模板批量填充，也不得把结构域文字计作变异级医学解析。
