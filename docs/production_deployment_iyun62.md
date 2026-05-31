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

## Backup And Cleanup

Install or refresh the user-level daily maintenance cron with:

```bash
bash scripts/iyun62_install_maintenance.sh
```

This installs `/media/desk16/iyun6208/apps/reportgen-web-runtime/backup.sh`
and a daily `crontab` block. The default schedule is `02:17` server time.

The maintenance job:

- creates a server-local archive under
  `/media/desk16/iyun6208/apps/reportgen-web-backups`;
- backs up SQLite using the SQLite online backup API, then runs
  `PRAGMA integrity_check` on the backup copy;
- includes uploads, generated reports, signatures, and reference reports;
- writes a redacted manifest with storage counts/sizes, current release, and
  archive SHA-256;
- verifies the `.tar.gz` archive and extracted SQLite copy;
- removes old backup archives after `BACKUP_KEEP_DAYS`, default `30`;
- removes old clean release directories while keeping the current release and
  the newest `RELEASE_KEEP_COUNT`, default `8`;
- removes stale previews after `PREVIEW_KEEP_DAYS`, default `7`;
- removes uploaded Excel files after `UPLOAD_KEEP_DAYS`, default `30`;
- removes regenerated ZIP packages after `ZIP_KEEP_DAYS`, default `14`;
- removes generated report task directories after `REPORT_KEEP_DAYS`, default
  `180`;
- removes operation audit rows after `AUDIT_LOG_KEEP_DAYS`, default `365`;
- removes rotated logs after `LOG_KEEP_DAYS`, default `14`.

Manual commands:

```bash
ssh iyun-server '/media/desk16/iyun6208/apps/reportgen-web-runtime/backup.sh backup'
ssh iyun-server 'DRY_RUN=1 /media/desk16/iyun6208/apps/reportgen-web-runtime/backup.sh cleanup'
ssh iyun-server '/media/desk16/iyun6208/apps/reportgen-web-runtime/backup.sh verify --archive /media/desk16/iyun6208/apps/reportgen-web-backups/reportgen-web-backup-YYYYmmdd_HHMMSS.tar.gz'
```

Maintenance logs are written to:

```text
/media/desk16/iyun6208/apps/reportgen-web-runtime/logs/maintenance.log
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

The frontend download buttons show an in-progress state and byte progress. If a
large DOCX or ZIP stalls, the browser aborts the idle transfer and retries with
HTTP Range resume when the server supports it.

## Ops Alerts

`/api/v1/admin/ops/status` returns sanitized red/yellow alerts for the
production dashboard. These alerts contain no patient names, Excel filenames,
report filenames, client IPs, user agents, or full server paths.

Current thresholds:

- disk warning at `>=80%`, danger at `>=90%`;
- backup warning after `30h`, danger after `48h` or no backup;
- generation queue warning when queued jobs exist, danger when
  `queued >= max_workers`;
- download danger when any recent terminal download failed;
- download warning when any recent terminal download was slow or max duration is
  at least `30s`;
- warning when LibreOffice listener is missing or no cleanup completion is
  recorded.

The same status payload exposes the active retention policy under `retention`,
so the dashboard shows the actual keep-days currently used by the deployed
environment.

## Operation Audit

Task-level operation audit events are written to the SQLite `audit_logs` table
and exposed through:

```bash
curl https://panel.mailuo-report.com.cn/api/v1/reports/<task_id>/audit-log
```

Recorded events include report generation requests, batch queue/retry actions,
download requests, and review/delivery state changes. The API response is
sanitized: it does not include patient fields, Excel filenames, report
filenames, full paths, client IPs, or user agents.

## Known Limitation

The current SSH user does not have passwordless sudo, and `loginctl` linger is
disabled. The runtime script is therefore a user-level process supervisor around
`nohup`, not a root-level `systemd` service. A production hardening pass should
add a real system service or enable user linger through an administrator.
