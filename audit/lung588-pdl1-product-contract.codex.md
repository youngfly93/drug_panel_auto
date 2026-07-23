---
module: lung588-pdl1-product-contract
agent: codex
identity_kind: git_commit
identity_value: d67a97e2252c683fb6fb708155f9fbb43b9c7c73
---

# 肺癌588 PD-L1产品合同审计（Codex）

本审计只覆盖冻结提交
`d67a97e2252c683fb6fb708155f9fbb43b9c7c73`。目标是验证PD-L1结果是否
绑定具体检测方案、逐病例原始IHC记录和标本身份，确认没有已批准方案时
Web与直接生成接口均失败关闭，并区分工程验证、医学二审和正式病例UAT。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-pdl1-product-contract-01 | P0 | 肺癌NGS Excel中的字段可作为PD-L1患者结果来源。 | `panels/lung_588_pdl1/rules/pdl1_product_contract.yaml:7-10,29-40` 明确NGS不是PD-L1来源，并要求逐病例原始记录、日期和标本身份。 | REFUTED |
| lung588-pdl1-product-contract-02 | P0 | 只要填写TPS、CPS和高/低/阴性即可生成交付报告。 | `pdl1_product_contract.yaml:12-27,54-61` 当前无运行方案且禁止报告文本；`reportgen/core/report_generator.py:1043-1067` 在输入阶段以独立错误码阻断。 | REFUTED |
| lung588-pdl1-product-contract-03 | P0 | 登记22C3参考资料代表报告组实际使用的就是22C3 pharmDx。 | `pdl1_product_contract.yaml:56-68,132-137` 将其标为不可运行候选，并挂起实际方案名称、克隆、平台和二审确认。 | REFUTED |
| lung588-pdl1-product-contract-04 | P0 | TPS 1%/50%可作为所有PD-L1检测方案的通用分层。 | `panels/lung_588_pdl1/panel.yaml:134-163` 通用层只校验原始数值范围；`pdl1_product_contract.yaml:78-92` 由具体22C3/NSCLC候选持有分层；`reportgen/rules/pdl1.py:66-151` 按所选profile校验。 | REFUTED |
| lung588-pdl1-product-contract-05 | P0 | 候选方案ID即使未二审，也能通过直接API绕过前端生成Word。 | `reportgen/rules/pdl1.py:154-230` 同时校验顶层合同、运行列表、profile运行资格和二审状态；`backend/tests/test_lung588_contract.py:610-665` 端到端断言直接生成被阻断且无DOCX。 | REFUTED |
| lung588-pdl1-product-contract-06 | P0 | 模板可以继续复用历史病例的固定PD-L1显微图。 | `pdl1_product_contract.yaml:42-52` 禁止静态病例图；`scripts/build_lung588_template.py:90-95,625-647` 要求无图说明和来源占位；`backend/tests/test_lung588_contract.py:181-239` 锁定源图媒体哈希不进入新模板。 | REFUTED |
| lung588-pdl1-product-contract-07 | P0 | 选定检测方案后可从TPS/CPS直接推导免疫治疗用药。 | `pdl1_product_contract.yaml:19-22,73-97` 禁止治疗推断，并限定CPS仅转录、22C3候选仅做方案内展示分层。 | REFUTED |
| lung588-pdl1-product-contract-08 | P1 | Web表单会把待二审候选显示成可选运行方案。 | `backend/app/services/clinical_info_service.py:284-318,350-361` 只有同时进入运行列表、允许报告文本并完成二审的profile才显示；当前选项为空。 | REFUTED |
| lung588-pdl1-product-contract-09 | P1 | 旧的3份肺癌机器预UAT可继续证明PD-L1产品已通过。 | `scripts/validate_lung588_real_inputs.py:109-129,174-218,401-428` 明确旧值为合成视觉QA来源并纳入产品门禁；固定提交复测3/3均因产品合同按预期FAIL。 | REFUTED |
| lung588-pdl1-product-contract-10 | P1 | 新增肺癌PD-L1门禁改变了CRC301/358既有报告行为。 | 固定提交全后端回归`672 passed, 4 skipped`；release-check中CRC301/358参考、候选、重复diff和当前输出检查全部PASS。 | REFUTED |
| lung588-pdl1-product-contract-11 | P1 | 本提交已经具备肺588医学发布和iyun129生产部署条件。 | `docs/spec_lung588_pdl1_production_readiness.md:242-258` 明确实际方案二审和病例UAT未完成；肺588严格知识门禁仍有4类阻断；本提交未执行部署。 | REFUTED |

## 方法保真与理由核实

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-pdl1-product-contract-M01 | PD-L1结果必须回溯逐病例IHC来源，不得由NGS或共享批次值自证 | 要求方案ID、原始记录编号/日期、标本ID和图像处置，明确禁止NGS推断和共享值 | FAITHFUL | `pdl1_product_contract.yaml:29-40`；`panel.yaml:107-163` |
| lung588-pdl1-product-contract-M02 | 检测方法、评分和阈值必须按具体产品/癌种边界治理 | 22C3、平台、显色系统、NSCLC、TPS和分层均在单一候选profile中；通用Panel层不再持有1%/50%分层 | FAITHFUL | `pdl1_product_contract.yaml:56-131`；`panel.yaml:134-163` |
| lung588-pdl1-product-contract-M03 | 医学二审前不得显示或运行候选方案 | 顶层合同、运行列表、profile三重关闭；前端无选项，后端重复验证并阻断 | FAITHFUL | `pdl1_product_contract.yaml:12-22,54-61`；`clinical_info_service.py:284-318`；`report_generator.py:1043-1067` |
| lung588-pdl1-product-contract-M04 | 分层结果必须与方案所属原始评分字段一致 | profile声明必需评分字段和分层范围；实现拒绝缺失、非数值、未声明分类及范围不一致，0值边界有回归测试 | FAITHFUL | `reportgen/rules/pdl1.py:56-151`；`test_lung588_contract.py:540-597` |
| lung588-pdl1-product-contract-M05 | 图像必须逐病例可追溯；管线未实现时失败关闭 | 当前仅允许“无病例专属图像且不展示”，其它处置被拒；固定历史图已从模板媒体中移除 | HONEST_BOUNDARY | `pdl1_product_contract.yaml:42-52`；`reportgen/rules/pdl1.py:232-263`；模板媒体回归测试 |
| lung588-pdl1-product-contract-M06 | 工程测试不得冒充医学UAT | 真实NGS复测显式标记PD-L1值为`synthetic_visual_qa_only`并输出产品合同FAIL；spec将报告组病例UAT保持0/10 | HONEST_BOUNDARY | `validate_lung588_real_inputs.py:109-129,214-218,409-428`；`spec_lung588_pdl1_production_readiness.md:253-258` |
| lung588-pdl1-product-contract-M07 | 模板变化必须可重建、无患者硬编码且做页级视觉QA | 构建脚本要求方案/来源占位与无图说明；模板重复构建字节哈希一致；硬编码扫描0 HARD/0 SOFT；LibreOffice渲染24页、0近空白页 | FAITHFUL | `scripts/build_lung588_template.py:625-647,853-864`；固定提交验证凭据 |
| lung588-pdl1-product-contract-M08 | 工程总闸与肺588医学发布状态必须分层裁决 | 活动生产Panel工程release-check PASS；肺588严格知识门禁按预期FAIL，PD-L1二审和病例UAT未完成 | HONEST_BOUNDARY | 固定提交release-check；肺588严格知识门禁；本审计分层裁决 |

## 冻结凭据

- 被审业务提交：
  `d67a97e2252c683fb6fb708155f9fbb43b9c7c73`；开审时业务工作树干净。
- PD-L1产品合同 SHA256：
  `922e842f2fb65e93c2892e61606b71fa5d6341ea65cc1d2128e59e29eca9d901`。
- 肺588 Panel校验：PASS，11个规则文件，0 errors、0 warnings；收据 SHA256：
  `e3c406c37eab60f2766d69169a0a06677a40f7542824a83d6db8a32d4d3112be`。
- 聚焦回归：肺癌合同、治理和API边界共`46 passed`。
- 全后端回归：`672 passed, 4 skipped, 0 failed`。
- 固定提交本地release-check：PASS；16项工程检查PASS、1项legacy跳过、
  GitHub远端检查按声明未执行。QA报告 SHA256：
  `ee02e9c5417beabcb29ebf4e176694790c54d40f0cef636abdd3fa7ccbecdaf7`。
- 活动Panel知识总闸 SHA256：
  `d3104e1c59513e0cd292fc9b7ea0ae674965cdf1e264cff7beba55df2baaba38`。
- 3份真实肺癌NGS输入产品预UAT：整体FAIL，3/3均只因PD-L1产品合同未批准；
  收据 SHA256：
  `feac3411ffbcef04fe3eb12d6109090f0fe7a4701e90dc3004bbe5644a96c385`。
- 肺588严格知识门禁按预期FAIL：247个运行解释缺口、247个未知变异解析
  缺口、551个固定结构域缺口和1个来源错配；收据 SHA256：
  `e10890af4f13c3d3cf242c0de2b0232d73771cd006c70f04334425ece956084e`。
- 模板 SHA256：
  `a3e837c1a63891153c88169aaf307709a35f85c177af8e55e5ff0743e94d3c9b`；
  重建两次字节一致。macOS LibreOffice 25.8渲染24页、0近空白页；视觉
  收据 SHA256：
  `d9783208cb8c6d3e8ec93a19d5ca8d34a92727e60614bfd633a4afd28702051e`。
- 模板患者硬编码扫描0 HARD、0 SOFT；收据 SHA256：
  `823bc9e9a0c757a19f5ff1a1b0e521ba541fe969fe98a481e25253b6243e9caa`。
- 当前未获得报告组实际PD-L1方案、克隆、平台或逐病例IHC原始记录；未执行
  Linux候选渲染、正式病例医学UAT、iyun129部署或活实例验收，本审计不虚构这些凭据。

## 分层裁决

- PD-L1来源、方案和图像失败关闭机制：**PASS（工程）**。
- 22C3/NSCLC参考候选的来源边界记录：**PASS（非权威Codex一审）**。
- 22C3候选医学二审：**PENDING / 不可运行**。
- 实际报告组PD-L1检测方案：**UNKNOWN / BLOCKED**。
- 3份真实NGS结构预UAT：**输入结构可复核，但PD-L1产品均按预期BLOCKED**。
- 肺588知识医学完善：**BLOCKED**。
- 肺588正式病例UAT：**BLOCKED（报告组0/10）**。
- iyun129生产部署：**NOT READY / NOT DEPLOYED**。

下一阶段应由报告组提供实际PD-L1检测方案名称、抗体克隆、染色/显色平台、
评分方法及一份脱敏原始IHC记录样例；完成方案二审和正反例后，才能将对应
profile加入运行列表。与此同时继续处理肺588严格知识门禁中的247/247/551
缺口和STK11来源错配，不能用PD-L1工程合同PASS替代整个Panel医学发布。
