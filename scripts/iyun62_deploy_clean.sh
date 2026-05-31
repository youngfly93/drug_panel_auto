#!/usr/bin/env bash
# Deploy reportgen-web to iyun62 using a clean release checkout.
#
# Run this from a clean repository root on a local machine that has Node/npm and
# SSH access to the iyun-server host alias. The deployed release is built from
# DEPLOY_REF, not from the mutable working tree.

set -euo pipefail

SSH_HOST="${SSH_HOST:-iyun-server}"
APP_ROOT="${APP_ROOT:-/media/desk16/iyun6208/apps}"
LEGACY_APP_DIR="${LEGACY_APP_DIR:-$APP_ROOT/reportgen-web}"
RELEASES_DIR="${RELEASES_DIR:-$APP_ROOT/reportgen-web-releases}"
RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
STORAGE_DIR="${STORAGE_DIR:-$LEGACY_APP_DIR/storage}"
VENV_DIR="${VENV_DIR:-$LEGACY_APP_DIR/.venv}"
DEPLOY_REF="${DEPLOY_REF:-$(git rev-parse HEAD)}"
PORT="${PORT:-8000}"

if [ ! -f "frontend/package.json" ] || [ ! -f "scripts/iyun62_start_reportgen.sh" ]; then
    echo "Run this script from the reportgen-web repository root." >&2
    exit 1
fi

short_ref="$(git rev-parse --short "$DEPLOY_REF")"
release_dir="$RELEASES_DIR/$short_ref"
tmp_dir="$(mktemp -d)"
cleanup() {
    rm -rf "$tmp_dir"
}
trap cleanup EXIT

echo "== Local checks =="
git rev-parse --verify "$DEPLOY_REF" >/dev/null
git diff --check
if [ -n "$(git status --porcelain)" ]; then
    echo "Working tree is dirty; commit or stash before production deploy." >&2
    git status --short
    exit 1
fi

git archive "$DEPLOY_REF" | tar -x -C "$tmp_dir"
python -m py_compile \
    "$tmp_dir/backend/app/api/ops.py" \
    "$tmp_dir/backend/app/services/generation_process.py" \
    "$tmp_dir/backend/app/services/task_recovery.py" \
    "$tmp_dir/reportgen/core/report_summary.py" \
    "$tmp_dir/reportgen/core/report_generator.py" \
    "$tmp_dir/backend/app/services/reportgen_bridge.py"
(cd "$tmp_dir/frontend" && npm install --no-audit --no-fund && npm run build)
rm -rf "$tmp_dir/backend/static"
mkdir -p "$tmp_dir/backend/static"
cp -R "$tmp_dir/frontend/dist/." "$tmp_dir/backend/static/"
rm -rf "$tmp_dir/frontend/node_modules"
find "$tmp_dir" -name ".DS_Store" -delete
xattr -cr "$tmp_dir" 2>/dev/null || true

# Keep a quick compile check for the currently checked-out scripts too.
python -m py_compile \
    backend/app/api/ops.py \
    backend/app/services/generation_process.py \
    backend/app/services/task_recovery.py \
    reportgen/core/report_summary.py \
    reportgen/core/report_generator.py \
    backend/app/services/reportgen_bridge.py

echo "== Prepare remote release $short_ref =="
ssh "$SSH_HOST" "set -euo pipefail
mkdir -p '$RELEASES_DIR' '$RUNTIME_DIR' '$release_dir.tmp'
rm -rf '$release_dir.tmp'
mkdir -p '$release_dir.tmp'
test -x '$VENV_DIR/bin/python'
test -x '$VENV_DIR/bin/uvicorn'
"

COPYFILE_DISABLE=1 tar --format ustar -C "$tmp_dir" -cf - . | ssh "$SSH_HOST" "set -euo pipefail
tar -xf - -C '$release_dir.tmp'
printf '%s\n' '$DEPLOY_REF' > '$release_dir.tmp/REVISION'
rm -rf '$release_dir'
mv '$release_dir.tmp' '$release_dir'
"

echo "== Upload runtime start script =="
rsync -az scripts/iyun62_start_reportgen.sh "$SSH_HOST:$RUNTIME_DIR/start_reportgen.sh"
if [ -f scripts/iyun62_watchdog.sh ]; then
    rsync -az scripts/iyun62_watchdog.sh "$SSH_HOST:$RUNTIME_DIR/watchdog.sh"
fi
if [ -f scripts/iyun62_backup.sh ]; then
    rsync -az scripts/iyun62_backup.sh "$SSH_HOST:$RUNTIME_DIR/backup.sh"
fi
ssh "$SSH_HOST" "chmod +x '$RUNTIME_DIR/start_reportgen.sh' '$RUNTIME_DIR/watchdog.sh' 2>/dev/null || chmod +x '$RUNTIME_DIR/start_reportgen.sh'"
ssh "$SSH_HOST" "chmod +x '$RUNTIME_DIR/backup.sh' 2>/dev/null || true"

echo "== Start remote service =="
ssh "$SSH_HOST" "RELEASE_DIR='$release_dir' STORAGE_DIR='$STORAGE_DIR' VENV_DIR='$VENV_DIR' RUNTIME_DIR='$RUNTIME_DIR' PORT='$PORT' bash '$RUNTIME_DIR/start_reportgen.sh'"

echo "== Public smoke =="
curl -s -o /dev/null -w "https://panel.mailuo-report.com.cn/api/v1/tasks/stats HTTP %{http_code}\n" \
    https://panel.mailuo-report.com.cn/api/v1/tasks/stats

echo "deployed_ref=$DEPLOY_REF"
echo "release_dir=$release_dir"
