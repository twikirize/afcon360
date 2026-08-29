"""
app/wallet/services/payment_identity_service.py

Normalization, registration, and recipient resolution for Payment Identities.

This is the single canonical service for:
  1. normalizing a payment identifier (phone/email/AFCON360_ID/merchant_code)
  2. registering a payment identity for an owner/account
  3. resolving a recipient from a raw identifier (for transfers)

Security boundary (per frozen architecture):
  - Resolution answers "WHO IS THIS?" only.
  - It does NOT grant permission to debit any account.
  - Authorization/debit permission remains in wallet_service.transfer().
"""

import re
from typing import Optional, Dict, Any

from app.extensions import db
from app.wallet.models.payment_identity import (
    PaymentIdentityModel,
    PaymentIdentityType,
)
from app.wallet.models.ledger import AccountModel, AccountOwnerType, AccountStatus


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

_PHONE_STRIP = re.compile(r"[^\d+]")
_UG_PHONE_PREFIXES = ('070', '071', '072', '073', '074', '075', '076', '077', '078', '079')


def normalize_phone(raw: str) -> str:
    """
    Normalize a phone number to Uganda E.164 form: 2567XXXXXXXX.

    Handles:
        0700123456   -> 256700123456
        +256700123456 -> 256700123456
        256700123456  -> 256700123456
        0700 123 456  -> 256700123456
    """
    if not raw:
        return ''
    digits = _PHONE_STRIP.sub('', raw)
    # Keep a leading + only for detection, then strip it.
    has_plus = digits.startswith('+')
    digits = digits.lstrip('+')

    if digits.startswith('256') and len(digits) == 12:
        return '256' + digits[3:]
    if digits.startswith('0') and len(digits) == 10:
        return '256' + digits[1:]
    if has_plus and len(digits) == 12 and digits.startswith('256'):
        return digits
    # Fallback: return digits as-is (may be international). Strip leading 00.
    if digits.startswith('00'):
        digits = digits[2:]
    return digits


def normalize_email(raw: str) -> str:
    """Lowercase and strip an email."""
    if not raw:
        return ''
    return raw.strip().lower()


def normalize_afcon360_id(raw: str) -> str:
    """Uppercase, strip whitespace."""
    if not raw:
        return ''
    return raw.strip().upper()


def normalize_merchant_code(raw: str) -> str:
    """Uppercase, strip whitespace only (preserve hyphens)."""
    if not raw:
        return ''
    return re.sub(r"\s", "", raw).upper()


_NORMALIZERS = {
    PaymentIdentityType.PHONE: normalize_phone,
    PaymentIdentityType.EMAIL: normalize_email,
    PaymentIdentityType.AFCON360_ID: normalize_afcon360_id,
    PaymentIdentityType.MERCHANT_CODE: normalize_merchant_code,
}


def normalize_identity(identity_type: str, value: str) -> str:
    """Normalize a value for the given identity type."""
    normalizer = _NORMALIZERS.get(identity_type)
    if normalizer is None:
        raise ValueError(f"Unsupported identity type: {identity_type}")
    return normalizer(value)


def detect_identity_type(value: str) -> Optional[str]:
    """
    Best-effort detection of identity type from a raw identifier.

    Used by resolve_payment_recipient() so callers can pass a raw string
    without declaring the type.
    """
    if not value:
        return None
    v = value.strip()
    # AFCON360 ID: specific format "AFC-" followed by digits.
    if re.fullmatch(r"AFC-\d+", v):
        return PaymentIdentityType.AFCON360_ID
    # Merchant code: 2-5 letters, optional hyphen + 2-6 alnum (e.g. MTN-UG, AKL123).
    if re.fullmatch(r"[A-Z]{2,5}(?:-[A-Z0-9]{2,6}|[A-Z0-9]{2,6})", v):
        return PaymentIdentityType.MERCHANT_CODE
    if '@' in v and '.' in v.split('@')[-1]:
        return PaymentIdentityType.EMAIL
    if _PHONE_STRIP.sub('', v).lstrip('+').startswith(('0', '256')):
        return PaymentIdentityType.PHONE
    # Generic alphanumeric (no @, no leading +): treat as AFCON360_ID.
    if re.fullmatch(r"[A-Za-z0-9]{3,12}", v) and not v.isdigit():
        return PaymentIdentityType.AFCON360_ID
    return None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class PaymentIdentityService:
    """Register and manage payment identities."""

    @staticmethod
    def register(
        identity_type: str,
        raw_value: str,
        owner_type: str,
        owner_id: int,
        account_id: Optional[str] = None,
        is_verified: bool = False,
        is_primary: bool = False,
    ) -> PaymentIdentityModel:
        """
        Register (or update) a payment identity for an owner.

        Args:
            identity_type: PHONE/EMAIL/AFCON360_ID/MERCHANT_CODE
            raw_value: Raw user-supplied value
            owner_type: USER/ORGANISATION/PLATFORM/SYSTEM
            owner_id: Internal owner id (users.id convention)
            account_id: Target account UUID (optional at registration)
            is_verified: Verification state
            is_primary: Primary identity flag

        Returns:
            PaymentIdentityModel

        Raises:
            ValueError: On invalid type or empty value
        """
        if identity_type not in _NORMALIZERS:
            raise ValueError(f"Unsupported identity type: {identity_type}")
        normalized = normalize_identity(identity_type, raw_value)
        if not normalized:
            raise ValueError("Payment identity value is required")

        existing = PaymentIdentityModel.query.filter_by(
            identity_type=identity_type,
            normalized_value=normalized,
        ).first()

        if existing:
            # Update in place (idempotent registration / claim flow).
            existing.owner_type = owner_type
            existing.owner_id = owner_id
            if account_id is not None:
                existing.account_id = account_id
            existing.is_verified = is_verified
            existing.is_active = True
            if is_primary:
                existing.is_primary = True
            db.session.add(existing)
            return existing

        identity = PaymentIdentityModel(
            identity_type=identity_type,
            identity_value=raw_value,
            normalized_value=normalized,
            owner_type=owner_type,
            owner_id=owner_id,
            account_id=account_id,
            is_verified=is_verified,
            is_primary=is_primary,
            is_active=True,
        )
        db.session.add(identity)
        db.session.flush()
        return identity

    @staticmethod
    def set_verified(identity_id, verified: bool = True):
        identity = db.session.get(PaymentIdentityModel, identity_id)
        if identity:
            identity.is_verified = verified
            db.session.add(identity)
        return identity


# ---------------------------------------------------------------------------
# Recipient resolution
# ---------------------------------------------------------------------------

def _mask_phone(normalized: str) -> str:
    """Mask a normalized Uganda phone: 256700123456 -> +256 *** ***456."""
    if len(normalized) >= 9:
        return f"+{normalized[:3]} *** ***{normalized[-3:]}"
    return normalized


def _mask_email(normalized: str) -> str:
    """Mask an email: alice@example.com -> a***@example.com."""
    if '@' in normalized:
        local, domain = normalized.split('@', 1)
        if local:
            return f"{local[0]}***@{domain}"
    return normalized


def resolve_payment_recipient(identifier: str) -> Dict[str, Any]:
    """
    Resolve a payment recipient from a raw identifier.

    Performs, in order:
      1. normalize the identifier
      2. determine identity type
      3. find the verified/active PaymentIdentity
      4. resolve owner
      5. resolve eligible destination account
      6. validate account status

    Returns a safe representation (never exposes internal ids/sensitive data).
    If not found or not trusted, returns {'found': False, ...}.
    """
    if not identifier:
        return {"found": False, "reason": "empty_identifier"}

    identity_type = detect_identity_type(identifier)
    if identity_type is None:
        return {"found": False, "reason": "unknown_identifier_type"}

    normalized = normalize_identity(identity_type, identifier)

    identity = PaymentIdentityModel.query.filter_by(
        identity_type=identity_type,
        normalized_value=normalized,
        is_active=True,
    ).first()

    if not identity:
        return {"found": False, "reason": "no_identity"}

    # Address resolution only — NOT authorization.
    if not identity.is_verified:
        return {
            "found": True,
            "trusted": False,
            "reason": "identity_not_verified",
            "identity_type": identity_type,
            "masked_identifier": _mask(identity_type, normalized),
        }

    account = None
    if identity.account_id:
        account = db.session.get(AccountModel, identity.account_id)

    if account is None:
        # Fall back to canonical account lookup by owner.
        account = AccountModel.query.filter_by(
            user_id=identity.owner_id,
            owner_type=identity.owner_type,
            currency='UGX',
        ).first()

    if account is None:
        return {
            "found": True,
            "trusted": False,
            "reason": "no_account",
            "identity_type": identity_type,
            "masked_identifier": _mask(identity_type, normalized),
        }

    if account.status != AccountStatus.ACTIVE:
        return {
            "found": True,
            "trusted": False,
            "reason": "account_not_active",
            "identity_type": identity_type,
            "masked_identifier": _mask(identity_type, normalized),
            "account_number": account.account_number,
            "status": account.status,
        }

    display_name = _resolve_display_name(identity.owner_type, identity.owner_id)

    return {
        "found": True,
        "trusted": True,
        "recipient_type": identity.owner_type.lower(),
        "display_name": display_name,
        "identity_type": identity_type,
        "masked_identifier": _mask(identity_type, normalized),
        "account_number": account.account_number,
        "currency": account.currency,
        "status": account.status,
        # Explicitly NOT returning: user.id, account.id (UUID), KYC docs, etc.
    }


def _mask(identity_type: str, normalized: str) -> str:
    if identity_type == PaymentIdentityType.PHONE:
        return _mask_phone(normalized)
    if identity_type == PaymentIdentityType.EMAIL:
        return _mask_email(normalized)
    return normalized


def _resolve_display_name(owner_type: str, owner_id: int) -> str:
    """Best-effort display name without leaking sensitive data."""
    try:
        if owner_type == AccountOwnerType.USER.value:
            from app.identity.models.user import User
            user = db.session.get(User, owner_id)
            if user:
                return user.username or user.email or f"User {owner_id}"
        elif owner_type == AccountOwnerType.ORGANISATION.value:
            from app.identity.models.organisation import Organisation
            org = db.session.get(Organisation, owner_id)
            if org:
                return org.legal_name or f"Organisation {owner_id}"
    except Exception:
        pass
    return f"{owner_type.title()} {owner_id}"
