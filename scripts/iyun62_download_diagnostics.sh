#!/usr/bin/env bash
# Summarize production report download timing from iyun62 uvicorn logs.
#
# This script reads structured report_download_* events only. Those events avoid
# patient names, report filenames, Excel filenames, and full report paths.

set -euo pipefail

SSH_HOST="${SSH_HOST:-iyun-server}"
RUNTIME_DIR="${RUNTIME_DIR:-/media/desk16/iyun6208/apps/reportgen-web-runtime}"
LOG_FILE="${LOG_FILE:-$RUNTIME_DIR/logs/uvicorn.log}"
TASK_ID="${TASK_ID:-}"
SINCE_MINUTES="${SINCE_MINUTES:-1440}"
LIMIT="${LIMIT:-30}"
TAIL_LINES="${TAIL_LINES:-5000}"
SLOW_MS="${SLOW_MS:-10000}"

usage() {
    cat <<'EOF'
Usage:
  scripts/iyun62_download_diagnostics.sh [options]

Options:
  --task-id ID          Show one task only.
  --since-minutes N     Only include events from the last N minutes. Default: 1440.
  --limit N             Recent terminal rows to print. Default: 30.
  --tail-lines N        Log lines to read from uvicorn.log. Default: 5000.
  --slow-ms N           Slow-download threshold in milliseconds. Default: 10000.
  -h, --help            Show this help.

Environment overrides:
  SSH_HOST, RUNTIME_DIR, LOG_FILE, TASK_ID, SINCE_MINUTES, LIMIT, TAIL_LINES, SLOW_MS

Examples:
  scripts/iyun62_download_diagnostics.sh
  TASK_ID=39486aef-cf33-4fba-8592-ea6dbc19f3e4 scripts/iyun62_download_diagnostics.sh
  scripts/iyun62_download_diagnostics.sh --since-minutes 60 --limit 50
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --task-id)
            TASK_ID="${2:?--task-id requires a value}"
            shift 2
            ;;
        --since-minutes)
            SINCE_MINUTES="${2:?--since-minutes requires a value}"
            shift 2
            ;;
        --limit)
            LIMIT="${2:?--limit requires a value}"
            shift 2
            ;;
        --tail-lines)
            TAIL_LINES="${2:?--tail-lines requires a value}"
            shift 2
            ;;
        --slow-ms)
            SLOW_MS="${2:?--slow-ms requires a value}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

ssh "$SSH_HOST" \
    "LOG_FILE='$LOG_FILE' TASK_ID='$TASK_ID' SINCE_MINUTES='$SINCE_MINUTES' LIMIT='$LIMIT' TAIL_LINES='$TAIL_LINES' SLOW_MS='$SLOW_MS' python3 -" <<'PY'
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from collections import defaultdict


log_file = os.environ["LOG_FILE"]
task_id_filter = os.environ.get("TASK_ID") or ""
since_minutes = int(os.environ.get("SINCE_MINUTES") or "1440")
limit = int(os.environ.get("LIMIT") or "30")
tail_lines = int(os.environ.get("TAIL_LINES") or "5000")
slow_ms = float(os.environ.get("SLOW_MS") or "10000")


def parse_ts(value: object) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def fmt_ms(value: object) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1f}"
    except Exception:
        return "-"


def fmt_num(value: object, digits: int = 2) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "-"


def compact_task(value: object) -> str:
    text = str(value or "-")
    if len(text) <= 12:
        return text
    return f"{text[:8]}...{text[-4:]}"


def event_name(event: dict) -> str:
    return str(event.get("event_type") or event.get("message") or "")


try:
    raw = subprocess.check_output(
        ["tail", "-n", str(tail_lines), log_file],
        text=True,
        stderr=subprocess.DEVNULL,
    )
except subprocess.CalledProcessError:
    print(f"ERROR: cannot read log file: {log_file}")
    raise SystemExit(1)

cutoff = dt.datetime.now() - dt.timedelta(minutes=since_minutes)
events: list[dict] = []
for line in raw.splitlines():
    if "report_download_" not in line:
        continue
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        continue
    if not event_name(payload).startswith("report_download_"):
        continue
    if task_id_filter and payload.get("task_id") != task_id_filter:
        continue
    timestamp = parse_ts(payload.get("timestamp"))
    if timestamp and timestamp < cutoff:
        continue
    payload["_parsed_timestamp"] = timestamp
    events.append(payload)

terminal = [
    e
    for e in events
    if event_name(e)
    in {"report_download_completed", "report_download_slow", "report_download_failed"}
]
started = [e for e in events if event_name(e) == "report_download_started"]
by_task: dict[str, list[dict]] = defaultdict(list)
for event in events:
    by_task[str(event.get("task_id") or "-")].append(event)

slow = [
    e
    for e in terminal
    if event_name(e) == "report_download_slow"
    or float(e.get("duration_ms") or 0) >= slow_ms
]
failed = [e for e in terminal if event_name(e) == "report_download_failed"]
completed = [e for e in terminal if event_name(e) == "report_download_completed"]
durations = [float(e.get("duration_ms") or 0) for e in terminal if e.get("duration_ms")]
sizes = [float(e.get("file_size_bytes") or 0) for e in terminal if e.get("file_size_bytes")]

open_starts = []
terminal_task_ids = {str(e.get("task_id") or "-") for e in terminal}
for event in started:
    tid = str(event.get("task_id") or "-")
    if tid not in terminal_task_ids:
        open_starts.append(event)

print("Download diagnostics")
print(f"  log_file: {log_file}")
print(f"  since_minutes: {since_minutes}")
print(f"  tail_lines: {tail_lines}")
print(f"  task_filter: {task_id_filter or '-'}")
print(f"  events: {len(events)}  started: {len(started)}  terminal: {len(terminal)}")
print(f"  completed: {len(completed)}  slow_or_over_threshold: {len(slow)}  failed: {len(failed)}")
if durations:
    print(
        "  duration_ms: "
        f"min={min(durations):.1f} max={max(durations):.1f} "
        f"avg={sum(durations) / len(durations):.1f}"
    )
if sizes:
    print(f"  largest_file_mb: {max(sizes) / 1024 / 1024:.2f}")

print()
if not events:
    print("No matching report_download_* events found.")
    raise SystemExit(0)

print("Recent terminal downloads")
print(
    "  timestamp              event                     task_id        kind"
    "              size_mb duration_ms mbps client"
)
for event in terminal[-limit:]:
    timestamp = event.get("timestamp", "-")
    print(
        "  "
        f"{str(timestamp)[:19]:<19} "
        f"{event_name(event):<25} "
        f"{compact_task(event.get('task_id')):<14} "
        f"{str(event.get('download_kind') or '-'):<17} "
        f"{fmt_num(event.get('file_size_mb')):>7} "
        f"{fmt_ms(event.get('duration_ms')):>11} "
        f"{fmt_num(event.get('throughput_mbps'), 1):>6} "
        f"{str(event.get('client_host') or '-')[:24]}"
    )

if slow:
    print()
    print("Slow downloads")
    for event in slow[-limit:]:
        print(
            "  "
            f"task_id={event.get('task_id')} "
            f"kind={event.get('download_kind')} "
            f"size_mb={fmt_num(event.get('file_size_mb'))} "
            f"duration_ms={fmt_ms(event.get('duration_ms'))} "
            f"mbps={fmt_num(event.get('throughput_mbps'), 1)} "
            f"client={event.get('client_host') or '-'} "
            f"cf_ray={event.get('cf_ray') or '-'}"
        )

if open_starts:
    print()
    print("Started without terminal event in selected log window")
    for event in open_starts[-limit:]:
        print(
            "  "
            f"task_id={event.get('task_id')} "
            f"kind={event.get('download_kind')} "
            f"started_at={event.get('timestamp')} "
            f"size_mb={fmt_num(event.get('file_size_mb'))} "
            f"client={event.get('client_host') or '-'}"
        )

print()
print("Triage rule of thumb")
print("  fast server duration + user sees slow => client/browser/network/Cloudflare side")
print("  report_download_slow or high duration_ms => server/tunnel/disk send path")
print("  high prepare_duration_ms on ZIP => packaging bottleneck before transfer")
PY
