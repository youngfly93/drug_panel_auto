---
module: lung588-treatment-context
agent: codex
identity_kind: git_commit
identity_value: 16d55e1a8d7e44fb444485103e037d22347081c6
---

# 肺癌588治疗适应证上下文审计（Codex）

本审计只覆盖冻结提交
`16d55e1a8d7e44fb444485103e037d22347081c6`。它审查的是候选药物晋级所需
临床上下文的采集和失败关闭边界，不代表候选药物已经完成医学二审，也不代表
肺癌588已经可以部署。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-treatment-context-01 | P0 | 只凭肺癌诊断、基因和位点即可安全输出4条候选药物。 | `medical_candidates.yaml` 的4条候选分别要求病理类型、疾病范围、伴随诊断状态；ERBB2候选还要求既往系统治疗。候选仍非运行时来源。 | REFUTED |
| lung588-treatment-context-02 | P0 | 新增字段缺失或为“未明确/待确认”时可以默认匹配。 | `promotion_context_contract.missing_or_uncertain_policy=keep_candidate_hidden`，同时 `promotion_blocked=true`。 | REFUTED |
| lung588-treatment-context-03 | P1 | 治疗上下文字段会出现在CRC301/358表单中并改变既有病例录入。 | 四个字段加入 `PROJECT_ONLY_FIELDS`，只在 `lung_588_pdl1` 的 `show` 清单中暴露；定向测试锁定CRC358不可见。 | REFUTED |
| lung588-treatment-context-04 | P1 | 这次提交已经实现并开启患者级药物运行时匹配。 | 候选合同明确 `runtime_enforcement=not_implemented`、`promotion_blocked=true`；`rules/drugs.yaml` 仍关闭肺588靶向药物运行时。 | REFUTED |
| lung588-treatment-context-05 | P1 | 表单可输入任意自由文本，无法形成稳定的晋级条件。 | 四个字段均为受控下拉选项；候选合同登记允许值及不确定值。 | REFUTED |
| lung588-treatment-context-06 | P1 | 新提交冲刷了CRC301/358既有金标和知识门禁。 | release-check 全部通过；CRC301/358 reference、candidate、repeat diff 均PASS，知识门禁PASS。 | REFUTED |
| lung588-treatment-context-07 | P0 | 新提交已经切换到iyun129生产。 | 本次仅在隔离分支冻结和本地验证，未执行发布或生产切换；iyun129仍保持既有生产版本。 | REFUTED |

## 方法保真与限制核实

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-treatment-context-M01 | 药物适应证条件必须结构化，不得依赖自由文本猜测 | 新增病理类型、疾病范围、既往系统治疗、伴随诊断状态四个受控字段 | FAITHFUL | `config/mapping.yaml`；`backend/app/services/clinical_info_service.py` |
| lung588-treatment-context-M02 | 上下文缺失或不确定时必须失败关闭 | 候选治理合同统一指定 `keep_candidate_hidden`；规则测试锁定当前晋级阻断状态 | FAITHFUL | `panels/lung_588_pdl1/rules/medical_candidates.yaml`；`backend/tests/test_lung588_phase_c_governance.py` |
| lung588-treatment-context-M03 | 新字段不得污染其他Panel | 字段按项目隔离；CRC表单反向断言不包含这四项 | FAITHFUL | `backend/tests/test_lung588_contract.py` |
| lung588-treatment-context-M04 | 采集字段不等于已实现运行时判定 | 合同诚实登记 `runtime_enforcement=not_implemented`，候选继续隐藏 | HONEST_BOUNDARY | `panels/lung_588_pdl1/rules/medical_candidates.yaml` |
| lung588-treatment-context-M05 | 变更后必须证明既有CRC金标不回归 | 全量659通过、4跳过；正式release-check及CRC301/358三组金标差异均通过 | FAITHFUL | `.work/release_check_lung588_16d55e1/qa_gate/qa_gate_report.json` |

## 冻结凭据

- 被审提交：`16d55e1a8d7e44fb444485103e037d22347081c6`。
- 定向检查：Ruff PASS；肺588定向测试 `16 passed`；Panel 校验0错误、0警告。
- 后端全量回归：`659 passed, 4 skipped, 0 failed`。
- 本地 release-check：PASS；QA报告 SHA256
  `2cb6bfcaa99d8c85536d8507eb9d2afb1e0dbc87a3501f135046646e5d503c6c`。
- 知识工程门禁：PASS；报告 SHA256
  `e29c9bc5b9428cec8ce9830c708690265b3b62b77a69276f1683400dcc453350`。
- CRC301/358 的 reference、candidate、repeat diff 全部PASS。

## 分层裁决

- 字段采集与Panel隔离：**PASS**。
- 候选晋级失败关闭合同：**PASS**。
- 患者级运行时上下文匹配：**NOT IMPLEMENTED / BLOCKED**。
- 候选医学二审、10例正式UAT：**BLOCKED**。
- iyun129生产部署：**NOT READY / NOT DEPLOYED**。

下一阶段必须先实现可测试的逐候选上下文匹配，再由报告组逐事件二审并补齐
至少10例病例级UAT；不得因字段已经出现在表单中而解除运行时禁用。
