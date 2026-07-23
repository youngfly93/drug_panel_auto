---
module: lung588-candidate-evidence-review
agent: codex
identity_kind: git_commit
identity_value: a41c088b98d92a69e86e1eedd671532c9712cf64
---

# 肺癌588药物候选证据范围审计（Codex）

本审计只覆盖冻结提交
`a41c088b98d92a69e86e1eedd671532c9712cf64`。审计目标是核实4条肺癌
靶向药物候选的来源、癌种、疾病范围、精确事件、转录本、检测方法和患者
展示边界，并验证证据审查不会绕过报告组医学二审或把候选写入运行时。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-candidate-evidence-review-01 | P0 | 只要候选列出 PMID 或监管链接，就可视为来源已支持整条患者级结论。 | `candidate_evidence_review.yaml:49-319` 对每个来源分别记录 `supports` 与 `does_not_support`，并将直接疗效、功能、监管类别和伴随诊断拆开。 | REFUTED |
| lung588-candidate-evidence-review-02 | P0 | BRAF V600E 的肺癌证据可被同基因 D594G 或其它非V600事件继承。 | 两条BRAF候选均锁定 `NM_004333.6:c.1799T>A:p.V600E`；来源边界明确排除D594G和基因级规则；既有D594G显式反例继续保留。 | REFUTED |
| lung588-candidate-evidence-review-03 | P0 | ERBB2 G660D 的功能激活研究等同于该位点已有德曲妥珠单抗直接临床疗效。 | `candidate_evidence_review.yaml:175-243` 将G660D功能、伴随诊断可报告位点和ERBB2激活突变监管类别组成间接链，并明确 `direct_exact_drug_event_clinical_outcome: not_identified`。 | REFUTED |
| lung588-candidate-evidence-review-04 | P0 | 伴随诊断技术文件列出G660D，即可当作G660D药物疗效亚组。 | `candidate_evidence_review.yaml:207-236` 仅把P200010S008技术文件用于“可报告位点/检测范围”，同时明确它不支持G660D特异治疗反应估计。 | REFUTED |
| lung588-candidate-evidence-review-05 | P0 | 瑞康曲妥珠单抗已有HER2突变肺癌研究，因此G660D候选可以直接晋级。 | `candidate_evidence_review.yaml:263-327` 记录未识别G660D疗效亚组、未取得完整中国说明书和精确位点适用范围，裁决为 `hold_pending_official_china_label_and_secondary_review`。 | REFUTED |
| lung588-candidate-evidence-review-06 | P0 | 证据审查单可以与实际候选的ID、转录本、c./p.或药物名漂移而继续生成审核包。 | `24_build_lung588_p0_event_review.py:189-277` 对治理状态、候选集合、selector、药物名、来源边界和直接疗效处置做阻断校验；测试锁定4/4一一对应。 | REFUTED |
| lung588-candidate-evidence-review-07 | P0 | Codex完成来源范围一审后，4条候选已可进入患者第三部分或药物结论。 | 审查合同和候选文件均为 `runtime_eligible:false`、`report_text_allowed:false`；固定SHA审核包患者可见Part3及药物允许数均为0，报告组二审完成数为0。 | REFUTED |
| lung588-candidate-evidence-review-08 | P1 | 本地总门禁PASS表示肺588知识和医学发布均已完成。 | 活动CRC工程总闸PASS，但直接对肺588执行严格知识门禁仍FAIL，保留4类阻断：247个解释缺口、247个未知变异解析缺口、551个固定结构域缺口和1个来源错配。 | REFUTED |
| lung588-candidate-evidence-review-09 | P1 | 本提交已经切换iyun129或开放肺588批量。 | 提交只改肺588草案规则、审核脚本、测试和spec；未执行部署命令，肺588运行规则和批量禁用状态未改变。 | REFUTED |

## 方法保真与限制核实

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-candidate-evidence-review-M01 | 医学来源必须逐条核对其支持的癌种、事件和声明范围 | 4条候选按来源分别记录支持项与排除项，并区分直接临床、功能、监管及检测证据 | FAITHFUL | `candidate_evidence_review.yaml:49-319` |
| lung588-candidate-evidence-review-M02 | 精确事件身份必须包含转录本版本、c.和p.，证据未绑定转录本时不得静默放宽 | 审查合同与候选selector逐字段一致；BRAF/ERBB2来源未声明NM版本的边界被显式记录，运行时仍要求版本精确匹配 | FAITHFUL | `candidate_evidence_review.yaml:41-48,105-112,166-174,254-262`；转录本运行门禁前序提交 |
| lung588-candidate-evidence-review-M03 | 不得把间接证据链表述成精确位点药物疗效 | 两条ERBB2候选均标记精确位点直接疗效 `not_identified`；德曲妥珠单抗保留为间接链待二审，瑞康曲妥珠单抗进一步挂起 | FAITHFUL | `candidate_evidence_review.yaml:217-243,296-327` |
| lung588-candidate-evidence-review-M04 | 一审记录必须失败关闭且不得代替报告组医学二审 | 顶层治理与逐候选均禁止运行和报告文本，二审状态固定为待报告组；校验器发现漂移即抛错 | FAITHFUL | `candidate_evidence_review.yaml:13-37`；`24_build_lung588_p0_event_review.py:189-277` |
| lung588-candidate-evidence-review-M05 | 审核产物不得携带真实病例身份 | 固定SHA审核包只含CASE别名、精确事件、候选及来源范围；隐私测试通过，Git未新增Excel、Word或患者标识 | FAITHFUL | `test_lung588_phase_c_governance.py:899-973`；冻结提交diff |
| lung588-candidate-evidence-review-M06 | 工程非回归与医学发布状态必须分层裁决 | CRC301/358金标及工程总闸PASS；肺588直接知识门禁仍FAIL、二审0、病例UAT 0/10、未部署 | HONEST_BOUNDARY | 固定SHA release-check；肺588严格知识门禁凭据 |

## 冻结凭据

- 被审提交：
  `a41c088b98d92a69e86e1eedd671532c9712cf64`；开审时业务工作树干净。
- 证据范围合同 SHA256：
  `e20e49e98a3b259f0202fab39cd5723fcea780e32ec0ec18cbbecc5d69bdb7a6`。
- 肺588 Panel校验：PASS，10个规则文件，0 errors、0 warnings。
- 肺588治理回归：`14 passed, 0 failed`。
- 全后端回归：`670 passed, 4 skipped, 0 failed`。
- 固定提交本地 release-check：PASS；16项工程检查通过、0失败、1项legacy
  跳过、GitHub远端检查按声明未执行。
- QA报告 SHA256：
  `afe1b16cd2ed7f351d339f1f3ba9cb5c10451ecebf1b9549078a0c0c64250fa9`。
- 活动Panel知识总闸 SHA256：
  `de6e968c5d1445c1fd65d3ac027405c1bf252dbd414f217dcb435de39a2ec42d`。
- 固定SHA P0审核包 `git_head` 与被审提交一致；JSON SHA256：
  `57899601a0fb4df711061c6626ed685cb62bfc816a11e7cf60143d4471367076`。
- 肺588严格知识门禁按预期FAIL；报告 SHA256：
  `ebf5b44ece3167bf401f1b5c61b21c8d55d500d3bcb8df21e61962b7dfe9eddc`。
- `qa_gate_report.json` 当前不内嵌Git revision；固定SHA身份由运行前干净
  工作树、完整HEAD、P0审核包内嵌 `git_head` 和本审计共同锚定。本审计不
  虚构GitHub、Linux候选、生产部署或病例医学放行凭据。

## 分层裁决

- 4条候选逐来源范围一审：**PASS（非权威Codex一审）**。
- 候选与证据审查一一对应及失败关闭：**PASS**。
- CRC301/358工程非回归：**PASS**。
- BRAF V600E两条候选：**保留待报告组二审，不可运行**。
- ERBB2 G660D德曲妥珠单抗：**间接证据链待二审，不可运行**。
- ERBB2 G660D瑞康曲妥珠单抗：**HOLD，待完整中国说明书、精确位点范围及二审**。
- 肺癌588知识医学完善：**BLOCKED**。
- 肺癌588正式病例UAT：**BLOCKED（报告组0/10）**。
- 肺癌588生产部署：**NOT READY / NOT DEPLOYED**。

下一阶段应处理PD-L1产品合同（抗体克隆、平台、阈值和逐病例图像策略），
同时从P0真实事件队列继续补齐变异解释与来源；任何医学候选在报告组逐事件
二审和正式病例UAT完成前均不得迁入运行时规则。
