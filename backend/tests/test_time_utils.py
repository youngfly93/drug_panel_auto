from datetime import datetime, timezone

from app.time_utils import (
    business_day_start_utc_naive,
    local_datetime_to_utc_naive,
)


def test_shanghai_date_filter_converts_local_midnight_to_utc() -> None:
    assert local_datetime_to_utc_naive(
        "2026-07-20",
        "Asia/Shanghai",
    ) == datetime(2026, 7, 19, 16, 0)


def test_aware_filter_is_normalized_to_database_utc() -> None:
    assert local_datetime_to_utc_naive(
        "2026-07-20T00:00:00+08:00",
        "Asia/Shanghai",
    ) == datetime(2026, 7, 19, 16, 0)


def test_business_today_boundary_is_stable_across_utc_date_boundary() -> None:
    assert business_day_start_utc_naive(
        "Asia/Shanghai",
        now=datetime(2026, 7, 19, 16, 9, tzinfo=timezone.utc),
    ) == datetime(2026, 7, 19, 16, 0)
