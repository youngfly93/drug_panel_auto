#!/usr/bin/env bash
# Install the active-alert cron contract with iyun129 production coordinates.

set -euo pipefail

export SSH_HOST="${SSH_HOST:-iyun129}"
export APP_ROOT="${APP_ROOT:-/media/desk16/iy12922/apps}"
export RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
export PORT="${PORT:-18082}"
export OPS_URL="${OPS_URL:-http://127.0.0.1:$PORT/api/v1/admin/ops/status?recent_task_limit=5&download_event_limit=50}"
export OPS_LOGIN_URL="${OPS_LOGIN_URL:-http://127.0.0.1:$PORT/api/v1/auth/login}"

exec bash scripts/iyun62_install_alerts.sh "$@"
