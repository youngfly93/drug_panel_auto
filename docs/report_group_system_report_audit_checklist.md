# 报告组系统与报告审核清单

> 版本：1.1（2026-07-14）
> 适用范围：CRC301+MSI、CRC358+MSI 及 iyun129 Web 生产链路
> 性质：可重复执行的审核协议，不是任何版本的 PASS 结论

## 1. 使用规则

1. 每次审核只针对一个已提交的冻结 SHA，不审变化中的工作树。
2. “冻结候选”和“iyun129 实际运行版”必须分开记录；两者 SHA 不同时，生产实测不得代替候选版验证。
3. 规范真源为本文档；每次执行结果写入 `audit/report-group-system-uat.<agent>.md`，不将当次状态回写为本清单的永久结论。
4. 证据使用脱敏病例代号（如 `UAT358-01`）、文件 SHA256、程序输出和 `文件:行`指针；不在 Git/审核文档中写患者姓名、真实样本号、本机用户路径或报告原文。
5. 审核时先记录事实，再下结论；无证据不得标记 PASS，“未执行”不得写成“未发现问题”。

### 1.1 每次运行记录头

```yaml
---
module: report-group-system-uat
agent: codex
audited_commit: <full SHA>
candidate_kb_hash: <hash>
environment: iyun129-production | local-candidate | staging
deployed_release: <active process cwd/release id>
renderer_fingerprint: <os + soffice version + locale/font profile>
checklist_version: "1.1"
run_id: <YYYYMMDD_shortsha_environment>
started_at: <ISO-8601>
completed_at: <ISO-8601 or null>
overall_engineering_status: NOT_RUN | PASS | FAIL | BLOCKED
overall_medical_status: NOT_RUN | READY | BLOCKED
---
```

### 1.2 单项记录格式

| id | status | severity | observed | expected | evidence | defect_id | retest |
|---|---|---|---|---|---|---|---|
| RG-XXX | PASS/FAIL/BLOCKED/NA | P0-P3 | 实测事实 | 验收标准 | 路径:line / SHA / JSON 字段 | 稳定 ID | NOT_RUN/PASS/FAIL |

## 2. 严重度与停止条件

| 级别 | 定义 | 处置 |
|---|---|---|
| P0 | 串病例、必检结果错误/丢失、关键变异漏报、药物方向相反、PII 进入 Git/对外流出 | 立即判定医学与发布失败；保留证据后停止交付 |
| P1 | 重要内容缺失、证据/癌种/位点越权、候选与运行版不一致、高风险未审知识可正式交付 | 阻断对应版本放行，可继续低风险诊断 |
| P2 | 非关键完整性、可追溯性、版式或 UAT 覆盖缺口 | 记录并限期修复；若遮挡/改变内容则升为 P1 |
| P3 | 表达、可用性、文档优化 | 不阻断，纳入改进清单 |

任一 P0 直接阻断全版本医学交付。任一未闭环 P1 不得宣称“生产就绪”。人工 override 必须有操作人、原因、时间和被放行对象，不得无痕放行。

## 3. 执行顺序

```text
A. 冻结对象与 PII
→ B. iyun129 运行真相
→ C. 候选版本工程门禁
→ D. Web 主链路
→ E. 输入/结果映射
→ F. 药物与知识规则
→ G. 报告内容一致性
→ H. Word 视觉与跨引擎
→ I. 交付门禁与审计留痕
→ J. 脱敏真实病例 UAT
→ K. 签发与发布结论
```

## 4. A — 冻结对象与数据安全

| ID | 核查项 | PASS 标准 | 必备证据 |
|---|---|---|---|
| RG-A01 | 冻结 SHA | 为已提交 commit，记录 full SHA | `git rev-parse HEAD` |
| RG-A02 | 工作树 | 候选树干净；审核文件与临时产物不混入业务树 | `git status --short --branch` |
| RG-A03 | 候选变更范围 | 与上一生产 SHA 的文件和统计已记录 | `git diff --stat <prod>..<candidate>` |
| RG-A04 | PII 扫描 | staged/commit diff、已跟踪源码/测试/fixture、commit message、审核文档均无真实姓名/样本号/路径/签名；历史疑似值已完成人工定性与处置决策 | `git grep`/专用扫描器、diff/history 检索范围、0 命中或处置记录 |
| RG-A05 | 病例产物隔离 | Excel/DOCX/PDF/截图仅在受限存储或 `.work/`，不在 Git | `git ls-files` + ignore 证据 |
| RG-A06 | 知识锚点 | manifest、registry、Panel rules 哈希可重算 | 文件清单、顺序和 SHA256 |
| RG-A07 | 审核记录安全 | 只用脱敏代号，不复述被发现的 PII 值 | 审核文档 PII 扫描 |

## 5. B — iyun129 运行真相

| ID | 核查项 | PASS 标准 | 必备证据 |
|---|---|---|---|
| RG-B01 | 真实进程 | `:18082` 只有预期 uvicorn 进程 | PID、启动时间、cmdline |
| RG-B02 | 运行目录 | `/proc/<pid>/cwd` 指向明确 release | cwd + release ID |
| RG-B03 | 版本单一真相 | `current_release`、进程 cwd、REVISION、部署记录一致 | 四者对照表 |
| RG-B04 | 代码完整性 | 运行 release 关键文件哈希与该 SHA 一致 | renderer/rules/gate/frontend 哈希 |
| RG-B05 | 启动时序 | 进程启动时间晚于被加载代码的 mtime | 进程与文件时间 |
| RG-B06 | 前端资产 | HTML 引用的 JS/CSS 与该 release 构建一致，无旧缓存入口 | asset 名、hash、HTTP 头 |
| RG-B07 | 健康与隧道 | 本机 API 与公网域名均返回预期状态 | HTTP status + 时间 |
| RG-B08 | 运行目录隔离 | storage/logs/run/tmp/venv 不进 Git release | 目录与 ignore 检查 |
| RG-B09 | 回滚点 | 存在已知可用的回滚 release；使用 iyun129 release 工具可唯一定位，且切换失败不会提前改写 `current_release` | release ID + `iyun129_release.sh status/rollback` 记录 |

## 6. C — 冻结候选工程门禁

| ID | 核查项 | PASS 标准 | 必备证据 |
|---|---|---|---|
| RG-C01 | Panel 包校验 | CRC301/358 均 0 error，默认模板 active | 校验 JSON/终端输出 |
| RG-C02 | 回归测试 | 相关单测/回归全部通过 | pytest 命令、数量、时长 |
| RG-C03 | 知识工程门禁 | manifest、provenance、引用、重复 selector、内容完整性 PASS | `knowledge_release_gate.json` + SHA |
| RG-C04 | 医学就绪状态 | 必须单独显示 READY/BLOCKED，不被顶层工程 PASS 掩盖 | gate JSON 指定字段 |
| RG-C05 | Golden CRC358 | 在生产等价 Linux LibreOffice 环境生成并渲染成功，QA/visual PASS，无空白页 | DOCX/QA SHA + 页数 + renderer fingerprint |
| RG-C06 | Golden CRC301 | 同上 | DOCX/QA SHA + 页数 + renderer fingerprint |
| RG-C07 | 双病例防硬编码 | 两个不同合成病例无字段/药物/变异串入 | 差异报告 + 禁用 token 扫描 |
| RG-C08 | Web smoke | 上传→识别→预览→生成→QA→下载通路 | smoke 日志 |

## 7. D — Web 操作与权限

| ID | 核查项 | PASS 标准 |
|---|---|---|
| RG-D01 | 登录与会话 | 未登录拒绝，有效用户正常，超时/退出失效 |
| RG-D02 | 角色权限 | 普通用户不能编辑系统配置/越权查看 |
| RG-D03 | Excel 上传 | 合法文件成功；类型/大小/空文件异常可理解 |
| RG-D04 | Sheet 预览 | 页数、行列数与输入一致，无跨任务混数据 |
| RG-D05 | 动态临床表单 | required/只读/默认/覆盖顺序正确 |
| RG-D06 | 异步生成 | 状态、进度、失败原因和重试正确，无假完成 |
| RG-D07 | 任务隔离 | 并发任务不串临床信息、输入或输出 |
| RG-D08 | 知识页面 | 显示基础库 + reviewed overlay + 来源 + 审核/二审状态 |

## 8. E — 输入契约与结果映射

| ID | 核查项 | PASS 标准 |
|---|---|---|
| RG-E01 | Panel 识别 | CRC301/358 分别正确；模糊/未知输入不自信误判 |
| RG-E02 | 必需 Sheet/列 | 缺失时明确 FAIL，不静默回退 |
| RG-E03 | MSI 别名 | `Msisensor` 大小写/空格别名与列重排均能读取 |
| RG-E04 | MSI 缺失/无法解析 | CRC301/358 必须阻断，不写“未检测” |
| RG-E05 | TMB | 值、单位、阈值、分组和正文一致 |
| RG-E06 | 变异映射 | gene/transcript/c./p./VAF/类型/分级与原始输入逐行相符 |
| RG-E07 | Panel 范围 | Panel 内按规则纳入，Panel 外变异不泊入 |
| RG-E08 | CNV/融合/HLA | 有数据时展示、无数据时不伪造结果，且符合 Panel 支持范围 |
| RG-E09 | 字段来源优先级 | Excel/表单/计算字段冲突时按契约取值，且 provenance 可见 |

## 9. F — 药物规则与知识治理

| ID | 核查项 | PASS 标准 |
|---|---|---|
| RG-F01 | 药物表纳入范围 | 只展示命中合格用药规则的变异，不把所有检出变异填成空药物行 |
| RG-F02 | 分级边界 | 纳入的 Ⅰ/Ⅱ/Ⅲ 类范围与报告组确认的契约一致 |
| RG-F03 | 获益/耐药方向 | 方向、药物名、证据等级正确，无反向映射 |
| RG-F04 | 癌种边界 | 跨癌种证据有明确标识，不伪装为 CRC 独立疗效 |
| RG-F05 | 位点/事件边界 | gene-level 不越权到任意位点；LoF/热点/CNV/融合条件精确 |
| RG-F06 | FANCA 正例 | Ⅱ类 LoF 只在获批契约内命中，显示限定性跨癌种提示 |
| RG-F07 | FANCA 反例 | 普通错义及 Ⅲ类 LoF 不命中该用药结论 |
| RG-F08 | BARD1/RNF43 反例 | 无 reviewed selector 时不由泛 HRR 列表推导 PARP 获益 |
| RG-F09 | 全量展示 | CRC 匹配行的 >5 个药物全量展示，无“另 X 项”，无 Word 裁切 |
| RG-F10 | 过滤可解释 | 每个未进报告的候选有确定原因（无位点/癌种不符/低证据/安全排除） |
| RG-F11 | 知识分层 | 基础库、Panel overlay、动态药物库的来源层与优先级可追溯 |
| RG-F12 | 引用可解析 | 运行中 PMID/试验号均有结构化记录，无悬空引用 |
| RG-F13 | 审核状态 | review status、reviewer type、evidence as-of、secondary status 与 runtime 行为一致 |
| RG-F14 | 高风险 provisional | 可生成/预览/UAT；未二审时不得无痕正式交付 |
| RG-F15 | 覆盖率表述 | 分开运行覆盖、特异解释、来源、二审和位点级覆盖，不用单一 100% 宣称医学完成 |

## 10. G — 报告内容与跨章节一致性

| ID | 核查项 | PASS 标准 |
|---|---|---|
| RG-G01 | 患者/样本字段 | 与当次脱敏输入一致，无其他病例残留 |
| RG-G02 | 变异总数 | 小结、变异明细、第三部分和 QA 数量相符 |
| RG-G03 | 药物相关数 | 小结数、药物表行和第三部分用药解析相符 |
| RG-G04 | MSI/TMB | 结果表、小结、正文、用药提示一致 |
| RG-G05 | 同一变异表达 | transcript/c./p./分级在各章节一致 |
| RG-G06 | 证据等级 | 表格、正文、参考文献的等级和范围一致 |
| RG-G07 | 参考文献边界 | 正文引用均可在文献段找到，无无引用的药物结论 |
| RG-G08 | 无结果分支 | 无变异/无药物命中时使用获批措辞，不留空表/模板句 |

## 11. H — Word 视觉、分页与跨引擎

| ID | 核查项 | PASS 标准 |
|---|---|---|
| RG-H01 | DOCX 可打开 | Word/WPS/LibreOffice 无修复警告，无未渲染占位符 |
| RG-H02 | 空白/近空白页 | 非设计空白页为 0 |
| RG-H03 | 孤行标题 | 标题与首段/首表行同页，无动态基因标题孤立页尾 |
| RG-H04 | 表格分页 | 表头重复、行不被意外裁切，长药物列可见 |
| RG-H05 | 编号层级 | `1.` / `2.` / `2.1` 等层级符合金标准，无 `[1]`/重号 |
| RG-H06 | 签名与日期 | 签名块不拆页，名称/日期/免责声明位置正确 |
| RG-H07 | 尾页结构 | 质控→公司介绍+二维码→封底，二维码不漂移 |
| RG-H08 | 目录 | 每个目录项对应唯一专用书签，PAGEREF 可更新，页码与当前引擎分页一致 |
| RG-H09 | 跨引擎比对 | 同一 DOCX 先在与生产同款 Linux LibreOffice 渲染，再由 Windows Word/WPS 检查目录、表格、签名、页眉页脚；Mac LibreOffice 结果不得替代生产等价渲染 |
| RG-H10 | 视觉证据 | 保存 DOCX/渲染产物哈希、页数、空白页检测、高风险页截图哈希，并记录 OS、LibreOffice/Word/WPS 精确版本、渲染命令、locale 与字体环境；不保存真实 PII 截图到 Git |

## 12. I — 交付门禁和审计留痕

| ID | 核查项 | PASS 标准 |
|---|---|---|
| RG-I01 | QA FAIL 单份下载 | 返回 409，不直接下载 |
| RG-I02 | QA FAIL 批量/单文件 | 批量 ZIP 和逐文件下载无旁路 |
| RG-I03 | 高风险 provisional | 报告可生成/预览，未二审时正式交付被拦 |
| RG-I04 | override 权限 | 只授权角色可放行，不得通过普通参数绕过 |
| RG-I05 | override 留痕 | 必填操作人、原因、时间、知识条目/报告 ID；审计日志无 PII 原文 |
| RG-I06 | 二审后放行 | 审核状态改为允许后，同一报告无需风险 override 即可交付 |
| RG-I07 | 旧历史报告 | 旧任务缺少新字段时行为有明确政策，不静默放宽高风险结果 |

## 13. J1 — 合成边界病例矩阵

| Case ID | Panel | 覆盖场景 | 核心断言 |
|---|---|---|---|
| SYN-358-01 | CRC358 | MSS 基线 | 主链路、MSI/TMB、默认版式 PASS |
| SYN-301-01 | CRC301 | MSS 基线 | 同上，且 Panel 范围正确 |
| SYN-MSI-01 | CRC358 | MSI-H | 结果表/小结/正文/免疫提示一致 |
| SYN-MSI-02 | CRC358 | MSI sheet 别名+列重排 | 语义解析正确 |
| SYN-MSI-03 | CRC301/358 | MSI 缺失/无法解析 | 生成被阻断 |
| SYN-FANCA-01 | CRC358 | FANCA Ⅱ类 LoF | 只命中限定性提示，未二审交付被拦 |
| SYN-FANCA-02 | CRC358 | FANCA Ⅱ类错义 | 不命中 FANCA 用药 |
| SYN-FANCA-03 | CRC358 | FANCA Ⅲ类 LoF | 不命中 FANCA 用药 |
| SYN-DRUG-01 | CRC301/358 | 0 个药物命中 | 无空药物行/空解析 |
| SYN-DRUG-02 | CRC301/358 | >5 个药物/长文本 | 全量展示、无裁切/孤页 |
| SYN-MULTI-01 | CRC358 | Ⅰ/Ⅱ/Ⅲ类+获益/耐药混合 | 分类、方向、数量一致 |
| SYN-ISO-01 | CRC301/358 | 两病例交叉生成 | 临床字段、变异、药物、签名无串入 |

## 14. J2 — 脱敏真实报告 UAT

每个生产 Panel 至少 10 份；只在受限环境内使用真实输入，审核文档仅写代号和哈希。

| UAT ID | Panel | 覆盖标签 | input SHA | 报告 QA | 人工结论 | 缺陷 ID | 复测 |
|---|---|---|---|---|---|---|---|
| UAT301-01 | CRC301 | 待分层选样 |  |  |  |  |  |
| UAT301-02 | CRC301 | 待分层选样 |  |  |  |  |  |
| UAT301-03 | CRC301 | 待分层选样 |  |  |  |  |  |
| UAT301-04 | CRC301 | 待分层选样 |  |  |  |  |  |
| UAT301-05 | CRC301 | 待分层选样 |  |  |  |  |  |
| UAT301-06 | CRC301 | 待分层选样 |  |  |  |  |  |
| UAT301-07 | CRC301 | 待分层选样 |  |  |  |  |  |
| UAT301-08 | CRC301 | 待分层选样 |  |  |  |  |  |
| UAT301-09 | CRC301 | 待分层选样 |  |  |  |  |  |
| UAT301-10 | CRC301 | 待分层选样 |  |  |  |  |  |
| UAT358-01 | CRC358 | 待分层选样 |  |  |  |  |  |
| UAT358-02 | CRC358 | 待分层选样 |  |  |  |  |  |
| UAT358-03 | CRC358 | 待分层选样 |  |  |  |  |  |
| UAT358-04 | CRC358 | 待分层选样 |  |  |  |  |  |
| UAT358-05 | CRC358 | 待分层选样 |  |  |  |  |  |
| UAT358-06 | CRC358 | 待分层选样 |  |  |  |  |  |
| UAT358-07 | CRC358 | 待分层选样 |  |  |  |  |  |
| UAT358-08 | CRC358 | 待分层选样 |  |  |  |  |  |
| UAT358-09 | CRC358 | 待分层选样 |  |  |  |  |  |
| UAT358-10 | CRC358 | 待分层选样 |  |  |  |  |  |

真实 UAT 样本集合至少覆盖：MSS/MSI-H、0/1/多药物命中、Ⅰ/Ⅱ/Ⅲ类、SNV/indel/LoF/CNV/融合（若 Panel 支持）、获益/耐药、长报告分页、FANCA 正反例、两病例交叉防串入。

## 15. 已知缺陷回归映射

| 历史问题 | 必过清单项 |
|---|---|
| BPI-001 FANCA 用药 | RG-F05–F08、RG-I03–I06、SYN-FANCA-01–03 |
| BPI-002 MSI 静默“未检测” | RG-E03–E05、RG-G04、SYN-MSI-01–03 |
| BPI-003 药物全量展示 | RG-F09、RG-H04、SYN-DRUG-02 |
| BPI-004 编号 | RG-H05 |
| BPI-005 空白页/孤行标题 | RG-H02–H04 |
| BPI-006 签名分页 | RG-H06 |
| BPI-007 二维码/尾页 | RG-H07 |
| BPI-008 病例对照错位 | RG-A07、RG-G01–G03 |
| BPI-009 目录页码 | RG-H08–H09 |
| GATE-01 工程 PASS/医学 BLOCKED 混淆 | RG-C03–C04、RG-F15 |
| GATE-02 生产多版本标识 | RG-B01–B05 |
| BPI-KB-01 高风险 provisional 可无痕交付 | RG-F13–F14、RG-I03–I06、SYN-FANCA-01 |
| BPI-KB-02 测试/历史疑似真实样本号 | RG-A04–A05、RG-A07 |
| QA-409 交付拦截 | RG-I01–I07 |

## 16. K — 最终放行条件

### 16.1 工程发布 PASS

- RG-A01–RG-I07 的所有适用项完成，无未关闭 P0/P1。
- CRC301/358 Panel 校验、相关测试、知识门禁、Golden、Web smoke 全部通过。
- iyun129 实际运行 release 与被放行 SHA/文件哈希一致。
- 生产回滚点和部署记录完整。

### 16.2 医学交付 READY

- 二审状态和本次报告使用的知识条目相符。
- CRC301/358 各至少 10 份脱敏真实 UAT，总通过率 ≥90%。
- P0=0；任一串病例、必检结果错误、关键变异漏报、药物方向错误均直接判全版本不通过。
- `bug_pic1` 所有历史问题通过对应的脱敏/合成回归项。
- 报告组记录版本级结论：通过 / 有条件通过 / 不通过，并签署未关闭条件。

## 17. 首轮 iyun129 执行建议

1. 先执行 RG-A01–A07 和 RG-B01–B09，只读核清冻结 SHA、当前生产 release 和版本标识；生产状态使用 `bash scripts/iyun129_release.sh status`，不读取遗留 `/opt`/systemd 坐标。
2. 在冻结候选上执行 RG-C01–C08；候选未部署时，不把生产旧版结果代入。
3. 使用合成病例过 RG-D–I 和第 13 节矩阵，不先触碰真实病例。
4. 工程门禁和交付拦截正确后，再由报告组进行第 14 节真实 UAT。
5. 每发现一个缺陷，分配稳定 ID；修复后重新执行原项 + 相关反例，不仅验证“正例恢复”。
