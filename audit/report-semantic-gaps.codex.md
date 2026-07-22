---
module: report-semantic-gaps
agent: codex
identity_kind: git_commit
identity_value: b7fa69a921799ee568afd743b56b6e6860ef8101
---

# CRC 报告语义与发布就绪审计（Codex）

审计对象是冻结提交 `b7fa69a921799ee568afd743b56b6e6860ef8101`。病例输入只在
iyun129 隔离 UAT 目录中使用；公开凭据仅包含脱敏别名、哈希、变异 selector 与聚合状态，
未把患者姓名、样本号、Excel、Word、截图、签名或环境配置写入 Git。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| report-semantic-gaps-01 | P3 | 当前业务修改已冻结为精确提交，审计对象不再是变化中的工作树。 | `git rev-parse HEAD`=`b7fa69a…8101`；业务提交 `b7fa69a` 已推送至 `origin/codex/report-semantic-gaps-20260720`；工作树仅有本模块两份审计文件，均不属于被审业务提交。 | CONFIRMED |
| report-semantic-gaps-02 | P3 | 本提交未引入患者资料、报告成品、截图、签名、环境文件、storage 或凭据。 | `git show --stat b7fa69a` 仅修改 `reportgen/core/_field_mapper_targeted_drugs.py` 与 `backend/tests/test_report_semantic_gaps.py`；敏感后缀/路径扫描为 0。 | CONFIRMED |
| report-semantic-gaps-03 | P2 | 证据等级后两个药物黏连的问题已在共享摄入层根修，并覆盖真实数据库行。 | `_normalize_drug_evidence_label()` 在 benefit/caution 两列加载时统一补齐边界；ARID1A R1989*、FBXW7 E327* 实际库行与幂等反例均有回归。相关测试 `73 passed`；iyun129 精确 SHA 十例复扫后，f032 中 6 个“黏连型 missing”全部消失，10/10 的此类缺陷为 0。远端代码 SHA256 与 Git blob 一致：mapper `437593c9…7a82`、测试 `f2ba9c30…6084`。 | CONFIRMED |
| report-semantic-gaps-04 | P1 | 精确 SHA 十例 CRC358 证据证明所有病例的 Part2/Part3 药物一致。 | `public_crc358_semantic_scan_b7fa69a.json` 中 UAT358-03/06/08 仍为 `drug_consistency_status=FAIL`；分别缺 KRAS G12V/依维莫司（C）慎用、APC R876*/REC-4881（C）获益、APC Q1328*/REC-4881（C）获益。 | REFUTED |
| report-semantic-gaps-05 | P1 | CRC358 已满足不少于 10 例且通过率不少于 90% 的病例级 UAT。 | 精确 SHA 扫描虽有 10 例，但完整语义仅 2/10 PASS（20%），药物一致性也仅 7/10；知识发布门禁仍记录 `reviewed_reports=0`，语义扫描不能冒充报告组逐份 Word UAT。 | REFUTED |
| report-semantic-gaps-06 | P2 | 十例中使用的历史 Part3 候选均已进入审核过的精确运行契约。 | 同一凭据有 `unique_legacy_uncontracted_count=22`，8/10 病例为 `MIGRATION_PENDING`；22 个 selector 仍只来自历史候选库，不能从基因/等级泛化为医学批准规则。 | REFUTED |
| report-semantic-gaps-07 | P1 | 十例中不再存在真实的 Part2/Part3 药物漏项。 | UAT358-03/06/08 的三条 `drug_missing` 是独立于“药物黏连”的真实规则/契约缺口；修复黏连后仍稳定复现。 | REFUTED |
| report-semantic-gaps-08 | P1 | 已有至少 10 份真实 CRC301 输入，并完成 CRC301 病例级 UAT。 | 36 份生产备份快照均为 `crc301_seen=false`、CRC301 upload/task 最大值 0；当前上传目录 109 个 Excel 去重为 28 份，28/28 均识别为 CRC358、CRC301=0、解析错误=0；本地候选扫描也只有合成 CRC301 fixture。 | REFUTED |
| report-semantic-gaps-09 | P3 | 报告组二审回执与知识发布门禁已结构化落库，并会对内容漂移失败关闭。 | 精确 SHA 重放 `knowledge_release_gate_b7fa69a.json`：工程 `PASS`、issues=0；回执 bundle 预期/实算均为 `739da79c…2917`，受审工件逐项 hash 匹配；两个 Panel 临床状态仍因 UAT 为 `BLOCKED`。凭据 SHA256=`2403b6e5…e4`。 | CONFIRMED |
| report-semantic-gaps-10 | P2 | 同 SHA GitHub required check 单独即可证明可发布。 | GitHub run `29890515118` 的工程检查不覆盖报告组病例 UAT、精确 SHA 全量 Word 人工视觉复核和部署后现网验收；即使全部成功也不能替代 04–08、11–12。 | REFUTED |
| report-semantic-gaps-11 | P2 | `b7fa69a` 已在 iyun129 完成全量 Word 渲染和人工视觉复核。 | 本 SHA 只完成隔离 Linux 语义扫描；此前两份完整 Linux Word 属父提交 `f032ff3`。当前 iyun129 为 72 核且观测负载持续约 72–81、47 个 `vina` 任务并行，未在高负载窗口追加全量渲染；不存在本 SHA 的人工视觉 UAT receipt。 | REFUTED |
| report-semantic-gaps-12 | P1 | 生产已部署到本 SHA，并完成部署后活实例验收。 | `scripts/iyun129_release.sh status` 实测生产仍为 `be9b25a0a07f43b01b4c88cedcb51b705baa7381`，进程 cwd 指向同一 release，health=HTTP 200；`b7fa69a` 仅位于 `/reportgen-web-uat/b7fa69a` 隔离目录。 | REFUTED |
| report-semantic-gaps-13 | P1 | 当前候选已经可以 promotion/生产切换。 | 04–08、11–12 均未关闭，且精确知识门禁明确 `clinical_release_readiness=BLOCKED`；不得部署。 | REFUTED |

## 方法保真与限制核实

| id | mandated 方法 | 实际 method_status | verdict | evidence |
|---|---|---|---|---|
| report-semantic-gaps-M01 | 候选、Linux 扫描和审计必须锁同一 Git 身份 | `b7fa69a…8101` 的 Git blob 与 iyun129 隔离目录两份变更文件 hash 一致；语义凭据也记录同一完整 SHA | FAITHFUL | 隔离目录 `REVISION`；mapper/test 两组本地与远端 SHA256 |
| report-semantic-gaps-M02 | 真实病例 UAT 不得泄露 PII | 原始 Excel 仅留在受限远端目录；运行时注入 `UAT358-NN` 和脱敏姓名；公开 JSON 只含 hash、selector 和聚合状态 | FAITHFUL | `public_crc358_semantic_scan_b7fa69a.json:privacy` |
| report-semantic-gaps-M03 | 缺 CRC301 输入必须独立核实，不得用合成件冒充 | 已检查本地候选、36 份备份数据库及当前全部上传 Excel；三条来源均无真实 CRC301 | HONEST_BOUNDARY | `public_backup_panel_history.json`；当前上传目录去重扫描结果 |
| report-semantic-gaps-M04 | 生产结论必须基于 iyun129 同款 Linux 与部署后现网 | 已完成隔离 Linux 语义复测；因真实 UAT 阻断且共享服务器高负载，没有执行全量渲染或生产切换，未用 macOS/父 SHA 证据冒充 | HONEST_BOUNDARY | `public_crc358_semantic_scan_b7fa69a.json`；负载与 production status 实测 |

## 精确凭据

- 冻结提交：`b7fa69a921799ee568afd743b56b6e6860ef8101`，已推送。
- 相关定向回归：`73 passed`；Ruff 与 `git diff --check` 均 PASS。
- GitHub required check：run `29890515118`、head SHA `b7fa69a…8101`、结论
  `success`；后端回归、历史金标、前端、完整 QA Gate 与产物上传全部通过。
- iyun129 隔离语义凭据 SHA256：`73eb9a5cc6a74ce8e9558c85312c3e940647b441329aba8de954a6dd303da5ed`。
- 备份 Panel 历史凭据 SHA256：`65c9ce37927163196a5d57f27fa3d0ef2f804877cee3c3799674ab7c094799fa`。
- 真实 CRC358 输入清单凭据 SHA256：`32422b4472b330bc74951d95b4e453e5d63bcca041c400ae42a90bea8aad712d`。
- 精确知识门禁凭据 SHA256：`2403b6e57fff446ec240a6d125bb7671397e070025943b5cb9612b02cdf287e4`。
- 生产只读状态：`be9b25a…7381`，不是候选 SHA。

## 分层裁决

- 工程候选：**PASS**。冻结、PII 边界、药物黏连根修和知识回执有效。
- 医学/UAT：**BLOCKED**。CRC358 为 2/10，仍有 3 条真实漏项与 22 个未契约 selector；CRC301 无真实输入。
- Promotion：**NOT READY**。同 SHA 双审可以完成，但不能覆盖病例 UAT 和精确 Linux Word 视觉复核。
- 生产：**NOT DEPLOYED**。生产仍为 `be9b25a`，因此不存在本 SHA 的部署后验收。

本审计不把“报告组知识二审完成”扩大解释为“新发现的 22 个历史候选规则已二审”，也不把
语义扫描当作逐份 Word 人工 UAT。在这些条件关闭前，不执行生产切换。
