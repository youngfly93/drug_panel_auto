---
module: lung588-controlled-pilot
agent: codex
identity_kind: git_commit
identity_value: b97b8afafc0c417514730c19e557c993c2fe5039
---

# 肺癌588受控试运行审计（Codex）

本审计只覆盖运行时冻结提交
`b97b8afafc0c417514730c19e557c993c2fe5039`。其后
`c8d49c6a14a14186d0ba389e96785fcc4f286f62` 仅追加 Linux QA
验收记录、规格状态和相应契约测试，`ad50b8a` 仅追加下载闸行为测试；两者相对
冻结提交均未修改应用运行代码、模板或医学规则。

本轮按产品负责人要求采用 Codex 单方审计，不生成或冒充 Claude 配对审计。
审计只记录 CASE 别名、聚合结果和收据哈希；三份真实 Excel、生成的
Word/PDF/PNG、患者信息及原始路径均不进入 Git。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-controlled-pilot-01 | P0 | 3份真实病例加7份合成病例等同于10份真实病例UAT。 | `panels/lung_588_pdl1/uat/lung588_controlled_pilot_acceptance.yaml:10-35` 明确七份合成件只提供工程边界覆盖，并禁止声称“ten real cases completed”；正式晋级仍要求10份真实病例。 | REFUTED |
| lung588-controlled-pilot-02 | P0 | 未知PD-L1检测方案可以按22C3、特定染色平台或药物资格解释。 | `panels/lung_588_pdl1/rules/pdl1_product_contract.yaml:58-105` 的试运行方案将克隆、平台和显色系统显示为“原始记录未提供”，只允许同一病例来源记录的TPS/CPS/结果原值转录，禁止阈值重算和用药推导；22C3方案仍为候选且不可运行（`:107-145`）。 | REFUTED |
| lung588-controlled-pilot-03 | P0 | 肺癌588试运行已经启用未经审核的靶向药物或第三部分知识。 | `panels/lung_588_pdl1/panel.yaml:5-10,30-47` 保持 `pilot`，批量和第三部分关闭；Linux七份合成边界报告运行时靶向药物行与第三部分章节均为0。 | REFUTED |
| lung588-controlled-pilot-04 | P0 | 肺癌588报告机器QA通过后可未经人工复核直接下载。 | `backend/app/api/report.py:634-640,707-718,2611-2624` 同时在交付门禁和真实下载路径要求状态为 `reviewed/delivered`；`backend/tests/test_stateless_report_endpoints.py` 的行为测试锁定 draft=409、reviewed=200，并验证CRC358不受影响。 | REFUTED |
| lung588-controlled-pilot-05 | P1 | 七份合成边界病例仅检查脚本返回码，没有生成并视觉检查完整Word。 | iyun129 隔离 QA 使用 Linux、LibreOffice 7.3.7.2 和独立 profile：七份均生成26–27页完整报告，视觉QA 7/7 PASS，空白页0、异常低内容页0；收据SHA256为 `7bcfc8dafbb2065c3b52454aa296679c46965589744580b914e27a3500b28466`。 | REFUTED |
| lung588-controlled-pilot-06 | P1 | 三份现有真实肺癌NGS输入尚未经过生产同款Linux渲染。 | 三份脱敏别名 CASE-LUNG-A/B/C 均生成27页报告，视觉QA 3/3 PASS，空白页和异常低内容页均为0；变异数分别为7/8/9，收据SHA256为 `bbc72c83c4a37263d173ca7f18cad75306323d9cb4325a4e74a85a144168b8a5`。 | REFUTED |
| lung588-controlled-pilot-07 | P1 | 现有三份机器病例证明了真实PD-L1病例来源、抗体克隆和平台。 | 验收记录中 `verified_case_specific_ihc_source_count: 0`，三份机器病例只验证NGS映射与保守转录合同；实际克隆、平台和逐病例IHC来源仍未确认。 | CONFIRMED |
| lung588-controlled-pilot-08 | P1 | 当前已经满足肺癌588正式 active 发布条件。 | 验收记录明确 active 状态为 BLOCKED：仅3/10真实病例、0/3真实IHC来源、实际PD-L1方案未知，且靶向药物、第三部分和批量生成仍关闭。 | REFUTED |
| lung588-controlled-pilot-09 | P1 | 冻结提交在本审计时已经切换为iyun129生产版本。 | 隔离QA执行期间生产仍为 `49bae3da7387b7b7f789bcf7e8d7bc8dcdbbc4d4` 且健康检查PASS；本审计不把隔离渲染描述为生产部署。 | REFUTED |
| lung588-controlled-pilot-10 | P2 | 本轮试运行改动会重新打开或覆盖现有CRC肠癌规则。 | 肺癌配置独立归属 `panels/lung_588_pdl1/`；下载闸按项目类型限定；CRC358 draft下载行为测试仍为200。冻结提交的CRC回归需继续由发布总闸验证后方可部署。 | REFUTED |

## 方法保真与限制核实

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-controlled-pilot-M01 | 不足10份真实病例时不得用合成件补足医学UAT | 真实病例与合成病例分别记账为3与7；正式晋级分母仍为10份真实病例 | FAITHFUL | `lung588_controlled_pilot_acceptance.yaml:10-35,118-130` |
| lung588-controlled-pilot-M02 | PD-L1未知方法必须显式显示未知且禁止治疗推导 | 试运行方案只转录逐病例来源记录，克隆/平台/显色系统三项均为“原始记录未提供”，22C3保持不可运行 | FAITHFUL | `pdl1_product_contract.yaml:58-145`；`reportgen/rules/pdl1.py:167-211` |
| lung588-controlled-pilot-M03 | 每份报告必须携带逐病例来源与标本身份 | 运行时要求 source record ID/date、specimen ID、profile ID 和图像处置，缺任一项即失败关闭 | FAITHFUL | `pdl1_product_contract.yaml:33-44`；`reportgen/rules/pdl1.py:214-276` |
| lung588-controlled-pilot-M04 | Word视觉QA使用生产同款Linux渲染器 | 10份报告均在iyun129隔离目录以Linux/LibreOffice 7.3.7.2、独立profile执行全页QA | FAITHFUL | 验收记录 `environment` 与两份本地受控收据 |
| lung588-controlled-pilot-M05 | 机器QA不得冒充报告组逐病例医学审核 | 机器结果只允许作为工程试运行证据；下载前仍需任务级人工复核，active晋级保持BLOCKED | HONEST_BOUNDARY | `backend/app/api/report.py:707-718,2611-2624`；验收记录 `release_decision` |
| lung588-controlled-pilot-M06 | 不得把历史或合成PD-L1数值当作真实病例IHC来源 | 三份机器病例的真实IHC来源计数明确为0；当前只证明转录合同可运行 | HONEST_BOUNDARY | 验收记录 `results.confirmed_real_ngs` |

## 冻结凭据

- 运行时冻结提交：
  `b97b8afafc0c417514730c19e557c993c2fe5039`。
- Linux隔离QA源码归档SHA256：
  `85de784da8d63fcbc4db0b587fbf3841a1187027fc482f3d6828723d43cf6241`。
- 七份合成边界报告：7/7机器与视觉PASS，页数
  `26,26,26,26,26,26,27`，空白页0，异常低内容页0。
- 三份已确认真实NGS输入：3/3机器与视觉PASS，均27页，空白页0，
  异常低内容页0；不记录真实文件名。
- 受控收据：
  `.work/lung588_controlled_pilot_linux_b97b8af/synthetic/validation.json`
  与
  `.work/lung588_controlled_pilot_linux_b97b8af/real/validation.json`；
  收据文件处于 Git 外，仅在本地受控工作区保存。
- 定向契约与下载闸回归：15 passed，0 failed；此前冻结定向集合
  54 passed，0 failed。
- 生产测试期间版本：
  `49bae3da7387b7b7f789bcf7e8d7bc8dcdbbc4d4`；未发生切换。

## 分层裁决

- 3份现有真实NGS输入：**ENGINEERING PASS（3/3）**。
- 7份合成边界覆盖：**ENGINEERING PASS（7/7）**。
- Linux完整Word视觉QA：**PASS（10/10，空白页0）**。
- PD-L1保守原值转录合同：**CONTROLLED PILOT PASS**。
- 逐病例真实IHC来源：**BLOCKED（0/3已验证）**。
- 正式真实病例UAT：**BLOCKED（3/10输入可用）**。
- 靶向药物、第三部分、批量生成：**DISABLED / 不在本轮放行范围**。
- iyun129肺癌588：**仅允许受控试运行部署；不得称为active医学发布**。
