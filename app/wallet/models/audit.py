"""
app/wallet/models/audit.py
Immutable audit log for all financial operations.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Index, Text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from app.extensions import db
from app.models.base import BaseModel


class AuditLogModel(BaseModel):
    """
    Immutable audit trail for financial transactions.
    
    Records the complete before/after state for forensic analysis.
    Never updated, never deleted.
    """
    __tablename__ = 'wallet_audit_logs'
    __table_args__ = (
        Index('ix_wallet_audit_transaction_id', 'transaction_id'),
        Index('ix_wallet_audit_actor_id', 'actor_id'),
        Index('ix_wallet_audit_action', 'action'),
        Index('ix_wallet_audit_created_at', 'created_at'),
        Index('ix_wallet_audit_ip_address', 'ip_address'),
        # Composite for time-series queries
        Index('ix_wallet_audit_actor_time', 'actor_id', 'created_at'),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # Link to transaction (if applicable)
    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey('transactions.id', ondelete='CASCADE'),
        nullable=True,
        index=True
    )
    
    # Who performed the action
    actor_id = Column(
        db.BigInteger,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    # What happened
    action = Column(
        String(100),
        nullable=False,
        index=True
    )
    
    # Detailed description
    description = Column(
        Text,
        nullable=True
    )
    
    # Complete state snapshot
    before_state = Column(
        JSONB,
        nullable=True,
        default=dict
    )
    
    after_state = Column(
        JSONB,
        nullable=True,
        default=dict
    )
    
    # Request context
    ip_address = Column(
        String(45),  # IPv6 compatible
        nullable=True
    )
    
    user_agent = Column(
        Text,
        nullable=True
    )
    
    request_id = Column(
        String(100),
        nullable=True,
        index=True
    )
    
    # Risk indicators
    risk_score = Column(
        db.Numeric(5, 2),
        nullable=True
    )
    
    aml_flagged = Column(
        db.Boolean,
        nullable=False,
        default=False
    )
    
    requires_review = Column(
        db.Boolean,
        nullable=False,
        default=False
    )
    
    # Additional context
    audit_metadata = Column(
        JSONB,
        nullable=True,
        default=dict
    )
    
    # Immutable timestamp
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True
    )
    
    def __repr__(self):
        return (
            f"<AuditLog {self.id} {self.action} "
            f"actor={self.actor_id} tx={self.transaction_id}>"
        )


class IdempotencyKeyModel(BaseModel):
    """
    Persistent storage for idempotency keys.
    
    Redis is used for fast lookup, but PostgreSQL is the source of truth.
    Keys expire after a configurable period.
    """
    __tablename__ = 'idempotency_keys'
    __table_args__ = (
        Index('ix_idempotency_key_value', 'key_value', unique=True),
        Index('ix_idempotency_expires_at', 'expires_at'),
        Index('ix_idempotency_resource', 'resource_type', 'resource_id'),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    key_value = Column(
        String(255),
        nullable=False,
        unique=True
    )
    
    resource_type = Column(
        String(50),
        nullable=False
    )
    
    resource_id = Column(
        String(64),
        nullable=True
    )
    
    # Cached response for replay
    response_status = Column(
        db.Integer,
        nullable=True
    )
    
    response_body = Column(
        JSONB,
        nullable=True
    )
    
    # Expiration
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False
    )
    
    # Metadata
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    
    client_ip = Column(
        String(45),
        nullable=True
    )
    
    def __repr__(self):
        return f"<IdempotencyKey {self.key_value} type={self.resource_type}>"
