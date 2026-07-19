"""Time helpers for the database's naive-UTC and local-business contracts."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utc_now_naive() -> datetime:
    """Return current UTC without tzinfo for legacy SQLAlchemy DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def local_datetime_to_utc_naive(value: str, timezone_name: str) -> datetime:
    """Interpret a naive browser/business timestamp and return database UTC."""
    normalized = str(value or "").strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def business_day_start_utc_naive(
    timezone_name: str,
    *,
    now: datetime | None = None,
) -> datetime:
    """Return today's business-zone midnight in database naive-UTC form."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = current.astimezone(ZoneInfo(timezone_name))
    local_midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)
