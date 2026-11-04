"""Tests for non-settlement, indicative Wallet home-currency display FX."""
from datetime import datetime, timedelta, timezone

from app.wallet.services import display_fx_service


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_same_currency_display_does_not_call_provider(app, monkeypatch):
    display_fx_service._clear_process_cache_for_tests()

    def unexpected_request(*args, **kwargs):
        raise AssertionError("same-currency display must not make an FX request")

    monkeypatch.setattr(display_fx_service.requests, "get", unexpected_request)
    with app.app_context():
        result = display_fx_service.build_display_amount(12.5, "USD", "USD")

    assert result["display_amount"] == 12.5
    assert result["display_currency"] == "USD"
    assert result["display_is_home_currency"] is True
    assert result["display_is_approximate"] is False
    assert result["display_rate"] == "1"


def test_fresh_provider_rate_builds_indicative_home_currency_amount(
        app, monkeypatch):
    display_fx_service._clear_process_cache_for_tests()
    now = datetime.now(timezone.utc)
    payload = {
        "result": "success",
        "base_code": "USD",
        "time_last_update_unix": int(now.timestamp()),
        "time_next_update_unix": int((now + timedelta(hours=24)).timestamp()),
        "rates": {"USD": 1, "KES": 128.456, "UGX": 3800.75},
    }
    calls = []

    def fake_get(url, timeout):
        calls.append((url, timeout))
        return _Response(payload)

    monkeypatch.setattr(display_fx_service.requests, "get", fake_get)
    with app.app_context():
        result = display_fx_service.build_display_amount(10, "USD", "KES")

    assert len(calls) == 1
    assert result["display_amount"] == 1284.56
    assert result["display_currency"] == "KES"
    assert result["display_is_home_currency"] is True
    assert result["display_is_approximate"] is True
    assert result["display_rate"] == "128.456"
    assert result["display_rate_at"]
    assert result["display_rate_attribution_url"] == "https://www.exchangerate-api.com"


def test_stale_provider_rate_falls_back_to_original_currency(app, monkeypatch):
    display_fx_service._clear_process_cache_for_tests()
    now = datetime.now(timezone.utc)
    old = now - timedelta(hours=60)
    payload = {
        "result": "success",
        "base_code": "USD",
        "time_last_update_unix": int(old.timestamp()),
        "time_next_update_unix": int((old + timedelta(hours=24)).timestamp()),
        "rates": {"USD": 1, "KES": 128},
    }
    monkeypatch.setattr(
        display_fx_service.requests,
        "get",
        lambda url, timeout: _Response(payload),
    )
    with app.app_context():
        result = display_fx_service.build_display_amount(10, "USD", "KES")

    assert result["display_amount"] == 10.0
    assert result["display_currency"] == "USD"
    assert result["display_is_home_currency"] is False
    assert result["display_is_approximate"] is False
    assert result["display_rate"] is None


def test_zero_decimal_home_currency_rounds_to_whole_units(app, monkeypatch):
    display_fx_service._clear_process_cache_for_tests()
    now = datetime.now(timezone.utc)
    payload = {
        "result": "success",
        "base_code": "USD",
        "time_last_update_unix": int(now.timestamp()),
        "time_next_update_unix": int((now + timedelta(hours=24)).timestamp()),
        "rates": {"USD": 1, "UGX": 3800.75},
    }
    monkeypatch.setattr(
        display_fx_service.requests,
        "get",
        lambda url, timeout: _Response(payload),
    )
    with app.app_context():
        result = display_fx_service.build_display_amount(1, "USD", "UGX")

    assert result["display_amount"] == 3801.0
    assert result["display_currency"] == "UGX"
    assert result["display_is_approximate"] is True

def test_tzs_keeps_two_minor_unit_decimal_places(app, monkeypatch):
    display_fx_service._clear_process_cache_for_tests()
    now = datetime.now(timezone.utc)
    payload = {
        "result": "success",
        "base_code": "USD",
        "time_last_update_unix": int(now.timestamp()),
        "time_next_update_unix": int((now + timedelta(hours=24)).timestamp()),
        "rates": {"USD": 1, "TZS": 2500.25},
    }
    monkeypatch.setattr(
        display_fx_service.requests,
        "get",
        lambda url, timeout: _Response(payload),
    )
    with app.app_context():
        result = display_fx_service.build_display_amount(1, "USD", "TZS")

    assert result["display_amount"] == 2500.25
    assert result["display_currency"] == "TZS"
