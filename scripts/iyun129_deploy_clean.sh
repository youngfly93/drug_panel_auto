#!/usr/bin/env bash
# Deploy an exact Git commit to the iyun129 production release layout.

set -euo pipefail

if [ ! -f "scripts/iyun62_deploy_clean.sh" ]; then
    echo "Run this script from the reportgen-web repository root." >&2
    exit 1
fi

export SSH_HOST="${SSH_HOST:-iyun129}"
export APP_ROOT="${APP_ROOT:-/media/desk16/iy12922/apps}"
export LEGACY_APP_DIR="${LEGACY_APP_DIR:-$APP_ROOT/reportgen-web-prod}"
export RELEASES_DIR="${RELEASES_DIR:-$APP_ROOT/reportgen-web-releases}"
export RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
export STORAGE_DIR="${STORAGE_DIR:-$APP_ROOT/reportgen-web-storage}"
export VENV_DIR="${VENV_DIR:-$APP_ROOT/reportgen-web-venv}"
export BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/reportgen-web-backups}"
export DEPLOY_REF="${DEPLOY_REF:-$(git rev-parse HEAD)}"
export PORT="${PORT:-18082}"
export LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://127.0.0.1:$PORT/api/v1/healthz}"
export PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-https://panel.mailuo-report.com.cn/api/v1/healthz}"
export TUNNEL_METRICS_URL="${TUNNEL_METRICS_URL:-http://127.0.0.1:20242/metrics}"
export HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-180}"
export RG_WEB_DOCS_ENABLED="${RG_WEB_DOCS_ENABLED:-0}"
export RG_WEB_CORS_ORIGINS="${RG_WEB_CORS_ORIGINS:-https://panel.mailuo-report.com.cn}"
# Lung329 and lung588 expose single-case and case-isolated batch pilot drafts;
# batch PD-L1 fields remain blank/not-provided and formal clinical promotion is
# separate. CRC301, methylation and unbuilt small panels remain outside this
# release. The same scope is enforced in the Web API, reportgen core, and UI.
export RG_WEB_DISABLED_PROJECT_TYPES="${RG_WEB_DISABLED_PROJECT_TYPES:-crc_301_msi,lung_methylation,lung_13,lung_62,lung_62_pdl1,lung_588}"
export REPORTGEN_DISABLED_PROJECT_TYPES="${REPORTGEN_DISABLED_PROJECT_TYPES:-$RG_WEB_DISABLED_PROJECT_TYPES}"
export VITE_DISABLED_PROJECT_TYPES="${VITE_DISABLED_PROJECT_TYPES:-$RG_WEB_DISABLED_PROJECT_TYPES}"
export ORIGIN_REMOTE="${ORIGIN_REMOTE:-origin}"
export ORIGIN_MAIN_REF="${ORIGIN_MAIN_REF:-$ORIGIN_REMOTE/main}"
export REQUIRE_ORIGIN_MAIN_REACHABILITY="${REQUIRE_ORIGIN_MAIN_REACHABILITY:-1}"

# A panel whose committed readiness manifest is BLOCKED must remain disabled in
# the Web API, reportgen core, and compiled frontend. This runs before the first
# production-side mutation, so an environment override cannot silently expose
# the synthetic-only methylation package.
python3 scripts/check_production_panel_scope.py \
    --target iyun129 \
    --web-disabled "$RG_WEB_DISABLED_PROJECT_TYPES" \
    --core-disabled "$REPORTGEN_DISABLED_PROJECT_TYPES" \
    --frontend-disabled "$VITE_DISABLED_PROJECT_TYPES"

# iyun129 has a dedicated cloudflared watchdog; the Web watchdog must not race
# it by trying to manage the same tunnel.
export MANAGE_TUNNEL="${MANAGE_TUNNEL:-0}"

# iyun129 maintenance scripts have their own reviewed installation lifecycle.
# A Web release must not silently replace them with scripts carrying iyun62
# defaults.
export UPLOAD_MAINTENANCE_SCRIPTS="${UPLOAD_MAINTENANCE_SCRIPTS:-0}"
export UPLOAD_ALERTS_SCRIPT="${UPLOAD_ALERTS_SCRIPT:-1}"
export UPLOAD_CLOUDFLARED_SCRIPTS="${UPLOAD_CLOUDFLARED_SCRIPTS:-1}"

# Signature images are runtime assets and remain outside immutable Git
# releases. Sync without --delete, then verify all production-required roles.
export SYNC_SIGNATURE_ASSETS="${SYNC_SIGNATURE_ASSETS:-1}"
export SIGNATURE_ASSET_DIR="${SIGNATURE_ASSET_DIR:-storage/signatures}"

# Production releases are blocked unless a revision-pinned external historical
# golden manifest was generated from the candidate being deployed.
export REQUIRE_HISTORICAL_GOLDEN="${REQUIRE_HISTORICAL_GOLDEN:-1}"
export HISTORICAL_GOLDEN_MANIFEST="${HISTORICAL_GOLDEN_MANIFEST:-$PWD/.work/historical_golden_release_manifest.yaml}"

# Reject locally before making even a backup-side mutation on production.
if [ -n "$(git status --porcelain)" ]; then
    echo "Working tree is dirty; freeze the candidate before iyun129 deployment." >&2
    git status --short
    exit 1
fi
resolved_ref="$(git rev-parse "$DEPLOY_REF")"
if [ "$REQUIRE_ORIGIN_MAIN_REACHABILITY" = "1" ]; then
    git fetch --prune "$ORIGIN_REMOTE" main
    git rev-parse --verify "$ORIGIN_MAIN_REF" >/dev/null
    if ! git merge-base --is-ancestor "$resolved_ref" "$ORIGIN_MAIN_REF"; then
        echo "Deployment candidate is not reachable from $ORIGIN_MAIN_REF: $resolved_ref" >&2
        echo "Merge and push the reviewed candidate to origin/main before production deployment." >&2
        exit 1
    fi
fi
if [ "$REQUIRE_HISTORICAL_GOLDEN" = "1" ] && \
        [ ! -f "$HISTORICAL_GOLDEN_MANIFEST" ]; then
    echo "Historical golden manifest is missing: $HISTORICAL_GOLDEN_MANIFEST" >&2
    exit 1
fi

# A clinical production switch must have a verified restore point. Run the
# committed backup implementation directly on the remote host so iyun129 does
# not depend on a potentially stale installed maintenance-script copy.
export RUN_REMOTE_BACKUP="${RUN_REMOTE_BACKUP:-1}"
if [ "$RUN_REMOTE_BACKUP" = "1" ]; then
    backup_output="$(ssh "$SSH_HOST" "set -euo pipefail
APP_ROOT='$APP_ROOT' \
LEGACY_APP_DIR='$LEGACY_APP_DIR' \
RELEASES_DIR='$RELEASES_DIR' \
RUNTIME_DIR='$RUNTIME_DIR' \
STORAGE_DIR='$STORAGE_DIR' \
BACKUP_DIR='$BACKUP_DIR' \
bash -s -- backup
" < scripts/iyun62_backup.sh)"
    printf '%s\n' "$backup_output"
    backup_archive="${backup_output##*$'\n'}"
    case "$backup_archive" in
        "$BACKUP_DIR"/reportgen-web-backup-*.tar.gz) ;;
        *)
            echo "Remote backup did not return a verified archive path." >&2
            exit 1
            ;;
    esac
    ssh "$SSH_HOST" "set -euo pipefail
test -f '$backup_archive'
test -f '$backup_archive.sha256'
test -f '$backup_archive.manifest.json'
"
fi

exec bash scripts/iyun62_deploy_clean.sh "$@"
