#!/usr/bin/env bash
# User-level watchdog for a clean-release reportgen-web deployment.
#
# The filename is kept for backward compatibility. Environment-specific paths
# and ports come from deployment.env beside the runtime copy of this script.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-$SCRIPT_DIR}"
DEPLOYMENT_ENV="${DEPLOYMENT_ENV:-$RUNTIME_DIR/deployment.env}"
if [ -f "$DEPLOYMENT_ENV" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$DEPLOYMENT_ENV"
    set +a
fi

APP_ROOT="${APP_ROOT:-/media/desk16/iyun6208/apps}"
LEGACY_APP_DIR="${LEGACY_APP_DIR:-$APP_ROOT/reportgen-web}"
RELEASES_DIR="${RELEASES_DIR:-$APP_ROOT/reportgen-web-releases}"
RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
STORAGE_DIR="${STORAGE_DIR:-$LEGACY_APP_DIR/storage}"
VENV_DIR="${VENV_DIR:-$LEGACY_APP_DIR/.venv}"
BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/reportgen-web-backups}"
PORT="${PORT:-8000}"
LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://127.0.0.1:$PORT/api/v1/healthz}"
LEGACY_LOCAL_HEALTH_URL="${LEGACY_LOCAL_HEALTH_URL:-http://127.0.0.1:$PORT/api/v1/tasks/stats}"
PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-https://panel.mailuo-report.com.cn/api/v1/healthz}"
TUNNEL_METRICS_URL="${TUNNEL_METRICS_URL:-http://127.0.0.1:20242/metrics}"
CLOUDFLARED="${CLOUDFLARED:-/media/desk16/iyun6208/bin/cloudflared}"
CLOUDFLARED_TOKEN_FILE="${CLOUDFLARED_TOKEN_FILE:-/media/desk16/iyun6208/.config/reportgen-web/cloudflared-token}"
DISK_WARN_PERCENT="${DISK_WARN_PERCENT:-85}"
LOG_MAX_BYTES="${LOG_MAX_BYTES:-5242880}"
TUNNEL_RESTART_THRESHOLD="${TUNNEL_RESTART_THRESHOLD:-3}"
MANAGE_TUNNEL="${MANAGE_TUNNEL:-1}"

LOG_DIR="$RUNTIME_DIR/logs"
LOG_FILE="$LOG_DIR/watchdog.log"
START_SCRIPT="$RUNTIME_DIR/start_reportgen.sh"
CURRENT_RELEASE_FILE="$RUNTIME_DIR/current_release"
CLOUDFLARED_PID_FILE="$RUNTIME_DIR/cloudflared.pid"
TUNNEL_FAIL_COUNT_FILE="$RUNTIME_DIR/tunnel_fail_count"
SWITCH_LOCK_FILE="${SWITCH_LOCK_FILE:-$RUNTIME_DIR/run/reportgen-web.switch.lock}"
FLOCK_BIN="${FLOCK_BIN:-flock}"

mkdir -p "$LOG_DIR" "$RUNTIME_DIR/run"

rotate_log() {
    if [ -f "$LOG_FILE" ]; then
        size="$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)"
        if [ "${size:-0}" -gt "$LOG_MAX_BYTES" ]; then
            mv "$LOG_FILE" "$LOG_FILE.1"
        fi
    fi
}

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_FILE"
}

acquire_switch_lock() {
    if ! command -v "$FLOCK_BIN" >/dev/null 2>&1; then
        log "watchdog fail missing switch-lock command=$FLOCK_BIN"
        return 1
    fi
    exec 9> "$SWITCH_LOCK_FILE"
    if ! "$FLOCK_BIN" -n -x 9; then
        log "watchdog skip deployment switch lock held"
        return 2
    fi
    # start_reportgen.sh inherits descriptor 9 when watchdog performs a
    # recovery. It must reuse the lock instead of trying to acquire it again.
    export REPORTGEN_SWITCH_LOCK_HELD=1
}

http_code() {
    curl -sS --max-time 8 -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || true
}

current_release() {
    if [ -f "$CURRENT_RELEASE_FILE" ]; then
        read -r release < "$CURRENT_RELEASE_FILE"
        if [ -n "${release:-}" ] && [ -d "$release" ]; then
            printf '%s\n' "$release"
            return 0
        fi
    fi
    find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d \
        -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -n 1 | cut -d' ' -f2-
}

release_health_url() {
    local release="$1"
    if [ -f "$release/backend/app/api/health.py" ]; then
        printf '%s\n' "$LOCAL_HEALTH_URL"
    else
        # Compatibility only for switching or rolling back to a pre-healthz
        # immutable release. New releases always use the minimal health route.
        printf '%s\n' "$LEGACY_LOCAL_HEALTH_URL"
    fi
}

web_process_state() {
    local release
    release="$1"
    REPORTGEN_PORT="$PORT" EXPECTED_RELEASE="$release" "$VENV_DIR/bin/python" - <<'PY'
import os

port = os.environ.get("REPORTGEN_PORT", "8000")
expected = os.path.realpath(os.environ["EXPECTED_RELEASE"])
records = []

for name in os.listdir("/proc"):
    if not name.isdigit():
        continue
    pid = int(name)
    try:
        raw = open(f"/proc/{pid}/cmdline", "rb").read()
    except OSError:
        continue
    text = raw.replace(b"\x00", b" ").decode("utf-8", "ignore")
    if "uvicorn" not in text or "app.main:app" not in text or f"--port {port}" not in text:
        continue

    root = ""
    try:
        env_raw = open(f"/proc/{pid}/environ", "rb").read()
        for item in env_raw.split(b"\x00"):
            if item.startswith(b"RG_WEB_UPSTREAM_ROOT="):
                root = item.split(b"=", 1)[1].decode("utf-8", "ignore")
                break
    except OSError:
        pass
    if not root:
        try:
            root = os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            root = ""

    root_real = os.path.realpath(root) if root else ""
    records.append((pid, root_real))

if any(root == expected for _, root in records):
    pid, root = next((pid, root) for pid, root in records if root == expected)
    print(f"ok pid={pid} release={root}")
elif records:
    details = ",".join(f"{pid}:{root or 'unknown'}" for pid, root in records)
    print(f"mismatch expected={expected} running={details}")
else:
    print(f"missing expected={expected}")
PY
}

ensure_web() {
    local code release state health_url
    release="$(current_release)"
    if [ -z "${release:-}" ] || [ ! -d "$release" ]; then
        code="$(http_code "$LOCAL_HEALTH_URL")"
        if [ "$code" = "200" ]; then
            log "web fail local_http=$code; no usable release found"
        else
            log "web fail local_http=${code:-none}; no usable release found"
        fi
        return 1
    fi

    health_url="$(release_health_url "$release")"
    code="$(http_code "$health_url")"
    state="$(web_process_state "$release" 2>/dev/null || echo unknown)"
    if [ "$code" = "200" ] && [[ "$state" == ok\ * ]]; then
        log "web ok local_http=$code $state"
        return 0
    fi

    if [ ! -x "$START_SCRIPT" ]; then
        log "web fail local_http=${code:-none} state=$state; missing start script $START_SCRIPT"
        return 1
    fi

    log "web restart local_http=${code:-none} state=$state release=$release"
    RELEASE_DIR="$release" \
        APP_ROOT="$APP_ROOT" \
        RELEASES_DIR="$RELEASES_DIR" \
        STORAGE_DIR="$STORAGE_DIR" \
        VENV_DIR="$VENV_DIR" \
        RUNTIME_DIR="$RUNTIME_DIR" \
        BACKUP_DIR="$BACKUP_DIR" \
        PORT="$PORT" \
        bash "$START_SCRIPT" >> "$LOG_FILE" 2>&1
}

start_tunnel() {
    if [ ! -x "$CLOUDFLARED" ] || [ ! -f "$CLOUDFLARED_TOKEN_FILE" ]; then
        log "tunnel fail missing cloudflared or token"
        return 1
    fi

    mkdir -p "$LOG_DIR"
    nohup "$CLOUDFLARED" tunnel --no-autoupdate --protocol http2 run \
        --token-file "$CLOUDFLARED_TOKEN_FILE" \
        >> "$LOG_DIR/cloudflared.log" 2>&1 &
    echo "$!" > "$CLOUDFLARED_PID_FILE"
    rm -f "$TUNNEL_FAIL_COUNT_FILE"
    log "tunnel started pid=$!"
}

ensure_tunnel() {
    local public_code oldpid failures
    public_code="$(http_code "$PUBLIC_HEALTH_URL")"
    if [ "$public_code" = "200" ]; then
        rm -f "$TUNNEL_FAIL_COUNT_FILE"
        if ! pgrep -f "[c]loudflared tunnel --no-autoupdate --protocol http2 run --token-file" >/dev/null 2>&1; then
            log "tunnel public ok but process missing; starting anyway"
            start_tunnel
        else
            log "tunnel ok public_http=$public_code"
        fi
        return 0
    fi

    if ! pgrep -f "[c]loudflared tunnel --no-autoupdate --protocol http2 run --token-file" >/dev/null 2>&1; then
        log "tunnel restart process_missing public_http=${public_code:-none}"
        start_tunnel
        return 0
    fi

    failures="$(cat "$TUNNEL_FAIL_COUNT_FILE" 2>/dev/null || echo 0)"
    failures=$((failures + 1))
    printf '%s\n' "$failures" > "$TUNNEL_FAIL_COUNT_FILE"
    if [ "$failures" -lt "$TUNNEL_RESTART_THRESHOLD" ]; then
        log "tunnel warn public_http=${public_code:-none} consecutive_failures=$failures threshold=$TUNNEL_RESTART_THRESHOLD"
        return 0
    fi

    if pgrep -f "[c]loudflared tunnel --no-autoupdate --protocol http2 run --token-file" >/dev/null 2>&1; then
        oldpid="$(cat "$CLOUDFLARED_PID_FILE" 2>/dev/null || true)"
        if [ -n "${oldpid:-}" ] && kill -0 "$oldpid" 2>/dev/null; then
            kill "$oldpid" || true
        fi
        pkill -f "[c]loudflared tunnel --no-autoupdate --protocol http2 run --token-file" >/dev/null 2>&1 || true
        sleep 2
    fi
    log "tunnel restart public_http=${public_code:-none} consecutive_failures=$failures"
    start_tunnel
}

check_external_tunnel() {
    local connections
    connections="$(curl -fsS --max-time 4 "$TUNNEL_METRICS_URL" 2>/dev/null | \
        awk '$1 == "cloudflared_tunnel_ha_connections" {print int($2); exit}' || true)"
    if [ "${connections:-0}" -ge 1 ]; then
        log "tunnel ok connector_connections=$connections external_manager"
        return 0
    fi
    log "tunnel fail connector_connections=${connections:-0} external_manager"
    return 1
}

check_disk() {
    local pct
    pct="$(df -P "$STORAGE_DIR" 2>/dev/null | awk 'NR==2 {gsub(/%/, "", $5); print $5}')"
    if [ -n "${pct:-}" ] && [ "$pct" -ge "$DISK_WARN_PERCENT" ]; then
        log "disk warn storage_percent=${pct}"
    fi
}

check_libreoffice() {
    if pgrep -f "soffice.*port=2202" >/dev/null 2>&1; then
        log "libreoffice listener ok"
    else
        log "libreoffice listener missing; app will attempt startup warmup on next render"
    fi
}

main() {
    local lock_status
    rotate_log
    if acquire_switch_lock; then
        :
    else
        lock_status=$?
        if [ "$lock_status" -eq 2 ]; then
            return 0
        fi
        return "$lock_status"
    fi
    log "watchdog begin"
    ensure_web || true
    if [ "$MANAGE_TUNNEL" = "1" ]; then
        ensure_tunnel || true
    else
        check_external_tunnel || true
    fi
    check_disk || true
    check_libreoffice || true
    log "watchdog end"
}

main "$@"
