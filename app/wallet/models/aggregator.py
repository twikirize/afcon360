"""
Aggregator Model
Manages third-party aggregators for bulk wallet operations
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index, BigInteger
from app.extensions import db


class Aggregator(db.Model):
    """
    Third-party aggregator for bulk wallet operations.
    
    Aggregators can perform bulk deposits, withdrawals, and transfers
    on behalf of multiple users (e.g., payroll services, bill payment platforms).
    """
    __tablename__ = 'aggregators'
    
    __table_args__ = (
        Index('ix_aggregators_api_key', 'api_key'),
        Index('ix_aggregators_status', 'status'),
    )
    
    id = Column(BigInteger, primary_key=True)
    
    # Aggregator details
    name = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # API credentials
    api_key = Column(String(255), nullable=False, unique=True, index=True)
    api_secret = Column(String(255), nullable=False)  # Will be encrypted
    webhook_url = Column(String(500), nullable=True)
    webhook_secret = Column(String(255), nullable=True)
    
    # Configuration
    status = Column(String(20), nullable=False, default='active', index=True)  # active, suspended, disabled
    tier = Column(String(20), nullable=False, default='standard')  # standard, premium, enterprise
    
    # Rate limits
    rate_limit_per_minute = Column(Integer, default=100)
    rate_limit_per_hour = Column(Integer, default=1000)
    rate_limit_per_day = Column(Integer, default=10000)
    
    # Transaction limits
    max_single_transaction = Column(Integer, default=10000000)  # In smallest currency unit
    max_daily_volume = Column(Integer, default=100000000)
    
    # Allowed operations
    allow_bulk_deposits = Column(Boolean, default=True)
    allow_bulk_withdrawals = Column(Boolean, default=True)
    allow_bulk_transfers = Column(Boolean, default=True)
    
    # Security settings
    require_ip_whitelist = Column(Boolean, default=False)
    ip_whitelist = Column(Text, nullable=True)  # JSON array of IP addresses
    
    # Metadata
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    company_name = Column(String(255), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    
    def to_dict(self, exclude_secret=True):
        """Convert to dictionary for JSON serialization"""
        data = {
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'status': self.status,
            'tier': self.tier,
            'rate_limit_per_minute': self.rate_limit_per_minute,
            'rate_limit_per_hour': self.rate_limit_per_hour,
            'rate_limit_per_day': self.rate_limit_per_day,
            'max_single_transaction': self.max_single_transaction,
            'max_daily_volume': self.max_daily_volume,
            'allow_bulk_deposits': self.allow_bulk_deposits,
            'allow_bulk_withdrawals': self.allow_bulk_withdrawals,
            'allow_bulk_transfers': self.allow_bulk_transfers,
            'require_ip_whitelist': self.require_ip_whitelist,
            'contact_email': self.contact_email,
            'contact_phone': self.contact_phone,
            'company_name': self.company_name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
        }
        
        if not exclude_secret:
            data['api_key'] = self.api_key
            data['api_secret'] = self.api_secret
            data['webhook_url'] = self.webhook_url
            data['webhook_secret'] = self.webhook_secret
            data['ip_whitelist'] = self.ip_whitelist
        
        return data
    
    def __repr__(self):
        return f"<Aggregator {self.id}: {self.display_name} ({self.status})>"
