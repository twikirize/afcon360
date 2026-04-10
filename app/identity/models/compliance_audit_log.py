# app/identity/models/compliance_audit_log.py
from sqlalchemy import Column, BigInteger, String, DateTime, Enum, ForeignKey, JSON, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel

class ComplianceAuditLog(BaseModel):
    """
    ComplianceAuditLog records every compliance enforcement decision.
    Unlike OrganisationAuditLog (which tracks data changes),
    this log tracks whether an operation was allowed, blocked, or conditional.
    """

    __tablename__ = "compliance_audit_logs"

    # Works for both organisations and individuals
    entity_id = Column(BigInteger, nullable=False)
    entity_type = Column(Enum("organisation", "individual", name="entity_type"), nullable=False)

    # Operation being checked (e.g. "wallet_payouts", "list_offers")
    operation = Column(String(64), nullable=False)

    # Decision outcome
    decision = Column(Enum("allowed", "blocked", "conditional", name="compliance_decision"), nullable=False)

    # Requirement key from ComplianceSettings
    requirement_key = Column(String(64))

    # Snapshot of compliance state at the time of decision
    compliance_level = Column(Integer)  # 0–3
    risk_tier = Column(Enum("low", "medium", "high", name="risk_tier"))

    # Extra context (e.g. expired doc, missing license)
    context = Column(JSON)

    # Who made the decision (system, admin, user)
    decided_by = Column(BigInteger, ForeignKey("users.id"))
    decided_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    reviewer = relationship("User", foreign_keys=[decided_by])
