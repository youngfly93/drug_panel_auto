# iyun62 ReportGen Production SOP

适用范围：`https://panel.mailuo-report.com.cn`，生产主机 `iyun-server`
上的 ReportGen Web。当前阶段暂不引入登录系统，所有上传、生成、下载、
交付确认都按内部生产环境处理。

## 1. 基本原则

- 生产部署只从干净 `main` commit 发布，禁止直接在服务器脏 worktree 改代码。
- Excel、DOCX、ZIP、审计日志、备份只保存在服务器运行目录，不进入 Git。
- 报告可视化摘要只用于快速判断，交付前仍以 Word 报告和 QA 信息为准。
- `status=draft` 的 panel 只能试用和人工复核，不能按全自动成品交付。
- 生产异常先保护数据和可回滚性，再处理体验问题。

## 2. 每日开工检查

报告组开始批量生成前，值守同事检查：

```bash
curl -s https://panel.mailuo-report.com.cn/api/v1/tasks/stats
ssh iyun-server 'tail -n 80 /media/desk16/iyun6208/apps/reportgen-web-runtime/logs/watchdog.log'
ssh iyun-server 'tail -n 80 /media/desk16/iyun6208/apps/reportgen-web-runtime/logs/alerts.log'
ssh iyun-server 'ls -1t /media/desk16/iyun6208/apps/reportgen-web-backups/reportgen-web-backup-*.tar.gz | head -1'
```

通过标准：

- 公开 API 返回 HTTP 200；
- watchdog 没有连续重启失败；
- 告警群没有未处理的 `danger`；
- 最近一次备份时间不超过 30 小时。

## 3. 报告生成流程

1. 报告组上传 Excel，确认系统自动识别的项目类型和模板正确。
2. 查看上传后自动带出的报告摘要、QA 提示和草稿护栏。
3. 若为批量任务，等待任务进度完成；失败项先重试一次，再升级给开发值守。
4. 下载 DOCX、QA 文件或批量 ZIP；前端显示下载进度，慢下载优先等待自动重试。
5. 交付前打开 Word 检查关键页：抬头、检测结果表、药物提示、Part 3 解析、签名/页眉页脚。
6. 通过后在系统中标记复核或交付状态，审计日志会记录生成、下载、复核/交付动作。

## 4. 交付闸口

报告可以交付必须同时满足：

- 任务状态成功；
- QA 无阻断项；
- panel 不是 `draft`，或已由报告负责人明确签收人工修改内容；
- Word 关键页人工核对无错版、空页、错表格、错病人信息；
- 下载文件大小合理，能在本地正常打开。

遇到以下情况不能直接交付：

- 摘要显示“草稿/需人工复核/勿直接交付”；
- Word 中出现模板源病例信息、异常蓝色下划线、小方块、表格断裂；
- 下载失败、ZIP 缺文件、QA 文件缺失；
- Excel 来源或检测项目类型不确定。

## 5. 告警处理

企业微信告警由 `/media/desk16/iyun6208/apps/reportgen-web-runtime/alerts.sh`
每 5 分钟读取本机 sanitized ops endpoint 后发送。告警内容不包含患者字段、
Excel 文件名、报告文件名、IP、UA 或服务器完整路径。

常见告警处理：

- `disk`：先暂停大批量生成，确认 `storage/reports` 和备份目录占用，必要时先做备份再清理。
- `backup`：立即手工运行一次备份并验证。
- `queue`：检查是否有卡住任务，必要时重启 uvicorn 后重试失败任务。
- `downloads.slow`：先看是否只是单次大 ZIP；连续出现时运行下载诊断脚本。
- `libreoffice`：检查 listener 是否缺失，重启运行脚本或服务。

手工检查：

```bash
ssh iyun-server 'DRY_RUN=1 /media/desk16/iyun6208/apps/reportgen-web-runtime/alerts.sh check'
ssh iyun-server 'tail -n 120 /media/desk16/iyun6208/apps/reportgen-web-runtime/logs/alerts.log'
```

## 6. 备份与恢复

自动维护任务每天 02:17 运行，默认策略：

- Excel 上传保留 30 天；
- DOCX/任务报告目录保留 180 天；
- 可再生 ZIP 保留 14 天；
- 审计日志保留 365 天；
- 备份包保留 30 天；
- 运行日志保留 14 天；
- 预览文件保留 7 天；
- clean release 保留当前版本和最近 8 个旧版本。

手工备份：

```bash
ssh iyun-server '/media/desk16/iyun6208/apps/reportgen-web-runtime/backup.sh backup'
```

每月至少做一次非破坏性恢复演练：

```bash
ssh iyun-server '/media/desk16/iyun6208/apps/reportgen-web-runtime/restore_drill.sh'
```

演练通过标准：

- 备份包 SHA-256 校验通过；
- `tar -tzf` 完整归档可读；
- 能解出 `meta/manifest.pre.json` 和 `db/reportgen_web.sqlite`；
- SQLite `PRAGMA integrity_check` 返回 `ok`；
- 生成 `logs/restore-drill-YYYYmmdd_HHMMSS.json` 演练记录；
- 默认演练不修改生产 storage，不保留解出的 DB。

季度或重大版本发布前，可在磁盘充足的隔离环境做全量解压演练：

```bash
ssh iyun-server 'RESTORE_DRILL_FULL=1 /media/desk16/iyun6208/apps/reportgen-web-runtime/restore_drill.sh'
```

## 7. 发布与回滚

发布前本地要求：

- 当前 worktree 干净；
- 关键后端回归和前端 build 通过；
- 变更已 commit，并推送到 `origin/main`；
- 若涉及报告模板，至少有 golden case 或真实样本签收记录。

发布：

```bash
DEPLOY_REF=$(git rev-parse HEAD) bash scripts/iyun62_deploy_clean.sh
```

回滚：

```bash
DEPLOY_REF=<known_good_commit> bash scripts/iyun62_deploy_clean.sh
```

发布后必须验证：

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://panel.mailuo-report.com.cn/api/v1/tasks/stats
ssh iyun-server 'cat /media/desk16/iyun6208/apps/reportgen-web-runtime/current_release'
```

## 8. 常见故障分流

- 网站打不开：先看 Cloudflare tunnel 和本地 `127.0.0.1:8000` API。
- 生成失败：看任务错误、Excel 是否缺 sheet/列、LibreOffice 是否存在。
- 下载慢：让前端自动重试；同时运行 `scripts/iyun62_download_diagnostics.sh` 查服务端耗时。
- Word 格式异常：保留任务 ID、Excel、生成时间和截图，先暂停同模板批量交付。
- 备份失败：先不要清理旧备份，手工运行 backup 并把日志贴给开发值守。

## 9. 每周复盘

每周固定检查：

- 最近 7 天生成成功率、失败原因和重试次数；
- 最近 7 天慢下载/失败下载次数；
- 最近一次恢复演练时间；
- 磁盘增长趋势；
- 草稿 panel 的人工修改点是否可以沉淀为自动规则。
