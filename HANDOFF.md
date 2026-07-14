# HANDOFF —— 基因组 Panel 自动化报告系统（Web 平台）

> 当前状态快照。更新就改这个文件，别新建 `_v2`。
> 最近更新：**2026-07-14**（CRC358 历史金标准、批量生命周期与发布门禁加固）。

---

## 一、一句话现状

结直肠癌 358/301 报告线由 iyun129 的 immutable release 体系提供服务。CRC358
历史终版迁移、批量生命周期、MSI 回归、统一筛选排序、Word 资源链路及历史 Diff
发布门禁已形成工程发布候选；生产是否已切换必须以 `current_release`、`REVISION`、
进程 cwd 和健康检查四项实时证据为准，不能由本文档静态推断。

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
