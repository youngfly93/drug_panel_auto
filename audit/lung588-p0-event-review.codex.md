---
module: lung588-p0-event-review
agent: codex
identity_kind: git_commit
identity_value: 6b1fc4199c6935b1dbab72f080cb24a8bebc152b
---

# 肺癌588 P0事件一审审计（Codex）

本审计只覆盖冻结提交
`6b1fc4199c6935b1dbab72f080cb24a8bebc152b`。审计目标是验证三份脱敏
真实病例已经形成可复核的精确事件身份，一审结论没有被误写成报告组二审或
患者可见医学结论，并确认既有CRC生产报告未回归。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-p0-event-review-01 | P0 | 基因+c./p.足以唯一定位医学变异，不需要转录本。 | 三病例合同新增NM转录本、染色体和外显子；P0事件ID包含基因、转录本、c.和p.。BRAF与ERBB2候选及反例也绑定对应NM版本。 | REFUTED |
| lung588-p0-event-review-02 | P1 | 金标准只需锁定位点，不必锁Ⅰ/Ⅱ/Ⅲ类和VAF。 | A/B/C的24个病例观察均锁定输入分级和VAF；验证器逐行比对，三份合同全部PASS。 | REFUTED |
| lung588-p0-event-review-03 | P1 | ATM `NM_000051.4:c.1236-2A>T` 在B/C两病例应作为两条医学规则重复审核。 | P0包按完整事件身份去重为1个变异审核单元，同时在 `case_observations` 保留B/C及VAF 1.67/0.92。 | REFUTED |
| lung588-p0-event-review-04 | P0 | Codex一审完成后，28个单元可以进入患者第三部分或药物结论。 | 23个变异、4条药物候选、1条错引均为 `runtime_eligible:false`；患者可见Part3允许数0、药物允许数0，二审完成数0。 | REFUTED |
| lung588-p0-event-review-05 | P0 | BRAF p.D594G可因同一基因继承V600E药物。 | D594G绑定 `NM_004333.6` 并标记显式不晋级；一审决定为保留检测结果、禁止宽规则继承。 | REFUTED |
| lung588-p0-event-review-06 | P1 | ERBB2 p.G660D有候选药物，就可继承任意HER2药物。 | G660D绑定 `NM_004448.4`；四条候选只有2条属于该事件，另有显式排除药物合同，所有候选继续隐藏待二审。 | REFUTED |
| lung588-p0-event-review-07 | P0 | 新增事件合同会改变CRC301/358生产报告。 | release-check 16项PASS，CRC301/358 reference、candidate、repeat diff和当前输出检查全部PASS。 | REFUTED |
| lung588-p0-event-review-08 | P0 | P0一审完成代表肺588已可部署。 | 588知识深度、STK11错引、报告组逐事件二审、PD-L1产品合同和正式UAT均未收口；Panel仍为draft且运行规则关闭。 | REFUTED |

## 方法保真与限制核实

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-p0-event-review-M01 | 医学审核身份必须包含转录本和精确事件 | 合同及审核包使用 `gene + transcript + c_hgvs + p_hgvs`，候选与反例同步登记转录本 | FAITHFUL | 三病例合同；`medical_candidates.yaml`；步骤24脚本 |
| lung588-p0-event-review-M02 | 同一事件跨病例去重时不得丢失病例观察 | 23个唯一变异对应24个病例观察，ATM单元保留两病例分级和VAF | FAITHFUL | `p0_event_review.json` |
| lung588-p0-event-review-M03 | AI一审与报告组二审必须分开记录 | 每个单元写入 `completed_ai_assisted_triage`，二审统一保留 `pending_report_group_review` 和空审核人 | FAITHFUL | 步骤24输出合同 |
| lung588-p0-event-review-M04 | 既有历史报告不得直接成为当前医学真理 | 旧内容仅作为 `current_content` 和候选来源；9个通用解释标记需改写、11个特异但未获肺癌事件批准需核源 | FAITHFUL | P0一审决策分布 |
| lung588-p0-event-review-M05 | 输入审核产物不得包含患者身份 | 工具只使用CASE别名、结构化事件和源SHA；测试反断言真实样本号与患者字段不进入JSON/TSV | FAITHFUL | 三病例验证与P0包测试 |

## 冻结凭据

- 被审提交：`6b1fc4199c6935b1dbab72f080cb24a8bebc152b`。
- 定向回归：`29 passed`。
- 本地 release-check：PASS（16通过、0警告、0失败、1跳过）；QA报告
  SHA256
  `bcd7f1974cb45c871e50634c26827e7df8b7a8791887b0f95d17a967937d12ef`。
- 三病例完整事件身份合同：PASS，A/B/C为7/8/9条；报告 SHA256
  `ecdb98283045c2d2367facc956abfa80c09a967978c3dc67443ddbc4f1640437`。
- 588知识深度盘点：P0/P1/P2/P3/P4为20/247/300/2/19；JSON
  SHA256
  `91a2ea9fa125b50100a6f21e79d32ea6234aa421ad50b55c9a67f2bd67c20658`。
- P0一审包：28单元，其中23个唯一变异、4条精确药物候选、1条文献错配；
  JSON SHA256
  `8e07a982fff9959a36a8d54540ad1e0644cb7a4879557d944e1c83994b61f80e`，
  TSV SHA256
  `5a9533e17083aa0b529b40d5544bce3e92ed0a589fb62b0a560a6f8f50525ec9`。

## 分层裁决

- 三病例精确事件身份与分级/VAF合同：**PASS**。
- P0事件去重和一审安全分流：**PASS**。
- BRAF D594G与ERBB2 G660D反例边界：**PASS**。
- 报告组逐事件二审：**BLOCKED（0/28）**。
- P0患者可见Part3/药物结论：**BLOCKED（0条获准）**。
- 588整体医学知识深度：**BLOCKED**。
- 肺588正式病例UAT：**BLOCKED（报告组0/10）**。
- iyun129肺588部署：**NOT READY / NOT DEPLOYED**。

下一步应先对P0包中的9个通用解释和11个未获肺癌事件批准的既有解释逐条
补证/核源，再由报告组填写二审结论；不得仅凭输入中的Ⅰ/Ⅱ/Ⅲ类自动产生
药物结论。
