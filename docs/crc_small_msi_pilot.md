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

The seed is not committed. It only confirms that a reviewed CRC35+MSI report can
be scrubbed into a working DOCX source after replacing known patient/sample
tokens. It still needs structural variableization before it can become a panel
template.

## Required Before Committing A Template

- Replace patient/sample/report fields with Jinja variables.
- Replace variant result rows with table loops.
- Replace CRC35 gene/drug interpretation with a dynamic marker.
- Decide how to model the chemotherapy/pharmacogenomics tables without keeping
  case-specific genotypes or drug result rows.
- Run a known-token hardcoding scan against the original source values.
- Generate at least two distinct synthetic CRC35 cases.
- Run package validation and QA gates while template status is still `pilot`.

## Current Decision

Proceed with a draft `crc_35_msi` package only after the chemotherapy and
pharmacogenomics variable regions are mapped. Do not commit the scrubbed seed as
a reusable template until those dynamic regions are removed or looped.
