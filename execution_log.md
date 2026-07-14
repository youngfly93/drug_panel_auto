# Execution Log

## 2026-07-14 CRC358 历史金标准与批量生成加固

- 建立执行 Spec：`docs/spec_crc358_historical_golden_batch_hardening.md`。
- 基线：`4545e0b`；生产核查版本：`7c04472`。
- 隐私边界：真实病例 Excel/DOCX 与签名只保留在 ignored/runtime 路径，不提交 Git。
- 当前阶段：S1 批量任务生命周期与 MSI。
- S1：新增运行时进程互斥锁；应用取得锁后才访问 SQLite/恢复任务，运维状态暴露锁状态。
- S1：iyun129 发布配置显式启用互斥锁；启动脚本在候选进程启动前完整终止旧 uvicorn。
- S2：新增脱敏金标准契约 `crc358_reviewed_case_a`，记录历史 DOCX 哈希、关键表行、Part 3 条目数与位点级正文哈希。
- S2：新增通用运行时参考报告注册工具和契约校验工具；真实 DOCX 继续外置。
- S3：迁移 TP53 Q167*、FLT3 G846D、ATR R431Gfs*8、KRAS G12C 的
  CRC358 panel/癌种/位点级规则；同基因非目标位点不继承这些精确规则。
- S3：新增 reviewed Part 3 overlay，固定 11 个基因解释和 18 个药物解析，
  治理状态为 `legacy_runtime + pending_report_group_reconfirmation`，保留报告组二审权。
- S4：小结、2.1、免疫表和第三部分复用基因分组 VAF 稳定排序；reviewed
  overlay 注入后再次排序。历史终版免疫阳性列表的一处旧排序差异已登记为显式偏差。
- S5：动态变异表与 NCCN 结果表按相邻同基因执行 OOXML 纵向合并；称呼由性别
  生成；签名从外部 runtime registry 解析并由部署 preflight 校验，真实签名未入 Git。
- S5：签名说明块与签名作为一个分页语义块处理，Linux LibreOffice 复测未出现
  签名独页、空白页或孤行标题。
- S6：新增脱敏历史契约门禁和外部 reference/candidate Diff 门禁，输出 reference/
  candidate SHA、QA/Diff 状态、规则/知识哈希及渲染引擎指纹。
- Linux 候选实测：99 页；29 个表；小结 7 行；第三部分 11 个基因解释、18 个
  药物解析；变异表/NCCN 表 `w:vMerge` 数为 8/25；两枚签名；视觉 QA `PASS`，0 issue。
- 候选 DOCX SHA-256：`0aa25db517ca292856377901ef480f409248bc6e12e9d6348a41bad466ce088a`；
  QA SHA-256：`f14e0e5eb7a4cc84d1f526afd316c4ce3aa9db110a4fd148b99afa11c626ce78`。
- 历史契约校验 `PASS`；历史全文 Diff 为 `WARN`、0 个阻断错误，警告包含已登记的
  免疫阳性 VAF 排序纠正及渲染/样式差异，仍待报告组二审确认。
- 完整后端回归：`428 passed, 1 skipped`（297.24 秒）；116 条均为既有
  `datetime.utcnow()` 弃用警告，无功能失败。
- 变更相关复测：`29 passed, 1 skipped`；脱敏契约 registry `PASS`；签名注册表
  preflight `PASS`；Python 编译与 6 个发布 Shell 脚本语法检查 `PASS`。
- 发布静态 QA：panel validation、knowledge release gate、受控 ruff lint 均 `PASS`。
- 前端 production build：`vue-tsc --noEmit` + Vite build `PASS`；大 chunk 为既有性能警告。
- 模板患者硬编码扫描：HARD 0；SOFT 仅 1 条文献发布日期，经人工核对不是病例数据。
- GitHub Linux 首轮门禁暴露样式回归依赖本机外置签名：本机有真实 runtime 资产时
  为 2 张签名，干净 CI 为 0 张。测试现于隔离的临时 storage 创建确定性伪签名，
  不再读取真实签名或依赖机器状态；CRC358/CRC301 样式基线定向复测 `2 passed`。
