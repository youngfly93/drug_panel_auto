# Panel Migration Roadmap

Last updated: 2026-05-26

This roadmap describes how to turn the historical reviewed Word reports into
versioned ReportGen panel packages without rewriting report layouts from
scratch.

## Version Control Rules

- Never commit raw historical reports, generated customer reports, patient
  files, source filenames, sample IDs, report dates, signatures, or tunnel
  credentials.
- Keep local corpus-derived outputs under `tmp/panel_inventory/` unless they
  are explicitly sanitized documentation.
- Commit panel work in small reviewable steps:
  1. privacy guardrails and sanitized inventory tooling;
  2. panel package skeleton;
  3. cleaned golden seed and variable map;
  4. rules and knowledge-base updates;
  5. QA/golden-case validation and promotion.
- Do not promote a template to `active` until at least two distinct cases pass
  generation and QA.
- Keep `ReportGenerator.generate()` externally compatible until the staged
  pipeline migration explicitly changes that contract.

## Branch Plan

Use focused branches so each panel can be rolled back independently:

```text
codex/panel-inventory-roadmap
codex/panel-crc301-golden
codex/panel-crc-small-msi
codex/panel-lung13-golden
codex/panel-lung62-pd-golden
codex/panel-endometrial29-golden
codex/panel-gastric108-msi-golden
codex/panel-pancancer-large-golden
```

These branches should remain compatible with the existing platform migration
plan:

```text
codex/panel-platform-m6-pipeline
  -> codex/panel-platform-m7-rule-engine
  -> codex/panel-platform-m8-template-processors
  -> codex/panel-platform-m9-web-production
```

Panel migrations can proceed incrementally before or alongside M6, but should
not introduce a separate rendering framework.

## Package Version Lifecycle

Use the same lifecycle for every new panel package:

| Version | Status | Meaning |
|---|---|---|
| `0.1.0` | `draft` | Package skeleton, detector aliases, preliminary contract. |
| `0.2.0` | `pilot` | Cleaned golden template, variable map, rules, first generation path. |
| `0.3.x` | `pilot` | Additional cases, QA fixes, knowledge-base review. |
| `1.0.0` | `active` | Two-case validation, package validation, diff/QA gates, Web smoke path. |

Template IDs should include the panel and source generation, for example:

```text
crc_301_msi_golden_template_v0
lung_13_targeted_golden_template_v0
lung_62_pd_golden_template_v0
endometrial_29_molecular_golden_template_v0
```

## Standard Panel Build Flow

1. Select a reviewed final DOCX as the layout source of truth.
2. Build a cleaned seed with `scripts/build_golden_template_seed.py`.
3. Create `panels/<panel_id>/templates/*_variables.yaml`.
4. Apply structural variableization with
   `scripts/variableize_golden_template.py`.
5. Define `panel.yaml`:
   - aliases and detector rules;
   - input contract;
   - template contract;
   - processor list;
   - golden cases.
6. Put medical/business wording in `panels/<panel_id>/rules/*.yaml` or curated
   knowledge bases, not renderer branches.
7. Add at least two tests or QA cases:
   - one seed-derived case;
   - one distinct case that exercises different variants/biomarkers.
8. Run package and generation gates before promotion.

## Required Gates

At minimum:

```bash
python -m reportgen.cli panel validate --project-root . --format json
```

For promoted panels, add:

```bash
python -m reportgen.cli qa gate --panel <panel_id> --output-root /tmp/reportgen-<panel_id>-qa
```

When upload, detection, generation, or frontend behavior changes:

```bash
make web-smoke
```

Use layout/visual checks for blank pages, table widths, headers, footers,
signatures, TOC, or Word refresh behavior.

## Migration Order

### 1. CRC301 Golden Template

Rationale:

- largest historical product group;
- already has an active package;
- uses the same CRC enhancer and most CRC358 variable regions;
- best first test of converting another reviewed final report into a golden
  template without changing Excel format.

Expected work:

- completed locally on `codex/panel-crc301-golden`;
- current local default is `crc_301_msi_golden_template_v1`;
- `crc_301_msi_standard_v1` is retained as rollback;
- server deployment has not been performed while the server is under external
  testing.

### 2. Small CRC MSI Family

Products such as CRC20/CRC35 need a smaller template contract:

- patient/sample metadata;
- detection content;
- variant detail table;
- other potential benefit drugs;
- MSI extension;
- optional chemotherapy;
- gene/drug interpretation.

They should not inherit the full CRC358 TMB/immune layout when the reviewed
report does not contain those sections.

### 3. Lung Small Targeted Family

Products such as Lung13/Lung20 need a lung-specific template:

- variant detail and drug tips;
- NCCN/approved routine target genes;
- lung-specific important gene interpretation;
- no required TMB/MSI unless present in the product.

This should introduce a lung enhancer or a generic oncology enhancer profile,
not CRC-specific business branching.

### 4. Lung PD-L1 Family

Products such as Lung62+PD and Lung329+PD introduce PD-L1:

- PD-L1 test content;
- PD-L1 result block;
- lung variant/drug tables;
- optional TMB/MSI/immune sections for large products.

PD-L1 should be added to the shared normalized context as optional fields, then
selected by panel templates.

### 5. Endometrial Molecular Typing 29-Gene Panel

This is a distinct workflow:

- QC information;
- molecular typing result;
- MSI result;
- hereditary tumor risk;
- gene variant analysis;
- targeted/immune drug interpretation.

Build it as its own package rather than as a CRC-style derivative.

### 6. Gastric MSI And Pan-Cancer Large Panels

Gastric MSI panels can reuse much of the targeted/MSI layout with
gastric-specific rules. Pan-cancer large panels should wait until the shared
context model supports optional TMB, MSI, PD-L1, hereditary risk, chemotherapy,
and drug metabolism cleanly.

## Knowledge Base Workstream

Create a shared reviewed cancer-gene-drug data layer rather than copying
report text into templates:

```text
data/knowledge_bases/processed/
panels/<panel_id>/rules/
```

The curated records should include source/provenance and review status. Panel
rules should filter or override shared records by cancer type and panel scope.

## Current First Action

CRC301 local promotion is complete and documented in:

```text
docs/crc301_local_promotion_release_note.md
```

The next implementation step is `codex/panel-crc-small-msi` scope:

- build a local candidate manifest for CRC35+MSI and CRC20+MSI;
- select a reviewed CRC35+MSI final DOCX as the layout source of truth;
- compare its variable regions against CRC301 golden v1;
- create a pilot `crc_35_msi` panel package without changing server state.

Candidate rationale is tracked in:

```text
docs/panel_next_candidate_analysis.md
```
