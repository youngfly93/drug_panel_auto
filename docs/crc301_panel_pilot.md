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
- `reportgen qa run --panel crc_301_msi` is supported.
- Default `reportgen qa gate` includes `crc_301_msi`.

## Acceptance Commands

```bash
python -m reportgen.cli panel validate crc_301_msi --project-root .
python -m reportgen.cli qa run --panel crc_301_msi
python -m reportgen.cli qa gate --panel crc_301_msi
```

Expected result for each command: `PASS`.

## Next Work

- Select 3 to 5 representative historical CRC 301 reports as reference cases.
- Build a sanitized text/QA snapshot set for those references.
- Compare newly generated CRC 301 reports against those references with the
  existing diff gate.
- Decide whether CRC 301 needs separate template assets or can keep sharing the
  current CRC template.
