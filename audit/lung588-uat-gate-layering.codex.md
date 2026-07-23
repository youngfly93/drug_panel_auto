---
module: lung588-uat-gate-layering
agent: codex
identity_kind: git_commit
identity_value: f1932094025bbf090a43b25d382f012ce76fe0da
---

# 肺癌588机器预UAT与正式UAT分层审计（Codex）

本审计只覆盖冻结业务提交
`f1932094025bbf090a43b25d382f012ce76fe0da`。目标是防止三份真实NGS
输入的结构机器检查，被误写成PD-L1产品通过或正式病例UAT通过。本提交只增强
脱敏验证收据和规格文档，不启用肺588、不接受合成PD-L1为患者来源、不执行
病例签发，也不部署生产。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-uat-gate-layering-01 | P0 | 三份真实肺癌Excel的结构合同通过，因此肺588病例UAT已达到3/10。 | 验证器把scope固定为`machine_pre_uat_only`，正式UAT固定BLOCKED；报告组审核数仍为0，见`validate_lung588_real_inputs.py:387-408`。 | REFUTED |
| lung588-uat-gate-layering-02 | P0 | CASE-LUNG-A/B/C中的合成TPS/CPS可作为真实逐病例IHC来源。 | 三份记录均标记`synthetic_visual_qa_only`；收据单独统计真实IHC来源0/3并产生`PDL1_CASE_SOURCE_NOT_VERIFIED`阻断，见`:337-376`。 | REFUTED |
| lung588-uat-gate-layering-03 | P0 | 只要候选PD-L1方案能校验数值，正式报告即可生成。 | 固定实测3/3的PD-L1产品合同均FAIL；运行方案仍为空，正式收据为`PD-L1产品0/3 BLOCKED`。 | REFUTED |
| lung588-uat-gate-layering-04 | P1 | 当前真实输入无法支持肺588的NGS结构链路。 | 固定实测三份输入分别为7、8、9个报告变异，自动识别均保持未识别、TMB/MSI与病例上下文合同均PASS、运行药物行均为0；分层结果为`NGS结构3/3 PASS`。 | REFUTED |
| lung588-uat-gate-layering-05 | P1 | 三份现有输入足以满足至少10份真实病例要求。 | 收据固定`required_formal_uat_case_count=10`、`observed_real_input_count=3`、`additional_real_case_count_required=7`，并产生`INSUFFICIENT_REAL_CASES`。 | REFUTED |
| lung588-uat-gate-layering-06 | P1 | 该机器验证器可代替未来报告组UAT记录系统。 | 本工具有意将报告组审核数固定为0，只用于机器预UAT；未来正式审核必须由独立、可追溯的病例UAT记录进入发布门禁。 | REFUTED |
| lung588-uat-gate-layering-07 | P1 | 增加UAT分层逻辑改变了CRC301/358输出。 | 固定SHA release-check中CRC301/358参考与候选生成均PASS，重复diff文本相似度均为1.0，表格数保持63和29。 | REFUTED |
| lung588-uat-gate-layering-08 | P1 | 本提交已经允许肺588部署iyun129。 | 肺588仍为draft、批量和第三部分关闭；严格知识门禁仍有247/247/551三类缺口，正式UAT为BLOCKED，未执行部署。 | REFUTED |

## 方法保真与边界

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-uat-gate-layering-M01 | NGS结构检查必须与PD-L1产品检查分开 | 结构通过要求未误识别、药物行0、生物标志物和病例合同PASS；PD-L1产品另计 | FAITHFUL | `validate_lung588_real_inputs.py:324-340` |
| lung588-uat-gate-layering-M02 | 合成机器QA值不得计入真实患者来源 | 只有`case_specific_verified_ihc_source`才计数；当前三份均为0 | FAITHFUL | `:337-340,367-376` |
| lung588-uat-gate-layering-M03 | 不足10例必须量化而非笼统提示 | 固定分母10，当前3例，自动计算仍需7例并输出机器可读阻断码 | FAITHFUL | `:51,343-356,387-408` |
| lung588-uat-gate-layering-M04 | 报告组UAT不可由机器推断 | 本机器预UAT工具不接收人工PASS，明确输出0/10和BLOCKED | HONEST_BOUNDARY | `:341,378-408` |
| lung588-uat-gate-layering-M05 | 局部PASS不得改变总门禁退出状态 | 固定真实输入验证仍退出1；顶层status为FAIL，三项PD-L1合同失败完整列出 | FAITHFUL | `:500-518,578`及固定收据 |
| lung588-uat-gate-layering-M06 | 分层定义必须有回归保护 | 合成三行正例锁定3/3结构PASS、0/3 PD-L1、0/10人工UAT和四个阻断码 | FAITHFUL | `test_lung588_phase_c_governance.py:721-758` |
| lung588-uat-gate-layering-M07 | 工程可用与医学发布必须分开 | 规格明确ENGINEERING_DRAFT，生产禁用不变；strict gate仍FAIL | HONEST_BOUNDARY | `spec_lung588_pdl1_production_readiness.md:268-275` |

## 冻结凭据

- 被审业务提交：
  `f1932094025bbf090a43b25d382f012ce76fe0da`；固定检查期间业务工作树
  干净。
- 固定真实输入分层收据SHA256：
  `67f6ff0c044ccbf104f3a288aa6d93bee909c1d4f926c7bc2207408f8ef5d876`；
  其`source_commit`与业务提交完全一致。
- 三份真实输入固定结果：
  `NGS结构3/3 PASS`、`PD-L1产品0/3 BLOCKED`、
  `真实逐病例IHC来源0/3`、`报告组病例UAT 0/10`；报告变异数分别为
  7、8、9，运行药物行均为0。验证器按预期退出1。
- 肺癌合同与治理复测：`31 passed, 0 failed`；Panel校验PASS，
  `0 errors / 0 warnings`。
- 肺588 strict gate按预期FAIL，仍恰有
  `RUNTIME_GENE_COVERAGE_GAP=247`、
  `RUNTIME_MUTATION_ANALYSIS_GAP=247`、
  `RUNTIME_FIXED_DOMAIN_GAP=551`；收据SHA256：
  `0d459d3aeaaed6913e8800721c21e5fab7a14162faf36da76a45c21421a87c8b`。
- 固定提交release-check：PASS；16项工程检查PASS、1项legacy跳过，
  GitHub远端检查按声明未执行。QA报告SHA256：
  `f52f594b648c11851352403d4c66cbbe74f7ed0e401c05c35f664780ce716071`。
- release-check回归子集：
  `291 passed, 2 skipped, 0 failed`；CRC358/301与肺部甲基化金标准均
  PASS，三条重复diff文本相似度均为1.0。
- 未执行真实PD-L1方案启用、真实逐病例IHC来源录入、报告组病例审核、
  10例正式UAT、当前SHA Linux视觉QA、iyun129部署或部署后活实例验收。

## 分层裁决

- 3份真实输入的NGS结构与脱敏病例合同：**PASS（机器预UAT）**。
- 实际PD-L1检测方案：**BLOCKED / 未二审启用**。
- 逐病例真实IHC来源：**BLOCKED（0/3）**。
- 病例数量门禁：**BLOCKED（3/10，仍差7份）**。
- 报告组病例级UAT：**BLOCKED（0/10）**。
- 肺588正式医学发布与iyun129部署：**NOT READY / NOT DEPLOYED**。
