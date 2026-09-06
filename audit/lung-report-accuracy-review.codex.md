---
module: lung-report-accuracy-review
agent: codex
identity_kind: git_commit
identity_value: da8e62de672ecaa5416d3c2b29e3e9294531f519
audit_date: 2026-09-05
---

# 肺癌 Excel → Word 准确性复核与整改记录

当前冻结审计对象为 `da8e62de672ecaa5416d3c2b29e3e9294531f519`；新增发现使用
13–18，不复用历史条目的 id。当前修复仍为未提交开发工作树，后文的测试通过只说明
开发候选行为，不是冻结提交验收或生产发布证明。

## 2026-09-02 原冻结基线记录（保留，不改判）

本表复核 Claude 在冻结生产基线 `808a289a7cb253745d0247066249fb8982454cbf`
上提出的 12 条发现。结论只描述该冻结基线；整改后的证据单列在后，不回写旧结论。

以下引用保留原 verdict；它们属于 808a289，不作为当前 da8e62d 的发现表重新计数。

> | id | severity | claim | evidence | verdict |
> |---|---|---|---|---|
> | lung-report-accuracy-review-01 | P1 | 肺癌指南药物提示表未按历史 10 行固定结构输出。 | fix_log.md:29 | CONFIRMED |
> | lung-report-accuracy-review-02 | P1 | 既有数据库支持的 C/D 级研究性靶向药未进入病例靶向药表。 | fix_log.md:33 | CONFIRMED |
> | lung-report-accuracy-review-03 | P1 | 化疗正文关闭且 CtDrug 附录未按 1B/2A/2B 过滤。 | fix_log.md:31 | CONFIRMED |
> | lung-report-accuracy-review-04 | P2 | 混合送检样本的 TMB 参考值未跟随实际 TMB 测定样本。 | fix_log.md:35 | CONFIRMED |
> | lung-report-accuracy-review-05 | P2 | 肺癌未检出列表错误复用 CRC 基因集。 | fix_log.md:37 | CONFIRMED |
> | lung-report-accuracy-review-06 | P2 | 免疫正相关、负相关、超进展三表未列全历史固定基因集。 | fix_log.md:39 | CONFIRMED |
> | lung-report-accuracy-review-07 | P2 | 禁用内容占位段落造成近空白页。 | fix_log.md:41 | CONFIRMED |
> | lung-report-accuracy-review-08 | P2 | 329 缩短版模板存在孤行溢出且未覆盖综合版章节。 | fix_log.md:41 | CONFIRMED |
> | lung-report-accuracy-review-09 | P3 | A 例肺癌诊疗知识前空白页来自历史源模板分页伪影。 | fix_log.md:64 | CONFIRMED |
> | lung-report-accuracy-review-10 | P3 | TMB 单位缺空格且批量缺失 PD-L1 时表格未明确显示“未提供”。 | fix_log.md:43 | CONFIRMED |
> | lung-report-accuracy-review-11 | P3 | 2.3 表连续同基因行重复显示基因名。 | fix_log.md:43 | CONFIRMED |
> | lung-report-accuracy-review-12 | P3 | 批量提交后缺少明确成功提示和任务跳转。 | fix_log.md:43 | CONFIRMED |

## 整改后验证（不改变上述冻结基线 verdict）

- 指南 10 行、免疫 15/12/8、化疗 27/22/11、顺铂 9 行及肺癌未检出基因集由
  `backend/tests/test_lung_history_alignment.py:96` 起的确定性回归覆盖。
- TMB 测定样本来源和组织阈值 10 由
  `backend/tests/test_lung_history_alignment.py:155` 覆盖；CRC 金标样式回归保持通过。
- 329 基因表由 `scripts/align_lung_comprehensive_templates.py:185` 从治理清单生成，
  329/329 唯一且生成脚本重复运行哈希一致。
- 批量失败记录和 macOS 资源叉过滤由
  `backend/tests/test_lung_history_alignment.py:511` 与
  `backend/tests/test_lung_history_alignment.py:530` 覆盖。
- 前端批量成功提示和任务跳转位于
  `frontend/src/views/ReportGenerateView.vue:1186`、
  `frontend/src/views/ReportGenerateView.vue:1211`。
- 最终复验汇总见 `fix_log.md:49`：588 A/B/C 整本渲染全部 PASS，329 七场景
  7/7 PASS，相关回归 115 passed，肺癌 QA gate PASS。
- 首轮远端全回归额外检出 PTEN 同基因非登记事件被误纳入的问题；修复没有放宽旧断言，
  而是将固定 15/12/8 版式与 B/C 精确事件选择器分离。精确性回归 46 项通过，A/B/C
  真实输入结构合同 3/3 PASS，详见 `fix_log.md` 的 R5。
- 合并后历史金标发布门禁另检出 2.3 续行显示曾影响 CRC358；生产未切换，修复将该行为
  限定到肺癌 329/588，并保留 CRC 金标及其批准差异指纹不变，详见 `fix_log.md` 的 R6。
- 冻结生产复验另捕获 329 长封面字段下的重复分页；同案修复后中间空白页由 1 降为 0，
  329 七场景整本回归 `7/7 PASS`，详见 `fix_log.md` 的 R8。
- 后续 P2/P3 复验补齐 PTEN/TSC2/BRIP1/PIK3CA、确定性化疗小结、UGT1A1 剂量文字、
  MLH1/PMS2 和指南/用法逐字口径。真实 A/B/C 结构合同 `3/3 PASS`，C 例靶向药表、
  药物介绍和第三部分均覆盖 8/8 历史基因；A/B/C 59/68/70 页且无空白/意外近空白页。
  329/588 各七个合成边界重新生成并全页检查，均 `7/7 PASS`。证据见 `fix_log.md` 的 R9；
  该整改证据不改变本审计对冻结基线的原始 verdict。

## 保留边界

329 当前只有合成边界输入，因此可以确认工程结构和确定性规则，但不能把它表述为真实
329 病例内容准确性 UAT。合成或未核实的 PD-L1 来源也不替代报告组医学签署。

## 2026-09-05 冻结生产基线 da8e62d 的新增发现

本次直接使用原始 Excel 并在 iyun129 相同冻结代码的隔离环境生成，不写生产病例库。
原始 A/B/C 的 24 个 SNV/indel 及 TMB/MSI 共 30 项数值复算一致，但不能由这些数字
一致推导 CNV 映射、药物身份或剂量建议正确。原完整只读证据保留于
`.work/lung-report-accuracy-review/pre_sync_audit.codex.md`；该早期过程稿的 01–06
在本真源中映射为 13–18，避免与 2026-09-02 的历史 id 冲突。

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung-report-accuracy-review-13 | P1 | Cnv 固定跳行误读多块表头，A 的 5 个基因未正确映射却在 Word 输出未检出。 | da8e62d 的 config/mapping.yaml:1029、reportgen/core/excel_reader.py:689；CASE-A Cnv!A1:G8；原 Word 表 13；.work/lung-report-accuracy-review/cnv_mapping.tsv | CONFIRMED |
| lung-report-accuracy-review-14 | P1 | 肺癌 UGT1A1 历史剂量文字不足以支持自动正常/减量结论，并未完整展示两个用于判定的位点。 | da8e62d 的 panels/lung_588_pdl1/rules/guideline_tables.yaml:189；CASE-C CtDrug!C645:D646、C654:D654；原 Word 表 26；下述 FDA 依据 | CONFIRMED |
| lung-report-accuracy-review-15 | P1 | 长春新碱被作为长春瑞滨别名，跨药物 H/L 汇总进入病例方案推荐。 | da8e62d 的 panels/lung_588_pdl1/rules/guideline_tables.yaml:213；CASE-C Ct1000!B92:E94、A95；原 Word 表 5、14、15；下述 NCI 药物身份依据 | CONFIRMED |
| lung-report-accuracy-review-16 | P2 | 续页表头、窄列断词和孤立尾段仍影响专业呈现。 | 原 CASE-C 物理页 6/21、CASE-B 物理页 12/14；.work/lung-report-accuracy-review/server/contact_sheets/ | CONFIRMED |
| lung-report-accuracy-review-17 | P2 | 登录后 Web E2E、真实 329 病例及 Windows Word/WPS 人工排版验收尚未完成。 | ego-browser 空间 72 为登录交接；.work/lung-report-accuracy-review/actual_xlsx329_check.json:biological_data；同目录 runtime_identity_extended.json | CONFIRMED |
| lung-report-accuracy-review-18 | P3 | TMB 恰为 10.0 时分类正确，但正文写“高于参考值 10”。 | SYN-L329-GOLDEN TMB!D3；原 Word 表 4；.work/lung-report-accuracy-review/actual_xlsx329_check.json:threshold_wording_defect | CONFIRMED |

依据：FDA 的 [2024 irinotecan 标签](https://www.accessdata.fda.gov/drugsatfda_docs/label/2024/020571Orig1s056lbl.pdf)
分别讨论 UGT1A1 风险基因型、剂量及临床监测，不能把历史单一显示基因型等同于普适
处方规则；这里只引用该冻结版本，不声称它是当前最新标签。NCI 分别登记
[vincristine sulfate](https://www.cancer.gov/publications/dictionaries/cancer-drug/def/vincristine-sulfate)
和 [vinorelbine tartrate](https://www.cancer.gov/publications/dictionaries/cancer-drug/def/vinorelbine-tartrate)，
支持二者是不同药物。修复撤下未经支持的自动结论，不自行引入新 CNV 阈值或处方标准。

### 需求覆盖、步骤地图与方法保真

本软件仓库无根级 plan.md；沿用既有 `lung-report-accuracy-review` 模块、Panel 输入/
模板契约和 `docs/release_checklist.md`，不另造一套临床签发标准。

`原始 XLSX → ExcelReader → Panel 规则/字段映射 → 分阶段生成 → DOCX 后处理 → 全页 QA → 独立源表回溯`。

新增验证脚本均在 ignored `.work/lung-report-accuracy-fix/` 且具有四行脚本头。
没有重做变异检测、基因组比对或 TMB 算法；这不是新生信分析项目，分析/绘图目录重构
为 NOT_APPLICABLE。真实输入、Word、PNG、日志留在受控临时路径，不进入 Git。

| mandated 方法 | 实际 method_status | verdict | evidence |
|---|---|---|---|
| 原始 CNV 字段可追溯，不将缺失/解析失败当阴性 | 语义解析两类表块，保留行号和原值；不明确的扩增/临床意义待复核 | FAITHFUL | reportgen/core/excel_reader.py:_extract_cnv_data；reportgen/rules/cnv.py；backend/tests/test_lung_input_fidelity.py |
| 同药物来源与双位点基因型保真 | 不同分子、混合块、冲突汇总不能借用；*28/*6 均显示，不自动处方 | FAITHFUL | reportgen/core/template_bridge_358.py:_build_lung_chemotherapy_tables；.work/lung-report-accuracy-fix/source_to_word.json |
| 真实 Excel 输入验证 | 3 份真实 588 输入实际读取、重生成；329 使用有效 XLSX 但生物数据为合成 | HONEST_BOUNDARY | 原始输入 SHA 及 source_to_word.json；SYN-L329-GOLDEN 来源记录 |
| 缺失 PD-L1 不杜撰 | 3 份真实源输入缺 PD-L1，Word 均为“未提供” | HONEST_BOUNDARY | source_to_word.json:reports[*].pdl1_missing_pass |
| 全页视觉 QA，不能通过放宽阈值消除 FAIL | 候选 A 原 FAIL 留存；修复语义段落连排后新 Word 全页通过 | FAITHFUL | Linux candidate_reports/ 与 retest_reports/ 的各自 DOCX/QA；reportgen/core/template_renderer.py:_restore_part3_dynamic_styles |
| 冻结提交与发布门禁 | 开发测试不作为冻结验收，尚未提交/合并/部署 | HONEST_BOUNDARY | development_snapshot.json:release_eligible=false；docs/release_checklist.md；HANDOFF.md:0.9 |

### 修复后开发验证（不改变上述原基线 verdict）

- 405 个源码/规则/模板/测试文件的开发快照 SHA256 为
  `8f6f52c70f868b63233b41730c3c1e6c1dd9998be4410357f8b98b0abf3a1811`；服务器与
  正本 405/405 一致，0 缺失、0 差异。该 SHA 是开发内容身份，不是 Git commit。
- 新增真实 XLSX 格式的输入/边界回归 72 项通过。四个 Panel package validation
  全部 0 issue，生产关闭范围未放宽。完整后端回归仍在隔离环境执行。
- A/B/C 的 24 个变异字段及 TMB/MSI 共 30 项源表比对全通过；A 的 5 个 CNV 基因
  全部待复核，双位点 UGT1A1 和长春瑞滨缺证据提示均通过，三份 PD-L1 均未杜撰。
  当前 Word 为 61/71/75 页，全页视觉/空白页检查通过，整体 QA 均 WARN。
- 首轮 A 的短药物解析尾段落在独占近空白页，已用肺癌限定的语义连排修复；新页 29/30
  肉眼复核确认审核尾段不再独占一页。旧 FAIL 不改写，仍留在 candidate_reports/。
- 剩余 16 的部分窄列表头/断词及历史知识文本专业审核、17 的 Web/真实 329/客户端
  人工验收仍未关闭；不得据此宣称可以自动临床签发。

### 已核实但不计新增业务缺陷

- Linux 首轮整库测试因缺少 httpx 和 pytest-asyncio 在收集阶段中止，属于
  `VERIFIER_PLUMBING`，不是业务断言失败。只在独立 test_dependencies/ 安装并重放，
  生产 venv 未变；旧 backend_tests.log/xml 不覆盖。
- 本地旧 main 落后 146 个提交是原核查时的事实；本轮已快进至 da8e62d，不能继续把
  “本地主干仍落后”作为当前问题。修复分支未发布则是另一件事。
- 新增 CNV 文案造成合理篇幅增长不是空白页缺陷；判定依据为逐页渲染和正文内容，
  不是要求所有病例保持同一页数。

下一步先取得 Git 提交授权并冻结候选，再补齐该 SHA 的完整回归、独立审计及历史金标
发布凭据。保留 pilot/医学复核边界，经 CI、备份与受控部署后核验运行身份及真实 Web 链路。

### R11 兼容性回归与身份补充

- R10 的 CRC 开发门禁捕获实际回归：合法空 Cnv 表只有 CopyNumber，旧解析器不接受。
  CRC 两个 Panel 的 reference/candidate 在读表阶段均失败；这是实际 producer 兼容性
  缺陷，不是环境失败。原 `crc_gate/qa_gate_report.json` 保留，未修改金标或批准差异。
- 在正本修复 CopyNumber 表头/原数值保留，先以 3 个真实 XLSX 反例重现，再得到
  75 项专项通过。数字型 CopyNumber 仍为未解释来源，不能自动升格为 AMP。
- 新开发快照 `7ebceb8ac0f6c0eb2e62cf618548e27818f723c76ba0e00a0bea6225e2d9b83f`
  与服务器 `source_final/` 405/405 文件一致；旧 R10 产物与源码身份仍为上文 8f6f52c…。
  当前正重跑 CRC 开发门禁；真实肺癌输入另做完整解析对象和 CNV 函数等价性复核。
- 329 新 Word 为 51 页，TMB 文案已改为“等于”，9 项实际 XLSX/Word/QA 检查均通过；
  输入生物数据仍为合成，QA 为 WARN。证据：`.work/lung-report-accuracy-fix/actual_xlsx329_check.json`。
- audit_reconcile 退出 1：Claude 原稿用带说明的短 SHA，本稿用完整 SHA；独立
  `git rev-parse da8e62d^{commit}` 确认是同一提交，并非源码版本漂移，但原始对账仍未通过。
  其他模块的覆盖缺口也未在本轮处理。对方的“历史一致性”通过不代表本轮新快照的
  原始字段/药物身份/医学证据审核通过，不擅自改写其结论。
- R11 Linux 定向回归实际为 102 项通过；完整解析对象与 CNV 函数的四案等价重放
  亦通过（`parser_equivalence.json`）。该结果只允许复用原 Word 观察证据，不将原
  生成记录的 8f6f52c… 身份改成新快照的身份。
- 两项治理测试的独立复现均停于 `git rev-parse HEAD` 退出 128，属于归档测试环境
  缺少 Git 元数据；未执行到业务断言，不计新业务缺陷，也不计验证通过。待冻结提交
  后在真实 Git 工作树补验；证据 `governance_probe.log/xml` 不覆盖旧失败。
- R11 CRC 开发 gate 已通过：358 两份各 68 页、301 两份各 75 页，生成/整本渲染、
  重复性 diff、current-output、知识门禁、Ruff 均通过。该 gate 的独立整库步骤和外部
  历史 reference 如实 SKIPPED，不能替代冻结后的历史发布门禁。共用 CNV 判别/等阈值
  文字仍须在同 SHA 外部历史金标上核验，不宣称所有 CRC 行为已经完全无回归。
- R10 整库原结果为 895 通过、2 跳过、9 失败：6 项 CRC 生成/样式受旧 CopyNumber
  解析影响、2 项无 Git 元数据、1 项 3 秒进程时限。R11 已以原断言重放其中 4 个 CRC
  用例并通过；另两项样式断言通过，3 秒用例仍失败并进入 R12。保留原 JUnit，
  不将原失败改写成通过，也未更新批准样式基线。

### R12 短时限子进程修复的独立证据

- `OPERATIONS`：实际独立重放同样超时，profiling 证实患者服务导入时提前加载
  报告引擎，单次累积约 6.345 秒。两个入口改为按需加载后约 0.592 秒；测量只作为
  固定环境观察，不充当时延 SLA。原 3 秒时限、进程隔离与回收机制均未更改。
- Linux `bootstrap_replay` 为 66 项通过：包含完整进程安全和无状态 API 模块、
  原 3 秒断言、签名表单及两项新增的无重型模块导入测试。只关闭此已复现的开发
  问题；不能据此宣称完整冻结 SHA 回归或登录后浏览器验收已通过。
- 新开发快照 `5d91ca05d445fa39ce6e6cfa45a6dfe97c55c43249bbffb3f893c5d4eb988e89`
  与 iyun129 `source_r12/` 405/405 一致。`bootstrap_scope.json` 确认仅两个 API
  服务与一个测试文件变动，报告引擎/规则/模板、原时限断言与 R11 字节相等。
  原 Word/CRC 证据保留各自生成身份，不覆盖旧 FAIL 或升级为发布凭据。
- 旧整库 9 个失败中的 7 项已定向复验通过；2 项治理检查、完整新 Git SHA 门禁、
  同 SHA 外部 CRC 历史回归、独立审计、Web/真实 329/Word 客户端人工验收未完成。
  三份真实 588 开发报告 QA 仍为 WARN，不是医学签发 PASS。
- 06:42 只读运行复核仍为 da8e62d，387/387 文件匹配、PID 未变，内外 health 为
  HTTP 200；只证明旧生产稳定且同步，不证明 R12 已部署。收尾身份回执为
  `.work/lung-report-accuracy-review/runtime_identity_r12_readonly.json`。
