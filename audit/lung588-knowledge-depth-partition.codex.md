---
module: lung588-knowledge-depth-partition
agent: codex
identity_kind: git_commit
identity_value: 57eeccb81e0946b8d3071f22dee07524d619bde1
---

# 肺癌588知识深度分层审计（Codex）

本审计只覆盖冻结业务提交
`57eeccb81e0946b8d3071f22dee07524d619bde1`。目标是验证固定蛋白/结构域
内容不再被误当作变异级医学叙述，并将588个基因形成可追溯、患者不可见的
分批二审工作表；本提交不新增医学结论，不启用肺癌第三部分，也不部署生产。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-knowledge-depth-partition-01 | P0 | 只要`mutation_analysis`非空，就证明存在独立的变异级解析。 | `reportgen/knowledge/gene_knowledge.py`新增`mutation_narrative`，只移除渲染器生成的规范结构域前缀；`knowledge_coverage.yaml`要求肺588单独校验非结构域叙述。 | REFUTED |
| lung588-knowledge-depth-partition-02 | P0 | 固定结构域文字可以单独满足肺588的变异解析门禁。 | `reportgen/knowledge/release_gate.py`在该Panel合同开启时改用`missing_mutation_narrative_genes`；固定提交strict gate仍报告247个非结构域叙述缺口。 | REFUTED |
| lung588-knowledge-depth-partition-03 | P0 | 这次分层已经把588个基因都判成医学通过。 | 二审manifest共588行、25批，所有批次`secondary_review_completed_count=0`、`patient_visible_allowed_count=0`。 | REFUTED |
| lung588-knowledge-depth-partition-04 | P1 | 551个结构域缺口与247个叙述缺口是互不相关的两组。 | 固定提交清单显示：247个同时缺叙述和结构域，304个有叙述但缺结构域，37个两者均有，0个只有结构域而无叙述。 | REFUTED |
| lung588-knowledge-depth-partition-05 | P1 | 现有341个非空叙述都属于肺癌特异内容。 | 341个非空叙述中仅32个通过当前特异性检查，309个仍为通用fallback。 | REFUTED |
| lung588-knowledge-depth-partition-06 | P1 | 分批清单包含真实患者姓名或样本号。 | 输出只保留CASE事件数量、候选数量、知识文本及内容哈希；递归扫描未发现`LZ`样本号或`patient_name`字段。 | REFUTED |
| lung588-knowledge-depth-partition-07 | P1 | 新增质量字段改变了既有CRC Word内容。 | `mutation_analysis`字段与模板接口保持不变，新增字段只供质量侧使用；固定SHA release-check中CRC301/358参考、候选和重复diff均PASS。 | REFUTED |
| lung588-knowledge-depth-partition-08 | P1 | 该提交已经达到肺588生产发布条件。 | strict gate仍有247/247/551三类阻断，PD-L1实际方案二审和病例UAT仍未完成；未执行部署。 | REFUTED |

## 方法保真与边界

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-knowledge-depth-partition-M01 | Word兼容字段必须保持不变 | `mutation_analysis`继续含结构域+叙述；仅增加不被旧模板消费的`mutation_narrative` | FAITHFUL | `gene_knowledge.py`最终section构造 |
| lung588-knowledge-depth-partition-M02 | 不能用宽泛正则误删医学叙述 | 只在最终文本等于规范结构域，或以“结构域+换行”为精确前缀时分离；中间相似文字不删除 | FAITHFUL | `_mutation_narrative_from_composed`实现与正反例测试 |
| lung588-knowledge-depth-partition-M03 | 肺癌深度门禁不得无意改变CRC策略 | 分离门禁由Panel合同显式启用；未启用Panel保持原`missing_analysis_genes`行为 | FAITHFUL | `knowledge_coverage.yaml`与`release_gate.py`条件分支 |
| lung588-knowledge-depth-partition-M04 | 审核队列必须覆盖完整分母且可复现 | 588行按P0–P4和Panel顺序确定性分成25批，每批不超过25行；每行含内容哈希、来源状态和二审空栏 | FAITHFUL | `scripts/analysis/23_profile_lung588_medical_knowledge.py` |
| lung588-knowledge-depth-partition-M05 | 工程可用不等于医学发布 | active Panel工程门禁PASS；肺588strict gate保持FAIL，二审与患者可见状态保持关闭 | HONEST_BOUNDARY | 固定提交release-check、strict gate及batch manifest |

## 冻结凭据

- 被审业务提交：
  `57eeccb81e0946b8d3071f22dee07524d619bde1`；开审时业务工作树干净。
- 固定提交知识深度清单 SHA256：
  `551db382758cd7852cdc3831d381175755397c50e4a7de45b841bfe150c57e75`。
- 固定提交二审批次manifest SHA256：
  `c073c6c294df55ca2c7d2e56b9800b858239abe5588b16ef0406159a2fd09313`。
- 固定提交二审总表 SHA256：
  `8e73021c1e7ddeab558b8bd3282f03b5412b5357ed5ccb6d3436f6e86492bf97`。
- 肺588 strict gate按预期FAIL，恰有
  `RUNTIME_GENE_COVERAGE_GAP=247`、
  `RUNTIME_MUTATION_ANALYSIS_GAP=247`和
  `RUNTIME_FIXED_DOMAIN_GAP=551`；第二项明确为non-domain narrative。
  收据 SHA256：
  `be1d69b487e07daf2b41f852972099fa772e2437460e9bd102e801b468c7cb1d`。
- 聚焦肺癌治理复测：`15 passed, 0 failed`。
- 固定提交release-check：PASS；16项工程检查PASS、1项legacy跳过，
  GitHub远端检查按声明未执行。QA报告 SHA256：
  `ea1adf8059e6f3d4c85cb7f8927e6523ef400f48e0ce1937d11094e163ce510c`。
- release-check回归子集：
  `291 passed, 2 skipped, 0 failed`；CRC358/301与肺部甲基化金标准均PASS。
- 本提交未新增、替换或批准任何患者可见医学叙述；未执行Linux候选渲染、
  正式病例UAT、iyun129部署或部署后活实例验收。

## 分层裁决

- 结构域与变异叙述分离机制：**PASS（工程）**。
- 588行深度清单与25批二审工作表：**PASS（工程）**。
- P0真实病例/候选基因二审：**PENDING（19行）**。
- 247个缺失叙述与309个通用fallback医学完善：**BLOCKED**。
- 551个固定结构域候选补充：**BLOCKED，待官方来源候选和映射审核**。
- 肺588整体医学发布：**BLOCKED**。
- iyun129生产部署：**NOT READY / NOT DEPLOYED**。
