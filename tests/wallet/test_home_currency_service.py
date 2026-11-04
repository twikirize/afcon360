"""Focused tests for Wallet home-currency onboarding resolution."""
from types import SimpleNamespace

import pytest

from app.wallet.services import home_currency_service


def test_profile_country_sets_home_currency_before_nationality(app, monkeypatch):
    profile = SimpleNamespace(country="Kenya", nationality="UG")
    monkeypatch.setattr(home_currency_service, "_profile_for", lambda _user: profile)

    with app.app_context():
        assert home_currency_service.resolve_home_currency(
            SimpleNamespace(id=1)
        ) == "KES"


def test_profile_country_code_sets_home_currency(app, monkeypatch):
    profile = SimpleNamespace(country="TZ", nationality="UG")
    monkeypatch.setattr(home_currency_service, "_profile_for", lambda _user: profile)

    with app.app_context():
        assert home_currency_service.resolve_home_currency(
            SimpleNamespace(id=1)
        ) == "TZS"


def test_explicit_supported_choice_overrides_profile_default(app, monkeypatch):
    profile = SimpleNamespace(country="Uganda", nationality="UG")
    monkeypatch.setattr(home_currency_service, "_profile_for", lambda _user: profile)

    with app.app_context():
        assert home_currency_service.resolve_home_currency(
            SimpleNamespace(id=1), requested_currency="kes"
        ) == "KES"


def test_unmapped_profile_uses_configured_default(app, monkeypatch):
    profile = SimpleNamespace(country="Unknown market", nationality=None)
    monkeypatch.setattr(home_currency_service, "_profile_for", lambda _user: profile)
    app.config["WALLET_DEFAULT_HOME_CURRENCY"] = "EUR"

    with app.app_context():
        assert home_currency_service.resolve_home_currency(
            SimpleNamespace(id=1)
        ) == "EUR"


def test_unsupported_explicit_currency_is_rejected(app):
    with app.app_context(), pytest.raises(ValueError):
        home_currency_service.resolve_home_currency(
            SimpleNamespace(id=1), requested_currency="XYZ"
        )

def test_nationality_is_not_used_as_missing_residence(app, monkeypatch):
    profile = SimpleNamespace(country=None, nationality="Uganda")
    monkeypatch.setattr(home_currency_service, "_profile_for", lambda _user: profile)
    app.config["WALLET_DEFAULT_HOME_CURRENCY"] = "USD"

    with app.app_context():
        assert home_currency_service.resolve_home_currency(
            SimpleNamespace(id=1)
        ) == "USD"

def test_operating_country_maps_to_supported_market_currency():
    assert home_currency_service.home_currency_for_country("KE") == "KES"
    assert home_currency_service.home_currency_for_country("Uganda") == "UGX"
    assert home_currency_service.home_currency_for_country("TZ") == "TZS"
    assert home_currency_service.home_currency_for_country("Unknown") is None
