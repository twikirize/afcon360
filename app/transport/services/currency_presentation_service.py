"""Driver-facing operating-market currency presentation for Transport offers.

A declared operating country determines the display currency. Without one, the
original fare currency is retained. This adds display fields only; it never
rewrites the signed fare, request amount, Wallet invoice, earnings, or settlement.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List

logger = logging.getLogger(__name__)


def enrich_driver_offers_with_operating_currency(
    offers: Iterable[Dict[str, Any]],
    driver_profile: Any,
) -> List[Dict[str, Any]]:
    """Add indicative display amounts using the driver's operating-market currency.

    A declared, supported operating country controls the display currency.
    If no operating country is recorded, keep the original fare currency;
    never infer a driver's operating market from nationality or Wallet currency.
    Missing/stale FX also falls back to the original fare currency.
    """
    rows = list(offers or [])
    if not rows or driver_profile is None:
        return rows

    try:
        user = getattr(driver_profile, "user", None)
        if user is None:
            return rows
        from app.wallet.services.home_currency_service import home_currency_for_country
        from app.wallet.services.display_fx_service import build_display_amount

        metadata = getattr(driver_profile, "driver_metadata", None) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        operating_country_code = str(
            metadata.get("operating_country_code") or ""
        ).strip().upper() or None
        operating_currency = home_currency_for_country(operating_country_code)
        display_currency_basis = (
            "operating_country" if operating_currency else "fare_currency"
        )
    except Exception:
        logger.warning(
            "Could not resolve driver operating currency for offer display",
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
                display_currency = operating_currency or base_currency
                display_fields = build_display_amount(
                    fare.get("amount"), base_currency, display_currency
                )
                item["fare_estimate"] = {
                    **fare,
                    **display_fields,
                    "operating_currency": operating_currency,
                    "operating_country_code": operating_country_code,
                    "operating_country_verified": bool(
                        metadata.get("operating_country_verified")
                    ),
                    "display_currency_basis": display_currency_basis,
                    "display_label": (
                        "Indicative operating-market gross fare estimate"
                        if display_currency_basis == "operating_country"
                        else "Gross fare estimate — operating country not set; base fare currency shown"
                    ),
                }
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
