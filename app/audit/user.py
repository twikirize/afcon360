# app/audit/user.py
"""
Audit logging for user actions
"""

from datetime import datetime
from app.extensions import db
from sqlalchemy import Column, BigInteger, String, DateTime, JSON, Integer
import logging

logger = logging.getLogger(__name__)


class AuditLog(db.Model):
    """Audit log for all user actions"""
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True, index=True)
    action = Column(String(128), nullable=False, index=True)
    resource_type = Column(String(64), index=True)
    resource_id = Column(String(128), index=True)
    ip_address = Column(String(64))
    user_agent = Column(String(512))
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    @staticmethod
    def log(user_id=None, action=None, resource_type=None, resource_id=None, meta=None, ip_address=None,
            user_agent=None):
        """Create an audit log entry"""
        try:
            log_entry = AuditLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                ip_address=ip_address,
                user_agent=user_agent,
                meta=meta or {}
            )
            db.session.add(log_entry)
            db.session.commit()
            logger.info(f"Audit log: {action} by user {user_id}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create audit log: {e}")
