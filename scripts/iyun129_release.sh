#!/usr/bin/env bash
# Inspect or switch the active iyun129 reportgen-web release.
#
# Usage:
#   bash scripts/iyun129_release.sh status
#   bash scripts/iyun129_release.sh switch <release-id-or-revision-prefix>
#   bash scripts/iyun129_release.sh rollback <known-good-release-id-or-revision-prefix>

set -euo pipefail

ACTION="${1:-status}"
TARGET="${2:-}"
SSH_HOST="${SSH_HOST:-iyun129}"
APP_ROOT="${APP_ROOT:-/media/desk16/iy12922/apps}"
LEGACY_APP_DIR="${LEGACY_APP_DIR:-$APP_ROOT/reportgen-web-prod}"
RELEASES_DIR="${RELEASES_DIR:-$APP_ROOT/reportgen-web-releases}"
RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
STORAGE_DIR="${STORAGE_DIR:-$APP_ROOT/reportgen-web-storage}"
VENV_DIR="${VENV_DIR:-$APP_ROOT/reportgen-web-venv}"
BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/reportgen-web-backups}"
PORT="${PORT:-18082}"
LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://127.0.0.1:$PORT/api/v1/healthz}"
LEGACY_LOCAL_HEALTH_URL="${LEGACY_LOCAL_HEALTH_URL:-http://127.0.0.1:$PORT/api/v1/tasks/stats}"
PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-https://panel.mailuo-report.com.cn/api/v1/healthz}"
TUNNEL_METRICS_URL="${TUNNEL_METRICS_URL:-http://127.0.0.1:20242/metrics}"
RG_WEB_DOCS_ENABLED="${RG_WEB_DOCS_ENABLED:-0}"
RG_WEB_CORS_ORIGINS="${RG_WEB_CORS_ORIGINS:-https://panel.mailuo-report.com.cn}"
# CRC301 and the lung588 draft remain disabled until their independent
# case-level UAT and promotion gates are complete.
RG_WEB_DISABLED_PROJECT_TYPES="${RG_WEB_DISABLED_PROJECT_TYPES:-crc_301_msi,lung_588_pdl1}"
REPORTGEN_DISABLED_PROJECT_TYPES="${REPORTGEN_DISABLED_PROJECT_TYPES:-$RG_WEB_DISABLED_PROJECT_TYPES}"

status_remote() {
    ssh "$SSH_HOST" bash -s -- \
        "$RUNTIME_DIR" "$LOCAL_HEALTH_URL" "$LEGACY_LOCAL_HEALTH_URL" <<'REMOTE'
set -euo pipefail
runtime_dir="$1"
health_url="$2"
legacy_health_url="$3"
current="$(head -n 1 "$runtime_dir/current_release")"
revision="$(head -n 1 "$current/REVISION")"
pid="$(cat "$runtime_dir/reportgen-web.pid")"
process_cwd="$(readlink "/proc/$pid/cwd")"
if [ ! -f "$current/backend/app/api/health.py" ]; then
    health_url="$legacy_health_url"
fi
health="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$health_url" || true)"
printf 'current_release=%s\nrevision=%s\npid=%s\nprocess_cwd=%s\nhealth=HTTP %s\n' \
    "$current" "$revision" "$pid" "$process_cwd" "$health"
test "$process_cwd" = "$current"
test "$health" = "200"
REMOTE
}

install_runtime_tools() {
    if [ ! -f scripts/iyun62_start_reportgen.sh ] || [ ! -f scripts/iyun62_watchdog.sh ]; then
        echo "Run this script from the reportgen-web repository root." >&2
        exit 1
    fi
    if [ -n "$(git status --porcelain -- scripts/iyun62_start_reportgen.sh scripts/iyun62_watchdog.sh scripts/iyun129_release.sh)" ]; then
        echo "Runtime-control scripts must be committed before a production switch." >&2
        git status --short -- \
            scripts/iyun62_start_reportgen.sh \
            scripts/iyun62_watchdog.sh \
            scripts/iyun129_release.sh
        exit 1
    fi

    runtime_config="$(mktemp)"
    trap 'rm -f "$runtime_config"' RETURN
    {
        printf 'APP_ROOT=%q\n' "$APP_ROOT"
        printf 'LEGACY_APP_DIR=%q\n' "$LEGACY_APP_DIR"
        printf 'RELEASES_DIR=%q\n' "$RELEASES_DIR"
        printf 'RUNTIME_DIR=%q\n' "$RUNTIME_DIR"
        printf 'STORAGE_DIR=%q\n' "$STORAGE_DIR"
        printf 'VENV_DIR=%q\n' "$VENV_DIR"
        printf 'BACKUP_DIR=%q\n' "$BACKUP_DIR"
        printf 'PORT=%q\n' "$PORT"
        printf 'LOCAL_HEALTH_URL=%q\n' "$LOCAL_HEALTH_URL"
        printf 'LEGACY_LOCAL_HEALTH_URL=%q\n' "$LEGACY_LOCAL_HEALTH_URL"
        printf 'PUBLIC_HEALTH_URL=%q\n' "$PUBLIC_HEALTH_URL"
        printf 'TUNNEL_METRICS_URL=%q\n' "$TUNNEL_METRICS_URL"
        printf 'MANAGE_TUNNEL=0\n'
        printf 'RG_WEB_DOCS_ENABLED=%q\n' "$RG_WEB_DOCS_ENABLED"
        printf 'RG_WEB_CORS_ORIGINS=%q\n' "$RG_WEB_CORS_ORIGINS"
        printf 'RG_WEB_DISABLED_PROJECT_TYPES=%q\n' "$RG_WEB_DISABLED_PROJECT_TYPES"
        printf 'REPORTGEN_DISABLED_PROJECT_TYPES=%q\n' "$REPORTGEN_DISABLED_PROJECT_TYPES"
    } > "$runtime_config"

    rsync -az scripts/iyun62_start_reportgen.sh "$SSH_HOST:$RUNTIME_DIR/start_reportgen.sh.next"
    rsync -az scripts/iyun62_watchdog.sh "$SSH_HOST:$RUNTIME_DIR/watchdog.sh.next"
    rsync -az "$runtime_config" "$SSH_HOST:$RUNTIME_DIR/deployment.env.next"
    ssh "$SSH_HOST" "set -euo pipefail
chmod 700 '$RUNTIME_DIR/start_reportgen.sh.next' '$RUNTIME_DIR/watchdog.sh.next'
chmod 600 '$RUNTIME_DIR/deployment.env.next'
mv -f '$RUNTIME_DIR/deployment.env.next' '$RUNTIME_DIR/deployment.env'
mv -f '$RUNTIME_DIR/start_reportgen.sh.next' '$RUNTIME_DIR/start_reportgen.sh'
mv -f '$RUNTIME_DIR/watchdog.sh.next' '$RUNTIME_DIR/watchdog.sh'
"
    rm -f "$runtime_config"
    trap - RETURN
}

resolve_remote() {
    local target="$1"
    ssh "$SSH_HOST" bash -s -- "$target" "$RELEASES_DIR" <<'REMOTE'
set -euo pipefail
target="$1"
releases_dir="$2"

if [[ ! "$target" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
    echo "Target must be a 7-40 character hexadecimal release ID or revision prefix." >&2
    exit 2
fi

matches=()
for release in "$releases_dir"/*; do
    [ -d "$release" ] || continue
    [ -f "$release/REVISION" ] || continue
    revision="$(head -n 1 "$release/REVISION")"
    basename="${release##*/}"
    if [[ "$basename" == "$target" || "$revision" == "$target"* ]]; then
        matches+=("$release")
    fi
done

if [ "${#matches[@]}" -ne 1 ]; then
    echo "Expected exactly one release for $target; found ${#matches[@]}." >&2
    printf '%s\n' "${matches[@]:-}" >&2
    exit 2
fi

printf '%s\n' "${matches[0]}"
REMOTE
}

switch_remote() {
    local target_release="$1"
    ssh "$SSH_HOST" bash -s -- "$target_release" "$RELEASES_DIR" "$RUNTIME_DIR" <<'REMOTE'
set -euo pipefail
target_release="$(readlink -f "$1")"
releases_dir="$(readlink -f "$2")"
runtime_dir="$3"
case "$target_release" in
    "$releases_dir"/*) ;;
    *)
        echo "Resolved release is outside RELEASES_DIR: $target_release" >&2
        exit 2
        ;;
esac
test -d "$target_release"
test -f "$target_release/REVISION"
previous_release="$(head -n 1 "$runtime_dir/current_release" 2>/dev/null || true)"
printf 'switch_from=%s\nswitch_to=%s\n' "$previous_release" "$target_release"
RELEASE_DIR="$target_release" bash "$runtime_dir/start_reportgen.sh"
REMOTE
}

case "$ACTION" in
    status)
        if [ -n "$TARGET" ]; then
            echo "status does not accept a release argument." >&2
            exit 2
        fi
        status_remote
        ;;
    switch|rollback)
        if [ -z "$TARGET" ]; then
            echo "$ACTION requires a release ID or revision prefix." >&2
            exit 2
        fi
        resolved_target="$(resolve_remote "$TARGET")"
        echo "resolved_release=$resolved_target"
        install_runtime_tools
        switch_remote "$resolved_target"
        status_remote
        curl -fsS -o /dev/null -w "$PUBLIC_HEALTH_URL HTTP %{http_code}\n" "$PUBLIC_HEALTH_URL"
        ;;
    *)
        echo "Usage: $0 {status|switch|rollback <release-id-or-revision-prefix>}" >&2
        exit 2
        ;;
esac
