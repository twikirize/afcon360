# app/identity/models/compliance_audit_log.py
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, JSON, Integer, CheckConstraint
from sqlalchemy.orm import relationship, validates
from datetime import datetime, timezone
from app.extensions import db
from app.models.base import BaseModel
from app.utils.enums import (
    EntityType,
    ComplianceDecision,
    RiskTier,
)


class ComplianceAuditLog(BaseModel):
    """
    ComplianceAuditLog records every compliance enforcement decision.
    Unlike OrganisationAuditLog (which tracks data changes),
    this log tracks whether an operation was allowed, blocked, or conditional.
    """

    __tablename__ = "compliance_audit_logs"

    # Works for both organisations and individuals
    entity_id = Column(BigInteger, nullable=False)
    # Use String + CHECK constraint instead of PostgreSQL ENUM
    entity_type = Column(String(16), nullable=False)

    # Operation being checked (e.g. "wallet_payouts", "list_offers")
    operation = Column(String(64), nullable=False)

    # Decision outcome - Use String + CHECK constraint instead of PostgreSQL ENUM
    decision = Column(String(16), nullable=False)

    # Requirement key from ComplianceSettings
    requirement_key = Column(String(64))

    # Snapshot of compliance state at the time of decision
    compliance_level = Column(Integer)  # 0-3
    # Use String + CHECK constraint instead of PostgreSQL ENUM
    risk_tier = Column(String(8))

    # Extra context (e.g. expired doc, missing license)
    context = Column(JSON)

    # Who made the decision (system, admin, user)
    decided_by = Column(BigInteger, ForeignKey("users.id"))
    decided_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint(EntityType.check_constraint(), name="ck_entity_type"),
        CheckConstraint(ComplianceDecision.check_constraint(), name="ck_compliance_decision"),
        CheckConstraint(RiskTier.check_constraint(), name="ck_risk_tier"),
    )

    reviewer = relationship("User", foreign_keys=[decided_by])

    @validates("entity_type")
    def validate_entity_type(self, key, value):
        if value and value not in EntityType.values():
            raise ValueError(f"Invalid entity_type. Must be one of: {EntityType.values()}")
        return value

    @validates("decision")
    def validate_decision(self, key, value):
        if value and value not in ComplianceDecision.values():
            raise ValueError(f"Invalid decision. Must be one of: {ComplianceDecision.values()}")
        return value

    @validates("risk_tier")
    def validate_risk_tier(self, key, value):
        if value and value not in RiskTier.values():
            raise ValueError(f"Invalid risk_tier. Must be one of: {RiskTier.values()}")
        return value