---
module: lung588-p0-event-narrative-candidates
agent: codex
identity_kind: git_commit
identity_value: 447c1b7a6b83ec4070b49d85e9d0518ef57e48f8
---

# 肺癌588 P0精确事件候选解释审计（Codex）

本审计只覆盖冻结业务提交
`447c1b7a6b83ec4070b49d85e9d0518ef57e48f8`。目标是核验真实脱敏肺癌
输入中仍落入通用文案的10个精确事件，是否形成来源边界清楚、可进入报告组
二审但不能进入运行时的候选解释。本提交不批准任何精确事件的功能、致病性、
治疗、免疫、预后或遗传风险结论，不启用肺癌第三部分，也不部署生产。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-p0-event-narrative-candidates-01 | P0 | 10条候选已经替换运行时通用文案。 | `reviewed_part3_p0_event_narrative_candidates.yaml:21-35`默认`runtime_eligible/report_text_allowed/patient_visible=false`；`test_lung588_phase_c_governance.py:1310-1325`逐事件断言provider仍返回原通用叙述。 | REFUTED |
| lung588-p0-event-narrative-candidates-02 | P0 | 候选保存了transcript，因此当前运行时选择器已经逐转录本匹配。 | `reviewed_part3_p0_event_narrative_candidates.yaml:36-49`明确记录当前overlay不匹配transcript，并在运行选择器支持transcript前阻断晋级。 | REFUTED |
| lung588-p0-event-narrative-candidates-03 | P0 | NCBI Gene来源可以直接证明10个精确位点的功能与肺癌临床意义。 | 每行`source_refs.supports`仅为`gene_identity_and_function_only`，例如BRIP1见该YAML `:66-78`、ERBB2见`:100-115`；精确功能/肺癌临床证据另列为未识别或独立待审。 | REFUTED |
| lung588-p0-event-narrative-candidates-04 | P0 | 候选可据终止/移码字面后果直接判定功能缺失或用药。 | 候选仅陈述HGVS序列后果，并逐条保留“是否NMD/是否功能缺失需直接证据”边界；推导治疗、免疫、预后和遗传风险均为false，见该YAML `:61-83`、`:232-254`、`:299-321`。 | REFUTED |
| lung588-p0-event-narrative-candidates-05 | P1 | P0通用文案事件仍有遗漏。 | `test_lung588_phase_c_governance.py:1232-1257`锁定10个gene+transcript+cHGVS+pHGVS事件；P0包断言10条、9基因、运行晋级0，见`:1072-1083`及`:1133-1150`。 | REFUTED |
| lung588-p0-event-narrative-candidates-06 | P1 | 候选解释夹带药物规则。 | 候选文件`drug_sections=[]`，且每行四类医学推导均关闭；结构校验见`test_lung588_phase_c_governance.py:1227-1301`。 | REFUTED |
| lung588-p0-event-narrative-candidates-07 | P1 | 候选包包含真实患者姓名或样本号。 | 候选源声明仅使用脱敏CASE事件，见该YAML`:2-13`；输出回归禁止`LZ258`与`patient_name`，见`test_lung588_phase_c_governance.py:1189-1195`。 | REFUTED |
| lung588-p0-event-narrative-candidates-08 | P1 | 新增肺癌候选改变了CRC301/358既有报告。 | 固定SHA release-check中CRC301/358参考生成、候选生成和重复diff均PASS，文本相似度均为1.0；291项回归通过。 | REFUTED |
| lung588-p0-event-narrative-candidates-09 | P1 | 本提交已完成肺588医学发布，可部署iyun129。 | `panel.yaml:30-51`仍关闭肺588批量和患者可见第三部分；strict gate仍恰有247/247/551三类运行缺口，且病例UAT、Linux渲染和部署均未执行。 | REFUTED |

## 方法保真与边界

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-p0-event-narrative-candidates-M01 | 每条候选必须使用完整精确事件身份 | 10行均保存gene、transcript、cHGVS、pHGVS与变异类型；构建器拒绝缺字段、重复或不在脱敏P0合同内的候选 | FAITHFUL | `24_build_lung588_p0_event_review.py:190-307,709-729` |
| lung588-p0-event-narrative-candidates-M02 | 官方来源支持范围不得越界 | 9个基因分别使用NCBI Gene 83990、2064、2099、2322、2778、3459、4437、7248、7249；来源只支持基因身份与功能 | FAITHFUL | candidate YAML逐行`source_refs`；校验器`24_build_lung588_p0_event_review.py:260-289` |
| lung588-p0-event-narrative-candidates-M03 | 序列后果与临床结论必须分层 | 错义仅描述氨基酸替换；终止/移码仅描述预计提前终止并保留NMD与实际功能不确定性；无直接证据不写临床获益/耐药 | FAITHFUL | candidate YAML各`mutation_analysis`与`evidence_boundaries` |
| lung588-p0-event-narrative-candidates-M04 | 候选必须默认关闭并要求二审 | 文件级与行级均为needs_review、runtime=false、report=false、patient-visible=false、secondary review pending | FAITHFUL | candidate YAML`:15-49`及各行治理字段；测试`:1207-1227,1270-1301` |
| lung588-p0-event-narrative-candidates-M05 | 当前选择器不支持transcript时不得假装安全晋级 | 明示记录选择器缺口，并将`runtime_selector_enforces_transcript`列为晋级前置条件 | HONEST_BOUNDARY | candidate YAML`:36-49` |
| lung588-p0-event-narrative-candidates-M06 | P0工作表必须展示候选但不改变原28个审核单元 | 构建器把候选嵌入对应variant unit；总数仍为23个变异叙述、4个药物候选、1个引用错配，候选数作为独立指标10/9/0 | FAITHFUL | `24_build_lung588_p0_event_review.py:709-810`；测试`:1060-1150` |
| lung588-p0-event-narrative-candidates-M07 | 候选可得不得冒充运行覆盖 | fixed-SHA strict gate仍FAIL且计数不变；患者可见第三部分与药物结论均为0 | HONEST_BOUNDARY | strict gate收据与P0 review JSON |

## 冻结凭据

- 被审业务提交：
  `447c1b7a6b83ec4070b49d85e9d0518ef57e48f8`；固定检查期间业务工作树
  干净。
- 候选YAML SHA256：
  `6ba3d8773cac00a1b95bb5b39d38cddc826c252cc0fab1d5641fa1df51a9650a`。
- 固定提交P0 review JSON SHA256：
  `ef40b0633fc130a5847fa93a05672e3e363716f6d138b34fe186353b560ae90e`；
  其中`git_head`与被审业务提交完全一致。
- 固定提交P0 review TSV SHA256：
  `ee250c49c231080af3e5562aec76fba2b22ce8fee77052b62d1c85a2976f5a52`。
- P0包仍为28个审核单元：23个精确变异叙述、4个精确药物候选、1个
  引用错配；新增候选解释10条、9基因、运行晋级0、患者可见解释0、患者
  可见药物结论0。
- 肺588 strict gate按预期FAIL，仍恰有
  `RUNTIME_GENE_COVERAGE_GAP=247`、
  `RUNTIME_MUTATION_ANALYSIS_GAP=247`、
  `RUNTIME_FIXED_DOMAIN_GAP=551`；收据SHA256：
  `1c8f2095e8a0c6c066f455e2d4bb17c869e462b7dca88e54c8ac3337da70eae7`。
- 肺癌合同与治理聚焦复测：`29 passed, 0 failed`；候选专项复测：
  `3 passed, 0 failed`。
- 固定提交release-check：PASS；16项工程检查PASS、1项legacy跳过，
  GitHub远端检查按声明未执行。QA报告SHA256：
  `ddf240b6df8f5be70a07e67412fdcb83fc38bd573acc1c9403068796eb3f987b`。
- release-check回归子集：
  `291 passed, 2 skipped, 0 failed`；CRC358/301与肺部甲基化金标准均PASS。
- 未执行报告组事件级二审、候选运行启用、肺588患者可见第三部分、
  Linux病例渲染、正式病例UAT、iyun129部署或部署后活实例验收。

## 分层裁决

- 10条P0精确事件候选的身份完整性：**PASS（Codex一审）**。
- 9个基因的NCBI官方身份与基础功能来源：**PASS（来源范围内）**。
- 终止/移码/错义序列后果的保守边界：**PASS（候选表述）**。
- 精确位点功能、肺癌临床意义与任何治疗/免疫/预后/遗传结论：
  **PENDING / 未批准**。
- 运行时transcript选择器：**BLOCKED，支持前不得晋级候选**。
- 报告组事件级二审：**PENDING（10条）**。
- 肺588患者可见第三部分：**DISABLED**。
- 肺588整体医学发布与iyun129部署：**NOT READY / NOT DEPLOYED**。
