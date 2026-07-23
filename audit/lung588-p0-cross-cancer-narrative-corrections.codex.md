---
module: lung588-p0-cross-cancer-narrative-corrections
agent: codex
identity_kind: git_commit
identity_value: 5cad539f33baec8495ea0cda63e4c2517f6d047f
---

# 肺癌588 P0跨癌种解释收窄审计（Codex）

本审计只覆盖冻结业务提交
`5cad539f33baec8495ea0cda63e4c2517f6d047f`。审计对象是3份脱敏肺癌
输入中13个已有“具体解释”、但旧文案含结直肠癌语境、其他位点/基因级证据
外推、未经证实功能缺失或治疗/预后/遗传推导的精确事件。本提交仅形成报告组
二审候选，不替换运行时文本，不启用肺588第三部分，不批准治疗规则，也不部署
生产。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-p0-cross-cancer-narrative-corrections-01 | P0 | 原23个P0变异中，只有先前10个通用文案事件需要候选解释，其余13个旧“具体解释”均可直接用于肺癌。 | 新增合同逐事件登记旧风险；APC、BRAF V600E、TP53运行时阳性对照仍分别命中“结直肠癌/肠癌预后/结直肠癌”，见测试`test_lung588_phase_c_governance.py:1484-1492`。 | REFUTED |
| lung588-p0-cross-cancer-narrative-corrections-02 | P0 | 新增13条候选已替换患者报告中的旧解释。 | 候选文件顶层和逐行均为`runtime_eligible=false`、`report_text_allowed=false`、`patient_visible=false`；provider反向测试逐行断言当前运行文本不等于候选文本，见`:1415-1447,1461-1482`。 | REFUTED |
| lung588-p0-cross-cancer-narrative-corrections-03 | P0 | NCBI Gene来源足以证明精确事件功能、肺癌临床意义或治疗结论。 | 每个`source_refs.supports`只允许`gene_identity_and_function_only`；四类医学推导全部为false，例如候选YAML`:67-79,101-113`。 | REFUTED |
| lung588-p0-cross-cancer-narrative-corrections-04 | P0 | ATM、MLH1、PTEN剪接事件没有p.HGVS，因此可以按基因级规则匹配或忽略转录本。 | 三条候选仍强制gene+transcript+c.HGVS，p.HGVS明确为空；构建器只允许p.HGVS在此类事件为空，且当前runtime不执行transcript匹配，故保持晋级阻断，见构建器`:197-204,247-264`和测试`:1449-1459`。 | REFUTED |
| lung588-p0-cross-cancer-narrative-corrections-05 | P0 | BRAF V600E解释候选可直接带出靶向药。 | 候选只链接独立药物候选ID，`drug_sections=[]`，治疗推导仍为false；肺癌亚型、疾病范围、伴随诊断和药物来源仍须分别审核，见候选YAML`:156-184`。 | REFUTED |
| lung588-p0-cross-cancer-narrative-corrections-06 | P1 | 新旧两份事件候选合同可以包含重复事件或不一致的运行选择器边界。 | 构建器在合并时拒绝重复事件，并拒绝两份合同的`runtime_selector_contract`不一致，见`24_build_lung588_p0_event_review.py:717-766`。 | REFUTED |
| lung588-p0-cross-cancer-narrative-corrections-07 | P1 | 13条候选可消除肺588整体知识发布缺口。 | 固定SHA strict gate仍按预期FAIL且仅有原三类问题：247个运行解释缺口、247个未知事件解析缺口、551个固定结构域缺口；患者可见解释和药物结论仍为0。 | REFUTED |
| lung588-p0-cross-cancer-narrative-corrections-08 | P1 | 本提交改变了CRC301/358既有输出。 | 固定SHA release-check中CRC301和CRC358参考/候选生成均PASS，重复diff文本相似度均为1.0，表格数分别保持63和29。 | REFUTED |
| lung588-p0-cross-cancer-narrative-corrections-09 | P1 | 本提交已达到肺588医学发布和iyun129部署条件。 | `panel.yaml:30-52`仍关闭肺588批量与患者可见第三部分；事件级二审、病例UAT、Linux视觉QA和生产部署均未执行。 | REFUTED |

## 方法保真与边界

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-p0-cross-cancer-narrative-corrections-M01 | 必须逐精确事件识别跨癌种和越级推导风险 | 13行覆盖APC、ATM、BRAF×2、BRCA2、MLH1、PIK3CA、PMS2、PTEN、SMAD4、TP53×3，每行保存`superseded_risk` | FAITHFUL | candidate YAML全部`gene_sections`；测试`:1367-1414` |
| lung588-p0-cross-cancer-narrative-corrections-M02 | 官方来源支持范围不得越界 | 10个基因使用NCBI Gene 324、472、673、675、4292、5290、5395、5728、4089、7157；仅支持基因身份与基础功能 | FAITHFUL | candidate YAML逐行`source_refs`；测试`:1401-1447` |
| lung588-p0-cross-cancer-narrative-corrections-M03 | HGVS序列后果与临床推导必须分层 | 错义仅确认氨基酸替换；终止/移码保留NMD和稳定蛋白不确定性；剪接仅写预测影响并要求RNA/直接证据 | FAITHFUL | candidate YAML各`mutation_analysis`和`evidence_boundaries` |
| lung588-p0-cross-cancer-narrative-corrections-M04 | 既有具体文案不得因“有文字”而逃过肺癌专属审核 | 测试以旧运行文案中的CRC词句作为阳性对照，并逐行保证候选未进入provider运行结果 | FAITHFUL | `test_lung588_phase_c_governance.py:1461-1492` |
| lung588-p0-cross-cancer-narrative-corrections-M05 | P0审核包必须覆盖全部检出事件但不增加审核单元 | 合并两份候选合同后，原28个审核单元不变；23/23个variant unit均带候选，覆盖19基因，运行晋级0 | FAITHFUL | 构建器`:717-889`；测试`:1036-1160` |
| lung588-p0-cross-cancer-narrative-corrections-M06 | 当前运行选择器不核转录本时不得晋级 | 文件明确记录缺口，构建器验证两份合同一致；候选继续失败关闭 | HONEST_BOUNDARY | candidate YAML`:37-50`；构建器`:233-245,738-752` |
| lung588-p0-cross-cancer-narrative-corrections-M07 | 不得以候选可得率冒充医学发布覆盖 | strict gate保持247/247/551；肺588第三部分保持关闭，二审完成数和患者可见数均为0 | HONEST_BOUNDARY | 固定SHA strict gate与P0 review JSON |

## 冻结凭据

- 被审业务提交：
  `5cad539f33baec8495ea0cda63e4c2517f6d047f`；固定检查期间业务工作树
  干净。
- 新增候选YAML SHA256：
  `5449e8914b59b03b9cca3996200f62286e9bea268e4120046bd2769d7d16b91f`。
- 固定提交P0 review JSON SHA256：
  `fa7f900d031a95608bd122fc5ae4586fa7dfa5a011204639a0351a0936e0ea00`；
  其中`git_head`与业务提交完全一致。
- 固定提交P0 review TSV SHA256：
  `1785ac517d25fdd68fa544b58d25725fc04ba81e99b045d03c40cfe53feb0c9a`。
- P0包仍为28个审核单元：23个精确变异叙述、4个精确药物候选、1个
  引用错配；23个变异均有候选解释，覆盖19基因；运行晋级0、患者可见
  解释0、患者可见药物结论0。
- 肺588 strict gate按预期FAIL，仍恰有
  `RUNTIME_GENE_COVERAGE_GAP=247`、
  `RUNTIME_MUTATION_ANALYSIS_GAP=247`、
  `RUNTIME_FIXED_DOMAIN_GAP=551`；收据SHA256：
  `48aa6504dec76ca5461caeac300586f4d912359294ff2adcf6d1c58bfad08627`。
- 肺癌合同与治理复测：`30 passed, 0 failed`；Panel校验PASS，
  `0 errors / 0 warnings`。
- 固定提交release-check：PASS；16项工程检查PASS、1项legacy跳过，
  GitHub远端检查按声明未执行。QA报告SHA256：
  `227eefa8d7fec0dcc4c09c2d8d1794679c5ac79fd5abd62262d2939a7e8fddb7`。
- release-check回归子集：
  `291 passed, 2 skipped, 0 failed`；CRC358/301与肺部甲基化金标准均
  PASS，三条重复diff文本相似度均为1.0。
- 未执行报告组事件级二审、候选运行启用、肺588患者可见第三部分、
  Linux病例渲染、正式病例UAT、iyun129部署或部署后活实例验收。

## 分层裁决

- 13条跨癌种/越级旧文案风险识别：**PASS（Codex一审）**。
- 13条精确事件替代候选的身份和失败关闭治理：**PASS**。
- 10个基因的NCBI官方身份与基础功能来源：**PASS（来源范围内）**。
- 精确位点功能、肺癌临床意义及治疗/免疫/预后/遗传结论：
  **PENDING / 未批准**。
- 当前运行时transcript选择器：**BLOCKED，支持前不得晋级候选**。
- 报告组事件级二审：**PENDING（23条事件候选）**。
- 肺588患者可见第三部分与批量生成：**DISABLED**。
- 肺588整体医学发布与iyun129部署：**NOT READY / NOT DEPLOYED**。
