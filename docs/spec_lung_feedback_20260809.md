# 肺癌报告组反馈修复规格（2026-08-09）

## 1. 范围与身份

- 基线提交：`fad5c87`
- 候选分支：`codex/lung-feedback-20260809`
- 覆盖 Panel：`lung_329_pdl1`、`lung_588_pdl1`
- 本文记录候选内容与验收口径；确切冻结 SHA 由同模块独立审计凭证绑定，
  生产实际运行身份只能由 iyun129 release/REVISION/进程/health 实时证据确认。
- 真实输入只在 `.work/` 中以 `CASE-LUNG-A/B/C` 处理，不进入 Git。

## 2. 反馈到根因与修复的映射

| 反馈 | 根因 | 修复与验收 |
|---|---|---|
| 网页显示“药物相关 0、靶向提示 0” | 肺癌规则此前整体失败关闭；历史候选没有经过癌种、转录本、HGVS 与治疗上下文边界后进入运行规则 | 仅启用 BRAF `NM_004333.6/c.1799T>A/p.V600E` 与 ERBB2 `NM_004448.4/c.1979G>A/p.G660D` 两个精确事件；必须满足 NSCLC、疾病范围、既往治疗和伴随诊断条件，并保留病例级审核下载闸。CASE-LUNG-C 网页摘要为药物相关 2、靶向 2。 |
| 免疫正/负相关均显示“未检出” | 肺癌 588 未关联任何运行时免疫事件；直接接通基因级公共库会造成任意位点继承 | `lung_588_pdl1` 只接入历史终版中已出现的 7 个“转录本 + c./p.HGVS + I/II 类”精确事件；CASE-LUNG-B 正相关 5，CASE-LUNG-C 正相关 2、负相关 1。`lung_329_pdl1` 只暂存候选，模块继续禁用。 |
| 化疗提示显示 0，容易被理解为“检测结果为零” | 模块禁用状态被前端压成数字 | 后端输出独立模块状态，前端显示“未启用（待医学审核）”，不再把未建设模块伪装成 0 条结果。 |
| 找不到“标记已审核” | 生成页直接暴露下载动作，任务详情中的审核区说明不明确 | 肺癌生成完成后只引导进入任务详情；审核区明确标注位置和操作顺序。管理员/复核人点击“标记已审核”前，顶部下载按钮显示“请先标记已审核”并禁用。 |
| 首次下载即提示“已重试 3 次” | 错误文案使用配置的最大重试次数，而不是实际尝试次数 | 下载错误携带真实 attempt；首次 409 不追加重试文案，只有确实发生断点续传时才显示“共尝试 N 次”。 |
| PD-L1 表单字段过多 | 把内部溯源字段直接暴露给报告组填写 | 用户只填写 TPS、CPS、结果判定和病例图片；方案、记录编号、日期、标本和图像处置由服务器从受控上传凭据生成。靶向用药上下文放在独立分组，并明确“不属于 PD-L1 检测字段”。 |
| PD-L1 Word 下方说明过多、缺少上传图片 | 模板保留历史方法/来源说明，且没有病例图片处理器 | 两套肺癌模板均只保留 TPS/CPS/结果表、病例图片与图注，之后直接进入 MSI；新增 `pdl1_case_image` 后处理器。 |

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
- 所有已启用精确规则仍要求逐病例报告组审核后下载。
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
- 专项回归：123 passed、0 failed。
- 整库回归：755 passed、4 skipped、0 failed；CRC 358/301 兼容、Web 任务前预检、直接生成输入契约和无 Panel `CtDrug` 旧回退均包含在内。
- 肺癌 329 合成边界：最终独立复跑 7/7 PASS；强制视觉 QA，逐例 `qa_status=PASS`、`failures=[]`。
- 肺癌 588 合成边界：最终独立复跑 7/7 PASS；强制视觉 QA，逐例 `qa_status=PASS`、`failures=[]`。
- PD-L1 模板迁移只读门禁：两套模板均为 `up to date`，检查前后 SHA-256 不变。
- PD-L1 病例图片后处理器满足幂等合同：同一文档重复执行时第二次为字节级无操作，文档只保留一个受控标记图片；已增加回归测试。
- 3 份受控真实 NGS 输入：字段/Panel/事件语义 3/3 PASS。
- 3 份完整 Word（macOS LibreOffice）：均为 26 页，QA PASS，空白页 0，异常低内容页 0；PD-L1 病例图片已实际嵌入。
- 磁盘卫生：删除 9,110 个未跟踪且已忽略的 AppleDouble 文件及 3,562 个可再生 Python/pytest 缓存文件；源码、输入与验收凭证未删除。

验证凭据：

- `.work/lung588_real_feedback_visual_20260809/validation.json`
- `.work/lung588_real_feedback_visual_20260809/reports/`
- `.work/lung588_feedback_boundary_20260809_run2/validation.json`
- `.work/lung329_feedback_boundary_20260809_run2/validation.json`
- `.work/lung329_feedback_final_20260809/validation.json`
- `.work/lung329_p1_acceptance_20260809/validation.json`
- `.work/lung588_p1_acceptance_20260809_run2/validation.json`
- `.work/lung588_p1_real_inputs_20260809/validation.json`

## 6. 尚未满足的发布条件

- 当前 3 例的 PD-L1 值和图片只用于机器/视觉 QA，不是经核验的病例级 IHC 来源。
- 报告组尚未在本候选身份上登记 3 例逐病例 UAT 结论、审核人和日期。
- 冻结身份仍需完成独立审计、iyun129 隔离 Linux/LibreOffice 复验和 Windows Word/WPS 人工验收；本候选不因 macOS QA PASS 自动获得生产等价资格。
- 生产切换和部署后网站验收是后续独立发布动作；不得在正式 UAT 与发布总闸未通过时把本候选描述为 `active` 或“已上线”。

## 7. 本轮验收结论

- 工程候选验收：**PASS**。
- 医学/生产发布验收：**尚未通过**；必须完成第 6 节的来源核验、逐病例 UAT、冻结提交独立审计、跨平台验收及发布总闸。
