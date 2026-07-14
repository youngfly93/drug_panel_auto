---
module: knowledge-governance
agent: claude
audited_commit: 4545e0b331f14c2a3af0f4bb0ca07fc8c52fc848
audited_commit_short: 4545e0b
prior_sha_amended_from: 6b45a77
tree_identical_to_prior: true   # amend 仅改 commit message,树内容/KB_HASH 不变
kb_hash: 292c386db6a0904e
auditor: Claude (Opus 4.8) · AI 一审 · 独立于 drafter(codex)
audit_date: 2026-07-14
status: 预审已修订（PII/日期/格式/冻结候选复验已补）；待报告组 FANCA 决策 + codex 实施
verdict_scope: AI 一审 —— "通过" 指措辞/工程层无越权,非医学放行
---

# 审核报告 · 知识治理 + 系统发布（一审 / 预审 · rev.2）

> rev.2 修订:采纳 codex 反审计——脱敏本报告自身 PII、更正审核日期(07-13→07-14)、
> 加 YAML frontmatter 与 file:line 指针、在**冻结候选**上重跑工程门禁(此前 E2E 跑在旧生产
> 7c04472,非冻结候选)、更正 BPI-03/QA-409 描述、补部署可追溯 GATE-02、澄清条目计数、
> BPI-KB-01 改为"交付层门禁"而非直接下线。

---

## 0. 已锁口径（审核合同）

1. 两轨各自独立通过:**系统发布**(能否稳定可追溯产报告)+ **知识/单份**(结果与医学解释能否交付)。
2. 证据分层:64 运行行做治理级审核;仅高危行做文献级核验。
3. AI(codex/Claude)都不是医学放行人;`provisional` 条目在报告组签字前不得视为已过医学审。
4. 审核基于冻结 SHA `4545e0b`;drafter 修复须基于同一 SHA,改完回审核方复核 diff(闸②)。

---

## 1. 总体结论

> **工程发布:冻结候选已复验通过(见 §2)。医学发布:BLOCKED —— 二审 0%、UAT 0。**
> 知识措辞:60 gene 行保守合格;4 FANCA 药物行证据真实、措辞保守,但已 runtime-live 且先于报告组二审(BPI-KB-01),须报告组决定显示/交付策略。
> **本报告为 AI 一审;终审(通过/不通过)权在报告组。**

---

## 2. 系统发布审核（工程轨）

### 2.1 冻结候选复验（rev.2 新增 —— 直接在 `4545e0b` 树上跑，本机 LibreOffice）

| panel | ok | QA | 视觉渲染 | 页数 | 空白页 | 失败检查 | 产物 SHA256 |
|---|---|---|---|---|---|---|---|
| crc_358_msi | ✅ | PASS | PASS | 57 | 0 | 无 | `afa300d3…dbe5d6f9` |
| crc_301_msi | ✅ | PASS | PASS | 63 | 0 | 无 | `a37a6a5a…d65b20c` |

- 产物路径:`.work/freeze_revalidation_6b45a77/{crc_358_msi,crc_301_msi}/output/golden_*.docx`(+ `.qa.json`),汇总 `.work/freeze_revalidation_6b45a77/revalidation_summary.json`。
- 复现:`scripts`(scratch) `revalidate_freeze.py`,`PYTHONPATH=. .venv/bin/python … `,cwd=repo=候选树。
- **注意**:冻结候选页数(57/63)≠ 旧生产 7c04472(67/74)——含 33 个知识治理改动使渲染内容变化,证实"必须在候选本身复验"(codex P1-3 成立,已闭合)。

### 2.2 早前生产端到端(7c04472,供对照,非冻结候选)

在运行的生产 release 上 BPI-001/002/004~007 实测通过(MSI 不静默、FANCA 限定命中、无空白页)。**此为旧生产版结果,仅作参照;冻结候选以 §2.1 为准。**

### 2.3 部署可追溯缺陷 GATE-02（rev.2 新增,此前漏报）

生产存在**三个互相矛盾的版本标识**:

| 标识 | 值 | 可信 |
|---|---|---|
| `:18082` 进程 `/proc/<pid>/cwd` | **7c04472** | ✅ 权威(实际运行) |
| `runtime/current_release` | 7c04472 | ✅ 一致 |
| `runtime/REVISION` 文件 | **80fbecb** | ❌ 陈旧,与实际不符 |
| 旧 `reportgen-web-prod` git HEAD | **16a24b8** | ❌ 陈旧(遗留目录) |

→ 读 `runtime/REVISION`(80fbecb)或旧 prod git(16a24b8)会被误导。建议:统一以 `current_release`+进程 cwd 为准,修正/删除陈旧 REVISION 标识。

---

## 3. 知识逐条审核（医学轨 · 治理级）

条目计数(rev.2 更正 codex 指出的口径):队列 **64 运行行** = 60 gene + 4 FANCA;但**独立知识**更少 —— gene 仅 **48 个独立基因解释**(12 个跨 CRC301/358 复用),FANCA 为 1 基因×2 panel×2 kind。逐行裁决见 `audit/knowledge_master_audit.md`,14 字段机读工作表见 `audit/knowledge_review_worksheet.tsv`(已含 source_file:row / 审核状态 / 风险级 / 癌种 / 人工裁决+理由+审核人+时间+处置)。

### 3.1 gene 背景解释（60 行,48 独立基因）——治理级通过

- 全部 `functional_background_only`(ZNF703 `exploratory_crc_expression_evidence`),scope=背景、"no automatic drug claim"。
- **逐行读完 60 行**(rev.1 曾对未含"越权词"的约 37 行批量放行,rev.2 已逐行补读并留证,无空证据):每行均带限定性否定语,无一行对任意变异下治疗/PGx 结论。高风险 PGx 均设护栏:
  - `panels/crc_301_msi/rules/reviewed_part3_knowledge.yaml` DPYD:任意体细胞变异不能直接套用
  - 同上 UGT1A1:单个未分相/体细胞变异不能直接判定风险
  - 同上 CYP2D6:单个未分相变异不能直接判定代谢型
  - 同上 XRCC3:不能由任意错义变异直接推导 PARP 抑制剂获益
- **裁决:治理级通过**(=措辞无越权,非医学放行)。建议报告组抽检 3~5 行后批量确认。

### 3.2 FANCA 药物行（4 行）——文献级已核,需医学决定 + 交付门禁

- 限定:`applicability=loss_of_function` + `variant_level=Ⅱ类`;LoF 判定 = p 含 `fs`/`*` 或剪接 c。错义/非 LoF 不命中(端到端已验)。
- 证据(据 PubMed):`PMID:26510020` = Mateo et al., *DNA-Repair Defects and Olaparib in Metastatic Prostate Cancer*, N Engl J Med 2015([DOI](https://doi.org/10.1056/NEJMoa1506859))。摘要与 yaml 逐项吻合:50 入组、49 可评估中 16 例 DDR 缺陷(BRCA1/2、ATM、**范可尼贫血基因**、CHEK2)、14 例应答。FANCA 系**聚合 DDR 标志之一**,非单基因单独效力;yaml 已诚实标"D 级跨癌种、非 CRC 独立疗效"。
- **裁决:证据真实、措辞保守、标注诚实。核心医学判断成立。**
- 位置:`panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml`(drug_sections FANCA)、`panels/crc_358_msi/rules/drugs.yaml`(targeted_drug_rules.reviewed_variant_overrides[0])。

---

## 4. 缺陷清单（基于冻结 SHA `4545e0b`,交 codex 实施）

| ID | 级别 | 位置 | 问题 | 建议 |
|---|---|---|---|---|
| **BPI-KB-01** | P1（阻断医学交付） | FANCA reviewed + drugs.yaml；交付门禁 `backend/app/api/report.py` | `provisional_runtime` 却 `runtime_eligible=true`,off-label 结论已 runtime-live 且先于报告组二审 | **策略已定 = B（可预览·禁交付）**（用户 2026-07-14 决定,codex/Claude 同倾向）。实施:保留 FANCA 在生成/预览/UAT 显示;**扩展现有交付/下载门禁**(即 QA-FAIL 409 那套 `override_gate` 机制)——当报告含"高风险 provisional 且未二审"的知识条目(如 FANCA runtime-live)时,正式下载/交付返回拦截,需报告组二审通过或显式留痕 `override`(记审核人/原因/时间)才放行。生成/预览接口不拦。**不改 `runtime_eligible=false`。** |
| GATE-02 | P1 | runtime/REVISION、旧 prod 目录 | 三个版本标识矛盾(7c04472/16a24b8/80fbecb) | 统一以 current_release+进程 cwd 为准,修正/删陈旧 REVISION;部署脚本写正确 REVISION |
| BPI-KB-02 | P2 | `backend/tests/test_report_regression.py`(裸样本号,值不在本报告复述,定位见该文件用到 `sample_id_from_filename` 处 4 行 + 另 1 行) | 测试用裸样本号疑似真实、已在 git 历史 | 报告组/codex 确认合成与否;若真实→替换为 `LZ000001` 式并评估历史清理 |
| BPI-03 | P2 | 长药物列表 | **更正描述**:逻辑级全量展示测试已存在(`backend/tests/test_report_regression.py:1407`,含 7 药);缺的是**长列表完整 Word 视觉 UAT** | 补 >5 条药物变异的 Word 视觉 UAT |
| QA-409 | P2 | QA-FAIL 拦截 | **更正描述**:409 已有自动测试(`backend/tests/test_stateless_report_endpoints.py:831`);缺的是**生产环境 UAT** | 生产环境跑一次 FAIL 例确认 409 + override 留痕 |
| GATE-01 | P2 | `release_gate` 摘要 | 临床就绪(二审/UAT)置于 non-blocking,易读成"整体 PASS" | 报告级摘要明确"工程 PASS / 医学 BLOCKED",避免"覆盖 100%"被当"医学审完" |

> 修复口径:只按本清单改;改完不自宣通过,回审核方对 diff 复审(闸②)。

---

## 5. rev.2 已自纠（codex 反审计项）

| codex 指出 | 处置 |
|---|---|
| P0 本报告泄露姓名/样本号 | 已脱敏:不复述姓名/样本号,改按 file:line 引用 |
| P0 冻结 commit message 含样本号 | 已 `git commit --amend`(未推送),`6b45a77`→`4545e0b`,message PII=0 |
| P1 审计对象与实测版本不一致 | 已在冻结候选 `4545e0b` 树上重跑 golden+视觉QA(§2.1),旧生产结果降为参照(§2.2) |
| P1 三版本标识 | 已核实并记为 GATE-02(§2.3) |
| P2 日期 07-13 错 | 全部改为 07-14(实际 commit/生成日) |
| P2 audit/ 有 ._ 致对账失败 | 已删 ._ 并 `.gitignore` `._*`;`audit_reconcile.py` 障碍清除 |
| P2 无 frontmatter/证据指针 | 已加 YAML frontmatter + file:line 指针 |
| 64 条计数不精确 | 已澄清"64 运行行 = 48 独立基因解释 + FANCA 复用"(§3) |
| CYP2E1 等空证据却判通过 | 已补全所有行"已核限定语",无空证据 |
| TSV 是关键词扫描非完整工作表 | 已用 14 字段导出为底表 + 5 列人工裁决重建 `knowledge_review_worksheet.tsv` |
| BPI-03/QA-409 描述过头 | 已更正:代码测试已存在,缺的是视觉/生产 UAT |

---

## 6. 必须由报告组（人）决定 / 签发

1. **BPI-KB-01 —— 已决定 = (B)**（用户 2026-07-14）:FANCA 可预览/可生成,但正式交付/下载被门禁拦,需报告组二审或留痕放行。→ 已转为可实施缺陷条目(§4 BPI-KB-01),交 codex 实施;报告组仍需对 FANCA 措辞本身做医学二审签字。
2. 60 行 gene 措辞口径确认(抽检 + 批量)。
3. UAT:CRC301/358 各 ≥10 份脱敏真实 + 边界合成(FANCA 正反例、MSS/MSI-H、0/1/多药、Ⅰ/Ⅱ/Ⅲ类、长报告、交叉串病例),出版本级 通过/有条件/不通过。
4. 底线:P0=0、bug_pic1 缺陷全复测、总通过≥90%,任一串病例/必检错误/漏关键变异/药物方向错→整版不通过;人工放行留痕。
