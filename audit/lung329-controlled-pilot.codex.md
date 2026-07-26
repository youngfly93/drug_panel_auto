---
module: lung329-controlled-pilot
agent: codex
identity_kind: git_commit
identity_value: ee7a10737f0d4fee279dd7fdae87e200984f2500
---

# 肺癌329受控试运行发布审计（Codex）

本审计只覆盖冻结业务提交
`ee7a10737f0d4fee279dd7fdae87e200984f2500`。项目负责人明确要求本轮由
Codex 自审，不要求 Claude 配对审计。肺癌329仅按单病例受控试运行发布，
不等同于患者级医学知识、治疗规则或真实病例 UAT 已完成。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung329-controlled-pilot-01 | P0 | 旧329模板可继续作为 deprecated 资产随生产包发布。 | 冻结提交从 Panel 注册和当前 Git tip 删除 v0/v1，只注册经清理并锁定哈希的 v2；测试断言旧模板不存在且运行模板集合只有 v2。 | REFUTED |
| lung329-controlled-pilot-02 | P0 | 删除正文中的显微图后，病例图和失联媒体不会再构成风险。 | 自审发现 v2 压缩包仍有36个媒体部件，其中1个病例级 PD-L1 图仍被引用、25个为孤儿；修复后只保留9个被关系引用的通用素材，病例图字节哈希被生成器阻断，孤儿媒体测试固定为0。 | REFUTED |
| lung329-controlled-pilot-03 | P0 | 普通操作员可通过同步接口或审计包绕过人工复核取得未审核 DOCX。 | 受控 Panel 响应不再内嵌 Base64 文件；主下载继续阻断；未审核审计包仅 reviewer/admin 可取，审核完成后任务所属操作员才可下载。 | REFUTED |
| lung329-controlled-pilot-04 | P0 | 肺癌 NGS Excel 可以作为 PD-L1 来源，或整批病例共享一组 TPS/CPS。 | 产品合同声明 NGS Excel 不是 PD-L1 来源；TPS、CPS、结果、来源记录、日期、标本和图像处置均逐病例必填；前端与后端批量入口同时关闭。 | REFUTED |
| lung329-controlled-pilot-05 | P0 | 未提供真实抗体克隆和平台时，系统可以默认写成22C3并推导用药资格。 | 唯一运行配置为 `legacy_unspecified_ihc_transcription_v1`，只转录原始记录并显示方法未知；22C3仅为不可运行候选，7例边界报告均无22C3或治疗适应证推断。 | REFUTED |
| lung329-controlled-pilot-06 | P0 | 复用CRC增强器会把CRC药物、免疫基因或第三部分知识带入肺癌报告。 | 肺癌规则包显式关闭基础药物库、内部候选、固定药物行和第三部分；三类免疫集合显式为空且桥接层区分“未声明”和“声明为空”；7例报告药物行、第三部分患者知识和免疫结果行均为0。 | REFUTED |
| lung329-controlled-pilot-07 | P1 | 329个报告基因已全部完成肺癌医学知识审核。 | 运行覆盖实测为258/329（78.42%），第三部分和治疗规则因此保持关闭；工程边界 PASS 不被表述为医学知识完成。 | REFUTED |
| lung329-controlled-pilot-08 | P1 | 删除固定“10例”阈值等于真实病例 UAT 已完成。 | 风险策略只允许无真实病例时标记 controlled pilot；合成7例明确不计真实 UAT，临床发布状态继续 BLOCKED。 | REFUTED |
| lung329-controlled-pilot-09 | P1 | 本提交已通过生产同款 Linux 视觉 QA 并部署到 iyun129。 | 冻结时仅完成本地工程和合成边界验证；Linux候选、GitHub required check、生产切换和活实例验收仍是后续发布步骤。 | REFUTED |
| lung329-controlled-pilot-10 | P0 | 删除当前 tip 的旧模板即可清除远端历史风险。 | 远端仓库为公开仓库；普通提交只能清理当前 tip，历史 Git 对象仍需独立授权的历史清除与安全事件处置。当前发布不得宣称仓库历史已完成隐私清理。 | CONFIRMED |

## 方法保真与限制

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung329-controlled-pilot-M01 | 329只能以单病例、逐病例PD-L1来源、审核后下载方式试运行 | 前端标识“单份受控试运行”；后端批量策略、下载和审计包三条路径均失败关闭 | FAITHFUL | `panel.yaml`、`report.py`、`clinical_info_service.py` |
| lung329-controlled-pilot-M02 | 医学内容未审核时不得用通用知识补齐患者结论 | 药物、免疫、化疗PGx和第三部分均关闭，并显示边界说明 | FAITHFUL | `rules/drugs.yaml`、`rules/biomarkers.yaml`、`part3_knowledge` |
| lung329-controlled-pilot-M03 | 模板不得携带患者文本、病例图片或孤儿媒体 | 严格文字扫描0；v2媒体9/9均被引用；历史病例图与旧模板从当前tip移除 | FAITHFUL | v2 SHA、媒体合同测试、提交diff |
| lung329-controlled-pilot-M04 | 新肺癌线不得冲刷CRC301/358既有生产行为 | 全量707项通过；CRC301/358知识门禁PASS、issues=0；肺癌显式空集合不改变未声明集合的兼容默认 | FAITHFUL | 全量回归与知识门禁凭据 |
| lung329-controlled-pilot-M05 | 合成边界病例不得冒充真实医学UAT | 策略文件和结果均写明 synthetic、`counts_as_clinical_uat:false`；无真实病例时临床状态BLOCKED | HONEST_BOUNDARY | `uat/lung329_risk_based_release_policy.yaml` |
| lung329-controlled-pilot-M06 | 生产部署必须锁定精确Git身份并用Linux同款渲染 | 冻结提交已形成；Linux渲染、CI和部署后验收尚未发生 | PENDING | 后续发布阶段 |
| lung329-controlled-pilot-M07 | 当前tip去敏不得冒充Git历史已清除 | 审计显式记录公开仓库历史仍需另行授权处置 | HONEST_BOUNDARY | 远端可见性与提交历史检查 |

## 冻结凭据

- 被审业务提交：
  `ee7a10737f0d4fee279dd7fdae87e200984f2500`；父提交与
  `origin/main` 精确一致。
- 后端全量回归：`707 passed, 4 skipped, 0 failed`；唯一 warning 为仓库
  既有未注册 `slow` 标记。
- 肺癌329合成边界套件：7/7 PASS；每例机器 QA PASS；药物、第三部分患者
  知识和免疫分类结果均为空。
- Panel package 校验：PASS，0 errors、0 warnings。
- v2 模板 SHA256：
  `13d935be3f904d7400d0410ca8267a3d021806e21b708a58fa2f36eaee95e98a`；
  硬编码文本扫描0；媒体部件9，孤儿媒体0。
- CRC301/358知识发布门禁：PASS，issues=0。
- 前端生产构建：PASS；构建范围仅开放CRC358和肺癌329受控试运行。
- 公开指南来源核对：PMID 39375078、PMID 29355391及NCI NSCLC PDQ标题
  与模板引用用途一致；模板不据此生成患者级治疗结论。

## 分层裁决

- 肺癌329工程受控边界：**PASS**。
- 当前 Git tip 模板去敏：**PASS**。
- 真实病例医学 UAT：**NOT COMPLETED**。
- 肺癌329患者级药物、免疫、化疗和第三部分知识：**BLOCKED / DISABLED**。
- PD-L1正式检测产品（真实克隆、平台、评分合同）：**BLOCKED**。
- 远端 Git 历史隐私清除：**OPEN SECURITY REMEDIATION，需独立授权**。
- iyun129上线：**待Linux精确SHA视觉QA、required check和部署后活实例验收**。
