# CRC 301 + MSI Panel Pilot

## Scope

`crc_301_msi` is the second CRC panel promoted into the same golden-case gate
used by `crc_358_msi`.

The pilot is based on local historical reports in:

```text
/Volumes/KINGSTON/work/肠癌358基因/legacy_reports_by_panel/
```

The split is non-destructive. The panel folders contain symlinks back to the
original files in `legacy_reports`.

## Legacy Inventory

- `crc_301_msi`: 92 historical Word reports
- `crc_358_msi`: 63 historical Word reports
- `unknown`: 1 non-report Excel result file

Classification was checked by Word body text first and filename fallback second.
Filename/body conflicts found: 0.

## Migration Status

- Panel package exists at `panels/crc_301_msi/`.
- Input contract uses `ExistInsmall301` for CRC 301 variation membership.
- Report rules share the CRC rule structure with CRC 358, with panel-specific
  project wording.
- Synthetic CRC 301 golden workbook is now generated directly instead of
  mutating the CRC 358 fixture.
- Pilot golden-template asset exists as
  `crc_301_msi_golden_template_v0`, but the default template remains
  `crc_301_msi_standard_v1` until two-case QA and layout review are accepted.
- `reportgen qa run --panel crc_301_msi` is supported.
- Default `reportgen qa gate` includes `crc_301_msi`.
- `panels/crc_301_msi/qa.yaml` enables the CRC 301 legacy reference snapshot
  check when a local historical-report root is provided.
- `panels/crc_301_msi/qa.yaml` also enables current-output contract checks for
  the generated golden DOCX in default CI.

## Acceptance Commands

```bash
python -m reportgen.cli panel validate crc_301_msi --project-root .
python -m reportgen.cli qa run --panel crc_301_msi
python -m reportgen.cli qa gate --panel crc_301_msi
python -m reportgen.cli qa legacy-snapshot \
  --panel crc_301_msi \
  --source-dir /Volumes/KINGSTON/work/肠癌358基因/legacy_reports_by_panel/crc_301_msi \
  --output-dir tmp/crc301_reference_snapshots \
  --sample-count 5
python -m reportgen.cli qa gate \
  --panel crc_301_msi \
  --legacy-panel crc_301_msi \
  --legacy-source-root /Volumes/KINGSTON/work/肠癌358基因/legacy_reports_by_panel \
  --legacy-reference-required
python scripts/run_crc301_pilot_two_case_qa.py \
  --output-root tmp/crc301_pilot_two_case_qa
```

Expected result for each command: `PASS`.

## Current CRC301 Golden Pilot Two-Case Result

Last local run: 2026-05-26

Command:

```bash
python scripts/run_crc301_pilot_two_case_qa.py \
  --output-root tmp/crc301_pilot_two_case_qa
```

Result:

| Case | Generation | QA | Tables | Marker/Jinja Cleanup |
|---|---|---|---:|---|
| `crc301_case_a` | PASS | PASS | 63 | PASS |
| `crc301_case_b` | PASS | PASS | 63 | PASS |

The pilot remains `status: pilot` and `crc_301_msi_standard_v1` remains the
default template. Promotion still requires manual layout review of the generated
DOCX pages.

CRC 358 follows the same historical gate pattern:

```bash
python -m reportgen.cli qa gate \
  --skip-golden \
  --legacy-panel crc_358_msi \
  --legacy-source-root /Volumes/KINGSTON/work/肠癌358基因/legacy_reports_by_panel \
  --legacy-reference-required
```

## Next Work

- Review the generated `tmp/crc301_reference_snapshots/manifest.json` and
  `samples/*.json` files before using them as local reference material.
- Current local snapshot run over the CRC 301 legacy folder found 92 DOCX files,
  79 readable DOCX files, 13 historical DOCX read errors, and 5 representative
  sanitized reference snapshots.
- Use the legacy reference gate during local release checks so field extraction,
  section presence, table-shape fingerprints, and privacy redaction are checked
  against historical CRC 301 reports. Required fields and severities are owned
  by `panels/crc_301_msi/qa.yaml`.
- Review the two-case pilot manifest at
  `tmp/crc301_pilot_two_case_qa/manifest.json`. Promote the golden template only
  after the manifest is `ok: true`, no Jinja/Part 3 markers remain in outputs,
  QA is `PASS` for both cases, and layout review accepts the generated DOCX
  pages.
