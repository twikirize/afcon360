"""
app/wallet/models/ledger.py
Double-entry ledger models - the source of truth for all balances.

RULE #1: NEVER update a balance column directly.
RULE #2: Balance = derived from ledger_entries at query time.
RULE #3: Every financial op = ONE transaction, zero compensation.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, String, Numeric, DateTime, ForeignKey, 
    CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.extensions import db
import enum


class EntryType(str, enum.Enum):
    """Ledger entry types - double entry bookkeeping."""
    DEBIT = 'DEBIT'
    CREDIT = 'CREDIT'


class LedgerEntryModel(db.Model):
    """
    Immutable double-entry ledger record.
    
    Every financial transaction creates at least 2 ledger entries (debit + credit).
    Balance is ALWAYS derived from these entries, never stored.
    """
    __tablename__ = 'ledger_entries'
    __table_args__ = (
        CheckConstraint('amount > 0', name='ck_ledger_amount_positive'),
        CheckConstraint(
            "entry_type IN ('DEBIT', 'CREDIT')", 
            name='ck_ledger_entry_type_valid'
        ),
        Index('ix_ledger_account_id', 'account_id'),
        Index('ix_ledger_transaction_id', 'transaction_id'),
        Index('ix_ledger_currency', 'currency'),
        Index('ix_ledger_created_at', 'created_at'),
        # Composite index for balance queries
        Index('ix_ledger_account_currency', 'account_id', 'currency'),
    )

    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Foreign keys
    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey('transactions.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey('accounts.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # Entry details
    entry_type = Column(
        String(10),
        nullable=False
    )
    
    amount = Column(
        Numeric(18, 6),
        nullable=False
    )
    
    currency = Column(
        String(10),
        nullable=False
    )
    
    # Audit trail
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    
    # Optional metadata for this specific leg
    meta = Column(JSONB, nullable=True)
    
    def __repr__(self):
        return (
            f"<LedgerEntry {self.id} {self.entry_type} "
            f"{self.amount} {self.currency}>"
        )


class AccountOwnerType(str, enum.Enum):
    """Account owner types - can be individual user or organisation."""
    USER = 'user'
    ORGANISATION = 'organisation'


class AccountModel(db.Model):
    """
    Financial account for a user or organisation.
    
    One account per owner (user or organisation) per currency (or one multi-currency account).
    Balance is NEVER stored here - always derived from ledger_entries.
    """
    __tablename__ = 'accounts'
    __table_args__ = (
        # Ensure one account per owner per currency
        Index('ix_accounts_user_id', 'user_id'),
        Index('ix_accounts_currency', 'currency'),
        Index('ix_accounts_user_currency', 'user_id', 'currency', unique=True),
        Index('ix_accounts_owner_type', 'owner_type'),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Owner type - distinguishes between user and organisation accounts
    owner_type = Column(
        String(20),
        nullable=False,
        default=AccountOwnerType.USER
    )
    
    # Owner - one account per user or organisation
    # For users: user_id references users.id
    # For organisations: user_id references organisations.id (BIGINT)
    user_id = Column(
        db.BigInteger,
        nullable=False,
        unique=True  # One account per owner for now
    )
    
    # Currency this account operates in
    currency = Column(
        String(10),
        nullable=False,
        default='USD'
    )
    
    # Account status
    is_frozen = Column(
        db.Boolean,
        nullable=False,
        default=False
    )
    
    frozen_reason = Column(
        db.Text,
        nullable=True
    )
    
    frozen_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Daily/monthly limits tracking
    daily_volume = Column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal('0')
    )
    
    daily_volume_reset_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    
    monthly_volume = Column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal('0')
    )
    
    monthly_volume_reset_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Activation status
    verified = Column(
        db.Boolean,
        nullable=False,
        default=False
    )
    
    # Terms acceptance
    terms_accepted_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Lifecycle
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
    def __repr__(self):
        return f"<Account {self.id} user={self.user_id} currency={self.currency}>"
