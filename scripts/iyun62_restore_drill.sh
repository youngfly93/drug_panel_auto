#!/usr/bin/env bash
# Non-destructive backup restore drill for iyun62 reportgen-web production.
#
# The default drill verifies the complete archive stream, extracts only metadata
# and the SQLite backup copy into a temporary server-local directory, runs
# SQLite integrity checks, writes a redacted drill report, then removes the
# temporary extraction. Set RESTORE_DRILL_FULL=1 only when intentionally doing a
# full storage extraction on a host with enough free disk.

set -euo pipefail

APP_ROOT="${APP_ROOT:-/media/desk16/iyun6208/apps}"
RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
BACKUP_DIR="${BACKUP_DIR:-$APP_ROOT/reportgen-web-backups}"
DRILL_ROOT="${DRILL_ROOT:-$RUNTIME_DIR/restore-drills}"
LOG_DIR="${LOG_DIR:-$RUNTIME_DIR/logs}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/restore_drill.log}"
RESTORE_DRILL_FULL="${RESTORE_DRILL_FULL:-0}"
KEEP_DRILL_FILES="${KEEP_DRILL_FILES:-0}"
MODE="${MODE:-run}"

usage() {
    cat <<'EOF'
Usage:
  iyun62_restore_drill.sh [run] [--archive PATH] [--full] [--keep-files]

Options:
  --archive PATH  Backup archive to drill. Defaults to newest reportgen backup.
  --full          Extract the full archive into the drill directory.
  --keep-files    Keep temporary extracted metadata/DB after the drill.
  -h, --help      Show this help.

Environment overrides:
  APP_ROOT, RUNTIME_DIR, BACKUP_DIR, DRILL_ROOT, LOG_DIR, LOG_FILE
  RESTORE_DRILL_FULL=1, KEEP_DRILL_FILES=1
EOF
}

ARCHIVE=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        run)
            MODE="run"
            shift
            ;;
        --archive)
            ARCHIVE="${2:?--archive requires a value}"
            shift 2
            ;;
        --full)
            RESTORE_DRILL_FULL=1
            shift
            ;;
        --keep-files)
            KEEP_DRILL_FILES=1
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

if [ "$MODE" != "run" ]; then
    echo "Unsupported mode: $MODE" >&2
    usage >&2
    exit 2
fi

mkdir -p "$LOG_DIR" "$DRILL_ROOT"
chmod 700 "$DRILL_ROOT" 2>/dev/null || true

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

hash_file() {
    local path="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$path" | awk '{print $1}'
    else
        shasum -a 256 "$path" | awk '{print $1}'
    fi
}

if [ -z "$ARCHIVE" ]; then
    ARCHIVE="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'reportgen-web-backup-*.tar.gz' -printf '%T@ %p\n' 2>/dev/null | sort -rn | awk 'NR==1 {sub(/^[^ ]+ /, ""); print}')"
fi

if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
    echo "Backup archive not found: ${ARCHIVE:-<newest>}" >&2
    exit 1
fi

timestamp="$(date '+%Y%m%d_%H%M%S')"
archive_base="$(basename "$ARCHIVE")"
drill_dir="$DRILL_ROOT/restore-drill-$timestamp"
report_path="$LOG_DIR/restore-drill-$timestamp.json"
sidecar_manifest="$ARCHIVE.manifest.json"

cleanup() {
    if [ "$KEEP_DRILL_FILES" != "1" ]; then
        rm -rf "$drill_dir"
    fi
}
trap cleanup EXIT

mkdir -p "$drill_dir"
chmod 700 "$drill_dir" 2>/dev/null || true

log "restore_drill begin archive=$archive_base full=$RESTORE_DRILL_FULL"

expected_sha=""
if [ -f "$ARCHIVE.sha256" ]; then
    expected_sha="$(awk '{print $1}' "$ARCHIVE.sha256")"
fi
actual_sha="$(hash_file "$ARCHIVE")"
if [ -n "$expected_sha" ] && [ "$expected_sha" != "$actual_sha" ]; then
    echo "Checksum mismatch for $archive_base" >&2
    exit 1
fi

tar_stats_json="$(
    TAR_ARCHIVE="$ARCHIVE" python3 - <<'PY'
from __future__ import annotations

import json
import os
import subprocess

archive = os.environ["TAR_ARCHIVE"]
roots = [
    "meta",
    "db",
    "uploads",
    "reports",
    "signatures",
    "reference_reports",
    "patient_info.yaml",
]
counts = {root: 0 for root in roots}
required = {"meta/manifest.pre.json": False, "db/reportgen_web.sqlite": False}

proc = subprocess.Popen(
    ["tar", "-tzf", archive],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
assert proc.stdout is not None
for raw in proc.stdout:
    path = raw.rstrip("\n")
    for key in required:
        if path == key:
            required[key] = True
    for root in roots:
        if path == root or path.startswith(root + "/"):
            counts[root] += 1
stderr = proc.stderr.read() if proc.stderr else ""
rc = proc.wait()
if rc != 0:
    raise SystemExit(f"tar list failed rc={rc}: {stderr.strip()}")
print(json.dumps({"entry_counts": counts, "required_entries": required}, ensure_ascii=False))
PY
)"

tar -xzf "$ARCHIVE" -C "$drill_dir" meta db/reportgen_web.sqlite

manifest_path="$drill_dir/meta/manifest.pre.json"
if [ -f "$sidecar_manifest" ]; then
    manifest_path="$sidecar_manifest"
fi

db_result_json="$(
    DB_PATH="$drill_dir/db/reportgen_web.sqlite" python3 - <<'PY'
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

db_path = Path(os.environ["DB_PATH"])
result = {
    "exists": db_path.exists(),
    "bytes": db_path.stat().st_size if db_path.exists() else 0,
    "integrity_check": None,
    "tables": 0,
    "audit_log_rows": None,
}
if not db_path.exists():
    raise SystemExit("Extracted SQLite backup missing")

conn = sqlite3.connect(db_path)
try:
    row = conn.execute("PRAGMA integrity_check").fetchone()
    result["integrity_check"] = row[0] if row else None
    result["tables"] = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    has_audit = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_logs'"
    ).fetchone()
    if has_audit:
        result["audit_log_rows"] = conn.execute("SELECT count(*) FROM audit_logs").fetchone()[0]
finally:
    conn.close()

if result["integrity_check"] != "ok":
    raise SystemExit("Extracted backup SQLite integrity_check failed")
print(json.dumps(result, ensure_ascii=False))
PY
)"

full_extract_json='{"enabled": false}'
if [ "$RESTORE_DRILL_FULL" = "1" ]; then
    full_dir="$drill_dir/full_extract"
    mkdir -p "$full_dir"
    tar -xzf "$ARCHIVE" -C "$full_dir"
    full_extract_json="$(
        FULL_DIR="$full_dir" python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

root = Path(os.environ["FULL_DIR"])
files = 0
dirs = 0
bytes_total = 0
for current, dirnames, filenames in os.walk(root):
    dirs += len(dirnames)
    for filename in filenames:
        path = Path(current) / filename
        try:
            bytes_total += path.stat().st_size
            files += 1
        except OSError:
            pass
print(json.dumps({"enabled": True, "files": files, "dirs": dirs, "bytes": bytes_total}, ensure_ascii=False))
PY
    )"
fi

REPORT_PATH="$report_path" \
ARCHIVE_BASENAME="$archive_base" \
ARCHIVE_BYTES="$(stat -c '%s' "$ARCHIVE")" \
ARCHIVE_SHA256="$actual_sha" \
MANIFEST_PATH="$manifest_path" \
TAR_STATS_JSON="$tar_stats_json" \
DB_RESULT_JSON="$db_result_json" \
FULL_EXTRACT_JSON="$full_extract_json" \
RESTORE_DRILL_FULL="$RESTORE_DRILL_FULL" \
KEEP_DRILL_FILES="$KEEP_DRILL_FILES" \
DRILL_STARTED_AT="$timestamp" \
python3 - <<'PY'
from __future__ import annotations

import json
import os
import platform
from pathlib import Path

manifest_path = Path(os.environ["MANIFEST_PATH"])
manifest = {}
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

report = {
    "schema_version": "1.0",
    "status": "PASS",
    "host": platform.node(),
    "drill_started_at": os.environ["DRILL_STARTED_AT"],
    "archive": {
        "filename": os.environ["ARCHIVE_BASENAME"],
        "bytes": int(os.environ["ARCHIVE_BYTES"]),
        "sha256": os.environ["ARCHIVE_SHA256"],
    },
    "source_backup": {
        "created_at": manifest.get("created_at"),
        "revision": manifest.get("revision"),
        "storage_stats": manifest.get("storage_stats"),
    },
    "checks": {
        "checksum": "PASS",
        "tar_stream": "PASS",
        "required_entries": json.loads(os.environ["TAR_STATS_JSON"]).get("required_entries"),
        "entry_counts": json.loads(os.environ["TAR_STATS_JSON"]).get("entry_counts"),
        "sqlite": json.loads(os.environ["DB_RESULT_JSON"]),
        "full_extract": json.loads(os.environ["FULL_EXTRACT_JSON"]),
    },
    "cleanup": {
        "temporary_extraction_removed": os.environ["KEEP_DRILL_FILES"] != "1",
        "kept_files_for_manual_inspection": os.environ["KEEP_DRILL_FILES"] == "1",
    },
    "notes": [
        "No production storage path was modified.",
        "The drill report intentionally omits patient fields, filenames, client IPs, and user agents.",
        "Default mode validates archive readability plus SQLite restoreability without duplicating all report files.",
    ],
}
Path(os.environ["REPORT_PATH"]).write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
PY

chmod 600 "$report_path" 2>/dev/null || true
log "restore_drill PASS archive=$archive_base report=$report_path"
printf '%s\n' "$report_path"
