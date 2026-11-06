"""Wallet home-currency and verified-country policy.

A Wallet account is denominated in a user-selected currency accepted by the
AFCON360 Wallet capability configuration. USD is only the FX reference/base
currency; it is never an automatic customer-wallet denomination.

Wallet opening requires a verified country context. A verified address KYC
record takes precedence, followed by the verified country on the canonical
UserProfile. Nationality and unverified profile text are never residence proof.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from flask import current_app, has_app_context


FX_BASE_CURRENCY = "USD"


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def get_accepted_wallet_currencies() -> list[str]:
    """Read owner-approved Wallet currencies and ensure the FX engine can serve them.

    PaymentMethodConfig(method_id='wallet').supported_currencies is the
    authoritative Wallet acceptance list. The FX service has a separate and
    wider universe; being FX-known alone does not make a currency Wallet-
    accepted. This function is read-only and never seeds or mutates settings.
    """
    from app.wallet.models.payment_method import PaymentMethodConfig

    method = PaymentMethodConfig.query.filter_by(method_id="wallet").first()
    if method is not None:
        if not method.is_enabled or not method.is_active:
            raise ValueError(
                "AFCON360 Wallet is temporarily unavailable for new accounts."
            )
        configured = method.supported_currencies or []
    else:
        # Explicit deployment override is useful during bootstrap, but an
        # absent owner capability row is not replaced by a guessed USD list.
        configured = current_app.config.get("WALLET_ACCEPTED_CURRENCIES") or []

    accepted = {
        str(value or "").strip().upper()
        for value in configured
        if str(value or "").strip()
    }
    if not accepted:
        raise ValueError(
            "AFCON360 has not configured any accepted Wallet currencies. "
            "Please contact support."
        )

    from app.wallet.services.fx_service import FXService

    fx_supported = {str(value).upper() for value in FXService.SUPPORTED_CURRENCIES}
    unsupported = sorted(accepted - fx_supported)
    if unsupported:
        current_app.logger.error(
            "Wallet currency configuration contains currencies unsupported by FX: %s",
            ",".join(unsupported),
        )
    # A currency must be accepted by Wallet AND recognised by the FX engine.
    # Unsupported entries are not exposed as selectable wallet currencies.
    return sorted(accepted & fx_supported)


def _jurisdiction_catalogue() -> dict[str, dict]:
    """Return seeded jurisdiction defaults overlaid with active DB policy rows.

    This is a read-only lookup. It never seeds or mutates jurisdiction data.
    A partially populated database must not hide countries still present in
    the canonical jurisdiction catalogue.
    """
    catalogue: dict[str, dict] = {}
    try:
        from app.compliance.aml_regulatory_service import _JURISDICTIONS

        catalogue.update({
            str(code).strip().upper(): {
                "country_name": str(data.get("country_name") or ""),
                "currency_code": str(data.get("currency_code") or "").strip().upper(),
            }
            for code, data in _JURISDICTIONS.items()
        })
    except Exception:
        if has_app_context():
            current_app.logger.warning(
                "Canonical AML jurisdiction seed catalogue is unavailable",
                exc_info=True,
            )

    try:
        from app.compliance.aml_regulatory_models import JurisdictionProfile

        rows = JurisdictionProfile.query.filter_by(is_active=True).all()
        for row in rows:
            code = str(row.country_code or "").strip().upper()
            if not code:
                continue
            catalogue[code] = {
                "country_name": str(row.country_name or catalogue.get(code, {}).get("country_name") or ""),
                "currency_code": str(
                    row.currency_code or catalogue.get(code, {}).get("currency_code") or ""
                ).strip().upper(),
            }
    except Exception:
        # A missing optional AML table must not trigger a database write or
        # erase the canonical static reference data already loaded.
        if has_app_context():
            current_app.logger.debug(
                "AML jurisdiction database rows are unavailable",
                exc_info=True,
            )

    return catalogue


def normalize_country_code(country: Any) -> Optional[str]:
    """Resolve a verified country value to a configured ISO/jurisdiction code."""
    token = str(country or "").strip().upper()
    if not token:
        return None

    catalogue = _jurisdiction_catalogue()
    if len(token) == 2 and token.isalpha() and token in catalogue:
        return token

    # Accept exact country names and region-prefixed/suffixed profile labels
    # such as "Kampala, Uganda". Never match arbitrary substrings.
    for code, item in catalogue.items():
        name = str(item.get("country_name") or "").strip().upper()
        if not name:
            continue
        if token == name or token.startswith(name + ",") or token.endswith("," + name):
            return code

    # Preserve valid ISO-2 codes for jurisdictions not yet in the AML catalogue.
    if len(token) == 2 and token.isalpha():
        return token
    return None


def get_country_local_currency(country: Any) -> Optional[str]:
    """Return the configured jurisdiction currency, if the country is known."""
    code = normalize_country_code(country)
    if not code:
        return None
    catalogue = _jurisdiction_catalogue()
    details = catalogue.get(code)
    if not details:
        return None
    currency = str(details.get("currency_code") or "").strip().upper()
    return currency or None


def home_currency_for_country(country: Any) -> Optional[str]:
    """Compatibility helper for country-based display currency suggestions.

    Display currency is not proof of Wallet eligibility. Wallet account creation
    separately checks the verified country and owner-approved currency list.
    """
    return get_country_local_currency(country)


def _profile_for(user: Any):
    if user is None:
        return None
    try:
        from app.profile.models import get_profile_by_user

        return get_profile_by_user(user)
    except Exception:
        if has_app_context():
            current_app.logger.debug("Could not load canonical UserProfile", exc_info=True)
        return None


def get_verified_wallet_country(user: Any) -> Optional[Dict[str, str]]:
    """Resolve the user's proven residence/registration jurisdiction.

    Priority:
      1. Latest approved/verified address-proof KYC record with a country.
      2. Country on a verified/approved canonical UserProfile.

    A pending/rejected address record or an unverified profile country is not
    accepted as proof. Nationality is intentionally never consulted.
    """
    if user is None or getattr(user, "id", None) is None:
        return None

    # A verified address proof is the strongest signal of current residence.
    try:
        from app.kyc.models import KycRecord

        records = (
            KycRecord.query.filter_by(
                user_id=int(user.id),
                record_type="address_verification",
            )
            .filter(KycRecord.status.in_(("approved", "verified")))
            .order_by(
                KycRecord.verified_at.desc().nullslast(),
                KycRecord.created_at.desc(),
                KycRecord.id.desc(),
            )
            .all()
        )
        for record in records:
            code = normalize_country_code(record.country)
            if code:
                catalogue = _jurisdiction_catalogue()
                return {
                    "country_code": code,
                    "country_name": str(
                        (catalogue.get(code) or {}).get("country_name")
                        or record.country
                    ),
                    "source": "approved_address_kyc",
                }
    except Exception:
        if has_app_context():
            current_app.logger.debug(
                "Could not resolve approved address KYC country",
                exc_info=True,
            )

    profile = _profile_for(user)
    if profile is None or _status_value(
        getattr(profile, "verification_status", None)
    ) not in {"verified", "approved"}:
        return None

    code = normalize_country_code(getattr(profile, "country", None))
    if not code:
        return None

    catalogue = _jurisdiction_catalogue()
    return {
        "country_code": code,
        "country_name": str(
            (catalogue.get(code) or {}).get("country_name")
            or getattr(profile, "country", "")
        ),
        "source": "verified_profile",
    }


def validate_home_currency(value: Any, country_code: Optional[str] = None) -> str:
    """Validate a requested currency against Wallet acceptance and jurisdiction rules."""
    currency = str(value or "").strip().upper()
    accepted = get_accepted_wallet_currencies()
    if currency not in accepted:
        raise ValueError(
            "Choose a currency accepted by AFCON360 Wallet: "
            + ", ".join(accepted)
        )

    if country_code:
        try:
            from app.wallet.services.compliance_engine import CountryComplianceConfig

            if CountryComplianceConfig.is_country_restricted(country_code):
                raise ValueError(
                    "Wallet services are not available for the verified country."
                )
            if CountryComplianceConfig.is_currency_restricted(country_code, currency):
                raise ValueError(
                    f"{currency} is not available for Wallet accounts in "
                    f"your verified country ({country_code}). Choose another accepted currency."
                )
        except ValueError:
            raise
        except Exception as exc:
            current_app.logger.exception(
                "Could not verify Wallet currency restrictions for country %s",
                country_code,
            )
            raise ValueError(
                "AFCON360 could not verify the currency rules for your country. "
                "Please try again later."
            ) from exc

    return currency


def resolve_home_currency(
    user: Any,
    requested_currency: Any = None,
) -> str:
    """Resolve the first Wallet currency from proven country + user preference.

    The verified country's local currency is a suggestion, not a forced choice.
    Users can choose any other owner-approved Wallet currency permitted in
    their jurisdiction. There is deliberately no USD fallback.
    """
    country = get_verified_wallet_country(user)
    if country is None:
        raise ValueError(
            "Verify your country of residence or registration before opening "
            "an AFCON360 Wallet."
        )

    country_code = country["country_code"]
    if requested_currency not in (None, ""):
        return validate_home_currency(requested_currency, country_code=country_code)

    local_currency = get_country_local_currency(country_code)
    if local_currency:
        try:
            return validate_home_currency(local_currency, country_code=country_code)
        except ValueError as exc:
            accepted = get_accepted_wallet_currencies()
            raise ValueError(
                f"The local currency {local_currency} is not currently available "
                "for Wallet opening in this market. Choose one of the accepted "
                f"currencies: {', '.join(accepted)}."
            ) from exc

    accepted = get_accepted_wallet_currencies()
    raise ValueError(
        "Choose your preferred Wallet currency from the accepted currencies: "
        + ", ".join(accepted)
    )


def get_user_home_currency(user: Any) -> Optional[str]:
    """Return the user's persisted Wallet denomination, or a verified suggestion.

    No Wallet account is created as a side effect. If the country is not proven
    or there is no acceptable local suggestion, return None so the calling
    surface can keep its transaction/fare currency rather than assume USD.
    """
    if user is None:
        return None

    try:
        from app.wallet.models.ledger import AccountModel, AccountOwnerType

        account = (
            AccountModel.query.filter_by(
                user_id=getattr(user, "id", None),
                owner_type=AccountOwnerType.USER,
            )
            .order_by(AccountModel.created_at.asc(), AccountModel.id.asc())
            .first()
        )
        if account is not None:
            return str(account.currency or "").strip().upper() or None
    except Exception:
        # Display/quote discovery must remain read-only and must not prevent
        # the user from seeing an otherwise available screen.
        current_app.logger.debug(
            "Could not resolve persisted Wallet home currency",
            exc_info=True,
        )

    try:
        return resolve_home_currency(user)
    except ValueError:
        return None


def get_wallet_currency_context(user: Any) -> Dict[str, Any]:
    """Read-only native-app payload for wallet onboarding currency selection."""
    accepted = get_accepted_wallet_currencies()
    country = get_verified_wallet_country(user)
    suggested = None
    if country:
        local = get_country_local_currency(country["country_code"])
        if local:
            try:
                suggested = validate_home_currency(
                    local,
                    country_code=country["country_code"],
                )
            except ValueError:
                suggested = None

    return {
        "accepted_currencies": accepted,
        "fx_base_currency": FX_BASE_CURRENCY,
        "country_verified": country is not None,
        "country": country,
        "suggested_currency": suggested,
        "requires_country_verification": country is None,
    }
