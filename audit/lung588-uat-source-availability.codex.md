---
module: lung588-uat-source-availability
agent: codex
identity_kind: git_commit
identity_value: 48d342c70a2a423aab2c981133d5c2a8dfc4a61b
---

# 肺癌588 UAT来源可得性审计（Codex）

本审计只覆盖规格文档提交
`48d342c70a2a423aab2c981133d5c2a8dfc4a61b`。目标是确认现有受控资料能否
补齐真实PD-L1检测产品、逐病例IHC来源和至少10份真实肺癌病例。本审计只记录
脱敏别名、哈希和聚合计数，不提交患者文件、路径、姓名或样本号，不修改运行
规则，也不部署生产。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-uat-source-availability-01 | P0 | 两份历史终版已经记录了可直接启用的PD-L1抗体克隆和染色平台。 | 两份固定Word的PD-L1表均只有“检测项目/检测方法/TPS/CPS/结果判定”，数据行仅写“PD-L1蛋白表达/免疫组化/数值/结果”；22C3、28-8、SP263、SP142、Autostainer、Ventana、Dako、EnVision均未命中。 | REFUTED |
| lung588-uat-source-availability-02 | P0 | 历史终版中的显微图可以替代原始IHC记录和标本身份。 | CASE-LUNG-B/C图片哈希不同，但图内无可读方法标签；Word未记录原始IHC编号、标本身份或图片来源映射，故只能证明存在两张图，不能证明可追溯性。 | REFUTED |
| lung588-uat-source-availability-03 | P0 | 本地已经有至少10份可确认的真实肺588病例。 | 受控扫描仅有3个已冻结真实肺癌哈希；唯一额外肺癌路径工作簿含`Meta`页和“肺测试”合成标记，不能计入UAT。 | REFUTED |
| lung588-uat-source-availability-04 | P1 | 16个无癌种路径标签的工作簿可直接按肺癌补入。 | 其中1个可由同样本历史报告归为CRC，15个缺少可用外部癌种映射；未找到任何仅由肺癌兄弟报告确认的哈希。它们属于“未分类”，不是肺癌正例，也不能被宣称已排除。 | REFUTED |
| lung588-uat-source-availability-05 | P1 | 可从TPS/CPS数值反推出22C3或其它检测产品。 | 两例分别有TPS/CPS结果但无克隆/平台字段；相同数值字段不构成检测产品身份，当前产品合同继续失败关闭。 | REFUTED |
| lung588-uat-source-availability-06 | P1 | 现有资料穷尽后，工程侧仍没有可交给报告组的最小回填入口。 | 已生成本地受控4-sheet收集表，含10个CASE槽位、3个已冻结哈希和7个空位，以及PD-L1方案二审字段；公式数0，患者姓名数0。 | REFUTED |
| lung588-uat-source-availability-07 | P1 | 本次可得性核查改变了肺588或CRC运行行为。 | 被审提交只修改规格文档7行；候选规则、运行配置、模板、后端和生产均未修改。 | REFUTED |

## 方法保真与边界

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-uat-source-availability-M01 | 真实病例可得性必须按内容哈希去重 | 扫描911份xlsx副本，863份可读；所需12-sheet结构命中202份副本、36个唯一哈希，已冻结肺癌真实哈希仅3个 | FAITHFUL | `.work/lung588_uat_source_availability_20260724/source_availability.json:excel_availability` |
| lung588-uat-source-availability-M02 | 同结构Excel不得自动等同肺癌 | 33个未登记唯一哈希按路径、合成标记和同样本报告再分类；16个CRC路径、1个肺路径合成件、16个无标签，其中15个仍诚实保留未分类 | FAITHFUL | 同一收据`unregistered_path_label_counts`与`unlabeled_resolution` |
| lung588-uat-source-availability-M03 | Word方法字段必须从固定源文件读取 | 按完整SHA锁定CASE-LUNG-B/C源Word；仅在`/tmp`副本移除各1个失效`../NULL`关系后读取，不改源文件 | FAITHFUL | 收据`historical_pdl1_source_review.documents` |
| lung588-uat-source-availability-M04 | 图片存在不得冒充来源可追溯 | 分别锁定两张章节图片SHA；OCR字符数0，人工视觉只见染色图，无方法或病例来源标识 | HONEST_BOUNDARY | 收据`historical_pdl1_source_review.chapter_images` |
| lung588-uat-source-availability-M05 | 无法分类的病例不得静默归入或排除 | 15个无外部癌种映射哈希明确留为unclassifiable，需受控映射后才能决定 | HONEST_BOUNDARY | 收据`additional_real_lung_case_count_interpretation` |
| lung588-uat-source-availability-M06 | 报告组回填件不得含患者PII或进入Git | 收集表仅含CASE别名与已有SHA；输出位于gitignored `output/`，权限600，收据声明患者姓名0 | FAITHFUL | `output/lung588_report_group_uat_intake.receipt.json` |

## 冻结凭据

- 被审规格提交：
  `48d342c70a2a423aab2c981133d5c2a8dfc4a61b`。
- 脱敏可得性收据SHA256：
  `4cc44b55af8387766ea34bc79cbbc0d0857cae4a6a793627a0cbf22e44d7e0ce`。
- 历史终版SHA256：
  CASE-LUNG-B `8c9cb41572686445f2a06070049e262eb2b7d77eb64e0219b6bba2f4206daead`；
  CASE-LUNG-C `4754ededa67eeeef1b716dd7fb9e907d03c8fd79904a64f48bd271119c9a401b`。
- PD-L1章节图片SHA256：
  CASE-LUNG-B `aaec9fc11533160600149067cc045a713d66bf3eeddb4a1e0ff8520d13e06a3c`；
  CASE-LUNG-C `9d0846dc0d5022eedf8003efde26d9625ecc10edf456e2b44d8673b9095912d4`。
- 报告组UAT收集表SHA256：
  `eb803aae2091abd424136b5dac8c927eb111f4f634073f96adb7f9b6e545f056`；
  4个工作表、10个CASE槽位、3例预填、7例待补、公式0、患者姓名0；
  PD-L1二审与病例UAT宽表已用LibreOffice按A3横向完成视觉检查。
- 本提交不改变此前固定工程门禁结果；未重新声明医学发布PASS。

## 分层裁决

- 现有3份真实NGS输入：**AVAILABLE / 已冻结**。
- 可新增计入UAT的真实肺癌病例：**0份已确认；15个哈希仍需外部癌种映射**。
- 实际PD-L1检测产品身份：**NOT RECOVERABLE FROM CURRENT FILES**。
- 逐病例IHC来源和标本身份：**NOT RECOVERABLE FROM CURRENT FILES**。
- 报告组最小回填入口：**READY（本地受控Excel）**。
- 肺588正式UAT：**BLOCKED（3/10输入、0/3真实PD-L1来源、0/10报告组决定）**。
- 肺588部署：**NOT READY / NOT DEPLOYED**。
