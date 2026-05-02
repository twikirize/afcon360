"""
Fraud Detection Model
Configuration for ML-based fraud detection and transaction scoring
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, Index
from app.extensions import db


class FraudDetectionConfig(db.Model):
    """
    Configuration for fraud detection algorithms and scoring thresholds
    """
    __tablename__ = 'fraud_detection_config'
    
    __table_args__ = (
        Index('ix_fraud_detection_enabled', 'enabled'),
    )
    
    id = Column(Integer, primary_key=True)
    
    # General settings
    enabled = Column(Boolean, default=False, nullable=False, index=True)
    algorithm_type = Column(String(50), default='rule_based')  # rule_based, ml_based, hybrid
    
    # Scoring thresholds
    low_risk_threshold = Column(Float, default=0.3)  # Score below this is low risk
    medium_risk_threshold = Column(Float, default=0.7)  # Score above this is high risk
    auto_block_threshold = Column(Float, default=0.9)  # Score above this auto-blocks transaction
    
    # Velocity checks
    max_transactions_per_minute = Column(Integer, default=10)
    max_transactions_per_hour = Column(Integer, default=100)
    max_amount_per_transaction = Column(Float, default=1000000)  # In base currency
    max_amount_per_hour = Column(Float, default=10000000)
    
    # Geographic checks
    check_ip_location = Column(Boolean, default=True)
    check_device_fingerprint = Column(Boolean, default=True)
    check_velocity = Column(Boolean, default=True)
    
    # Behavioral checks
    check_unusual_patterns = Column(Boolean, default=True)
    check_new_account_large_transfer = Column(Boolean, default=True)
    check_multiple_failed_attempts = Column(Boolean, default=True)
    
    # Alert settings
    alert_on_high_risk = Column(Boolean, default=True)
    alert_on_medium_risk = Column(Boolean, default=False)
    alert_email_recipients = Column(Text, nullable=True)  # JSON array of email addresses
    
    # Action settings
    auto_block_high_risk = Column(Boolean, default=False)
    require_manual_review_medium_risk = Column(Boolean, default=True)
    allow_override = Column(Boolean, default=True)
    
    # ML Model settings (if using ML)
    model_name = Column(String(255), nullable=True)
    model_version = Column(String(50), nullable=True)
    retrain_interval_hours = Column(Integer, default=168)  # Default: weekly
    
    # Metadata
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'enabled': self.enabled,
            'algorithm_type': self.algorithm_type,
            'low_risk_threshold': self.low_risk_threshold,
            'medium_risk_threshold': self.medium_risk_threshold,
            'auto_block_threshold': self.auto_block_threshold,
            'max_transactions_per_minute': self.max_transactions_per_minute,
            'max_transactions_per_hour': self.max_transactions_per_hour,
            'max_amount_per_transaction': self.max_amount_per_transaction,
            'max_amount_per_hour': self.max_amount_per_hour,
            'check_ip_location': self.check_ip_location,
            'check_device_fingerprint': self.check_device_fingerprint,
            'check_velocity': self.check_velocity,
            'check_unusual_patterns': self.check_unusual_patterns,
            'check_new_account_large_transfer': self.check_new_account_large_transfer,
            'check_multiple_failed_attempts': self.check_multiple_failed_attempts,
            'alert_on_high_risk': self.alert_on_high_risk,
            'alert_on_medium_risk': self.alert_on_medium_risk,
            'alert_email_recipients': self.alert_email_recipients,
            'auto_block_high_risk': self.auto_block_high_risk,
            'require_manual_review_medium_risk': self.require_manual_review_medium_risk,
            'allow_override': self.allow_override,
            'model_name': self.model_name,
            'model_version': self.model_version,
            'retrain_interval_hours': self.retrain_interval_hours,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f"<FraudDetectionConfig {self.id}: {self.algorithm_type} (enabled={self.enabled})>"
