---
module: report-group-system-uat
agent: codex
identity_kind: git_commit
identity_value: fd3c98154e031832c8db9d698ddfddd2ad000008
audited_at: 2026-08-09
---

# 肺癌 Panel 跨平台与报告组 UAT 执行记录

## 1. 结论

- 冻结候选工程回归：`PASS`。
- iyun129 隔离 Linux/LibreOffice 验收：`PASS`。
- Windows Word/WPS 人工验收：`NOT_RUN`，无可访问且有版本记录的 Windows 审核会话，也无人工签署。
- 报告组真实病例 UAT：`BLOCKED`；病例级 PD-L1 来源为 0/3，完整报告组决定为 0/3。
- 生产发布：`NOT_RUN`；未部署、未切换，不能称为 `active` 或“已上线”。

这不是把外部人工工作留空后宣称完成：可自动执行的工程和 Linux 门禁已完成并留证，必须由 Windows/报告组人员签署的动作已形成逐文件哈希交接单，但当前客观状态仍为发布阻断。

### 共享发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| report-group-system-uat-01 | P1 | 冻结候选缺少 Windows Word/WPS 的实际执行、精确版本和人工签署。 | `.work/windows_uat_fd3c981/WINDOWS_WORD_WPS_AND_REPORT_GROUP_UAT.md:3-7` 的环境、逐文件结果和签署栏均为未填写/NOT_RUN。 | CONFIRMED |
| report-group-system-uat-02 | P1 | 三个受控真实病例没有已核验的病例级 PD-L1 IHC 来源。 | `.work/linux_lung_feedback_fd3c981/receipts/lung588_real_validation.json:uat_readiness.verified_case_pdl1_source_count=0`；逐例 `pdl1_input_provenance=synthetic_visual_qa_only`。 | CONFIRMED |
| report-group-system-uat-03 | P1 | 报告组逐病例 UAT 决定、审核人和日期尚未完成。 | 同一 receipt：`report_group_reviewed_case_count=0`、`formal_uat_status=BLOCKED`；`panels/lung_588_pdl1/uat/lung588_report_group_uat_decisions.yaml` 三例均 pending/null。 | CONFIRMED |
| report-group-system-uat-04 | P1 | 冻结 SHA 缺少生产等价 Linux 渲染证据。 | `.work/linux_lung_feedback_fd3c981/linux_acceptance_manifest_fd3c981.json`：三组 receipt PASS、17/17 QA 绑定冻结 SHA、`renderer_equivalence.status=PASS`。 | REFUTED |

## 2. 自动验收事实

| 项目 | 结果 | 证据 |
|---|---|---|
| 冻结源码 | `fd3c98154e031832c8db9d698ddfddd2ad000008` | Git 冻结提交 |
| 整库后端回归 | 755 passed / 4 skipped / 0 failed | 冻结提交测试记录；独立审计复验 |
| lung329 合成边界 | 7/7 PASS，逐例 QA PASS | `.work/linux_lung_feedback_fd3c981/receipts/lung329_validation.json` |
| lung588 合成边界 | 7/7 PASS，逐例 QA PASS | `.work/linux_lung_feedback_fd3c981/receipts/lung588_validation.json` |
| lung588 受控真实输入 | 3/3 结构、映射、生成与机器视觉 QA PASS；每例 26 页；空白/异常低内容页 0 | `.work/linux_lung_feedback_fd3c981/receipts/lung588_real_validation.json` |
| 冻结身份绑定 | 三份 receipt 与 17 份 QA 均绑定冻结 SHA；`source_dirty=false` | `.work/linux_lung_feedback_fd3c981/linux_acceptance_manifest_fd3c981.json` |
| Linux renderer 等价 | 17/17 候选指纹与 iyun129 runtime 一致；profile=`reportgen-cjk-font-substitution-v2`；mapping SHA=`ac68dee9344ddedefc8a3e579ba75d28657331300c36cb182ca84962dff95afb` | 同上 manifest `renderer_equivalence` |
| 生产影响 | 无部署、无切换、无服务重启；只读核对时 release/REVISION/process cwd 均为 `fad5c87775e1f217fbe13c8181165045841c27ec`，本地/公网 health 均 HTTP 200 | 隔离路径执行，证据带回后临时目录已删除；候选 SHA 未成为 active release |

## 3. Windows Word/WPS 门禁

同一批 Linux 源 DOCX 已放入 `.work/windows_uat_fd3c981/source_linux/`，逐文件 SHA、检查步骤和签署栏位见 `.work/windows_uat_fd3c981/WINDOWS_WORD_WPS_AND_REPORT_GROUP_UAT.md`。

| ID | 当前状态 | 说明 |
|---|---|---|
| RG-H01 至 RG-H08 | NOT_RUN | 需要在 Windows Word/WPS 实际打开、刷新域并人工检查版式与内容。 |
| RG-H09 | BLOCKED | Linux 端已完成；Windows 端尚无执行人与版本证据。 |
| RG-H10 | PARTIAL | Linux 环境、DOCX/QA 哈希和页数齐全；Windows 版本、刷新后哈希与签署缺失。 |

## 4. 报告组真实病例 UAT

| Case | 输入 SHA-256 | Linux 自动 QA | PD-L1 病例来源 | 报告组审核 | 当前结论 |
|---|---|---|---|---|---|
| CASE-LUNG-A | `267a8cbab4d112ea38660dcb1734bb4fb3a7269f50abed6d83a9bf1262ee5646` | PASS | synthetic_visual_qa_only | pending | BLOCKED |
| CASE-LUNG-B | `623c96cee1eb7b16cacb62cababba3b790e82007a00a59d0f159efbe025db000` | PASS | synthetic_visual_qa_only | pending | BLOCKED |
| CASE-LUNG-C | `7b39431044c4a9298f7663c97a47c4df83b5b1e0875d88a64b3e24c05bfa498a` | PASS | synthetic_visual_qa_only | pending | BLOCKED |

UAT gate 复算：observed=3，NGS structure=3/3，PD-L1 product contract=3/3，verified case-specific PD-L1 source=0/3，report-group reviewed/pass=0/3，P0=0，`formal_uat_status=BLOCKED`。阻断码为 `PDL1_CASE_SOURCE_NOT_VERIFIED` 与 `REPORT_GROUP_UAT_INCOMPLETE`。

## 5. 解除阻断所需的外部签署

1. 在受控 Windows 环境用 Word 和 WPS 审核交接包，记录精确版本、源/刷新后 SHA、页数、逐文件结果、缺陷和审核人日期。
2. 为 CASE-LUNG-A/B/C 逐例提供并核验真实 IHC 来源、检测产品/方案与标本绑定；不得继续使用机器视觉用合成值作为医学 UAT 输入。
3. 报告组逐例填写 decision、reviewer、reviewed_at、p0_count；三例全部通过且 P0=0 后重跑 UAT gate。
4. 上述两项通过后才能另行申请生产发布；发布需走 immutable release、健康/进程/REVISION/公网 smoke 总闸。
