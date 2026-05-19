# app/models/system_config.py
"""
System configuration model for storing platform-wide settings
"""

from app.extensions import db
from datetime import datetime


class SystemConfig(db.Model):
    """System configuration key-value store"""
    __tablename__ = 'system_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
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
