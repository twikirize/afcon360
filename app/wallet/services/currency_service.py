"""
app/wallet/services/currency_service.py
Currency conversion service with caching and audit.
"""

from decimal import Decimal, ROUND_DOWN, getcontext
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import threading
from flask import current_app

# Set decimal precision for financial calculations
getcontext().prec = 28
MONEY_QUANT = Decimal("0.01")


class CurrencyService:
    """
    Currency conversion service.

    Features:
    - Cached exchange rates (Redis/In-memory)
    - Audit trail for rate usage
    - Support for direct and cross rates
    - Fee calculation
    """

    def __init__(self):
        self._cache: Dict[str, Tuple[Decimal, datetime]] = {}
        self._cache_lock = threading.Lock()

    def _get_cache_key(self, from_currency: str, to_currency: str) -> str:
        """Generate cache key for rate pair."""
        return f"{from_currency.upper()}:{to_currency.upper()}"

    def _get_rate_from_provider(self, from_currency: str, to_currency: str) -> Optional[Decimal]:
        """
        Get exchange rate from configured provider.

        TODO: Implement actual provider integration (OpenExchangeRates, Fixer.io, etc.)
        For now, uses config fallback.
        """
        if from_currency == to_currency:
            return Decimal("1.00")

        # Check config for manual rates
        cfg = current_app.config.get("FX_RATES", {})
        try:
            rate = cfg[from_currency][to_currency]
            return Decimal(str(rate))
        except (KeyError, TypeError, ValueError):
            pass

        # Try USD as base currency (cross rate)
        try:
            rate_to_usd = self._get_rate_from_provider(from_currency, "USD")
            rate_from_usd = self._get_rate_from_provider("USD", to_currency)
            if rate_to_usd and rate_from_usd:
                return rate_to_usd * rate_from_usd
        except Exception:
            pass

        # Log warning and return None
        current_app.logger.warning(f"No FX rate available for {from_currency} -> {to_currency}")
        return None

    def get_rate(self, from_currency: str, to_currency: str, use_cache: bool = True) -> Optional[Decimal]:
        """
        Get exchange rate between two currencies.

        Args:
            from_currency: Source currency code (e.g., "USD")
            to_currency: Target currency code (e.g., "UGX")
            use_cache: If True, use cached rate (default True)

        Returns:
            Decimal rate or None if unavailable
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency == to_currency:
            return Decimal("1.00")

        cache_key = self._get_cache_key(from_currency, to_currency)
        ttl = current_app.config.get("FX_CACHE_TTL_SECONDS", 300)

        # Check cache
        if use_cache:
            with self._cache_lock:
                entry = self._cache.get(cache_key)
                if entry:
                    rate, timestamp = entry
                    if datetime.utcnow() - timestamp < timedelta(seconds=ttl):
                        return rate

        # Get from provider
        rate = self._get_rate_from_provider(from_currency, to_currency)

        if rate is not None:
            # Cache the rate
            with self._cache_lock:
                self._cache[cache_key] = (rate, datetime.utcnow())

        return rate

    def convert(
            self,
            amount: Decimal,
            from_currency: str,
            to_currency: str,
            apply_fee: bool = True
    ) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Convert amount from one currency to another.

        Args:
            amount: Amount to convert
            from_currency: Source currency
            to_currency: Target currency
            apply_fee: If True, apply conversion fee

        Returns:
            Tuple of (converted_amount, rate_used, fee_amount)
        """
        amount = Decimal(str(amount))

        if amount == Decimal("0"):
            return Decimal("0"), Decimal("1"), Decimal("0")

        # Get exchange rate
        rate = self.get_rate(from_currency, to_currency)
        if rate is None:
            raise ValueError(f"No exchange rate available for {from_currency} -> {to_currency}")

        # Calculate converted amount
        converted = (amount * rate).quantize(MONEY_QUANT, rounding=ROUND_DOWN)

        # Calculate fee
        fee = Decimal("0")
        if apply_fee:
            fee_pct = current_app.config.get("CONVERSION_FEE_PCT", Decimal("0.02"))
            fee = (converted * fee_pct).quantize(MONEY_QUANT, rounding=ROUND_DOWN)
            converted = (converted - fee).quantize(MONEY_QUANT, rounding=ROUND_DOWN)

        return converted, rate, fee

    def clear_cache(self) -> None:
        """Clear all cached rates."""
        with self._cache_lock:
            self._cache.clear()

    def get_supported_currencies(self) -> list:
        """Get list of supported currencies."""
        return current_app.config.get("SUPPORTED_CURRENCIES", ["USD", "UGX", "KES", "TZS", "NGN", "EUR", "CFA"])

    def validate_currency(self, currency: str) -> bool:
        """Check if currency is supported."""
        return currency.upper() in self.get_supported_currencies()
