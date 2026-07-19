#!/usr/bin/env bash
# Install iyun62 backup/cleanup maintenance into reportgen-web-runtime and crontab.

set -euo pipefail

SSH_HOST="${SSH_HOST:-iyun-server}"
APP_ROOT="${APP_ROOT:-/media/desk16/iyun6208/apps}"
LEGACY_APP_DIR="${LEGACY_APP_DIR:-$APP_ROOT/reportgen-web}"
RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
STORAGE_DIR="${STORAGE_DIR:-$LEGACY_APP_DIR/storage}"
RELEASES_DIR="${RELEASES_DIR:-$APP_ROOT/reportgen-web-releases}"
BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/reportgen-web-backups}"
CRON_SCHEDULE="${CRON_SCHEDULE:-17 2 * * *}"
RESTORE_DRILL_SCHEDULE="${RESTORE_DRILL_SCHEDULE:-41 3 3 * *}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
RELEASE_KEEP_COUNT="${RELEASE_KEEP_COUNT:-8}"
PREVIEW_KEEP_DAYS="${PREVIEW_KEEP_DAYS:-7}"
LOG_KEEP_DAYS="${LOG_KEEP_DAYS:-14}"
UPLOAD_KEEP_DAYS="${UPLOAD_KEEP_DAYS:-30}"
REPORT_KEEP_DAYS="${REPORT_KEEP_DAYS:-180}"
ZIP_KEEP_DAYS="${ZIP_KEEP_DAYS:-14}"
AUDIT_LOG_KEEP_DAYS="${AUDIT_LOG_KEEP_DAYS:-365}"

if [ ! -f "scripts/iyun62_backup.sh" ] || [ ! -f "scripts/iyun62_restore_drill.sh" ]; then
    echo "Run this script from the reportgen-web repository root." >&2
    exit 1
fi

echo "== Upload maintenance script =="
ssh "$SSH_HOST" "mkdir -p '$RUNTIME_DIR/logs'"
rsync -az scripts/iyun62_backup.sh "$SSH_HOST:$RUNTIME_DIR/backup.sh"
rsync -az scripts/iyun62_restore_drill.sh "$SSH_HOST:$RUNTIME_DIR/restore_drill.sh"
ssh "$SSH_HOST" "chmod +x '$RUNTIME_DIR/backup.sh' '$RUNTIME_DIR/restore_drill.sh'"

echo "== Install crontab =="
ssh "$SSH_HOST" "set -euo pipefail
tmp=\$(mktemp)
crontab -l 2>/dev/null > \"\$tmp\" || true
python3 - \"\$tmp\" <<'PY'
from __future__ import annotations

import pathlib
import sys

path = pathlib.Path(sys.argv[1])
lines = path.read_text().splitlines()
out: list[str] = []
skip = False
for line in lines:
    stripped = line.strip()
    if stripped == '# BEGIN reportgen-web-maintenance':
        skip = True
        continue
    if stripped == '# END reportgen-web-maintenance':
        skip = False
        continue
    if skip:
        continue
    if 'reportgen-web-runtime/backup.sh' in line or 'reportgen-web-runtime/restore_drill.sh' in line:
        continue
    out.append(line)

block = [
    '# BEGIN reportgen-web-maintenance',
    '$CRON_SCHEDULE APP_ROOT=$APP_ROOT LEGACY_APP_DIR=$LEGACY_APP_DIR RUNTIME_DIR=$RUNTIME_DIR STORAGE_DIR=$STORAGE_DIR RELEASES_DIR=$RELEASES_DIR BACKUP_DIR=$BACKUP_DIR BACKUP_KEEP_DAYS=$BACKUP_KEEP_DAYS RELEASE_KEEP_COUNT=$RELEASE_KEEP_COUNT PREVIEW_KEEP_DAYS=$PREVIEW_KEEP_DAYS LOG_KEEP_DAYS=$LOG_KEEP_DAYS UPLOAD_KEEP_DAYS=$UPLOAD_KEEP_DAYS REPORT_KEEP_DAYS=$REPORT_KEEP_DAYS ZIP_KEEP_DAYS=$ZIP_KEEP_DAYS AUDIT_LOG_KEEP_DAYS=$AUDIT_LOG_KEEP_DAYS $RUNTIME_DIR/backup.sh all >/dev/null 2>&1',
    '$RESTORE_DRILL_SCHEDULE APP_ROOT=$APP_ROOT RUNTIME_DIR=$RUNTIME_DIR BACKUP_DIR=$BACKUP_DIR $RUNTIME_DIR/restore_drill.sh run >/dev/null 2>&1',
    '# END reportgen-web-maintenance',
]
if out and out[-1].strip():
    out.append('')
out.extend(block)
path.write_text('\\n'.join(out) + '\\n')
PY
crontab \"\$tmp\"
rm -f \"\$tmp\"
crontab -l
"

echo "== Dry-run cleanup preview =="
ssh "$SSH_HOST" "DRY_RUN=1 '$RUNTIME_DIR/backup.sh' cleanup; tail -n 80 '$RUNTIME_DIR/logs/maintenance.log'"
