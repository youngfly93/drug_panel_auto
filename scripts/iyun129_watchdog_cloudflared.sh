#!/usr/bin/env bash
# Monitor the iyun129 panel connector without origin-to-public hairpin probes.

set -euo pipefail

RUNTIME_DIR="${RUNTIME_DIR:-/media/desk16/iy12922/apps/reportgen-web-runtime}"
DEPLOYMENT_ENV="${DEPLOYMENT_ENV:-$RUNTIME_DIR/deployment.env}"
if [ -f "$DEPLOYMENT_ENV" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$DEPLOYMENT_ENV"
    set +a
fi

CLOUDFLARED_TOKEN_FILE="${CLOUDFLARED_TOKEN_FILE:-/media/desk16/iy12922/.cloudflared/panel-reportgen.token}"
TUNNEL_METRICS_URL="${TUNNEL_METRICS_URL:-http://127.0.0.1:20242/metrics}"
RESTART_THRESHOLD="${TUNNEL_RESTART_THRESHOLD:-3}"
LOG_MAX_BYTES="${LOG_MAX_BYTES:-5242880}"
PID_FILE="$RUNTIME_DIR/panel-cloudflared.pid"
FAIL_FILE="$RUNTIME_DIR/panel-cloudflared-fail-count"
START_SCRIPT="$RUNTIME_DIR/start_panel_cloudflared.sh"
LOG_DIR="$RUNTIME_DIR/logs"
LOG_FILE="$LOG_DIR/panel-cloudflared-watchdog.log"

mkdir -p "$LOG_DIR"
if [ -f "$LOG_FILE" ] && [ "$(wc -c < "$LOG_FILE")" -gt "$LOG_MAX_BYTES" ]; then
    mv -f "$LOG_FILE" "$LOG_FILE.1"
fi
log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_FILE"; }

if [ ! -s "$CLOUDFLARED_TOKEN_FILE" ]; then
    log "connector fail token_missing"
    exit 0
fi

pid="$(cat "$PID_FILE" 2>/dev/null || true)"
connections="$(curl -fsS --max-time 3 "$TUNNEL_METRICS_URL" 2>/dev/null | \
    awk '$1 == "cloudflared_tunnel_ha_connections" {print int($2); exit}' || true)"
if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null && \
        [ "${connections:-0}" -ge 1 ]; then
    rm -f "$FAIL_FILE"
    log "connector ok pid=$pid connections=$connections protocol=http2"
    exit 0
fi

failures="$(cat "$FAIL_FILE" 2>/dev/null || echo 0)"
failures=$((failures + 1))
printf '%s\n' "$failures" > "$FAIL_FILE"
if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null && \
        [ "$failures" -lt "$RESTART_THRESHOLD" ]; then
    log "connector warn pid=$pid connections=${connections:-0} failures=$failures"
    exit 0
fi

log "connector restart pid=${pid:-none} connections=${connections:-0} failures=$failures"
if bash "$START_SCRIPT" >> "$LOG_FILE" 2>&1; then
    rm -f "$FAIL_FILE"
    log "connector restart_ok"
else
    log "connector restart_failed"
fi
