"""Unit tests for the provider-independent helpers in ``calc``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.ai_sub.calc import (
    api_param,
    build_daily_series,
    day_boundaries,
    days_since,
    days_until,
    empty_daily_series,
    number,
    pace_status,
    parse_timestamp,
    percent,
    tzinfo,
)


def test_number_rejects_non_numbers() -> None:
    assert number("12.5") == 12.5
    assert number(3) == 3.0
    assert number(True) is None
    assert number("abc") is None
    assert number(None) is None
    assert number(-1) is None
    assert number(-1, allow_negative=True) == -1.0
    assert number(float("inf")) is None


def test_parse_timestamp_handles_iso_and_epoch() -> None:
    expected = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert parse_timestamp("2026-01-02T03:04:05Z") == expected
    assert parse_timestamp("2026-01-02T03:04:05") == expected
    assert parse_timestamp(1_767_323_045_000) == expected
    assert parse_timestamp("not a date") is None
    assert parse_timestamp(None) is None


def test_api_param_preserves_raw_strings() -> None:
    assert api_param("2026-01-02T03:04:05+00:00") == "2026-01-02T03:04:05+00:00"
    parsed = api_param(datetime(2026, 1, 2, 3, 4, 5, 123000, tzinfo=UTC))
    assert parsed == "2026-01-02T03:04:05.123Z"


def test_percent_and_pace() -> None:
    assert percent(25, 100) == 25.0
    assert percent(200, 100) == 100.0
    assert percent(5, 0) is None
    assert pace_status(5, 10) == "under"
    assert pace_status(10, 10) == "on"
    assert pace_status(15, 10) == "over"
    assert pace_status(1, 0) == "over"
    assert pace_status(None, 10) is None


def test_days_helpers() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    assert days_until(now, now + timedelta(days=2)) == 2.0
    assert days_until(now, now - timedelta(days=2)) == 0.0
    assert days_until(now, None) is None
    assert days_since(now - timedelta(days=1), now) == 1.0
    assert days_since(None, now) is None


def test_tzinfo_falls_back_to_utc() -> None:
    assert tzinfo("Europe/Rome").key == "Europe/Rome"
    assert tzinfo("Not/AZone") is UTC
    assert tzinfo(None) is UTC


def test_day_boundaries_start_at_period_and_end_at_local_midnight() -> None:
    start = datetime(2026, 1, 10, 15, 0, tzinfo=UTC)
    now = datetime(2026, 1, 13, 10, 0, tzinfo=UTC)
    boundaries = day_boundaries(start, now, "Europe/Rome")
    assert boundaries[0] == start
    assert len(boundaries) == 4
    # Local midnight in Rome is 23:00 UTC the previous day.
    assert boundaries[-1] == datetime(2026, 1, 12, 23, 0, tzinfo=UTC)
    assert day_boundaries(None, now, "UTC") == []


def test_day_boundaries_are_capped() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert len(day_boundaries(start, now, "UTC", max_days=5)) == 6


def test_build_daily_series_differences_cumulative_totals() -> None:
    start = datetime(2026, 1, 10, 0, 0, tzinfo=UTC)
    boundaries = [start, start + timedelta(days=1), start + timedelta(days=2)]
    now = start + timedelta(days=2, hours=12)
    series = build_daily_series(
        boundaries,
        [10.0, 7.0, 3.0],
        10.0,
        "UTC",
        max_usd=80.0,
        period_end=start + timedelta(days=4),
        now=now,
    )
    assert series["source"] == "api"
    assert [day["usd"] for day in series["days"]] == [3.0, 4.0, 3.0]
    assert series["today"] == 3.0
    assert series["cumulative"][-1]["usd"] == 10.0
    assert series["pace_per_day_usd"] == 20.0
    assert series["pace"][-1]["usd"] == 80.0


def test_build_daily_series_reconciles_to_used_total() -> None:
    start = datetime(2026, 1, 10, tzinfo=UTC)
    boundaries = [start, start + timedelta(days=1)]
    series = build_daily_series(
        boundaries, [8.0, 2.0], 12.0, "UTC", now=start + timedelta(days=1)
    )
    assert [day["usd"] for day in series["days"]] == [6.0, 6.0]
    assert series["cumulative"][-1]["usd"] == 12.0


def test_build_daily_series_is_unavailable_without_totals() -> None:
    series = build_daily_series([], [], 5.0)
    assert series["source"] == "unavailable"
    assert series["days"] == []
    assert empty_daily_series()["today"] is None
