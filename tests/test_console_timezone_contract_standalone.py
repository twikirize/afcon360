"""Source-contract checks for console timestamp semantics without app/database imports."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_source(path):
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_console_events_use_offset_explicit_utc_iso_timestamps():
    streaming = read_source("app/production_console/streaming.py")
    assert streaming.count("'timestamp': to_iso_utc(timestamp)") == 2
    assert streaming.count("'timestamp_display': timestamp.strftime('%H:%M:%S UTC')") == 2


def test_console_uses_timestamp_as_source_of_truth_and_localizes_in_browser():
    template = read_source("templates/owner/production_console.html")
    assert "function formatConsoleTimestamp(timestamp)" in template
    assert "var time = formatConsoleTimestamp(event.timestamp);" in template
    assert "localizeExistingTimestamps();" in template
    assert "event.timestamp_display || new Date(event.timestamp).toLocaleTimeString()" not in template
    assert 'datetime="{{ event.timestamp or \'\' }}"' in template
    assert "if (!/(?:Z|[+-]\\\\d{2}:?\\\\d{2})$/i.test(raw)) return 'TZ?';" in template


def test_application_logging_uses_utc_iso_formatter():
    app_init = read_source("app/__init__.py")
    time_module = read_source("app/utils/time.py")
    assert "handler.setFormatter(UTCISOFormatter(" in app_init
    assert "class UTCISOFormatter(logging.Formatter)" in time_module
    assert 'return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")' in time_module
