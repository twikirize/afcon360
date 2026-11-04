"""Driver-facing operating-market currency presentation for Transport offers.

The declared driver operating country is preferred for offer display. The
persisted Wallet home currency is the fallback for legacy profiles without an
operating-country declaration. This only adds display fields: it never rewrites
the signed fare, request amount, Wallet invoice, earnings, or settlement.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List

logger = logging.getLogger(__name__)


def enrich_driver_offers_with_home_currency(
    offers: Iterable[Dict[str, Any]],
    driver_profile: Any,
) -> List[Dict[str, Any]]:
    """Add indicative display amounts using the driver's operating-market currency.

    The driver's persisted Wallet home currency is used only when no supported
    operating country is declared. The base offer amount/currency remains
    authoritative. Missing/stale FX falls back to the original currency.
    """
    rows = list(offers or [])
    if not rows or driver_profile is None:
        return rows

    try:
        user = getattr(driver_profile, "user", None)
        if user is None:
            return rows
        from app.wallet.services.home_currency_service import (
            get_user_home_currency,
            home_currency_for_country,
        )
        from app.wallet.services.display_fx_service import build_display_amount

        wallet_home_currency = get_user_home_currency(user)
        metadata = getattr(driver_profile, "driver_metadata", None) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        operating_country_code = str(
            metadata.get("operating_country_code") or ""
        ).strip().upper() or None
        operating_currency = home_currency_for_country(operating_country_code)
        display_currency = operating_currency or wallet_home_currency
        display_currency_basis = (
            "operating_country" if operating_currency else "wallet_home_currency"
        )
    except Exception:
        logger.warning(
            "Could not resolve driver operating/Wallet currency for offer display",
            exc_info=True,
        )
        return rows

    enriched: List[Dict[str, Any]] = []
    for offer in rows:
        item = dict(offer or {})
        fare = item.get("fare_estimate")
        if isinstance(fare, dict) and fare.get("amount") is not None:
            base_currency = str(fare.get("currency") or "USD").upper()
            try:
                display_fields = build_display_amount(
                    fare.get("amount"), base_currency, display_currency
                )
                item["fare_estimate"] = {
                    **fare,
                    **display_fields,
                    "home_currency": display_currency,
                    "wallet_home_currency": wallet_home_currency,
                    "operating_country_code": operating_country_code,
                    "display_currency_basis": display_currency_basis,
                    "display_label": (
                        "Indicative operating-market gross fare estimate"
                        if display_currency_basis == "operating_country"
                        else "Indicative Wallet-home gross fare estimate"
                    ),
                }
                item["home_currency"] = wallet_home_currency
                item["display_currency_basis"] = display_currency_basis
                item["operating_country_code"] = operating_country_code
            except Exception:
                # The offer itself must not be lost because a display-only
                # conversion failed; preserve the untouched base fare.
                logger.warning(
                    "Could not convert driver offer display currency for %s",
                    item.get("booking_reference"),
                    exc_info=True,
                )
        enriched.append(item)
    return enriched
