---
module: lung-feedback-20260809
agent: codex
identity_kind: git_commit
identity_value: 9dd7bf94ced595c089f25406ec01245eb0777e83
audited_at: 2026-08-10
---

# 肺癌草稿文件名最终增量审计

## 1. 最终结论

本次 subject 为当前完整 HEAD `9dd7bf94ced595c089f25406ec01245eb0777e83`；开审时工作树干净。工程实现冻结提交为祖先 `cd3069e47f214213db367a3db0b8231e1c9332b2`，backend 草稿生成逻辑提交为更早祖先 `6af2a3567cbf587afcb95ab930056a2f352a901e`。

**最终工程判定：PASS，本轮工程缺口关闭。P0/P1/P2/P3=`0/0/0/0`。** 本次仅新增下载文件名标识：未审核的 `lung_329_pdl1`/`lung_588_pdl1` 在 `_download_report_response` 向文件名构造器传入 `revision_label="草稿"`；`reviewed`/`delivered` 及非肺癌项目仍传 `None`，继续使用既有默认标签。QA FAIL 拦截和 override 权限语义未改。spec 精确记录工程冻结 SHA `cd3069e...`，未发现新的 P0-P3 回归。

测试边界必须分层理解：已记录的 `51 passed in 105.58s`、两套 7/7 validation、冻结草稿正负路径来自祖先 backend 提交 `6af2a356...`。主代理另在工程冻结增量上执行新增定向回归并回报 `2 passed`；本审计只读核对测试源码，没有自行重跑。`cd3069e...→9dd7bf9...` 仅修改 `docs/spec_lung_feedback_20260809.md`，故不得把当前结论写成“当前 HEAD 已重跑测试/构建/LibreOffice”。

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
| lung-feedback-20260809-13 | P2 | spec 冻结工程身份仍是旧 SHA。 | `docs/spec_lung_feedback_20260809.md:7` 精确为 `cd3069e47f214213db367a3db0b8231e1c9332b2`。当前审计 subject 另以 frontmatter 锁定完整 HEAD `9dd7bf94...`。 | REFUTED |
| lung-feedback-20260809-14 | P2 | 页面仍要求先审核才能下载或隐藏草稿按钮。 | `ReportGenerateView.vue:428-481` 显示“下载报告草稿”并提示可先下载；`TaskDetailView.vue:11-23,63-89` 同样显示草稿按钮，并明确审核人/非审核人都可先下载，权限只限制登记审核状态。 | REFUTED |
| lung-feedback-20260809-15 | P3 | 当前清爽体检仍有 AppleDouble/cache/tracked garbage。 | 本审计写入前只读计数：`._*`=0；`.ruff_cache/.mypy_cache/.pytest_cache/__pycache__/htmlcov`=0；Git tracked 的上述垃圾、`.DS_Store`、`.pyc`、`.log`=0。 | REFUTED |
| lung-feedback-20260809-16 | P2 | 新增文件名逻辑会误标已审核/已交付或非肺癌报告，或改变 QA FAIL/权限语义。 | `backend/app/api/report.py:2653,2664-2677,2682-2695`：权限检查和 QA FAIL 409 路径保持在文件名逻辑之前；仅当项目属于两个受控肺癌 Panel 且状态不在 `reviewed/delivered` 时传 `revision_label="草稿"`。`backend/tests/test_stateless_report_endpoints.py:1927-2005` 覆盖两 Panel 的 draft/reviewed/delivered、普通用户 override 403、reviewer 放行及 CRC 默认标签；主代理执行新增定向回归回报 2 passed。 | REFUTED |

## 3. 增量覆盖矩阵

| # | 增量要求 | 状态 | 当前证据 |
|---:|---|---|---|
| 1 | 两处页面均允许并清楚标识审核前草稿下载 | ✅ | ReportGenerateView 按钮/提示与 TaskDetailView 按钮/提示一致；未见“须先审核才能下载”残留。 |
| 2 | 两个事件、三个治疗组合且不增 selector | ✅ | YAML 文案一致；解析为 selectors=2、treatment combinations=3；事件为 BRAF V600E、ERBB2 G660D。 |
| 3 | spec 工程冻结 SHA 精确 | ✅ | `docs/spec_lung_feedback_20260809.md:7`=`cd3069e47f214213db367a3db0b8231e1c9332b2`。 |
| 4 | 写入前清爽体检 | ✅ | AppleDouble=0、known cache dirs=0、tracked garbage=0。 |
| 5 | 草稿文件名仅作用于未审核的两套肺癌 Panel | ✅ | `_download_report_response` 的项目/审核状态分支；定向矩阵明确 reviewed/delivered 与 CRC 均传 `None`。 |
| 6 | QA FAIL 与权限语义不变 | ✅ | `_require_override_permission`、FAIL 409 门禁均保持原路径；冻结增量对这些语句无 diff。 |
| 7 | 当前 HEAD 仅冻结身份文档增量 | ✅ | `git diff --name-only cd3069e...HEAD` 只有 `docs/spec_lung_feedback_20260809.md`。 |

## 4. 祖先测试与验收证据（未冒充当前重跑）

| 证据 | 绑定身份 | 已核实结果 | 当前适用边界 |
|---|---|---|---|
| 定向 pytest | `6af2a3567cbf587afcb95ab930056a2f352a901e` | 51 passed / 105.58s | 证明 backend 草稿、输入 gate、QA FAIL 下载、批量隔离与 exact-context 行为；当前未重跑。 |
| 文件名定向回归 | `cd3069e47f214213db367a3db0b8231e1c9332b2` | 主代理执行回报 2 passed | 覆盖未审核肺癌草稿标签、reviewed/delivered/CRC 默认标签及 QA/override 邻接语义；本审计未独立重跑。 |
| lung329 validation | `source_revision=6af2a356...` | 7/7 PASS；逐例 QA/失败/validation→DOCX/QA→DOCX hash 均回算一致 | 合成边界祖先证据，不是当前 HEAD receipt。 |
| lung588 validation | `source_revision=6af2a356...` | 7/7 PASS；逐例 QA/失败/validation→DOCX/QA→DOCX hash 均回算一致 | 合成边界祖先证据，不是当前 HEAD receipt。 |
| 草稿正负路径 | `6af2a356...` clean worktree | 两 Panel缺 PD-L1/来源/图像/上下文均 success+WARN；缺上下文 BRAF targeted_count=0；非法范围/词表/不存在图片均 FAIL | backend 逻辑证据；当前增量未改 backend。 |

## 5. 方法保真与限制

| 子步 | mandated 方法 | 当前 method_status | 判定 | 证据 |
|---|---|---|---|---|
| 草稿下载引导 | 允许先下载草稿，审核只控制正式交付状态 | 两页面文案一致且按钮可见 | 严格完成 | 两个 Vue 文件当前行号见 §2 |
| 下载文件名状态 | 未审核肺癌草稿显式标识，不污染正式/非肺癌报告 | 两个受控 Panel 的非 reviewed/delivered 状态传“草稿”；其余传 `None` | 严格完成 | `backend/app/api/report.py:2682-2695`；定向矩阵 `backend/tests/test_stateless_report_endpoints.py:1927-2005` |
| 医学规则范围 | 2 exact events → 3 treatment combinations | 2 selectors / 3 combinations，无 selector diff | 严格完成 | `rules/drugs.yaml` + 只读 YAML 解析 |
| 冻结身份分层 | current audit、engineering freeze、backend/test ancestor 分开记录 | 三个完整 SHA 均明确，不互相冒充 | 严格完成 | frontmatter；spec:7；本节祖先证据表 |
| 人审/UAT/生产 | 工程 PASS 不冒充人工或上线 PASS | 仍明确在本审计范围外 | 诚实边界 | spec/release 边界 + 本报告结论 |

限制：依指令没有在当前 HEAD 运行 pytest、前端构建或 LibreOffice，也没有删除文件。`2 passed` 是主代理提供的执行证据，本审计仅核对测试源码与冻结差异。当前 HEAD 相对工程冻结提交仅有 spec 身份记录，不能冒充新的全量执行 receipt。

## 6. 最终解除条件

本轮草稿工作流工程缺口无需更多整改即可关闭。后续若要宣称医学/正式交付/生产 PASS，仍须另行取得病例级来源、报告组 UAT、Windows 人工验收和部署后身份/health 证据；这些不属于本次 P0-P3 开放 finding。
