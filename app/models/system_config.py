# app/models/system_config.py
"""
System configuration model for storing platform-wide settings
"""

from sqlalchemy import Column, String, Text, BigInteger, ForeignKey, Boolean, DateTime
from app.models.base import BaseModel
from app.extensions import db
from datetime import datetime, timezone
import json


class SystemConfig(BaseModel):
    """System configuration key-value store"""
    __tablename__ = 'system_configs'

    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(20), default='str')
    category = Column(String(50), default='general', index=True)
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=False)
    requires_restart = Column(Boolean, default=False)
    updated_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f'<SystemConfig {self.key}={self.value}>'
    
    @classmethod
    def get(cls, key: str, default=None):
        """Get a configuration value by key with type handling"""
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            return default
        
        if setting.value_type == 'bool':
            return setting.value.lower() in ('true', '1', 'yes', 'on') if setting.value else False
        elif setting.value_type == 'int':
            try:
                return int(setting.value)
            except (ValueError, TypeError):
                return default
        elif setting.value_type == 'json':
            try:
                return json.loads(setting.value) if setting.value else {}
            except (ValueError, TypeError):
                return default
        return setting.value or default

    @classmethod
    def set(cls, key: str, value, value_type='str', category='general', description=None,
            is_public=False, requires_restart=False, updated_by=None, commit=True):
        """Create or update a system setting"""
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            setting = cls(key=key)
            db.session.add(setting)

        if value is None:
            setting.value = None
        else:
            if value_type == 'bool':
                setting.value = 'true' if value else 'false'
            elif value_type == 'int':
                setting.value = str(int(value))
            elif value_type == 'json':
                setting.value = json.dumps(value)
            else:
                setting.value = str(value)

        setting.value_type = value_type
        setting.category = category
        setting.description = description
        setting.is_public = is_public
        setting.requires_restart = requires_restart
        setting.updated_by = updated_by
        setting.updated_at = datetime.now(timezone.utc)

        if commit:
            db.session.commit()
        return setting

    @classmethod
    def initialize_defaults(cls):
        """Initialize default system settings"""
        defaults = [
            {'key': 'SITE_NAME', 'value': 'AFCON 360', 'value_type': 'str', 'category': 'branding', 'description': 'Site display name'},
            {'key': 'MAINTENANCE_MODE', 'value': 'false', 'value_type': 'bool', 'category': 'system', 'description': 'Enable maintenance mode'},
            {'key': 'payment_cash_globally_enabled', 'value': 'true', 'value_type': 'bool', 'category': 'payments', 'description': 'Allow cash payments system-wide'},
            {'key': 'payment_cash_development_mode', 'value': 'true', 'value_type': 'bool', 'category': 'payments', 'description': 'Bypass fraud checks for cash (development/testing)'},
            {'key': 'payment_cash_requires_kyc', 'value': 'true', 'value_type': 'bool', 'category': 'payments', 'description': 'Require KYC for cash payments'},
            {'key': 'payment_cash_min_kyc_level', 'value': '2', 'value_type': 'int', 'category': 'payments', 'description': 'Minimum KYC level for cash'},
            {'key': 'payment_cash_requires_verified_phone', 'value': 'true', 'value_type': 'bool', 'category': 'payments', 'description': 'Require phone verification for cash'},
            {'key': 'payment_cash_requires_verified_email', 'value': 'true', 'value_type': 'bool', 'category': 'payments', 'description': 'Require email verification for cash'},
            {'key': 'payment_cash_requires_previous_booking', 'value': 'true', 'value_type': 'bool', 'category': 'payments', 'description': 'Require at least 1 previous booking for cash'},
            {'key': 'payment_cash_max_amount', 'value': '500000', 'value_type': 'int', 'category': 'payments', 'description': 'Maximum cash booking amount (UGX)'},
            {'key': 'payment_cash_default_deposit_pct', 'value': '30', 'value_type': 'int', 'category': 'payments', 'description': 'Default deposit percentage for cash bookings'},
        ]
        created = 0
        for item in defaults:
            if not cls.query.filter_by(key=item['key']).first():
                db.session.add(cls(**item))
                created += 1
        db.session.commit()
        return created

