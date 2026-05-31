#!/usr/bin/env bash
# Start reportgen-web on iyun62 from a clean release directory.
#
# This script is intended to run on iyun62 as the iyun6208 user. It avoids
# touching the legacy dirty worktree and keeps runtime state outside releases.

set -euo pipefail

APP_ROOT="${APP_ROOT:-/media/desk16/iyun6208/apps}"
RELEASE_DIR="${RELEASE_DIR:?RELEASE_DIR is required}"
STORAGE_DIR="${STORAGE_DIR:?STORAGE_DIR is required}"
VENV_DIR="${VENV_DIR:?VENV_DIR is required}"
RUNTIME_DIR="${RUNTIME_DIR:?RUNTIME_DIR is required}"
BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/reportgen-web-backups}"
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
APP_MODULE="${APP_MODULE:-app.main:app}"

LOG_DIR="$RUNTIME_DIR/logs"
ENV_FILE="$RUNTIME_DIR/.env.prod"
LOG_FILE="$LOG_DIR/uvicorn.log"
PID_FILE="$RUNTIME_DIR/reportgen-web.pid"
CURRENT_RELEASE_FILE="$RUNTIME_DIR/current_release"

mkdir -p "$LOG_DIR" "$STORAGE_DIR"/{uploads,reports,previews,db,signatures,reference_reports}

if [ ! -x "$VENV_DIR/bin/python" ] || [ ! -x "$VENV_DIR/bin/uvicorn" ]; then
    echo "Missing Python runtime in $VENV_DIR" >&2
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    secret_key="$("$VENV_DIR/bin/python" - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
    cat > "$ENV_FILE" <<EOF
RG_WEB_SECRET_KEY=$secret_key
RG_WEB_MAX_WORKERS=2
EOF
    chmod 600 "$ENV_FILE"
fi

stop_existing() {
    REPORTGEN_PORT="$PORT" "$VENV_DIR/bin/python" - <<'PY'
import os
import signal
import time

current = os.getpid()
port = os.environ.get("REPORTGEN_PORT", "8000")
targets = []
for name in os.listdir("/proc"):
    if not name.isdigit():
        continue
    pid = int(name)
    if pid == current:
        continue
    try:
        raw = open(f"/proc/{pid}/cmdline", "rb").read()
    except OSError:
        continue
    text = raw.replace(b"\x00", b" ").decode("utf-8", "ignore")
    if "uvicorn" in text and "app.main:app" in text and f"--port {port}" in text:
        targets.append(pid)

for pid in targets:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

deadline = time.time() + 10
remaining = set(targets)
while remaining and time.time() < deadline:
    for pid in list(remaining):
        if not os.path.exists(f"/proc/{pid}"):
            remaining.remove(pid)
    time.sleep(0.2)

for pid in remaining:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

if targets:
    print("Stopped uvicorn PIDs:", " ".join(map(str, targets)))
PY
}

stop_existing

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

export RG_WEB_UPSTREAM_ROOT="$RELEASE_DIR"
export RG_WEB_STORAGE_ROOT="$STORAGE_DIR"
export RG_WEB_RUNTIME_DIR="$RUNTIME_DIR"
export RG_WEB_BACKUP_DIR="$BACKUP_DIR"

cd "$RELEASE_DIR"
nohup "$VENV_DIR/bin/python" "$VENV_DIR/bin/uvicorn" "$APP_MODULE" \
    --host "$HOST" \
    --port "$PORT" \
    --app-dir backend \
    >> "$LOG_FILE" 2>&1 &

pid=$!
echo "$pid" > "$PID_FILE"
printf '%s\n' "$RELEASE_DIR" > "$CURRENT_RELEASE_FILE"

sleep 5
if ! kill -0 "$pid" 2>/dev/null; then
    echo "uvicorn failed to stay running; recent log follows:" >&2
    tail -n 80 "$LOG_FILE" >&2 || true
    exit 1
fi

code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/v1/tasks/stats" || true)"
if [ "$code" != "200" ]; then
    echo "Health check failed: HTTP $code" >&2
    tail -n 80 "$LOG_FILE" >&2 || true
    exit 1
fi

echo "reportgen-web running from $RELEASE_DIR"
echo "pid=$pid"
echo "health=HTTP $code"
