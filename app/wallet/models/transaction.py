"""
app/wallet/models/transaction.py
Transaction model with DB-enforced idempotency.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, String, Numeric, DateTime, ForeignKey,
    CheckConstraint, Index, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID, ENUM, JSONB
from app.extensions import db
from app.models.base import BaseModel
import enum


class TransactionType(str, enum.Enum):
    """Types of financial transactions."""
    DEPOSIT = 'deposit'
    WITHDRAW = 'withdraw'
    TRANSFER = 'transfer'
    FEE = 'fee'
    REFUND = 'refund'
    ADJUSTMENT = 'adjustment'


class TransactionStatus(str, enum.Enum):
    """Transaction lifecycle states."""
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class TransactionModel(BaseModel):
    """
    Immutable transaction record with DB-enforced idempotency.
    
    The client_request_id has a UNIQUE constraint - attempts to insert
    duplicates will fail at the database level, eliminating TOCTOU races.
    """
    __tablename__ = 'transactions'
    __table_args__ = (
        # DB-enforced idempotency - no TOCTOU possible
        CheckConstraint(
            "status IN ('PENDING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name='ck_transaction_status_valid'
        ),
        CheckConstraint('amount > 0', name='ck_transaction_amount_positive'),
        Index('ix_transactions_client_request_id', 'client_request_id', unique=True),
        Index('ix_transactions_status', 'status'),
        Index('ix_transactions_type', 'tx_type'),
        Index('ix_transactions_created_at', 'created_at'),
        Index('ix_transactions_user_id', 'user_id'),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # IDEMPOTENCY: DB-enforced unique constraint
    client_request_id = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )
    
    # Transaction classification
    tx_type = Column(
        SQLEnum(TransactionType, name='transaction_type_enum', create_type=True),
        nullable=False
    )
    
    status = Column(
        SQLEnum(TransactionStatus, name='transaction_status_enum', create_type=True),
        nullable=False,
        default=TransactionStatus.PENDING
    )
    
    # Transaction details
    amount = Column(
        Numeric(18, 6),
        nullable=False
    )
    
    currency = Column(
        String(10),
        nullable=False
    )
    
    # Primary actor (sender for transfers, owner for deposits/withdrawals)
    user_id = Column(
        db.BigInteger,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    # For transfers: recipient
    recipient_user_id = Column(
        db.BigInteger,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    # External references (payment provider, etc.)
    external_reference = Column(
        String(255),
        nullable=True,
        index=True
    )
    
    payment_provider = Column(
        String(50),
        nullable=True
    )
    
    payment_method = Column(
        String(50),
        nullable=True
    )
    
    # Fees and conversions
    fee_amount = Column(
        Numeric(18, 6),
        nullable=True
    )
    
    fee_currency = Column(
        String(10),
        nullable=True
    )
    
    conversion_rate = Column(
        Numeric(18, 8),
        nullable=True
    )
    
    converted_amount = Column(
        Numeric(18, 6),
        nullable=True
    )
    
    converted_currency = Column(
        String(10),
        nullable=True
    )
    
    # Flexible metadata
    tx_metadata = Column(JSONB, nullable=True, default=dict)
    
    # Lifecycle
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    
    failed_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    
    failure_reason = Column(
        db.Text,
        nullable=True
    )
    
    def __repr__(self):
        return (
            f"<Transaction {self.id} {self.tx_type} "
            f"{self.amount} {self.currency} {self.status}>"
        )
