# Historical Panel Report Inventory Audit

Last updated: 2026-05-26

This audit summarizes the local historical Word report corpus under
`各癌种基因报告近年汇总/` and compares its structural patterns with the current
CRC358 golden template. It is intentionally sanitized: no source report
filenames, patient names, sample IDs, report dates, or individual visible text
samples are recorded here.

## Scope And Privacy

- Source corpus: local historical final DOCX reports grouped by cancer type.
- Baseline template:
  `panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx`.
- Raw reports are local development references only and must not be committed.
- The corpus path is ignored in `.gitignore`.
- Reproducible inventory script:
  `scripts/audit_panel_report_inventory.py`.
- Local generated audit outputs should stay under `tmp/panel_inventory/`.

## Method

The audit reads `word/document.xml` directly from DOCX files instead of opening
them through Word or `python-docx`. This is more tolerant of old Word packages
whose relationship metadata may be incomplete. The script records aggregate
counts, table counts, paragraph counts, and section-feature flags only.

Suggested command:

```bash
python scripts/audit_panel_report_inventory.py \
  --root "各癌种基因报告近年汇总" \
  --output tmp/panel_inventory/report_inventory.json
```

## Corpus Summary

The current local corpus contains 1,571 real files after excluding macOS
metadata files:

| Extension | Count |
|---|---:|
| `.docx` | 1,563 |
| `.doc` | 7 |
| `.lnk` | 1 |

All 1,563 DOCX files were readable through low-level XML extraction in the
current audit.

Top cancer directories by real file count:

| Cancer Directory | Count |
|---|---:|
| 肠癌 | 603 |
| 肺癌 | 487 |
| 妇科肿瘤-子宫内膜癌 | 203 |
| 妇科肿瘤-卵巢癌 | 134 |
| 胃癌 | 49 |
| 胆管、胆囊癌 | 22 |
| 胰腺癌 | 17 |
| 肝癌 | 16 |
| 神经内分泌癌 | 8 |
| 妇科肿瘤-外阴癌 | 6 |
| 妇科肿瘤-乳腺癌 | 5 |
| 食管癌 | 5 |
| 黑色素瘤 | 4 |
| 膀胱癌 | 2 |
| 头颈癌 | 2 |

## Product Families

The product-level structure strongly suggests template families rather than a
unique template for every product name.

| Family | Representative Products | Template Impact |
|---|---|---|
| CRC large MSI/TMB/immune | CRC358, CRC301, CRC166, CRC208, CRC733, CRC1350 | Closest to current CRC358 golden flow. Reuse the same staged variableization model. |
| CRC small MSI/targeted | CRC20, CRC35 | Smaller CRC template with variant/drug/MSI sections; not the full CRC358 immune/TMB layout. |
| Lung small targeted | Lung13, Lung20 | Separate lung-specific template family; do not force the CRC template. |
| Lung PD-L1 panels | Lung62+PD, Lung158+PD, Lung329+PD | Needs PD-L1 result blocks plus lung-specific drug/gene rules. |
| Endometrial molecular typing | Endometrial molecular typing 29-gene report | Needs QC, molecular typing, MSI, hereditary-risk, and gene-analysis sections. |
| Gastric MSI panels | Gastric108+MSI, Gastric358+MSI | Similar to medium MSI/targeted reports, with gastric-specific knowledge and guideline rules. |
| Pan-cancer large panels | Pan-cancer150, Pan-cancer1350 | Broad TMB/MSI/immune/drug/hereditary sections; migrate after narrower families stabilize. |

## Variable Region Comparison To CRC358 Golden

The current CRC358 golden template already proves the correct authoring model:
fixed cell variables, paragraph variables near stable headings, table row loops,
and one structured dynamic narrative region for Part 3.

| Variable Region | CRC358 Golden Status | New Panel Handling |
|---|---|---|
| Patient/sample/report metadata | Already variableized | Reuse shared context fields. |
| Detection content/project scope | Partly template-specific | Move wording to panel rules. |
| Result summary | Already generated for CRC | Add panel-specific summary builders/rules. |
| Variant detail table | `variants_2_1` row loop | Reuse table-loop model; adjust columns/filtering per panel. |
| Targeted drug tips | `targeted_drug_tips` row loop | Reuse shared knowledge base plus cancer filters. |
| NCCN/CSCO/guideline rows | `nccn_results` row loop | Panel-specific guideline rule files. |
| TMB/MSI/immune sections | Supported in CRC358 | Optional by panel; omitted for small targeted-only reports. |
| PD-L1 | Not a dedicated CRC358 block | Add shared PD-L1 fields and PD-specific template loops. |
| Chemotherapy | `chemotherapy` row loop | Reuse for CRC and large panel families. |
| Gene/drug interpretation | Dynamic Part 3 marker | Expand shared cancer-gene-drug knowledge source. |
| Hereditary-risk section | Not primary CRC358 flow | Required for endometrial and pan-cancer large panels. |
| Molecular typing/QC | Not primary CRC358 flow | Required for endometrial molecular typing panel. |

## Excel Format Impact

Current evidence supports keeping one shared Excel ingestion path:

- The historical folder is a Word report corpus, not an Excel corpus.
- The reporting group stated that Excel formats are the same.
- Existing `config/mapping.yaml` already covers shared sheets such as
  `Variations`, `TMB`, `Msisensor`, `QC`, `Cnv`, `Fusion`, `HLA`, `CtDrug`,
  `基因临床解读`, and related drug tables.
- New panels should extend shared optional fields only where needed, especially
  PD-L1 and molecular typing fields, instead of creating per-cancer Excel
  readers.

The correct split is therefore:

- shared Excel reader and shared normalized report context;
- panel-specific detector aliases;
- panel-specific template contracts;
- panel-specific rules and knowledge filters.

## Knowledge Base Direction

The reporting group asked to extract cancer, gene, and drug sections into a
summary database. The repo already has this direction:

- `data/knowledge_bases/processed/gene_knowledge_db.xlsx`
- `data/knowledge_bases/processed/targeted_drug_db_public.xlsx`
- `data/knowledge_bases/processed/immune_gene_list_public.xlsx`
- panel-local rule overlays such as
  `panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml`

New extraction should produce reviewed, provenance-bearing records keyed by:

- cancer type or panel family;
- gene;
- cHGVS/pHGVS or alteration class where available;
- drug;
- benefit/caution/immune/chemo category;
- evidence level and source;
- review status.

Raw extracted text should stay local until reviewed. Commit only curated,
de-identified knowledge records and extraction scripts.

## Immediate Migration Candidates

1. CRC301 golden template migration.
   It is the largest historical group and shares the CRC358 architecture.
2. CRC35/CRC20 small CRC family.
   This validates optional omission of TMB/immune-heavy sections.
3. Lung13 small targeted family.
   This creates the first non-CRC template family.
4. Lung62+PD.
   This introduces PD-L1 handling before the larger lung329+PD template.
5. Endometrial molecular typing 29-gene report.
   This introduces molecular typing, QC, MSI, and hereditary-risk sections.

