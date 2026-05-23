# Deployment Preflight Gate

`deploy.sh` runs the same report-generation QA gate before building frontend
assets or restarting the service. A deployment stops immediately if the gate
fails.

Default deployment:

```bash
bash deploy.sh
```

The default gate command is:

```bash
python -m reportgen.cli qa gate --output-root /opt/reportgen-web/tmp/deploy_qa_gate
```

It validates panel packages, runs lint, runs regression tests, generates
synthetic golden reports, compares repeated golden outputs, and records the
current generated DOCX contract plus the legacy reference step. The legacy step
is skipped when no local historical report root is mounted. Panels opt into
current-output and legacy-reference checks through their own
`panels/<panel_id>/qa.yaml` profile.

The default panel set currently covers:

- `crc_358_msi`
- `crc_301_msi`
- `lung_methylation`

## Useful Environment Variables

```bash
DEPLOY_BRANCH=main bash deploy.sh
```

Deploy a specific branch. The default is `main`.

```bash
DEPLOY_REF=fe265e4 bash deploy.sh
```

Deploy a specific commit or tag. This is the standard rollback mechanism when a
known-good commit must be restored.

```bash
PREFLIGHT_ARGS="--panel crc_358_msi" bash deploy.sh
```

Pass extra arguments to `reportgen qa gate`. Use this only for a targeted
investigation; normal deployments should run the full default panel set.

```bash
REPORTGEN_LEGACY_REPORTS_ROOT=/data/reportgen/legacy_reports_by_panel \
PREFLIGHT_ARGS="--legacy-reference-required" \
bash deploy.sh
```

Run deployment preflight with mounted historical reports. This blocks deployment
when the legacy reference snapshot check cannot read, sanitize, or structurally
fingerprint the configured historical panel samples. The enabled panels, sample
counts, required sections, and privacy severities come from each panel's
`qa.yaml`.

For a targeted historical check, use `--legacy-panel`; `--panel` scopes
golden/current-output checks.

```bash
REPORTGEN_LEGACY_REPORTS_ROOT=/data/reportgen/legacy_reports_by_panel \
PREFLIGHT_ARGS="--skip-golden --legacy-panel crc_358_msi --legacy-reference-required" \
bash deploy.sh
```

```bash
PREFLIGHT_OUTPUT_ROOT=/tmp/reportgen-deploy-gate bash deploy.sh
```

Write gate reports to a custom directory.

```bash
RUN_PREFLIGHT=0 bash deploy.sh
```

Skip the deployment gate. This is only for emergency rollback or infrastructure
repair; normal deployments should not use it.

## Failure Handling

When the gate fails, inspect:

```bash
/opt/reportgen-web/tmp/deploy_qa_gate/qa_gate_report.json
/opt/reportgen-web/tmp/deploy_qa_gate/logs/
```

Do not restart `reportgen-web` manually with a failed gate unless the purpose is
an explicit rollback to a known-good commit.
