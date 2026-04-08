# app/admin/owner/models.py
"""
Owner-specific models
REFACTORED: Use BIGINT IDs for database relations, UUID for display/API.
"""

import logging
from datetime import datetime
from sqlalchemy.orm import validates
from sqlalchemy import event
from app.extensions import db
from app.models.base import ProtectedModel

logger = logging.getLogger(__name__)


class OwnerAuditLog(ProtectedModel):
    """Audit trail for owner actions"""
    __tablename__ = 'owner_audit_logs'

    # id inherited from ProtectedModel
    # ✅ CORRECT: Use BIGINT for database relations
    owner_id = db.Column(db.BigInteger, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=False, index=True)

    action = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    details = db.Column(db.JSON, nullable=True)

    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(20), default='success')
    failure_reason = db.Column(db.String(255), nullable=True)

    # created_at, updated_at inherited from ProtectedModel

    # ✅ Relationship uses internal ID
    owner = db.relationship('User', foreign_keys=[owner_id])

    def __repr__(self):
        return f'<OwnerAuditLog {self.action}>'

    @validates('owner_id')
    def validate_owner_id(self, key, value):
        """Ensure owner_id is BIGINT (integer), not UUID (string)"""
        if isinstance(value, str):
            if '-' in value:
                # This is a UUID! Log it and try to explain what happened
                logger.error(f"CRITICAL MODEL ERROR: Attempted to assign UUID '{value}' to OwnerAuditLog.owner_id (BIGINT)")
                raise ValueError(
                    f"Cannot assign UUID '{value}' to owner_id. "
                    f"Use user.id (BIGINT) instead of user.user_id (UUID)"
                )
            # Try to convert string digit to int if possible
            if value.isdigit():
                return int(value)
        return value

    @classmethod
    def log_action(cls, user, action, category, details=None, request=None, status='success', failure_reason=None):
        """Helper to create audit log using BIGINT ID"""
        log = cls(
            owner_id=user.id,  # BIGINT for FK
            action=action,
            category=category,
            details=details,
            status=status,
            failure_reason=failure_reason
        )
        if request:
            log.ip_address = request.remote_addr
            log.user_agent = request.headers.get('User-Agent')
        db.session.add(log)
        db.session.commit()
        return log


class OwnerSettings(ProtectedModel):
    """Owner preferences"""
    __tablename__ = 'owner_settings'

    # id inherited from ProtectedModel
    # ✅ CORRECT: Use BIGINT for database relations
    owner_id = db.Column(db.BigInteger, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)

    # Security
    session_timeout_minutes = db.Column(db.Integer, default=120)
    max_login_attempts = db.Column(db.Integer, default=5)
    lockout_minutes = db.Column(db.Integer, default=15)

    # 2FA
    twofa_enabled = db.Column(db.Boolean, default=False)
    twofa_secret = db.Column(db.String(32), nullable=True)
    twofa_backup_codes = db.Column(db.JSON, nullable=True)

    # Notifications
    email_alerts = db.Column(db.Boolean, default=True)
    alert_on_new_device = db.Column(db.Boolean, default=True)
    alert_on_danger_action = db.Column(db.Boolean, default=True)

    # Danger zone
    require_password_for_danger = db.Column(db.Boolean, default=True)
    danger_action_delay_hours = db.Column(db.Integer, default=24)

    # created_at, updated_at inherited from ProtectedModel

    # ✅ Relationship uses internal ID
    owner = db.relationship('User', foreign_keys=[owner_id])


# Also add a before_insert listener for belt-and-suspenders safety
@event.listens_for(OwnerAuditLog, 'before_insert')
def validate_before_insert(mapper, connection, target):
    if isinstance(target.owner_id, str) and '-' in target.owner_id:
        raise ValueError(
            f"Cannot insert UUID '{target.owner_id}' into owner_id column. "
            f"Use the internal BIGINT ID (user.id)"
        )
