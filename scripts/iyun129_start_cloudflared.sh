#!/usr/bin/env bash
# Start the iyun129 panel Cloudflare connector with TCP-based HTTP/2.

set -euo pipefail

RUNTIME_DIR="${RUNTIME_DIR:-/media/desk16/iy12922/apps/reportgen-web-runtime}"
DEPLOYMENT_ENV="${DEPLOYMENT_ENV:-$RUNTIME_DIR/deployment.env}"
if [ -f "$DEPLOYMENT_ENV" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$DEPLOYMENT_ENV"
    set +a
fi

CLOUDFLARED="${CLOUDFLARED:-/media/desk16/iy12922/.local/bin/cloudflared}"
CLOUDFLARED_TOKEN_FILE="${CLOUDFLARED_TOKEN_FILE:-/media/desk16/iy12922/.cloudflared/panel-reportgen.token}"
LOCAL_ORIGIN_URL="${LOCAL_ORIGIN_URL:-http://127.0.0.1:18082}"
TUNNEL_METRICS_ADDR="${TUNNEL_METRICS_ADDR:-127.0.0.1:20242}"
TUNNEL_METRICS_URL="${TUNNEL_METRICS_URL:-http://$TUNNEL_METRICS_ADDR/metrics}"
PID_FILE="$RUNTIME_DIR/panel-cloudflared.pid"
LOG_DIR="$RUNTIME_DIR/logs"
LOG_FILE="$LOG_DIR/panel-cloudflared.log"
LOG_MAX_BYTES="${LOG_MAX_BYTES:-10485760}"

if [ ! -x "$CLOUDFLARED" ] || [ ! -s "$CLOUDFLARED_TOKEN_FILE" ]; then
    echo "cloudflared binary or token file is missing" >&2
    exit 2
fi

mkdir -p "$LOG_DIR"
if [ -f "$PID_FILE" ]; then
    old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "${old_pid:-}" ] && kill -0 "$old_pid" 2>/dev/null; then
        kill "$old_pid" 2>/dev/null || true
        for _ in $(seq 1 10); do
            kill -0 "$old_pid" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "$old_pid" 2>/dev/null; then
            kill -9 "$old_pid" 2>/dev/null || true
        fi
    fi
fi

if [ -f "$LOG_FILE" ] && [ "$(wc -c < "$LOG_FILE")" -gt "$LOG_MAX_BYTES" ]; then
    mv -f "$LOG_FILE" "$LOG_FILE.1"
fi

nohup "$CLOUDFLARED" tunnel --no-autoupdate \
    --protocol http2 \
    --metrics "$TUNNEL_METRICS_ADDR" \
    --url "$LOCAL_ORIGIN_URL" \
    run --token-file "$CLOUDFLARED_TOKEN_FILE" \
    >> "$LOG_FILE" 2>&1 &
pid=$!
printf '%s\n' "$pid" > "$PID_FILE"

for _ in $(seq 1 20); do
    if ! kill -0 "$pid" 2>/dev/null; then
        break
    fi
    connections="$(curl -fsS --max-time 3 "$TUNNEL_METRICS_URL" 2>/dev/null | \
        awk '$1 == "cloudflared_tunnel_ha_connections" {print int($2); exit}' || true)"
    if [ "${connections:-0}" -ge 1 ]; then
        echo "panel cloudflared running pid=$pid protocol=http2 connections=$connections"
        exit 0
    fi
    sleep 1
done

echo "panel cloudflared failed to establish an edge connection" >&2
tail -n 40 "$LOG_FILE" >&2 || true
kill "$pid" 2>/dev/null || true
exit 1
