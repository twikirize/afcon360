"""Driver offer display-currency enrichment contract tests."""
from types import SimpleNamespace

from app.transport.services import currency_presentation_service
from app.wallet.services import display_fx_service, home_currency_service


def test_driver_without_operating_country_keeps_base_fare_currency(monkeypatch):
    profile = SimpleNamespace(user=SimpleNamespace(), driver_metadata={})
    offer = {
        "booking_reference": "ride-public-reference",
        "fare_estimate": {"amount": 10.0, "currency": "USD"},
    }
    requested = []

    def same_currency_display(amount, base, preferred):
        requested.append((base, preferred))
        return {
            "display_amount": amount,
            "display_currency": preferred,
            "display_rate": "1",
            "display_rate_at": None,
            "display_rate_source": "same_currency",
            "display_rate_attribution_url": None,
            "display_is_home_currency": True,
            "display_is_approximate": False,
        }

    monkeypatch.setattr(
        display_fx_service, "build_display_amount", same_currency_display
    )
    enriched = currency_presentation_service.enrich_driver_offers_with_home_currency(
        [offer], profile
    )

    assert requested == [("USD", "USD")]
    fare = enriched[0]["fare_estimate"]
    assert fare["amount"] == 10.0
    assert fare["currency"] == "USD"
    assert fare["display_amount"] == 10.0
    assert fare["display_currency"] == "USD"
    assert fare["display_currency_basis"] == "fare_currency"
    assert fare["operating_country_code"] is None
    assert fare["display_label"] == (
        "Gross fare estimate — operating country not set; base fare currency shown"
    )
    # Enrichment is a read-time projection, not mutation of canonical offer data.
    assert offer["fare_estimate"] == {"amount": 10.0, "currency": "USD"}


def test_driver_offer_survives_display_fx_failure(monkeypatch):
    profile = SimpleNamespace(user=SimpleNamespace(), driver_metadata={})
    offer = {
        "booking_reference": "ride-public-reference",
        "fare_estimate": {"amount": 10.0, "currency": "USD"},
    }
    def fail_conversion(*args, **kwargs):
        raise RuntimeError("display-only provider unavailable")

    monkeypatch.setattr(
        display_fx_service, "build_display_amount", fail_conversion
    )

    enriched = currency_presentation_service.enrich_driver_offers_with_home_currency(
        [offer], profile
    )

    assert enriched[0]["fare_estimate"] == offer["fare_estimate"]
    assert enriched[0]["booking_reference"] == offer["booking_reference"]

def test_operating_country_determines_driver_display_currency(monkeypatch):
    profile = SimpleNamespace(
        user=SimpleNamespace(),
        driver_metadata={"operating_country_code": "KE"},
    )
    offer = {
        "booking_reference": "ride-public-reference",
        "fare_estimate": {"amount": 10.0, "currency": "USD"},
    }
    requested = []
    def fake_display(amount, base, preferred):
        requested.append(preferred)
        return {
            "display_amount": 1280.0,
            "display_currency": preferred,
            "display_rate": "128",
            "display_rate_at": "2026-11-04T00:00:00+00:00",
            "display_rate_source": "exchange_rate_api_open",
            "display_rate_attribution_url": "https://www.exchangerate-api.com",
            "display_is_home_currency": True,
            "display_is_approximate": True,
        }

    monkeypatch.setattr(
        display_fx_service, "build_display_amount", fake_display
    )
    enriched = currency_presentation_service.enrich_driver_offers_with_home_currency(
        [offer], profile
    )

    assert requested == ["KES"]
    fare = enriched[0]["fare_estimate"]
    assert fare["amount"] == 10.0
    assert fare["currency"] == "USD"
    assert fare["display_currency"] == "KES"
    assert fare["display_currency_basis"] == "operating_country"
    assert fare["operating_country_code"] == "KE"
    assert fare["operating_currency"] == "KES"
    assert fare["display_label"] == "Indicative operating-market gross fare estimate"
