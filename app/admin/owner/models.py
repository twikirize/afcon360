#app/admin/owner/models.py
"""
Owner-specific models
These are separate from regular admin models
"""

from datetime import datetime
from app.extensions import db


class OwnerAuditLog(db.Model):
    """Audit trail for owner actions"""
    __tablename__ = 'owner_audit_logs'
    # __table_args__ = {'schema': 'admin'}  # COMMENT OUT - schema not needed

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    action = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    details = db.Column(db.JSON, nullable=True)

    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(20), default='success')
    failure_reason = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationship
    owner = db.relationship('User', foreign_keys=[owner_id])

    def __repr__(self):
        return f'<OwnerAudit {self.action}>'


class OwnerSettings(db.Model):
    """Owner preferences"""
    __tablename__ = 'owner_settings'
    # __table_args__ = {'schema': 'admin'}  # COMMENT OUT - schema not needed

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)

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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = db.relationship('User', foreign_keys=[owner_id])