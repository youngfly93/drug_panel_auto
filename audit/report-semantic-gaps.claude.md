---
module: report-semantic-gaps
agent: claude
identity_kind: git_commit
identity_value: b7fa69a921799ee568afd743b56b6e6860ef8101
identity_value_short: b7fa69a
auditor: Claude (Fable 5) · AI 独立审核 · 与 drafter/codex 相互独立
audit_date: 2026-07-22
verdict_scope: AI 独立审核 —— 工程/证据层裁决；"CONFIRMED" 仅指该 claim 措辞成立，非医学放行；医学终审权在报告组
status: 工程候选 PASS；医学/UAT BLOCKED；promotion 未就绪；生产未部署
---

# 审核报告 · report-semantic-gaps（CRC358 语义缺口 / 药物一致性 · 独立一审）

> 冻结对象：`git_commit b7fa69a921799ee568afd743b56b6e6860ef8101`（工作树干净，见 report-semantic-gaps-01）。
> 证据来源：`.work/uat_evidence/` 下四个脱敏 JSON + 冻结源码。未读取任何 agent 运行态/会话/缓存/患者文件。
> 沙箱说明：本机沙箱拦截了 `pytest`/`python3` 执行，回归测试为**静态核验**（读代码+读证据），未实跑；已在下文如实标注。

## 0. 已锁口径（审核合同）
1. 四级分开裁决：**工程候选** ≠ **医学/UAT** ≠ **promotion** ≠ **生产部署**；任一上层不因下层工程 PASS 而自动成立。
2. 证据分层：exact-SHA 执行证据（语义扫描、发布门禁 replay）与"数据可得性"证据（备份历史、真实清单）不可混用；后者用于"有没有料"，不能当 exact-SHA 执行结论。
3. AI 不是医学放行人；`clinical_release_readiness=BLOCKED`、UAT 未过阈值时，不得表述为"医学审完"。
4. 已知阻断必须保持可见，不因工程门禁 PASS 而隐去。

## 1. 主发现表（stable ID）

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| report-semantic-gaps-01 | P3 | 冻结身份精确：HEAD 精确等于目标 SHA b7fa69a，工作树对业务代码为冻结干净态（无改动/暂存/未跟踪业务文件）。 | `git rev-parse HEAD`=b7fa69a…60ef8101；`git diff --stat HEAD`、`git diff --cached --stat`、`git ls-files --others --exclude-standard` 均空。据此 HEAD 精确等于目标 SHA，无已跟踪文件改动、无暂存、无未跟踪非忽略业务文件；本审核仅新增 `audit/report-semantic-gaps.claude.md`，属允许的唯一写入。 | CONFIRMED |
| report-semantic-gaps-02 | P3 | 该提交未引入任何 PII/患者数据/二进制产物/密钥/环境文件。 | `git show --stat b7fa69a`：仅 `backend/tests/test_report_semantic_gaps.py`(+40) 与 `reportgen/core/_field_mapper_targeted_drugs.py`(+13/-1)。该提交只引入测试与字段映射代码，未引入任何患者 Excel/DOCX/截图/签名/环境文件/storage/凭据。树内既有的 `*.xlsx`(KB 工作簿) 与 `*_golden_template_*.docx`(模板) 均为脱敏/公开资产、非本提交引入、非患者数据；未跟踪任何 `.env/.key/.pem/storage/`。 | CONFIRMED |
| report-semantic-gaps-03 | P2 | 拼接缺分隔的证据级药物条目边界缺陷已在共享摄入点根治，并有代表性真实行回归。 | `reportgen/core/_field_mapper_targeted_drugs.py:24-51`（`_normalize_drug_evidence_label`）+ `:144-146`（`_load_targeted_drug_db` 对 benefit/caution 列 `.map()`）；测试 `backend/tests/test_report_semantic_gaps.py:2462-2500`。缺陷在**共享摄入点**（工作簿加载时对两列一次性归一化）被根治：正则 `([（(]\s*[A-Da-d]\s*[)）])(?=[^\s、，,；;\r\n])`→`\1\n`，在证据级闭合标记后遇非分隔符补换行，尾部 `（C）` 与已洁净标签不动（幂等）。回归覆盖代表性真实行 ARID1A `c.5965C>T p.R1989*`、FBXW7 `c.979G>T p.E327*`（二者均在本次 10 例扫描的 legacy_uncontracted 中出现），并含负例 `A+B（C）` 不变。注：为**代表性**覆盖（2 条真实行+3 断言），非穷举；执行被沙箱拦截，裁决基于静态核验正则语义与测试断言一致。此修复解决的是"条目被并成一条"（计数虚高），与 report-semantic-gaps-07 的"漏条目"（计数缺失）是不同缺陷。 | CONFIRMED |
| report-semantic-gaps-04 | P1 | 已证明全部十例药物一致。 | `public_crc358_semantic_scan_b7fa69a.json` cases UAT358-03/06/08 `drug_consistency_status=FAIL`（43→42、24→23、38→37），各 `drug_missing` 一条真实药物条目。10 例中 3 例药物一致性 FAIL，未对全部十例证明一致性；缺失项为患者可见药物（KRAS G12V→依维莫司(C) caution；APC R876*→REC-4881(C) benefit；APC Q1328*→REC-4881(C) benefit）。故"证明全部十例药物一致"不成立。 | REFUTED |
| report-semantic-gaps-05 | P1 | 发布 UAT 阈值已达（≥10 例、≥90% 通过）。 | 同扫描 `case_count=10, semantic_passes=2`（仅 UAT358-05/09 PASS）；`knowledge_release_gate…json` `uat.status=pending, reviewed_reports=0, required_pass_rate_percent=90, minimum_reviewed_reports=10`。例数达 10，但 exact-SHA 语义 PASS 率仅 20%（即便只看药物一致性也是 7/10=70%），远低于 90% 阈值；且该语义扫描是工程语义检查，不等于报告组真实报告 UAT（门禁记 UAT 仍 pending、reviewed=0）。阈值未达。 | REFUTED |
| report-semantic-gaps-06 | P2 | 这十例用到的 legacy Part3 变异全部被已审精确契约治理。 | 同扫描 `unique_legacy_uncontracted_count=22`；8/10 例 `contract_coverage_status=MIGRATION_PENDING`，`contract_governed_variant_count < contract_expected_variant_count`（如 01:0/6、06:0/4、08:0/5、10:0/1）。仍有 22 个唯一未契约化变异、多例 governed=0；契约迁移进行中（MIGRATION_PENDING），claim 不成立。 | REFUTED |
| report-semantic-gaps-07 | P1 | 无真实药物漏项残留。 | 同扫描 UAT358-03/06/08 `drug_missing` 各一条（variant_key=null 的药物级漏项）。十例中 3 例仍存在真实的 Part2/Part3 药物漏项（工具自身判为 drug_consistency FAIL / drug_missing）；"无真实漏项残留"被证伪。 | REFUTED |
| report-semantic-gaps-08 | P1 | CRC301 有 ≥10 份真实历史输入且通过 CRC301 病例 UAT。 | `public_backup_panel_history.json`（36 快照）`crc301_seen=false, max_crc301_uploads=0, max_crc301_tasks=0`；无任何 CRC301 语义/UAT 证据。备份历史（candidate_revision=f032ff3，为数据可得性证据）显示 CRC301 真实历史输入为 0，达不到"≥10 份"，更无 CRC301 病例 UAT 通过；双条件均不成立。（按要求：此处 revision 与 b7fa69a 不一致属证据范围差异、非篡改；仅当"可得性"证据用。） | REFUTED |
| report-semantic-gaps-09 | P3 | 二审 receipt + 发布门禁存在且 fail-closed，工程状态与临床就绪明确分离。 | `knowledge_release_gate_b7fa69a.json`（exact-SHA 本地 replay）；代码 `reportgen/knowledge/release_gate.py:167-226`(`_secondary_review_receipt`)、`:229-277`(`_clinical_readiness`)。二审 receipt 存在且 hash 钉死：逐工件与 bundle 重算 sha256，`expected==actual`（37 工件全 match）；任一内容漂移→sha 不符→receipt `FAIL`（fail-closed）。发布门禁存在且 fail-closed：二审未完成/receipt 非 PASS/有 pending 行/reviewed<10/rate<90 任一命中即 `BLOCKED`。工程状态与临床就绪明确分离：顶层 `status=PASS`、`panels_passed=2`，而两 panel `clinical_release_readiness.status=BLOCKED`（blocking_reasons: insufficient_uat_reports + uat_pass_rate_below_threshold_or_unknown）。 | CONFIRMED |
| report-semantic-gaps-10 | P2 | 同-SHA 的 GitHub required check 单独即可证明 promotion 就绪。 | HANDOFF「四、待办」1-3；`clinical_release_registry.policy.description`（二审通过不能替代病例 UAT）；本表 04/05/07/11/12。同-SHA 的 GitHub required check 仅覆盖工程门禁，无法独立证明医学 UAT、Linux 全量视觉复核、生产验收；以其"单独"即判 promotion 就绪，不成立。 | REFUTED |
| report-semantic-gaps-11 | P2 | 本 SHA(b7fa69a) 已完成全量 Word 渲染 + 人工视觉复核。 | 无 exact-SHA(b7fa69a) 全量 Word 渲染+人工视觉复核 receipt；`knowledge_release_gate…` `uat.reviewed_reports=0`；HANDOFF §0.2 的 99 页隔离候选属**另一 SHA**、非 b7fa69a。语义扫描运行于 iyun129 隔离 Linux，但只是语义检查、非全量视觉渲染+人工复核；此 SHA 无"渲染+人工视觉复核完成"证据，且 UAT reviewed=0，故"已完成"被证伪。 | REFUTED |
| report-semantic-gaps-12 | P1 | 生产已切到本 SHA 并完成现网验收。 | 无 b7fa69a 部署证据；HANDOFF 明确"候选尚未提交、未部署，生产仍须按实时四项证据确认"；审核禁连生产。无任何证据表明生产已切到本 SHA，更无 post-deploy 现网验收；候选处于冻结、未部署态，claim 不成立。 | REFUTED |
| report-semantic-gaps-13 | P1 | 候选现在可以 promote。 | 综合 04/05/06/07/08/11/12 + 门禁 `clinical_release_readiness=BLOCKED`。医学/UAT 阻断（语义 PASS 20%、3 例真实漏药、22 个未契约化变异、CRC301 0 例、UAT reviewed=0），promotion/生产前置未满足；候选**现在不可 promote**。 | REFUTED |

## 2. 关键阻断（保持可见）
- **B-01（P1，医学）**：UAT358-03/06/08 三例 exact-SHA 药物一致性 FAIL，各漏一条 Part3 药物条目（KRAS G12V→依维莫司(C)；APC R876*/Q1328*→REC-4881(C)）。这是与本提交所修"拼接边界"不同的**漏条目**缺陷，需报告组/drafter 复核根因（是否筛选/契约缺口所致）。
- **B-02（P1，UAT）**：exact-SHA 语义 PASS 率 20%（2/10），远低于 90%；报告组真实报告 UAT reviewed=0。发布 UAT 阈值未达。
- **B-03（P1，覆盖）**：CRC301 真实历史输入 = 0，无法起 CRC301 病例 UAT。
- **B-04（P2，治理）**：22 个 legacy 未契约化变异、8/10 例 MIGRATION_PENDING；契约迁移未完。
- 说明：以上均为已知阻断，工程门禁 `status=PASS` 不覆盖之——门禁自身已把它们记为 `clinical_release_readiness=BLOCKED`。

## 3. 正面确认（工程层）
- 冻结身份精确、工作树干净（report-semantic-gaps-01）。
- 提交无 PII/二进制/密钥引入（report-semantic-gaps-02）。
- 拼接药物条目边界缺陷在共享摄入点根治，含代表性真实行回归（report-semantic-gaps-03，静态核验）。
- 二审 receipt + 发布门禁存在且 fail-closed，工程/临床状态分离清晰（report-semantic-gaps-09）。

## 3.5 方法保真表（method-fidelity · 共享审核合同要求）

> 裁决方法本身是否忠实：只用 FAITHFUL / HONEST_BOUNDARY / UNDISCLOSED_DOWNGRADE / FALSE_REASON。
> 本表仅评估"我审核所用方法与被强制方法是否一致"，不改动上文 13 条发现的任何裁决/身份/结论。沙箱说明（见 §4 caveats）继续有效：`pytest`/`python3` 部分执行被本机沙箱拦截，我未做任何远端 blob 校验、未连生产。

| id | mandated 方法 | 实际 method_status | verdict | evidence |
|---|---|---|---|---|
| report-semantic-gaps-M01 | candidate、隔离 Linux 扫描、审核三者须绑定同一 Git 身份。 | 我用本地 `git rev-parse HEAD` 确认 checkout 精确等于 b7fa69a（report-semantic-gaps-01），exact-SHA 执行证据文件名/内容为 `…_b7fa69a`（语义扫描、发布门禁）；但"数据可得性"证据（`public_real_crc358_inventory.json`、`public_backup_panel_history.json`）标注 `candidate_revision=f032ff3`，与冻结审核 SHA 不同。我**未执行任何远端 blob / 远端 candidate 二进制比对**，只在本地 checkout 与 exact-SHA 证据之间绑定身份，并已把 f032ff3 明确降级为"仅可得性用"（report-semantic-gaps-08）。 | HONEST_BOUNDARY | `git rev-parse HEAD`=b7fa69a…60ef8101；`public_crc358_semantic_scan_b7fa69a.json`、`knowledge_release_gate_b7fa69a.json`（exact-SHA）；`public_real_crc358_inventory.json`/`public_backup_panel_history.json` `candidate_revision=f032ff3`（可得性，非本 SHA 执行）。未做远端 blob 校验。 |
| report-semantic-gaps-M02 | 真实病例 UAT 公开证据须保持脱敏。 | 直接读 `privacy` 字段与可见键：清单 `privacy="No patient name, sample identifier, original filename, or source path is included."`，可见键仅 `case_id`+`sha256`+`sheet_count`+`required_fields_complete_in_source`；备份历史 `privacy="Only aggregate panel counts are included."`。无姓名/样本号/原文件名/路径/患者可识别字段泄露；与 report-semantic-gaps-02"提交无 PII"一致。此项可从字段与可见键直接核验，方法按强制执行。 | FAITHFUL | `public_real_crc358_inventory.json` `privacy` 字段 + 可见键（仅 case_id/sha256/sheet_count）；`public_backup_panel_history.json` `privacy=aggregate counts only`。 |
| report-semantic-gaps-M03 | CRC301 不可得须独立取证，且不得用合成 fixture 顶替。 | CRC301 不可得由 36 快照备份历史独立佐证（`crc301_seen=false, max_crc301_uploads=0, max_crc301_tasks=0`），无 CRC301 语义/UAT 证据，且我**未以任何合成 fixture 顶替**真实 CRC301 输入（report-semantic-gaps-08 直接判 REFUTED）。边界：该 36-backup 为 candidate_revision=f032ff3 的"可得性"证据；且**当前上传目录的实时 rescan 不在我的证据范围内**（我只读 `.work/uat_evidence/` 快照，未扫 storage/当前上传）。故为诚实边界而非 FAITHFUL。 | HONEST_BOUNDARY | `public_backup_panel_history.json`（36 快照，`crc301_seen=false`）；无 CRC301 UAT；未substitute合成 fixture；current-upload rescan 不在本审证据内。 |
| report-semantic-gaps-M04 | 生产结论须有 exact-SHA Linux 全量渲染 + post-deploy 现网证据。 | 我**没有** b7fa69a 的 exact-SHA Linux 全量 Word 渲染 receipt，也**没有** post-deploy 现网验收证据（`uat.reviewed_reports=0`；HANDOFF §0.2 的 99 页隔离候选属另一 SHA）。审核禁连生产，我未连生产、未实测现网。因此我把生产/promotion 结论严格界定为 NOT DEPLOYED / NOT READY（report-semantic-gaps-11/-12/-13 REFUTED），基于缺证边界作否定，未越界断言"已渲染/已验收"。 | HONEST_BOUNDARY | 无 b7fa69a 全量渲染 receipt、无 post-deploy 现网证据；`knowledge_release_gate_b7fa69a.json` `uat.reviewed_reports=0`；report-semantic-gaps-11/-12/-13。审核禁连生产。 |

## 4. 分级裁决（结论）
- **工程候选（Engineering）：PASS。** 冻结干净、边界修复根治+回归、门禁工程状态 PASS、二审 receipt hash 有效。
- **医学 / UAT：BLOCKED（FAIL）。** exact-SHA 语义 PASS 20%、3 例真实漏药（B-01）、22 个未契约化变异、CRC301 0 例、报告组 UAT reviewed=0。不得表述为医学审完。
- **Promotion：NOT READY（REFUTED，report-semantic-gaps-13）。** 医学/UAT 前置未满足；同-SHA CI 单独不足（report-semantic-gaps-10）；无 exact-SHA 全量渲染+人工视觉复核（report-semantic-gaps-11）。
- **生产部署（Production）：NOT DEPLOYED（REFUTED，report-semantic-gaps-12）。** 无本 SHA 部署与现网验收证据；切换须以 `current_release`/完整 `REVISION`/进程 cwd/健康检查四项实时证据为准。

### 沙箱说明（caveats）
- 本机沙箱拦截 `pytest`/`python3` 执行，report-semantic-gaps-03 的回归为**静态核验**（读代码+读证据），未实跑。
- 审核禁连生产，report-semantic-gaps-11/-12 的生产/渲染结论基于缺证（无 exact-SHA receipt），非现网实测。
- report-semantic-gaps-08 使用的 `public_backup_panel_history.json` 属 candidate_revision=f032ff3 的"数据可得性"证据、非 b7fa69a exact-SHA 执行证据，仅当可得性用。
- 方法保真表（§3.5）中 report-semantic-gaps-M01 未做远端 blob 校验、report-semantic-gaps-M03 的 current-upload 实时 rescan 不在本审证据范围内、report-semantic-gaps-M04 未连生产/无渲染 receipt——均已如实标注为 HONEST_BOUNDARY。

> 本报告为 AI 独立一审；医学终审（通过/不通过）与放行权在报告组（人）。修复须基于同一冻结 SHA，改后回审核方复核 diff。
