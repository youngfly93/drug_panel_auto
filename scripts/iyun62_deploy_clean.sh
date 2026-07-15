#!/usr/bin/env bash
# Deploy reportgen-web using an immutable clean release checkout.
#
# Run this from a clean repository root on a local machine that has Node/npm and
# SSH access to the configured host alias. The deployed release is built from
# DEPLOY_REF, not from the mutable working tree. The historical filename is kept
# for compatibility; use the iyun129 wrapper for the current production target.

set -euo pipefail

SSH_HOST="${SSH_HOST:-iyun-server}"
APP_ROOT="${APP_ROOT:-/media/desk16/iyun6208/apps}"
LEGACY_APP_DIR="${LEGACY_APP_DIR:-$APP_ROOT/reportgen-web}"
RELEASES_DIR="${RELEASES_DIR:-$APP_ROOT/reportgen-web-releases}"
RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
STORAGE_DIR="${STORAGE_DIR:-$LEGACY_APP_DIR/storage}"
VENV_DIR="${VENV_DIR:-$LEGACY_APP_DIR/.venv}"
BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/reportgen-web-backups}"
DEPLOY_REF="${DEPLOY_REF:-$(git rev-parse HEAD)}"
PORT="${PORT:-8000}"
LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://127.0.0.1:$PORT/api/v1/healthz}"
PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-https://panel.mailuo-report.com.cn/api/v1/healthz}"
TUNNEL_METRICS_URL="${TUNNEL_METRICS_URL:-http://127.0.0.1:20242/metrics}"
MANAGE_TUNNEL="${MANAGE_TUNNEL:-1}"
RUN_PREFLIGHT="${RUN_PREFLIGHT:-1}"
UPLOAD_MAINTENANCE_SCRIPTS="${UPLOAD_MAINTENANCE_SCRIPTS:-1}"
UPLOAD_ALERTS_SCRIPT="${UPLOAD_ALERTS_SCRIPT:-0}"
UPLOAD_CLOUDFLARED_SCRIPTS="${UPLOAD_CLOUDFLARED_SCRIPTS:-0}"
SYNC_SIGNATURE_ASSETS="${SYNC_SIGNATURE_ASSETS:-0}"
SIGNATURE_ASSET_DIR="${SIGNATURE_ASSET_DIR:-storage/signatures}"

if [ ! -f "frontend/package.json" ] || \
        [ ! -f "scripts/iyun62_start_reportgen.sh" ] || \
        [ ! -f "scripts/iyun62_watchdog.sh" ]; then
    echo "Run this script from the reportgen-web repository root." >&2
    exit 1
fi
if [ "$UPLOAD_CLOUDFLARED_SCRIPTS" = "1" ] && \
        { [ ! -f scripts/iyun129_start_cloudflared.sh ] || \
          [ ! -f scripts/iyun129_watchdog_cloudflared.sh ]; }; then
    echo "iyun129 cloudflared runtime scripts are missing." >&2
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

resolved_ref="$(git rev-parse "$DEPLOY_REF")"
if [ "$RUN_PREFLIGHT" = "1" ]; then
    if [ "$resolved_ref" != "$(git rev-parse HEAD)" ]; then
        echo "RUN_PREFLIGHT=1 requires DEPLOY_REF to equal local HEAD." >&2
        echo "Use the dedicated release-switch command for an existing rollback release." >&2
        exit 1
    fi
    make release-check
fi
if [ "$SYNC_SIGNATURE_ASSETS" = "1" ]; then
    test -d "$SIGNATURE_ASSET_DIR"
    RG_WEB_STORAGE_ROOT="$(cd "$(dirname "$SIGNATURE_ASSET_DIR")" && pwd)" \
        python scripts/check_signature_registry.py \
        --config-dir config \
        --storage-root "$(cd "$(dirname "$SIGNATURE_ASSET_DIR")" && pwd)"
fi

git archive "$DEPLOY_REF" | tar -x -C "$tmp_dir"
python -m py_compile \
    "$tmp_dir/backend/app/api/health.py" \
    "$tmp_dir/backend/app/api/router.py" \
    "$tmp_dir/backend/app/dependencies.py" \
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
    backend/app/api/health.py \
    backend/app/api/router.py \
    backend/app/dependencies.py \
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
printf '%s\n' '$resolved_ref' > '$release_dir.tmp/REVISION'
rm -rf '$release_dir'
mv '$release_dir.tmp' '$release_dir'
"

if [ "$SYNC_SIGNATURE_ASSETS" = "1" ]; then
    echo "== Sync external signature assets =="
    ssh "$SSH_HOST" "mkdir -p '$STORAGE_DIR/signatures'"
    rsync -az "$SIGNATURE_ASSET_DIR/" "$SSH_HOST:$STORAGE_DIR/signatures/"
    ssh "$SSH_HOST" "set -euo pipefail
RG_WEB_STORAGE_ROOT='$STORAGE_DIR' '$VENV_DIR/bin/python' \
  '$release_dir/scripts/check_signature_registry.py' \
  --config-dir '$release_dir/config' \
  --storage-root '$STORAGE_DIR'
"
fi

echo "== Upload runtime start script =="
rsync -az scripts/iyun62_start_reportgen.sh "$SSH_HOST:$RUNTIME_DIR/start_reportgen.sh.next"
rsync -az scripts/iyun62_watchdog.sh "$SSH_HOST:$RUNTIME_DIR/watchdog.sh.next"
runtime_config="$tmp_dir/deployment.env.runtime"
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
    printf 'PUBLIC_HEALTH_URL=%q\n' "$PUBLIC_HEALTH_URL"
    printf 'TUNNEL_METRICS_URL=%q\n' "$TUNNEL_METRICS_URL"
    printf 'MANAGE_TUNNEL=%q\n' "$MANAGE_TUNNEL"
    printf 'RG_WEB_RUNTIME_INSTANCE_LOCK_ENABLED=1\n'
    printf 'RG_WEB_DOCS_ENABLED=%q\n' "${RG_WEB_DOCS_ENABLED:-0}"
    printf 'RG_WEB_CORS_ORIGINS=%q\n' "${RG_WEB_CORS_ORIGINS:-https://panel.mailuo-report.com.cn}"
} > "$runtime_config"
rsync -az "$runtime_config" "$SSH_HOST:$RUNTIME_DIR/deployment.env.next"
ssh "$SSH_HOST" "set -euo pipefail
chmod 700 '$RUNTIME_DIR/start_reportgen.sh.next' '$RUNTIME_DIR/watchdog.sh.next'
chmod 600 '$RUNTIME_DIR/deployment.env.next'
mv -f '$RUNTIME_DIR/deployment.env.next' '$RUNTIME_DIR/deployment.env'
mv -f '$RUNTIME_DIR/start_reportgen.sh.next' '$RUNTIME_DIR/start_reportgen.sh'
mv -f '$RUNTIME_DIR/watchdog.sh.next' '$RUNTIME_DIR/watchdog.sh'
"

if [ "$UPLOAD_MAINTENANCE_SCRIPTS" = "1" ]; then
    if [ -f scripts/iyun62_backup.sh ]; then
        rsync -az scripts/iyun62_backup.sh "$SSH_HOST:$RUNTIME_DIR/backup.sh"
    fi
    if [ -f scripts/iyun62_alerts.sh ]; then
        rsync -az scripts/iyun62_alerts.sh "$SSH_HOST:$RUNTIME_DIR/alerts.sh"
    fi
    if [ -f scripts/iyun62_restore_drill.sh ]; then
        rsync -az scripts/iyun62_restore_drill.sh "$SSH_HOST:$RUNTIME_DIR/restore_drill.sh"
    fi
fi
if [ "$UPLOAD_ALERTS_SCRIPT" = "1" ]; then
    rsync -az scripts/iyun62_alerts.sh "$SSH_HOST:$RUNTIME_DIR/alerts.sh.next"
    ssh "$SSH_HOST" "set -euo pipefail
chmod 700 '$RUNTIME_DIR/alerts.sh.next'
mv -f '$RUNTIME_DIR/alerts.sh.next' '$RUNTIME_DIR/alerts.sh'
"
fi
if [ "$UPLOAD_CLOUDFLARED_SCRIPTS" = "1" ]; then
    rsync -az scripts/iyun129_start_cloudflared.sh \
        "$SSH_HOST:$RUNTIME_DIR/start_panel_cloudflared.sh.next"
    rsync -az scripts/iyun129_watchdog_cloudflared.sh \
        "$SSH_HOST:$RUNTIME_DIR/watchdog_panel_cloudflared.sh.next"
    ssh "$SSH_HOST" "set -euo pipefail
chmod 700 '$RUNTIME_DIR/start_panel_cloudflared.sh.next' \
  '$RUNTIME_DIR/watchdog_panel_cloudflared.sh.next'
mv -f '$RUNTIME_DIR/start_panel_cloudflared.sh.next' \
  '$RUNTIME_DIR/start_panel_cloudflared.sh'
mv -f '$RUNTIME_DIR/watchdog_panel_cloudflared.sh.next' \
  '$RUNTIME_DIR/watchdog_panel_cloudflared.sh'
"
fi
ssh "$SSH_HOST" "chmod +x '$RUNTIME_DIR/backup.sh' 2>/dev/null || true"
ssh "$SSH_HOST" "chmod +x '$RUNTIME_DIR/alerts.sh' 2>/dev/null || true"
ssh "$SSH_HOST" "chmod +x '$RUNTIME_DIR/restore_drill.sh' 2>/dev/null || true"

echo "== Start remote service =="
ssh "$SSH_HOST" "RELEASE_DIR='$release_dir' bash '$RUNTIME_DIR/start_reportgen.sh'"

echo "== Verify release identity =="
ssh "$SSH_HOST" "set -euo pipefail
current=\$(head -n 1 '$RUNTIME_DIR/current_release')
test \"\$current\" = '$release_dir'
test \"\$(head -n 1 \"\$current/REVISION\")\" = '$resolved_ref'
pid=\$(cat '$RUNTIME_DIR/reportgen-web.pid')
test \"\$(readlink \"/proc/\$pid/cwd\")\" = '$release_dir'
curl -fsS -o /dev/null --max-time 8 '$LOCAL_HEALTH_URL'
printf 'current_release=%s\\nrevision=%s\\npid=%s\\nprocess_cwd=%s\\n' \
  \"\$current\" \"\$(head -n 1 \"\$current/REVISION\")\" \"\$pid\" \"\$(readlink \"/proc/\$pid/cwd\")\"
"

echo "== Public smoke =="
curl -fsS -o /dev/null -w "$PUBLIC_HEALTH_URL HTTP %{http_code}\n" "$PUBLIC_HEALTH_URL"

if [ "$UPLOAD_CLOUDFLARED_SCRIPTS" = "1" ]; then
    echo "== Restart Cloudflare connector with reviewed runtime =="
    ssh "$SSH_HOST" "bash '$RUNTIME_DIR/start_panel_cloudflared.sh'"
    curl -fsS -o /dev/null -w "$PUBLIC_HEALTH_URL HTTP %{http_code}\n" "$PUBLIC_HEALTH_URL"
fi

echo "deployed_ref=$resolved_ref"
echo "release_dir=$release_dir"
