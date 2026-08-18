# app/auth/models/delegation.py
"""
Delegation model - persisted store for role-based delegations.

Replaces the previous in-memory dict (`DelegationService._shared_active_delegations`).
That store lived in one worker process's memory: under gunicorn's multi-worker
model a delegation created on one worker was invisible to requests served by
another, and every delegation vanished on restart/redeploy. The database is
the source of truth here, same as everywhere else in this codebase.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Text, JSON,
    ForeignKey, Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class Delegation(BaseModel):
    """A single delegation grant, scoped and time-limited."""

    __tablename__ = "auth_delegations"
    __table_args__ = (
        Index("idx_delegation_delegatee_active", "delegatee_id", "is_active"),
        Index("idx_delegation_delegator", "delegator_id"),
        Index("idx_delegation_expires", "expires_at"),
        CheckConstraint("expires_at > created_at", name="ck_delegation_expiry_after_creation"),
    )

    delegation_reference = Column(String(40), nullable=False, unique=True, index=True)
    # e.g. "DEL-20260813120501-9F2A" — human-readable, matches the format the
    # in-memory version generated, so any existing UI/logs referencing that
    # shape keep working unchanged.

    delegator_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    delegatee_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    delegator = relationship("User", foreign_keys=[delegator_id])
    delegatee = relationship("User", foreign_keys=[delegatee_id])

    delegator_role = Column(String(30), nullable=False)
    delegatee_role = Column(String(30), nullable=False)

    # Stored as a JSON list of scope value strings (e.g.
    # ["accommodation_registration_management"]) rather than a comma string,
    # so membership checks don't need string parsing.
    scopes = Column(JSON, nullable=False, default=list)

    reason = Column(Text, nullable=True)
    duration_hours = Column(BigInteger, nullable=False)

    requires_approval = Column(Boolean, default=False, server_default="false", nullable=False)
    approved_by_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    is_active = Column(Boolean, default=True, server_default="true", nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    revocation_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    @property
    def is_expired(self) -> bool:
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires <= datetime.now(timezone.utc)

    @property
    def is_valid(self) -> bool:
        """Active, approved if approval was required, and not expired."""
        if not self.is_active or self.is_expired:
            return False
        if self.requires_approval and not self.approved_by_user_id:
            return False
        return True

    def has_scope(self, scope_value: str) -> bool:
        return scope_value in (self.scopes or [])

    def revoke(self, revoked_by_user_id: int, reason: str):
        self.is_active = False
        self.revoked_at = datetime.now(timezone.utc)
        self.revoked_by_user_id = revoked_by_user_id
        self.revocation_reason = reason

    def __repr__(self):
        return f"<Delegation {self.delegation_reference} {self.delegator_id}->{self.delegatee_id} active={self.is_active}>"