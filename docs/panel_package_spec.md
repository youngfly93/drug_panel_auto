# Panel Package Directory Specification

M5.1 defines the minimum package contract for adding or promoting a panel.
The goal is to make every panel self-describing enough that the report
pipeline can reject incomplete packages before customer reports are generated.

## Required Layout

```text
panels/
  <panel_id>/
    panel.yaml
    qa.yaml
    rules/
      *.yaml
    templates/
      *.docx
    mappings.yaml
    golden_cases/
      ...
```

`panel_id` must use lowercase letters, digits, and underscores. The directory
name must exactly match `panel_id`.

Legacy packages may reference shared project files such as
`config/mapping.yaml` or `templates/aligned_template_with_cnv_fusion_hla_FIXED.docx`.
New packages should prefer colocated `rules/`, `templates/`, and mapping files
so that a panel can be reviewed and moved as one unit.

## `panel.yaml` Minimum Fields

Required fields:

- `schema_version`
- `panel_id`
- `display_name`
- `version`
- `status`
- `aliases`
- `project_detector_rules`
- `default_template`
- `templates`
- `mappings`
- `rules`
- `input_contract`
- `template_contract`
- `processors`
- `golden_cases`

Supported package and template statuses:

- `draft`
- `pilot`
- `active`
- `deprecated`

Every active or pilot panel must declare at least one synthetic golden case.
Production customer files must not be placed under `golden_cases/`.

Optional `naming.output_pattern` overrides the global automatic output filename
pattern for this package only. Explicit caller-provided filenames are preserved.
The four historical lung draft packages use a `评审草稿.docx` suffix, so their
default filenames do not imply clinical final approval. Packages without this
field retain the existing global naming behavior.

Optional `gene_symbol_aliases` is a panel-scoped `historical_alias -> current_symbol`
mapping for assays whose historical input keys differ from the current official
gene symbol:

```yaml
gene_symbol_aliases:
  WHSC1: NSD2
```

The mapping normalizes knowledge lookup and identical Part 3 variant identity,
but does not rewrite the first input symbol displayed in the report. It must not
be used as a global synonym table: symbol history can be assay-specific or
ambiguous (for example, `TCF4` and the historical `TCF7L2` alias). Keys and
values must be non-empty strings; self-maps and cycles are invalid.

### Input table and column contract

`input_contract.required_tables` and `required_columns` are enforced twice:
by the Web preflight before a task is created, and again by
`ReportGenerator.generate()` for direct/CLI callers. Use
`required_any_columns` when the upstream workbook may provide one of several
equivalent headers:

```yaml
input_contract:
  required_tables: [Variations]
  required_columns:
    Variations: [Gene_Symbol, cHGVS, Transcript]
  required_any_columns:
    Variations: [pHGVS_S, pHGVS_A]
```

Here the `Variations` sheet and every `required_columns` header are mandatory,
while either protein-HGVS header is sufficient. Structural validation reports
only configured sheet/column names and never includes patient values.

`input_contract.optional_source_fields` maps optional display variables to
explicit source-key aliases. It is opt-in per package; missing values become
`未提供`, never a clinical finding or a QC approval. Existing mapped values are
preserved, and the report metadata records source/default provenance. Fields
not declared here remain subject to the strict template-variable gate.

## `qa.yaml` Minimum Fields

Every panel package must include a QA profile:

```yaml
schema_version: "1.0"
panel_id: "crc_301_msi"

legacy_reference:
  enabled: true
  source_dir_name: "crc_301_msi"
  sample_count: 5
  required_features:
    total_variants_count: warn
    drug_related_count: warn
    msi_status: warn
  required_sections:
    variant_summary: warn
    biomarkers: warn
    gene_list: warn
  require_table_shapes: warn
  privacy_checks:
    source_dir: fail
    report_id: fail
    sample_id: fail
    date: fail

current_output:
  enabled: true
  source: "golden_reference"
  required_features:
    total_variants_count: warn
    drug_related_count: warn
    msi_status: warn
  required_sections:
    variant_summary: warn
    biomarkers: warn
    gene_list: warn
  require_table_shapes: warn
  privacy_checks:
    report_id: fail
    sample_id: fail
    date: fail
```

Rule severities are `off`, `warn`, or `fail`. A panel that has no historical
reference set should keep `legacy_reference.enabled: false`; the profile still
documents the expected QA behavior before the panel is promoted. CRC 301 and
CRC 358 enable historical reference checks when
`REPORTGEN_LEGACY_REPORTS_ROOT` or `--legacy-source-root` points at the local
split reference root.

`current_output` applies the same contract style to the freshly generated golden
DOCX during `reportgen qa gate`. Its `source` can be `golden_reference` or
`golden_candidate`; CRC 301 and CRC 358 both enable this check in default CI.

## Validator

Run the full registry validator:

```bash
python -m reportgen.cli panel validate --project-root .
```

Run one package:

```bash
python -m reportgen.cli panel validate crc_358_msi --project-root .
```

Machine-readable output:

```bash
python -m reportgen.cli panel validate --project-root . --format json
```

The validator checks:

- `panel.yaml` schema and required metadata.
- directory name equals `panel_id`.
- declared templates, rules, and mappings exist.
- declared files stay under the panel or project root and do not use absolute
  paths or `..`.
- template and YAML suffixes are correct.
- enhancer imports are resolvable when declared.
- processor names exist in the DOCX processor registry and are not duplicated.
- input/template contracts are non-empty.
- required-column and alternative-column declarations are well formed.
- `qa.yaml` exists, matches `panel_id`, and uses valid legacy reference rule
  severities.
- golden case ids are unique and runnable.
- registry aliases do not collide across packages.
- `gene_symbol_aliases`, when declared, is a non-cyclic string-to-string map.

The runtime `PanelRegistry` also rejects alias collisions during registration,
so a package cannot silently steal another panel's project type.

## Generation Gate

Report generation now runs the same package validator before reading the Excel
or rendering the template whenever the selected project type resolves to a
Panel Package. A failing package returns `success=false` with a structured
`panel_package_validation` payload and no DOCX is produced.

Single-report API responses expose this payload as `panel_package_validation`.
Batch validation reports include it under each result's `validation` object.

This keeps package mistakes such as missing templates, invalid rule paths,
unknown processors, or alias collisions out of the customer report path.
