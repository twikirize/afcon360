# app/audit/user.py
from datetime import datetime
from app.extensions import db
from sqlalchemy import (
    Column, BigInteger, String, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import relationship

class AuditLog(db.Model):
    """
    Immutable audit log for compliance. Do NOT delete or modify entries programmatically.
    Avoid storing secrets or full PII in meta.
    """
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # FK to internal PKs (consistent with identity models)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    org_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True, index=True)

    action = Column(String(128), nullable=False, index=True)
    resource_type = Column(String(64), index=True)
    resource_id = Column(String(128), index=True)
    ip = Column(String(64), index=True)
    user_agent = Column(String(512))
    device_id = Column(String(128), index=True)
    meta = Column(JSON, nullable=False, default=dict)

    # Relationships
    user = relationship("User", lazy="joined")
    organisation = relationship("Organisation", lazy="joined")

    @staticmethod
    def recent_audits(limit=50):
        return AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
