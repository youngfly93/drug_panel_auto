---
module: lung-feedback-20260809
agent: codex
identity_kind: git_commit
identity_value: fd3c98154e031832c8db9d698ddfddd2ad000008
audited_at: 2026-08-09
updated_at: 2026-08-09T23:35:33+08:00
---

# 肺癌报告组反馈冻结提交独立审计

## 1. 总体评价与最终判定

审计对象为冻结提交 `fd3c98154e031832c8db9d698ddfddd2ad000008`。审计开始与冻结代码复验结束时，`git rev-parse HEAD` 均为该完整 SHA；首次写入本观察层文件前，`git status --short` 为空。本项目无 `plan.md`，故以 `docs/spec_lung_feedback_20260809.md`、`docs/panel_package_spec.md`、两套肺癌 Panel 包及 UAT 契约、`docs/release_checklist.md` 为审计主轴。新增证据复核期间，共享工作树出现其他 agent 写入的 `HANDOFF.md`、spec 与审计观察层变更；`HEAD` 未变且未见实现文件改动，这些并不改变冻结 subject。

结论分层如下：

- **两项原 P1 工程缺口均已在冻结代码中关闭。** 显式 Panel 即使公共 KB 不可用也不会重新打开基因级 `CtDrug`；必需表/列由同一中央校验器在 Web 创建任务前与 `ReportGenerator` 内再次强制。源码追溯、定向测试和冻结提交整库测试相互印证。
- **CRC/legacy 代码兼容性在冻结提交上复验通过。** 本审计运行 `pytest -q -p no:cacheprovider backend/tests`，得到 `755 passed, 4 skipped, 6 warnings`；另行定向覆盖了无 Panel `CtDrug` 旧回退、CRC301 基本生成和 Panel registry。
- **冻结身份的 Linux 工程验收已经完成。** 新增 manifest、3 份 receipt、17 份 QA 和 17 份待 Windows 验收 DOCX 构成可闭合的哈希链：3/3 receipt 为 PASS 并绑定冻结 SHA；17/17 QA 为 PASS、`source_dirty=false`、pipeline/visual/pixel PASS；17/17 DOCX 的实际 SHA-256 与同病例 QA 的 `metrics.output_sha256` 一致。
- **Linux renderer 与 iyun129 runtime 等价已独立核实。** 17/17 QA 的 renderer fingerprint 与 manifest 内 runtime profile 逐字段一致；manifest 记录的 runtime fingerprint SHA-256 `a0e3a1fe...` 与本审计通过只读 SSH 对 iyun129 当前 `renderer_fingerprint.json` 的实算值完全相同，字体替换 profile/hash 也一致。
- **医学 UAT、病例级 PD-L1 来源、Windows Word/WPS 和生产部署仍未被工程 PASS 冒充。** Linux real receipt 明确自报 `formal_uat_status=BLOCKED`、病例级来源 `0/3`、报告组审核 `0/3`；Windows 交接单逐例标为 Word/WPS `NOT_RUN`，最终签署也是 `NOT_RUN/BLOCKED`；iyun129 只读 release status 显示 current release/REVISION/process cwd 均仍指向 `fad5c877...`，local/public health HTTP 200，说明本冻结提交未部署且隔离验收未影响健康生产。

**修订后最终判定：Linux 工程验收 `PASS`；医学/正式 UAT/生产发布 `BLOCKED`。** 总体发布判定仍为 `BLOCKED`，但原“冻结 receipt 身份未绑定”和“Linux 验收缺失”两项已由新证据关闭；spec 的 `source_dirty` 字段载体已纠正，AppleDouble/已知 cache 目录也已清零。剩余阻断仅为：Windows Word/WPS 人工签署、3 例病例级真实 IHC 来源、3 例报告组 UAT 决策/审核人/日期，以及生产合并、部署和部署后 smoke/身份对账。

### P0-P3 概览

| 级别 | 数量 | 摘要 |
|---|---:|---|
| P0 | 0 | 未发现会直接产生错误患者级结论或跨病例泄漏的已证实缺陷。 |
| P1 | 1 | 正式 UAT/病例级 PD-L1 来源、Windows 人工签署和生产晋级仍被阻断。 |
| P2 | 1 | “三个候选”措辞与实际两个精确事件不一致。 |
| P3 | 0 | AppleDouble、已知 cache 目录与对应 Git tracked 项均复核为 0。 |

## 2. 共享发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung-feedback-20260809-01 | P1 | 329/588 合成及 588 真实输入的冻结 receipt 仍不能证明产物来自冻结提交。 | 新证据反证该 claim：`.work/linux_lung_feedback_fd3c981/linux_acceptance_manifest_fd3c981.json:3,18-24,123-129,228-234` 及 `receipts/*.json:5` 均绑定 `fd3c981...`；17/17 QA 进一步给出同 SHA 与 `source_dirty=false`，receipt/QA/DOCX 哈希链 17/17 闭合。旧 `fad5c877...` receipt 保留为历史证据，不再是当前 Linux acceptance。 | REFUTED |
| lung-feedback-20260809-02 | P1 | 当前候选不得晋级为医学 UAT 通过或生产已上线状态。 | Linux real receipt `.work/linux_lung_feedback_fd3c981/receipts/lung588_real_validation.json:18-34` 回报 PD-L1 来源 `0/3`、报告组审核 `0/3`、`formal_uat_status=BLOCKED`；Windows 交接单 `:47-67,73-91` 明示 17 例 Word/WPS `NOT_RUN`、IHC `NOT_VERIFIED`、报告组 pending/BLOCKED；只读 release status 仍为 `fad5c877...`；release checklist `:62-70,306-312,388-403` 仍要求 UAT、Windows 和生产门禁。 | CONFIRMED |
| lung-feedback-20260809-03 | P2 | UAT/规则说明中的“三个精确候选/结论”与实际两个精确事件不一致。 | `panels/lung_329_pdl1/uat/lung329_risk_based_release_policy.yaml:39-48`、`panels/lung_588_pdl1/uat/lung588_risk_based_release_policy.yaml:43-50`、`panels/lung_588_pdl1/rules/drugs.yaml:7-10` 写“三个”；但同一规则文件仅有 BRAF V600E 与 ERBB2 G660D 两个 selector（`:47-87,89-129`），且规格 `docs/spec_lung_feedback_20260809.md:16` 也只定义两个事件。 | CONFIRMED |
| lung-feedback-20260809-04 | P3 | 清理后 2.5 清爽体检仍非零垃圾。 | 二次只读 `find` 复核：`._*` AppleDouble 文件 0；已知 cache 目录（`.ruff_cache/.mypy_cache/.pytest_cache/__pycache__/htmlcov`）0；对应 Git tracked 路径 0。原 8 个 AppleDouble 与后续识别的 2 个 Ruff cache 目录已由维护方清理，不是审计方删除。 | REFUTED |
| lung-feedback-20260809-12 | P2 | 修订后的 spec 仍把 `source_dirty=false` 错写成 receipt 自身字段。 | `docs/spec_lung_feedback_20260809.md:75-76` 已明确区分“三份 receipt 记录冻结 SHA”与“17 份 QA 记录 `source_dirty=false`”，并用 output hash 描述 receipt/QA/DOCX 17/17 闭环；与三个 receipt 无 dirty 字段、17 QA 全部 false 的复算一致。 | REFUTED |

## 3. 需求覆盖矩阵

| 序号 | 规格/契约要求 | 覆盖状态 | 对应证据与判定 |
|---:|---|---|---|
| 1 | 冻结身份由独立审计及验收证据绑定 | ✅ | 本文件头使用完整 SHA；Linux manifest、3 份 receipt 和 17 份 QA 均绑定 `fd3c981...`；QA 17/17 `source_dirty=false`。receipt 本身不含 dirty 字段，靠病例输出哈希连接到 clean QA；spec 已准确描述该字段载体。 |
| 2 | 仅 BRAF V600E、ERBB2 G660D 两个上下文受限精确靶向事件 | ✅ | `panels/lung_588_pdl1/rules/drugs.yaml:47-129`；转录本和上下文失败关闭见 `reportgen/rules/targeted_drugs.py:26-127,161-194`。 |
| 3 | lung329 继承相同精确靶向规则，不打开公共/内部库 | ✅ | `panels/lung_329_pdl1/rules/drugs.yaml:18-25`：source panel 指向 588、`base_db_enabled:false`、空 allowed sources；继承时再按 Panel 过滤见 `reportgen/rules/targeted_drugs.py:445-477`。 |
| 4 | lung588 仅 7 个 transcript+HGVS 精确免疫事件；lung329 禁用 | ✅ | `panels/lung_588_pdl1/rules/biomarkers.yaml:24-118` 为 6 正、1 负且 runtime eligible；329 对应表 `:24-118` 整体 `enabled:false` 且逐行 `runtime_eligible:false`。 |
| 5 | 化疗和 Part 3 禁用应显示状态而非伪装为 0 | ✅ | 两个 `panel.yaml` 均关闭 Part 3（329 `:42-50`；588 `:55-64`）；逐例 summary 的 `chemotherapy_status` 为“未启用（待医学审核）”，冻结整库回归通过。 |
| 6 | 肺癌生成完成后进入任务详情审核，未审核不能下载 | ✅ | `frontend/src/views/ReportGenerateView.vue:428-475` 仅引导进入详情；`frontend/src/views/TaskDetailView.vue:11-24,64-89,113-123,844-853` 禁用下载并给出操作顺序；后端回归 `backend/tests/test_stateless_report_endpoints.py:1928-1996` 覆盖 329/588，且 CRC 不受影响。 |
| 7 | 下载错误展示实际 attempt，不把首次 409 写成重试 3 次 | ✅ | `frontend/src/api/report.ts:486-583` 按实际循环次数记录 `attempts`，`:796-821` 仅当 `attempts>1` 追加次数。源码满足要求；本审计未执行浏览器交互 UAT。 |
| 8 | PD-L1 表单只暴露报告组字段，内部溯源由服务端生成 | ✅ | `backend/app/services/clinical_info_service.py:196-240` 只展示/必填 TPS、CPS、结果、图像及独立治疗上下文；内部字段只在 `PROJECT_ONLY_FIELDS` 中登记（`:245-260`），由 `apply_pdl1_image_metadata()` 服务端生成（`:634-679`）。 |
| 9 | PD-L1 图片解码重编码、去元数据、相对凭据、账号/样本/SHA 绑定、单图幂等 | ✅ | `backend/app/services/file_manager.py:175-248,251-315`；Word marker 与幂等保护见 `reportgen/core/template_renderer.py:255-319`。整库回归覆盖相关测试。 |
| 10 | 显式 Panel + KB 不可用时不得 `CtDrug` fail-open | ✅ | 原 P1 已关闭，详见 §5.1 与 exonerated 表。 |
| 11 | required tables/columns 在 Web 任务前及 Generator 内双重强制 | ✅ | 原 P1 已关闭，详见 §5.2；两 Panel 契约见 329 `panel.yaml:100-138`、588 `panel.yaml:117-159`。 |
| 12 | Panel package schema、声明文件、processor、marker、golden case 可验证 | ✅ | 两包具备 `docs/panel_package_spec.md:31-50` 所列字段；冻结整库中的 registry/package validator 测试通过。 |
| 13 | 329/588 合成边界各 7/7、逐例 Linux QA PASS、失败数 0 | ✅ | 新 Linux receipt 分别 7/7 PASS；对应 14 份 QA 均冻结 SHA、clean source、pipeline/visual/pixel PASS；DOCX 哈希逐例闭合。 |
| 14 | 588 三个受控真实 NGS 输入结构/事件/Linux Word QA | ✅ | 新 Linux receipt 为 3/3 generation/QA PASS、共 78 页、空白/低内容 0，绑定冻结 SHA；3 份 DOCX 与 QA 输出哈希逐例一致。原始受控 Excel 仍不在审计目录，故只证明登记输入的 Linux pre-UAT，不证明正式病例级 PD-L1/UAT。 |
| 15 | 合成 PD-L1 不算真实 UAT；病例级来源、报告组 UAT 必须完整 | ❌ | 规则本身正确失败关闭；当前客观状态为来源 `0/3`、审核 `0/3`、formal UAT BLOCKED。 |
| 16 | 冻结 SHA 的 iyun129 Linux/LibreOffice 工程验收 | ✅ | manifest 指定 isolated acceptance/no deployment、Linux 5.15、LibreOffice 7.3.7.2；17 QA 全部视觉 PASS；runtime fingerprint 实算 SHA、profile/hash 与 candidate 17/17 相同。 |
| 17 | Windows Word/WPS 人工验收 | ❌ | 17 份待验 DOCX 与 Linux QA 哈希一致；交接单 `WINDOWS_WORD_WPS_AND_REPORT_GROUP_UAT.md:21-41,47-67,81-91` 的环境字段和签署栏为空，17 例 Word/WPS 均为 `NOT_RUN`。 |
| 18 | iyun129 生产部署与 smoke/身份对账 | ❌ | manifest `execution_scope` 明示 `isolated_acceptance_only_no_deployment`；2026-08-09 只读 release status 显示 current release、`REVISION`、process cwd 均为 `fad5c877...`，local/public health HTTP 200。候选未部署，生产未受隔离验收影响。 |

## 4. 数字溯源台账（承重 claim 复算）

复算方式不是重跑完整分析：以新 Linux receipt 病例数组逐项聚合；逐份读取 17 个 QA 的 build provenance、pipeline、visual/pixel 与 renderer；实算 3 个 receipt、17 个 QA 和 Windows source 17 个 DOCX 的 SHA-256；再用只读 SSH 对账 iyun129 runtime fingerprint 和当前生产 `REVISION`。整库测试仍直接在冻结 HEAD 上执行。

| claim | 位置 | 源数据（文件:字段/行） | 复算值 | 一致? |
|---|---|---|---:|---|
| 冻结身份 | 本审计 | `git rev-parse HEAD` | `fd3c98154e031832c8db9d698ddfddd2ad000008` | 是 |
| 冻结 backend 整库回归 | 规格 §5 | `backend/tests/`；命令 `pytest -q -p no:cacheprovider backend/tests` | 755 passed / 4 skipped / 0 failed（6 个弃用 warning） | 是 |
| 329 Linux 合成病例 | spec:63 | `.work/linux_lung_feedback_fd3c981/receipts/lung329_validation.json:5-10,11-130` | cases 7；status/QA PASS 7；failures 0；target expected/runtime 2/2；Part3 0 | 是 |
| 588 Linux 合成病例 | spec:64 | `.work/linux_lung_feedback_fd3c981/receipts/lung588_validation.json:5-10,11-130` | cases 7；status/QA PASS 7；failures 0；target expected/runtime 2/2；Part3 0 | 是 |
| 588 Linux 登记真实输入 | spec:67-68 | `.work/linux_lung_feedback_fd3c981/receipts/lung588_real_validation.json:5-35,37-489` | cases 3；generation/QA PASS 3；页数 78；空白/低内容 0；content failures 0 | 是 |
| 真实输入靶向与免疫计数 | spec:16-17,67 | 同一 real receipt 每例 expected/runtime | targeted 2/2；immune positive 7/7；negative 1/1；B=5/0、C=2/1 | 是 |
| 三组 receipt 冻结身份与状态 | spec:8,63-68 | Linux `receipts/*.json` + manifest `:18-24,123-129,228-234` | receipt 3；full SHA match 3；status PASS 3；case failures 0 | 是 |
| SHA/`source_dirty` 字段载体 | spec:75-76 | Linux `receipts/*.json` 与 `qa/**/*.qa.json` 逐层 key 检查 | receipt full SHA 3/3、dirty key 0/3；QA full SHA 17/17、dirty=false 17/17 | 是；与修订 spec 一致 |
| 17 QA 冻结/clean/视觉状态 | release checklist:306-312 | Linux `qa/{lung329,lung588,real}/*.qa.json` 逐份读取 | QA 17；status PASS 17；SHA match 17；`source_dirty=false` 17；pipeline/visual/pixel PASS 17；blank/low-content 0 | 是 |
| receipt/QA/Windows DOCX 哈希链 | manifest + Windows source | 3 receipt 实算 SHA；17 QA 实算 SHA；17 DOCX 实算 SHA；QA `metrics.output_sha256` | receipt 3/3；QA 17/17；DOCX→同病例 QA 17/17；mismatch 0 | 是 |
| Linux visual 页数 | manifest/QA | 17 QA 的 visual rendered pages/pixel pages | lung329 162；lung588 synthetic 176；real 78；合计 416；空白/低内容 0 | 是 |
| renderer equivalence | release checklist:291-312 | manifest `:310-334` + 17 QA renderer + iyun129 runtime file | candidate exact 17/17；runtime raw SHA `a0e3a1fe...` 一致；profile `reportgen-cjk-font-substitution-v2`、hash `ac68dee9...` 一致 | 是 |
| 正式 UAT gate | spec:84-87 | Linux real receipt `:7-35` + UAT decision register | observed 3；NGS 3/3；product 3/3；verified PD-L1 0/3；reviewed 0/3；BLOCKED | 是 |
| Windows 人工 UAT | release checklist:306-312 | Windows source + `WINDOWS_WORD_WPS_AND_REPORT_GROUP_UAT.md:47-67,81-91` | 待验 DOCX 17；Word PASS 0；WPS PASS 0；两引擎均 NOT_RUN 17；最终签署未填 | 未完成（如实阻断） |
| 生产部署身份/健康 | release checklist:225-249 | manifest `:4` + 2026-08-09 只读 release status | isolated acceptance only；current release/REVISION/process cwd=`fad5c877...`；local/public health HTTP 200；候选未部署 | 候选生产未完成（如实阻断）；现生产健康 |

新 Linux 三份 receipt 的审计时 SHA-256 分别为：329 synthetic `58d8921e0b1369752287d60e50165e10e81625ff421aec8e00b322a82eedc6ba`；588 synthetic `d934c5cf21ff1346f59f77b3bcc9b9309c18b35fd81ac4ce3dade9ba1d1ade6d`；588 real `7fc16a1ba040bc86931a713c332796deffbbcf51e8c1e9c5ba8a5ffc8476a26d`。三值均与 manifest 完全一致。

## 4B. 方法保真表、raw→mapped 与限制登记

### 方法保真五反射

| 模块/子步 | mandated 方法 | 实际 method_status | 判定 | fitness-for-purpose | 证据 |
|---|---|---|---|---|---|
| 靶向规则选择 | Panel scoped、transcript+HGVS exact、临床上下文 exact、未知/缺失失败关闭 | 两事件精确 selector；上下文缺失、非法、不确定、范围外均 blocked；无基因级回退 | 严格完成 | 冻结代码与定向测试适合证明工程门控；不替代病例级医学复核 | `reportgen/rules/targeted_drugs.py:26-127,161-194,408-499`；`backend/tests/test_lung588_phase_c_governance.py:432-554` |
| KB 不可用 fallback | 显式 Panel 只走精确规则，`CtDrug` 仅留给无 Panel legacy | `allow_ctdrug_fallback = targeted_drug_rules is None and not has_kb` | 严格完成 | 能关闭原 P1 | `reportgen/core/_field_mapper_targeted_drugs.py:1040-1050,1146-1172`；定向参数化测试两 Panel 通过 |
| 输入结构 gate | required tables、required columns、required-any；Web 前置 + Generator 二次 gate | 同一中央校验器被两层复用；缺失时不建任务、不写 DOCX；空表头完整可通过 | 严格完成 | 能关闭原 P1 | `reportgen/panels/input_contract.py:72-139`；`backend/app/services/generation_preflight.py:94-102,214-225`；`reportgen/core/report_generator.py:447-461,1004-1073` |
| 免疫事件展示 | lung588 只允许 7 个 transcript+HGVS exact 历史展示事件；329 禁用 | 588 6 positive + 1 negative 均 exact/runtime；329 同行暂存但全局和逐行禁用 | 严格完成 | 仅适合历史展示合同，不适合作为独立治疗建议 | 两套 `rules/biomarkers.yaml:24-118`；冻结精确事件测试通过 |
| 合成边界与视觉 QA | synthetic 只算工程边界，不算真实病例 UAT | Linux 两 receipt 各 7/7；14 QA 全部冻结/clean/pipeline/visual/pixel PASS；`counts_as_real_case_uat:false` | 严格完成 | 适合冻结 Linux 工程边界，不适合正式病例 UAT | Linux synthetic receipts + QA；manifest `:18-227` |
| 真实 NGS pre-UAT | all registered real inputs；结构/product gate 与正式 UAT 分层 | 3/3 NGS/product PASS；PD-L1 使用 synthetic visual QA；formal UAT BLOCKED | 诚实边界 | 适合机器 pre-UAT，不适合医学 UAT/发布 | real receipt `:7-35,39-175,178-326,328-488` |
| 验收产物身份 | receipt/QA/DOCX 必须绑定被冻结提交且源树 clean | receipt 3/3 绑定 full SHA；QA 17/17 full SHA + `source_dirty=false`；receipt/QA/DOCX 哈希链闭合；spec 已准确区分字段载体 | 严格完成 | 适合冻结 Linux acceptance attestation | Linux manifest `:3,18-24,123-129,228-234`；17 QA build provenance；spec `:75-76`；发现 01/12 |
| Linux renderer 等价 | candidate 与 iyun129 runtime engine/profile/hash 一致 | 17 candidate fingerprints 完全一致；manifest runtime raw SHA 与 SSH 实算值一致 | 严格完成 | 适合 Linux 生产等价渲染验收 | manifest `:310-334`；17 QA renderer；只读 SSH runtime fingerprint |
| Windows/正式 UAT/生产发布 | Windows Word/WPS + verified IHC + report-group decisions + immutable deploy/smoke | Windows 从未签署；IHC 0/3、review 0/3；生产仍在旧 SHA | 诚实边界 | **不适合**声明 medical/UAT/production ready，且按 spec 阻断发布 | `docs/spec_lung_feedback_20260809.md:82-92`；Linux real receipt `:7-35`；release checklist `:225-334,362-403` |

### raw→mapped 折进表

本模块不存在把自由文本批量映射到受控词表列的中间表；相关字段是 Web 下拉值或 Excel exact selector，运行时直接逐字比较。为避免把“不存在映射阶段”静默略过，逐 stage 登记如下。`mapping_fidelity.py` 需要 raw/mapped 表格输入，对这些直接值路径不适用；不存在可诚实提供的 raw→mapped TSV。

| stage / 受控字段 | raw 入口 | mapped 输出 | raw→mapped 折进率 | 未知值处理 | 判定/证据 |
|---|---|---|---|---|---|
| 临床上下文四字段 | Web `CONTROLLED_FIELD_OPTIONS` 的原值 | 无重映射，原值逐字传入规则 | N/A（direct exact） | `未明确/待确认/不符合` 或缺失不会命中受控治疗规则 | `backend/app/services/clinical_info_service.py:262-275`；`reportgen/rules/targeted_drugs.py:78-123` |
| PD-L1 result | Web 受控值 | 无重映射，按 contract allowed values 校验 | N/A（direct exact） | 非 allowed value 失败关闭 | 两 Panel `panel.yaml` 的 `pdl1_result.allowed_values`（329 `:158-161`；588 `:179-182`） |
| variant transcript/HGVS | Excel `Transcript/cHGVS/pHGVS_S或A` | 无同义词折叠；版本和 HGVS exact | N/A（direct exact） | 缺列先结构阻断；值缺失/不匹配不命中规则 | 两 Panel `panel.yaml` 输入契约；`reportgen/rules/targeted_drugs.py:161-194` |

### fallback 三分类

| fallback | 类型 | 实际状态 | 判定 |
|---|---|---|---|
| 显式 lung Panel → `CtDrug` | 禁止 fallback | 已禁止，即使 KB unavailable 也不打开 | 严格完成 |
| 无 Panel legacy → `CtDrug` | 授权兼容 fallback | 保留；冻结回归通过 | 授权 override/兼容边界 |
| PD-L1 病例来源 → synthetic image/value | 仅机器/视觉 QA fallback | receipt 明示 `synthetic_visual_qa_only`，formal UAT 阻断 | 诚实边界 |
| Part 3/化疗 → 公共或跨癌种知识 | 禁止 fallback | 两 Panel 关闭并显示禁用状态 | 严格完成 |

### spec/schema 列完整性与 gate 回源

- 两套 Panel 均声明 `Variations/TMB/Msisensor`、`Gene_Symbol/cHGVS/ExistIn552/Transcript` 及 `pHGVS_S/pHGVS_A` 任一列；中央校验器输出仅含配置表/列名，不含文件名或病例值（`reportgen/panels/input_contract.py:72-139`）。
- Web 三条单例生成路径均在 Task 构造前调用 `_raise_required_inputs_if_missing()`（`backend/app/api/report.py:1255-1273,1441-1462,1628-1648`）；生成器在输出路径与模板渲染前执行二次 gate（`reportgen/core/report_generator.py:447-470`）。
- 定向测试复算：缺 Msisensor、Transcript 和两种 protein-HGVS 时得到三个结构 failure；Web async 返回 422、queue 为空、Task 数 0；Generator 返回 `success:false` 和 `output_file:null`。8 个 P1/输入/下载节点全通过。
- UAT gate 从 case registry 回算：policy 要求非空、100% review/pass、0 P0、逐例 verified IHC 来源（`lung588_risk_based_release_policy.yaml:18-31`）；实际三例 decision 均 pending，receipt 正确得到 `BLOCKED`，未把 NGS/product 3/3 PASS 折叠成正式 UAT PASS。
- 字段级身份核对：三份 receipt 均具备 `source_revision/source_commit` 与 `status`，但均无 `source_dirty`；17 份 QA 均在 `build_provenance` 具备 source revision/kind/dirty。Linux acceptance 的 clean-source 结论来自 receipt output hash → QA output hash → DOCX 实算 hash 的 17/17 连接，而不是 receipt 自身字段。

### 限制登记

| limitation | blocker 是否独立核实 | 影响 |
|---|---|---|
| 三个受控真实 Excel 未保留在 `.work/lung588_p1_real_inputs_20260809/`，目录只含脱敏 reports/sidecars/receipt；输入 SHA 仅能与 `scripts/validate_lung588_real_inputs.py:28-60` 的登记清单对账，不能在本次审计重新哈希原始 Excel。 | 是；只读目录枚举确认源文件缺席，符合“不进入 Git/受控外部输入”边界。 | 不否定脱敏 receipt 内部计数，但原始输入真实性为 `NEEDS_HUMAN`。 |
| 病例级真实 IHC 来源未核实。 | 是；receipt 0/3 + 每例 `pdl1_input_provenance: synthetic_visual_qa_only`。 | 正式 UAT 和医学发布阻断。 |
| 报告组三例决策、审核人、日期未登记。 | 是；UAT decision register 三例均 pending/null。 | 正式 UAT 阻断。 |
| Windows Word/WPS 人工签署缺失。 | 是；Windows 交接单 `:25-31` 环境/执行人/日期为空，`:47-67` 共 17 例 Word/WPS 均 `NOT_RUN`，`:81-91` 最终签署未完成。 | Windows 验收和正式发布阻断；不影响已完成的 Linux 工程验收。 |
| 候选尚未生产部署。 | 是；manifest `execution_scope=isolated_acceptance_only_no_deployment`；2026-08-09 只读 `scripts/iyun129_release.sh status` 核对显示 current release、REVISION、process cwd 均一致指向 `fad5c877...`，local/public health 均 HTTP 200。 | `fd3c981...` 不得标为 production PASS/active；同时证明隔离验收未改变当前生产，旧生产仍健康。 |
| `limitation_register.py . --json` 返回 22 条，均指向历史审计文档；过滤当前 spec/两个 lung package 为 0 条。 | 已运行确定性扫描，并对本节实际 blocker 逐条回源，而非把扫描 0 当作无限制。 | 无新增自动扫描缺陷；上述人工登记仍有效。 |

## 5. 两项原 P1 专项结论

### 5.1 显式 Panel 在 KB 不可用时的 CtDrug fail-open

**结论：已关闭。** 证据链有三层：

1. loader 明确规定 `None` 只代表 legacy/no-panel；显式包即使规则缺失/禁用也返回 disabled context（`reportgen/rules/targeted_drugs.py:408-443`）。
2. mapper 只在 `targeted_drug_rules is None and not has_kb` 时允许 `CtDrug`（`reportgen/core/_field_mapper_targeted_drugs.py:1040-1050`）；显式 Panel 仍先查精确规则，最后一层 `CtDrug` 分支也受同一布尔门禁（`:1146-1172`）。
3. 两 Panel 参数化测试强制 KB unavailable，同时提供 BRAF V600E、BRAF D594G 和基因级 sentinel CtDrug；结果只保留 V600E 且 sentinel 不出现（`backend/tests/test_panel_scoped_targeted_drugs.py:264-328`）。本审计定向运行通过；冻结整库也通过。无 Panel legacy 回退回归同时通过。

因此，“P1-1 仍可 fail-open”这一候选问题被反证，见 exonerated 表。

### 5.2 required tables/columns 双重强制

**结论：已关闭。** 中央校验器 `validate_excel_input_contract()` 同时处理 required tables、逐列必需和 required-any，并生成安全载荷（`reportgen/panels/input_contract.py:72-139`）。Web preflight 先调用结构校验并在缺失时返回 missing（`backend/app/services/generation_preflight.py:94-102,214-225`），API 在创建 Task 前调用；`ReportGenerator` 又在 Excel/规则阶段之后、输出/模板阶段之前执行相同校验并在失败时返回 `output_file:null`。

本审计运行：

- `backend/tests/test_panel_input_contract.py` 全部 3 项通过；
- `test_generate_file_async_blocks_missing_lung_selector_columns` 通过，确认 HTTP 422、无入队、Task 数为 0；
- 冻结整库 755 passed/4 skipped。

因此，“P1-2 仍只是声明未执行”被反证。

## 6. Exonerated claims

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung-feedback-20260809-05 | P1 | 显式肺癌 Panel 在 KB unavailable 时仍会从 `CtDrug` 继承未审核基因级药物。 | 冻结源码的 no-panel-only 门禁 + 两 Panel 参数化 sentinel 测试 + 整库测试通过，详见 §5.1。 | REFUTED |
| lung-feedback-20260809-06 | P1 | `required_tables/required_columns` 仍只声明不执行，或只能从 Web 绕过 Generator。 | 中央校验器同时被 Web preflight 和 Generator 使用；缺列端点不建 Task；直接生成失败关闭，详见 §5.2。 | REFUTED |
| lung-feedback-20260809-07 | P1 | 工程 PASS 被写成医学 UAT/生产 PASS。 | spec `:82-92`、real receipt `:7-35` 和 release checklist 均明确区分并自报 BLOCKED。 | REFUTED |
| lung-feedback-20260809-08 | P1 | 本轮共享代码修改已破坏 CRC/legacy backend 回归。 | 冻结 HEAD 上整库 `755 passed, 4 skipped`；定向无 Panel CtDrug legacy、CRC301 basic generation、registry validator 均通过。 | REFUTED |
| lung-feedback-20260809-09 | P1 | 历史十例 acceptance 或旧 targeted-disabled 记录被当成当前 UAT policy。 | 当前 risk-based policy 明确 all available、无固定最小值，并在 `historical_record_policy` 中说明旧 receipt 只保留历史证据（`lung588_risk_based_release_policy.yaml:8-31,53-56`）。 | REFUTED |
| lung-feedback-20260809-10 | P1 | 冻结提交缺少 Linux/LibreOffice 生产等价工程验收。 | Linux manifest、3 receipts、17 QA、17 DOCX 哈希链完整；17/17 renderer 与 iyun129 runtime profile/hash 一致，详见 §4。 | REFUTED |
| lung-feedback-20260809-11 | P1 | iyun129 隔离验收已经把候选部署到生产或影响生产健康。 | manifest 明示 no deployment；只读 release status 显示 current release/REVISION/process cwd 仍为 `fad5c877...`，local/public health HTTP 200。 | REFUTED |

## 7. 结果溯源与 2.5 步骤地图/清爽体检

### 步骤地图

```text
Panel package / panel.yaml
  ├─ input_contract ──> Web generation_preflight ──> Task 创建前阻断
  │                                      └────────> ReportGenerator InputContractValidationStage 二次阻断
  ├─ drugs.yaml + clinical_context.yaml ──> targeted_drugs loader ──> FieldMapper exact-event rows
  │                                                        └─ no-panel-only CtDrug legacy fallback
  ├─ biomarkers.yaml ──> exact transcript/HGVS immune display
  ├─ pdl1_product_contract.yaml + 受控图片 receipt ──> provenance gate ──> DOCX case-image processor
  ├─ template_contract/processors ──> DOCX ──> QA/summary/stage sidecars
  └─ uat policy + report_group_uat_decisions ──> NGS/product pre-UAT ──> formal UAT BLOCKED/PASS
```

### 结构契约检查

- 本项目是报告生成软件平台，不是常规 `results/<NN_step>/` 生信分析项目；本轮可再生验证产物集中在 `.work/`，没有把运行产物混入 `results/`/`figures/`。
- `scripts/analysis/21-24` 均具备强制四行头 `# 步骤 / # 上游 / # 输出 / # 种子`；本轮相关 `scripts/analysis/24_build_lung588_p0_event_review.py:1-4` 输出到 `.work/lung588_p0_event_review/`。
- `scripts/validate_lung588_real_inputs.py:1-5` 同样具备四行头，输出到 `.work/lung588_real_input_audit/validation.json`；当前实际验收目录使用带日期命名，属于 receipt 保存，不是源码交付目录。
- Git 跟踪文件中未发现 `._*`、`.DS_Store`、`__pycache__`、`.pyc` 或 `.log`；真实病例 Excel 未进入 Git。跟踪的 `.xlsx` 是知识库，跟踪的 `.docx` 是 Panel 模板/黄金模板。
- 二次清爽体检结果为：`._*` AppleDouble 文件 0；已知 cache 目录（`.ruff_cache/.mypy_cache/.pytest_cache/__pycache__/htmlcov`）0；上述类别的 Git tracked 路径 0。原 8 个 AppleDouble 与 2 个 Ruff cache 目录由维护方在确认 ignored、0 tracked、非 symlink 后删除；审计方未执行删除。finding 04 已关闭。

## 8. 改进建议与解除阻断条件

1. 对 `.work/windows_uat_fd3c981/source_linux/` 的 17 份已锁定哈希 DOCX 完成 Windows Word/WPS 人工验收，落盘逐例 decision、reviewer、date 和问题记录；在此之前不得把 Linux 视觉 PASS 外推成 Windows PASS。
2. 获取三个真实病例的受控病例级 IHC 来源，逐例验证 assay/profile、source record、specimen 绑定；由报告组登记 decision、reviewer、date、P0 count。只有 gate 从源登记重算为 PASS 才能解除正式 UAT 阻断。
3. 将 UAT/规则说明中的“三个候选/结论”统一为“两个精确事件”，或若“三个”意指三个药物组合，则改写为无歧义的“两个事件、三个治疗组合”。
4. 正式发布必须作为后续独立动作：合并接受的 commit 后执行 iyun129 immutable deploy，再对 current release、`REVISION`、process cwd、local/public health 和 Web/report smoke 逐项留证。当前健康生产 `fad5c877...` 不应因候选隔离验收而被切换或描述为候选已上线。
