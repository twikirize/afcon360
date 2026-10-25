"""Runtime tests for timezone primitives without importing the full Flask app."""

from datetime import datetime, timezone
import logging
import importlib.util
from pathlib import Path
import sys


TIME_MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "utils" / "time.py"
SPEC = importlib.util.spec_from_file_location("afcon360_timezone_primitives", TIME_MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
time_utils = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = time_utils
SPEC.loader.exec_module(time_utils)


def test_utc_now_is_timezone_aware():
    value = time_utils.utc_now()
    assert value.tzinfo is not None
    assert value.utcoffset().total_seconds() == 0


def test_offset_input_is_normalized_to_utc():
    value = time_utils.to_utc(datetime.fromisoformat("2026-10-25T12:00:00+03:00"))
    assert value == datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)


def test_naive_input_is_rejected_without_an_explicit_zone():
    try:
        time_utils.parse_datetime_to_utc("2026-10-25T12:00:00")
    except ValueError as exc:
        assert "timezone offset" in str(exc)
    else:
        raise AssertionError("naive datetime was silently accepted")


def test_explicit_kampala_wall_time_converts_to_utc():
    value = time_utils.parse_datetime_to_utc(
        "2026-10-25T12:00:00", local_timezone="Africa/Kampala"
    )
    assert value == datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)


def test_ambiguous_daylight_saving_wall_time_is_rejected():
    try:
        time_utils.parse_datetime_to_utc(
            "2026-10-25T02:30:00", local_timezone="Europe/Berlin"
        )
    except ValueError as exc:
        assert "ambiguous" in str(exc)
    else:
        raise AssertionError("ambiguous local time was silently accepted")


def test_nonexistent_daylight_saving_wall_time_is_rejected():
    try:
        time_utils.parse_datetime_to_utc(
            "2026-03-29T02:30:00", local_timezone="Europe/Berlin"
        )
    except ValueError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("nonexistent local time was silently accepted")


def test_iso_utc_serialization_uses_z_suffix():
    value = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)
    assert time_utils.to_iso_utc(value) == "2026-10-25T09:00:00Z"


def test_local_conversion_preserves_the_instant():
    utc_value = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)
    local_value = time_utils.to_local(utc_value, "Africa/Kampala")
    assert local_value.hour == 12
    assert local_value.astimezone(timezone.utc) == utc_value



def test_log_formatter_emits_explicit_utc_iso_timestamp():
    formatter = time_utils.UTCISOFormatter("%(asctime)s [%(levelname)s] %(message)s")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="timezone check",
        args=(),
        exc_info=None,
    )
    record.created = datetime(2026, 10, 25, 9, 0, 0, 123000, tzinfo=timezone.utc).timestamp()

    assert formatter.format(record) == "2026-10-25T09:00:00.123Z [INFO] timezone check"
