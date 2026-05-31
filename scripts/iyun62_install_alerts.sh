#!/usr/bin/env bash
# Install iyun62 active alert checks into reportgen-web-runtime and crontab.

set -euo pipefail

SSH_HOST="${SSH_HOST:-iyun-server}"
APP_ROOT="${APP_ROOT:-/media/desk16/iyun6208/apps}"
RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
CRON_SCHEDULE="${CRON_SCHEDULE:-*/5 * * * *}"
ALERT_FORMAT="${ALERT_FORMAT:-auto}"
ALERT_MIN_SEVERITY="${ALERT_MIN_SEVERITY:-warning}"
ALERT_REPEAT_MINUTES="${ALERT_REPEAT_MINUTES:-60}"
ALERT_SEND_RECOVERY="${ALERT_SEND_RECOVERY:-1}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-${RG_WEB_ALERT_WEBHOOK_URL:-}}"

if [ ! -f "scripts/iyun62_alerts.sh" ]; then
    echo "Run this script from the reportgen-web repository root." >&2
    exit 1
fi

echo "== Upload alerts script =="
ssh "$SSH_HOST" "mkdir -p '$RUNTIME_DIR/logs'"
rsync -az scripts/iyun62_alerts.sh "$SSH_HOST:$RUNTIME_DIR/alerts.sh"
ssh "$SSH_HOST" "chmod +x '$RUNTIME_DIR/alerts.sh'"

if [ -n "$ALERT_WEBHOOK_URL" ]; then
    echo "== Upload alerts env =="
    tmp_env="$(mktemp)"
    ALERT_WEBHOOK_URL="$ALERT_WEBHOOK_URL" \
    ALERT_FORMAT="$ALERT_FORMAT" \
    ALERT_MIN_SEVERITY="$ALERT_MIN_SEVERITY" \
    ALERT_REPEAT_MINUTES="$ALERT_REPEAT_MINUTES" \
    ALERT_SEND_RECOVERY="$ALERT_SEND_RECOVERY" \
    python3 - <<'PY' > "$tmp_env"
from __future__ import annotations

import os
import shlex

for key in (
    "ALERT_WEBHOOK_URL",
    "ALERT_FORMAT",
    "ALERT_MIN_SEVERITY",
    "ALERT_REPEAT_MINUTES",
    "ALERT_SEND_RECOVERY",
):
    value = os.environ.get(key)
    if value:
        print(f"{key}={shlex.quote(value)}")
PY
    rsync -az "$tmp_env" "$SSH_HOST:$RUNTIME_DIR/alerts.env"
    rm -f "$tmp_env"
    ssh "$SSH_HOST" "chmod 600 '$RUNTIME_DIR/alerts.env'"
else
    echo "ALERT_WEBHOOK_URL not set; cron will log active alerts without external delivery."
fi

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
    if stripped == '# BEGIN reportgen-web-alerts':
        skip = True
        continue
    if stripped == '# END reportgen-web-alerts':
        skip = False
        continue
    if skip:
        continue
    if 'reportgen-web-runtime/alerts.sh' in line:
        continue
    out.append(line)

block = [
    '# BEGIN reportgen-web-alerts',
    '$CRON_SCHEDULE $RUNTIME_DIR/alerts.sh check >/dev/null 2>&1',
    '# END reportgen-web-alerts',
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

echo "== Dry-run alert check =="
ssh "$SSH_HOST" "DRY_RUN=1 '$RUNTIME_DIR/alerts.sh' check; tail -n 40 '$RUNTIME_DIR/logs/alerts.log'"
