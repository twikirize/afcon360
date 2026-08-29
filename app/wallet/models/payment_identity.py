"""
app/wallet/models/payment_identity.py

Payment Identity — a SEPARATE concept from Account.

A Payment Identity identifies HOW another party can address a person/business
for payment. It is NOT the account itself; it RESOLVES to an eligible account.

Examples:
    PHONE         +256700123456
    EMAIL         alice@example.com
    AFCON360_ID   AF7K29XQ
    MERCHANT_CODE AKL123

Ownership model: the project's canonical ownership uses `user_id` (BigInteger,
FK -> users.id) on AccountModel for ALL owner types (user/organisation/
platform/system). PaymentIdentity follows the same convention with `owner_id`.

This model deliberately does NOT add phone/email/merchant_code columns onto
Account — those belong here as addressable identities.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Boolean, BigInteger, ForeignKey, UniqueConstraint, Index,
    DateTime,
)
from sqlalchemy.dialects.postgresql import UUID

from app.extensions import db


class PaymentIdentityType(str):
    """Payment identity types (string constants, not an enum to stay flexible)."""
    PHONE = 'PHONE'
    EMAIL = 'EMAIL'
    AFCON360_ID = 'AFCON360_ID'
    MERCHANT_CODE = 'MERCHANT_CODE'


class PaymentIdentityModel(db.Model):
    """
    Addressable payment identity for a user/organisation/platform/system.

    One verified/active identity per (identity_type, normalized_value).
    Resolves to an eligible Account via `account_id`.
    """

    __tablename__ = 'payment_identities'

    __table_args__ = (
        # Normalization guarantees a single canonical representation per type.
        UniqueConstraint(
            'identity_type', 'normalized_value',
            name='uq_payment_identity_type_normalized'
        ),
        Index('ix_payment_identity_owner', 'owner_type', 'owner_id'),
        Index('ix_payment_identity_account', 'account_id'),
        Index('ix_payment_identity_normalized', 'normalized_value'),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # ── Identity ──
    identity_type = Column(
        String(20),
        nullable=False,
    )
    identity_value = Column(
        String(320),
        nullable=False,
    )
    normalized_value = Column(
        String(320),
        nullable=False,
    )

    # ── Ownership (same convention as AccountModel: owner_id = users.id FK) ──
    owner_type = Column(
        String(20),
        nullable=False,
    )
    owner_id = Column(
        BigInteger,
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
    )

    # ── Resolution target ──
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey('accounts.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
    )

    # ── State ──
    is_verified = Column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_primary = Column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    # ── Lifecycle ──
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return (
            f"<PaymentIdentity {self.identity_type}:{self.normalized_value} "
            f"owner={self.owner_type}:{self.owner_id} verified={self.is_verified}>"
        )
