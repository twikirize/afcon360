"""
app/wallet/models/ledger.py
Double-entry ledger models - the source of truth for all balances.

RULE #1: NEVER update a balance column directly.
RULE #2: Balance = derived from ledger_entries at query time.
RULE #3: Every financial op = ONE transaction, zero compensation.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, String, Numeric, DateTime, ForeignKey, 
    CheckConstraint, Index, BigInteger
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
    """Account owner types - can be individual user, organisation, platform, or system."""
    USER = 'user'
    ORGANISATION = 'organisation'
    PLATFORM = 'platform'
    SYSTEM = 'system'


class AccountStatus(str, enum.Enum):
    """Account status lifecycle."""
    ACTIVE = 'active'
    FROZEN = 'frozen'
    CLOSED = 'closed'
    SUSPENDED = 'suspended'


class AccountType(str, enum.Enum):
    """Financial account classification."""
    REVENUE = 'revenue'
    ESCROW = 'escrow'
    OPERATIONS = 'operations'
    SETTLEMENT = 'settlement'
    RESERVE = 'reserve'
    USER_WALLET = 'user_wallet'
    ORG_WALLET = 'org_wallet'


class AccountModel(db.Model):
    """
    Financial account for a user, organisation, platform, or system.
    
    One account per owner (user, organisation, platform, or system) per currency.
    Balance is NEVER stored here - always derived from ledger_entries.
    """
    __tablename__ = 'accounts'
    __table_args__ = (
        Index('ix_accounts_user_id', 'user_id'),
        Index('ix_accounts_currency', 'currency'),
        Index('ix_accounts_owner_type', 'owner_type'),
        Index('ix_account_account_number', 'account_number', unique=True),
        Index('ix_account_type', 'account_type'),
        Index('ix_account_status', 'status'),
        Index('ix_account_platform', 'platform_account'),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # ── Identity ──
    account_number = Column(
        String(20),
        unique=True,
        nullable=True,
        index=True
    )
    account_name = Column(
        String(200),
        nullable=False,
        default=''
    )
    account_description = Column(
        String(500),
        nullable=True
    )
    
    # ── Ownership ──
    owner_type = Column(
        String(20),
        nullable=False,
        default=AccountOwnerType.USER
    )
    
    # Owner - references users.id
    user_id = Column(
        BigInteger,
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False
    )
    
    platform_account = Column(
        db.Boolean,
        default=False,
        nullable=False
    )
    
    # ── Account Type ──
    account_type = Column(
        String(30),
        nullable=False,
        default=AccountType.USER_WALLET
    )
    
    # ── Status ──
    status = Column(
        String(20),
        nullable=False,
        default=AccountStatus.ACTIVE
    )
    
    # ── Currency ──
    currency = Column(
        String(10),
        nullable=False,
        default='USD'
    )
    
    # ── Freeze ──
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
    frozen_by = Column(
        BigInteger,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True
    )
    
    # ── Volume tracking ──
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
    
    # ── Limits ──
    daily_volume_limit = Column(
        Numeric(20, 2),
        nullable=True
    )
    monthly_volume_limit = Column(
        Numeric(20, 2),
        nullable=True
    )
    per_transaction_limit = Column(
        Numeric(20, 2),
        nullable=True
    )
    require_dual_authorization = Column(
        db.Boolean,
        default=False,
        nullable=False
    )
    
    # ── Activation & Terms ──
    verified = Column(
        db.Boolean,
        nullable=False,
        default=False
    )
    terms_accepted_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # ── Financial reporting ──
    chart_of_accounts_code = Column(
        String(20),
        nullable=True
    )
    ifrs_category = Column(
        String(50),
        nullable=True
    )
    
    # ── Metadata ──
    extra_data = Column(
        JSONB,
        nullable=True,
        default=dict
    )
    
    # ── Lifecycle ──
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
        return f"<Account {self.account_number or self.id}: {self.account_name} ({self.status})>"

    @property
    def is_platform_account(self) -> bool:
        """Check if this is a platform-owned account."""
        return self.platform_account or self.owner_type == AccountOwnerType.PLATFORM

    @property
    def display_type(self) -> str:
        """Human-readable account type."""
        types = {
            AccountType.REVENUE.value: 'Revenue',
            AccountType.ESCROW.value: 'Escrow',
            AccountType.OPERATIONS.value: 'Operations',
            AccountType.SETTLEMENT.value: 'Settlement',
            AccountType.RESERVE.value: 'Reserve',
            AccountType.USER_WALLET.value: 'User Wallet',
            AccountType.ORG_WALLET.value: 'Organisation Wallet'
        }
        return types.get(self.account_type, self.account_type)

    def freeze(self, reason: str, frozen_by: int):
        """Freeze the account."""
        self.status = AccountStatus.FROZEN
        self.is_frozen = True
        self.frozen_at = datetime.now(timezone.utc)
        self.frozen_reason = reason
        self.frozen_by = frozen_by

    def unfreeze(self):
        """Unfreeze the account."""
        self.status = AccountStatus.ACTIVE
        self.is_frozen = False
        self.frozen_at = None
        self.frozen_reason = None
        self.frozen_by = None
