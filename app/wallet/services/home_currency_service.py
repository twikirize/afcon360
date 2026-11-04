"""Resolve a user's primary Wallet currency from their home market.

The primary AccountModel.currency is the Wallet home-currency choice for the
user's first wallet. It remains distinct from Transport's USD fare denomination.
No FX is performed here; this module only resolves and validates the preference.
"""
from __future__ import annotations

from typing import Any, Optional

from flask import current_app


# Keep this list aligned with the currencies currently exposed in wallet_create.
# Adding a currency requires Wallet/payment-method support to be reviewed first.
SUPPORTED_HOME_CURRENCIES = frozenset({
    "USD", "UGX", "KES", "TZS", "NGN", "EUR", "GBP",
})

# Country-of-residence defaults. ISO country codes and common profile country
# names are accepted. Country takes precedence over nationality.
COUNTRY_HOME_CURRENCY = {
    "UG": "UGX",
    "UGANDA": "UGX",
    "KE": "KES",
    "KENYA": "KES",
    "TZ": "TZS",
    "TANZANIA": "TZS",
    "RW": "USD",  # Rwanda Franc is not currently offered in wallet_create.
    "RWANDA": "USD",
    "NG": "NGN",
    "NIGERIA": "NGN",
    "US": "USD",
    "USA": "USD",
    "UNITED STATES": "USD",
    "GB": "GBP",
    "UK": "GBP",
    "UNITED KINGDOM": "GBP",
    "IE": "EUR",
    "IRELAND": "EUR",
    "DE": "EUR",
    "GERMANY": "EUR",
    "FR": "EUR",
    "FRANCE": "EUR",
}


def validate_home_currency(value: Any) -> str:
    """Return a supported ISO currency code or raise ValueError."""
    currency = str(value or "").strip().upper()
    if currency not in SUPPORTED_HOME_CURRENCIES:
        raise ValueError(
            "Choose a supported Wallet home currency: "
            + ", ".join(sorted(SUPPORTED_HOME_CURRENCIES))
        )
    return currency


def _country_currency(country: Any) -> Optional[str]:
    token = str(country or "").strip().upper()
    if not token:
        return None

    # Exact matching is preferred. A few profiles store a country label with
    # a region suffix (for example, "Kampala, Uganda"), so match full country
    # names only at token boundaries; never guess from arbitrary substrings.
    if token in COUNTRY_HOME_CURRENCY:
        return COUNTRY_HOME_CURRENCY[token]

    for name, currency in COUNTRY_HOME_CURRENCY.items():
        if len(name) > 2 and (
            token == name
            or token.startswith(name + ",")
            or token.endswith("," + name)
            or (" " + name + " ") in (" " + token + " ")
        ):
            return currency
    return None


def _profile_for(user: Any):
    try:
        from app.profile.models import get_profile_by_user
        return get_profile_by_user(user)
    except Exception:
        # A missing optional profile must not prevent account creation. The
        # explicit currency picker or platform default remains available.
        return None


def resolve_home_currency(
    user: Any,
    requested_currency: Any = None,
) -> str:
    """Resolve the first Wallet's home currency.

    An explicit selection is validated and wins. Otherwise use the user's
    profile country, then nationality as a legacy fallback, then the
    configured platform default (USD unless explicitly configured).
    """
    if requested_currency not in (None, ""):
        return validate_home_currency(requested_currency)

    profile = _profile_for(user)
    if profile is not None:
        country_currency = _country_currency(getattr(profile, "country", None))
        if country_currency:
            return validate_home_currency(country_currency)

        nationality_currency = _country_currency(
            getattr(profile, "nationality", None)
        )
        if nationality_currency:
            return validate_home_currency(nationality_currency)

    configured_default = current_app.config.get(
        "WALLET_DEFAULT_HOME_CURRENCY", "USD"
    )
    try:
        return validate_home_currency(configured_default)
    except ValueError:
        current_app.logger.error(
            "Invalid WALLET_DEFAULT_HOME_CURRENCY; using USD"
        )
        return "USD"


def get_user_home_currency(user: Any) -> str:
    """Return the persisted primary Wallet currency, or its onboarding default."""
    if user is None:
        return "USD"

    try:
        from app.wallet.models.ledger import AccountModel, AccountOwnerType

        account = AccountModel.query.filter_by(
            user_id=getattr(user, "id", None),
            owner_type=AccountOwnerType.USER,
        ).first()
        if account is not None:
            return validate_home_currency(account.currency)
    except Exception:
        # Display/quote discovery should remain available when Wallet has no
        # account yet. It must not create an account as a side effect.
        pass

    return resolve_home_currency(user)
