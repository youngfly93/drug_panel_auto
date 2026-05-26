# Next Panel Candidate Analysis

Date: 2026-05-26

This analysis uses only sanitized aggregate inventory from the local historical
report corpus. It does not record source filenames, patient identifiers, sample
IDs, report dates, or visible report text.

Source inventory:

```text
tmp/panel_inventory/report_inventory_current.json
```

The source inventory is ignored by Git and should remain local.

## Current Status

CRC301+MSI has been locally promoted to the golden-template default path:

- `crc_301_msi_golden_template_v1`
- `status: active`
- local release gate: `PASS`
- server deployment: not performed

The next panel should therefore test a different reusable template family
without disturbing the server.

## Candidate Comparison

| Candidate Family | Readable DOCX Count | Median Tables | Shared Sections | Main New Work |
|---|---:|---:|---|---|
| CRC35+MSI | 57 | 22 | metadata, detection content, variant table, MSI, drug tips, chemotherapy, gene/drug interpretation | smaller CRC template; optional omission of TMB-heavy layout |
| CRC20+MSI | 31 | 5 | metadata, detection content, variant table, MSI, drug tips, gene/drug interpretation | very compact CRC template; likely distinct from CRC35 layout |
| Lung13 | 241 | 7 | metadata, detection content, variant table, drug tips, guideline, gene/drug interpretation | first non-CRC small targeted template and lung-specific rules |
| Lung62+PD | 55 | 10 | metadata, detection content, variant table, PD-L1, TMB/MSI, immune, drug tips | introduces shared PD-L1 fields and lung PD-specific template blocks |
| Gastric108+MSI | 22 | 26 | metadata, detection content, variant table, TMB/MSI, immune, chemotherapy, drug tips | gastric-specific MSI/targeted rules after CRC families stabilize |
| Endometrial29 molecular typing | 201 | 11 | metadata, QC, molecular typing, MSI, hereditary risk, variant analysis, drug tips | distinct workflow; should be its own package, not a CRC derivative |

## Recommended Next Step

Build the small CRC MSI family first, starting with CRC35+MSI.

Rationale:

- It is close enough to CRC301/CRC358 to reuse the current Excel ingestion,
  CRC enhancer behavior, drug tables, and Part 3 dynamic rendering model.
- It is different enough to validate optional section handling because the
  reviewed reports are smaller than the CRC301/CRC358 golden layout.
- It has enough historical reports for two-case QA and layout comparison.
- It is lower risk than introducing lung-specific rules or PD-L1 before the
  staged generation pipeline is refactored.

CRC20+MSI should be evaluated in the same branch as a sibling template only if
its layout matches CRC35+MSI closely. Its median table count is much smaller, so
it may need a separate template package or a second template under the same
small-CRC family.

## Proposed Branch

```text
codex/panel-crc-small-msi
```

## Proposed Package Direction

Start with one package:

```text
panels/crc_35_msi/
```

Expected identifiers:

```text
panel_id: crc_35_msi
aliases:
  - crc35
  - crc_35
  - crc_35_msi
```

Template candidate:

```text
crc_35_msi_golden_template_v0
```

Keep status `pilot` until at least two distinct synthetic cases pass generation,
QA, and layout review.

## Variable Region Expectations

Reuse from CRC301/CRC358:

- patient/sample/report metadata
- report number/date fields
- detection content wording, moved to panel rules
- variant detail table row loop
- targeted drug tips row loop
- chemotherapy row loop where present
- MSI summary and interpretation
- dynamic gene/drug interpretation marker for Part 3
- signature placeholder/layout processors if the reviewed template contains the
  same detector/reviewer/date block

Likely omit or make optional:

- full TMB section
- large immune biomarker sections
- PD-L1 blocks
- hereditary-risk blocks
- large gene-list appendix layout

Likely new or adjusted:

- compact detection-content paragraph for 20/35 gene products
- smaller table-shape contract
- CRC-small-specific required section set in `qa.yaml`
- product detector rules for "20基因" and "35基因"

## First Implementation Tasks

1. Create a local, ignored candidate manifest under `tmp/panel_inventory/` that
   points to representative CRC35+MSI and CRC20+MSI source DOCX files.
2. Convert one CRC35+MSI reviewed final report into a scrubbed golden seed.
3. Compare its sections and table shapes against CRC301 golden v1.
4. Decide whether CRC20+MSI can share the same package/template family.
5. Add a draft `panel.yaml`, mapping/rule references, and a pilot template.
6. Add two synthetic QA cases before any active/default promotion.
