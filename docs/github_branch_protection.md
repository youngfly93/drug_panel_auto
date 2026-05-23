# GitHub Branch Protection

This project uses the `Reportgen QA Gate` workflow as the merge gate for report
generation changes. The required GitHub status check context is:

```text
qa-gate
```

## Configure

Run this once with a GitHub account that has admin permission on the repository:

```bash
scripts/configure_branch_protection.sh youngfly93/drug_panel_auto main
```

The script configures the `main` branch to:

- require the `qa-gate` status check before merging;
- require branches to be up to date before merging;
- block force pushes;
- block branch deletion;
- require conversation resolution.

## Verify

```bash
gh api repos/youngfly93/drug_panel_auto/branches/main/protection \
  --jq '.required_status_checks.contexts'
```

Expected output:

```json
["qa-gate"]
```

## Local Preflight

Before opening or updating a pull request, run:

```bash
make preflight
```

or:

```bash
python -m reportgen.cli qa gate
```

The gate runs panel validation, lint, regression tests, synthetic golden cases,
repeated-generation DOCX diffs, current generated DOCX contract checks, and an
optional legacy reference snapshot step. The legacy step is skipped unless a
historical-report root is available through `--legacy-source-root` or
`REPORTGEN_LEGACY_REPORTS_ROOT`; panel-specific rules are read from
`panels/<panel_id>/qa.yaml`.
