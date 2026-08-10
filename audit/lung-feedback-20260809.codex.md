---
module: lung-feedback-20260809
agent: codex
identity_kind: git_commit
identity_value: 6ac5e65092c895a024faf911dc3631f169d5b1f7
audited_at: 2026-08-10
---

# 肺癌草稿工作流最终增量审计

## 1. 最终结论

本次 subject 为当前完整 HEAD `6ac5e65092c895a024faf911dc3631f169d5b1f7`；开审时工作树干净。工程实现冻结提交为祖先 `e79177872c9dfde21e0fc35b373143023e4fb241`，backend 草稿逻辑提交为更早祖先 `6af2a3567cbf587afcb95ab930056a2f352a901e`。

**最终工程判定：PASS，本轮工程缺口关闭。P0/P1/P2/P3=`0/0/0/0`。** ReportGenerateView 与 TaskDetailView 均明确草稿可先下载；规则/UAT 已统一为两个 exact events、三个 treatment combinations，实际仍仅两个 selector；spec 精确记录工程冻结 SHA `e791...`；审计写入前 AppleDouble、已知 cache 目录和 tracked garbage 均为 0。原 finding 03/13/14/15 全部关闭。

测试边界必须分层理解：已记录的 `51 passed in 105.58s`、两套 7/7 validation、冻结草稿正负路径来自祖先 backend 提交 `6af2a356...`，不是在当前 HEAD 上重跑。`6af2a356...→e791...` 仅改两处 Vue 展示文案与规则/UAT 描述字段，没有 backend 逻辑或 selector 增量；`e791...→6ac5e650...` 仅改 spec 与审计记录。因此这些祖先测试仍是 backend 行为证据，但不得写成“当前 HEAD 已重跑测试/构建/LibreOffice”。

本结论仍不外推为病例级 IHC 来源、报告组 UAT、Windows 人工验收或生产部署 PASS。

### P0-P3

| 级别 | 数量 | 结论 |
|---|---:|---|
| P0 | 0 | 无开放 finding。 |
| P1 | 0 | 无开放 finding。 |
| P2 | 0 | 原三项文案/身份问题均已修正。 |
| P3 | 0 | 写入前清爽体检三项均为 0。 |

## 2. 共享发现表（最终状态）

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung-feedback-20260809-03 | P2 | 当前规则/UAT 仍把两个 exact events 模糊写成“三个候选”。 | `panels/lung_588_pdl1/rules/drugs.yaml:7-10` 已写 two exact events / three treatment combinations；329/588 risk policy 分别在 `:43`/`:47` 使用相同口径。只读解析 `reviewed_variant_overrides` 得 2 个 selector（BRAF V600E、ERBB2 G660D）和 3 个 `benefit_drugs` 组合；`6af..e791` diff 未增加 selector。 | REFUTED |
| lung-feedback-20260809-13 | P2 | spec 冻结工程身份仍是旧 SHA。 | `docs/spec_lung_feedback_20260809.md:7` 精确为 `e79177872c9dfde21e0fc35b373143023e4fb241`。当前审计 subject 另以 frontmatter 锁定完整 HEAD `6ac5e650...`。 | REFUTED |
| lung-feedback-20260809-14 | P2 | 页面仍要求先审核才能下载或隐藏草稿按钮。 | `ReportGenerateView.vue:428-481` 显示“下载报告草稿”并提示可先下载；`TaskDetailView.vue:11-23,63-89` 同样显示草稿按钮，并明确审核人/非审核人都可先下载，权限只限制登记审核状态。 | REFUTED |
| lung-feedback-20260809-15 | P3 | 当前清爽体检仍有 AppleDouble/cache/tracked garbage。 | 本审计写入前只读计数：`._*`=0；`.ruff_cache/.mypy_cache/.pytest_cache/__pycache__/htmlcov`=0；Git tracked 的上述垃圾、`.DS_Store`、`.pyc`、`.log`=0。 | REFUTED |

## 3. 增量覆盖矩阵

| # | 增量要求 | 状态 | 当前证据 |
|---:|---|---|---|
| 1 | 两处页面均允许并清楚标识审核前草稿下载 | ✅ | ReportGenerateView 按钮/提示与 TaskDetailView 按钮/提示一致；未见“须先审核才能下载”残留。 |
| 2 | 两个事件、三个治疗组合且不增 selector | ✅ | YAML 文案一致；解析为 selectors=2、treatment combinations=3；事件为 BRAF V600E、ERBB2 G660D。 |
| 3 | spec 工程冻结 SHA 精确 | ✅ | `docs/spec_lung_feedback_20260809.md:7`=`e79177872c9dfde21e0fc35b373143023e4fb241`。 |
| 4 | 写入前清爽体检 | ✅ | AppleDouble=0、known cache dirs=0、tracked garbage=0。 |
| 5 | 当前增量未偷换 backend 方法 | ✅ | `git diff 6af2a356..e791778` 仅 Vue 展示和 YAML 描述/UAT 口径；`git diff e791778..HEAD` 仅 audit/spec。 |

## 4. 祖先测试与验收证据（未冒充当前重跑）

| 证据 | 绑定身份 | 已核实结果 | 当前适用边界 |
|---|---|---|---|
| 定向 pytest | `6af2a3567cbf587afcb95ab930056a2f352a901e` | 51 passed / 105.58s | 证明 backend 草稿、输入 gate、QA FAIL 下载、批量隔离与 exact-context 行为；当前未重跑。 |
| lung329 validation | `source_revision=6af2a356...` | 7/7 PASS；逐例 QA/失败/validation→DOCX/QA→DOCX hash 均回算一致 | 合成边界祖先证据，不是当前 HEAD receipt。 |
| lung588 validation | `source_revision=6af2a356...` | 7/7 PASS；逐例 QA/失败/validation→DOCX/QA→DOCX hash 均回算一致 | 合成边界祖先证据，不是当前 HEAD receipt。 |
| 草稿正负路径 | `6af2a356...` clean worktree | 两 Panel缺 PD-L1/来源/图像/上下文均 success+WARN；缺上下文 BRAF targeted_count=0；非法范围/词表/不存在图片均 FAIL | backend 逻辑证据；当前增量未改 backend。 |

## 5. 方法保真与限制

| 子步 | mandated 方法 | 当前 method_status | 判定 | 证据 |
|---|---|---|---|---|
| 草稿下载引导 | 允许先下载草稿，审核只控制正式交付状态 | 两页面文案一致且按钮可见 | 严格完成 | 两个 Vue 文件当前行号见 §2 |
| 医学规则范围 | 2 exact events → 3 treatment combinations | 2 selectors / 3 combinations，无 selector diff | 严格完成 | `rules/drugs.yaml` + 只读 YAML 解析 |
| 冻结身份分层 | current audit、engineering freeze、backend/test ancestor 分开记录 | 三个完整 SHA 均明确，不互相冒充 | 严格完成 | frontmatter；spec:7；本节祖先证据表 |
| 人审/UAT/生产 | 工程 PASS 不冒充人工或上线 PASS | 仍明确在本审计范围外 | 诚实边界 | spec/release 边界 + 本报告结论 |

限制：依指令没有在当前 HEAD 运行 pytest、前端构建或 LibreOffice，也没有删除文件。当前 HEAD 的通过结论是“祖先 backend 证据 + 当前纯文案/spec 增量的只读核验”，不是新的全量执行 receipt。

## 6. 最终解除条件

本轮草稿工作流工程缺口无需更多整改即可关闭。后续若要宣称医学/正式交付/生产 PASS，仍须另行取得病例级来源、报告组 UAT、Windows 人工验收和部署后身份/health 证据；这些不属于本次 P0-P3 开放 finding。
