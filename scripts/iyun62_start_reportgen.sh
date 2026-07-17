#!/usr/bin/env bash
# Start reportgen-web from an immutable release directory.
#
# The filename is kept for backward compatibility with the former iyun62
# deployment. Runtime coordinates are loaded from deployment.env, so the same
# implementation can safely serve iyun129 without hardcoded release paths.

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
RELEASES_DIR="${RELEASES_DIR:-$APP_ROOT/reportgen-web-releases}"
RUNTIME_DIR="${RUNTIME_DIR:-$SCRIPT_DIR}"
STORAGE_DIR="${STORAGE_DIR:?STORAGE_DIR is required}"
VENV_DIR="${VENV_DIR:?VENV_DIR is required}"
BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/reportgen-web-backups}"
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
APP_MODULE="${APP_MODULE:-app.main:app}"
LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://127.0.0.1:$PORT/api/v1/healthz}"
LEGACY_LOCAL_HEALTH_URL="${LEGACY_LOCAL_HEALTH_URL:-http://127.0.0.1:$PORT/api/v1/tasks/stats}"
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-60}"
HEALTH_STABLE_CHECKS="${HEALTH_STABLE_CHECKS:-2}"

LOG_DIR="$RUNTIME_DIR/logs"
ENV_FILE="$RUNTIME_DIR/.env.prod"
LOG_FILE="$LOG_DIR/uvicorn.log"
PID_FILE="$RUNTIME_DIR/reportgen-web.pid"
CURRENT_RELEASE_FILE="$RUNTIME_DIR/current_release"
SWITCH_LOCK_FILE="${SWITCH_LOCK_FILE:-$RUNTIME_DIR/run/reportgen-web.switch.lock}"
FLOCK_BIN="${FLOCK_BIN:-flock}"

mkdir -p "$LOG_DIR" "$RUNTIME_DIR/run" \
    "$STORAGE_DIR"/{uploads,reports,previews,db,signatures,reference_reports}

acquire_switch_lock() {
    # A watchdog that invokes this script already owns descriptor 9. Reusing
    # the inherited descriptor avoids self-deadlock while keeping one lock for
    # the complete stop -> health validation -> commit/rollback transition.
    if [ "${REPORTGEN_SWITCH_LOCK_HELD:-0}" = "1" ] && \
            [ -e "/proc/$$/fd/9" ]; then
        return 0
    fi
    if ! command -v "$FLOCK_BIN" >/dev/null 2>&1; then
        echo "Missing required switch-lock command: $FLOCK_BIN" >&2
        return 1
    fi
    exec 9> "$SWITCH_LOCK_FILE"
    "$FLOCK_BIN" -x 9
    export REPORTGEN_SWITCH_LOCK_HELD=1
}

acquire_switch_lock

if [ -z "${RELEASE_DIR:-}" ] && [ -f "$CURRENT_RELEASE_FILE" ]; then
    read -r RELEASE_DIR < "$CURRENT_RELEASE_FILE"
fi
RELEASE_DIR="${RELEASE_DIR:?RELEASE_DIR is required (or current_release must exist)}"

canonical_dir() {
    "$VENV_DIR/bin/python" - "$1" <<'PY'
import os
import sys

print(os.path.realpath(sys.argv[1]))
PY
}

validate_release() {
    local release releases_root revision
    release="$(canonical_dir "$1")"
    releases_root="$(canonical_dir "$RELEASES_DIR")"
    case "$release" in
        "$releases_root"/*) ;;
        *)
            echo "Release is outside RELEASES_DIR: $release" >&2
            return 1
            ;;
    esac
    if [ ! -d "$release" ] || [ ! -f "$release/REVISION" ]; then
        echo "Release directory or REVISION is missing: $release" >&2
        return 1
    fi
    revision="$(head -n 1 "$release/REVISION")"
    if [[ ! "$revision" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
        echo "Invalid REVISION in $release" >&2
        return 1
    fi
    printf '%s\n' "$release"
}

if [ ! -x "$VENV_DIR/bin/python" ] || [ ! -x "$VENV_DIR/bin/uvicorn" ]; then
    echo "Missing Python runtime in $VENV_DIR" >&2
    exit 1
fi

RELEASE_DIR="$(validate_release "$RELEASE_DIR")"
previous_release=""
if [ -f "$CURRENT_RELEASE_FILE" ]; then
    read -r previous_release < "$CURRENT_RELEASE_FILE" || true
    if [ -n "$previous_release" ] && [ -d "$previous_release" ]; then
        previous_release="$(canonical_dir "$previous_release")"
    else
        previous_release=""
    fi
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

# A killed predecessor may still hold the runtime flock for a short window.
# Wait for /proc removal before allowing the candidate to start.
deadline = time.time() + 10
while remaining and time.time() < deadline:
    for pid in list(remaining):
        if not os.path.exists(f"/proc/{pid}"):
            remaining.remove(pid)
    time.sleep(0.1)

if remaining:
    raise SystemExit(
        "uvicorn processes did not terminate: " + " ".join(map(str, remaining))
    )

if targets:
    print("Stopped uvicorn PIDs:", " ".join(map(str, targets)))
PY
}

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# Deployment-controlled safety settings must win over stale values in the
# long-lived secret file (for example a historical wildcard CORS value).
if [ -f "$DEPLOYMENT_ENV" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$DEPLOYMENT_ENV"
    set +a
fi

# Production reports must contain ReportGen PAGEREF fields plus cached page
# numbers.  The old FAST_TOC/skip switches omit that construction and can leave
# an empty TOC while the service itself still looks healthy.  Refuse to stop a
# known-good process when any of these unsafe shortcuts is enabled.
for unsafe_toc_flag in \
    REPORTGEN_FAST_TOC \
    REPORTGEN_SKIP_FINAL_LO_REFRESH \
    REPORTGEN_SKIP_STATIC_TOC_PAGE_NUMBERS; do
    unsafe_toc_value="${!unsafe_toc_flag:-}"
    case "$unsafe_toc_value" in
        1|true|TRUE|True|yes|YES|Yes|y|Y|on|ON|On)
            echo "$unsafe_toc_flag must be disabled for production report generation." >&2
            exit 1
            ;;
    esac
done

export RG_WEB_STORAGE_ROOT="$STORAGE_DIR"
export RG_WEB_RUNTIME_DIR="$RUNTIME_DIR"
export RG_WEB_BACKUP_DIR="$BACKUP_DIR"
# Clinical metadata is runtime/PII state.  Keep both the Web enrichment layer
# and the report generator on the same external registry instead of reading or
# mutating config/patient_info.yaml inside an immutable release.
export REPORTGEN_PATIENT_INFO_PATH="${REPORTGEN_PATIENT_INFO_PATH:-$STORAGE_DIR/patient_info.yaml}"

STARTED_PID=""
LAST_HEALTH_CODE="000"

start_release() {
    local release="$1" expected_cwd actual_cwd process_state process_cmdline attempt stable_checks health_url
    expected_cwd="$(canonical_dir "$release")"
    health_url="$LOCAL_HEALTH_URL"
    if [ ! -f "$expected_cwd/backend/app/api/health.py" ]; then
        # Compatibility only for rollback to a pre-healthz immutable release.
        health_url="$LEGACY_LOCAL_HEALTH_URL"
    fi
    export RG_WEB_UPSTREAM_ROOT="$expected_cwd"
    cd "$expected_cwd"
    nohup "$VENV_DIR/bin/python" "$VENV_DIR/bin/uvicorn" "$APP_MODULE" \
        --host "$HOST" \
        --port "$PORT" \
        --app-dir backend \
        >> "$LOG_FILE" 2>&1 9>&- &

    STARTED_PID=$!
    echo "$STARTED_PID" > "$PID_FILE"
    LAST_HEALTH_CODE="000"
    stable_checks=0

    for attempt in $(seq 1 "$HEALTH_TIMEOUT_SECONDS"); do
        if ! kill -0 "$STARTED_PID" 2>/dev/null; then
            return 1
        fi
        process_state="$(awk '/^State:/ {print $2}' "/proc/$STARTED_PID/status" 2>/dev/null || true)"
        if [ -z "$process_state" ] || [ "$process_state" = "Z" ]; then
            return 1
        fi
        LAST_HEALTH_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 \
            "$health_url" || true)"
        if [ "$LAST_HEALTH_CODE" = "200" ]; then
            actual_cwd="$(readlink "/proc/$STARTED_PID/cwd" 2>/dev/null || true)"
            process_state="$(awk '/^State:/ {print $2}' "/proc/$STARTED_PID/status" 2>/dev/null || true)"
            process_cmdline="$(tr '\000' ' ' < "/proc/$STARTED_PID/cmdline" 2>/dev/null || true)"
            if [ -n "$process_state" ] && [ "$process_state" != "Z" ] && \
                    [ "$(canonical_dir "${actual_cwd:-/nonexistent}")" = "$expected_cwd" ] && \
                    [[ "$process_cmdline" == *uvicorn* ]] && \
                    [[ "$process_cmdline" == *"--port $PORT"* ]]; then
                stable_checks=$((stable_checks + 1))
                if [ "$stable_checks" -ge "$HEALTH_STABLE_CHECKS" ]; then
                    return 0
                fi
            else
                stable_checks=0
            fi
        else
            stable_checks=0
        fi
        sleep 1
    done
    return 1
}

write_current_release() {
    local release="$1" tmp
    tmp="$(mktemp "$RUNTIME_DIR/.current_release.XXXXXX")"
    printf '%s\n' "$release" > "$tmp"
    mv -f "$tmp" "$CURRENT_RELEASE_FILE"
}

stop_existing
if start_release "$RELEASE_DIR"; then
    write_current_release "$RELEASE_DIR"
    echo "reportgen-web running from $RELEASE_DIR"
    echo "revision=$(head -n 1 "$RELEASE_DIR/REVISION")"
    echo "pid=$STARTED_PID"
    echo "health=HTTP $LAST_HEALTH_CODE"
    exit 0
fi

echo "Target release failed health/cwd validation: $RELEASE_DIR (HTTP $LAST_HEALTH_CODE)" >&2
tail -n 80 "$LOG_FILE" >&2 || true
stop_existing

if [ -n "$previous_release" ] && [ "$previous_release" != "$RELEASE_DIR" ] && \
        previous_release="$(validate_release "$previous_release")"; then
    echo "Attempting automatic rollback to $previous_release" >&2
    if start_release "$previous_release"; then
        write_current_release "$previous_release"
        echo "rollback_release=$previous_release" >&2
        echo "rollback_health=HTTP $LAST_HEALTH_CODE" >&2
        exit 1
    fi
    echo "Automatic rollback also failed: $previous_release" >&2
    tail -n 80 "$LOG_FILE" >&2 || true
fi

exit 1
