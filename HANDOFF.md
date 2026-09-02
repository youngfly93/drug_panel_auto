# HANDOFF —— 基因组 Panel 自动化报告系统（Web 平台）

> 当前状态快照。更新就改这个文件，别新建 `_v2`。
> 最近更新：**2026-09-02**（肺癌 329/588 历史终版内容对齐候选）。

---

## 一、一句话现状

结直肠癌 358/301 报告线由 iyun129 的 immutable release 体系提供服务；肺癌
329/588 按“先生成报告组 pilot 评审稿、再依据真实 Word 反馈优化”的口径开放单份与
批量生成。该口径不等于正式临床放行或医学签署。任何生产状态仍必须以
`current_release`、`REVISION`、进程 cwd 和健康检查四项实时证据为准，不能由本文档
静态推断。

## 0.6 2026-09-02 肺癌 329/588 历史终版内容对齐候选

本节是当前候选的最新人工可读真源；与 0.4 的旧靶向药/化疗范围冲突时，以本节和
Panel/UAT YAML 为准。合并部署前不得据此推断生产已切换。

- 工作分支：`codex/lung-report-history-alignment-20260902`；冻结生产基线
  `808a289a7cb253745d0247066249fb8982454cbf`。588 的同案对照仅使用受控外部 B/C
  历史终版，患者文件不进入 Git；329 仍只有合成工程边界输入。
- 329/588 固定输出历史 10 行肺癌指南表、正相关 15 / 负相关 12 / 超进展 8 行免疫表，
  并启用 Ct1000/CtDrug 化疗正文；化疗位点附录只保留 1B/2A/2B。
- 既有肺癌知识库可匹配的 C/D 级研究性靶向药进入摘要、2.1 和药物介绍，显式标记
  “待报告组审”。这扩展的是报告组 pilot 可见内容，不等于医学终审或外部自动签发。
- 固定免疫版式不放宽 B/C 的病例事件证据：MLH1、PMS2、ATM、BRIP1、MSH3、BRCA2、
  PTEN 仍按已登记转录本 + HGVS 精确匹配；同基因其它事件不得继承该病例关联。
  CASE-LUNG-A 没有配对历史终版，不补造未登记的精确事件主张；固定基因/基因组行仍按
  其确定性匹配规则展示。
- TMB 参考值跟随实际 TMB 测定样本；肺癌未检出列表使用独立指南基因集；批量缺失
  PD-L1 显示“未提供”，批量提交有成功提示并跳到任务详情。
- 当前候选的本地 A/B/C 结构合同为 3/3 PASS；B/C 免疫计数为历史对照的 5/0、2/1。
  正式发布仍需冻结 commit 的 CI、Linux 历史金标凭据、iyun129 切换和生产浏览器 smoke。

## 0.5 2026-09-02 肺癌 329/588 报告组 UAT 修复候选

- 工作分支：`codex/lung-report-uat-fixes-20260902`；冻结基线
  `808a289a7cb253745d0247066249fb8982454cbf`。本节在合并、部署前描述的是候选状态，
  不得据此推断 iyun129 已切换。
- 生产浏览器反馈中的首页预览鉴权、审核状态登记、工作台统计、反馈弹窗和单例阶段进度
  已由基线版本修复；本轮补齐报告内容、来源溯源、预览语义和肺癌发布验证器。
- 329/588 第三部分对配置的跨癌种历史语境执行字段级结构化隐藏；不删除变异或药物身份，
  渲染后残留扫描继续作为 QA 证据。两套 7 例合成边界均 `7/7 PASS`，残留检查全部
  `PASS`。
- PD-L1 原始来源字段与病例图片上传回执已拆分；图片上传不再伪装成 IHC 原始记录。
  网页仍不从 NGS Excel 杜撰 TPS/CPS、克隆、平台或标本身份。
- 人工确认 329/588 Panel 后可继续生成；年龄缺失不显示 0，TMB 预览随当前样本类型
  刷新，329/588 单份和批量入口保持开放。预览和正式报告统一应用 Panel 文本规则与
  Panel 限定知识源。
- 新增 329/588 合成金标入口，PD-L1 来源、标本和图像均为显式合成数据。正式肺癌
  QA gate 的 Panel validation、知识门禁、Ruff、回归、两次金标生成、重复性 diff、
  current-output 契约全部 `PASS`；本机未配置历史外部报告目录，legacy reference
  如实 `SKIPPED`，没有伪记为 PASS。
- 代表件视觉 QA：329 为 23 页、588 为 46 页，均无空白/近空白页；页数随病例内容及
  588 历史固定附录变化，不得重新宣称“每份固定 25 页”。Web production build 与
  API smoke（上传、识别、生成、QA、下载）均通过。
- 当前工程支持并完成上述证据的肺癌产品仅为 `lung_329_pdl1` 与
  `lung_588_pdl1`。13/20/62/66/158、无 PD-L1 等产品仍需技术老师提供配套 Excel、
  金标和产品规则后逐族接入；不得由 329/588 的 PASS 推导为全肺癌产品覆盖。
- 工程 PASS 仍不替代真实病例医学签署和 Windows Word/WPS 报告组 UAT；pilot 标记、
  不杜撰、PII 不入 Git 和病例隔离纪律不变。

## 0.4 2026-09-01 肺癌 329/588 已锁决策（当前唯一真源）

本节是肺癌 pilot 当前治理口径的唯一人工可读真源；Panel/UAT YAML 是其机器执行镜像。
较早审计、验收记录和本文件后续历史段落只说明当时状态，不得覆盖本节。

- 报告组可在网站上传肺癌 588/329 Excel，取得带明显 pilot/评审稿标记的完整 Word；
  单份和批量均开放，目的仅是尽早看到真实报告并反馈问题。
- 第三部分启用。最终 Word 继续扫描跨癌种历史叙述残留；命中记为 QA `WARN`，不阻断
  pilot 草稿生成，但正式临床放行前必须复核。
- 靶向药仅显示 Panel 已登记的 BRAF V600E、ERBB2 G660D 精确事件规则，并标
  “待报告组审”。临床背景缺失或不确定时仍显示，但只列本条规则实际缺少/未明确的项
  （病理类型、疾病范围/分期、既往系统治疗或伴随诊断状态）；无效值、明确超出癌种/
  分期/治疗史适用范围时继续阻断。泛基因、跨癌种和基础药物库回退不开放。
- 批量表单中的 PD-L1 数值、判定、来源和图片不得整批复制，也不得从 NGS Excel 推断；
  每个批量病例保持空值并在 Word 显示“未提供”。
- 329/588 批量病例若 Excel 与逐病例富集均没有患者姓名，Word 姓名栏显式显示“未提供”，
  不复制整批共享姓名、不补造身份；已有病例姓名保持原值，样本编号仍须逐病例可识别。
- 报告组逐病例 `decision`、`reviewer`、`date` 不再是生成 pilot 草稿的前置门禁；产品
  负责人本次指令已作为一条反馈来源登记。正式临床发布、医学签署和外部无人工复核
  交付仍是另一层决策，未被本次去锁替代。
- 任务详情中的 `CONTROLLED_PILOT_REVIEW_REQUIRED` 只作 warning，不再制造 blocker；
  `admin`/`reviewer` 可在页面登记“已审核”或“退回修改”，系统自动记录账号与时间。
- PII 纪律、不杜撰缺失数据、病例间不串值和 pilot/评审稿可见标记保持不变。
- `lung_13`、`lung_62`、`lung_62_pdl1` 允许搭建报告组评审用 draft；在金标、同案
  Excel、病例级来源和正式发布证据齐备前，生产入口继续关闭。

## 0.3 2026-08-09 肺癌 329/588 反馈冻结候选

- 冻结工程提交：`fd3c98154e031832c8db9d698ddfddd2ad000008`，分支
  `codex/lung-feedback-20260809`；本轮只关闭两个 P1 工程缺口，没有继续扩大医学规则。
- P1-1：显式肺癌 Panel 在公共 KB 不可用时仍只走 Panel 精确事件，不能回退并继承
  基因级 `CtDrug`；无 Panel legacy 回退保持兼容。
- P1-2：`required_tables`、必需列和 protein-HGVS 二选一列现在由中央校验器强制，
  Web 在建任务前阻断，`ReportGenerator` 对直接/CLI 调用再次阻断。
- 冻结回归：后端整库 `755 passed, 4 skipped, 0 failed`；修改文件 Ruff、前端
  typecheck/build/ESLint、两套 Panel package validator 均通过。
- iyun129 隔离 Linux：329/588 合成边界各 7/7 PASS，3 份受控真实输入 3/3
  完整 Word QA PASS；三份 receipt 和 17 份 QA 均绑定冻结 SHA，17/17 renderer
  fingerprint 与 runtime profile/mapping hash 一致。
- Linux 证据：`.work/linux_lung_feedback_fd3c981/`；同一批 Linux DOCX 的 Windows/
  报告组交接：`.work/windows_uat_fd3c981/`。受限真实报告不得离开授权环境。
- 当前正式 UAT 仍为 `BLOCKED`：病例级 PD-L1 来源 0/3，报告组审核/通过 0/3；
  Windows Word/WPS 尚无人工签署。不得把机器 QA 或 Linux PASS 写成医学 UAT PASS。
- 2026-08-09 只读核对时，iyun129 当前 release/REVISION/process cwd 仍一致指向
  `fad5c87775e1f217fbe13c8181165045841c27ec`，本地/公网 health 均 HTTP 200；候选
  `fd3c981...` 未部署、未切换。
- 审计观察层：`audit/lung-feedback-20260809.codex.md` 与
  `audit/report-group-system-uat.codex.md`；独立审计 P0/P1/P2/P3=`0/1/1/0`，其中
  P1 为外部签署/发布阻断，P2 为“两个事件、三个治疗组合”的旧措辞歧义。
- `audit_reconcile.py` 对账未发现 identity 缺失/不一致，但当前肺癌模块只有 Codex
  审计、缺少 Claude 对审；发布前继续以未关闭的人审 blocker 和共享审计覆盖缺口为准。

## 0.2 2026-07-14 CRC358 历史金标准发布候选

- 唯一执行 Spec：`docs/spec_crc358_historical_golden_batch_hardening.md`。
- 脱敏病例代号：`crc358_reviewed_case_a`；真实 Excel/DOCX、患者信息及签名均在
  ignored/runtime 路径，未进入 Git。
- 工程回归：后端 `428 passed, 1 skipped`；前端 production build、知识发布门禁、
  签名 preflight、Linux LibreOffice 视觉 QA 和脱敏历史契约均通过。
- 历史全文 Diff 无阻断错误；一处历史免疫列表旧排序已按统一 VAF 契约纠正并显式
  登记，仍待报告组二审确认。
- 反馈项 3/6 的当前候选已进一步加固：靶向药物商品名摘要使用显式审核顺序与非重叠
  名称匹配，第三部分使用全局 VAF 严格降序；Word 结果表为保证同基因纵向合并，仍使用
  独立的基因分组排序。历史门禁分别固定 41 项商品名和 11 个第三部分章节顺序。
- 最新 iyun129 同款 Linux 隔离候选为 99 页，历史契约、机器 QA、空白/低内容页扫描
  均 `PASS`；候选尚未提交、未部署，生产仍须按实时四项证据确认。
- 精确知识规则保持 panel/癌种/位点边界，治理状态为
  `pending_report_group_reconfirmation`，不得表述为医学终审完成。

---

## 0.1 2026-07-13 CASE-BPI-01 目录页码根治（本地在制）

- 根因：旧目录页码是按 LibreOffice PDF 排版预先写死的纯静态数字，Word/WPS 重排版后必然可能漂移；目录末项小于物理总页数本身则部分正常，因为目录写的是章节起始页，参考文献后仍有质控/方法/公司介绍/封底。
- 修复：`template_renderer.py` 为每个目录项的精确正文标题创建 `_ReportGenToc_*` 专用书签，写入 dirty `PAGEREF` 和缓存页码，设置 `updateFields=true`；不复用曾导致“目录全部变 1”的模板 `_Toc*` 书签。
- 首页锚点：“患者及样本信息”绑定“第一部分：基本信息”，“检测内容”只接受精确标题，不再误绑到第 3 页导读句。
- 分页补漏：“本次检测质控结果”已纳入最终 LibreOffice 刷新前后的精确标题分页清理，消除参考文献后只有页眉/水印的近空白页。
- QA 门禁：`qa_report.py` 现直接校验 PAGEREF/书签 XML；最终件为 14 fields / 14 unique targets / 14 bookmarks，missing/unclosed/duplicate 均 0，`update_fields=true`。
- 最终报告：`.work/lz251578_dynamic_toc_final_20260713/CASE-BPI-01_动态目录页码根治_最终复测.docx`。Panel PASS，QA PASS，视觉渲染 67 页，空白/近空白页 0；同一 DOCX 在 67/78 页的两种排版下，14/14 目录项均与章节页脚一致。
- 内容口径仍为 9 个检出变异、5 个药物相关行（KRAS/FANCA/PMS2/SMARCA4/ATM）；视觉/报告回归 `242 passed`。
- Windows 交付：已通过 SSH 复制到 `[Windowsäº¤ä»è·¯å¾å·²è±æ]`，两端 SHA-256 一致：`6BDA59FA87A94B136A741DA68105B63F271AE56D89A6B0B6461A14BF146FA4AA`。

---

## 二、部署坐标（接手先看这里）

| 项 | 值 |
|---|---|
| 生产主机 | **iyun129**（`ssh iyun129` → `100.84.58.72:12922`，user `iy12922`，Tailscale 内网）|
| 生产 release 根 | `/media/desk16/iy12922/apps/reportgen-web-releases/<短SHA>`；活动版本由 `…/reportgen-web-runtime/current_release` 指向 |
| 运行 | uvicorn `app.main:app` on **:18082**；cloudflared 隧道 `panel-reportgen` → `panel.mailuo-report.com.cn` |
| 运维体系 | `…/apps/reportgen-web-runtime/`：`.env.prod`（含密钥）+ `start_reportgen.sh`（重启用它，带 FAST_TOC）+ `watchdog.sh`（每分钟自愈）+ crontab `@reboot` 自启 |
| 前端 | `backend/static/`（uvicorn 直接 serve）；改前端要 `cd frontend && npm run build` 再把 `dist/` 同步过去 |
| 外部状态/备份 | `…/reportgen-web-storage/`（患者、签名、上传、报告、参考报告）与 `…/reportgen-web-backups/`；不得打进 release |
| ⚠️ 旧机 | 老的 `iyun-server`(218.205.37.74) 已**弃用/关停**，别再找它 |

**状态/切换/回滚**：使用 `scripts/iyun129_release.sh status|switch|rollback`；发布使用
`scripts/iyun129_deploy_clean.sh`。切换后必须断言 current release、完整 `REVISION`、
进程 cwd 和 :18082 health 一致。

---

## 三、本会话线已完成并入 main 的成果（都在 `origin/main` 历史里）

1. **蓝下划线修复**（`c5f6e9b`）：2.1 变异表「未见突变」行基因名不再蓝下划线（行感知）。
2. **性能：报告生成 166s → 58s**（约 65%）。根因=目录页码反复 LibreOffice 导 PDF；开关 `REPORTGEN_FAST_TOC=1` 跳过，已写进 `.env.prod`。
3. **药物护栏 + sheet 锁定 + 知识库缺口补齐**（`e65f228`）：P0 基因（EGFR/KRAS/NRAS/BRAF/NTRK/ERBB2/TP53/TSC1）内部泛化行不再兜底；药物库显式锁 `targeted_drug_tips` sheet；5 个缺口基因补保守解析。
4. **质量门禁做硬**（`d905368` / `904b189` / `16a24b8`）：
   - 认表失败从 SKIP 改 **FAIL**（模板被改坏立即报警，`qa_report.py`）；
   - 金标准基线加 **integrity 维度**（计数/占位符/结构，`test_style_baseline.py`）；
   - **QA=FAIL 报告禁止下载交付**（单份 + 批量逐文件 + zip 打包，返回 409，复核人可 `override_gate=1` 放行）。
5. **上传超时修复**（`e0b5f0f`）：报告组「timeout of 30000ms exceeded」。根因=`/excel/inspect` 同步串行做读表+识别+**患者富集**+预览，marvelbio 富集冷启动最坏 ~24s 顶破前端 30s。修法：前端 axios 超时 **30s→90s**（`client.ts`）+ 后端富集包 **12s 硬超时、超时即跳过不阻断**（`excel.py`）。

---

## 四、⚠️ 悬而未决 / 待办（按优先级）

1. **报告组医学二审**：历史迁移知识和统一排序的显式偏差仍为
   `pending_report_group_reconfirmation`；工程 PASS 不能替代医学签发。
2. **生产发布/回归**：每次只针对一个冻结 SHA；切换后必须复测旧格式 MSI、单份
   生成、批量生成、金标准契约/Diff 和公网下载，不得只看 health=200。
3. **共享审计重跑**：现有 Claude 审计绑定旧冻结基线；新冻结 SHA 需要独立审计者
   重新出具报告，并用 harness `audit_reconcile.py` 对账。旧审计不得自动继承 PASS。
4. **扩大真实 UAT/金标准**：在当前单个历史终版之外，继续按 panel 注册脱敏契约；
   CRC301/358 各不少于 10 份脱敏真实报告，并补充正反例合成病例。
5. **架构长期债**：`template_renderer.py` 仍较大且依赖结构识别；后续按 M6→M9
   增量迁移计划拆分，同时用现有金标准、字段溯源和 panel validation 防回归。

---

## 五、iyun129 安全发布动作

1. 冻结并记录完整 Git SHA；工作树必须干净，PHI/签名/密钥不得进入提交；
2. 备份生产 SQLite、患者 registry、上传、报告、签名和 reference reports；记录
   当前 known-good release；
3. 使用 revision-pinned 历史金标准 manifest 运行 `make release-check`；
4. 使用 `scripts/iyun129_deploy_clean.sh` 构建 immutable release；运行时资产继续外置；
5. 切换后核对 current release、`REVISION`、进程 cwd、进程唯一性、恢复摘要、内外网
   health、单份/批量生成与金标准；任一 P0/P1 失败立即用已记录 release 回滚。

---

## 六、给领导的进展汇报（本会话产出，在 scratchpad）

- `…/scratchpad/进展汇报.xlsx`（4 sheet：项目完成度[双口径 主力线~90%/全规划~65%] + 进展总览 + 系统能力 + 下一步）。已 `/transfer` 传过 Windows。
- 完成度百分比是**工程评估非精确度量**，发领导前须用户认可；总览有 1 处黄底待填（每月报告量/节省工时）。

---

## 七、纪律备忘（本项目反复踩的坑）

- 生产是临床报告系统：改动先勘察→改→**实测双向验证（正常不误伤 + 异常被拦）**→再部署；只加安全网别重写正确逻辑。
- 动生产/hard reset 前先备份、先确认敏感配置；重启后断言进程晚于代码。
- 完成度/数字对领导负责的是用户——评估性数字标注清楚、用户认可才发。
