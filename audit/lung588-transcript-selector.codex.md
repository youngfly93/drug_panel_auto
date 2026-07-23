---
module: lung588-transcript-selector
agent: codex
identity_kind: git_commit
identity_value: 9600a4b1fc6c0aa9d54d884dbf790b31a5eb6155
---

# 肺癌588药物规则转录本边界审计（Codex）

本审计只覆盖冻结提交
`9600a4b1fc6c0aa9d54d884dbf790b31a5eb6155`。审计目标是验证药物规则
声明转录本后，FieldMapper、模板构建和 Word 后处理均按 accession+version
精确匹配；同时确认未声明转录本的既有 CRC 规则保持兼容，肺癌588候选没有
因此被提前启用。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-transcript-selector-01 | P0 | 候选文件写入 NM 转录本即可保证未来运行时按转录本匹配。 | `reportgen/rules/targeted_drugs.py:161-194` 新增统一 selector 解析和精确版本匹配；修复前运行链没有该检查。 | REFUTED |
| lung588-transcript-selector-02 | P0 | 声明 `NM_004333.6` 的规则可在转录本缺失或 `.5` 版本输入上命中。 | `backend/tests/test_lung588_phase_c_governance.py:400-469` 覆盖正确版本、缺失和错误版本；只有 `.6` 命中转录本限定 selector。 | REFUTED |
| lung588-transcript-selector-03 | P0 | 同 c./p. 的通用活动规则可越过更精确的转录本级阻断规则。 | `reportgen/rules/targeted_drugs.py:197-252` 将转录本纳入 specificity；`backend/tests/test_lung588_phase_c_governance.py:419-442` 证明正确转录本返回 `--/--`，不能被通用行重开。 | REFUTED |
| lung588-transcript-selector-04 | P0 | 只修 FieldMapper 即可，Word 后处理忽略转录本不会产生差异。 | `reportgen/core/template_bridge_358.py:1364-1466` 与 `:2881-3049` 共用同一匹配语义；`backend/tests/test_report_regression.py:1902-1945` 验证正确、错误和缺失转录本的最终行更新。 | REFUTED |
| lung588-transcript-selector-05 | P1 | 加入第五个回调参数会破坏历史四参数药物查询扩展。 | `reportgen/core/template_bridge_358.py:1542-1583` 按签名兼容四参数与转录本感知回调；既有混合分级药物行回归继续通过。 | REFUTED |
| lung588-transcript-selector-06 | P1 | 待审阻断规则仍可让原始 Excel 的 `Drug` 字段或宽药物库在模板构建阶段漏入。 | `reportgen/core/template_bridge_358.py:1660-1725` 在模板构建时保留 blocked 状态并跳过回调，药物及研究药物固定为 `--`。 | REFUTED |
| lung588-transcript-selector-07 | P0 | 通用运行时修复改变了 CRC301/358 已审核报告。 | 固定提交 release-check 的 CRC301/358 reference、candidate、repeat diff 和 current output 全部 PASS；QA 报告 SHA256 为 `7284ebbf2a5168bd21a57b899f81cf1ad645b87c0449afc49890e6c744d26652`。 | REFUTED |
| lung588-transcript-selector-08 | P0 | 转录本门禁通过表示肺癌588的4条候选已经可写入患者报告。 | `docs/spec_lung588_pdl1_production_readiness.md:221-240` 仍记录候选 `runtime_eligible:false`、二审0、病例 UAT 0/10，Panel 继续为工程草案。 | REFUTED |

## 方法保真与限制核实

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-transcript-selector-M01 | 医学事件 selector 使用基因、转录本版本、c./p. 和分级，不得只按基因继承 | 统一匹配器把声明的 transcript 作为精确可选边界，既有 c./p./class 条件继续同时生效 | FAITHFUL | `reportgen/rules/targeted_drugs.py:161-252`；`reportgen/core/_field_mapper_targeted_drugs.py:300-359` |
| lung588-transcript-selector-M02 | 声明转录本后，缺失和版本错配不得被推断为命中 | 规则有 transcript 时要求非空且完整字符串相等；正例、缺失反例和版本反例均有确定性测试 | FAITHFUL | `backend/tests/test_lung588_phase_c_governance.py:400-469` |
| lung588-transcript-selector-M03 | 同一 selector 语义必须贯穿数据映射、摘要表和 Word 后处理 | FieldMapper 传递源转录本，targeted tips 保留转录本，Bridge 的选择、检测和补丁路径均传递该字段 | FAITHFUL | `reportgen/core/field_mapper.py:1088-1108`；`reportgen/core/_field_mapper_targeted_drugs.py:1028-1174`；`reportgen/core/template_bridge_358.py:2881-3049` |
| lung588-transcript-selector-M04 | 现有未声明 transcript 的规则不得因新门禁失效 | 无 transcript selector 时统一匹配器返回兼容路径；四参数回调保留；CRC 双 Panel 金标和全量后端回归均通过 | FAITHFUL | `reportgen/rules/targeted_drugs.py:190-194`；`reportgen/core/template_bridge_358.py:1542-1583`；冻结凭据 |
| lung588-transcript-selector-M05 | 工程能力与医学启用状态必须分开 | 运行引擎已具备 selector 能力，但肺588药物总开关、候选 runtime 状态、二审和正式 UAT 均未改变 | HONEST_BOUNDARY | `panels/lung_588_pdl1/rules/drugs.yaml`；`panels/lung_588_pdl1/rules/medical_candidates.yaml`；生产就绪 spec |

## 冻结凭据

- 被审提交：
  `9600a4b1fc6c0aa9d54d884dbf790b31a5eb6155`；开审时业务工作树干净。
- 定向药物/模板/肺癌回归：`312 passed, 2 skipped, 0 failed`。
- 后端全量回归：`669 passed, 4 skipped, 0 failed`。
- 固定提交本地 release-check：PASS；16项通过、0失败、1项 legacy 跳过。
- QA 报告 SHA256：
  `7284ebbf2a5168bd21a57b899f81cf1ad645b87c0449afc49890e6c744d26652`。
- 知识发布门禁报告 SHA256：
  `56f878b3a56a7a061d427713bf94891c641402f5e10f7a6df0fe96cd5998802d`。
- 历史合同报告 SHA256：
  `3470eaf51376b27adad0a76f8cef9eabeebc46a9de6f654ccbf1eb603923dafc`。
- `delivery/proof.json` 不存在；本审计不虚构交付 proof，也未执行 GitHub
  分支检查、生产部署或病例医学放行。

## 分层裁决

- 转录本级运行时 selector：**PASS**。
- 缺失/错误版本反例与 blocked 优先级：**PASS**。
- 四参数历史扩展兼容：**PASS**。
- CRC301/358 工程非回归：**PASS**。
- 肺癌588候选医学二审：**BLOCKED**。
- 肺癌588正式病例 UAT：**BLOCKED（报告组0/10）**。
- 肺癌588生产部署：**NOT READY / NOT DEPLOYED**。

下一阶段可以在此 selector 基础上逐条复核 P0 药物候选的来源、癌种、病理、
分期和既往治疗边界；在二审与正式 UAT 完成前，不得把4条候选写入运行时
`reviewed_variant_overrides`。
