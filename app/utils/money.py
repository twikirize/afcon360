"""Money/currency utilities for the accommodation module."""

from decimal import Decimal, ROUND_HALF_UP


def money(value) -> Decimal:
    """Normalize values to two-decimal Decimal money amounts."""
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
