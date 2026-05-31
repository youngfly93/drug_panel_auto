# iyun62 Production Deployment

This server currently runs `panel.mailuo-report.com.cn` through the `iyun-server`
SSH alias.

## Current Layout

- Legacy dirty worktree: `/media/desk16/iyun6208/apps/reportgen-web`
- Clean releases: `/media/desk16/iyun6208/apps/reportgen-web-releases/<commit>`
- Runtime files: `/media/desk16/iyun6208/apps/reportgen-web-runtime`
- Persistent storage: `/media/desk16/iyun6208/apps/reportgen-web/storage`
- Python venv: `/media/desk16/iyun6208/apps/reportgen-web/.venv`
- App port: `8000`

The clean release process transfers a `git archive` of the exact `DEPLOY_REF`
from the local machine. It keeps generated reports, uploads, SQLite DB,
signatures, and logs outside the release directory. A release can therefore be
replaced or rolled back without moving production data.

## Deploy

From a clean local `main` checkout:

```bash
DEPLOY_REF=$(git rev-parse HEAD) bash scripts/iyun62_deploy_clean.sh
```

The script:

1. runs local syntax checks and frontend build;
2. builds the requested commit in a temporary local archive directory;
3. uploads the archive, including `backend/static`, to a clean remote release;
4. starts uvicorn from the clean release while pointing storage to the existing
   production storage directory;
5. verifies the public `/api/v1/tasks/stats` endpoint.

## Rollback

Use any known-good commit:

```bash
DEPLOY_REF=<known_good_commit> bash scripts/iyun62_deploy_clean.sh
```

The previous release directory remains in
`/media/desk16/iyun6208/apps/reportgen-web-releases/`, and the old dirty
worktree remains untouched.

## Verify

```bash
ssh iyun-server '
set -e
cat /media/desk16/iyun6208/apps/reportgen-web-runtime/current_release
cat /media/desk16/iyun6208/apps/reportgen-web-runtime/current_release | xargs -I{} cat {}/REVISION
pgrep -af "[u]vicorn app.main:app"
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8000/api/v1/tasks/stats
'
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://panel.mailuo-report.com.cn/api/v1/tasks/stats
```

## Watchdog

The current production user has crontab access. Install or refresh the user-level
watchdog with:

```bash
bash scripts/iyun62_install_watchdog.sh
```

This installs:

- `/media/desk16/iyun6208/apps/reportgen-web-runtime/watchdog.sh`
- `/media/desk16/iyun6208/apps/reportgen-web-runtime/start_reportgen.sh`
- one `crontab` block that runs every minute and once at reboot

The watchdog checks:

- local API health;
- public Cloudflare URL health;
- uvicorn process recovery from the current clean release;
- Cloudflare tunnel recovery;
- storage disk usage warning;
- LibreOffice listener presence.

Logs are written to:

```text
/media/desk16/iyun6208/apps/reportgen-web-runtime/logs/watchdog.log
```

## Download Performance Triage

Report download responses include diagnostic headers:

- `X-ReportGen-Task-Id`
- `X-ReportGen-Download-Kind`
- `X-ReportGen-Download-Bytes`
- `X-ReportGen-Task-Duration-Seconds`

The API also writes structured download events to uvicorn logs without patient
names, report filenames, Excel filenames, or full report paths:

```bash
scripts/iyun62_download_diagnostics.sh
scripts/iyun62_download_diagnostics.sh --task-id <task_id>
scripts/iyun62_download_diagnostics.sh --since-minutes 60 --limit 50
```

Use these fields to separate causes:

- `report_download_started` appears immediately when the endpoint starts sending.
- `report_download_completed` records server-side send duration and throughput.
- `report_download_slow` means the server-side send took at least
  `RG_WEB_DOWNLOAD_SLOW_WARN_SECONDS` seconds, default `10`.
- `prepare_duration_ms` on ZIP downloads measures server-side ZIP packaging time
  before the file transfer starts.

## Known Limitation

The current SSH user does not have passwordless sudo, and `loginctl` linger is
disabled. The runtime script is therefore a user-level process supervisor around
`nohup`, not a root-level `systemd` service. A production hardening pass should
add a real system service or enable user linger through an administrator.
