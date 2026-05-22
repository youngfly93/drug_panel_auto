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
synthetic golden reports, and compares repeated golden outputs.

## Useful Environment Variables

```bash
DEPLOY_BRANCH=main bash deploy.sh
```

Deploy a specific branch. The default is `main`.

```bash
PREFLIGHT_ARGS="--panel crc_358_msi" bash deploy.sh
```

Pass extra arguments to `reportgen qa gate`.

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
