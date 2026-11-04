"""Driver-facing home-currency presentation for Transport offers.

This service only adds display fields. It never rewrites the signed fare,
request amount, Wallet invoice, driver earnings, or settlement denomination.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List

logger = logging.getLogger(__name__)


def enrich_driver_offers_with_home_currency(
    offers: Iterable[Dict[str, Any]],
    driver_profile: Any,
) -> List[Dict[str, Any]]:
    """Add indicative display amounts using the driver's existing Wallet currency.

    The base offer amount/currency remains authoritative. When FX is missing or
    stale, the original amount/currency is shown and offers still render.
    """
    rows = list(offers or [])
    if not rows or driver_profile is None:
        return rows

    try:
        user = getattr(driver_profile, "user", None)
        if user is None:
            return rows
        from app.wallet.services.home_currency_service import get_user_home_currency
        from app.wallet.services.display_fx_service import build_display_amount

        home_currency = get_user_home_currency(user)
    except Exception:
        logger.warning(
            "Could not resolve driver Wallet currency for offer display",
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
                    fare.get("amount"), base_currency, home_currency
                )
                item["fare_estimate"] = {
                    **fare,
                    **display_fields,
                    "home_currency": home_currency,
                    "display_label": "Indicative gross fare estimate",
                }
                item["home_currency"] = home_currency
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
