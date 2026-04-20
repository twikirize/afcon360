# app/admin/owner/models.py
"""
Owner-specific models
REFACTORED: Use BIGINT IDs for database relations, UUID for display/API.
"""

import json
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


class SystemSetting(ProtectedModel):
    """System settings storage with caching support"""
    __tablename__ = 'system_settings'

    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    value_type = db.Column(db.String(20), default='str')
    category = db.Column(db.String(50), default='general', index=True)
    description = db.Column(db.Text, nullable=True)
    is_public = db.Column(db.Boolean, default=False)
    requires_restart = db.Column(db.Boolean, default=False)
    updated_by = db.Column(db.BigInteger, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # updater = db.relationship('User', foreign_keys=[updated_by])

    @classmethod
    def get(cls, key: str, default=None):
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            return default
        if setting.value_type == 'bool':
            return setting.value.lower() in ('true', '1', 'yes', 'on') if setting.value else False
        elif setting.value_type == 'int':
            try:
                return int(setting.value)
            except:
                return default
        elif setting.value_type == 'json':
            try:
                return json.loads(setting.value) if setting.value else {}
            except:
                return default
        return setting.value or default

    @classmethod
    def set(cls, key: str, value, value_type='str', category='general', description=None,
            is_public=False, requires_restart=False, updated_by=None, commit=True):
        """
        Create or update a system setting with the provided parameters.

        Args:
            key: Unique setting identifier
            value: Setting value (will be serialized based on value_type)
            value_type: Type of value ('str', 'bool', 'int', 'json')
            category: Setting category for grouping
            description: Human-readable description
            is_public: Whether the setting can be read without authentication
            requires_restart: Whether a restart is needed for changes to take effect
            updated_by: User ID (BIGINT) of the user making the change
            commit: Whether to commit the transaction immediately (default: True)

        Returns:
            The SystemSetting instance
        """
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            setting = cls(key=key)
            db.session.add(setting)

        # Handle None values
        if value is None:
            setting.value = None
        else:
            # Serialize value based on type
            if value_type == 'bool':
                # Convert boolean to string representation
                if isinstance(value, bool):
                    setting.value = 'true' if value else 'false'
                elif isinstance(value, str):
                    # Check if string represents a truthy value
                    setting.value = 'true' if value.lower() in ('true', '1', 'yes', 'on') else 'false'
                else:
                    # For numbers, treat non-zero as true
                    setting.value = 'true' if value else 'false'
            elif value_type == 'int':
                # Ensure it's an integer, then convert to string
                try:
                    int_value = int(value)
                    setting.value = str(int_value)
                except (ValueError, TypeError):
                    raise ValueError(f"Cannot convert value '{value}' to integer for setting '{key}'")
            elif value_type == 'json':
                # Serialize to JSON string
                try:
                    setting.value = json.dumps(value)
                except (TypeError, ValueError):
                    raise ValueError(f"Cannot serialize value to JSON for setting '{key}'")
            else:  # 'str' or any other type
                setting.value = str(value)

        setting.value_type = value_type
        setting.category = category
        setting.description = description
        setting.is_public = is_public
        setting.requires_restart = requires_restart
        setting.updated_by = updated_by
        setting.updated_at = datetime.utcnow()

        # Commit the transaction if requested
        if commit:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                raise e

        return setting

    @classmethod
    def initialize_defaults(cls):
        """Create default system settings if they don't exist."""
        defaults = [
            {
                'key': 'EMERGENCY_LOCKDOWN',
                'value': 'false',
                'value_type': 'bool',
                'category': 'security',
                'description': 'Global emergency lockdown toggle'
            },
            {
                'key': 'MAINTENANCE_MODE',
                'value': 'false',
                'value_type': 'bool',
                'category': 'system',
                'description': 'Enable maintenance mode site-wide'
            },
            {
                'key': 'ENABLE_WALLET',
                'value': 'true',
                'value_type': 'bool',
                'category': 'features',
                'description': 'Enable wallet functionality'
            },
            {
                'key': 'PAYMENT_PROCESSING_ENABLED',
                'value': 'false',
                'value_type': 'bool',
                'category': 'payment',
                'description': 'Enable payment processing'
            },
            {
                'key': 'RATE_LIMIT_ENABLED',
                'value': 'true',
                'value_type': 'bool',
                'category': 'security',
                'description': 'Enable rate limiting for API endpoints'
            },
            {
                'key': 'SECURITY_HEADERS_ENABLED',
                'value': 'true',
                'value_type': 'bool',
                'category': 'security',
                'description': 'Enable security headers in HTTP responses'
            },
            {
                'key': 'AUDIT_LOGGING_ENABLED',
                'value': 'true',
                'value_type': 'bool',
                'category': 'security',
                'description': 'Enable comprehensive audit logging'
            },
            {
                'key': 'SITE_NAME',
                'value': 'AFCON 360',
                'value_type': 'str',
                'category': 'branding',
                'description': 'Site display name'
            },
            {
                'key': 'CONTACT_EMAIL',
                'value': 'support@afcon360.example',
                'value_type': 'str',
                'category': 'contact',
                'description': 'Primary contact email'
            },
        ]
        created_count = 0
        for item in defaults:
            existing = cls.query.filter_by(key=item['key']).first()
            if not existing:
                setting = cls(
                    key=item['key'],
                    value=item['value'],
                    value_type=item['value_type'],
                    category=item['category'],
                    description=item['description']
                )
                db.session.add(setting)
                created_count += 1
        db.session.commit()
        return created_count
