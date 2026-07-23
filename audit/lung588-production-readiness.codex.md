---
module: lung588-production-readiness
agent: codex
identity_kind: git_commit
identity_value: 5077df0b3a073cdba871acdf3b386d78da2b43a2
---

# 肺癌588生产就绪审计（Codex）

本审计只覆盖冻结提交
`5077df0b3a073cdba871acdf3b386d78da2b43a2`。三份真实输入及其
Word/PDF/PNG 只在本地 `.work/` 和 iyun129 受控隔离 QA 目录使用；
Git 仅保存 CASE 别名、内容哈希、聚合计数、规则 selector 与机器验收状态。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-production-readiness-01 | P0 | 肺588候选药物已经进入患者报告运行时。 | `panels/lung_588_pdl1/rules/medical_candidates.yaml:18-27` 明确候选文件不是运行时来源且禁止报告文本；`panels/lung_588_pdl1/rules/drugs.yaml:16-24` 同时关闭靶向规则、基础库和审核药物表。三份真实病例运行时药物行均为0。 | REFUTED |
| lung588-production-readiness-02 | P1 | 两份历史终版中的169条旧药物记录可以按原等级整批迁移。 | `panels/lung_588_pdl1/rules/medical_candidates.yaml:28-49` 记录 A/C/D 分布，只保留4条待二审候选，165条不迁移；历史终版被定义为旧显示合同而非当前医学真理。 | REFUTED |
| lung588-production-readiness-03 | P1 | BRAF p.D594G 可以继承 BRAF V600E 的组合治疗规则。 | `panels/lung_588_pdl1/rules/medical_candidates.yaml:207-222` 将 D594G 作为显式反例；`backend/tests/test_lung588_phase_c_governance.py:176-186` 锁定 D594G 不得进入候选事件。 | REFUTED |
| lung588-production-readiness-04 | P1 | ERBB2 p.G660D 可以因基因相同继承任意 HER2 药物或激酶结构域规则。 | `panels/lung_588_pdl1/rules/medical_candidates.yaml:121-205` 将 G660D 限定为跨膜结构域精确事件并保留适应证条件；`:223-249` 明确宗艾替尼、恩美曲妥珠单抗、吡咯替尼及其余跨癌种/篮式记录不迁移。 | REFUTED |
| lung588-production-readiness-05 | P1 | 历史免疫基因表和化疗PGx表已经具备患者级处方合同。 | `panels/lung_588_pdl1/rules/medical_candidates.yaml:251-267` 将两域均设为历史观察、`enabled:false`、`runtime_eligible:false`；报告运行时仍不展示。 | REFUTED |
| lung588-production-readiness-06 | P2 | 两份历史 Word 的损坏关系只能通过覆盖源文件处理。 | `scripts/repair_docx_relationships.py` 只生成副本并校验源 SHA 不变；`backend/tests/test_lung588_phase_c_governance.py:196-220` 证明失效关系和孤儿节点被移除、原内容与源哈希保持。 | REFUTED |
| lung588-production-readiness-07 | P2 | 肺588在生产同款 Linux 渲染环境仍存在空白页、低内容页或跨癌种串漏。 | `panels/lung_588_pdl1/uat/lung588_machine_pre_uat_20260723.yaml:12-24,43-89`：A/B/C 均27页、机器QA PASS，空白页、异常低内容页和内容失败均为0；使用 iyun129 LibreOffice 7.3.7.2 隔离字体配置。 | REFUTED |
| lung588-production-readiness-08 | P0 | 当前已满足10份真实病例且通过率≥90%的正式UAT。 | `panels/lung_588_pdl1/uat/lung588_machine_pre_uat_20260723.yaml:34-41,91-95`：仅3份真实病例完成机器预UAT，报告组逐病例审核为0/10，仍缺至少7份。 | REFUTED |
| lung588-production-readiness-09 | P1 | 四条精确事件药物候选已经完成报告组医学二审。 | `panels/lung_588_pdl1/rules/medical_candidates.yaml:43-49,73-76,148-151,191-194`：全部仍为 `needs_review`、`runtime_eligible:false`、`pending_report_group_review`。 | REFUTED |
| lung588-production-readiness-10 | P1 | 588基因知识深度、PD-L1抗体/平台及图像合同已全部收口。 | `docs/spec_lung588_pdl1_production_readiness.md:207-210` 与 `panels/lung_588_pdl1/uat/lung588_machine_pre_uat_20260723.yaml:91-95` 均保留这些未决项。 | REFUTED |
| lung588-production-readiness-11 | P2 | 本分支破坏了已稳定的CRC301/358生成链。 | 冻结提交发布总闸16项通过、0警告、0失败；CRC301/358 reference、candidate、repeat diff 均PASS；后端全量656 passed、4 skipped。QA凭据 SHA256=`159811c0…8163`。 | REFUTED |
| lung588-production-readiness-12 | P0 | 冻结提交已经部署为 iyun129 生产版本。 | `panels/lung_588_pdl1/uat/lung588_machine_pre_uat_20260723.yaml:21-24`：测试为隔离副本，生产仍为 `49bae3d…d4`，未切换且健康检查PASS。 | REFUTED |

## 方法保真与限制核实

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-production-readiness-M01 | 历史终版只用于合同抽取，不得当作当前医学真理 | 两份源文件不修改；修复副本仅用于脱敏抽取；169条旧记录先进入非运行时盘点，再按精确事件收敛为4条候选 | FAITHFUL | `docs/spec_lung588_pdl1_production_readiness.md:99-125` |
| lung588-production-readiness-M02 | 药物规则必须按精确事件、癌种、适应证条件、来源和审核状态治理 | BRAF V600E 与 ERBB2 G660D 候选均含 c./p.、肺癌范围、分期/既往治疗/检测条件及结构化来源 | FAITHFUL | `panels/lung_588_pdl1/rules/medical_candidates.yaml:51-205` |
| lung588-production-readiness-M03 | 未完成医学二审的候选不得进入患者报告 | 候选与运行时规则源物理分离；运行时全关闭；三份真实病例均输出0条靶向药物行 | FAITHFUL | `medical_candidates.yaml:18-27`；`drugs.yaml:16-24`；`lung588_machine_pre_uat_20260723.yaml:43-82` |
| lung588-production-readiness-M04 | 视觉QA必须使用生产同款 Linux/LibreOffice 并锁定源码、输入和渲染器身份 | iyun129 隔离目录按源码归档SHA、输入归档SHA、冻结commit和渲染器指纹执行；三份病例全页机器QA通过，生产进程未切换 | FAITHFUL | `panels/lung_588_pdl1/uat/lung588_machine_pre_uat_20260723.yaml:6-32,43-89` |
| lung588-production-readiness-M05 | 不足10份真实病例时不得用合成件或机器QA冒充正式UAT | 已执行全部3份现有冻结真实输入；账本分别记录机器预UAT 3/3 与报告组病例UAT 0/10，并保留7份输入缺口 | HONEST_BOUNDARY | `panels/lung_588_pdl1/uat/lung588_machine_pre_uat_20260723.yaml:34-41,91-95` |
| lung588-production-readiness-M06 | 医学二审、知识深度和PD-L1产品合同未完成时不得晋级或部署 | Panel/模板仍为draft，肺588在知识总闸中为非阻断 `NOT_PRODUCTION_ACTIVE`，生产禁用边界未解除 | HONEST_BOUNDARY | `docs/spec_lung588_pdl1_production_readiness.md:178-185,207-210` |

## 冻结凭据

- 被审提交：`5077df0b3a073cdba871acdf3b386d78da2b43a2`。
- 后端全量回归：`656 passed, 4 skipped, 0 failed`。
- 肺588定向测试：`15 passed`；Panel 校验0错误、0警告。
- 本地 release-check：`PASS`，16项通过、0警告、0失败、1项既有 legacy
  reference 跳过；QA报告 SHA256
  `159811c01161a7cf6d690a3653fb1bef2b11c8328618cd939453d3b3a9788163`。
- 知识工程门禁：`PASS`，issues=0；报告 SHA256
  `3d5ec11d3a020bb889b52a9672f08926c72c4890133ebd737da12e5d42140be9`。
- iyun129机器预UAT：3/3机器PASS；A/B/C均27页，空白页和异常低内容页为0；
  报告组正式病例UAT仍为0/10。
- 生产只读状态：`49bae3da7387b7b7f789bcf7e8d7bc8dcdbbc4d4`，健康检查PASS，
  不是被审提交。

## 分层裁决

- Phase A/B 工程合同：**PASS**。
- Phase C 历史语义盘点与失败关闭候选治理：**PASS**。
- iyun129 Linux机器预UAT：**PASS（3份已观测病例）**。
- 医学二审与正式病例UAT：**BLOCKED**（候选4条待二审；报告组0/10；缺7份真实输入）。
- Promotion / 生产部署：**NOT READY / NOT DEPLOYED**。

本审计不把“有4条可追溯候选”表述成“4条已获医学批准规则”，也不把
Linux机器QA 3/3 表述成报告组逐病例UAT完成。在上述阻断项关闭前，
`lung_588_pdl1` 必须保持 draft 和生产禁用。
