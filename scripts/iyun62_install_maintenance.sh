#!/usr/bin/env bash
# Install iyun62 backup/cleanup maintenance into reportgen-web-runtime and crontab.

set -euo pipefail

SSH_HOST="${SSH_HOST:-iyun-server}"
APP_ROOT="${APP_ROOT:-/media/desk16/iyun6208/apps}"
RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
CRON_SCHEDULE="${CRON_SCHEDULE:-17 2 * * *}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
RELEASE_KEEP_COUNT="${RELEASE_KEEP_COUNT:-8}"
PREVIEW_KEEP_DAYS="${PREVIEW_KEEP_DAYS:-7}"
LOG_KEEP_DAYS="${LOG_KEEP_DAYS:-14}"

if [ ! -f "scripts/iyun62_backup.sh" ]; then
    echo "Run this script from the reportgen-web repository root." >&2
    exit 1
fi

echo "== Upload maintenance script =="
ssh "$SSH_HOST" "mkdir -p '$RUNTIME_DIR/logs'"
rsync -az scripts/iyun62_backup.sh "$SSH_HOST:$RUNTIME_DIR/backup.sh"
ssh "$SSH_HOST" "chmod +x '$RUNTIME_DIR/backup.sh'"

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
    if 'reportgen-web-runtime/backup.sh' in line:
        continue
    out.append(line)

block = [
    '# BEGIN reportgen-web-maintenance',
    '$CRON_SCHEDULE BACKUP_KEEP_DAYS=$BACKUP_KEEP_DAYS RELEASE_KEEP_COUNT=$RELEASE_KEEP_COUNT PREVIEW_KEEP_DAYS=$PREVIEW_KEEP_DAYS LOG_KEEP_DAYS=$LOG_KEEP_DAYS $RUNTIME_DIR/backup.sh all >/dev/null 2>&1',
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

