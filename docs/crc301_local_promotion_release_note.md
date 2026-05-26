# CRC301 Local Golden Template Promotion

Date: 2026-05-26

## Scope

This note records the local promotion of the CRC301+MSI golden-template path.
It is a repository change only. It has not been deployed to the production
server because the server is currently reserved for external testing.

## Commits

- `4c8a91d fix(panel): stabilize crc301 golden pilot layout`
- `648ea67 chore(panel): promote crc301 golden template locally`

## Local Configuration

- Panel: `crc_301_msi`
- Default template: `crc_301_msi_golden_template_v1`
- Template status: `active`
- Rollback template: `crc_301_msi_standard_v1`
- Deprecated rollback artifact: `crc_301_msi_golden_template_v0`

Rollback is a panel-config-only change:

```yaml
default_template: "crc_301_msi_standard_v1"
```

## Validation

Local release readiness was run with GitHub checks disabled, so no server or
remote deployment state was touched:

```bash
RUN_GITHUB_CHECKS=0 make release-check
```

Result: `PASS`

Artifacts:

```text
tmp/release_check/20260526_120802/qa_gate/qa_gate_report.json
```

Covered gates:

- panel package validation
- ruff check
- backend pytest regression
- CRC358 golden reference/candidate/repeat diff
- CRC301 golden reference/candidate/repeat diff
- lung methylation golden reference/candidate/repeat diff
- current output contract for CRC358 and CRC301

CRC301 local Web/API smoke was also run before this note:

```bash
WEB_SMOKE_PANEL=crc_301_msi WEB_SMOKE_BUILD=0 make web-smoke
```

Result: `PASS`

The standard CRC358 Web/API smoke was rerun as a regression check:

```bash
WEB_SMOKE_BUILD=0 make web-smoke
```

Result: `PASS`

## Deployment Status

Not deployed.

Server promotion should be handled as a separate release step after the current
server testing window is clear. At that point, rerun the release checklist and
record the deployed commit hash.
