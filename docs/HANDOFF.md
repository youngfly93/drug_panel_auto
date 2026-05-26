# ReportGen Web Handoff

Last verified: 2026-05-26

This document is the onboarding entry point for the next maintainer. It records
the current source of truth, deployment topology, validation gates, and the
rules for future panel work.

## 1. Read This First

Use this repository/worktree as the development source of truth:

```bash
cd /Volumes/KINGSTON/work/minhao/基因组panel自动化系统_web_golden_template
git checkout main
git pull --ff-only
```

Current verified commit:

```text
385475e chore(report): promote crc358 golden template
```

GitHub remote:

```text
https://github.com/youngfly93/drug_panel_auto.git
```

Do not continue development in this old local worktree:

```text
/Volumes/KINGSTON/work/minhao/基因组panel自动化系统_web
```

That directory is on the stale branch `codex/report-v15-fixes` and currently
contains many uncommitted historical files, temporary files, generated reports,
and patient-level artifacts. Treat it as a historical reference only.

## 2. Current State

The active production line is `main`. The earlier
`codex/golden-template-pilot` branch has been merged/promoted; it now points to
the same commit as `main`.

The CRC358+MSI report is now using the golden-template path by default. The
important production decision is already reflected in:

```text
panels/crc_358_msi/panel.yaml
```

The platform has these main capabilities:

- Upload Excel and detect panel project type.
- Generate CRC358+MSI reports through the Web UI.
- Use the reviewed final Word report as the layout source of truth.
- Render dynamic Part 3 knowledge/drug interpretation instead of keeping
  case-specific hardcoded text.
- Validate reports through regression tests, context contract checks, golden
  template tests, legacy reference checks, and stateless Web endpoint tests.
- Serve the Web app publicly through Cloudflare Tunnel.

## 3. Important Local Commands

Install dependencies:

```bash
make install
```

Start local backend and frontend:

```bash
make dev
```

Run backend tests:

```bash
cd backend
pytest tests/ -v
```

Run release readiness checks:

```bash
make release-check
```

Run Web smoke test when upload, report generation, frontend, or API behavior is
changed:

```bash
make web-smoke
```

For targeted panel QA:

```bash
python -m reportgen.cli qa gate --panel crc_358_msi --output-root /tmp/reportgen-crc358-qa
```

## 4. Repository Map

Most future work should happen in these locations:

```text
backend/app/api/
```

FastAPI endpoints. `excel.py` and `report.py` are the highest-risk routes for
report generation.

```text
backend/app/services/
```

Web-to-reportgen bridge, task management, config services, and file handling.

```text
reportgen/core/
```

Core report generation pipeline. Keep generic behavior here; do not put
panel-specific business rules directly into renderer branches.

```text
panels/<panel_id>/
```

Panel packages. New panels should be added here with their own `panel.yaml`,
rules, mappings, templates, and QA profile.

```text
panels/crc_358_msi/
```

Current primary panel. CRC358+MSI template/rules live here.

```text
backend/tests/
```

Regression, contract, reference, and Web endpoint tests.

```text
docs/
```

Architecture, migration, deployment, and release documentation.

## 5. Golden Template Rules

The project should keep using the reviewed final Word report as the layout
source of truth. For new panels or large CRC358 changes:

1. Start from a reviewed final DOCX.
2. Replace only truly variable regions with Jinja/docxtpl variables.
3. Preserve the original Word runs, table widths, borders, colors, fonts,
   images, page breaks, headers, and footers as much as possible.
4. Repeated tables must be row loops, not one giant string inserted into a cell.
5. Narrative sections must render from structured context lists, not from
   case-specific paragraphs embedded in templates.
6. Test with at least two cases. A template built from case A and tested only
   with case A is circular validation and is not acceptable.

Helpful local skills:

```text
$reportgen-panel-development
$golden-doc-report-factory
```

## 6. Hardcoding Policy

Never hardcode patient-level or case-level facts in reusable code/templates.

Forbidden examples:

- patient name;
- sample ID;
- report date;
- specific variant such as `KRAS p.G12S` unless inside a named test fixture;
- mutation frequency such as `46.29%` unless fixture-scoped;
- drug interpretation copied from one case into a reusable template;
- signature image path tied to one reviewer unless configured through registry
  or upload;
- Cloudflare tunnel token, SSH key, password, or production secret.

Business knowledge belongs in structured YAML/Excel knowledge bases with
provenance. Renderer code should consume structured context, not decide medical
content with ad hoc branches.

## 7. Deployment And Network

### Public URL

The current public testing/production URL is:

```text
https://panel.mailuo-report.com.cn
```

Current health check:

```bash
curl -sS https://panel.mailuo-report.com.cn/api/v1/tasks/stats
```

Expected response shape:

```json
{"success":true,"data":{"total":...},"error":null}
```

### Domain

Domain:

```text
mailuo-report.com.cn
```

Registrar:

```text
京东云 / JD Cloud domain console
```

DNS is delegated to Cloudflare. The Cloudflare zone should be checked before any
DNS change. The nameservers shown during setup were:

```text
alberto.ns.cloudflare.com
ashley.ns.cloudflare.com
```

### Cloudflare Tunnel

Cloudflare Zero Trust tunnel:

```text
reportgen-web-iyun
```

Public hostname route:

```text
panel.mailuo-report.com.cn -> http://127.0.0.1:8000
```

Do not paste the tunnel token into Git, docs, screenshots, or chat. On the
server the token is stored outside the repository:

```text
~/.config/reportgen-web/cloudflared-token
```

### Server

SSH alias:

```bash
ssh iyun-server
```

Resolved server account from local SSH config:

```text
HostName 218.205.37.74
Port 6222
User iyun6208
```

Application directory on the server:

```text
~/apps/reportgen-web
```

The server currently runs:

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
cloudflared tunnel --no-autoupdate run --token-file ~/.config/reportgen-web/cloudflared-token
```

A watchdog cron job keeps both processes alive:

```text
* * * * * ~/apps/reportgen-web/bin/reportgen-watchdog.sh >/tmp/reportgen-watchdog.log 2>&1
```

Useful server checks:

```bash
ssh iyun-server
cd ~/apps/reportgen-web
git status --short --branch
git log -1 --oneline --decorate
pgrep -af "uvicorn|cloudflared"
curl -sS http://127.0.0.1:8000/api/v1/tasks/stats
tail -n 100 logs/server.log
tail -n 100 logs/cloudflared.log
```

Restart through the watchdog:

```bash
cd ~/apps/reportgen-web
bash bin/reportgen-watchdog.sh
```

If a process is stale, kill only the stale `uvicorn` or `cloudflared` process,
then rerun the watchdog. Do not start a second server on another port unless the
deployment plan explicitly says so.

## 8. Deployment Workflow

Preferred flow:

1. Develop locally on a feature branch from `main`.
2. Run tests and QA gates locally.
3. Push branch and open PR.
4. Merge only after checks pass.
5. Deploy the merged `main` commit to `iyun-server`.
6. Verify the public URL and run one report-generation smoke test.

Feature branch naming:

```text
codex/<short-topic>
```

Before deploy:

```bash
git checkout main
git pull --ff-only
make release-check
make web-smoke
```

After deploy on the server:

```bash
ssh iyun-server
cd ~/apps/reportgen-web
git status --short --branch
git rev-parse --short HEAD
curl -sS http://127.0.0.1:8000/api/v1/tasks/stats
```

Then verify from a normal browser:

```text
https://panel.mailuo-report.com.cn
```

## 9. How To Add A New Panel

Do not copy CRC358 code and edit renderer branches. Add a panel package.

Minimum expected structure:

```text
panels/<panel_id>/
  panel.yaml
  qa.yaml
  rules/
  templates/
  mappings/
```

Process:

1. Collect a reviewed final Word report for the new panel.
2. Build a cleaned golden template from that report.
3. Variableize only required fields and repeated regions.
4. Put business rules in `rules/*.yaml`.
5. Add project detector aliases if Excel/project names are inconsistent.
6. Add a two-case validation set.
7. Add tests under `backend/tests/`.
8. Add QA profile in `qa.yaml`.
9. Run release checks before making it default.

## 10. Review Workflow

The next maintainer can implement tasks, but every meaningful change should be
reviewed against these questions:

- Does this change keep `main` deployable?
- Is the worktree clean before and after the change?
- Are generated customer files outside Git?
- Does the change add patient/case hardcoding?
- Does a second-case test catch leakage from the golden source case?
- Do templates preserve Word layout instead of reconstructing it from scratch?
- Did `make release-check` and relevant tests pass?
- Did public Web smoke still work if deployment behavior changed?

Codex should primarily act as reviewer/QA gatekeeper after handoff:

- inspect diffs;
- look for hardcoding;
- run regression tests;
- compare generated reports to references;
- verify layout-sensitive DOCX/PDF output when the change touches templates;
- verify deployment and public URL behavior when the change touches Web/server.

## 11. Known Stop Conditions

Stop and ask for review before merging or deploying if any of these happen:

- tests or QA gate fail;
- generated CRC358 report loses known fixed behavior;
- table format visibly drifts from the reviewed reference;
- blank/half-blank pages reappear;
- Part 3 interpretation repeats a source case variant in a different case;
- Cloudflare Tunnel route points to the wrong local port;
- server Git commit differs from GitHub `main` without a written deployment
  reason;
- any `.xlsx`, `.docx`, `.pdf`, `storage/`, signature image, token, or patient
  data appears in `git status` as a candidate for commit.

