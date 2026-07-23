---
module: lung588-domain-candidate-catalog
agent: codex
identity_kind: git_commit
identity_value: 89f19ed5e590dc7030847f7be644d64b9af1cadc
---

# 肺癌588固定结构域候选库审计（Codex）

本审计只覆盖冻结业务提交
`89f19ed5e590dc7030847f7be644d64b9af1cadc`。目标是验证551个固定
蛋白/结构域缺口是否形成完整、可重复、来源明确的二审候选，并确认全部候选
在报告组二审前保持运行关闭。本提交不新增药物、疗效、耐药或适应证结论。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung588-domain-candidate-catalog-01 | P0 | 551条官方候选已经等同于551条运行知识。 | 候选catalog默认`review_status: needs_review`、`runtime_eligible: false`、`secondary_review_status: pending_report_group_review`；固定提交运行覆盖仍为37/588。 | REFUTED |
| lung588-domain-candidate-catalog-02 | P0 | 候选库可以直接进入患者第三部分。 | `panels/lung_588_pdl1/panel.yaml`仍关闭`part3_knowledge`；provider依据治理状态跳过全部551行；strict gate仍报告551个运行结构域缺口。 | REFUTED |
| lung588-domain-candidate-catalog-03 | P0 | 多个reviewed UniProt结果时可无痕选第一个。 | 15个多候选基因均记录selected、alternatives、选择依据和待二审状态；其中CDKN2A、CUX1、GNAS、RBM10标记为必须核对转录本/蛋白产物。 | REFUTED |
| lung588-domain-candidate-catalog-04 | P1 | 所有588个基因都应被当作蛋白编码基因描述结构域。 | TERC以NCBI Gene来源明确记录为非编码RNA，不虚构蛋白全长或结构域；其余550个缺口解析为reviewed UniProt蛋白。 | REFUTED |
| lung588-domain-candidate-catalog-05 | P1 | 候选库仍有无法解析或没有有效结构特征的基因。 | 固定来源构建收据显示`unresolved_genes=[]`、`featureless_genes=[]`，生成551行。 | REFUTED |
| lung588-domain-candidate-catalog-06 | P1 | 候选文本夹带药物、疗效或癌种治疗声明。 | 结构化扫描未命中患者、样本、获益、耐药、敏感、疗效、治疗、用药或适应证关键词；`drug_sections`为空。 | REFUTED |
| lung588-domain-candidate-catalog-07 | P1 | 候选文件依赖一次性网络顺序，不能重建。 | 同一提交使用缓存的规范化官方响应重建两次，且与跟踪文件字节SHA256完全一致。 | REFUTED |
| lung588-domain-candidate-catalog-08 | P1 | 551行候选会改变CRC301/358现有报告。 | 规则按`panels: [lung_588_pdl1]`隔离且运行关闭；固定SHA release-check中CRC301/358参考、候选和重复diff均PASS。 | REFUTED |
| lung588-domain-candidate-catalog-09 | P1 | 本提交已完成肺588医学发布。 | 247个无运行解释、247个无非结构域叙述和551个无运行结构域仍阻断；PD-L1产品二审和病例UAT未完成。 | REFUTED |

## 方法保真与边界

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| lung588-domain-candidate-catalog-M01 | 结构域事实须来自官方蛋白资源并记录版本 | 使用reviewed human UniProt `2026_02`，无合适UniProt feature时查询InterPro；逐行保存accession和官方URL | FAITHFUL | catalog `source`与每行`source_refs` |
| lung588-domain-candidate-catalog-M02 | 不能用空泛文字隐藏未解析项 | 构建器只在有蛋白长度及有界feature时生成蛋白行；未解析和无feature进入收据并导致非零退出 | FAITHFUL | `scripts/analysis/21_build_crc358_domain_catalog.py` |
| lung588-domain-candidate-catalog-M03 | 非编码基因必须独立处理 | TERC明确为不适用蛋白结构域，保存NCBI Gene来源 | FAITHFUL | candidate catalog中的TERC行 |
| lung588-domain-candidate-catalog-M04 | 一审候选与二审运行知识必须分层 | `--candidate-only`生成needs_review且runtime=false；二审表同时显示候选文本、来源、accession和空的二审栏 | FAITHFUL | 构建器、catalog治理默认值、知识二审TSV |
| lung588-domain-candidate-catalog-M05 | 多产物基因必须显式暴露映射风险 | 同义词碰撞与同基因多reviewed产物分别记录；4个同基因多产物候选标为转录本/产物强复核 | FAITHFUL | `accession_selection`结构 |
| lung588-domain-candidate-catalog-M06 | 候选可得率不得冒充运行覆盖率 | 清单分别记录候选551、运行候选0、运行结构域37、运行或候选合计588；strict gate保持运行FAIL | HONEST_BOUNDARY | 固定提交清单与strict gate |

## 冻结凭据

- 被审业务提交：
  `89f19ed5e590dc7030847f7be644d64b9af1cadc`；开审时业务工作树干净。
- 候选catalog SHA256：
  `b5587a8386f8515d8a006bb53ccf4a2a26a33d070b792fdc48106716508f8d06`；
  固定提交重建文件与跟踪文件字节一致。
- 官方来源构建收据 SHA256：
  `3130b70dc6ba5f2a7b6d7ef1b919b264b8df7039ea39d44247b9ee0641570325`。
- 固定提交知识深度清单 SHA256：
  `affe71edcf458efc9649125ff68745d1daa224f4a41112f68e0d06dbf395789f`。
- 固定提交二审批次manifest SHA256：
  `845aa7b11452b5358343485d4fde1ca30d9eda025c5f3bc0f51bfbb067629ca7`。
- 固定提交二审总表 SHA256：
  `04f3195342ce2957717f89e4dd091c136f7d4550776dd34b8f8c7ff6e3aa3828`。
- 肺588 strict gate按预期FAIL，仍恰有247/247/551三类运行问题；收据
  SHA256：
  `cff079b68428d75de903062555702cab2a5533f7e37549072b64600ce8d0ba06`。
- 肺癌合同与治理聚焦回归：`28 passed, 0 failed`。
- 固定提交release-check：PASS；16项工程检查PASS、1项legacy跳过，
  GitHub远端检查按声明未执行。QA报告 SHA256：
  `7fcc1760c791a0a1578d701377c6b00952ea543403bd50020b69e2de4180f72c`。
- release-check回归子集：
  `291 passed, 2 skipped, 0 failed`；CRC358/301与肺部甲基化金标准均PASS。
- 未执行候选医学二审、候选运行启用、肺588患者可见第三部分、Linux病例
  渲染、正式病例UAT、iyun129部署或部署后活实例验收。

## 分层裁决

- 551个官方结构域候选的来源与完整性：**PASS（Codex一审）**。
- 候选可重复生成：**PASS**。
- 候选运行关闭：**PASS**。
- 15个多候选accession映射：**PENDING（二审）**。
- 4个转录本/蛋白产物边界：**BLOCKED，未核对前不得运行**。
- 其余候选报告组二审：**PENDING（551行总表内）**。
- 肺588运行结构域覆盖：**BLOCKED（37/588）**。
- 肺588整体医学发布与iyun129部署：**NOT READY / NOT DEPLOYED**。
