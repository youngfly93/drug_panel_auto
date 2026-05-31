#!/usr/bin/env bash
# Install the iyun62 user-level watchdog into reportgen-web-runtime and crontab.

set -euo pipefail

SSH_HOST="${SSH_HOST:-iyun-server}"
APP_ROOT="${APP_ROOT:-/media/desk16/iyun6208/apps}"
RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
CRON_SCHEDULE="${CRON_SCHEDULE:-* * * * *}"

if [ ! -f "scripts/iyun62_watchdog.sh" ] || [ ! -f "scripts/iyun62_start_reportgen.sh" ]; then
    echo "Run this script from the reportgen-web repository root." >&2
    exit 1
fi

echo "== Upload watchdog scripts =="
ssh "$SSH_HOST" "mkdir -p '$RUNTIME_DIR/logs'"
rsync -az scripts/iyun62_watchdog.sh "$SSH_HOST:$RUNTIME_DIR/watchdog.sh"
rsync -az scripts/iyun62_start_reportgen.sh "$SSH_HOST:$RUNTIME_DIR/start_reportgen.sh"
ssh "$SSH_HOST" "chmod +x '$RUNTIME_DIR/watchdog.sh' '$RUNTIME_DIR/start_reportgen.sh'"

echo "== Install crontab =="
ssh "$SSH_HOST" "set -euo pipefail
tmp=\$(mktemp)
crontab -l 2>/dev/null > \"\$tmp\" || true
python3 - \"\$tmp\" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
lines = path.read_text().splitlines()
out = []
skip = False
for line in lines:
    stripped = line.strip()
    if stripped == '# BEGIN reportgen-web-watchdog':
        skip = True
        continue
    if stripped == '# END reportgen-web-watchdog':
        skip = False
        continue
    if skip:
        continue
    if 'reportgen-watchdog.sh' in line:
        continue
    if 'reportgen-web-runtime/watchdog.sh' in line:
        continue
    out.append(line)

block = [
    '# BEGIN reportgen-web-watchdog',
    '$CRON_SCHEDULE $RUNTIME_DIR/watchdog.sh >/dev/null 2>&1',
    '@reboot sleep 30 && $RUNTIME_DIR/watchdog.sh >/dev/null 2>&1',
    '# END reportgen-web-watchdog',
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

echo "== Run one watchdog check =="
ssh "$SSH_HOST" "bash '$RUNTIME_DIR/watchdog.sh'; tail -n 40 '$RUNTIME_DIR/logs/watchdog.log'"
