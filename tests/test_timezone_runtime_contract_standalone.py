"""Static contracts for runtime timestamp boundaries; no app/database import."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_geo_history_and_activity_windows_require_explicit_timezone():
    history = source("app/geo/history.py")
    activity = source("app/geo/activity.py")
    assert "parse_datetime_to_utc(value, field_name=name)" in history
    assert 'parse_datetime_to_utc(since, field_name="since")' in activity
    assert 'parse_datetime_to_utc(until, field_name="until")' in activity
    assert "bound = bound.replace(tzinfo=timezone.utc)" not in history
    assert "start = start.replace(tzinfo=timezone.utc)" not in activity
    assert "end = end.replace(tzinfo=timezone.utc)" not in activity


def test_geo_location_timestamps_require_explicit_timezone():
    validation = source("app/geo/validation.py")
    realtime = source("app/geo/realtime.py")
    assert 'parse_datetime_to_utc(ts, field_name="timestamp")' in validation
    assert "if point.timestamp.tzinfo is None or point.timestamp.utcoffset() is None:" in validation
    assert 'to_utc(ref, field_name="now")' in realtime
    assert 'parse_datetime_to_utc(observed_at, field_name="observed_at")' in realtime
    assert "ref = ref.replace(tzinfo=timezone.utc)" not in realtime
