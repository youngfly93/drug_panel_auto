# 肺癌报告组反馈修复规格（2026-08-09）

## 1. 范围与身份

- 基线提交：`fad5c87`
- 候选分支：`codex/lung-feedback-20260809`
- 冻结工程提交：`e79177872c9dfde21e0fc35b373143023e4fb241`
- 覆盖 Panel：`lung_329_pdl1`、`lung_588_pdl1`
- 本文记录候选内容与验收口径；冻结 SHA 由独立审计及 Linux receipt/QA
  双重绑定，生产实际运行身份仍只能由 iyun129 release/REVISION/进程/health
  实时证据确认。
- 真实输入只在 `.work/` 中以 `CASE-LUNG-A/B/C` 处理，不进入 Git。

## 2. 反馈到根因与修复的映射

| 反馈 | 根因 | 修复与验收 |
|---|---|---|
| 网页显示“药物相关 0、靶向提示 0” | 肺癌规则此前整体失败关闭；历史候选没有经过癌种、转录本、HGVS 与治疗上下文边界后进入运行规则 | 仅启用 BRAF `NM_004333.6/c.1799T>A/p.V600E` 与 ERBB2 `NM_004448.4/c.1979G>A/p.G660D` 两个精确事件；必须满足 NSCLC、疾病范围、既往治疗和伴随诊断条件。上下文缺失时仍生成草稿，但精确规则不命中。CASE-LUNG-C 网页摘要为药物相关 2、靶向 2。 |
| 免疫正/负相关均显示“未检出” | 肺癌 588 未关联任何运行时免疫事件；直接接通基因级公共库会造成任意位点继承 | `lung_588_pdl1` 只接入历史终版中已出现的 7 个“转录本 + c./p.HGVS + I/II 类”精确事件；CASE-LUNG-B 正相关 5，CASE-LUNG-C 正相关 2、负相关 1。`lung_329_pdl1` 只暂存候选，模块继续禁用。 |
| 化疗提示显示 0，容易被理解为“检测结果为零” | 模块禁用状态被前端压成数字 | 后端输出独立模块状态，前端显示“未启用（待医学审核）”，不再把未建设模块伪装成 0 条结果。 |
| 报告组在审核前看不到 Word | 下载动作错误依赖“已审核”，形成必须先审核、后查看报告的循环门禁 | 肺癌生成完成后进入任务详情；未审核时顶部按钮显示“下载报告草稿”且可下载。审核状态继续记录正式复核/交付过程，但不阻止报告组取得待审 Word。 |
| 首次下载即提示“已重试 3 次” | 错误文案使用配置的最大重试次数，而不是实际尝试次数 | 下载错误携带真实 attempt；首次 409 不追加重试文案，只有确实发生断点续传时才显示“共尝试 N 次”。 |
| PD-L1 表单字段过多 | 把内部溯源字段直接暴露给报告组填写，并把可后补信息设为生成前必填 | 页面只展示 TPS、CPS、结果判定、病例图片及独立的靶向用药上下文，且全部改为可选。填写后仍执行范围/词表/来源校验；未填写时生成带 WARN 的待审草稿。 |
| PD-L1 Word 下方说明过多、缺少上传图片 | 模板保留历史方法/来源说明，且没有病例图片处理器 | 两套肺癌模板均只保留 TPS/CPS/结果表、病例图片与图注，之后直接进入 MSI；有图片时嵌入受控病例图，无图片时在原位置显示“待补”草稿提示。 |

## 2.1 后续 P1 工程审计修复

| P1 | 修复 | 失败关闭与兼容边界 |
|---|---|---|
| 显式肺癌 Panel 在公共 KB 不可用时仍回退基因级 `CtDrug` | 显式 Panel 无论 base DB 是否可用都先执行 Panel 精确规则；`CtDrug` 只保留给无 Panel 的旧调用 | BRAF V600E 精确规则在 KB 缺失时仍命中；BRAF D594G 等未审核事件不再继承基因级药物；旧无 Panel 排序/回退回归继续 PASS |
| `required_tables` / `required_columns` 只声明不执行，且精确选择器列未入契约 | 新增中央结构校验器，Web 在任务创建前阻断，`ReportGenerator.generate()` 对直接/CLI 调用再次阻断；两套肺癌契约增加 `Transcript` 与 `pHGVS_S/pHGVS_A` 任一列 | 缺 Variations/TMB/Msisensor、缺 Transcript、两种蛋白 HGVS 均缺时 FAIL；空 Variations 只要表头完整仍可通过；失败载荷只含配置的表/列名，不含病例值或文件名 |

## 3. PD-L1 图片安全合同

1. 上传接口要求登录，仅接受 PNG/JPG/JPEG/WEBP。
2. 服务端解码后重新编码为 PNG，去除 EXIF 与原文件名，限制最大像素数。
3. 浏览器只获得不透明相对凭据，不能提交任意服务器绝对路径。
4. 生成前核验账号、样本绑定和 SHA-256；同一图片不能跨账号或跨样本复用。
5. 核验通过后才在服务器内部解析为受控存储绝对路径并交给 Word 渲染器。

## 4. 医学边界

- 靶向结论不是基因级推断：错转录本、错 HGVS、BRAF D594G 或缺少治疗上下文均不得命中。
- ERBB2 G660D 的德曲妥珠单抗结论使用“精确事件功能/伴随诊断可报告性 + 激活型 ERBB2 突变 NSCLC 标签”的证据链，不宣称已有 G660D 单独疗效亚组。
- 瑞康曲妥珠单抗继续保持禁用；肺癌化疗药物基因组学模块继续禁用。
- 免疫表为历史报告组精确事件展示合同，属于研究性相关标志物，不能单独用于治疗决策。
- 草稿 Word 可在审核前下载，供报告组逐病例核对；审核/交付状态继续独立留痕。
- PD-L1 或靶向用药上下文缺失不会阻断草稿生成，也不会被系统补造；依赖缺失上下文的精确药物规则保持不命中。
- 肺癌 Part 3 专属知识继续失败关闭，不以本轮规则迁移冒充完整肺癌知识库。

一手证据锚点：

- BRAF V600E：FDA 对达拉非尼联合曲美替尼及康奈非尼联合比美替尼的 NSCLC 批准信息与现行标签；
  <https://www.fda.gov/drugs/resources-information-approved-drugs/fda-approves-encorafenib-binimetinib-metastatic-non-small-cell-lung-cancer-braf-v600e-mutation>
  <https://www.accessdata.fda.gov/drugsatfda_docs/label/2024/202806s031%2C217514s004lbl.pdf>
- ERBB2 突变 NSCLC：德曲妥珠单抗现行 FDA 标签；G660D 的位点层依据记录为功能证据链，不能外推为该位点独立疗效亚组；
  <https://www.accessdata.fda.gov/drugsatfda_docs/label/2026/761139s041s043lbl.pdf>
  <https://pubmed.ncbi.nlm.nih.gov/30449325/>

## 5. 验证结果

- Ruff：修改 Python 文件全部通过。
- 前端：`vue-tsc --noEmit`、Vite production build、ESLint 全部通过。
- 肺癌/Web 专项：87 项覆盖；本轮相关运行 86 项加新增 329 NGS-only 用例均通过，最终草稿显示修复的受影响闭包 4/4 通过。
- 整库回归：758 passed、4 skipped、0 failed；CRC 358/301 兼容、Web 任务前预检、直接生成输入契约和无 Panel `CtDrug` 旧回退均包含在内。
- NGS-only 草稿验收：329/588 均未提供 PD-L1 数值、来源、图片或靶向用药上下文，仍成功生成 Word；QA 为预期 `WARN`，LibreOffice 全页视觉检查均为 `PASS`（329 为 23 页、588 为 24 页），TPS/CPS/结果格显示“待补充”，图片位置显示待审核草稿提示。
- 肺癌 329 合成边界：最终独立复跑 7/7 PASS；强制视觉 QA，逐例 `qa_status=PASS`、`failures=[]`。
- 肺癌 588 合成边界：最终独立复跑 7/7 PASS；强制视觉 QA，逐例 `qa_status=PASS`、`failures=[]`。
- PD-L1 模板迁移只读门禁：两套模板均为 `up to date`，检查前后 SHA-256 不变。
- PD-L1 病例图片后处理器满足幂等合同：同一文档重复执行时第二次为字节级无操作，文档只保留一个受控标记图片；已增加回归测试。
- 3 份受控真实 NGS 输入：字段/Panel/事件语义 3/3 PASS。
- 3 份完整 Word（macOS LibreOffice）：均为 26 页，QA PASS，空白页 0，异常低内容页 0；PD-L1 病例图片已实际嵌入。
- 磁盘卫生：删除 9,110 个未跟踪且已忽略的 AppleDouble 文件及 3,562 个可再生 Python/pytest 缓存文件；源码、输入与验收凭证未删除。
- 冻结 SHA 的 iyun129 隔离 Linux 复验：329 合成边界 7/7 PASS、588 合成边界
  7/7 PASS、3 份受控真实输入 3/3 结构/映射/完整 Word QA PASS；真实输入报告
  均为 26 页，空白页和异常低内容页均为 0。
- 三份 Linux receipt 全部记录冻结 SHA；17 份 QA 同样绑定冻结 SHA，并全部记录
  `source_dirty=false`。receipt 的病例输出哈希与 QA/DOCX 17/17 闭合；17/17
  renderer fingerprint 与 iyun129 runtime 一致，profile 为
  `reportgen-cjk-font-substitution-v2`，mapping SHA-256 为
  `ac68dee9344ddedefc8a3e579ba75d28657331300c36cb182ca84962dff95afb`。
- Linux 总清单 SHA-256：
  `3c72e15d616d93cb887b34482bc216757202617688166e1622d27c21c18dc447`。
- 只读生产核对显示当前 release/REVISION/进程 cwd 仍一致指向基线
  `fad5c87775e1f217fbe13c8181165045841c27ec`，本地和公网 health 均为 HTTP 200；
  冻结候选未部署、未切换。
- 独立审计对草稿工作流提交 `6af2a356...` 的工程结论为 PASS、P0/P1=`0/0`；
  审计指出的旧冻结 SHA、两处下载提示冲突及“两事件/三治疗组合”措辞歧义，
  均已在冻结工程提交 `e791778...` 中对齐，未新增运行时医学事件。
- 共享审计机器对账未发现 identity 缺失或不一致；当前肺癌模块只有 Codex 审计，
  缺少 Claude 对审，因此不得表述为 Claude/Codex 双审完成。

验证凭据：

- `.work/lung588_real_feedback_visual_20260809/validation.json`
- `.work/lung588_real_feedback_visual_20260809/reports/`
- `.work/lung588_feedback_boundary_20260809_run2/validation.json`
- `.work/lung329_feedback_boundary_20260809_run2/validation.json`
- `.work/lung329_feedback_final_20260809/validation.json`
- `.work/lung329_p1_acceptance_20260809/validation.json`
- `.work/lung588_p1_acceptance_20260809_run2/validation.json`
- `.work/lung588_p1_real_inputs_20260809/validation.json`
- `.work/linux_lung_feedback_fd3c981/linux_acceptance_manifest_fd3c981.json`
- `.work/linux_lung_feedback_fd3c981/receipts/`
- `.work/linux_lung_feedback_fd3c981/qa/`
- `.work/windows_uat_fd3c981/WINDOWS_WORD_WPS_AND_REPORT_GROUP_UAT.md`
- `audit/lung-feedback-20260809.codex.md`
- `audit/report-group-system-uat.codex.md`

## 6. 尚未满足的发布条件

- 当前 3 例的 PD-L1 值和图片只用于机器/视觉 QA，不是经核验的病例级 IHC 来源。
- 报告组尚未在本候选身份上登记 3 例逐病例 UAT 结论、审核人和日期。
- 冻结身份的独立审计与 iyun129 隔离 Linux/LibreOffice 复验已经完成；Windows
  Word/WPS 人工验收仍未执行。待验的同一批 Linux DOCX、逐文件哈希、检查项和签署栏
  已整理在 `.work/windows_uat_fd3c981/`，但交接包不能替代 Windows 人工结论。
- 生产切换和部署后网站验收是后续独立发布动作；不得在正式 UAT 与发布总闸未通过时把本候选描述为 `active` 或“已上线”。

## 7. 本轮验收结论

- 冻结工程候选及 Linux 生产等价渲染验收：**PASS**。
- Windows 跨引擎、医学 UAT 与生产发布验收：**尚未通过**；必须完成第 6 节的
  病例来源核验、逐病例报告组 UAT、Windows Word/WPS 签署及后续发布总闸。
