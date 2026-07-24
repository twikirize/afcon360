# app/admin/owner/models.py
"""
Owner-specific models
REFACTORED: Use BIGINT IDs for database relations, UUID for display/API.
"""

import json
import logging
from datetime import datetime, timezone
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


class RateLimitSettings(ProtectedModel):
    """Global rate limiting configuration (singleton row)"""
    __tablename__ = 'rate_limit_settings'

    # Global toggle
    enabled = db.Column(db.Boolean, default=True, nullable=False)

    # Algorithm strategy (fixed-window | sliding-window | token-bucket)
    strategy = db.Column(db.String(20), default='fixed-window', nullable=False)

    # Global default limits
    default_per_minute = db.Column(db.Integer, default=500, nullable=False)
    default_per_hour = db.Column(db.Integer, default=2000, nullable=False)
    default_per_day = db.Column(db.Integer, default=10000, nullable=False)

    # Blocking behavior
    block_duration_minutes = db.Column(db.Integer, default=15, nullable=False)
    progressive_blocking_enabled = db.Column(db.Boolean, default=False, nullable=False)
    max_violations_before_block = db.Column(db.Integer, default=10, nullable=False)

    # Key diversity (comma-separated identity sources)
    key_sources = db.Column(db.String(200), default='ip,user_id', nullable=False)

    # Monitoring
    logging_enabled = db.Column(db.Boolean, default=True, nullable=False)
    alert_on_breach = db.Column(db.Boolean, default=False, nullable=False)
    alert_threshold_per_minute = db.Column(db.Integer, default=100, nullable=False)

    # Edge / WAF
    edge_rate_limiting_enabled = db.Column(db.Boolean, default=False, nullable=False)

    updated_by = db.Column(db.BigInteger, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    # created_at, updated_at inherited from ProtectedModel
    updated_by_user = db.relationship('User', foreign_keys=[updated_by])

    @staticmethod
    def get_settings():
        """Get singleton settings row, create default if missing"""
        settings = RateLimitSettings.query.first()
        if not settings:
            settings = RateLimitSettings(
                enabled=True,
                strategy='fixed-window',
                default_per_minute=500,
                default_per_hour=2000,
                default_per_day=10000,
                block_duration_minutes=15,
                progressive_blocking_enabled=False,
                max_violations_before_block=10,
                key_sources='ip,user_id',
                logging_enabled=True,
                alert_on_breach=False,
                alert_threshold_per_minute=100,
                edge_rate_limiting_enabled=False,
            )
            db.session.add(settings)
            db.session.commit()
        return settings

    @staticmethod
    def update_settings(updates: dict, updated_by: int = None):
        """Update singleton settings row"""
        settings = RateLimitSettings.get_settings()
        for key, value in updates.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        settings.updated_by = updated_by
        db.session.commit()
        return settings


class RateLimitBreach(ProtectedModel):
    """Tracks rate limit breach events for alerting and audit"""
    __tablename__ = 'rate_limit_breaches'

    identity_type = db.Column(db.String(20), nullable=False)
    identity_value = db.Column(db.String(200), nullable=False)
    endpoint = db.Column(db.String(200), nullable=True)
    method = db.Column(db.String(10), nullable=True)
    limit_exceeded = db.Column(db.String(100), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    country = db.Column(db.String(5), nullable=True)

    blocked = db.Column(db.Boolean, default=False, nullable=False)
    block_duration_minutes = db.Column(db.Integer, nullable=True)

    notified = db.Column(db.Boolean, default=False, nullable=False)
    notified_at = db.Column(db.DateTime, nullable=True)

    owner_id = db.Column(db.BigInteger, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    owner = db.relationship('User', foreign_keys=[owner_id])

    # created_at, updated_at inherited from ProtectedModel

    def __repr__(self):
        return f'<RateLimitBreach {self.identity_type}:{self.identity_value} {self.limit_exceeded}>'


# Also add a before_insert listener for belt-and-suspenders safety
@event.listens_for(OwnerAuditLog, 'before_insert')
def validate_before_insert(mapper, connection, target):
    if isinstance(target.owner_id, str) and '-' in target.owner_id:
        raise ValueError(
            f"Cannot insert UUID '{target.owner_id}' into owner_id column. "
            f"Use the internal BIGINT ID (user.id)"
        )
