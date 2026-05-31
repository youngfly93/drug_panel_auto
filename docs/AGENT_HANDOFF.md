# Agent Handoff — 基因组 Panel 报告自动化(2026-05-31 快照)

> 给**接手的 AI agent**。这是一份带时效的工作状态地图。持久事实见用户记忆库
> （`~/.claude/.../memory/MEMORY.md`,每次会话自动加载);本文补充当前在飞的工作 + 坑。

## 0. TL;DR
- 工程侧**没有技术卡点**;实质产出全部堆在**报告组的临床/内容审核闸口**。
- 唯一卡在**用户**手里的决定:**endometrial 怎么让报告组试跑到**(部署/测试环境;用户说过"别部署生产",未解)。
- 当前在飞的大件:**lung_329 C-beta**,在 **PR #14**(branch `feat/lung-329-cbeta`,OPEN/MERGEABLE/BEHIND)。
- **建议接手后:别急着再建。** 瓶颈是审核不是建设;再堆未审核的代码=制造债。

## 1. 项目与环境(先懂这个)
- FastAPI + Vue3 web 平台,包着 `reportgen` Python 包(golden-template + docxtpl + **后处理器链**架构)。
- **运行时用仓库内的 `reportgen/`**,不是 sibling upstream — 改这份(见记忆 runtime-reportgen-copy)。
- 平行仓库 `../基因组panel自动化系统_web_golden_template`(金标模板开发线,手动搬进 `_web`)。
- 生产:`panel.mailuo-report.com.cn` → iyun62(`ssh iyun-server`),git 同步源是 GitHub `youngfly93/drug_panel_auto`。

## 2. ⚠️ 硬约束(违反会出事,先读)
1. **PII**:绝不提交病人数据。语料 `各癌种基因报告近年汇总/` gitignored(本地)。overlay/模板必须**去标识**(无病人变异位点/频率/姓名/样本号)。`config/patient_info.yaml`/`config/signatures.yaml` 是真实 PII(server 上 skip-worktree)。`*.variableize.json` manifest 会把源病人名记进 protected-token 列表 → **删,别提交**。根目录 `*.xlsx`/`*.docx` 已 gitignored。
2. **同事共享这个工作区,且高频 push main**(运维/摘要/批量:`report.py`/`report_summary.py`/`batch.py`/前端 views)。**别碰、别提交他的 WIP**;用显式路径 `git add`,绝不 `git add -A`。
3. **git**:只在用户明确要求时 commit/push;实质工作开 feature 分支;main 保护是人肉纪律(enforce_admins=false)。提交尾加 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。
4. **不写/编医学内容**:lung 叙述是**收割报告组真实肺报告** + **CIViC 权威英文底稿**,最终都要报告组临床签收。
5. 每个 `reportgen` 核心改动**必跑金标基线** `backend/tests/test_style_baseline.py`(crc_358/crc_301,~2min)确认 CRC 零回归。

## 3. 工作流状态

| 工作流 | 状态 | 在哪 | 卡在 |
|---|---|---|---|
| **lung_329 C-beta** | 工程完成 + 内容 first pass(CRC串44→9)| **PR #14** | 报告组临床审 overlay 内容 |
| endometrial_29 B档 | 落地 + 3份试跑Excel + 编辑成本表 | main | 报告组试跑(需部署access)|
| crc_301 | 结构验收 | main | 报告组真实Excel签收 |
| 同事:摘要预览/批量/运维硬化 | 活跃推进 | main(顶 ~`d602f83`)| — |

## 4. lung_329 C-beta 详情(PR #14,9 commit)

**已做(都有测试/基线守护,勿改机制):**
- v1 金标模板 `panels/lung_329_pdl1/templates/lung_329_pdl1_golden_template_v1.docx`:`__PART3_MARKER__` + 变异/药物/3免疫表 `{%tr%}` 循环 + PD-L1 标量(IHC 表单录入)。panel.yaml default→v1、v0 deprecated、status=draft。
- **CIViC 标签归一化**(`_field_mapper_targeted_drugs._normalize_drug_evidence_label`):`（CIViC:Tier I - Level A）`→`（A）`,所有 panel 受益。
- **gene-level Part-3 overlay 机制**(`reportgen/knowledge/gene_knowledge.py`):`reviewed_part3_knowledge.yaml` 的 `gene_sections`(intro/mutation_analysis)+ `drug_sections`(benefit/caution)按**基因级**(无 c_hgvs)覆盖基础 KB。优先级 **变异级 > 基因级 > base KB**。守护单测 `backend/tests/test_gene_level_drug_override.py`(3 passed)。
- panel 级化了 `reviewed_part3_overlay`(`report_generator._resolve_panel_reviewed_part3_overlay` 从 panel.yaml 顶层 `reviewed_part3_overlay` 解析;crc_358/301 声明用 crc_358 的、lung 用自己的)。
- **内容 first pass**:`scripts/harvest_lung_part3_knowledge.py` 收割语料肺报告 15 驱动基因(gene + benefit/caution drug)+ `scripts/download_civic_gene_summaries.py` 下载 CIViC → `civic_gene_reference.md`。效果:报告"结直肠癌"串 **44→9**。
- **Handoff 给报告组**:`docs/lung329_handoff.md`(逐基因覆盖表 + 待办)+ PR #14 评论。

**剩(报告组内容活)**:审 15 基因临床准确性;补 5 个缺 intro(EGFR/BRAF/RET/ERBB2/KIT,用 CIViC);扩驱动基因列表(剩余 CRC 里有 **FBXW7** 等不在 15 列表);核 MSI 共识指南名(合规保留)。

**关键文件**:`docs/lung329_cbeta_assessment.md`(评估)、`docs/lung329_cbeta_status.md`(状态+根因)、`docs/lung329_handoff.md`(报告组清单)。

## 5. 坑 / 教训(别重蹈)
- **TOC vs 正文锚点**:报告/模板里章节标题在**目录**也出现一次。按文本找正文段要用**最后一次出现**(`starts[-1]`),否则会误删 TOC→正文整段(我犯过,删了 430 段)。
- **variableize 工具的 `_variant_key` 要 gene+c_hgvs 都非空**,gene-only 条目被跳过 → 所以加了 `_gene_level_section_overrides`/`_gene_level_drug_overrides`。
- **drug-relation 收割必须 benefit + caution 都收**:caution 段(抗 EGFR 耐药=CRC 逻辑)是早先没去掉的 CRC 源。
- **CRC 味有多源**:base gene KB「基因变异解析」+「用药提示解析」sheet(各 44/200 处结直肠)、reviewed overlay(已 panel 级化)、targeted_drug_db 的 CIViC 标签(已归一化)。
- **gene_sections 的 analysis 别加 CRC 过滤**(会误排有效肺 analysis→回退 base CRC,我犯过 31→38);**drug 段要加 CRC 过滤**。
- **肺语料报告有坏 image rel `../NULL`** → python-docx 崩,用 `zipfile` 读 `word/document.xml`。
- **golden_case 默认签发人**张医生/李医生来自 patient_info.yaml,要在 signatures.yaml 登记否则 QA WARN。
- **prod 重启**:`watchdog.sh` 无 restart 子命令(healthy 时 no-op);必须 kill pid + respawn,且断言 process-start > 文件 mtime(否则在测旧代码)。
- **draft 护栏**:同事的摘要 review-guard 已按 panel `status` 派生(draft 自动红旗);endometrial 模板首页有红色草稿横幅,lung v1 没有(待补)。

## 6. 建议下一步(接手者读)
1. **别急着再建**:全部在等报告组。再堆未审核工作=债。
2. 真正能推的是**人**的事:用户定 endometrial 部署access;报告组消化审核队列。
3. **PR #14 真要合并时**:先 `git merge origin/main`(现 MERGEABLE 但 BEHIND;同事高频推 main,现在合是白做,等真合并前再做)。
4. 用户给具体方向(如"合 PR"/"做 endometrial 部署")才执行;否则待命。

## 7. 记忆库指针(持久,自动加载)
关键记忆:`panel-migration-status`(各 panel + lung 重大修正)、`lung329-onboarding`、`runtime-reportgen-copy`、`prod-deployment-topology`、`prod-restart-procedure`、`architecture-debt-brakes`、`gene-knowledge-db-is-stripped`、`signature-system`、`main_protection_policy`、`crc35-supervision`。
