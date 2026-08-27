# Execution Log

## 2026-08-26 肺癌模板族实施基础与版本对齐

- GitHub `origin/main` 与 iyun129 当前 immutable release 均核对为提交
  `1020e1e659201beb39138dcf40931e2aa44d240d`；生产进程工作目录和 `REVISION`
  一致，本地原 `main` 的未提交内容保持不动。
- 从该精确提交建立独立工作树和分支
  `codex/lung-template-family-foundation-20260826`，新工作与既有脏工作树隔离。
- 新增肺癌资料索要清单校验器；真实 ignored 清单验收为 36 行、36 个唯一样本、
  PD-L1 24 例/非 PD-L1 12 例，并与 487 行历史终版台账交叉核对 `PASS`。
- 建立覆盖全部 10 个已声明模板（含 active/pilot/draft/deprecated）的模板样式基线矩阵。
  源模板指纹只提交布局指标和 SHA-256，不提交段落、表格正文或媒体字节；CRC301/358
  继续保留独立的渲染后 golden style baseline，静态基线不冒充端到端验收。
- 新增六模板肺癌架构总规格，明确“版式族 × PD-L1 变体 × 产品规则包”、评审稿与生产
  发布分层，以及技术老师需要提供的同案 Excel/Word、PD-L1 来源包和 UAT 结论。
- 本地定向回归 `36 passed`：清单校验、10 模板矩阵、CRC301/358 渲染样式基线和
  golden-template pilot 全部通过；受控 Ruff 与 Python 编译通过。6 条 Pillow
  `getdata()` 弃用警告为既有技术债，无功能失败。
- iyun129 当前发布完整 `qa gate` 为 `PASS`：panel/知识/工具链/lint/完整回归、
  CRC358 reference/candidate/repeat diff 和当前输出检查全部通过；生产未重启或切换版本。

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
- S4：小结、2.1 和免疫表使用基因分组 VAF 稳定排序，以保证同基因相邻及 Word
  纵向合并；第三部分改用全局 VAF 严格降序。reviewed overlay 注入后按各自展示契约
  重新排序。历史终版免疫阳性列表的一处旧排序差异已登记为显式偏差。
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
- 合并后精确门禁发现相同 Git tree 的规则/知识哈希受 macOS `._*` AppleDouble
  文件影响。发布哈希现统一排除未随 `git archive` 发布的 Finder 元数据；回归测试
  固定“加入 `._*`/`.DS_Store` 后哈希不得变化”。
- 生产 UAT 暴露遗留 `REPORTGEN_FAST_TOC=1` 会跳过 PAGEREF/缓存页码构建，导致
  HTTP 健康但报告 QA 为 `TOC_PAGE_NUMBERS_MISSING`。运行时已关闭该开关；启动脚本
  现于停止旧进程前阻断 FAST_TOC 及两个同类 skip 开关，防止配置漂移复发。
- 报告组商品名复核发现历史终版靶向药物备注为 41 项，而旧候选仅 22 项。根因是
  18 项映射未迁移，且金模板精简处理器链跳过 `report_content`，导致已有映射的
  1 项仍停留在模板静态旧文本。现已补齐映射并新增关键
  `targeted_drug_brand_summary` 处理器，CRC358/CRC301 金模板均显式声明执行。
- 脱敏历史契约新增 41 项商品名精确顺序断言；旧候选稳定触发
  `TARGETED_DRUG_BRAND_SUMMARY_COUNT/ORDER`，新候选 41/41 通过。iyun129 隔离
  Linux LibreOffice 复测为 99 页、机器 QA `PASS`、0 issue、空白/低内容页 0，
  目录 PAGEREF 有效；生产 `current_release` 未切换，仍为既有版本。
- 商品名修复 Linux 候选 DOCX SHA-256：
  `c4446704b43af7ef73aadc498f19403e7feecfb1ab0f66e9fdd79fac34fd16c4`；QA
  SHA-256：`cfb458e75dcbb883b97b021e2916540a18d35cab233804b27194831e6e9ca670`。
- 本轮相关完整回归 `282 passed`，iyun129 发布契约测试 `14 passed, 1 skipped`；
  模板病例硬编码扫描 HARD 0，新增运行时代码差异未包含病例姓名或样本号。
- 继续复核反馈项 3/6 后确认两项共用一个设计问题：展示契约被隐式绑定到容器/配置
  顺序。商品名摘要原先依赖 YAML 映射插入顺序，且子串扫描会把“替西罗莫司”误判为
  同时命中“西罗莫司”；第三部分则错误复用了仅适合 Word 合并的基因分组排序。
- 商品名配置现显式声明 41 项审核顺序；加载时校验重复项、未知项与空配置，名称匹配
  使用最长优先且不重叠的区间算法。摘要输出不再依赖 YAML 字典顺序。
- 第三部分现有独立的全局 VAF 稳定降序策略；变异表仍保留基因分组策略。历史契约新增
  11 个章节精确顺序及严格单调门禁；旧候选会稳定触发
  `PART3_GENE_SECTION_ORDER/PART3_GENE_SECTION_VAF_ORDER`，防止同类回归再次发布。
- iyun129 同款 Linux LibreOffice 隔离复测候选为 99 页：41/41 商品名、第三部分 VAF
  `22.03 > 20.00 > 17.50 > 14.87 > 13.58 > 1.37 > 1.18 > 1.16 > 1.02 > 1.00 > 0.98`；
  历史契约、机器 QA、全页空白/低内容扫描均 `PASS`，直接 DOCX Diff 为 `WARN`、
  0 个阻断错误。候选 DOCX SHA-256：
  `edb4d45cff0eefbc53e1da03a550bda8f853862a99073bc9d51cb3d479472bc2`；QA SHA-256：
  `a97a12940a5b12ec534157f5009a73e27b7184555ee460fe1826793f59b066fb`。
- 本轮仅在 iyun129 独立 scratch release 中生成和渲染，未切换 `current_release`、未重启
  生产进程，也未提交 Git；报告组医学二审和正式发布仍是后续独立动作。
- 反馈项 3/6 修复后的完整后端回归：`439 passed, 1 skipped`（306.27 秒）；116 条
  `datetime.utcnow()` 弃用警告均为既有技术债，无功能失败。变更集中回归另为
  `281 passed`，脱敏历史契约 registry `PASS`。
