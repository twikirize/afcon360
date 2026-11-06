"""Focused tests for the verified-country Wallet currency policy."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.wallet.services import home_currency_service


ACCEPTED = ["EUR", "GBP", "KES", "NGN", "TZS", "UGX", "USD"]
CATALOGUE = {
    "UG": {"country_name": "Uganda", "currency_code": "UGX"},
    "KE": {"country_name": "Kenya", "currency_code": "KES"},
    "TZ": {"country_name": "Tanzania", "currency_code": "TZS"},
    "NG": {"country_name": "Nigeria", "currency_code": "NGN"},
    "RW": {"country_name": "Rwanda", "currency_code": "RWF"},
    "ZA": {"country_name": "South Africa", "currency_code": "ZAR"},
}


def _policy(monkeypatch, country):
    monkeypatch.setattr(
        home_currency_service,
        "get_verified_wallet_country",
        lambda _user: country,
    )
    monkeypatch.setattr(
        home_currency_service,
        "_jurisdiction_catalogue",
        lambda: CATALOGUE,
    )
    monkeypatch.setattr(
        home_currency_service,
        "get_accepted_wallet_currencies",
        lambda: list(ACCEPTED),
    )


@pytest.mark.parametrize(
    ("country", "expected"),
    [("UG", "UGX"), ("KE", "KES"), ("TZ", "TZS"), ("NG", "NGN")],
)
def test_verified_country_suggests_local_currency(app, monkeypatch, country, expected):
    _policy(
        monkeypatch,
        {"country_code": country, "country_name": CATALOGUE[country]["country_name"], "source": "approved_address_kyc"},
    )

    with app.app_context():
        assert home_currency_service.resolve_home_currency(
            SimpleNamespace(id=1)
        ) == expected


def test_user_can_choose_any_owner_accepted_currency_not_only_local(app, monkeypatch):
    _policy(
        monkeypatch,
        {"country_code": "UG", "country_name": "Uganda", "source": "approved_address_kyc"},
    )

    with app.app_context():
        assert home_currency_service.resolve_home_currency(
            SimpleNamespace(id=1),
            requested_currency="eur",
        ) == "EUR"


def test_missing_verified_country_blocks_wallet_creation_without_usd_fallback(app, monkeypatch):
    _policy(monkeypatch, None)
    monkeypatch.setattr(
        home_currency_service,
        "_profile_for",
        lambda _user: SimpleNamespace(country="Uganda", nationality="UG", verification_status="pending"),
    )

    with app.app_context(), pytest.raises(ValueError, match="Verify your country"):
        home_currency_service.resolve_home_currency(SimpleNamespace(id=1))


def test_declared_country_without_proof_does_not_become_wallet_residence(app, monkeypatch):
    _policy(monkeypatch, None)
    monkeypatch.setattr(
        home_currency_service,
        "_profile_for",
        lambda _user: SimpleNamespace(country="Kenya", nationality="UG", verification_status="pending"),
    )

    with app.app_context(), pytest.raises(ValueError, match="Verify your country"):
        home_currency_service.resolve_home_currency(SimpleNamespace(id=1))


def test_unknown_verified_country_requires_explicit_accepted_currency(app, monkeypatch):
    _policy(
        monkeypatch,
        {"country_code": "XX", "country_name": "XX", "source": "approved_address_kyc"},
    )

    with app.app_context(), pytest.raises(ValueError, match="Choose your preferred Wallet currency"):
        home_currency_service.resolve_home_currency(SimpleNamespace(id=1))

    with app.app_context():
        assert home_currency_service.resolve_home_currency(
            SimpleNamespace(id=1), requested_currency="GBP"
        ) == "GBP"


def test_country_specific_restricted_currency_is_rejected(app, monkeypatch):
    _policy(
        monkeypatch,
        {"country_code": "NG", "country_name": "Nigeria", "source": "approved_address_kyc"},
    )

    with app.app_context(), pytest.raises(ValueError, match="not available for Wallet accounts"):
        home_currency_service.resolve_home_currency(
            SimpleNamespace(id=1), requested_currency="USD"
        )


def test_unaccepted_currency_is_rejected_even_if_fx_engine_knows_it(app, monkeypatch):
    _policy(
        monkeypatch,
        {"country_code": "UG", "country_name": "Uganda", "source": "approved_address_kyc"},
    )

    with app.app_context(), pytest.raises(ValueError, match="Choose a currency accepted"):
        home_currency_service.resolve_home_currency(
            SimpleNamespace(id=1), requested_currency="RWF"
        )


def test_country_normalization_uses_jurisdiction_catalogue_not_nationality(app, monkeypatch):
    monkeypatch.setattr(
        home_currency_service,
        "_jurisdiction_catalogue",
        lambda: CATALOGUE,
    )

    with app.app_context():
        assert home_currency_service.normalize_country_code("Kampala, Uganda") == "UG"
        assert home_currency_service.normalize_country_code("Kenya") == "KE"
        assert home_currency_service.normalize_country_code("UG") == "UG"
        assert home_currency_service.get_country_local_currency("TZ") == "TZS"


def test_address_kyc_country_precedes_profile_country(app, monkeypatch):
    from app.kyc import models as kyc_models

    record = SimpleNamespace(
        country="TZ",
        verified_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        id=99,
    )

    class FakeKycQuery:
        def filter_by(self, **kwargs):
            assert kwargs == {"user_id": 12, "record_type": "address_verification"}
            return self

        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def all(self):
            return [record]

    _policy(
        monkeypatch,
        {"country_code": "TZ", "country_name": "Tanzania", "source": "approved_address_kyc"},
    )
    monkeypatch.setattr(kyc_models.KycRecord, "query", FakeKycQuery())

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            home_currency_service,
            "_profile_for",
            lambda _user: SimpleNamespace(country="Kenya", verification_status="verified"),
        )
        with app.app_context():
            country = home_currency_service.get_verified_wallet_country(
                SimpleNamespace(id=12)
            )

    assert country["country_code"] == "TZ"
    assert country["source"] == "approved_address_kyc"


def test_operating_country_display_mapping_remains_available():
    assert home_currency_service.home_currency_for_country("KE") == "KES"
    assert home_currency_service.home_currency_for_country("Uganda") == "UGX"
    assert home_currency_service.home_currency_for_country("TZ") == "TZS"
    assert home_currency_service.home_currency_for_country("Unknown") is None
