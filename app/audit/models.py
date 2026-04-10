# app/audit/models.py
import logging
from datetime import datetime

from app.extensions import db
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

logger = logging.getLogger(__name__)


class AuditLog(BaseModel):
    """
    Immutable audit log for compliance. Do NOT delete or modify entries programmatically.
    Avoid storing secrets or full PII in meta.

    Single source of truth — app/audit/user.py re-exports this class for backwards compatibility.
    """
    __tablename__ = "audit_logs"

    # Named 'created_at' to match all callers (previously used user.py which had created_at)

    # FK to internal PKs
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    org_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True, index=True)

    action = Column(String(128), nullable=False, index=True)
    resource_type = Column(String(64), index=True)
    resource_id = Column(String(128), index=True)

    # Named 'ip_address' to match all callers (previously used user.py which had ip_address)
    ip_address = Column(String(64), index=True)
    user_agent = Column(String(512))
    device_id = Column(String(128), index=True)
    meta = Column(JSON, nullable=False, default=dict)

    # Relationships
    user = relationship("User", lazy="joined")
    organisation = relationship("Organisation", lazy="joined")

    @staticmethod
    def log(user_id=None, action=None, resource_type=None, resource_id=None,
            meta=None, ip_address=None, user_agent=None, org_id=None, device_id=None,
            db_session=None):
        """
        Create an audit log entry WITHOUT committing.
        Caller must handle transaction commit/rollback.
        """
        try:
            session = db_session or db.session
            entry = AuditLog(
                user_id=user_id,
                org_id=org_id,
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                ip_address=ip_address,
                user_agent=user_agent,
                device_id=device_id,
                meta=meta or {},
            )
            session.add(entry)
            # DO NOT commit here - let caller handle transaction
            logger.info(f"Audit log entry created: {action} by user {user_id}")
        except Exception as e:
            # Log error but don't rollback - let caller handle
            logger.error(f"Failed to create audit log entry: {e}")
            # Re-raise to let caller know audit logging failed
            raise

    @staticmethod
    def recent_audits(limit=50):
        return AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()
