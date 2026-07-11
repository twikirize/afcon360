# app/models/system_config.py
"""
System configuration model for storing platform-wide settings
"""

from sqlalchemy import Column, String, Text, BigInteger, ForeignKey
from app.models.base import BaseModel
from app.extensions import db
from datetime import datetime


class SystemConfig(BaseModel):
    """System configuration key-value store"""
    __tablename__ = 'system_configs'

    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    
    def __repr__(self):
        return f'<SystemConfig {self.key}={self.value}>'
    
    @classmethod
    def get(cls, key, default=None):
        """Get a configuration value by key"""
        try:
            config = cls.query.filter_by(key=key).first()
            if config:
                return config.value
            return default
        except Exception:
            db.session.rollback()
            return default
    
    @classmethod
    def set(cls, key, value, description=None, created_by=None):
        """Set a configuration value"""
        try:
            config = cls.query.filter_by(key=key).first()
            if config:
                config.value = str(value)
                if description:
                    config.description = description
                config.updated_at = datetime.utcnow()
            else:
                config = cls(
                    key=key,
                    value=str(value),
                    description=description,
                    created_by=created_by
                )
                db.session.add(config)
            db.session.commit()
            return config
        except Exception as e:
            db.session.rollback()
            raise e
