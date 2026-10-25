"""Source-level contracts for explicit UTC logging across entry points."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_flask_factory_normalizes_preconfigured_stream_handlers():
    app_init = read("app/__init__.py")
    assert "for existing_handler in root.handlers:" in app_init
    assert "isinstance(existing_handler, logging.StreamHandler)" in app_init
    assert "existing_handler.setFormatter(UTCISOFormatter(" in app_init


def test_standalone_entrypoint_bootstrap_logs_explicit_utc():
    entry = read("app.py")
    assert "_utc_formatter.converter = time.gmtime" in entry
    assert "'%(asctime)sZ [%(levelname)s] %(message)s'" in entry
    assert "datefmt='%Y-%m-%dT%H:%M:%S'" in entry


def test_event_consumer_and_production_console_use_shared_utc_formatter():
    consumer = read("app/notifications/events/stream_consumer.py")
    console = read("app/production_console/streaming.py")
    assert "from app.utils.time import UTCISOFormatter" in consumer
    assert "handler.setFormatter(UTCISOFormatter(" in consumer
    assert "from app.utils.time import UTCISOFormatter, to_iso_utc" in console
    assert "handler.setFormatter(UTCISOFormatter(" in console
