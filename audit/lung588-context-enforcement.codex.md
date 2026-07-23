---
module: lung588-context-enforcement
agent: codex
identity_kind: git_commit
identity_value: cbb15075c11195a300e194d8d1803bfce37cb989
---

# 肺癌588治疗上下文运行时门禁审计（Codex）

本审计只覆盖冻结提交
`cbb15075c11195a300e194d8d1803bfce37cb989`。审计目标是验证通用药物
规则加载路径已具备逐事件治疗上下文失败关闭能力，同时确认肺癌588的候选
药物总开关、医学二审和生产状态均未被提前开放。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-context-enforcement-01 | P0 | 上下文缺失时，精确位点规则仍可通过宽泛药物库兜底。 | 上下文不合格的活动规则会被移入 `blocked_reviewed_variant_overrides`；相同精确 selector 返回 `--/--`，不能落到低特异度行。 | REFUTED |
| lung588-context-enforcement-02 | P0 | “未明确”“待确认”可被当作有效适应证条件。 | `clinical_context.yaml` 明确不确定值；评估器返回 `CONTEXT_VALUE_UNCERTAIN` 并阻断。 | REFUTED |
| lung588-context-enforcement-03 | P1 | 非小细胞肺癌的任意分期都满足BRAF V600E候选。 | 两条BRAF候选要求病理类型为非小细胞肺癌、疾病范围为转移性、伴随诊断状态为已确认符合；早期病例反例被拒绝。 | REFUTED |
| lung588-context-enforcement-04 | P1 | ERBB2 G660D候选不需要既往治疗条件。 | 两条ERBB2候选同时要求不可切除局部晚期/转移性、已接受系统治疗及伴随诊断已确认；“未接受”反例被拒绝。 | REFUTED |
| lung588-context-enforcement-05 | P1 | 新的上下文门禁会改变不声明上下文合同的CRC规则。 | 只有带 `required_context_fields` 的规则进入新评估；全量661项通过，CRC301/358三组金标差异全部PASS。 | REFUTED |
| lung588-context-enforcement-06 | P0 | 上下文引擎完成等于肺588药物候选已上线。 | `rules/drugs.yaml` 仍为 `enabled:false`；4条候选仍为 `runtime_eligible:false`、`report_text_allowed:false`、待报告组二审。 | REFUTED |
| lung588-context-enforcement-07 | P0 | 本提交已切换iyun129生产。 | 生产只读检查显示 `current_release=49bae3d`、revision与进程cwd一致、健康检查HTTP 200；不是本提交。 | REFUTED |

## 方法保真与限制核实

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-context-enforcement-M01 | 上下文必须来自结构化病例字段，不得从自由文本诊断推断 | 评估器只读取四个受控字段；代码说明和合同均禁止自由文本推断 | FAITHFUL | `reportgen/rules/targeted_drugs.py`；`panels/lung_588_pdl1/rules/clinical_context.yaml` |
| lung588-context-enforcement-M02 | 缺合同、缺字段、非法值、不确定值和超范围值均失败关闭 | 每种状态产生稳定原因码并移入阻断 selector | FAITHFUL | `evaluate_required_clinical_context()`；定向正反例测试 |
| lung588-context-enforcement-M03 | 上下文必须在请求范围内传递，不能成为跨患者全局状态 | `FieldMapper` 和增强桥按当前 `ReportData.context` 显式传入规则加载器 | FAITHFUL | `reportgen/core/field_mapper.py`；`reportgen/core/template_bridge_358.py` |
| lung588-context-enforcement-M04 | 运行时能力实现不得解除医学发布门禁 | Context engine已实现，但肺588药物总开关仍关闭，候选仍不可输出 | HONEST_BOUNDARY | `panels/lung_588_pdl1/rules/drugs.yaml`；`medical_candidates.yaml` |
| lung588-context-enforcement-M05 | 通用规则引擎改动必须证明既有Panel不回归 | 全量回归、release-check、CRC301/358金标差异及3份肺癌输入脱敏验证全部通过 | FAITHFUL | 本审计冻结凭据 |

## 冻结凭据

- 被审提交：`cbb15075c11195a300e194d8d1803bfce37cb989`。
- 定向测试：24项通过；Panel校验0错误、0警告。
- 后端全量回归：`661 passed, 4 skipped, 0 failed`。
- 本地 release-check：PASS；QA报告 SHA256
  `6a856ec021352f5b44a2d0587b6ee0bfe2a5fae7d2c96e95ac6db319aebea9f1`。
- 知识工程门禁：PASS；报告 SHA256
  `01a1b8984ba4c2ab3ac7b99bf804c1c94dd88d998dcf8fdf172d0e38174f258a`。
- 现有3份真实输入脱敏验证：PASS，变异数分别为7/8/9，B/C上下文合同
  PASS；验证文件 SHA256
  `e602940c37e49c1239c8a46a14f5f85a0d5261f0b82bd4feca14435ea644232e`。
- 生产只读状态：revision
  `49bae3da7387b7b7f789bcf7e8d7bc8dcdbbc4d4`，进程cwd与
  `current_release`一致，健康检查HTTP 200。

## 分层裁决

- 治疗上下文字段采集：**PASS**。
- 逐候选上下文运行时失败关闭能力：**PASS**。
- CRC301/358非回归：**PASS**。
- 4条候选医学二审与启用：**BLOCKED**。
- 肺588正式病例UAT：**BLOCKED（报告组0/10，仍缺至少7份真实脱敏输入）**。
- iyun129肺588部署：**NOT READY / NOT DEPLOYED**。

下一阶段可以继续做588基因知识深度盘点和PD-L1产品合同；在医学二审及10例
病例级UAT完成前，不得把上下文引擎PASS解释成患者级药物结论已获批准。
