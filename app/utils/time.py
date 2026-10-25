"""Canonical timezone primitives for AFCON360.

Contract:
- Store and compare absolute instants in UTC.
- Do not silently guess the meaning of a naive datetime.
- A wall-clock datetime may be interpreted only with an explicit IANA timezone.
- Reject ambiguous/nonexistent local wall times unless the caller supplies an offset.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc


def utc_now() -> datetime:
    """Return the current instant as an aware UTC datetime."""
    return datetime.now(UTC)


def is_aware(value: datetime) -> bool:
    """Return True only when value has a usable UTC offset."""
    return value.tzinfo is not None and value.utcoffset() is not None


def require_aware(value: datetime, *, field_name: str = "datetime") -> datetime:
    """Return an aware datetime or fail closed on a naive value."""
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if not is_aware(value):
        raise ValueError(
            f"{field_name} must include a timezone offset; "
            "naive datetimes are not accepted"
        )
    return value


def to_utc(value: datetime, *, field_name: str = "datetime") -> datetime:
    """Normalize an explicitly aware instant to UTC."""
    return require_aware(value, field_name=field_name).astimezone(UTC)


def _resolve_zone(value: str | tzinfo, *, field_name: str) -> tzinfo:
    if isinstance(value, str):
        try:
            return ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"{field_name} is not a valid IANA timezone: {value!r}") from exc
    if not isinstance(value, tzinfo):
        raise TypeError(f"{field_name} must be an IANA timezone name or tzinfo")
    return value


def parse_datetime_to_utc(
    value: str | datetime,
    *,
    field_name: str = "datetime",
    local_timezone: str | tzinfo | None = None,
) -> datetime:
    """Parse an ISO-8601 instant and return UTC.

    Offset-aware input is normalized directly. Naive input is rejected unless
    the caller explicitly supplies its IANA timezone. For local wall-clock
    input, DST gaps and folds are rejected: the caller must submit an explicit
    UTC offset to identify one unambiguous instant.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{field_name} must not be empty")
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a valid ISO-8601 datetime") from exc
    else:
        raise TypeError(f"{field_name} must be an ISO-8601 string or datetime")

    if is_aware(parsed):
        return parsed.astimezone(UTC)

    if local_timezone is None:
        raise ValueError(
            f"{field_name} must include a timezone offset; "
            "provide an explicit local_timezone only for wall-clock input"
        )

    zone = _resolve_zone(local_timezone, field_name="local_timezone")
    wall_time = parsed.replace(tzinfo=None)
    valid_instants: list[datetime] = []

    # ZoneInfo permits construction of nonexistent local times. A UTC
    # round-trip tells us whether each fold represents a real wall time.
    for fold in (0, 1):
        candidate = wall_time.replace(tzinfo=zone, fold=fold)
        instant = candidate.astimezone(UTC)
        round_trip = instant.astimezone(zone).replace(tzinfo=None)
        if round_trip == wall_time and instant not in valid_instants:
            valid_instants.append(instant)

    if not valid_instants:
        raise ValueError(
            f"{field_name} does not exist in timezone {local_timezone!s} "
            "because of a daylight-saving transition"
        )
    if len(valid_instants) > 1:
        raise ValueError(
            f"{field_name} is ambiguous in timezone {local_timezone!s}; "
            "submit an ISO-8601 value with an explicit UTC offset"
        )

    return valid_instants[0]


def to_iso_utc(value: datetime, *, field_name: str = "datetime") -> str:
    """Serialize an aware instant as ISO-8601 UTC with a trailing Z."""
    return to_utc(value, field_name=field_name).isoformat().replace("+00:00", "Z")


def to_local(value: datetime, timezone_name: str) -> datetime:
    """Convert an aware instant to a requested IANA timezone for display."""
    return to_utc(value).astimezone(_resolve_zone(timezone_name, field_name="timezone_name"))


class UTCISOFormatter(logging.Formatter):
    """Format application log timestamps as ISO-8601 UTC, independent of host TZ."""

    def formatTime(self, record, datefmt=None):
        moment = datetime.fromtimestamp(record.created, tz=UTC)
        if datefmt:
            return moment.strftime(datefmt)
        return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")
