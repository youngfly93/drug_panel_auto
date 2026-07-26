# 肺癌329基因+PD-L1 受控试运行发布规格

日期：2026-07-25
Panel：`lung_329_pdl1`
发布层级：`pilot`（不是主动医学发布）

## 1. 产品决策

肺癌329先以单病例受控试运行方式进入 iyun129。该层级只允许报告结构化
分子检测事实，并逐病例转录有来源记录的 PD-L1 TPS、CPS 和结果判定。
它不输出患者级靶向药物、免疫相关基因、化疗 PGx 或第三部分医学解释。

本规格取代旧文档中的开发期 C-beta 状态描述；旧文档仅保留为历史记录，
不得用作当前发布结论。

## 2. 允许与禁止

允许：

- 单份 Excel 生成；
- Ⅰ/Ⅱ/Ⅲ类变异、TMB、MSI 等结构化检测事实；
- 逐病例表单录入 PD-L1 结果及其来源记录、标本和图像处置；
- 报告组审核后下载。

禁止：

- 批量生成或整批共享 PD-L1 字段；
- 从 NGS Excel 推导 PD-L1；
- 推断抗体克隆、染色平台、显色系统或不同检测方案等效；
- 自动生成患者级靶向、免疫或化疗用药结论；
- 调用未经肺癌医学审核的基础库/CRC 知识生成第三部分解释；
- 未经人工复核直接下载受控试运行报告。

## 3. PD-L1 输入合同

每个病例必须同时提供：

- `pdl1_tps`
- `pdl1_cps`
- `pdl1_result`
- `pdl1_assay_profile_id`
- `pdl1_source_record_id`
- `pdl1_source_record_date`
- `pdl1_specimen_id`
- `pdl1_image_disposition`

当前仅开放 `legacy_unspecified_ihc_transcription_v1`：原值转录并明确显示
检测方法信息未完整提供。它不支持治疗适应证推断。

## 4. 发布阻断门禁

候选提交必须同时满足：

1. Panel 包校验 PASS，规则来源可追溯；
2. 默认模板 SHA256 固定，硬编码病例扫描为 0，历史病例图像及已删除章节
   的孤儿媒体为 0；旧迁移模板不注册、不跟踪、也不进入生产发布包；
3. 7 个脱敏合成边界病例全部生成成功，覆盖 PD-L1 0/1/49/50/100、
   MSS/MSI-H、TMB 边界和多变异长表；
4. 药物行、第三部分患者级知识和免疫分类行均为 0；
5. 既有 CRC301/CRC358 金标准及全量回归无倒退；
6. 前端只显示“单份受控试运行”，批量入口不存在，后端批量 API 同时阻断；
7. Linux LibreOffice 全视觉 QA PASS；
8. iyun129 发布前备份、精确 Git 身份、健康检查和回滚点齐全；
9. 部署后验证未审核下载阻断、审核后可下载、跨病例无残留。

合成边界套件只计工程覆盖，不冒充真实病例 UAT；本项目不设置人为的固定
“10 例”数量门槛。若未来启用患者级医学知识或治疗结论，必须另行完成事件级
医学审核和相应真实病例验收。

## 5. iyun129 范围

启用：`crc_358_msi`、`lung_329_pdl1`（受控试运行）。
保持禁用：`crc_301_msi`、`lung_588_pdl1`、`lung_methylation`。

三层范围必须一致：

```text
REPORTGEN_DISABLED_PROJECT_TYPES=crc_301_msi,lung_588_pdl1,lung_methylation
RG_WEB_DISABLED_PROJECT_TYPES=crc_301_msi,lung_588_pdl1,lung_methylation
VITE_DISABLED_PROJECT_TYPES=crc_301_msi,lung_588_pdl1,lung_methylation
```

模板迁移工具只接受显式提供的受控外部源文件，并校验固定源哈希。历史迁移
源不得复制进 Git 或生产 release；运行时仅注册上述受治理的 v2 模板。

## 6. 后续晋级条件

只有在报告组确认真实抗体克隆、检测平台、评分体系和病例来源合同，并完成
相关医学规则的逐条复审后，才可提出从 `pilot` 晋级。晋级必须建立新的冻结
提交、审计和发布基线，不能直接修改本受控层级的语义。
