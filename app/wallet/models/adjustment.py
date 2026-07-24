"""
app/wallet/models/adjustment.py
Manual balance adjustment requests with multi-layer approval.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, Index, Text, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.extensions import db
from app.models.base import BaseModel

class AdjustmentStatus:
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'

class AdjustmentRequestModel(BaseModel):
    """
    Tracks manual adjustment requests that require approval.
    Inherits from BaseModel which provides id (BigInteger), created_at, updated_at, is_deleted.
    """
    __tablename__ = 'wallet_adjustment_requests'
    __table_args__ = (
        Index('ix_adjustment_status', 'status'),
        Index('ix_adjustment_account_id', 'account_id'),
        Index('ix_adjustment_requested_by', 'requested_by_id'),
        Index('ix_adjustment_public_id', 'public_id'),
    )

    # EXTERNAL ID (UUID) - for public exposure
    public_id = Column(
        String(64), unique=True, nullable=False, index=True,
        default=lambda: str(uuid.uuid4())
    )

    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey('accounts.id'),
        nullable=False,
        index=True
    )

    amount = Column(
        Numeric(18, 6),
        nullable=False
    )

    currency = Column(
        String(10),
        nullable=False
    )

    # 'deposit' or 'withdraw'
    adjustment_type = Column(
        String(20),
        nullable=False
    )

    reason = Column(
        Text,
        nullable=False
    )

    status = Column(
        String(20),
        nullable=False,
        default=AdjustmentStatus.PENDING
    )

    requested_by_id = Column(
        BigInteger,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    approved_by_id = Column(
        BigInteger,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    approved_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    rejected_by_id = Column(
        BigInteger,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    rejected_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    rejection_reason = Column(
        Text,
        nullable=True
    )

    # Link to the actual transaction after approval
    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey('transactions.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    metadata_json = Column(
        JSONB,
        nullable=True,
        default=dict
    )

    def __repr__(self):
        return (
            f"<AdjustmentRequest {self.public_id} {self.adjustment_type} "
            f"{self.amount} {self.currency} {self.status}>"
        )
