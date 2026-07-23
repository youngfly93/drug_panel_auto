---
module: lung588-medical-knowledge-readiness
agent: codex
identity_kind: git_commit
identity_value: 8c0a74ecef5870d0c350cd7433a30bf208bdcb33
---

# 肺癌588医学知识就绪度审计（Codex）

本审计只覆盖冻结提交
`8c0a74ecef5870d0c350cd7433a30bf208bdcb33`。目标是把“588个基因均有文本”
与“肺癌特异医学知识已完成”严格分开，并验证病例契约、来源语义门禁及既有
CRC生产行为没有互相污染。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-medical-knowledge-01 | P0 | 只要 PMID 能查到题名，就足以证明患者报告中的声明有来源。 | STK11 文本以 PMID 25980754 支持 KRAS/STK11 共突变与免疫治疗反应；该文实际研究疑似 Lynch 综合征人群的胚系癌症易感基因。新增 claim-level 来源审查后，即使 PMID 元数据已登记，肺588仍以 `RUNTIME_CITATION_SOURCE_MISMATCH` 阻断。 | REFUTED |
| lung588-medical-knowledge-02 | P0 | 可将建议替代文献 PMID 29773717 自动视为已审核运行知识。 | 建议来源只写入待复核合同；`runtime_eligible:false`，`secondary_review_status:pending_report_group_review`，未写入患者可见 overlay。 | REFUTED |
| lung588-medical-knowledge-03 | P1 | 588个基因均有简介，等于肺癌知识库医学完成。 | 588/588 有简介，但只有341个有变异解析、32个为非通用特异解释、37个有固定蛋白/结构域内容；直接肺588知识门禁仍FAIL。 | REFUTED |
| lung588-medical-knowledge-04 | P1 | 三份真实输入都只能做非结构化人工核对。 | CASE-LUNG-A/B/C 均已绑定脱敏上下文合同，变异数分别7/8/9，三份合同均PASS；产物只含CASE别名和源文件哈希。 | REFUTED |
| lung588-medical-knowledge-05 | P1 | 肺588空药物规则文件可不声明知识治理。 | `rules/drugs.yaml` 已补齐失败关闭的治理默认值，患者级药物运行总开关仍关闭，空表不再触发治理结构错误。 | REFUTED |
| lung588-medical-knowledge-06 | P0 | 新增全局来源语义门禁会破坏CRC301/358生产知识。 | 活动Panel知识总闸PASS，2/2 Panel通过、0问题；CRC301/358参考件、候选件与重复生成diff全部PASS。 | REFUTED |
| lung588-medical-knowledge-07 | P0 | 本提交代表肺588已可部署或已经切换iyun129。 | 肺588直接门禁仍有4个阻断项；Panel保持`draft`、Part3与药物规则保持关闭。本提交未执行生产切换。 | REFUTED |

## 方法保真与限制核实

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-medical-knowledge-M01 | 来源完整性必须同时检查“标识可解析”和“来源支持声明” | 注册表解决元数据完整性；Panel自有 `citation_source_reviews` 解决声明级错配，二者分别计数 | FAITHFUL | `reference_registry.yaml`；`quality.py`；`release_gate.py` |
| lung588-medical-knowledge-M02 | 已确认错引在移除或完成替换二审前必须失败关闭 | 只要该 PMID 仍存在于 STK11 运行候选文本，来源错配保持阻断；文案变化也不能无痕绕过 | FAITHFUL | `RUNTIME_CITATION_SOURCE_MISMATCH` 正反向测试 |
| lung588-medical-knowledge-M03 | 医学覆盖率必须使用固定588分母并逐行输出 | 脚本从Panel有序基因合同生成588行队列，按P0-P4分层，输出JSON与TSV | FAITHFUL | `scripts/analysis/23_profile_lung588_medical_knowledge.py` |
| lung588-medical-knowledge-M04 | 审核产物不得暴露真实患者身份 | 输入按源文件SHA映射CASE别名；队列和病例合同不写患者姓名、样本号或源文件名 | FAITHFUL | 三病例脱敏验证与测试中的PII反断言 |
| lung588-medical-knowledge-M05 | 肺癌工作不得冲刷既有CRC修复 | 后端全量664项通过；release-check 16项PASS、0警告、0失败；CRC双Panel金标diff通过 | FAITHFUL | 本审计冻结凭据 |

## 冻结凭据

- 被审提交：`8c0a74ecef5870d0c350cd7433a30bf208bdcb33`。
- 定向回归：`28 passed`。
- 后端全量回归：`664 passed, 4 skipped, 0 failed`。
- 本地 release-check：PASS（16通过、0警告、0失败、1跳过）；QA报告
  SHA256
  `0f668adf34ae2c0eb5ab964f222196540561ae2a1ccf68958e530ed872022cab`。
- 活动Panel知识门禁：PASS，2/2 Panel通过、0问题；报告 SHA256
  `8b5ffd0f437b3966df16aeb6e63b237ec378464a786c8312475c7167eebfdf3a`。
- 肺588直接知识门禁：预期FAIL，4个问题：
  `RUNTIME_GENE_COVERAGE_GAP`、`RUNTIME_MUTATION_ANALYSIS_GAP`、
  `RUNTIME_FIXED_DOMAIN_GAP`、`RUNTIME_CITATION_SOURCE_MISMATCH`；
  报告 SHA256
  `9fbdd4cc5eb118ef83f5c9a87d24663902d5d981b77e9f268bfe8f919477f8f8`。
- 医学知识盘点：588基因；完整简介588、变异解析341、特异解释32、固定
  蛋白/结构域37；优先级P0/P1/P2/P3/P4为20/247/300/2/19；JSON
  SHA256
  `e112feae10c1a74a73222369dbd142a19114932a84f7cb02569cb1eaf3385bcd`。
- 三份真实输入脱敏契约：PASS，变异数7/8/9，A/B/C合同全部PASS；报告
  SHA256
  `7a6874c163c4340ccce08052561b4e7d6aa4dc4e0f07c28c4a059025d0abb116`。
- NCBI ESummary全量复算：CRC301 + CRC358 + lung588 合计501条当前运行
  引用、0未解析；跟踪注册表无缺失且共同条目的题名、引文和URL逐项一致。

## 分层裁决

- 医学知识盘点与逐行复核队列：**PASS**。
- 三病例结构化输入契约：**PASS**。
- PMID元数据完整性：**PASS**。
- STK11声明级来源归因：**BLOCKED，待替换/删改并完成报告组逐声明二审**。
- 肺588基因知识深度：**BLOCKED（247缺解析、300通用fallback、551缺固定结构域；计数有重叠）**。
- 4条精确药物候选医学二审：**BLOCKED**。
- 肺588正式病例UAT：**BLOCKED（报告组0/10，仍缺至少7份真实脱敏病例）**。
- iyun129肺588部署：**NOT READY / NOT DEPLOYED**。

下一阶段应从P0队列开始逐事件补证和复核，优先处理19个真实病例/候选相关
基因及STK11错引；不得用批量生成通用文字将覆盖率伪装为医学完成。
