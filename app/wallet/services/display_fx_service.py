"""Indicative FX presentation for prices; never used for settlement.

The public ExchangeRate-API endpoint is used only to render approximate home-
currency equivalents. Wallet invoices, ledger entries and signed Transport
quotes retain their original denomination. A missing/stale feed falls back to
that original denomination instead of inventing a value.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
import threading
from typing import Any, Dict, Optional

import requests
from flask import current_app

logger = logging.getLogger(__name__)

RATE_SOURCE = "exchange_rate_api_open"
RATE_ATTRIBUTION_URL = "https://www.exchangerate-api.com"
DEFAULT_ENDPOINT = "https://open.er-api.com/v6/latest/{base}"
DEFAULT_MAX_AGE_SECONDS = 36 * 60 * 60
_CACHE_LOCK = threading.RLock()
_BASE_CACHE: Dict[str, Dict[str, Any]] = {}

# Currencies whose ISO 4217 minor-unit precision is zero.
_ZERO_DECIMAL = frozenset({"UGX", "RWF", "JPY", "KRW", "VND", "XAF", "XOF"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _digits(currency: str) -> int:
    return 0 if currency in _ZERO_DECIMAL else 2


def _round_display(value: Decimal, currency: str) -> Decimal:
    quantum = Decimal("1") if _digits(currency) == 0 else Decimal("0.01")
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _fetch_base_rates(base: str) -> Optional[Dict[str, Any]]:
    """Fetch one provider rate table, validate it, and cache in this worker."""
    now = _utcnow()
    with _CACHE_LOCK:
        cached = _BASE_CACHE.get(base)
        if cached and cached["cache_until"] > now:
            if cached.get("unavailable"):
                return None
            return cached

    endpoint = str(current_app.config.get(
        "WALLET_DISPLAY_FX_ENDPOINT", DEFAULT_ENDPOINT
    ) or DEFAULT_ENDPOINT)
    if "{base}" not in endpoint:
        logger.error("WALLET_DISPLAY_FX_ENDPOINT must contain the {base} placeholder")
        return None
    url = endpoint.format(base=base)

    try:
        response = requests.get(url, timeout=(1.5, 2.5))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("result") != "success":
            raise ValueError("FX provider response did not report success")
        if str(payload.get("base_code") or "").upper() != base:
            raise ValueError("FX provider returned an unexpected base currency")

        raw_rates = payload.get("rates")
        if not isinstance(raw_rates, dict):
            raise ValueError("FX provider response has no rates object")

        updated_unix = payload.get("time_last_update_unix")
        if isinstance(updated_unix, bool) or not isinstance(updated_unix, (int, float)):
            raise ValueError("FX provider update timestamp is invalid")
        updated_at = datetime.fromtimestamp(float(updated_unix), tz=timezone.utc)
        age_seconds = (now - updated_at).total_seconds()
        max_age = int(current_app.config.get(
            "WALLET_DISPLAY_FX_MAX_AGE_SECONDS", DEFAULT_MAX_AGE_SECONDS
        ))
        if age_seconds < -300 or age_seconds > max_age:
            raise ValueError("FX provider data is outside the allowed freshness window")

        rates: Dict[str, Decimal] = {}
        for raw_code, raw_rate in raw_rates.items():
            code = str(raw_code or "").upper()
            if len(code) != 3:
                continue
            try:
                rate = Decimal(str(raw_rate))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if rate.is_finite() and rate > 0:
                rates[code] = rate

        if base not in rates:
            rates[base] = Decimal("1")
        try:
            next_unix = payload.get("time_next_update_unix")
            next_update = (
                datetime.fromtimestamp(float(next_unix), tz=timezone.utc)
                if isinstance(next_unix, (int, float)) and not isinstance(next_unix, bool)
                else updated_at + timedelta(hours=24)
            )
        except (TypeError, ValueError, OverflowError, OSError):
            next_update = updated_at + timedelta(hours=24)
        cache_until = min(
            max(now + timedelta(minutes=5), next_update),
            now + timedelta(hours=24),
        )
        table = {
            "rates": rates,
            "updated_at": updated_at,
            "next_update": next_update,
            "cache_until": cache_until,
            "source": RATE_SOURCE,
        }
        with _CACHE_LOCK:
            _BASE_CACHE[base] = table
        return table
    except Exception as exc:
        # No stale or mock-rate fallback. This is display-only, so callers
        # safely show the signed fare denomination when conversion is absent.
        logger.warning("Indicative FX lookup unavailable for %s: %s", base, type(exc).__name__)
        # Avoid retrying the same failed provider request for every vehicle
        # option in one quote response. This is only a short negative cache;
        # no stale/estimated rate is stored or returned.
        with _CACHE_LOCK:
            _BASE_CACHE[base] = {
                "unavailable": True,
                "cache_until": now + timedelta(seconds=30),
            }
        return None


def get_display_rate(base_currency: str, display_currency: str) -> Optional[Dict[str, Any]]:
    """Return a fresh indicative rate for presentation, or None."""
    base = str(base_currency or "").strip().upper()
    quote = str(display_currency or "").strip().upper()
    if len(base) != 3 or len(quote) != 3:
        return None
    if base == quote:
        return {
            "rate": Decimal("1"),
            "source": "same_currency",
            "updated_at": None,
            "next_update": None,
            "attribution_url": None,
        }

    table = _fetch_base_rates(base)
    if not table:
        return None
    rate = table["rates"].get(quote)
    if rate is None or not rate.is_finite() or rate <= 0:
        return None
    return {
        "rate": rate,
        "source": table["source"],
        "updated_at": table["updated_at"],
        "next_update": table["next_update"],
        "attribution_url": RATE_ATTRIBUTION_URL,
    }


def build_display_amount(
    amount: Any,
    base_currency: str,
    preferred_currency: str,
) -> Dict[str, Any]:
    """Return presentation fields without changing the underlying amount.

    Amount/currency on invoices remain the base values. When fresh indicative
    FX exists, display_amount/display_currency are a second UI representation.
    """
    base = str(base_currency or "USD").strip().upper()
    preferred = str(preferred_currency or base).strip().upper()
    try:
        base_amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        base_amount = Decimal("0")
    if not base_amount.is_finite():
        base_amount = Decimal("0")

    fallback = {
        "display_amount": float(_round_display(base_amount, base)),
        "display_currency": base,
        "display_rate": None,
        "display_rate_at": None,
        "display_rate_source": None,
        "display_rate_attribution_url": None,
        "display_is_home_currency": base == preferred,
        "display_is_approximate": False,
    }
    rate_info = get_display_rate(base, preferred)
    if rate_info is None:
        return fallback

    converted = _round_display(base_amount * rate_info["rate"], preferred)
    return {
        "display_amount": float(converted),
        "display_currency": preferred,
        "display_rate": str(rate_info["rate"]),
        "display_rate_at": (
            rate_info["updated_at"].isoformat()
            if rate_info["updated_at"] else None
        ),
        "display_rate_source": rate_info["source"],
        "display_rate_attribution_url": rate_info["attribution_url"],
        "display_is_home_currency": True,
        "display_is_approximate": rate_info["source"] != "same_currency",
    }


def _clear_process_cache_for_tests() -> None:
    """Clear this worker's indicative-rate cache (test helper)."""
    with _CACHE_LOCK:
        _BASE_CACHE.clear()
