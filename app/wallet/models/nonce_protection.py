"""
Nonce Replay Protection Model
Manages user-specific nonce counters to prevent transaction replay attacks
"""

from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, DateTime, Text, Index, Boolean
from app.extensions import db


class UserNonce(db.Model):
    """
    User-specific nonce counter for replay protection
    """
    __tablename__ = 'user_nonces'
    
    __table_args__ = (
        Index('ix_user_nonces_user_id', 'user_id'),
        Index('ix_user_nonces_nonce', 'nonce'),
        Index('ix_user_nonces_created_at', 'created_at'),
    )
    
    id = Column(Integer, primary_key=True)
    
    # User identification
    user_id = Column(Integer, nullable=False, index=True)
    user_type = Column(String(20), default='user')  # user, aggregator, admin
    
    # Nonce information
    nonce = Column(String(255), nullable=False, unique=True, index=True)
    nonce_type = Column(String(50), default='transaction')  # transaction, api_call, webhook
    
    # Transaction details
    transaction_type = Column(String(50), nullable=True)  # deposit, withdraw, transfer
    amount = Column(Integer, nullable=True)  # Amount in smallest currency unit
    currency = Column(String(10), nullable=True)
    
    # Status
    used = Column(Boolean, default=False)
    voided = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_type': self.user_type,
            'nonce': self.nonce,
            'nonce_type': self.nonce_type,
            'transaction_type': self.transaction_type,
            'amount': self.amount,
            'currency': self.currency,
            'used': self.used,
            'voided': self.voided,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'used_at': self.used_at.isoformat() if self.used_at else None
        }
    
    def __repr__(self):
        return f"<UserNonce {self.id}: {self.nonce} (user={self.user_id}, used={self.used})>"


class NonceProtectionConfig(db.Model):
    """
    Configuration for nonce replay protection settings
    """
    __tablename__ = 'nonce_protection_config'
    
    id = Column(Integer, primary_key=True)
    
    # General settings
    enabled = Column(Boolean, default=True)
    
    # Expiration settings
    nonce_ttl_minutes = Column(Integer, default=15)  # How long nonces are valid
    cleanup_interval_hours = Column(Integer, default=1)  # How often to clean up expired nonces
    
    # Rate limiting
    max_nonces_per_user_per_hour = Column(Integer, default=1000)
    max_nonces_per_aggregator_per_hour = Column(Integer, default=10000)
    
    # Security settings
    require_nonce_for_all_transactions = Column(Boolean, default=True)
    allow_nonce_reuse_same_amount = Column(Boolean, default=False)
    strict_ip_binding = Column(Boolean, default=False)
    
    # Monitoring
    alert_on_suspicious_nonce_usage = Column(Boolean, default=True)
    alert_threshold_per_hour = Column(Integer, default=100)
    
    # Metadata
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'enabled': self.enabled,
            'nonce_ttl_minutes': self.nonce_ttl_minutes,
            'cleanup_interval_hours': self.cleanup_interval_hours,
            'max_nonces_per_user_per_hour': self.max_nonces_per_user_per_hour,
            'max_nonces_per_aggregator_per_hour': self.max_nonces_per_aggregator_per_hour,
            'require_nonce_for_all_transactions': self.require_nonce_for_all_transactions,
            'allow_nonce_reuse_same_amount': self.allow_nonce_reuse_same_amount,
            'strict_ip_binding': self.strict_ip_binding,
            'alert_on_suspicious_nonce_usage': self.alert_on_suspicious_nonce_usage,
            'alert_threshold_per_hour': self.alert_threshold_per_hour,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f"<NonceProtectionConfig {self.id}: enabled={self.enabled}>"
