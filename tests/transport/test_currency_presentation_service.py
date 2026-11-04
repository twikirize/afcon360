"""Driver offer display-currency enrichment contract tests."""
from types import SimpleNamespace

from app.transport.services import currency_presentation_service
from app.wallet.services import display_fx_service, home_currency_service


def test_driver_offer_adds_wallet_display_without_changing_base_fare(monkeypatch):
    profile = SimpleNamespace(user=SimpleNamespace())
    offer = {
        "booking_reference": "ride-public-reference",
        "fare_estimate": {"amount": 10.0, "currency": "USD"},
    }
    monkeypatch.setattr(
        home_currency_service, "get_user_home_currency",
        lambda _user: "KES",
    )
    monkeypatch.setattr(
        display_fx_service, "build_display_amount",
        lambda amount, base, home: {
            "display_amount": 1280.0,
            "display_currency": "KES",
            "display_rate": "128",
            "display_rate_at": "2026-11-04T00:00:00+00:00",
            "display_rate_source": "exchange_rate_api_open",
            "display_rate_attribution_url": "https://www.exchangerate-api.com",
            "display_is_home_currency": True,
            "display_is_approximate": True,
        },
    )

    enriched = currency_presentation_service.enrich_driver_offers_with_home_currency(
        [offer], profile
    )

    assert enriched[0]["fare_estimate"]["amount"] == 10.0
    assert enriched[0]["fare_estimate"]["currency"] == "USD"
    assert enriched[0]["fare_estimate"]["display_amount"] == 1280.0
    assert enriched[0]["fare_estimate"]["display_currency"] == "KES"
    assert enriched[0]["fare_estimate"]["display_label"] == "Indicative Wallet-home gross fare estimate"
    assert enriched[0]["home_currency"] == "KES"
    # Enrichment is a read-time projection, not mutation of canonical offer data.
    assert offer["fare_estimate"] == {"amount": 10.0, "currency": "USD"}


def test_driver_offer_survives_display_fx_failure(monkeypatch):
    profile = SimpleNamespace(user=SimpleNamespace())
    offer = {
        "booking_reference": "ride-public-reference",
        "fare_estimate": {"amount": 10.0, "currency": "USD"},
    }
    monkeypatch.setattr(
        home_currency_service, "get_user_home_currency",
        lambda _user: "KES",
    )

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

def test_driver_operating_country_currency_precedes_wallet_home_currency(monkeypatch):
    profile = SimpleNamespace(
        user=SimpleNamespace(),
        driver_metadata={"operating_country_code": "KE"},
    )
    offer = {
        "booking_reference": "ride-public-reference",
        "fare_estimate": {"amount": 10.0, "currency": "USD"},
    }
    requested = []
    monkeypatch.setattr(
        home_currency_service, "get_user_home_currency",
        lambda _user: "UGX",
    )

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
    assert fare["wallet_home_currency"] == "UGX"
    assert fare["display_label"] == "Indicative operating-market gross fare estimate"
