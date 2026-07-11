# app/wallet/models.py
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, ForeignKey, JSON,
    Index, UniqueConstraint, Text, Float, Integer, Enum as SQLEnum
)
from sqlalchemy.orm import relationship, validates
from app.extensions import db
from app.models.base import ProtectedModel
import enum


class WalletType(enum.Enum):
    """Wallet types for modular deployment"""
    PERSONAL = "personal"
    BUSINESS = "business"
    MERCHANT = "merchant"
    SAVINGS = "savings"
    INVESTMENT = "investment"


class WalletStatus(enum.Enum):
    """Wallet status types"""
    ACTIVE = "active"
    FROZEN = "frozen"
    SUSPENDED = "suspended"
    CLOSED = "closed"
    LIMITED = "limited"


class TransactionCategory(enum.Enum):
    """Transaction categories"""
    TRANSFER = "transfer"
    PAYMENT = "payment"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FEE = "fee"
    REFUND = "refund"
    DISPUTE = "dispute"


class Wallet(ProtectedModel):
    """Core wallet model - can be shipped as separate product"""
    __tablename__ = "wallets"
    
    id = Column(BigInteger, primary_key=True)
    public_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    organisation_id = Column(BigInteger, ForeignKey('organisations.id'), nullable=True, index=True)
    
    # Wallet identification
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    wallet_type = Column(SQLEnum(WalletType), nullable=False, index=True)
    currency = Column(String(3), nullable=False, default="UGX", index=True)
    
    # Wallet status and limits
    status = Column(SQLEnum(WalletStatus), nullable=False, index=True, default=WalletStatus.ACTIVE)
    balance = Column(Float, default=0.0, nullable=False)
    available_balance = Column(Float, default=0.0, nullable=False)  # Balance minus pending transactions
    frozen_balance = Column(Float, default=0.0, nullable=False)  # Amount temporarily frozen
    
    # Limits
    daily_limit = Column(Float, nullable=True)
    monthly_limit = Column(Float, nullable=True)
    transaction_limit = Column(Float, nullable=True)
    
    # Configuration
    is_default = Column(Boolean, default=False, nullable=False)
    requires_mfa = Column(Boolean, default=True, nullable=False)
    requires_pin = Column(Boolean, default=True, nullable=False)
    
    # Metadata
    metadata = Column(JSON, nullable=True)  # Custom wallet settings
    tags = Column(JSON, nullable=True)  # Wallet tags for organization
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_activity = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    organisation = relationship("Organisation", foreign_keys=[organisation_id])
    transactions = relationship("WalletTransaction", back_populates="wallet", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_wallets_user_status', 'user_id', 'status'),
        Index('ix_wallets_organisation', 'organisation_id'),
        Index('ix_wallets_type_currency', 'wallet_type', 'currency'),
        UniqueConstraint('user_id', 'name', name='uq_wallet_user_name'),
    )
    
    def __repr__(self):
        return f"<Wallet {self.name} ({self.wallet_type.value})>"
    
    @property
    def is_active(self):
        return self.status == WalletStatus.ACTIVE
    
    @property
    def can_transact(self):
        return (
            self.is_active and
            self.balance > 0 and
            self.available_balance > 0
        )
    
    def freeze_amount(self, amount: float, reason: str = None):
        """Freeze specified amount"""
        self.frozen_balance += amount
        self.available_balance = max(0, self.available_balance - amount)
        if reason:
            if not self.metadata:
                self.metadata = {}
            self.metadata['freeze_reasons'] = self.metadata.get('freeze_reasons', [])
            self.metadata['freeze_reasons'].append({
                'amount': amount,
                'reason': reason,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
    
    def unfreeze_amount(self, amount: float):
        """Unfreeze specified amount"""
        self.frozen_balance = max(0, self.frozen_balance - amount)
        self.available_balance += amount
    
    def check_limits(self, amount: float, transaction_type: str = None) -> tuple[bool, str]:
        """Check if transaction exceeds limits"""
        # Transaction limit
        if self.transaction_limit and amount > self.transaction_limit:
            return False, f"Transaction amount exceeds limit of {self.transaction_limit}"
        
        # Daily limit (simplified - should check actual daily transactions)
        if self.daily_limit and amount > self.daily_limit:
            return False, f"Transaction amount exceeds daily limit of {self.daily_limit}"
        
        # Monthly limit (simplified - should check actual monthly transactions)
        if self.monthly_limit and amount > self.monthly_limit:
            return False, f"Transaction amount exceeds monthly limit of {self.monthly_limit}"
        
        return True, "OK"


class WalletTransaction(ProtectedModel):
    """Wallet transactions - separate from payment gateway transactions"""
    __tablename__ = "wallet_transactions"
    
    id = Column(BigInteger, primary_key=True)
    transaction_id = Column(String(100), unique=True, nullable=False, index=True)
    wallet_id = Column(BigInteger, ForeignKey('wallets.id'), nullable=False, index=True)
    from_wallet_id = Column(BigInteger, ForeignKey('wallets.id'), nullable=True, index=True)
    to_wallet_id = Column(BigInteger, ForeignKey('wallets.id'), nullable=True, index=True)
    
    # Transaction details
    amount = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, index=True)
    category = Column(SQLEnum(TransactionCategory), nullable=False, index=True)
    description = Column(Text, nullable=True)
    reference = Column(String(200), nullable=True)  # External reference
    
    # Status and timing
    status = Column(String(20), default="pending", nullable=False, index=True)
    initiated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Fees
    fee_amount = Column(Float, default=0.0, nullable=False)
    fee_type = Column(String(50), nullable=True)  # percentage, fixed, tiered
    
    # Metadata and audit
    metadata = Column(JSON, nullable=True)  # Additional transaction data
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    device_id = Column(String(100), nullable=True)
    
    # Compliance
    compliance_checked = Column(Boolean, default=False, nullable=False)
    risk_score = Column(Float, default=0.0, nullable=False)
    aml_flagged = Column(Boolean, default=False, nullable=False)
    
    # Relationships
    wallet = relationship("Wallet", foreign_keys=[wallet_id], back_populates="transactions")
    from_wallet = relationship("Wallet", foreign_keys=[from_wallet_id])
    to_wallet = relationship("Wallet", foreign_keys=[to_wallet_id])
    
    __table_args__ = (
        Index('ix_wallet_transactions_wallet_status', 'wallet_id', 'status'),
        Index('ix_wallet_transactions_date', 'initiated_at'),
        Index('ix_wallet_transactions_category', 'category'),
    )
    
    def __repr__(self):
        return f"<WalletTransaction {self.transaction_id} ({self.status})>"
    
    @property
    def is_completed(self):
        return self.status == "completed"
    
    @property
    def is_pending(self):
        return self.status == "pending"
    
    def mark_completed(self):
        """Mark transaction as completed"""
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc)
    
    def mark_failed(self, reason: str):
        """Mark transaction as failed"""
        self.status = "failed"
        if not self.metadata:
            self.metadata = {}
        self.metadata['failure_reason'] = reason


class WalletLimit(ProtectedModel):
    """Wallet transaction limits - configurable per wallet type"""
    __tablename__ = "wallet_limits"
    
    id = Column(BigInteger, primary_key=True)
    wallet_type = Column(SQLEnum(WalletType), nullable=False, index=True)
    currency = Column(String(3), nullable=False, index=True)
    
    # Limit amounts
    min_transaction = Column(Float, nullable=True)
    max_transaction = Column(Float, nullable=True)
    daily_limit = Column(Float, nullable=True)
    weekly_limit = Column(Float, nullable=True)
    monthly_limit = Column(Float, nullable=True)
    
    # Configuration
    requires_kyc_level = Column(Integer, default=0, nullable=False)  # Minimum KYC level
    requires_mfa = Column(Boolean, default=False, nullable=False)
    max_daily_transactions = Column(Integer, nullable=True)  # Maximum number of transactions per day
    
    # Timing
    effective_from = Column(DateTime, nullable=True)
    effective_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('ix_wallet_limits_type_currency', 'wallet_type', 'currency'),
        UniqueConstraint('wallet_type', 'currency', name='uq_wallet_limits'),
    )
    
    def __repr__(self):
        return f"<WalletLimit {self.wallet_type.value} ({self.currency})>"


class WalletAuditLog(ProtectedModel):
    """Audit trail for wallet operations"""
    __tablename__ = "wallet_audit_logs"
    
    id = Column(BigInteger, primary_key=True)
    wallet_id = Column(BigInteger, ForeignKey('wallets.id'), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    
    # Audit details
    action = Column(String(50), nullable=False, index=True)  # create, update, freeze, unfreeze, close
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    
    # Context
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    session_id = Column(String(128), nullable=True)
    
    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    wallet = relationship("Wallet", foreign_keys=[wallet_id])
    user = relationship("User", foreign_keys=[user_id])
    
    __table_args__ = (
        Index('ix_wallet_audit_logs_wallet_action', 'wallet_id', 'action'),
        Index('ix_wallet_audit_logs_user', 'user_id'),
        Index('ix_wallet_audit_logs_date', 'created_at'),
    )
    
    def __repr__(self):
        return f"<WalletAuditLog {self.action} on wallet {self.wallet_id}>"


class WalletSettings(ProtectedModel):
    """Global wallet settings - configurable by admin"""
    __tablename__ = "wallet_settings"
    
    id = Column(BigInteger, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(JSON, nullable=False)
    description = Column(Text, nullable=True)
    
    # Configuration
    is_public = Column(Boolean, default=False, nullable=False)  # Visible to users
    is_editable = Column(Boolean, default=True, nullable=False)  # Can be changed by admin
    requires_restart = Column(Boolean, default=False, nullable=False)  # Requires service restart
    
    # Versioning
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    
    # Relationships
    updater = relationship("User", foreign_keys=[updated_by])
    
    def __repr__(self):
        return f"<WalletSettings {self.key}>"
