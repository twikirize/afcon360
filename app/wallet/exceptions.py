"""
app/wallet/exceptions.py
Custom exceptions for wallet module.

These exceptions are used across all wallet services for consistent error handling.
"""


class WalletError(Exception):
    """Base exception for all wallet-related errors."""
    pass


class WalletNotFoundError(WalletError):
    """Raised when a wallet does not exist for a user/organisation."""

    def __init__(self, user_id: int = None, org_id: int = None, wallet_ref: str = None):
        self.user_id = user_id
        self.org_id = org_id
        self.wallet_ref = wallet_ref
        identifier = wallet_ref or f"user_id={user_id}" or f"org_id={org_id}"
        super().__init__(f"Wallet not found: {identifier}")


class InsufficientBalanceError(WalletError):
    """Raised when a wallet has insufficient funds for an operation."""

    def __init__(self, currency: str, required: float, available: float):
        self.currency = currency
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient balance in {currency}: required {required}, available {available}"
        )


class DuplicateTransactionError(WalletError):
    """Raised when a transaction with the same idempotency key already exists."""

    def __init__(self, idempotency_key: str, existing_transaction_id: str):
        self.idempotency_key = idempotency_key
        self.existing_transaction_id = existing_transaction_id
        super().__init__(f"Duplicate transaction: {idempotency_key}")


class WalletFrozenError(WalletError):
    """Raised when an operation is attempted on a frozen wallet."""

    def __init__(self, wallet_ref: str, reason: str = None):
        self.wallet_ref = wallet_ref
        self.reason = reason
        message = f"Wallet {wallet_ref} is frozen"
        if reason:
            message += f": {reason}"
        super().__init__(message)


class LimitExceededError(WalletError):
    """Raised when a transaction exceeds daily/monthly limits."""

    def __init__(self, limit_type: str, currency: str, limit: float, current: float):
        self.limit_type = limit_type  # daily, monthly, per_transaction
        self.currency = currency
        self.limit = limit
        self.current = current
        super().__init__(
            f"{limit_type.title()} limit exceeded for {currency}: {current}/{limit}"
        )


class UnsupportedCurrencyError(WalletError):
    """Raised when an unsupported currency is used."""

    def __init__(self, currency: str, supported: list):
        self.currency = currency
        self.supported = supported
        super().__init__(f"Unsupported currency: {currency}. Supported: {supported}")


class ConversionError(WalletError):
    """Raised when currency conversion fails."""

    def __init__(self, from_currency: str, to_currency: str, reason: str = None):
        self.from_currency = from_currency
        self.to_currency = to_currency
        self.reason = reason
        message = f"Conversion failed: {from_currency} → {to_currency}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)


class TransactionNotFoundError(WalletError):
    """Raised when a transaction reference is not found."""

    def __init__(self, transaction_ref: str):
        self.transaction_ref = transaction_ref
        super().__init__(f"Transaction not found: {transaction_ref}")


class ComplianceBlockError(WalletError):
    """Raised when a transaction is blocked by compliance rules."""

    def __init__(self, reason: str, rule_name: str = None):
        self.reason = reason
        self.rule_name = rule_name
        message = f"Transaction blocked by compliance: {reason}"
        super().__init__(message)