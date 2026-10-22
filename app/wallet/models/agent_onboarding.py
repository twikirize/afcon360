"""
app/wallet/models/agent_onboarding.py

Agent onboarding + tiered approval (bank-style sequential chain).

Lifecycle (status):
    submitted          -> wallet_admin reviews (operational / docs completeness)
    wallet_approved    -> compliance_officer reviews (KYC/KYB docs, sanctions/PEP, EDD)
    compliance_approved-> super_admin OR owner gives final approval
    active             -> User.is_agent=True, agent_code issued, float account created
    rejected           -> any step may reject (returns to applicant with reason)

Every decision is recorded immutably in AgentOnboardingApproval (the audit chain).
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Text,
    DateTime,
    JSON,
    Index,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.sql import func
from app.models.base import BaseModel
from app.extensions import db


class AgentOnboarding(BaseModel):
    __tablename__ = "agent_onboardings"

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user_id = Column(
        BigInteger,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    agent_type = Column(String(20), nullable=False)

    reference = Column(String(64), nullable=False)

    status = Column(String(30), nullable=False, default="submitted")

    applicant_data = Column(JSON, nullable=False, default=dict)

    current_stage = Column(String(30), nullable=False, default="wallet_review")

    reviewed_by_wallet_admin_at = Column(DateTime(timezone=True), nullable=True)

    reviewed_by_compliance_at = Column(DateTime(timezone=True), nullable=True)

    activated_at = Column(DateTime(timezone=True), nullable=True)

    rejected_at = Column(DateTime(timezone=True), nullable=True)

    rejection_reason = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("reference", name="uq_agent_onboardings_reference"),
        Index("ix_agent_onb_user", "user_id"),
        Index("ix_agent_onb_status_stage", "status", "current_stage"),
    )

    def __repr__(self):
        return f"<AgentOnboarding {self.reference} user={self.user_id} {self.status}>"


class AgentOnboardingApproval(BaseModel):
    """
    Immutable record of one decision in the approval chain.
    """

    __tablename__ = "agent_onboarding_approvals"

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    onboarding_id = Column(
        BigInteger,
        db.ForeignKey("agent_onboardings.id", ondelete="CASCADE"),
        nullable=False,
    )

    stage = Column(String(30), nullable=False)

    approver_user_id = Column(
        BigInteger,
        db.ForeignKey("users.id"),
        nullable=False,
    )

    approver_role = Column(String(50), nullable=False)

    decision = Column(String(20), nullable=False)

    comment = Column(Text, nullable=True)

    # Temporary Item 15 migration-workflow verification probe.
    h3_workflow_probe = Column(String(32), nullable=True)

    __table_args__ = (
        Index("ix_agent_appr_onb", "onboarding_id"),
        Index("ix_agent_appr_stage", "stage"),
    )

    def __repr__(self):
        return f"<AgentOnboardingApproval onboarding={self.onboarding_id} {self.stage} {self.decision}>"