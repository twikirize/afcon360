"""
app/wallet/models/regulatory_volume.py
Regulatory Volume Policy Configuration and Audit Models
"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, BigInteger, DateTime, Text, Enum as SQLEnum, Index, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.extensions import db
from app.models.base import BaseModel
import enum


class WindowMode(str, enum.Enum):
    """Window calculation mode for regulatory volume."""
    CALENDAR = 'calendar'
    ROLLING = 'rolling'


class RegulatoryVolumePolicy(BaseModel):
    """
    Active regulatory volume calculation policy.
    
    Only one policy can be active at a time. Policy changes require dual authorization.
    """
    __tablename__ = 'regulatory_volume_policies'
    __table_args__ = (
        Index('ix_rvp_active', 'is_active', unique=True, postgresql_where=(Column('is_active') == True)),
        Index('ix_rvp_effective_from', 'effective_from'),
    )

    id = Column(BigInteger, primary_key=True)

    # Policy configuration
    daily_window_mode = Column(
        SQLEnum(WindowMode, name='window_mode_enum', create_constraint=True),
        nullable=False,
        default=WindowMode.CALENDAR
    )
    monthly_window_mode = Column(
        SQLEnum(WindowMode, name='window_mode_enum', create_constraint=True),
        nullable=False,
        default=WindowMode.CALENDAR
    )
    timezone = Column(String(50), nullable=False, default='Africa/Kampala')

    # Lifecycle
    is_active = Column(Boolean, default=False, nullable=False)
    effective_from = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    effective_until = Column(DateTime(timezone=True), nullable=True)

    # Authorization
    requested_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    requested_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    rejection_at = Column(DateTime(timezone=True), nullable=True)

    # Context
    reason = Column(Text, nullable=True)
    previous_policy_id = Column(BigInteger, ForeignKey('regulatory_volume_policies.id'), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<RegulatoryVolumePolicy id={self.id} daily={self.daily_window_mode.value} monthly={self.monthly_window_mode.value} active={self.is_active}>"

    def to_dict(self):
        return {
            "id": self.id,
            "daily_window_mode": self.daily_window_mode.value,
            "monthly_window_mode": self.monthly_window_mode.value,
            "timezone": self.timezone,
            "is_active": self.is_active,
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "effective_until": self.effective_until.isoformat() if self.effective_until else None,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejection_reason": self.rejection_reason,
            "rejection_at": self.rejection_at.isoformat() if self.rejection_at else None,
            "reason": self.reason,
            "previous_policy_id": self.previous_policy_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def get_active(cls):
        """Get the currently active regulatory volume policy."""
        return cls.query.filter_by(is_active=True).first()

    @classmethod
    def get_active_or_default(cls):
        """Get active policy or create default if none exists."""
        try:
            policy = cls.get_active()
        except Exception:
            # Table may not exist yet (e.g., during tests before migration)
            policy = None
        
        if not policy:
            policy = cls(
                daily_window_mode=WindowMode.CALENDAR,
                monthly_window_mode=WindowMode.CALENDAR,
                timezone='Africa/Kampala',
                is_active=True,
                effective_from=datetime.now(timezone.utc),
                requested_by=None,
                approved_by=None,
                reason="Default policy - auto-created"
            )
            # Only persist if table exists
            try:
                db.session.add(policy)
                db.session.commit()
            except Exception:
                # Table doesn't exist, return in-memory default
                db.session.rollback()
        return policy


class RegulatoryVolumePolicyChangeRequest(BaseModel):
    """
    Change request for regulatory volume policy.
    
    Requires dual authorization: requester != approver.
    """
    __tablename__ = 'regulatory_volume_policy_changes'
    __table_args__ = (
        Index('ix_rvpcr_status', 'status'),
        Index('ix_rvpcr_requested_at', 'requested_at'),
    )

    class Status(str, enum.Enum):
        PENDING = 'pending'
        APPROVED = 'approved'
        REJECTED = 'rejected'
        CANCELLED = 'cancelled'
        EXPIRED = 'expired'

    id = Column(BigInteger, primary_key=True)

    # Proposed configuration
    proposed_daily_mode = Column(
        SQLEnum(WindowMode, name='window_mode_enum', create_constraint=True),
        nullable=False
    )
    proposed_monthly_mode = Column(
        SQLEnum(WindowMode, name='window_mode_enum', create_constraint=True),
        nullable=False
    )
    proposed_timezone = Column(String(50), nullable=False, default='Africa/Kampala')
    proposed_effective_from = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Authorization
    requested_by = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    requested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    approved_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    status = Column(SQLEnum(Status, name='rvpcr_status_enum', create_constraint=True), nullable=False, default=Status.PENDING)
    reason = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Result
    resulting_policy_id = Column(BigInteger, ForeignKey('regulatory_volume_policies.id'), nullable=True)

    # Metadata
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    correlation_id = Column(String(36), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<RegulatoryVolumePolicyChangeRequest id={self.id} status={self.status.value} daily={self.proposed_daily_mode.value}>"

    def to_dict(self):
        return {
            "id": self.id,
            "proposed_daily_mode": self.proposed_daily_mode.value,
            "proposed_monthly_mode": self.proposed_monthly_mode.value,
            "proposed_timezone": self.proposed_timezone,
            "proposed_effective_from": self.proposed_effective_from.isoformat() if self.proposed_effective_from else None,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejected_by": self.rejected_by,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "status": self.status.value,
            "reason": self.reason,
            "rejection_reason": self.rejection_reason,
            "resulting_policy_id": self.resulting_policy_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "correlation_id": self.correlation_id,
        }

    def can_approve(self, user_id: int) -> bool:
        """Check if user can approve this request (must not be requester)."""
        return self.status == self.Status.PENDING and self.requested_by != user_id

    def can_reject(self, user_id: int) -> bool:
        """Check if user can reject this request (must not be requester)."""
        return self.status == self.Status.PENDING and self.requested_by != user_id


class LedgerReversalReference(BaseModel):
    """
    Tracks reversal relationships between ledger entries.
    
    This allows the regulatory volume calculator to exclude reversals
    from customer outgoing volume.
    """
    __tablename__ = 'ledger_reversal_references'
    __table_args__ = (
        Index('ix_lrr_original_entry', 'original_entry_id'),
        Index('ix_lrr_reversal_entry', 'reversal_entry_id'),
        Index('ix_lrr_original_transaction', 'original_transaction_id'),
    )

    id = Column(BigInteger, primary_key=True)

    # The original ledger entry that is being reversed
    original_entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey('ledger_entries.id', ondelete='CASCADE'),
        nullable=False
    )

    # The reversal ledger entry
    reversal_entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey('ledger_entries.id', ondelete='CASCADE'),
        nullable=False,
        unique=True  # One reversal per original entry
    )

    # Original transaction for context
    original_transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey('transactions.id', ondelete='CASCADE'),
        nullable=True
    )

    # Reversal type
    reversal_type = Column(String(30), nullable=False)  # 'refund', 'reversal', 'chargeback', 'correction'

    # Authorization
    initiated_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    approved_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)

    # Context
    reason = Column(Text, nullable=True)
    reversal_metadata = Column(JSONB, nullable=True, default=dict)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f"<LedgerReversalReference original={self.original_entry_id} reversal={self.reversal_entry_id} type={self.reversal_type}>"


__all__ = ['WindowMode', 'RegulatoryVolumePolicy', 'RegulatoryVolumePolicyChangeRequest', 'LedgerReversalReference']