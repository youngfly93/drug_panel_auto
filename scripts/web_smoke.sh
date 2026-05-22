#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${WEB_SMOKE_HOST:-127.0.0.1}"
PORT="${WEB_SMOKE_PORT:-8000}"
BASE_URL="${WEB_SMOKE_BASE_URL:-http://${HOST}:${PORT}}"
RUN_BUILD="${WEB_SMOKE_BUILD:-1}"
KEEP_SERVER="${WEB_SMOKE_KEEP_SERVER:-0}"
OUTPUT_ROOT="${WEB_SMOKE_OUTPUT_ROOT:-${ROOT}/tmp/web_smoke/$(date +%Y%m%d_%H%M%S)}"
TMP_ROOT="${WEB_SMOKE_TMPDIR:-${ROOT}/tmp/web_smoke_tmp}"
PYTHON="${PYTHON:-}"
SERVER_PID=""
STARTED_SERVER=0

if [ -z "$PYTHON" ]; then
  if [ -x "$ROOT/.venv/bin/python" ]; then
    PYTHON="$ROOT/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
  else
    PYTHON="python"
  fi
fi

mkdir -p "$OUTPUT_ROOT" "$TMP_ROOT"
export TMPDIR="$TMP_ROOT"

cleanup() {
  if [ "$STARTED_SERVER" = "1" ] && [ "$KEEP_SERVER" != "1" ] && [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

http_ok() {
  curl -fsS "$BASE_URL/" >/dev/null 2>&1
}

wait_for_server() {
  local deadline
  deadline=$((SECONDS + 60))
  until http_ok; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "Server did not become ready at $BASE_URL" >&2
      if [ -f "$OUTPUT_ROOT/server.log" ]; then
        echo "---- server.log ----" >&2
        tail -80 "$OUTPUT_ROOT/server.log" >&2 || true
      fi
      return 1
    fi
    sleep 1
  done
}

echo "Web smoke"
echo "  root: $ROOT"
echo "  base_url: $BASE_URL"
echo "  python: $PYTHON"
echo "  output_root: $OUTPUT_ROOT"

if [ "$RUN_BUILD" = "1" ]; then
  echo ""
  echo "[1/3] Building frontend"
  (cd "$ROOT" && make build)
else
  echo ""
  echo "[1/3] Skipping frontend build"
fi

if http_ok; then
  echo ""
  echo "[2/3] Reusing running server at $BASE_URL"
else
  echo ""
  echo "[2/3] Starting local backend"
  (
    cd "$ROOT"
    PYTHONPATH=backend "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
  ) >"$OUTPUT_ROOT/server.log" 2>&1 &
  SERVER_PID="$!"
  STARTED_SERVER=1
  wait_for_server
fi

echo ""
echo "[3/3] Running Web API smoke"
WEB_SMOKE_BASE_URL="$BASE_URL" \
WEB_SMOKE_OUTPUT_ROOT="$OUTPUT_ROOT" \
  "$PYTHON" "$ROOT/scripts/web_smoke.py"
