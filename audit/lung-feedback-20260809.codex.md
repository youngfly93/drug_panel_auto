---
module: lung-feedback-20260809
agent: codex
identity_kind: git_commit
identity_value: 6af2a3567cbf587afcb95ab930056a2f352a901e
audited_at: 2026-08-10
---

# 肺癌草稿生成冻结提交独立审计

## 1. 结论

本次只审冻结提交 `6af2a3567cbf587afcb95ab930056a2f352a901e`。开审时 `HEAD` 精确等于该 SHA，工作树干净；旧 `fd3c981...` 的测试、receipt 和审计结论仅作历史，未被复用为本次通过证据。

**工程结论：PASS，本轮工程缺口可以关闭。** `lung_329_pdl1` 与 `lung_588_pdl1` 均能在 PD-L1 数值、来源、图片和治疗上下文全部缺失时生成可供报告组审核的 Word 草稿；草稿 QA 为预期 `WARN`，正文明确显示“待审核草稿”、TPS/CPS/结果三个“待补充”和缺图提示。未审核状态可以下载，QA=`FAIL` 仍被拦截。缺失上下文时即使输入精确 BRAF V600E，运行靶向条目仍为 0；已提供但越界、非法词表或不存在的图片继续失败关闭。

这不是医学或生产发布 PASS：本审计没有把合成病例、机器 QA 或草稿下载冒充病例级 IHC 来源、报告组 UAT、Windows 人工验收或生产部署。

### P0-P3

| 级别 | 数量 | 结论 |
|---|---:|---|
| P0 | 0 | 未发现患者级错误结论、跨病例串用或数据泄漏。 |
| P1 | 0 | 未发现阻断本轮草稿生成工程目标的功能/安全缺陷。 |
| P2 | 3 | spec 冻结 SHA 仍是旧值；任务页提示语与实际草稿下载策略冲突；“三个候选”措辞与两个精确事件不一致。 |
| P3 | 1 | ignored AppleDouble/cache 未清爽，合并记一个卫生发现。 |

## 2. 共享发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung-feedback-20260809-03 | P2 | 医学规则/UAT 文案把两个精确事件称为“三个候选”。 | `panels/lung_588_pdl1/rules/drugs.yaml:8,47-129` 仅有 BRAF V600E、ERBB2 G660D 两个 selector，却写 three conclusions；两套 risk policy `:43-47` 也写 three candidates。当前运行目录没有新增第三个 selector。 | CONFIRMED |
| lung-feedback-20260809-13 | P2 | 当前 spec 的冻结身份没有随新冻结提交更新。 | `docs/spec_lung_feedback_20260809.md:7` 仍写 `fd3c981...`；本审计 HEAD、两套新 validation 与 QA 均绑定 `6af2a356...`。 | CONFIRMED |
| lung-feedback-20260809-14 | P2 | 任务页下载提示内部矛盾。 | `frontend/src/views/TaskDetailView.vue:18-23` 未审核时按钮为“下载报告草稿”，后端 `backend/app/api/report.py:2647-2691` 也允许；但页面 `TaskDetailView.vue:79-85` 仍提示须先标记审核后才能下载/当前账号不能下载。 | CONFIRMED |
| lung-feedback-20260809-15 | P3 | 2.5 清爽体检仍有 ignored 运行垃圾。 | 审计输出写入前只读 `find` 计得 `._*` 814 个、已知 cache 目录 21 个，Git tracked 对应项为 0；不影响冻结 SHA，但不符合清爽合同。 | CONFIRMED |

## 3. 审计目标覆盖

| # | 目标 | 状态 | 冻结证据 |
|---:|---|---|---|
| 1 | 缺 PD-L1/来源/图片/上下文仍生成并下载明确草稿 | ✅ | 冻结 HEAD 独立直调两 Panel：均 `success=true`、QA=`WARN`、`source_dirty=false`；Word 含“待审核草稿”、三个“待补充”、缺图提示且无病例图。Web 队列/下载测试通过。 |
| 2 | 缺上下文不命中依赖字段的精确药物规则 | ✅ | 独立直调在两 Panel 输入 BRAF `NM_004333.6/c.1799T>A/p.V600E`、不提供四个上下文字段，summary 均为 `targeted_count=0`，状态提示补齐上下文；上下文 evaluator/runtime exact-rule 测试通过。 |
| 3 | 已提供的非法范围/词表/不存在图片仍失败 | ✅ | TPS=101、非法 `pdl1_result` 均在 InputContractValidationStage 以 `PANEL_REQUIRED_BIOMARKER_MISSING` FAIL；非空但不存在图片在 TemplateRenderingStage 以 `STAGE_EXCEPTION` FAIL，消息明确“病例专属PD-L1图片不存在”。 |
| 4 | required sheets/columns/required-any、QA FAIL 下载、批量隔离仍在 | ✅ | `reportgen/panels/input_contract.py:72-139`；两 Panel `panel.yaml` required contract；Web 缺 selector 列 422/不建任务、Generator 直调阻断测试通过；单份/批量 QA FAIL 下载及两 Panel shared batch 禁用测试通过。 |
| 5 | 未扩大医学规则或伪造人审/UAT | ✅ | 新提交未修改 `drugs.yaml`、`biomarkers.yaml` 或 UAT registry；运行 selector 仍为 2 个精确事件。`pdl1_product_contract.yaml:15-39` 仍 `promotion_blocked:true`、`treatment_inference_allowed:false`；草稿 WARN 不改写 review/UAT。 |
| 6 | 两套冻结边界均 7/7 PASS 且绑定 SHA | ✅ | `.work/lung_boundary_regression_20260810/{lung329,lung588}/validation.json` 均 status PASS、7 cases、7 passed、source_revision=`6af2a356...`；逐例 QA/失败/哈希已回算。 |
| 7 | 无明显 P0-P2 功能回归 | ⚠️ | 受影响闭包 51 项全部通过，未见 P0/P1；发现 3 个非阻断 P2 文档/UX 问题。未重跑完整 758 项 backend suite，因此不把定向通过外推成“整库已独立复验”。 |

## 4. 承重数字与独立复算

| claim | 源证据 | 独立复算 | 一致? |
|---|---|---:|---|
| lung329 冻结边界 | `.work/lung_boundary_regression_20260810/lung329/validation.json` | source SHA match；7 cases；7 PASS；7 QA PASS；0 failures；7/7 validation→DOCX hash match；7/7 QA→DOCX hash match；QA clean 7/7 | 是 |
| lung588 冻结边界 | `.work/lung_boundary_regression_20260810/lung588/validation.json` | source SHA match；7 cases；7 PASS；7 QA PASS；0 failures；7/7 validation→DOCX hash match；7/7 QA→DOCX hash match；QA clean 7/7 | 是 |
| validation 文件身份 | 两个 validation JSON | 329 SHA-256 `f5993988d3a909574c4704c4e7ec4dfc26c56cc1661df6dc601fc09fdbdedeea`；588 `cf421a57896f6d1995ad91c879d2f658e5a0323369057fa6cbf9137a22548061` | 已锁定 |
| 冻结草稿正路径 | `/tmp/lung-6af-audit.RMDy2K/missing_lung_{329,588}_pdl1/` | 2/2 success；2/2 QA WARN；2/2 QA revision 精确匹配；2/2 source_dirty=false；BRAF targeted_count 0/0 | 是 |
| 非法输入负路径 | 同一临时独立直调 | range FAIL 1/1；vocabulary FAIL 1/1；nonexistent image FAIL 1/1；均无可交付 output | 是 |
| 定向 pytest | 冻结 HEAD，`PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider ...` | **51 passed in 105.58s** | 是 |

## 5. 方法保真与限制

| 子步 | mandated 方法 | 实际 method_status | 判定 | fitness-for-purpose | 证据 |
|---|---|---|---|---|---|
| 缺失 PD-L1 | 缺失可降级为可见 WARN 草稿，不补造值/来源 | 两 Panel可见待补字段、缺图提示、QA WARN | 严格完成 | 适合报告组预审，不适合正式交付/UAT | `reportgen/core/report_generator.py:1081-1156`；`template_renderer.py:252-345`；冻结直调 |
| 已提供非法值 | range/词表继续失败关闭 | biomarker gate 在模板前 FAIL | 严格完成 | 适合阻止非法患者值进入草稿 | `report_generator.py:93-230,1081-1115`；冻结负路径 |
| 缺治疗上下文 | exact selector 不命中，不回退基因级药物 | BRAF 精确事件被识别但 targeted rows=0 | 严格完成 | 适合草稿生成且不产生上下文依赖结论 | `reportgen/rules/targeted_drugs.py:26-127`；冻结直调 |
| 草稿下载/QA | draft/WARN 可下载，QA FAIL 需 reviewer override | 单份及批量门禁测试通过 | 严格完成 | 适合报告组预审；审核/交付状态仍独立 | `backend/app/api/report.py:2647-2691`；定向 pytest |
| 批量隔离 | shared lung form 不得跨病例复用 | 两 Panel shared batch 均 409 | 严格完成 | 阻止跨病例 PD-L1 串用 | 两 Panel smoke/contract tests |
| 人审/UAT | 工程草稿不得伪装人审通过 | promotion 仍 blocked，无新 UAT decision | 诚实边界 | 不适合声明医学/生产发布 | 两套 `pdl1_product_contract.yaml:15-39`；UAT registry |

受控字段为 Web 受控选项或 Excel exact selector，运行时没有 raw→mapped 批量折进阶段；本轮直接核对 allowed values 和 exact comparison，未虚构 mapping TSV。gate 自报的 7/7 没有照抄：已逐例回 validation、QA 和 DOCX 实算哈希。

限制：完整 backend suite、本轮 Windows Word/WPS、真实病例级 IHC 来源、报告组 UAT 和生产部署均未在此审计中执行。它们不阻断“可生成并下载明确 WARN 草稿”的工程缺口关闭，但阻断任何医学/正式交付/生产 PASS 表述。

## 6. Exonerated

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung-feedback-20260809-16 | P1 | 缺 PD-L1 或上下文仍会阻断两 Panel 草稿生成。 | 冻结独立直调 2/2 success/WARN/clean SHA；Word 可见待补草稿标识。 | REFUTED |
| lung-feedback-20260809-17 | P1 | 缺上下文的 BRAF V600E 会 fail-open 成患者级靶向药物。 | 两 Panel独立直调 targeted_count 均为 0；exact-context 测试通过。 | REFUTED |
| lung-feedback-20260809-18 | P1 | warn 模式会把已提供的非法范围、词表或坏图片也放行。 | 三类冻结负路径均 FAIL。 | REFUTED |
| lung-feedback-20260809-19 | P1 | 草稿下载改动取消了 QA FAIL 或批量跨病例保护。 | 单份/批量 QA FAIL、shared batch 与 input-contract 测试通过。 | REFUTED |
| lung-feedback-20260809-20 | P1 | 新提交扩大医学 selector 或把草稿标为 UAT PASS。 | 医学规则/UAT 文件相对旧冻结无改动；2 个 selector，promotion blocked。 | REFUTED |

## 7. 建议

1. 将 `docs/spec_lung_feedback_20260809.md` 的冻结 SHA 与验收凭据索引更新到 `6af2a356...`。
2. 统一任务页提示为“草稿可先下载；正式交付前必须审核”，避免与按钮/后端行为冲突。
3. 把 two events / three treatment combinations 写清，清理 ignored AppleDouble/cache；这些 P2/P3 不阻断本轮工程缺口关闭。
