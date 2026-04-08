"""
app/wallet/validators.py
Input validation for wallet operations.
"""

from decimal import Decimal, InvalidOperation
from typing import Optional
from flask import request


def parse_amount(value) -> Optional[Decimal]:
    """
    Parse amount from various input types.

    Args:
        value: String, int, float, or Decimal

    Returns:
        Decimal amount or None if invalid
    """
    try:
        if value is None:
            return None
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def validate_amount(amount: Decimal, min_value: Decimal = Decimal("0.01")) -> bool:
    """
    Validate amount is positive and meets minimum.

    Args:
        amount: Amount to validate
        min_value: Minimum allowed amount

    Returns:
        True if valid, False otherwise
    """
    return amount is not None and amount >= min_value


def validate_currency(currency: str, supported_currencies: list) -> bool:
    """
    Validate currency is supported.

    Args:
        currency: Currency code to validate
        supported_currencies: List of supported currency codes

    Returns:
        True if supported, False otherwise
    """
    return currency and currency.upper() in supported_currencies


def extract_idempotency_key() -> Optional[str]:
    """
    Extract idempotency key from request.

    Priority:
    1. X-Idempotency-Key header
    2. idempotency_key in JSON body
    3. client_request_id in JSON body (legacy)

    Returns:
        Idempotency key or None
    """
    # Check header first
    key = request.headers.get('X-Idempotency-Key')
    if key:
        return key

    # Check JSON body
    if request.is_json:
        data = request.get_json(silent=True) or {}
        return data.get('idempotency_key') or data.get('client_request_id')

    return None


class DepositRequest:
    """Validator for deposit requests."""

    @staticmethod
    def validate(data: dict) -> tuple[Optional[dict], Optional[str]]:
        """
        Validate deposit request data.

        Returns:
            Tuple of (validated_data, error_message)
        """
        amount = parse_amount(data.get('amount'))
        if not validate_amount(amount):
            return None, "Invalid amount. Must be greater than zero."

        currency = data.get('currency', 'USD').upper()

        return {
            'amount': amount,
            'currency': currency,
            'idempotency_key': data.get('idempotency_key') or data.get('client_request_id'),
            'metadata': data.get('metadata', {})
        }, None


class WithdrawRequest:
    """Validator for withdrawal requests."""

    @staticmethod
    def validate(data: dict) -> tuple[Optional[dict], Optional[str]]:
        amount = parse_amount(data.get('amount'))
        if not validate_amount(amount):
            return None, "Invalid amount. Must be greater than zero."

        currency = data.get('currency', '').upper()
        if not currency:
            return None, "Currency is required."

        return {
            'amount': amount,
            'currency': currency,
            'idempotency_key': data.get('idempotency_key') or data.get('client_request_id'),
            'metadata': data.get('metadata', {})
        }, None


class TransferRequest:
    """Validator for transfer requests."""

    @staticmethod
    def validate(data: dict) -> tuple[Optional[dict], Optional[str]]:
        amount = parse_amount(data.get('amount'))
        if not validate_amount(amount):
            return None, "Invalid amount. Must be greater than zero."

        to_user_id = data.get('to_user_id') or data.get('receiver_user_id')
        if not to_user_id:
            return None, "Recipient user ID is required."

        currency = data.get('currency', '').upper()
        if not currency:
            return None, "Currency is required."

        return {
            'amount': amount,
            'to_user_id': int(to_user_id),
            'currency': currency,
            'idempotency_key': data.get('idempotency_key') or data.get('client_request_id'),
            'note': data.get('note'),
            'metadata': data.get('metadata', {})
        }, None
