"""Pure math and time helpers shared by the providers.

Nothing in this module imports Home Assistant or touches the network: providers
compose these primitives to build the normalized snapshot described in
``providers/base.py``, and the unit tests exercise them standalone.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from typing import Any
from zoneinfo import ZoneInfo


def number(value: Any, *, allow_negative: bool = False) -> float | None:
    """Return a finite number or ``None``.

    Provider APIs occasionally serialise numbers as strings and booleans are not
    numbers in this context.  Negative values are dropped unless the caller
    expects adjustments.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except (TypeError, ValueError):
            return None
    if not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(result):
        return None
    if result < 0 and not allow_negative:
        return None
    return result


def parse_timestamp(value: Any) -> datetime | None:
    """Parse an API timestamp (ISO string or epoch millis/seconds) to UTC."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 100_000_000_000:  # epoch milliseconds
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def api_param(value: Any) -> str | None:
    """Return a timestamp in the exact form a usage endpoint accepts.

    Some endpoints reject the ``+00:00`` form, so a raw provider string is
    preserved verbatim when possible.  Datetimes are rendered with ``Z``.
    """
    if isinstance(value, str) and value.strip():
        return value.strip()
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def tzinfo(name: str | None) -> ZoneInfo:
    """Return a timezone, falling back to UTC for unknown names."""
    try:
        return ZoneInfo(name) if name else UTC
    except Exception:
        return UTC


def days_until(now: datetime, target: datetime | None) -> float | None:
    """Return the non-negative number of days between ``now`` and ``target``."""
    if target is None:
        return None
    return max((target - now).total_seconds(), 0.0) / 86400.0


def days_since(start: datetime | None, now: datetime) -> float | None:
    """Return the non-negative number of days between ``start`` and ``now``."""
    if start is None:
        return None
    return max((now - start).total_seconds(), 0.0) / 86400.0


def percent(used: float | None, maximum: float | None) -> float | None:
    """Return ``used / maximum`` as a clamped percentage."""
    if used is None or maximum is None or maximum <= 0:
        return None
    return round(min(max(used / maximum * 100, 0.0), 100.0), 2)


def pace_status(
    current_daily: float | None, suggested_daily: float | None
) -> str | None:
    """Compare actual daily spend with the suggested daily pace."""
    if current_daily is None or suggested_daily is None:
        return None
    if suggested_daily <= 0:
        return "over"
    ratio = current_daily / suggested_daily
    if ratio <= 0.95:
        return "under"
    if ratio <= 1.05:
        return "on"
    return "over"


def day_boundaries(
    period_start: datetime | None,
    now: datetime | None = None,
    tz_name: str = "UTC",
    max_days: int = 45,
) -> list[datetime]:
    """Return day-start boundaries (UTC) covering a billing period.

    The first boundary is the exact billing period start.  Every later boundary
    is local midnight, and the list ends at local midnight of "today" so the
    final entry represents the current partial day.
    """
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if period_start is None:
        return []
    tz = tzinfo(tz_name)
    start_local = period_start.astimezone(tz)
    today_local = current.astimezone(tz).date()
    boundaries = [period_start.astimezone(UTC)]
    day = start_local.date() + timedelta(days=1)
    count = 0
    while day <= today_local and count < max_days:
        boundaries.append(datetime.combine(day, dt_time.min, tzinfo=tz).astimezone(UTC))
        day += timedelta(days=1)
        count += 1
    return boundaries


def empty_daily_series(
    tz_name: str = "UTC",
    max_usd: float | None = None,
    period_end: datetime | None = None,
    now: datetime | None = None,
    source: str = "unavailable",
) -> dict[str, Any]:
    """Return a daily series that carries no data."""
    del tz_name  # kept for signature symmetry with build_daily_series
    current = (now or datetime.now(UTC)).astimezone(UTC)
    return {
        "today": None,
        "days": [],
        "cumulative": [],
        "pace": [],
        "period_start": None,
        "period_end": period_end.isoformat() if period_end else None,
        "max_usd": max_usd,
        "pace_per_day_usd": None,
        "source": source,
        "backfilled_at": current.isoformat(),
    }


def build_daily_series(
    boundaries: list[datetime],
    totals: list[float | None],
    used: float | None,
    tz_name: str = "UTC",
    max_usd: float | None = None,
    period_end: datetime | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Turn cumulative-since-boundary totals into per-day usage.

    ``totals[i]`` is the usage from ``boundaries[i]`` to now, so the difference
    between adjacent totals is the usage of the earlier day.  The final total is
    today's partial day; the last day is reconciled so the cumulative series
    ends exactly at the plan's used amount.
    """
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if (
        not boundaries
        or len(boundaries) != len(totals)
        or any(t is None for t in totals)
    ):
        return empty_daily_series(tz_name, max_usd, period_end, current)
    tz = tzinfo(tz_name)

    values = [float(t) for t in totals if t is not None]
    daily: list[float] = []
    for index in range(len(values) - 1):
        daily.append(max(0.0, values[index] - values[index + 1]))
    daily.append(max(0.0, values[-1]))

    target = used if used is not None else sum(daily)
    if daily:
        daily[-1] = max(0.0, daily[-1] + (target - sum(daily)))

    days: list[dict[str, Any]] = []
    for boundary, value in zip(boundaries, daily, strict=False):
        days.append(
            {
                "date": boundary.astimezone(tz).date().isoformat(),
                "usd": round(value, 4),
            }
        )

    cumulative: list[dict[str, Any]] = []
    running = 0.0
    for item in days:
        running += item["usd"]
        cumulative.append({"date": item["date"], "usd": round(running, 4)})

    period_start = boundaries[0]
    total_days = None
    if period_end is not None:
        total_days = max((period_end - period_start).total_seconds() / 86400.0, 1 / 24)
    pace_per_day = (
        (max_usd / total_days) if max_usd is not None and total_days else None
    )
    pace: list[dict[str, Any]] = []
    if period_start and period_end and max_usd is not None:
        pace = [
            {"date": period_start.astimezone(tz).date().isoformat(), "usd": 0.0},
            {
                "date": period_end.astimezone(tz).date().isoformat(),
                "usd": round(max_usd, 4),
            },
        ]

    return {
        "today": days[-1]["usd"] if days else None,
        "days": days,
        "cumulative": cumulative,
        "pace": pace,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "max_usd": max_usd,
        "pace_per_day_usd": round(pace_per_day, 4)
        if pace_per_day is not None
        else None,
        "source": "api",
        "backfilled_at": current.isoformat(),
    }
