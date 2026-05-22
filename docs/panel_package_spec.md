# Panel Package Directory Specification

M5.1 defines the minimum package contract for adding or promoting a panel.
The goal is to make every panel self-describing enough that the report
pipeline can reject incomplete packages before customer reports are generated.

## Required Layout

```text
panels/
  <panel_id>/
    panel.yaml
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
- golden case ids are unique and runnable.
- registry aliases do not collide across packages.

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
