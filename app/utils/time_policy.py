"""Shared, explicit calendar-time policy for AFCON360.

Technical instants are UTC. Business calendars are evaluated in a named IANA
timezone. Browser and host operating-system zones are never used for business
calendar decisions.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional, Tuple

UTC = timezone.utc


def require_iana_timezone(value: str, *, field: str = "timezone") -> ZoneInfo:
    """Return a validated IANA ZoneInfo; reject abbreviations and fixed offsets."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an IANA timezone name")
    name = value.strip()
    if name in {"UTC", "Etc/UTC"}:
        return ZoneInfo("UTC")
    if "/" not in name:
        raise ValueError(f"{field} must be an IANA timezone name, got {name!r}")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"{field} is not a recognized IANA timezone: {name!r}") from exc


def local_day_utc_bounds(day: date, timezone_name: str) -> Tuple[datetime, datetime]:
    """Return [start, end) UTC instants for a calendar day in an IANA zone."""
    if isinstance(day, datetime) or not isinstance(day, date):
        raise TypeError("day must be a datetime.date calendar date")
    zone = require_iana_timezone(timezone_name)
    next_day = day + timedelta(days=1)
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    end_local = datetime.combine(next_day, time.min, tzinfo=zone)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def local_month_utc_bounds(day: date, timezone_name: str) -> Tuple[datetime, datetime]:
    """Return [start, end) UTC instants for the month containing *day*."""
    if isinstance(day, datetime) or not isinstance(day, date):
        raise TypeError("day must be a datetime.date calendar date")
    start_day = date(day.year, day.month, 1)
    end_day = date(day.year + (day.month == 12), 1 if day.month == 12 else day.month + 1, 1)
    start_utc, _ = local_day_utc_bounds(start_day, timezone_name)
    end_utc, _ = local_day_utc_bounds(end_day, timezone_name)
    return start_utc, end_utc


def resolve_local_datetime(value: str | datetime, timezone_name: str) -> dict:
    """Resolve a scheduled wall time in its business zone and return auditable values.

    Naive input means local wall time in *timezone_name*. Ambiguous and
    nonexistent DST wall times are rejected. Offset-bearing input is accepted
    only when its UTC offset agrees with the IANA zone at that instant.
    """
    zone = require_iana_timezone(timezone_name, field="pickup timezone")
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("scheduled time must be a valid ISO-8601 datetime") from exc

    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        local = parsed.astimezone(zone)
        if parsed.utcoffset() != local.utcoffset():
            raise ValueError(
                "scheduled time offset does not match the pickup location's timezone"
            )
    else:
        wall = parsed.replace(tzinfo=None)
        candidates = []
        for fold in (0, 1):
            candidate = wall.replace(tzinfo=zone, fold=fold)
            round_trip = candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
            if round_trip == wall:
                candidates.append(candidate)
        distinct_offsets = {candidate.utcoffset() for candidate in candidates}
        if not candidates:
            raise ValueError(
                "scheduled local time does not exist in the pickup location's timezone"
            )
        if len(distinct_offsets) > 1:
            raise ValueError(
                "scheduled local time is ambiguous in the pickup location's timezone; "
                "choose a time outside the clock-change hour"
            )
        local = candidates[0]

    utc_instant = local.astimezone(UTC)
    return {
        "utc_datetime": utc_instant,
        "local_datetime": local.replace(tzinfo=None).isoformat(),
        "timezone_name": zone.key,
        "utc_offset": local.strftime("%z"),
    }


def choose_display_timezone(
    *,
    business_timezone: Optional[str] = None,
    preferred_timezone: Optional[str] = None,
    browser_timezone: Optional[str] = None,
    fallback_timezone: str = "UTC",
) -> str:
    """Apply business context, then user preference, then browser, then fallback."""
    for candidate in (
        business_timezone,
        preferred_timezone,
        browser_timezone,
        fallback_timezone,
    ):
        if not candidate:
            continue
        try:
            return require_iana_timezone(candidate).key
        except ValueError:
            continue
    return "UTC"
