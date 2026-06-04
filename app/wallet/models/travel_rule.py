"""
Travel Rule Compliance Model
FATF Travel Rule implementation for crypto/fiat transfers
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index, ForeignKey, BigInteger
from app.extensions import db


class TravelRuleConfig(db.Model):
    """
    Configuration for FATF Travel Rule compliance
    """
    __tablename__ = 'travel_rule_config'
    
    __table_args__ = (
        Index('ix_travel_rule_config_enabled', 'enabled'),
    )
    
    id = Column(BigInteger, primary_key=True)
    
    # General settings
    enabled = Column(Boolean, default=False, nullable=False, index=True)
    
    # Thresholds
    fiat_threshold_usd = Column(Integer, default=1000)  # USD threshold for fiat transfers
    crypto_threshold_usd = Column(Integer, default=1000)  # USD threshold for crypto transfers
    
    # Jurisdiction settings
    apply_to_all_jurisdictions = Column(Boolean, default=True)
    exempted_jurisdictions = Column(Text, nullable=True)  # JSON array of country codes
    
    # Data collection settings
    collect_originator_info = Column(Boolean, default=True)
    collect_beneficiary_info = Column(Boolean, default=True)
    collect_transaction_purpose = Column(Boolean, default=True)
    
    # Verification settings
    verify_originator_identity = Column(Boolean, default=True)
    verify_beneficiary_identity = Column(Boolean, default=True)
    
    # Reporting settings
    auto_report_to_vasp = Column(Boolean, default=True)
    retain_records_days = Column(Integer, default=1825)  # 5 years
    
    # API settings for VASP communication
    vasp_api_endpoint = Column(String(500), nullable=True)
    vasp_api_key = Column(String(255), nullable=True)
    vasp_timeout_seconds = Column(Integer, default=30)
    
    # Metadata
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'enabled': self.enabled,
            'fiat_threshold_usd': self.fiat_threshold_usd,
            'crypto_threshold_usd': self.crypto_threshold_usd,
            'apply_to_all_jurisdictions': self.apply_to_all_jurisdictions,
            'exempted_jurisdictions': self.exempted_jurisdictions,
            'collect_originator_info': self.collect_originator_info,
            'collect_beneficiary_info': self.collect_beneficiary_info,
            'collect_transaction_purpose': self.collect_transaction_purpose,
            'verify_originator_identity': self.verify_originator_identity,
            'verify_beneficiary_identity': self.verify_beneficiary_identity,
            'auto_report_to_vasp': self.auto_report_to_vasp,
            'retain_records_days': self.retain_records_days,
            'vasp_api_endpoint': self.vasp_api_endpoint,
            'vasp_timeout_seconds': self.vasp_timeout_seconds,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f"<TravelRuleConfig {self.id}: enabled={self.enabled}>"


class TravelRuleTransfer(db.Model):
    """
    Travel Rule transfer record for compliance tracking
    """
    __tablename__ = 'travel_rule_transfers'
    
    __table_args__ = (
        Index('ix_travel_rule_transfers_transaction_id', 'transaction_id'),
        Index('ix_travel_rule_transfers_status', 'status'),
        Index('ix_travel_rule_transfers_created_at', 'created_at'),
    )
    
    id = Column(BigInteger, primary_key=True)
    
    # Transaction reference
    transaction_id = Column(BigInteger, ForeignKey('transactions.id'), nullable=False, index=True)
    
    # Originator information
    originator_name = Column(String(255), nullable=True)
    originator_account_number = Column(String(255), nullable=True)
    originator_address = Column(Text, nullable=True)
    originator_dob = Column(DateTime, nullable=True)  # Date of birth
    originator_id_number = Column(String(100), nullable=True)
    originator_nationality = Column(String(10), nullable=True)
    
    # Beneficiary information
    beneficiary_name = Column(String(255), nullable=True)
    beneficiary_account_number = Column(String(255), nullable=True)
    beneficiary_address = Column(Text, nullable=True)
    beneficiary_dob = Column(DateTime, nullable=True)
    beneficiary_id_number = Column(String(100), nullable=True)
    beneficiary_nationality = Column(String(10), nullable=True)
    
    # Transaction details
    amount = Column(Integer, nullable=False)  # Amount in smallest currency unit
    currency = Column(String(10), nullable=False)
    transaction_purpose = Column(String(100), nullable=True)
    
    # VASP information
    originator_vasp_name = Column(String(255), nullable=True)
    originator_vasp_address = Column(String(500), nullable=True)
    beneficiary_vasp_name = Column(String(255), nullable=True)
    beneficiary_vasp_address = Column(String(500), nullable=True)
    
    # Compliance status
    status = Column(String(20), default='pending')  # pending, verified, rejected, reported
    verification_score = Column(Integer, nullable=True)  # 0-100 verification score
    rejection_reason = Column(Text, nullable=True)
    
    # Reporting
    reported_to_vasp = Column(Boolean, default=False)
    vasp_response = Column(Text, nullable=True)
    vasp_reported_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'originator_name': self.originator_name,
            'originator_account_number': self.originator_account_number,
            'originator_address': self.originator_address,
            'originator_dob': self.originator_dob.isoformat() if self.originator_dob else None,
            'originator_id_number': self.originator_id_number,
            'originator_nationality': self.originator_nationality,
            'beneficiary_name': self.beneficiary_name,
            'beneficiary_account_number': self.beneficiary_account_number,
            'beneficiary_address': self.beneficiary_address,
            'beneficiary_dob': self.beneficiary_dob.isoformat() if self.beneficiary_dob else None,
            'beneficiary_id_number': self.beneficiary_id_number,
            'beneficiary_nationality': self.beneficiary_nationality,
            'amount': self.amount,
            'currency': self.currency,
            'transaction_purpose': self.transaction_purpose,
            'originator_vasp_name': self.originator_vasp_name,
            'originator_vasp_address': self.originator_vasp_address,
            'beneficiary_vasp_name': self.beneficiary_vasp_name,
            'beneficiary_vasp_address': self.beneficiary_vasp_address,
            'status': self.status,
            'verification_score': self.verification_score,
            'rejection_reason': self.rejection_reason,
            'reported_to_vasp': self.reported_to_vasp,
            'vasp_response': self.vasp_response,
            'vasp_reported_at': self.vasp_reported_at.isoformat() if self.vasp_reported_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f"<TravelRuleTransfer {self.id}: {self.currency} {self.amount} ({self.status})>"
