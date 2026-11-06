"""Executable FX routing tests: USD is the reference, mock rates never execute."""
from decimal import Decimal

import pytest

from app.wallet.services.fx_service import FXService, RateUnavailableError


def test_non_usd_cross_pair_uses_two_usd_reference_legs(app):
    calls = []

    class Provider:
        source_name = "test-executable-provider"

        def get_rate(self, *, base_currency, quote_currency):
            calls.append((base_currency, quote_currency))
            assert base_currency == "USD"
            rates = {
                "KES": Decimal("128.00"),
                "NGN": Decimal("1550.00"),
                "EUR": Decimal("0.926"),
            }
            return rates[quote_currency]

    with app.app_context():
        app.extensions["fx_rate_provider"] = Provider()
        service = FXService()
        result = service._fetch_from_api_safe("KES", "NGN")

    assert result == (Decimal("1") / Decimal("128.00")) * Decimal("1550.00")
    assert calls == [("USD", "KES"), ("USD", "NGN")]
    assert service._last_rate_source == "test-executable-provider"


def test_fx_pair_to_usd_inverts_usd_reference_rate(app):
    class Provider:
        def get_rate(self, *, base_currency, quote_currency):
            assert (base_currency, quote_currency) == ("USD", "UGX")
            return Decimal("3800")

    with app.app_context():
        app.extensions["fx_rate_provider"] = Provider()
        result = FXService()._fetch_from_api_safe("UGX", "USD")

    assert result == Decimal("1") / Decimal("3800")


def test_fx_from_usd_uses_direct_provider_reference_pair(app):
    class Provider:
        def get_rate(self, *, base_currency, quote_currency):
            assert (base_currency, quote_currency) == ("USD", "EUR")
            return Decimal("0.926")

    with app.app_context():
        app.extensions["fx_rate_provider"] = Provider()
        result = FXService()._fetch_from_api_safe("USD", "EUR")

    assert result == Decimal("0.926")


def test_fx_never_falls_back_to_mock_rates_when_provider_is_missing(app):
    with app.app_context():
        app.extensions.pop("fx_rate_provider", None)
        service = FXService()
        with pytest.raises(RateUnavailableError, match="No executable FX provider"):
            service._fetch_from_api_safe("KES", "NGN")


def test_mock_rate_table_is_not_used_even_when_it_contains_a_direct_cross_pair(app):
    class Provider:
        def get_rate(self, *, base_currency, quote_currency):
            return {
                "KES": Decimal("128"),
                "NGN": Decimal("1550"),
            }[quote_currency]

    with app.app_context():
        app.extensions["fx_rate_provider"] = Provider()
        service = FXService()
        service._get_mock_rates = lambda: {
            ("KES", "NGN"): Decimal("99"),
            ("USD", "KES"): Decimal("128"),
            ("USD", "NGN"): Decimal("1550"),
        }
        result = service._fetch_from_api_safe("KES", "NGN")

    assert result == (Decimal("1") / Decimal("128")) * Decimal("1550")
