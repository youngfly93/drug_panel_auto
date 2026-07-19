#!/usr/bin/env bash
# Install reviewed backup and monthly restore-drill jobs on iyun129.

set -euo pipefail

export SSH_HOST="${SSH_HOST:-iyun129}"
export APP_ROOT="${APP_ROOT:-/media/desk16/iy12922/apps}"
export LEGACY_APP_DIR="${LEGACY_APP_DIR:-$APP_ROOT/reportgen-web-prod}"
export RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
export STORAGE_DIR="${STORAGE_DIR:-$APP_ROOT/reportgen-web-storage}"
export RELEASES_DIR="${RELEASES_DIR:-$APP_ROOT/reportgen-web-releases}"
export BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/reportgen-web-backups}"

exec bash scripts/iyun62_install_maintenance.sh "$@"
