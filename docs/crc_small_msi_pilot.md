# CRC Small MSI Pilot

Date: 2026-05-26

## Scope

This branch starts the small CRC MSI panel family after CRC301 local promotion.
No server deployment is part of this work.

The first implementation target is CRC35+MSI:

```text
panel_id candidate: crc_35_msi
template candidate: crc_35_msi_golden_template_v0
branch: codex/panel-crc-small-msi
```

CRC20+MSI remains a sibling candidate, but it should not share the first
CRC35+MSI template without further proof.

## Local Candidate Inventory

Reproducible command:

```bash
python scripts/analyze_crc_small_msi_candidates.py \
  --root "各癌种基因报告近年汇总" \
  --summary-output tmp/panel_inventory/crc_small_candidate_summary.json \
  --local-manifest-output tmp/panel_inventory/crc_small_candidate_manifest.local.json
```

The summary and manifest are ignored local artifacts. The local manifest
contains source paths and heading text, so it must not be committed.

Sanitized aggregate result:

| Product | Readable DOCX Count | Median Table Count | Decision |
|---|---:|---:|---|
| CRC35+MSI | 57 | 22 | first pilot target |
| CRC20+MSI | 31 | 5 | separate sibling evaluation |

## Structure Finding

CRC35+MSI and CRC20+MSI share the same broad concept:

- basic patient/sample information
- detection content
- MSI result and interpretation
- targeted drug result table
- gene/drug interpretation
- appendix and references

They differ enough that they should not be collapsed into one first template:

- CRC35+MSI has a larger table footprint and includes clinical chemotherapy
  assessment in the common structure.
- CRC20+MSI is much more compact and uses a shorter Part 3 section sequence.
- Their section numbering diverges after the MSI section.

## Local Seed Status

A CRC35+MSI scrubbed seed was generated locally under:

```text
tmp/golden_template_seed/crc_35_msi_seed.docx
```

Seed manifest:

```text
tmp/golden_template_seed/crc_35_msi_seed.manifest.json
```

Reproducible command:

```bash
python scripts/build_crc35_msi_seed.py \
  --manifest tmp/panel_inventory/crc_small_candidate_manifest.local.json \
  --output tmp/golden_template_seed/crc_35_msi_seed.docx
```

The seed is not committed. It only confirms that a reviewed CRC35+MSI report can
be scrubbed into a working DOCX source after replacing known patient/sample
tokens. It still needs structural variableization before it can become a panel
template.

Current seed-builder behavior:

- Global replacement is limited to high-specific IDs (`report_number`,
  `sample_id`).
- Short/common values (`patient_name`, `gender`, `age`, `sample_type`,
  `clinical_diagnosis`) are patched by table position or targeted paragraph
  context to avoid corrupting ordinary medical text.
- A final OOXML pass checks headers, footers, and text boxes for high-risk
  residuals.

Latest local check:

```text
global_replacement_count: 2
targeted_scalar_count: 8
high_risk_residual_total: 0
```

## Local Variableization Candidate

The first CRC35+MSI variable map is versioned at:

```text
panels/crc_35_msi/templates/golden_template_v0_variables.yaml
```

It is metadata only; it contains no source paths or patient values.

Local candidate build:

```bash
python scripts/insert_docx_block_marker.py \
  tmp/golden_template_seed/crc_35_msi_seed.docx \
  --output tmp/golden_template_seed/crc_35_msi_seed_part3_marker.docx \
  --start-heading "3.基因变异及相应靶向药物解析" \
  --end-heading "4.附录" \
  --marker __PART3_MARKER__

python scripts/variableize_golden_template.py \
  tmp/golden_template_seed/crc_35_msi_seed_part3_marker.docx \
  --map panels/crc_35_msi/templates/golden_template_v0_variables.yaml \
  --output tmp/golden_template_seed/crc_35_msi_golden_template_v0_candidate.docx

python scripts/scrub_docx_signature_images.py \
  tmp/golden_template_seed/crc_35_msi_golden_template_v0_candidate.docx \
  --output tmp/golden_template_seed/crc_35_msi_golden_template_v0_candidate.docx
```

Latest local variableization result:

```text
operation_count: 21
Part 3 marker: present
high_risk_residual_total: 0
synthetic docxtpl smoke render: pass
runtime context smoke render: pass
signature/media metadata scrub: 2 handwritten-signature-like images replaced
```

Dynamic regions currently covered:

- MSI result summary paragraphs now use `{{ msi_detail_sentence }}`.
- `variants_2_1` uses a row loop.
- `chemotherapy` overview uses a row loop.
- CRC35 pharmacogenomics/detail tables 3-9 and 11-19 use existing CtDrug-backed
  `drug_*` row loops.
- Table 10 (`drug_yilitikang_dose_safety`) is a tentative reuse of
  `drug_yilitikang` and needs a second-case Excel verification before a DOCX
  template is committed.

The runtime smoke render used a local Excel artifact only to verify context
shape. It did not commit or document any source path, patient value, or rendered
report. The checked context contained non-empty `variants_2_1`, the CRC approved
`chemotherapy` list, and populated `drug_*` CtDrug lists.

The reusable verification script is:

```bash
python scripts/verify_crc35_msi_candidate.py \
  --template tmp/golden_template_seed/crc_35_msi_golden_template_v0_candidate.docx \
  --excel <local_excel_a> \
  --excel <local_excel_b>
```

Latest two-case smoke result after signature/metadata scrubbing:

```text
case_count: 2
ok: true
case_01 variants_2_1_rows: 25
case_02 variants_2_1_rows: 62
table10_rows: 50 in both cases
unresolved Jinja/Part3 markers: 0
```

Panel package validation and generation smoke:

```text
python -m reportgen.cli panel validate crc_35_msi --project-root . --format json
status: PASS

python -m reportgen.cli panel validate --project-root . --format json
status: PASS

ReportGenerator.generate(project_type="crc_35_msi") two-case smoke: PASS
panel_package_ok: true
generated unresolved Jinja/Part3 markers: 0
```

## Required Before Committing A Template

- Replace patient/sample/report fields with Jinja variables.
- Replace variant result rows with table loops.
- Replace CRC35 gene/drug interpretation with a dynamic marker.
- Verify the tentative table 10 dose-safety loop against another CRC35 Excel.
- Run a known-token hardcoding scan against the original source values.
- Generate at least two distinct synthetic CRC35 cases.
- Run package validation and QA gates while template status is still `pilot`.

## Current Decision

The structural recipe and scrubbed pilot DOCX template can be committed as a
`crc_35_msi` pilot package. Keep the package in `pilot` status until real CRC35
fixtures are added to the QA gate and a layout review passes.
