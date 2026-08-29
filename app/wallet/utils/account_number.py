"""
app/wallet/utils/account_number.py

Account number generation for AFCON360 financial accounts.

Account numbers are STABLE, human/business-facing financial identifiers.
They MUST NOT be derived from internal database IDs (user_id, org_id, pk).

Format (per frozen Payment Identity Architecture):
    USER         ACC-UGX-7F42K9
    ORGANISATION ORG-UGX-92KD81
    PLATFORM     PLT-REV-UGX-0001   (type abbreviation)
    SYSTEM       SYS-ESC-UGX-0001   (type abbreviation)

The random/sequential component is generated independently of any internal
identifier so account numbers survive internal DB changes and never leak IDs.
"""

import secrets
import string
from typing import Optional

from app.wallet.models.ledger import AccountOwnerType, AccountType

_ALPHANUM = string.ascii_uppercase + string.digits

# Owner-type prefix
_OWNER_PREFIX = {
    AccountOwnerType.USER.value: "ACC",
    AccountOwnerType.ORGANISATION.value: "ORG",
    AccountOwnerType.PLATFORM.value: "PLT",
    AccountOwnerType.SYSTEM.value: "SYS",
}

# Account-type abbreviation used inside platform/system numbers
_TYPE_ABBR = {
    AccountType.REVENUE.value: "REV",
    AccountType.ESCROW.value: "ESC",
    AccountType.OPERATIONS.value: "OPS",
    AccountType.SETTLEMENT.value: "SET",
    AccountType.RESERVE.value: "RSV",
    AccountType.USER_WALLET.value: "WAL",
    AccountType.ORG_WALLET.value: "WAL",
}


def _random_component(length: int = 6) -> str:
    """Cryptographically-random uppercase alphanumeric component."""
    return "".join(secrets.choice(_ALPHANUM) for _ in range(length))


def generate_account_number(
    owner_type: str,
    currency: str,
    account_type: Optional[str] = None,
) -> str:
    """
    Generate a unique account number for an account.

    Args:
        owner_type: AccountOwnerType value (user/organisation/platform/system)
        currency: ISO currency code (e.g. UGX)
        account_type: AccountType value (optional, used for PLT/SYS naming)

    Returns:
        Account number string, e.g. ACC-UGX-7F42K9
    """
    prefix = _OWNER_PREFIX.get(owner_type, "ACC")
    cur = (currency or "UGX").upper()

    if owner_type in (AccountOwnerType.PLATFORM.value, AccountOwnerType.SYSTEM.value):
        abbr = _TYPE_ABBR.get(account_type or "", "GEN")
        return f"{prefix}-{abbr}-{cur}-{_random_component(4)}"

    _ = account_type  # reserved for future use

    return f"{prefix}-{cur}-{_random_component(6)}"


def is_valid_account_number(value: str) -> bool:
    """Light structural validation for an account number."""
    if not value or not isinstance(value, str):
        return False
    parts = value.split("-")
    if len(parts) not in (3, 4):
        return False
    return all(p.isalnum() and p.isupper() for p in parts)
