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

```bash
git push origin "$(git branch --show-current)"
make release-check
```

Emergency local-only check:

```bash
RUN_GITHUB_CHECKS=0 make release-check
```

## 2. Pull Request

- Open a PR from the release branch into `main`.
- Confirm `Reportgen QA Gate / qa-gate` is green.
- Confirm the PR is up to date with `main`.
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
