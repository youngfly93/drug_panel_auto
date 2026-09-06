# 修复流水账

## R1 — 2026-09-02 肺癌报告组生产 UAT

- 冻结基线：`808a289a7cb253745d0247066249fb8982454cbf`
- 范围：肺癌 329/588 报告组自助生成链路。
- P1 / `MATERIAL_SCIENCE`：第三部分仍输出含非肺癌历史语境的知识段；修复边界为隐藏命中字段并显示待肺癌专属审核提示，不新增医学结论。
- P1 / `VERIFIER_PLUMBING`：网页上传的病例图片回执覆盖了人工填写的 PD-L1 原始来源编号、日期和标本身份；修复为图片回执与原始来源分字段保存。
- P2 / `VERIFIER_PLUMBING`：可选年龄的 `null` 被前端数值控件初始化成空字符串后显示为 `0`。
- P2 / `VERIFIER_SEMANTICS`：人工确认 Panel 后仍沿用自动识别失败的阻断提示。
- P2 / `VERIFIER_SEMANTICS`：上传预览没有随人工填写的样本类型刷新 TMB 展示口径。
- 观察项：肺癌 588 的完整历史金标附录篇幅较长；本轮不删除已锁定金标附录，避免把版式忠实度问题误修成内容缺失。

## R2 — 2026-09-02 修复与复验

- `MATERIAL_SCIENCE`：对 329/588 第三部分配置的跨癌种词只做字段级结构化隐藏，保留基因、变异和药物身份；渲染后的第三部分再做残留扫描。7 个合成边界病例/Panel 均为 `7/7 PASS`，全部 `part3_cross_cancer_residuals=PASS`。
- `VERIFIER_PLUMBING`：PD-L1 原始来源编号、来源日期、标本编号和 assay profile 与图片上传回执拆分保存；图片上传只写独立的 receipt/upload/bound-sample 技术字段，不再覆盖人工转录来源。
- `VERIFIER_SEMANTICS`：网页预览与正式生成使用同一 Panel 文本规则和 Panel 限定知识源；人工 Panel 选择成为有效选择，年龄空值保持空白，TMB 预览按当前样本类型刷新，329/588 恢复批量入口。
- `VERIFIER_PLUMBING`：为 `lung_329_pdl1`、`lung_588_pdl1` 接入可重复的合成金标；金标显式携带合成 PD-L1 来源和图片，不包含真实患者数据。当前输出快照补采 TPS/CPS/判定，发布门禁不再因验证器不认识肺癌 Panel 而失败。
- 正式 QA gate：`PASS`。Panel validation、知识发布门禁、Ruff、回归、329/588 金标 reference/candidate、重复性 diff、current-output 契约全部 PASS；历史外部报告目录未在本机配置，`legacy_reference` 如实 `SKIPPED`。
- 视觉代表件：329 为 23 页、588 为 46 页，均无空白/近空白页且视觉 QA PASS。页数由病例变异量和 588 历史固定附录决定，不锁定为 25 页。
- Web smoke：前端 production build PASS；登录、任务统计、Excel 上传/识别、预览、报告生成、QA、下载和 DOCX 文本检查全部 PASS。
- 未替代项：以上为工程与报告组 pilot 验收，不等于医学签署；真实病例 PD-L1 来源、医学规则和 Windows Word/WPS 人工版式确认仍需授权人员负责。

## R3 — 2026-09-02 肺癌历史终版内容对齐

- 冻结输入基线：`808a289a7cb253745d0247066249fb8982454cbf`；在制工程基线：
  `0421c06`。同案历史终版仅在受控外部目录只读使用，真实病例和患者标识不进入 Git。
- P1 / `MATERIAL_SCIENCE`（确认）：588 的肺癌指南药物提示表被收缩为 1 行占位；
  329 仍输出 14 条事件级检测行，均未实现历史终版的 10 行固定指南表加病例结果列。
- P1 / `MATERIAL_SCIENCE`（确认）：329/588 的化疗模块均为关闭状态；CtDrug 逐药附录
  未按 1B/2A/2B 收敛，英文药名前缀和 `Uncovered` 会进入读者可见输出。
- P1 / `MATERIAL_SCIENCE`（确认）：肺癌药物规则仅放行两个 A 级精确事件，历史 B 病例中
  由既有数据库支持的 C/D 级 PARP、mTOR 等研究性提示未进入 2.1/小结和药物介绍表。
- P2 / `VERIFIER_SEMANTICS`（确认）：混合“组织、血液”样本直接按血液阈值 16 计算；
  C 病例 TMB sheet 的 TCGA-fit 记录明确标注 `tissue`，应按组织阈值 10。
- P2 / `MATERIAL_SCIENCE`（确认）：`config/variant_table_baseline.yaml` 是 CRC 全局基线，
  导致肺癌追加 FBXW7/NF1/NRAS/SMAD4/SMARCA4/TCF7L2 等未检出行。
- P2 / `MATERIAL_SCIENCE`（确认）：588 免疫三表仅登记 6/1/0 条精确事件，329 整体关闭；
  同案终版固定契约为正相关 15、负相关 12、超进展 8 行。
- P2 / `VERIFIER_PLUMBING`（确认）：模板将化疗、2.2 等禁用内容保留成独占版面占位，
  是近空白页的直接来源；329 仍使用缩短版模板，未覆盖大 Panel 综合章节。
- P3（确认）：TMB 数值与单位缺空格；批量缺失 PD-L1 的正文表格仍可能为空；2.3 连续
  同基因行重复基因名；批量提交只在当前页写入状态，没有明确成功 toast 后跳转任务详情。
- 修复边界：固定文字从 SHA `8c9cb415…` / `4754eded…` 的同案历史终版转录；动态结果
  仅由本例 Variations/Fusion/Cnv/CtDrug/TMB 推导；C/D 级关系只使用既有数据库或已登记
  历史条目并显式标记“待报告组审”，不新增未经来源支持的药物关系。

## R4 — 2026-09-02 历史终版对齐修复与复验

- 329/588 均恢复 10 行肺癌指南表和正相关 15 / 负相关 12 / 超进展 8 行免疫表；
  肺癌未检出基因按 Panel 独立配置，读者可见结果中不再混入 CRC 基因集。
- Ct1000/CtDrug 解析恢复历史化疗结构：27 行药物预测、22 行方案预测、11 行用法；
  附录仅保留 1B/2A/2B，顺铂对照为 9 行，英文前缀和 `Uncovered` 已规范化。
- 既有数据库可按病例基因匹配的 C/D 级研究性靶向药进入 2.1、摘要和药物介绍，统一
  标记“待报告组审”；长列表只在摘要压缩，第三部分完整来源行不丢失。
- TMB 阈值优先跟随 TMB 测定样本；混合送检的组织测定例参考值为 10。数值与单位空格
  仅作用于肺癌 Panel，CRC 358/301 金标样式保持不变。
- 329 改用与 588 同族的历史综合版结构；329 基因附录由治理清单确定性生成，329/329
  唯一且顺序逐项一致。模板生成脚本连续运行两次哈希不变：329 为 `3cf8b164…`，588
  为 `fe53e154…`。
- 批量入口修复异常前上下文未初始化及 macOS `._*.xlsx` 资源叉误识别；A/B/C 单批
  3/3 成功、0 残留模板占位，缺失 PD-L1 的小结与明细均显式显示“未提供”。
- 588 A/B/C 整本渲染分别 59/67/64 页，均 0 空白页、0 近空白页，合同、内容和串案
  检查全部 PASS；329 七个边界场景 7/7 PASS，代表件 57 页且 0 空白/近空白页。
- 前端 production build PASS；相关回归 `115 passed, 2 skipped`；QA gate 的 Panel
  validation、知识门禁、329/588 reference/candidate、重复 diff 和 current-output 全部
  PASS。外部历史目录未配置时 `legacy_reference` 仍如实 SKIPPED。
- 边界不变：本轮是工程与报告组 pilot 对齐，不把合成/未核实 PD-L1 来源冒充临床真源，
  也不替代报告组医学签署和 Windows Word/WPS 正式 UAT。

## R5 — 2026-09-02 远端回归发现的免疫事件精确性修复

- 首轮 GitHub 全后端回归为 `821 passed, 2 skipped, 1 failed`；唯一失败证明固定免疫表
  曾把 PTEN 的历史精确事件错误放宽到同基因另一个变异。该失败未被忽略或改写测试。
- 固定正相关 15 / 负相关 12 / 超进展 8 行继续完整输出；B/C 已登记的 MLH1、PMS2、
  ATM、BRIP1、MSH3、BRCA2、PTEN 关联恢复为转录本与 HGVS 精确匹配。
- DDR 固定行支持一组精确事件选择器；同基因错误转录本、PTEN 非登记事件以及单独 TP53
  不再进入 B/C 免疫结果。CASE-LUNG-A 没有配对历史终版，不增加未登记的精确事件主张；
  固定 IFNGR1/2 基因组行仍按其确定性规则展示。
- 精确性及历史对齐回归 `46 passed`，冻结前组合回归 `142 passed, 2 skipped`；A/B/C
  真实输入结构合同和整本渲染均为 `3/3 PASS`，B/C 免疫计数恢复为 `5/0` 与 `2/1`；
  329 七场景 `7/7 PASS`，329/588 Panel package validation 均为 0 issue。

## R6 — 2026-09-02 历史金标发布门禁发现的 CRC 作用域回归

- `5036c0e` 的两条 GitHub `qa-gate` 均通过；但随后从冻结 SHA 在 iyun129 Linux
  渲染器生成的 102 页历史金标候选被正式 diff 门禁拒绝，未部署到生产。
- 新旧候选直接对比把新增差异收敛到两类：生成时使用的脱敏批准上下文不同，以及肺癌
  2.3 表“连续同基因续行留空”误作用于 CRC358。前者恢复原批准上下文重跑；后者把
  `gene_display` 写入严格限定到肺癌 329/588。
- 新增 CRC 回归断言：默认药物表压缩不得写入或留空 `gene_display`，NCCN/指南表的
  连续同基因行不得留空。历史批准差异哈希、CRC 医学规则和金标报告均不修改。

## R7 — 2026-09-02 肺癌指南旧占位清理

- 生产浏览器生成的 329 报告确认：10 行肺癌指南表已恢复，但表后仍残留“历史内容已移除”
  和“仅展示精确事件、需复核”的旧占位段落，与当前确定性表内容互相矛盾。
- 588 历史模板构建器改为删除整段旧 NCCN 正文及其占位标题，不新增医学文字；329 同族模板
  由同一 588 母版确定性派生，因此两种产品同时消除该残留。
- 模板版本升至 `0.5.2-review.5`，契约把两条旧文案改列为 forbidden；构建器增加规范化
  重载保存，从受控源重建的 588 模板 SHA256 与登记值逐字节一致。
- 相关契约/结构/历史对齐/样式回归 `70 passed`；588 A/B/C 整本渲染仍为 59/67/64 页、
  0 空白和 0 近空白页，329 七个边界场景 `7/7 PASS` 且均执行整本视觉 QA。

## R8 — 2026-09-02 329 长封面字段重复分页修复

- 冻结生产版 `4000d0d48e33bc966955882dc95ce2b2835dd2a0` 用网页验收 Excel 实测：
  329 报告生成和下载成功，但 Linux/LibreOffice 整本渲染为 60 页，第 2 页为
  `nonwhite_ratio=0.0` 的中间全空白页。首页字段较长时，329 未显式声明前置分页策略，
  默认插入的额外分页被挤到第 2 页，与综合模板已有的 section break 重叠。
- 修复仅使 `lung_329_pdl1` 显式继承同族前置版式契约：
  `guide_spacer_count=30` 且 `insert_page_break=false`；未改医学规则、模板或 588 行为。
- 同一 Excel、同一长封面字段复跑后为 57 页，整本视觉 QA `PASS`，空白页检查
  `PASS`；329 七个边界场景再验 `7/7 PASS`，每份 51–56 页，空白/近空白页均为 0。
- 回归棘轮：329/588 两个综合 Panel 都必须显式依赖已有 section break；
  肺癌相关测试 `92 passed`，329/588 Panel package validation 均为 0 issue。

## R9 — 2026-09-02 肺癌历史终版 P2/P3 内容补齐

- `MATERIAL_SCIENCE`：按同案 C 历史终版登记 PTEN、TSC2、BRIP1、PIK3CA 的
  Panel 级 C 类研究性药物映射，运行时统一附加“待报告组审”。C 例靶向药表和药物介绍
  均为 8/8 基因；第三部分只对有精确历史事件或已审核事件级来源的变异补入病例解析，
  不把事件级参考文献外推成药物特异证据。
- `VERIFIER_SEMANTICS`：化疗小结由有效性预测表中“敏感/优先”方案确定性推导；B 例为
  吉西他滨单药，C 例为吉西他滨+长春瑞滨、吉西他滨单药、白蛋白结合型紫杉醇单药、
  紫杉醇单药，与同案终版一致。旧“供报告组评审”占位不再进入 Word。
- `MATERIAL_SCIENCE`：仅从 CtDrug 中 UGT1A1 *28/*6 指定位点提取无冲突基因型；已登记
  的 6TA/6TA 与 6TA/7TA 组合分别输出历史“正常剂量使用”和“减少剂量使用”。缺失、
  冲突或未登记组合不推断剂量。
- 指南结果列改为历史标点和措辞：ALK 未检出为“未见变异”，检出行去掉“检出”前缀并
  使用半角逗号；肺癌未检出固定集补 MLH1、PMS2。11 条化疗方案用法逐条恢复历史文字。
- 删除“肺癌诊疗知识”和第二部分前重复的显式分页，让模板既有 section break 单独负责
  分页。A/B/C 整本渲染为 59/68/70 页，均 0 空白页、0 意外近空白页；三例结构合同
  `3/3 PASS`，C 例指南 BRAF/ERBB2、8 个靶向基因、14 个第三部分病例段均命中。
- 588 首轮边界复验如实因旧“仅精确事件”计数预期失败 3 例；同步为已批准的基因级
  C/D 规则后从零重跑，329 与 588 均为 `7/7 PASS`，14 份报告视觉 QA 和跨癌种残留
  扫描全部 PASS。期间磁盘满导致一次 329 中止；只清理可再生 `.work/` 中间件后完整
  重跑，不把中止或半成品记作 PASS。
- 冻结前后端整库回归 `830 passed, 4 skipped, 0 failed`。正式 329/588 QA gate 为
  `PASS`：Panel validation、知识发布门禁、Ruff、选择性回归、两种 Panel 的 reference /
  candidate / repeat diff 和 current-output 均 PASS；本轮未读取外部历史目录，
  `legacy_reference` 如实 SKIPPED。

## R10 — 2026-09-05 肺癌输入保真修复（在制，未部署）

- 输入代码基线：`da8e62de672ecaa5416d3c2b29e3e9294531f519`；用户已授权修改、同步和部署，尚未明确授权 Git 提交。当前工作分支为 `codex/lung-report-accuracy-fixes-20260905`，不把工作树测试冒充冻结发布门禁。
- P1 / `MATERIAL_SCIENCE`：Cnv 固定跳过两行使多块工作表的基因汇总被当作表头；改为语义表头解析，分别保留汇总/区段、原始行号和原始数值。`gain`、数字型 Cnvkit 和不同口径 AvgCP 不自动升格为扩增或临床阳性；非空畸形表明确报错，缺表明确待复核。
- P1 / `MATERIAL_SCIENCE`：撤下肺癌历史 UGT1A1 自动“正常/减少剂量”映射；完整展示 *28/*6 原始基因型、缺失或冲突状态，剂量留待医学复核，不自行新增处方标准。本条取代 R9 的该项历史输出要求，不改写旧输出事实。
- P1 / `MATERIAL_SCIENCE`：删除长春新碱/长春碱到长春瑞滨的跨药物别名；没有同一分子的直接汇总时明确缺证据，禁止缺证据的分量进入优先组合。混合药物块、错误双语对照和互相冲突的汇总均不自动选第一条。C 例优先方案不再包含由错误映射产生的“吉西他滨+长春瑞滨”。
- P2/P3：仅对肺癌第三部分的短药物解析块按语义连排，消除独立审核尾段造成的近空白页；不按病例或物理页号硬编码。TMB 恰等于阈值时改为“等于”，保留原 `>=` 分类，不改阈值或原始数值。
- 保护边界：CRC358/301 二进制模板、医学规则、金标和批准差异指纹未改；肺癌 329/588 仍为 pilot，其他未就绪产品继续关闭。真实源表和生成文件不进入 Git。
- 本地同步：主干已快进至基线 da8e62d；用户原有 HANDOFF 改动保存在专用 stash `6af2a8c8ee77a6b35f0d25e9af65f6bf6c184c32`，未丢弃，其他未跟踪审计文件未动。先前完整只读审计留在 ignored `.work/lung-report-accuracy-review/pre_sync_audit.codex.md`，新记录不覆盖其失败证据。
- 环境/失败保留：外盘空间不足的一次临时 venv 安装未完成，只清理本轮新建的可重建 venv，未动业务数据。本地测试改用系统临时目录。Linux 首轮整库回归因缺 `httpx`/`pytest-asyncio` 在收集阶段失败；补到隔离 `test_dependencies/` 后重放，生产 venv 未安装或升级依赖。
- 候选 A 首轮生成触发 `VISUAL_RENDER_LOW_CONTENT`，原 FAIL 及原 Word 保留；短药物解析连排后重新生成新 Word，未放宽 QA 阈值。
- 已完成：新增输入与边界回归 `72 passed`；四个 Panel package validation 均 0 issue，生产禁用范围校验 PASS。服务器 `source_retest` 的 405 个源码/规则/模板/测试文件与正本逐一 SHA256 一致；开发快照为 `8f6f52c70f868b63233b41730c3c1e6c1dd9998be4410357f8b98b0abf3a1811`，不是 Git 发布 SHA。
- 已完成：真实 A/B/C 原始 Excel 字节不变，24 个 SNV/indel 字段及 TMB/MSI 共 30 项源表复核全通过；三份 Word 为 61/71/75 页，全页视觉及空白页检查 PASS。A 的 5 个 CNV 基因均显示待复核，UGT1A1 双位点与长春瑞滨缺证据提示均通过；整体 QA 为 WARN，医学签发并未通过。证据：`.work/lung-report-accuracy-fix/source_to_word.json`、`numeric_recalculation.tsv`、`snapshot_match.json`；Linux 原产物在 `reportgen-lung-fix-20260905.9x4Hk4/retest_reports/`。
- 在执行：完整后端回归、有效 329 XLSX 重生成。待后续：冻结 Git 提交、GitHub 必需检查、同一 SHA 的 Linux CRC 历史金标凭据、备份与 immutable release 部署、登录后 Web 异步生成验收。原生产仍为 da8e62d，未重启或切换。

## R11 — 2026-09-05 CRC 兼容性门禁捕获的 CopyNumber 表头边界

- P1 / `MATERIAL_SCIENCE`：R10 新 CNV 解析器只接受 Status/Cnvkit，拒绝了既有 CRC 合成金标的有效空表 `Gene/Chr/Start/End/CopyNumber`；CRC358/301 的 reference/candidate 共四个生成步骤均在读表阶段失败。未修改金标、批准差异哈希或把输入文件改成新格式来规避问题；旧 `crc_gate/qa_gate_report.json` 和 `crc_gate_receipt.json` 保留。
- 最小复现先红后绿：新增三个真实 XLSX 测试在修复前全部失败。解析器现识别 CopyNumber 作为数值来源表头，空表保持为空，非空值保留字段名与数值并待复核，不添加拷贝数阈值或把数值判为扩增。全专项回归现为 `75 passed`，Ruff 和 diff whitespace 检查通过。
- 当前开发内容快照为 `7ebceb8ac0f6c0eb2e62cf618548e27818f723c76ba0e00a0bea6225e2d9b83f`，405 个受测文件与 iyun129 的 `source_final/` 逐一匹配。R10 的 `source_retest/` 和其 Word/QA 保留不变，不把旧产物改标成新代码生成。
- 受影响闭包：重新执行 CRC358/301 的开发 golden/current-output/repeat-diff/整本渲染；完整后端 R10 作业继续保留原快照身份。对 A/B/C/329 另以新旧进程比较完整 ExcelDataSource 和全部相关 CNV 函数结果摘要，只有一致后才复用 R10 的 Word 证据。
- 329 实际 XLSX 已完成：51 页，QA WARN、全页/空白页 PASS；ERBB2 变异、TMB 10.0/H 的“等于参考值”、缺失 PD-L1、CNV 与 UGT1A1 双位点的保守显示均核对通过；这仍是合成生物数据，不是真实 329 临床 UAT。
- 同步复核：06:04 左右 origin/main、iyun129 release/REVISION/进程 cwd 仍为 da8e62d，PID 2596421 未重启，本地及公网 health 均 200。
- 共享审计对账仍非 PASS：现有 Claude 原稿的短 SHA 带说明文字，Codex 使用完整 SHA；Git 独立解析确认二者均指 da8e62d，但机器仍报告表示差异及其他模块覆盖缺口。未修改对方原稿、未宣称双审通过。其历史一致性审核明确不含医学时效；本轮 raw 字段保真发现不由历史一致性的通过结论抵消。
- 建议提交信息（尚未提交）：`fix(lung): preserve Excel evidence and conservative review boundaries`。
- 本轮文件范围：`reportgen/core/{excel_reader,template_bridge_358,template_renderer,qa_report,validation}.py`、`reportgen/rules/cnv.py`、`config/mapping.yaml`、肺癌 588 的 `rules/{biomarkers,guideline_tables}.yaml`（329 继承）、`backend/tests/test_lung_{history_alignment,input_fidelity}.py`、`scripts/validate_lung588_real_inputs.py`，以及本流水账、`HANDOFF.md`、本 agent 的 `audit/lung-report-accuracy-review.codex.md`。其他用户文件和运行凭证不提交。
- R11 Linux 定向回归：`test_lung_input_fidelity.py` + `test_lung_history_alignment.py` 为 `102 passed`（59.92 秒）。本地 75 项与 Linux 102 项分别有 JUnit 回执，不混计为 177 个独立用例。
- R11 对四份既有肺癌输入的完整解析对象、CNV 分类/源状态/显示函数结果均与 R10 逐项 SHA256 相等；源码差异仅 ExcelReader、CNV helper 和其测试三个文件。`parser_equivalence.json` 明确关联旧 Word 身份并声明 `release_eligible=false`，不是把旧报告冒充新快照生成。四份 Word 已复制到 ignored `reports/`，下载前后 SHA256 一致。
- R10 整库作业中的两项治理测试在 R11 独立重放仍失败于 `git rev-parse HEAD`（退出 128）：隔离归档没有 `.git`，尚未进入业务断言。证据为 `governance_probe.log/xml`；不修改脚本的身份门禁、不伪造 Git 版本来改成 PASS，待冻结提交的实际 Git 工作树/CI 补验。
- R11 CRC 开发 gate 为 PASS：358 reference/candidate 各 68 页、301 各 75 页，4 份均成功生成及全页渲染；repeat diff、current-output、知识门禁和 Ruff 通过。pytest 显式复用独立作业而 SKIPPED，外部 legacy_reference 未配置而 SKIPPED。该 gate 不等于冻结 SHA 的外部历史金标门禁。共用 CNV 状态判别和 TMB 等阈值文字有代码变动，不能只凭合成用例宣称所有 CRC 历史行为完全不变。
- 原整库中 4 个失败落在 CRC 合成 Excel/缺失 MSI 阻断/301 基础生成/301 golden；在 `source_final` 使用原断言重放，记录到 `crc_failure_replay.log/xml`，不覆盖 R10 结果。
- 整库 R10 最终为 `895 passed, 2 skipped, 9 failed`（2090.70 秒）：2 项无 Git 元数据，6 项旧 CopyNumber 解析影响的 CRC 生成/样式，1 项原本期望 3 秒内返回的患者信息子进程超时。该结果不能描述为整库通过，完整 JUnit 已回传保存。
- R11 的上述 4 项 CRC 失败重放为 `4 passed`（273.21 秒）；`remaining_replay` 最终为 `2 passed, 1 failed`（267.62 秒）：两个 CRC 样式测试通过，原 3 秒时限仍失败。显式 `REPORTGEN_UPDATE_BASELINE=0`，没有更改批准基线；旧失败回执保留，计时问题进入 R12。

## R12 — 2026-09-05 患者信息短时限子进程启动修复

- P2 / `OPERATIONS`：原 `test_enrichment_hard_timeout_returns_fast_child_payload` 在整库和独立重放均超出 3 秒。固定环境导入 profiling 显示 `clinical_info_service` 累积导入约 6.345 秒；模块级签名库与 ReportGenBridge 导入提前加载整套 Excel/Word 引擎，而患者 YAML 查询并不需要这些依赖。
- 仅将 `clinical_info_service.signature_options` 和 `generation_process` 中 ReportGenBridge 改为按需导入。签名选项调用及可替换接口保留；不改 3 秒硬时限、spawn、超时终止/回收、大队列交接或任何报告字段逻辑。没有修改 `reportgen.core.__init__` 或更换生产依赖。
- 新增两个独立解释器测试，禁止短任务模块导入时加载报告生成器、模板渲染器和 Bridge。Linux 完整进程测试、无状态接口模块及签名表单合同共 `66 passed`（50.82 秒，2 个依赖弃用告警），包含原 3 秒用例和超时终止/无泄漏断言。相同环境单次导入观察从 6.345 秒降为 0.592 秒，不将该单次耗时声明为性能 SLA。
- R12 开发快照 `5d91ca05d445fa39ce6e6cfa45a6dfe97c55c43249bbffb3f893c5d4eb988e89` 与 iyun129 `source_r12/` 的 405 个文件逐一一致。相对 R11 仅变动上述两个服务文件及 `backend/tests/test_generation_process.py`；报告 producer、规则、模板、原 3 秒测试字节不变。`bootstrap_scope.json` 关联 R10 Word 与 R11 CRC 证据，明确保留旧生成身份及 `release_eligible=false`。
- R10 整库原 FAIL 不改写：9 个失败中的 7 个业务/计时用例已在 R11/R12 按原断言重放通过；2 个需要 Git 元数据的治理检查待真实冻结工作树/CI 补验。完整新 SHA 回归、同 SHA 外部 CRC 历史门禁、独立审计、登录后 Web、真实 329 和 Word/WPS 人审均尚未完成。
- 增补文件范围：`backend/app/services/{clinical_info_service,generation_process}.py`、`backend/tests/test_generation_process.py`。建议提交信息仍为 `fix(lung): preserve Excel evidence and conservative review boundaries`；完整范围见 R11，本轮未提交或部署。
- 继续入口：`.work/lung-report-accuracy-fix/bootstrap_replay_receipt.json`、`bootstrap_scope.json`、`bootstrap_snapshot.json`；所有测试在隔离目录，生产仍保持原 release。需用户明确授权 Git 提交后，才能按冻结发布流程继续。
- 收尾核对（06:42）：origin/main 与实际生产 release/REVISION/进程 cwd 仍一致为 da8e62d；387 个运行源码/模板/知识文件逐一匹配，PID 2596421 未变、未发现启动后改写 Python 文件，本机与公网 health 均 HTTP 200。R12 本地/服务器测试后源码校验通过，Ruff 与 diff whitespace 通过。此次同步仅含本地主干和服务器隔离测试快照，不是生产部署。

本次各轮新发现计数（不是剩余问题计数或临床放行结论）：

| 轮次 | P0 | P1 | P2 | P3 | 当前状态 |
|---|---|---|---|---|---|
| R10 原始输入复核 | 0 | 3 | 2 | 1 | 三项 P1 与等阈值措辞已作定向修复；版式部分项、人审/Web 验收仍未闭环 |
| R11 CRC 兼容性回归 | 0 | 1 | 0 | 0 | CopyNumber 边界已修复、102 项定向及 CRC 开发门禁通过；冻结发布另验 |
| R12 子进程启动 | 0 | 0 | 1 | 0 | 66 项原合同与新增依赖隔离测试通过；冻结发布另验 |

## R13 — 2026-09-06 冻结提交与生产发布

- 用户明确授权“提交、部署吧”。开始冻结 R10–R12 的 18 个业务/测试/记录文件，保留其他未跟踪原稿及原用户 stash。405 个受测文件与 R12 快照一致，远端 main 仍为 da8e62d。
- 按既有流程执行 PR 必需检查、冻结 SHA 的 Linux 历史金标签注和 release-check，随后才运行 iyun129 备份及 immutable release 部署；不放宽断言、批准差异指纹、产品关闭范围或医学签发边界。
- 提交时点尚未部署；运行回执、CI URL、精确 SHA、金标哈希、备份和运行身份统一记录于 ignored `.work/lung-report-accuracy-release/`。若任何必需门禁失败，保留旧生产并据实停止发布。

## R14 — 2026-09-06 新规格边界与小 Panel 派生输入

- R13 的 PR #50 已合入 main（295ebd26ad03d1f213c0fbfc7e6b1b982cb2ae50），
  三次 CI 分别通过 909 项后端回归及完整 QA。Linux 冻结 QA、历史金标均通过；
  Vercel 非必需预览失败仍保留。三次部署记录分别为 GitHub 查询失败、本地磁盘不足、
  用户新规格到达后在上传阶段主动停止；未执行服务切换，生产仍是 da8e62d。
- 用户明确 #14/#15 与历史终版一致，暂不改动：前向恢复历史规则默认值，原医学
  疑点转入报告组待决；保留 #13 CNV 修复、候选严格策略代码及显式候选单测。
  这不是撤销原审计发现，也不代表医学认可历史药物/剂量口径。
- 新增派生脚本和 6 项单测，只改两个工作表产品旗标。首次单测 5 fail / 103 pass，
  捕获 ZipInfo 被目标写入过程修改、导致源 ZIP 复核偏移错误；以复制 ZipInfo 修复，
  原文件字节未改变。新回归 108 pass，原失败回执和新 JUnit 分开保留。
- 6 份真实派生输入完成全单元格与非目标 ZIP 成员复核。C 例指定 13 基因集合实际
  还包含源表第 39 行 PIK3CA A1066V（Ⅱ类），无法同时满足纯集合派生和三行验收。
  62/62+PD-L1 共同旗标不能形成独立结构指纹。两项均已提交用户确认；不改患者数据
  或放宽验收来消除冲突，Word 建包、Web 批量和新部署暂停。
