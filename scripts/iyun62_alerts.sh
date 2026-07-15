#!/usr/bin/env bash
# User-level active alerts for iyun62 reportgen-web production.
#
# The script reads sanitized /admin/ops/status alerts and posts them to an
# optional webhook. It never reads Excel files, report files, patient payloads,
# client IPs, user agents, or server paths.

set -euo pipefail

APP_ROOT="${APP_ROOT:-/media/desk16/iyun6208/apps}"
RUNTIME_DIR="${RUNTIME_DIR:-$APP_ROOT/reportgen-web-runtime}"
PORT="${PORT:-8000}"
OPS_URL="${OPS_URL:-http://127.0.0.1:$PORT/api/v1/admin/ops/status?recent_task_limit=5&download_event_limit=50}"
OPS_LOGIN_URL="${OPS_LOGIN_URL:-http://127.0.0.1:$PORT/api/v1/auth/login}"
AUTH_ENV_FILE="${AUTH_ENV_FILE:-$RUNTIME_DIR/.env.prod}"
ALERT_ENV_FILE="${ALERT_ENV_FILE:-$RUNTIME_DIR/alerts.env}"
ALERT_FORMAT="${ALERT_FORMAT:-auto}"
ALERT_MIN_SEVERITY="${ALERT_MIN_SEVERITY:-warning}"
ALERT_REPEAT_MINUTES="${ALERT_REPEAT_MINUTES:-60}"
ALERT_SEND_RECOVERY="${ALERT_SEND_RECOVERY:-1}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-${RG_WEB_ALERT_WEBHOOK_URL:-}}"
MODE="${1:-check}"
DRY_RUN="${DRY_RUN:-0}"

LOG_DIR="$RUNTIME_DIR/logs"
LOG_FILE="$LOG_DIR/alerts.log"
STATE_FILE="${STATE_FILE:-$RUNTIME_DIR/alert_state.json}"
LOCK_DIR="$RUNTIME_DIR/alerts.lock"

if [ -f "$AUTH_ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$AUTH_ENV_FILE"
    set +a
fi
OPS_AUTH_USERNAME="${OPS_AUTH_USERNAME:-${RG_WEB_MONITOR_USERNAME:-${RG_WEB_DEFAULT_ADMIN_USERNAME:-}}}"
OPS_AUTH_PASSWORD="${OPS_AUTH_PASSWORD:-${RG_WEB_MONITOR_PASSWORD:-${RG_WEB_DEFAULT_ADMIN_PASSWORD:-}}}"

if [ -f "$ALERT_ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ALERT_ENV_FILE"
    set +a
    ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-${RG_WEB_ALERT_WEBHOOK_URL:-}}"
    ALERT_FORMAT="${ALERT_FORMAT:-auto}"
    ALERT_MIN_SEVERITY="${ALERT_MIN_SEVERITY:-warning}"
    ALERT_REPEAT_MINUTES="${ALERT_REPEAT_MINUTES:-60}"
    ALERT_SEND_RECOVERY="${ALERT_SEND_RECOVERY:-1}"
fi

usage() {
    cat <<'EOF'
Usage:
  iyun62_alerts.sh [check]

Environment overrides:
  RUNTIME_DIR, PORT, OPS_URL, OPS_LOGIN_URL, AUTH_ENV_FILE
  OPS_AUTH_USERNAME, OPS_AUTH_PASSWORD
  ALERT_WEBHOOK_URL / RG_WEB_ALERT_WEBHOOK_URL
  ALERT_FORMAT=auto|wecom|dingtalk|feishu|generic
  ALERT_MIN_SEVERITY=warning|danger
  ALERT_REPEAT_MINUTES=60
  ALERT_SEND_RECOVERY=1
  DRY_RUN=1
EOF
}

mkdir -p "$LOG_DIR"

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

with_lock() {
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        old_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
        if [ -n "${old_pid:-}" ] && ! kill -0 "$old_pid" 2>/dev/null; then
            rm -rf "$LOCK_DIR"
            mkdir "$LOCK_DIR"
        else
            log "alerts already running"
            exit 0
        fi
    fi
    printf '%s\n' "$$" > "$LOCK_DIR/pid"
    trap 'rm -rf "$LOCK_DIR" 2>/dev/null || true' EXIT
}

case "$MODE" in
    check)
        ;;
    -h|--help|help)
        usage
        exit 0
        ;;
    *)
        echo "Unsupported mode: $MODE" >&2
        usage >&2
        exit 2
        ;;
esac

with_lock

OPS_URL="$OPS_URL" \
OPS_LOGIN_URL="$OPS_LOGIN_URL" \
OPS_AUTH_USERNAME="$OPS_AUTH_USERNAME" \
OPS_AUTH_PASSWORD="$OPS_AUTH_PASSWORD" \
STATE_FILE="$STATE_FILE" \
ALERT_WEBHOOK_URL="$ALERT_WEBHOOK_URL" \
ALERT_FORMAT="$ALERT_FORMAT" \
ALERT_MIN_SEVERITY="$ALERT_MIN_SEVERITY" \
ALERT_REPEAT_MINUTES="$ALERT_REPEAT_MINUTES" \
ALERT_SEND_RECOVERY="$ALERT_SEND_RECOVERY" \
DRY_RUN="$DRY_RUN" \
python3 - <<'PY' | while IFS= read -r line; do log "$line"; done
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from typing import Any


SEVERITY_ORDER = {"info": 0, "success": 0, "warning": 1, "danger": 2}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def login_token(url: str, username: str, password: str) -> str:
    if not username or not password:
        raise RuntimeError("ops monitor credentials are missing")
    body = json.dumps({"username": username, "password": password}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "reportgen-alerts/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = str((payload.get("data") or {}).get("access_token") or "")
    if not token:
        raise RuntimeError("ops monitor login did not return a token")
    return token


def fetch_status(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "reportgen-alerts/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def alert_signature(alerts: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "id": str(item.get("id") or ""),
            "severity": str(item.get("severity") or ""),
            "title": str(item.get("title") or ""),
            "threshold": str(item.get("threshold") or ""),
        }
        for item in sorted(alerts, key=lambda item: str(item.get("id") or ""))
    ]
    data = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def choose_format(webhook_url: str, configured: str) -> str:
    if configured != "auto":
        return configured
    if "qyapi.weixin.qq.com" in webhook_url:
        return "wecom"
    if "oapi.dingtalk.com" in webhook_url:
        return "dingtalk"
    if "open.feishu.cn" in webhook_url:
        return "feishu"
    return "generic"


def post_webhook(webhook_url: str, fmt: str, title: str, text: str) -> None:
    if fmt == "wecom":
        payload = {"msgtype": "markdown", "markdown": {"content": text}}
    elif fmt == "dingtalk":
        payload = {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
    elif fmt == "feishu":
        payload = {"msg_type": "text", "content": {"text": text}}
    else:
        payload = {"text": text, "title": title}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "reportgen-alerts/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        response.read()


def format_alert_message(data: dict[str, Any], alerts: list[dict[str, Any]]) -> str:
    deployment = data.get("deployment") or {}
    retention = data.get("retention") or {}
    lines = [
        "## ReportGen 生产告警",
        f"- Release: {deployment.get('release') or '-'} ({deployment.get('revision_short') or '-'})",
        f"- 时间: {data.get('generated_at') or now_iso()}",
        f"- 告警数: {len(alerts)}",
    ]
    if retention:
        lines.append(
            "- 保留策略: "
            f"Excel {retention.get('upload_keep_days', '-')}天 / "
            f"报告 {retention.get('report_keep_days', '-')}天 / "
            f"审计 {retention.get('audit_log_keep_days', '-')}天"
        )
    lines.append("")
    for item in alerts[:12]:
        severity = str(item.get("severity") or "warning")
        label = str(item.get("label") or "告警")
        title = str(item.get("title") or item.get("id") or "未知告警")
        message = str(item.get("message") or "")
        threshold = item.get("threshold")
        prefix = "[DANGER]" if severity == "danger" else "[WARN]"
        line = f"{prefix} **{label}**: {title}"
        if threshold:
            line += f"（阈值 {threshold}）"
        lines.append(line)
        if message:
            lines.append(f"> {message}")
    if len(alerts) > 12:
        lines.append(f"... 还有 {len(alerts) - 12} 条")
    return "\n".join(lines)


def format_recovery_message(data: dict[str, Any]) -> str:
    deployment = data.get("deployment") or {}
    return "\n".join(
        [
            "## ReportGen 生产告警恢复",
            f"- Release: {deployment.get('release') or '-'} ({deployment.get('revision_short') or '-'})",
            f"- 时间: {data.get('generated_at') or now_iso()}",
            "- 当前无 active 告警。",
        ]
    )


def main() -> int:
    ops_url = os.environ["OPS_URL"]
    login_url = os.environ["OPS_LOGIN_URL"]
    state_file = pathlib.Path(os.environ["STATE_FILE"])
    webhook_url = os.environ.get("ALERT_WEBHOOK_URL") or ""
    fmt = choose_format(webhook_url, os.environ.get("ALERT_FORMAT") or "auto")
    min_severity = os.environ.get("ALERT_MIN_SEVERITY") or "warning"
    repeat_minutes = int(os.environ.get("ALERT_REPEAT_MINUTES") or "60")
    send_recovery = os.environ.get("ALERT_SEND_RECOVERY") != "0"
    dry_run = os.environ.get("DRY_RUN") == "1"

    try:
        token = login_token(
            login_url,
            os.environ.get("OPS_AUTH_USERNAME") or "",
            os.environ.get("OPS_AUTH_PASSWORD") or "",
        )
        payload = fetch_status(ops_url, token)
    except Exception as exc:
        payload = {
            "success": True,
            "data": {
                "generated_at": now_iso(),
                "deployment": {},
                "alerts": [
                    {
                        "id": "ops.status.unreachable",
                        "severity": "danger",
                        "label": "监控",
                        "title": "生产状态接口不可达",
                        "message": f"{type(exc).__name__}: {exc}",
                        "threshold": "HTTP 200",
                    }
                ],
            },
        }

    data = payload.get("data") or {}
    raw_alerts = data.get("alerts") or []
    min_rank = SEVERITY_ORDER.get(min_severity, 1)
    alerts = [
        item
        for item in raw_alerts
        if SEVERITY_ORDER.get(str(item.get("severity") or "warning"), 1) >= min_rank
    ]
    state = load_json(state_file)
    now = dt.datetime.now(dt.timezone.utc)
    last_sent = state.get("last_sent_at")
    last_dt = None
    if last_sent:
        try:
            last_dt = dt.datetime.fromisoformat(str(last_sent))
        except ValueError:
            last_dt = None
    repeat_due = not last_dt or (now - last_dt).total_seconds() >= repeat_minutes * 60

    if not alerts:
        if state.get("active") and send_recovery:
            text = format_recovery_message(data)
            if dry_run or not webhook_url:
                print(f"recovery webhook={'dry_run' if dry_run else 'missing'}")
            else:
                post_webhook(webhook_url, fmt, "ReportGen 生产告警恢复", text)
                print("recovery sent")
        if dry_run:
            print("dry_run state unchanged")
            print("alerts ok count=0")
            return 0
        write_json(
            state_file,
            {
                "active": False,
                "signature": "",
                "last_checked_at": now_iso(),
                "last_sent_at": state.get("last_sent_at"),
            },
        )
        print("alerts ok count=0")
        return 0

    signature = alert_signature(alerts)
    changed = signature != state.get("signature") or bool(webhook_url and state.get("webhook_missing"))
    should_send = changed or repeat_due
    if not should_send:
        print(f"alerts suppressed count={len(alerts)} signature={signature[:12]}")
        write_json(
            state_file,
            {
                **state,
                "active": True,
                "signature": signature,
                "last_checked_at": now_iso(),
                "last_alert_count": len(alerts),
                "webhook_missing": not bool(webhook_url),
            },
        )
        return 0

    text = format_alert_message(data, alerts)
    if dry_run or not webhook_url:
        print(f"alerts webhook={'dry_run' if dry_run else 'missing'} count={len(alerts)}")
    else:
        post_webhook(webhook_url, fmt, "ReportGen 生产告警", text)
        print(f"alerts sent count={len(alerts)} signature={signature[:12]} format={fmt}")

    if dry_run:
        print("dry_run state unchanged")
        return 0

    write_json(
        state_file,
        {
            "active": True,
            "signature": signature,
            "last_checked_at": now_iso(),
            "last_sent_at": now_iso(),
            "last_alert_count": len(alerts),
            "webhook_missing": not bool(webhook_url),
        },
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"webhook HTTPError status={exc.code}", file=sys.stderr)
        raise
PY
