# Release Checklist

This checklist is for promoting the report-generation platform from a feature
branch to the production server. It assumes the target production branch is
`main` and the required GitHub check is `qa-gate`.

The production target in this checklist is **iyun129** (`ssh iyun129`, user
`iy12922`) with immutable releases under
`/media/desk16/iy12922/apps/reportgen-web-releases/` and uvicorn on port
`18082`. The root-level `deploy.sh` targets a legacy JD Cloud layout
(`117.72.75.45`, `/opt/reportgen-web`, systemd, port `8000`) and must not be used
for iyun129.

For report-group review of the full input → rules → knowledge → DOCX →
delivery chain, use
[`report_group_system_report_audit_checklist.md`](report_group_system_report_audit_checklist.md).
Engineering release completion in this file does not replace medical secondary
review or real-report UAT.

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
duplicate selectors, PII/section leaks, final-provider content completeness,
and cited PMID/trial resolution for every `status: active` panel. A
`not_recorded` production Overlay entry, empty final gene explanation, unresolved
runtime citation, or knowledge file hash mismatch blocks the engineering release.
Draft/pilot panels are reported as non-blocking readiness warnings.

The same report contains a separate `clinical_release_readiness` status. It stays
`BLOCKED` while report-group secondary review is pending, generic fallback remains
above the accepted content-depth target, or the active Panel-specific UAT policy
is not satisfied. Legacy panels default to at least 10 reviewed reports and 90%
pass rate; a Panel may declare a versioned risk-based policy. Such a policy may
allow a controlled internal pilot without a fixed case-count minimum, but it must
remain explicitly blocked from active medical promotion when real-case UAT is
absent. An engineering `PASS` must not be described as medical approval or UAT
completion.

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

Deploy only from a clean local `main` checkout whose `HEAD` is the accepted
GitHub commit:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
DEPLOY_REF="$(git rev-parse HEAD)" bash scripts/iyun129_deploy_clean.sh
```

The iyun129 wrapper supplies the production coordinates:

- releases: `/media/desk16/iy12922/apps/reportgen-web-releases/<short-sha>`;
- runtime: `/media/desk16/iy12922/apps/reportgen-web-runtime`;
- persistent storage: `/media/desk16/iy12922/apps/reportgen-web-storage`;
- Python venv: `/media/desk16/iy12922/apps/reportgen-web-venv`;
- anonymous liveness endpoint: `http://127.0.0.1:18082/api/v1/healthz`;
- public liveness endpoint: `https://panel.mailuo-report.com.cn/api/v1/healthz`;
- authenticated task statistics: `https://panel.mailuo-report.com.cn/api/v1/tasks/stats`.

The deploy command runs `make release-check`, builds frontend assets from the
exact `DEPLOY_REF`, writes the full SHA to the release `REVISION`, installs a
non-secret `runtime/deployment.env`, and starts the candidate. It updates
`current_release` only after HTTP health, non-zombie uvicorn identity, and
process-cwd validation pass twice consecutively.
If the candidate fails, the start script attempts to restore the previous
release and exits non-zero.

Before any backup or production-side mutation, the iyun129 wrapper fetches the
latest `origin/main` and rejects a `DEPLOY_REF` that is not reachable from that
ref. A review branch or server-local commit must therefore be merged and pushed
to `origin/main` before it can become a production release.

Production `.env.prod` must keep `REPORTGEN_FAST_TOC`,
`REPORTGEN_SKIP_FINAL_LO_REFRESH`, and
`REPORTGEN_SKIP_STATIC_TOC_PAGE_NUMBERS` disabled. These shortcuts omit the
cached PAGEREF directory construction and can produce an empty TOC even when
HTTP health is green. The runtime start script checks them before stopping the
known-good process and refuses the switch when any is truthy.

### CRC358 + lung329/lung588 controlled-pilot release

The lung329 and lung588 products are exposed only for single-case controlled
generation. A report-review draft may be generated and downloaded when PD-L1
values, source identity, the case image, or treatment context are not yet
available; those omissions must remain visible as WARN/not-provided text and
must not produce context-dependent drug matches. Shared batch generation stays
disabled because one shared form must never be copied across patients. Review
state governs formal review/delivery records, not access to the draft Word file.
CRC301, lung methylation and the unbuilt small panels remain disabled in all
three scope guards:

```text
REPORTGEN_DISABLED_PROJECT_TYPES=crc_301_msi,lung_methylation,lung_13,lung_62,lung_62_pdl1
RG_WEB_DISABLED_PROJECT_TYPES=crc_301_msi,lung_methylation,lung_13,lung_62,lung_62_pdl1
VITE_DISABLED_PROJECT_TYPES=crc_301_msi,lung_methylation,lung_13,lung_62,lung_62_pdl1
```

The first guard blocks direct/core generation, the second blocks Web API entry
points, and the third removes unpromoted products from the production
generation selector. Batch generation remains independently disabled by each
lung pilot's committed Panel contract. The list also reserves `lung_13`,
`lung_62`, and `lung_62_pdl1`, which have product-intake records but no Panel
package or matching source Excel.
The iyun129 deployment wrapper supplies these values by default. The backend
guards are authoritative: a hidden or absent frontend option alone is not a
release boundary.

`panels/lung_methylation/release_readiness.yaml` is the committed promotion
record for the methylation draft. Its synthetic golden proves only that the
engineering pipeline can render a document; it is not production evidence.
Before any backup or server mutation,
`scripts/check_production_panel_scope.py` requires every panel whose readiness
record is `production_eligible: false` to remain present in the Web, core, and
frontend disabled scopes. Promotion additionally requires a SHA-pinned,
same-case report-group final DOCX and source Excel, report-group secondary
review, historical-golden PASS, and production-equivalent Linux visual QA.
Pre-package products use the same schema under
`config/panel_product_readiness/`; this lets production fail closed before an
unfinished Panel directory or frontend option exists.

Any CRC358 knowledge row whose secondary review is still pending must remain
visible in governance counts but set `runtime_eligible: false`. Exact pending
variant selectors must fail closed before legacy database or external-drug
fallback lookup; they must not silently regain a drug recommendation through a
lower-priority source. Verify both the positive path (reviewed CRC358 rules still
render) and the negative path (pending selector returns no recommendation).

Before and after switching production, verify that `deployment.env` contains
the two backend guards. A single request or a batch request that explicitly
selects CRC301 must be rejected before task creation. A batch submitted for
automatic project detection may create its lightweight task first; the worker
must reject a detected CRC301 item before report mapping or generation. Also
verify that a synthetic CRC358 report still completes with QA `PASS`. This
scoped engineering release does not convert remaining pending rows or a
blocked panel-level UAT state into medical approval.

When reviewed corrections intentionally supersede the historical final, do not
replace the historical reference or suppress broad diff categories. The
committed historical contract may carry an
`approved_reference_deviation` only when it records report-group approval, the
superseded contract, and an exact SHA-256 over the normalized text/table/Part-3
diff plus the diff schema and all other stable categories (document structure,
styles and QA).
A matching fingerprint is reported as `PASS_WITH_APPROVED_DEVIATION`; any
additional change in any comparison category remains a hard failure. This
engineering exception does not change a blocked medical-UAT status.

`current_release` is a status pointer, not a deployment command. Do not edit it
manually. Use the deployment or release-switch scripts below so the process,
pointer, `REVISION`, and health state change together.

## 4. Production Smoke Test

First verify the active runtime identity:

```bash
bash scripts/iyun129_release.sh status
```

Expected:

- `current_release` points to the intended immutable release;
- release `REVISION` is the intended full commit SHA;
- the uvicorn PID cwd equals `current_release`;
- local health is HTTP `200`.

Also verify the public route:

```bash
curl -fsS -o /dev/null -w "HTTP %{http_code}\n" \
  https://panel.mailuo-report.com.cn/api/v1/healthz
```

The liveness endpoint must remain anonymous and storage-free. Business and
operational endpoints, including `/api/v1/tasks/stats`, must continue to require
authentication and must not be reused as deployment probes.

Then run one report-generation smoke check on the server:

```bash
ssh iyun129 '
set -euo pipefail
runtime=/media/desk16/iy12922/apps/reportgen-web-runtime
current=$(head -n 1 "$runtime/current_release")
cd "$current"
/media/desk16/iy12922/apps/reportgen-web-venv/bin/python \
  -m reportgen.cli qa gate \
  --panel crc_358_msi \
  --output-root /tmp/reportgen-release-smoke
'
```

Expected:

- gate status is `PASS`;
- generated DOCX opens;
- QA report status is `PASS`;
- repeated golden diff is `PASS`.

Run the Web smoke flow against production when credentials for the synthetic
test account are available:

```bash
WEB_SMOKE_BASE_URL=https://panel.mailuo-report.com.cn \
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

Record the production renderer fingerprint used for Golden visual QA:

```bash
ssh iyun129 '
uname -srmo
soffice --version
locale | sed -n "1,6p"
for font in "Noto Sans CJK SC" "Noto Serif CJK SC" "Times New Roman"; do
  fc-match "$font"
done
fc-list | LC_ALL=C sort | sha256sum
cat /media/desk16/iy12922/apps/reportgen-web-runtime/renderer_fingerprint.json
'
```

The release evidence must include the exact Linux LibreOffice version and the
DOCX/QA hashes. The runtime and candidate QA fingerprints must carry the same
committed `reportgen-cjk-font-substitution-*` profile name and the same
64-character mapping hash; the isolated profile pins Word-only fonts to
installed Noto CJK fonts without changing the font names stored in the
delivered DOCX. Final visual acceptance still requires Windows Word/WPS; a Mac
LibreOffice PASS alone is not production-equivalent evidence.

For a formal historical-Golden release, generate every candidate from the
frozen commit on the production-equivalent Linux renderer with
`visual_render=all` and blocking visual QA enabled.  Then bind the candidate,
its QA sidecar, the source commit, and the renderer fingerprint into the
external manifest:

```bash
python scripts/attest_historical_golden_manifest.py \
  --manifest .work/historical_golden_release_manifest.yaml

REQUIRE_HISTORICAL_GOLDEN=1 \
HISTORICAL_GOLDEN_MANIFEST=.work/historical_golden_release_manifest.yaml \
make release-check
```

The attestation command intentionally refuses a dirty source tree.  It also
rejects candidates whose QA is not a required full-page `PASS` on Linux, whose
DOCX hash differs from the QA sidecar, or whose QA source revision differs from
the frozen commit.  Do not hand-edit candidate hashes or renderer fields into
the manifest.  An ordinary Web reference upload is useful for exploratory
comparison but cannot satisfy the formal historical-Golden gate.

## 5. Rollback

List the current identity, then switch to an existing known-good release:

```bash
bash scripts/iyun129_release.sh status
bash scripts/iyun129_release.sh rollback <known_good_release_id_or_revision_prefix>
```

The rollback command validates that exactly one immutable release matches,
installs the committed runtime-control scripts and iyun129 deployment config,
starts that release, and verifies pointer/cwd/health consistency. The start
script keeps `current_release` unchanged until the target passes; on failure it
automatically attempts to restart the previous release.

If the known-good release directory was removed but its commit is available
locally, rebuild that exact commit. Skipping preflight is allowed only for an
already approved known-good rollback SHA:

```bash
DEPLOY_REF=<known_good_full_commit> RUN_PREFLIGHT=0 \
  bash scripts/iyun129_deploy_clean.sh
```

After rollback, rerun the production smoke test in section 4.

## 6. Release Record

Record these values in the release note or team message:

- release branch;
- merged commit SHA on `main`;
- GitHub Actions run URL;
- deployment start/end time;
- output of `bash scripts/iyun129_release.sh status`;
- active release directory and full `REVISION`;
- uvicorn PID, process cwd, and local/public HTTP status;
- SHA-256 of `runtime/start_reportgen.sh`, `watchdog.sh`, and
  `deployment.env` (the environment file contains no secrets);
- production renderer fingerprint and Golden DOCX/QA hashes;
- attested historical-Golden manifest hash and gate JSON;
- smoke test output;
- previous and rollback release IDs.

```bash
ssh iyun129 '
runtime=/media/desk16/iy12922/apps/reportgen-web-runtime
sha256sum "$runtime/start_reportgen.sh" \
  "$runtime/watchdog.sh" "$runtime/deployment.env"
'
```

## 7. Stop Conditions

Do not deploy if any of these are true:

- local `make release-check` fails;
- GitHub `qa-gate` fails or is missing;
- PR contains real patient data or generated customer reports;
- the local tree or runtime-control scripts are uncommitted;
- the iyun129 deploy preflight fails;
- `current_release`, release `REVISION`, process cwd, or intended SHA disagree;
- no validated known-good rollback release is recorded;
- the deterministic render-stack preflight or renderer fingerprint is missing,
  or the candidate/runtime font-substitution profile hashes disagree;
- a required historical-Golden candidate lacks Linux full-page visual QA,
  source-revision provenance, or an attested manifest;
- production smoke test cannot generate the synthetic CRC 358 golden report.
