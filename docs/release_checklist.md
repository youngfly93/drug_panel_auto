# Release Checklist

This checklist is for promoting the report-generation platform from a feature
branch to the production server. It assumes the target production branch is
`main` and the required GitHub check is `qa-gate`.

## 0. Release Scope

- Confirm the release branch and commit:

```bash
git branch --show-current
git rev-parse --short HEAD
```

- Confirm what changed since the previous release:

```bash
git log --oneline main..HEAD
```

- Confirm no real patient files are included:

```bash
git status --short
git diff --cached --name-only
```

## 1. Local Readiness

Run the release readiness check:

```bash
make release-check
```

This runs the local QA gate and checks that GitHub `main` requires the `qa-gate`
status check. If the current branch has not been pushed yet, push it first and
wait for GitHub Actions to finish, then rerun:

The QA gate includes `knowledge_release_gate`. It verifies the versioned base
knowledge manifest, review-status/runtime consistency, structured provenance,
duplicate selectors, PII/section leaks, and runtime gene-explanation coverage
for CRC301/358. A `not_recorded` production Overlay entry or a knowledge file
hash mismatch blocks release.

The knowledge gate can also be run directly:

```bash
python scripts/check_knowledge_release_ready.py --strict \
  --output .work/knowledge_release/knowledge_release_gate.json
```

```bash
git push origin "$(git branch --show-current)"
make release-check
```

Emergency local-only check:

```bash
RUN_GITHUB_CHECKS=0 make release-check
```

Run the Web smoke test when the change touches upload, preview, clinical form,
report generation, download, deployment packaging, or frontend assets:

```bash
make web-smoke
```

This uses a synthetic CRC 358 + MSI workbook and verifies upload, project
detection, sheet preview, schema loading, report generation, QA status, and DOCX
download. If the frontend is already built, `WEB_SMOKE_BUILD=0 make web-smoke`
can be used for a faster rerun.

## 2. Pull Request

- Open a PR from the release branch into `main`.
- Confirm `Reportgen QA Gate / qa-gate` is green.
- Confirm the PR is up to date with `main`.
- Confirm the Actions run has no Node.js runtime deprecation warning. The QA
  workflow opts JavaScript actions into Node 24 and pins Node 24-compatible
  major versions.
- Review generated QA artifacts if the gate fails or warns.
- Confirm no `.xlsx`, `.docx`, `.pdf`, `storage/`, or patient-level outputs are
  added to Git.
- Merge only after the required `qa-gate` check passes.

## 3. Deploy

On the production server:

```bash
ssh root@117.72.75.45
cd /opt/reportgen-web
DEPLOY_BRANCH=main bash deploy.sh
```

`deploy.sh` runs the same preflight gate before frontend build and service
restart. If the gate fails, deployment stops and the existing service is not
restarted.

The deploy script requires Node.js 18+ for the frontend build. If the server has
an older Node.js runtime, it installs Node.js 22 by default. Override with
`NODE_INSTALL_MAJOR=<major>` only when a server image requires a different
NodeSource channel.

Preflight artifacts are written to:

```text
/opt/reportgen-web/tmp/deploy_qa_gate/
```

## 4. Production Smoke Test

After deployment:

```bash
systemctl status reportgen-web --no-pager
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/v1/tasks/stats
```

Expected:

- `reportgen-web` is active.
- API health endpoint returns `200`.

Then run one report-generation smoke check on the server:

```bash
cd /opt/reportgen-web
source venv/bin/activate
python -m reportgen.cli qa gate \
  --panel crc_358_msi \
  --output-root /tmp/reportgen-release-smoke
```

Expected:

- gate status is `PASS`;
- generated DOCX opens;
- QA report status is `PASS`;
- repeated golden diff is `PASS`.

If the server has build and test dependencies available, run the same Web smoke
flow against production:

```bash
cd /opt/reportgen-web
WEB_SMOKE_BASE_URL=http://127.0.0.1:8000 \
WEB_SMOKE_BUILD=0 \
WEB_SMOKE_ADMIN_USERNAME=<admin_user> \
WEB_SMOKE_ADMIN_PASSWORD=<admin_password> \
make web-smoke
```

Expected:

- synthetic upload is detected as `crc_358_msi`;
- sheet preview returns non-zero row/column counts;
- generated report QA status is `PASS`;
- DOCX download succeeds.

## 5. Rollback

Use the last known-good commit from GitHub Actions or deployment logs:

```bash
DEPLOY_REF=<known_good_commit_or_tag> bash deploy.sh
```

If production is down and the rollback commit is already known good, an
emergency rollback may skip the preflight gate:

```bash
DEPLOY_REF=<known_good_commit_or_tag> RUN_PREFLIGHT=0 bash deploy.sh
```

After rollback, rerun the production smoke test in section 4.

## 6. Release Record

Record these values in the release note or team message:

- release branch;
- merged commit SHA on `main`;
- GitHub Actions run URL;
- deployment start/end time;
- server commit after deploy:

```bash
cd /opt/reportgen-web
git rev-parse --short HEAD
```

- smoke test output;
- rollback commit/tag.

## 7. Stop Conditions

Do not deploy if any of these are true:

- local `make release-check` fails;
- GitHub `qa-gate` fails or is missing;
- PR contains real patient data or generated customer reports;
- `deploy.sh` preflight fails;
- production smoke test cannot generate the synthetic CRC 358 golden report.
