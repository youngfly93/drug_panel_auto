#!/usr/bin/env bash
# User-level backup and cleanup for iyun62 reportgen-web production.
#
# This script is intended to run on iyun62 as the iyun6208 user. It keeps real
# production data on the server only; do not copy backup archives into Git.

set -euo pipefail

APP_ROOT="${APP_ROOT:-/media/desk16/iyun6208/apps}"
LEGACY_APP_DIR="${LEGACY_APP_DIR:-$APP_ROOT/reportgen-web}"
RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
STORAGE_DIR="${STORAGE_DIR:-$LEGACY_APP_DIR/storage}"
RELEASES_DIR="${RELEASES_DIR:-$APP_ROOT/reportgen-web-releases}"
BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/reportgen-web-backups}"
CURRENT_RELEASE_FILE="${CURRENT_RELEASE_FILE:-$RUNTIME_DIR/current_release}"

BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
RELEASE_KEEP_COUNT="${RELEASE_KEEP_COUNT:-8}"
PREVIEW_KEEP_DAYS="${PREVIEW_KEEP_DAYS:-7}"
LOG_KEEP_DAYS="${LOG_KEEP_DAYS:-14}"
UPLOAD_KEEP_DAYS="${UPLOAD_KEEP_DAYS:-30}"
REPORT_KEEP_DAYS="${REPORT_KEEP_DAYS:-180}"
ZIP_KEEP_DAYS="${ZIP_KEEP_DAYS:-14}"
AUDIT_LOG_KEEP_DAYS="${AUDIT_LOG_KEEP_DAYS:-365}"
MODE="${MODE:-all}"
DRY_RUN="${DRY_RUN:-0}"

LOG_DIR="$RUNTIME_DIR/logs"
LOG_FILE="$LOG_DIR/maintenance.log"
LOCK_DIR="$RUNTIME_DIR/maintenance.lock"

usage() {
    cat <<'EOF'
Usage:
  iyun62_backup.sh [all|backup|cleanup|verify] [options]

Modes:
  all       Run backup, verify, then cleanup. Default.
  backup    Create one backup archive and verify it.
  cleanup   Remove old backups, old releases, stale previews, and rotated logs.
  verify    Verify an existing backup archive.

Options:
  --archive PATH       Backup archive to verify.
  --dry-run            Print cleanup actions without deleting.
  -h, --help           Show this help.

Environment overrides:
  APP_ROOT, LEGACY_APP_DIR, RUNTIME_DIR, STORAGE_DIR, RELEASES_DIR, BACKUP_DIR
  BACKUP_KEEP_DAYS=30, RELEASE_KEEP_COUNT=8, PREVIEW_KEEP_DAYS=7, LOG_KEEP_DAYS=14
  UPLOAD_KEEP_DAYS=30, REPORT_KEEP_DAYS=180, ZIP_KEEP_DAYS=14, AUDIT_LOG_KEEP_DAYS=365
EOF
}

VERIFY_ARCHIVE=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        all|backup|cleanup|verify)
            MODE="$1"
            shift
            ;;
        --archive)
            VERIFY_ARCHIVE="${2:?--archive requires a value}"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

mkdir -p "$LOG_DIR" "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR" 2>/dev/null || true

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

run_rm_rf() {
    local path="$1"
    if [ "$DRY_RUN" = "1" ]; then
        log "dry_run rm -rf $path"
    else
        rm -rf -- "$path"
        log "removed $path"
    fi
}

hash_file() {
    local path="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$path" | awk '{print $1}'
    else
        shasum -a 256 "$path" | awk '{print $1}'
    fi
}

with_lock() {
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        local old_pid
        old_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
        if [ -n "${old_pid:-}" ] && ! kill -0 "$old_pid" 2>/dev/null; then
            log "removing stale maintenance lock pid=$old_pid"
            rm -rf "$LOCK_DIR"
            mkdir "$LOCK_DIR"
        else
            if [ -z "${old_pid:-}" ]; then
                log "maintenance already running; lock=$LOCK_DIR"
            else
                log "maintenance already running; lock=$LOCK_DIR pid=$old_pid"
            fi
            exit 0
        fi
    fi
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    trap 'rm -rf "$LOCK_DIR" 2>/dev/null || true' EXIT
}

read_current_release() {
    if [ -f "$CURRENT_RELEASE_FILE" ]; then
        read -r release < "$CURRENT_RELEASE_FILE" || true
        if [ -n "${release:-}" ]; then
            realpath "$release" 2>/dev/null || printf '%s\n' "$release"
        fi
    fi
}

write_pre_manifest() {
    local staging="$1"
    local timestamp="$2"
    local current_release="$3"
    local db_copy="$4"
    RUNTIME_DIR="$RUNTIME_DIR" \
        STORAGE_DIR="$STORAGE_DIR" \
        RELEASES_DIR="$RELEASES_DIR" \
        BACKUP_DIR="$BACKUP_DIR" \
        APP_ROOT="$APP_ROOT" \
        STAGING_DIR="$staging" \
        CREATED_AT="$timestamp" \
        CURRENT_RELEASE="$current_release" \
        DB_COPY="$db_copy" \
        python3 - <<'PY'
from __future__ import annotations

import json
import os
import platform
from pathlib import Path


def tree_stats(path: Path) -> dict:
    files = 0
    dirs = 0
    bytes_total = 0
    if not path.exists():
        return {"exists": False, "files": 0, "dirs": 0, "bytes": 0}
    if path.is_file():
        return {"exists": True, "files": 1, "dirs": 0, "bytes": path.stat().st_size}
    for root, dirnames, filenames in os.walk(path):
        dirs += len(dirnames)
        for filename in filenames:
            candidate = Path(root) / filename
            try:
                st = candidate.stat()
            except OSError:
                continue
            files += 1
            bytes_total += st.st_size
    return {"exists": True, "files": files, "dirs": dirs, "bytes": bytes_total}


staging = Path(os.environ["STAGING_DIR"])
storage = Path(os.environ["STORAGE_DIR"])
runtime = Path(os.environ["RUNTIME_DIR"])
release = os.environ.get("CURRENT_RELEASE") or None
revision = None
if release:
    try:
        revision = (Path(release) / "REVISION").read_text(encoding="utf-8").strip()
    except OSError:
        revision = None

included = [
    "db",
    "uploads",
    "reports",
    "signatures",
    "reference_reports",
    "patient_info.yaml",
]
manifest = {
    "schema_version": "1.0",
    "created_at": os.environ["CREATED_AT"],
    "hostname": platform.node(),
    "app_root": os.environ.get("APP_ROOT"),
    "storage_root": str(storage),
    "runtime_root": str(runtime),
    "current_release": release,
    "revision": revision,
    "included_storage_roots": included,
    "storage_stats": {name: tree_stats(storage / name) for name in included},
    "db_backup": tree_stats(Path(os.environ["DB_COPY"])),
}
(staging / "meta" / "manifest.pre.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
PY
}

backup_sqlite() {
    local source_db="$STORAGE_DIR/db/reportgen_web.sqlite"
    local dest_db="$1"
    mkdir -p "$(dirname "$dest_db")"
    SOURCE_DB="$source_db" DEST_DB="$dest_db" STAGING_DIR="$(dirname "$(dirname "$dest_db")")" python3 - <<'PY'
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

source = Path(os.environ["SOURCE_DB"])
dest = Path(os.environ["DEST_DB"])
staging = Path(os.environ["STAGING_DIR"])
result = {
    "source_exists": source.exists(),
    "source": str(source),
    "destination": str(dest),
    "status": "SKIPPED",
    "integrity_check": None,
    "duration_seconds": None,
}
started = time.monotonic()
if source.exists():
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
        integrity = dst.execute("PRAGMA integrity_check").fetchone()
        result["integrity_check"] = integrity[0] if integrity else None
        result["status"] = "PASS" if result["integrity_check"] == "ok" else "FAIL"
    finally:
        dst.close()
        src.close()
result["duration_seconds"] = round(time.monotonic() - started, 3)
(staging / "meta" / "db_integrity.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
if result["status"] == "FAIL":
    raise SystemExit("SQLite integrity_check failed")
PY
}

create_backup() {
    local timestamp archive tmp_archive sidecar sha current_release staging db_copy
    timestamp="$(date '+%Y%m%d_%H%M%S')"
    archive="$BACKUP_DIR/reportgen-web-backup-$timestamp.tar.gz"
    tmp_archive="$archive.tmp"
    sidecar="$archive.manifest.json"
    staging="$BACKUP_DIR/.staging/$timestamp"
    db_copy="$staging/db/reportgen_web.sqlite"
    current_release="$(read_current_release || true)"

    log "backup begin archive=$archive"
    mkdir -p "$staging/meta" "$staging/db"
    chmod 700 "$staging" 2>/dev/null || true

    backup_sqlite "$db_copy"
    crontab -l > "$staging/meta/crontab.txt" 2>/dev/null || true
    df -P "$STORAGE_DIR" > "$staging/meta/df_storage.txt" 2>/dev/null || true
    {
        printf 'current_release=%s\n' "${current_release:-}"
        if [ -n "${current_release:-}" ] && [ -f "$current_release/REVISION" ]; then
            printf 'revision='
            cat "$current_release/REVISION"
            printf '\n'
        fi
    } > "$staging/meta/release.txt"
    write_pre_manifest "$staging" "$timestamp" "${current_release:-}" "$db_copy"

    local tar_args=()
    tar_args+=(-C "$staging" meta)
    if [ -f "$db_copy" ]; then
        tar_args+=(-C "$staging" db/reportgen_web.sqlite)
    fi
    for name in uploads reports signatures reference_reports patient_info.yaml; do
        if [ -e "$STORAGE_DIR/$name" ]; then
            tar_args+=(-C "$STORAGE_DIR" "$name")
        fi
    done

    tar -czf "$tmp_archive" "${tar_args[@]}"
    tar -tzf "$tmp_archive" >/dev/null
    mv "$tmp_archive" "$archive"
    sha="$(hash_file "$archive")"
    printf '%s  %s\n' "$sha" "$(basename "$archive")" > "$archive.sha256"

    ARCHIVE="$archive" SHA256="$sha" SIDECAR="$sidecar" STAGING_DIR="$staging" python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

archive = Path(os.environ["ARCHIVE"])
staging = Path(os.environ["STAGING_DIR"])
payload = json.loads((staging / "meta" / "manifest.pre.json").read_text(encoding="utf-8"))
payload["archive"] = {
    "path": str(archive),
    "filename": archive.name,
    "bytes": archive.stat().st_size,
    "sha256": os.environ["SHA256"],
}
Path(os.environ["SIDECAR"]).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
PY

    verify_backup "$archive"
    rm -rf "$staging"
    log "backup complete archive=$archive"
    printf '%s\n' "$archive"
}

verify_backup() {
    local archive="$1"
    if [ -z "$archive" ]; then
        echo "verify requires --archive PATH or a backup archive argument" >&2
        exit 2
    fi
    if [ ! -f "$archive" ]; then
        echo "Backup archive not found: $archive" >&2
        exit 1
    fi
    log "verify begin archive=$archive"
    tar -tzf "$archive" >/dev/null

    if [ -f "$archive.sha256" ]; then
        local expected actual
        expected="$(awk '{print $1}' "$archive.sha256")"
        actual="$(hash_file "$archive")"
        if [ "$expected" != "$actual" ]; then
            echo "Checksum mismatch for $archive" >&2
            exit 1
        fi
    fi

    local tmp_dir
    tmp_dir="$(mktemp -d)"
    tar -xzf "$archive" -C "$tmp_dir" db/reportgen_web.sqlite 2>/dev/null || true
    if [ -f "$tmp_dir/db/reportgen_web.sqlite" ]; then
        DB_PATH="$tmp_dir/db/reportgen_web.sqlite" python3 - <<'PY'
from __future__ import annotations

import os
import sqlite3

db = sqlite3.connect(os.environ["DB_PATH"])
try:
    result = db.execute("PRAGMA integrity_check").fetchone()
finally:
    db.close()
if not result or result[0] != "ok":
    raise SystemExit("Extracted backup SQLite integrity_check failed")
PY
    fi
    rm -rf "$tmp_dir"
    log "verify complete archive=$archive"
}

cleanup_backups() {
    log "cleanup backups begin keep_days=$BACKUP_KEEP_DAYS"
    find "$BACKUP_DIR" -maxdepth 1 -type f -name 'reportgen-web-backup-*.tar.gz' \
        -mtime +"$BACKUP_KEEP_DAYS" -print | while IFS= read -r archive; do
            run_rm_rf "$archive"
            [ -e "$archive.sha256" ] && run_rm_rf "$archive.sha256"
            [ -e "$archive.manifest.json" ] && run_rm_rf "$archive.manifest.json"
        done
    if [ -d "$BACKUP_DIR/.staging" ]; then
        find "$BACKUP_DIR/.staging" -mindepth 1 -maxdepth 1 -type d -mtime +1 -print \
            | while IFS= read -r path; do
                run_rm_rf "$path"
            done
    fi
}

cleanup_releases() {
    log "cleanup releases begin keep_count=$RELEASE_KEEP_COUNT"
    [ -d "$RELEASES_DIR" ] || return 0
    local current
    current="$(read_current_release || true)"
    mapfile -t releases < <(
        find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
            2>/dev/null | sort -rn | cut -d' ' -f2-
    )
    local kept=0
    for release in "${releases[@]}"; do
        local resolved
        resolved="$(realpath "$release" 2>/dev/null || printf '%s\n' "$release")"
        if [ -n "${current:-}" ] && [ "$resolved" = "$current" ]; then
            log "keep current release $release"
            continue
        fi
        if [ "$kept" -lt "$RELEASE_KEEP_COUNT" ]; then
            kept=$((kept + 1))
            log "keep recent release $release"
            continue
        fi
        run_rm_rf "$release"
    done
}

cleanup_previews() {
    local preview_dir="$STORAGE_DIR/previews"
    log "cleanup previews begin keep_days=$PREVIEW_KEEP_DAYS"
    [ -d "$preview_dir" ] || return 0
    find "$preview_dir" -mindepth 1 -mtime +"$PREVIEW_KEEP_DAYS" -print \
        | while IFS= read -r path; do
            run_rm_rf "$path"
        done
}

is_positive_days() {
    [[ "${1:-}" =~ ^[1-9][0-9]*$ ]]
}

cleanup_uploads() {
    local upload_dir="$STORAGE_DIR/uploads"
    log "cleanup uploads begin keep_days=$UPLOAD_KEEP_DAYS"
    if ! is_positive_days "$UPLOAD_KEEP_DAYS"; then
        log "cleanup uploads skipped keep_days=$UPLOAD_KEEP_DAYS"
        return 0
    fi
    [ -d "$upload_dir" ] || return 0
    find "$upload_dir" -mindepth 1 -maxdepth 1 -mtime +"$UPLOAD_KEEP_DAYS" -print \
        | while IFS= read -r path; do
            run_rm_rf "$path"
        done
}

cleanup_regenerable_zips() {
    local report_dir="$STORAGE_DIR/reports"
    log "cleanup regenerable zips begin keep_days=$ZIP_KEEP_DAYS"
    if ! is_positive_days "$ZIP_KEEP_DAYS"; then
        log "cleanup regenerable zips skipped keep_days=$ZIP_KEEP_DAYS"
        return 0
    fi
    [ -d "$report_dir" ] || return 0
    find "$report_dir" -type f \( \
        -name '*_reports.zip' -o \
        -name '*_qa_pass_reports.zip' -o \
        -name '*_audit_package.zip' -o \
        -name '*_passed_audit_package.zip' \
    \) -mtime +"$ZIP_KEEP_DAYS" -print | while IFS= read -r path; do
        run_rm_rf "$path"
    done
}

cleanup_reports() {
    local report_dir="$STORAGE_DIR/reports"
    log "cleanup reports begin keep_days=$REPORT_KEEP_DAYS"
    if ! is_positive_days "$REPORT_KEEP_DAYS"; then
        log "cleanup reports skipped keep_days=$REPORT_KEEP_DAYS"
        return 0
    fi
    [ -d "$report_dir" ] || return 0
    find "$report_dir" -mindepth 1 -maxdepth 1 -mtime +"$REPORT_KEEP_DAYS" -print \
        | while IFS= read -r path; do
            run_rm_rf "$path"
        done
}

cleanup_audit_logs() {
    local db_path="$STORAGE_DIR/db/reportgen_web.sqlite"
    log "cleanup audit logs begin keep_days=$AUDIT_LOG_KEEP_DAYS"
    if ! is_positive_days "$AUDIT_LOG_KEEP_DAYS"; then
        log "cleanup audit logs skipped keep_days=$AUDIT_LOG_KEEP_DAYS"
        return 0
    fi
    [ -f "$db_path" ] || return 0
    local message
    message="$(
        DB_PATH="$db_path" \
        AUDIT_LOG_KEEP_DAYS="$AUDIT_LOG_KEEP_DAYS" \
        DRY_RUN="$DRY_RUN" \
        python3 - <<'PY'
from __future__ import annotations

import datetime as dt
import os
import sqlite3

db_path = os.environ["DB_PATH"]
keep_days = int(os.environ["AUDIT_LOG_KEEP_DAYS"])
dry_run = os.environ.get("DRY_RUN") == "1"
cutoff = (dt.datetime.utcnow() - dt.timedelta(days=keep_days)).strftime("%Y-%m-%d %H:%M:%S")

conn = sqlite3.connect(db_path)
try:
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_logs'"
    ).fetchone()
    if not table_exists:
        print("audit_logs table missing; skipped")
    else:
        count = conn.execute(
            "SELECT count(*) FROM audit_logs WHERE created_at < ?",
            (cutoff,),
        ).fetchone()[0]
        if dry_run:
            print(f"dry_run delete audit_logs rows={count} cutoff={cutoff}")
        else:
            conn.execute("DELETE FROM audit_logs WHERE created_at < ?", (cutoff,))
            conn.commit()
            print(f"deleted audit_logs rows={count} cutoff={cutoff}")
finally:
    conn.close()
PY
    )"
    log "$message"
}

cleanup_logs() {
    log "cleanup rotated logs begin keep_days=$LOG_KEEP_DAYS"
    [ -d "$LOG_DIR" ] || return 0
    find "$LOG_DIR" -type f \( -name '*.log.*' -o -name '*.log.[0-9]' \) \
        -mtime +"$LOG_KEEP_DAYS" -print | while IFS= read -r path; do
            run_rm_rf "$path"
        done
}

cleanup_all() {
    cleanup_backups
    cleanup_releases
    cleanup_previews
    cleanup_uploads
    cleanup_regenerable_zips
    cleanup_reports
    cleanup_audit_logs
    cleanup_logs
    log "cleanup complete"
}

with_lock

case "$MODE" in
    all)
        create_backup
        cleanup_all
        ;;
    backup)
        create_backup
        ;;
    cleanup)
        cleanup_all
        ;;
    verify)
        verify_backup "$VERIFY_ARCHIVE"
        ;;
    *)
        echo "Unsupported mode: $MODE" >&2
        usage >&2
        exit 2
        ;;
esac
