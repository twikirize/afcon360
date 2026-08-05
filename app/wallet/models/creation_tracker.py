"""
app/wallet/models/creation_tracker.py
Database model for wallet creation lifecycle events.

Persists WalletCreationTracker data to the database so admins
can view the complete creation timeline in the financial account lookup.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Index, Text, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.extensions import db


class WalletCreationEventModel(db.Model):
    """
    Persisted wallet creation lifecycle events.

    Each step in the wallet creation process is recorded here
    so admins can see the complete creation timeline for any account.
    """
    __tablename__ = 'wallet_creation_events'
    __table_args__ = (
        Index('ix_wce_account_id', 'account_id'),
        Index('ix_wce_user_id', 'user_id'),
        Index('ix_wce_event', 'event'),
        Index('ix_wce_created_at', 'created_at'),
        Index('ix_wce_user_event', 'user_id', 'event'),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Foreign keys (BigInteger for internal DB relations)
    user_id = Column(
        BigInteger,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey('accounts.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    # Event details
    event = Column(
        String(50),
        nullable=False,
        index=True
    )

    step_order = Column(
        BigInteger,
        nullable=False,
        default=0
    )

    step_metadata = Column(
        JSONB,
        nullable=True,
        default=dict
    )

    # Session context (for anti-hijacking verification)
    session_id = Column(
        String(128),
        nullable=True
    )

    ip_address = Column(
        String(45),
        nullable=True
    )

    user_agent = Column(
        Text,
        nullable=True
    )

    # Timestamps
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
        nullable=False
    )

    def __repr__(self):
        return f'<WalletCreationEvent {self.event} for user {self.user_id}>'
