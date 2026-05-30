"""
Event Payment Configuration Models
Handles payment method configuration for events and mobile money settings
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from app.extensions import db


class PaymentMethodConfig(db.Model):
    """
    Configuration for available payment methods in the system
    Admin can enable/disable payment methods globally
    """
    __tablename__ = 'payment_method_configs'
    
    id = Column(Integer, primary_key=True)
    
    # Payment method identification
    method_id = Column(String(50), nullable=False, unique=True, index=True)  # e.g., 'mobile_money_mtn_ug'
    display_name = Column(String(100), nullable=False)
    method_type = Column(String(50), nullable=False)  # 'mobile_money', 'wallet', 'card'
    
    # Provider details
    provider_name = Column(String(50), nullable=False)  # 'mtn', 'airtel', 'safaricom'
    country_code = Column(String(2), nullable=False)  # 'UG', 'KE', 'NG'
    
    # Configuration
    is_enabled = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    requires_phone = Column(Boolean, default=False, nullable=False)
    
    # API Configuration
    api_key = Column(String(255), nullable=True)
    api_secret = Column(String(255), nullable=True)
    sandbox_url = Column(String(255), nullable=True)
    production_url = Column(String(255), nullable=True)
    use_sandbox = Column(Boolean, default=True, nullable=False)
    
    # Supported currencies
    supported_currencies = Column(JSON, default=list)  # ['UGX', 'USD']
    
    # Limits and fees
    min_amount = Column(db.Numeric(10, 2), default=0.00)
    max_amount = Column(db.Numeric(10, 2), default=1000000.00)
    transaction_fee = Column(db.Numeric(5, 4), default=0.0000)  # Decimal fee (0.0000 = 0%)
    
    # Additional configuration
    config_json = Column(JSON, default=dict)
    
    # Status and audit
    last_tested_at = Column(DateTime, nullable=True)
    last_test_result = Column(String(20), nullable=True)
    last_error_message = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, nullable=True)
    
    def __init__(self, method_id, display_name, method_type, provider_name, country_code):
        self.method_id = method_id
        self.display_name = display_name
        self.method_type = method_type
        self.provider_name = provider_name
        self.country_code = country_code
    
    @property
    def is_available(self):
        """Check if payment method is available for use"""
        return self.is_enabled and self.is_active
    
    @property
    def api_url(self):
        """Get appropriate API URL based on sandbox mode"""
        return self.sandbox_url if self.use_sandbox else self.production_url
    
    def supports_currency(self, currency):
        """Check if payment method supports the given currency"""
        return currency.upper() in [c.upper() for c in self.supported_currencies]
    
    def calculate_fee(self, amount):
        """Calculate transaction fee for given amount"""
        return float(amount) * float(self.transaction_fee)
    
    @classmethod
    def get_available_methods(cls, currency=None):
        """Get all available payment methods, optionally filtered by currency"""
        query = cls.query.filter(cls.is_enabled == True, cls.is_active == True)
        
        if currency:
            # Filter by currency support
            methods = query.all()
            return [m for m in methods if m.supports_currency(currency)]
        
        return query.all()
    
    @classmethod
    def get_by_id(cls, method_id):
        """Get payment method by ID"""
        return cls.query.filter_by(method_id=method_id).first()
    
    @classmethod
    def initialize_defaults(cls):
        """Initialize default payment method configurations"""
        defaults = [
            {
                'method_id': 'wallet',
                'display_name': 'AFCON360 Wallet',
                'method_type': 'wallet',
                'provider_name': 'afcon360',
                'country_code': 'UG',
                'is_enabled': True,
                'is_active': True,
                'requires_phone': False,
                'supported_currencies': ['UGX', 'KES', 'NGN', 'USD', 'EUR', 'GBP'],
                'min_amount': 0.00,
                'max_amount': 10000000.00,
                'transaction_fee': 0.0000
            },
            {
                'method_id': 'mobile_money_mtn_ug',
                'display_name': 'MTN Mobile Money Uganda',
                'method_type': 'mobile_money',
                'provider_name': 'mtn',
                'country_code': 'UG',
                'is_enabled': False,  # Disabled by default until configured
                'is_active': False,
                'requires_phone': True,
                'supported_currencies': ['UGX'],
                'min_amount': 500.00,
                'max_amount': 5000000.00,
                'transaction_fee': 0.0100,  # 1%
                'sandbox_url': 'https://sandbox.mtn.co.ug/momo/api/v1',
                'production_url': 'https://api.mtn.co.ug/momo/api/v1'
            },
            {
                'method_id': 'mobile_money_airtel_ug',
                'display_name': 'Airtel Money Uganda',
                'method_type': 'mobile_money',
                'provider_name': 'airtel',
                'country_code': 'UG',
                'is_enabled': False,
                'is_active': False,
                'requires_phone': True,
                'supported_currencies': ['UGX'],
                'min_amount': 500.00,
                'max_amount': 5000000.00,
                'transaction_fee': 0.0100,
                'sandbox_url': 'https://sandbox.airtel.com/airtel-money/api/v1',
                'production_url': 'https://api.airtel.com/airtel-money/api/v1'
            },
            {
                'method_id': 'mobile_money_mpesa_ke',
                'display_name': 'M-PESA Kenya',
                'method_type': 'mobile_money',
                'provider_name': 'safaricom',
                'country_code': 'KE',
                'is_enabled': False,
                'is_active': False,
                'requires_phone': True,
                'supported_currencies': ['KES'],
                'min_amount': 10.00,
                'max_amount': 700000.00,
                'transaction_fee': 0.0100,
                'sandbox_url': 'https://sandbox.safaricom.co.ke/mpesa/api/v1',
                'production_url': 'https://api.safaricom.co.ke/mpesa/api/v1'
            },
            {
                'method_id': 'mobile_money_mtn_ng',
                'display_name': 'MTN Mobile Money Nigeria',
                'method_type': 'mobile_money',
                'provider_name': 'mtn',
                'country_code': 'NG',
                'is_enabled': False,
                'is_active': False,
                'requires_phone': True,
                'supported_currencies': ['NGN'],
                'min_amount': 100.00,
                'max_amount': 10000000.00,
                'transaction_fee': 0.0100,
                'sandbox_url': 'https://sandbox.mtn.com.ng/momo/api/v1',
                'production_url': 'https://api.mtn.com.ng/momo/api/v1'
            },
            {
                'method_id': 'mobile_money_airtel_ng',
                'display_name': 'Airtel Money Nigeria',
                'method_type': 'mobile_money',
                'provider_name': 'airtel',
                'country_code': 'NG',
                'is_enabled': False,
                'is_active': False,
                'requires_phone': True,
                'supported_currencies': ['NGN'],
                'min_amount': 100.00,
                'max_amount': 10000000.00,
                'transaction_fee': 0.0100,
                'sandbox_url': 'https://sandbox.airtel.com.ng/airtel-money/api/v1',
                'production_url': 'https://api.airtel.com.ng/airtel-money/api/v1'
            }
        ]
        
        for default_config in defaults:
            existing = cls.query.filter_by(method_id=default_config['method_id']).first()
            if not existing:
                config = cls(**default_config)
                db.session.add(config)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e


class EventPaymentPreference(db.Model):
    """
    Event owner's payment preferences for their events
    Allows event owners to specify which payment methods they accept
    """
    __tablename__ = 'event_payment_preferences'
    
    id = Column(Integer, primary_key=True)
    
    # Event identification
    event_id = Column(Integer, ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # Payment method preferences
    accepted_methods = Column(JSON, default=list)  # List of method_ids
    preferred_currency = Column(String(3), nullable=False, default='UGX')
    
    # Wallet preferences
    auto_convert_wallet = Column(Boolean, default=True, nullable=False)
    wallet_conversion_rate = Column(db.Numeric(10, 6), default=1.000000, nullable=False)
    
    # Additional settings
    payment_settings = Column(JSON, default=dict)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    event = relationship("Event", backref="payment_preferences")
    user = relationship("User", foreign_keys=[user_id])
    
    def __init__(self, event_id, user_id, preferred_currency='UGX'):
        self.event_id = event_id
        self.user_id = user_id
        self.preferred_currency = preferred_currency
    
    def accepts_method(self, method_id):
        """Check if event accepts this payment method"""
        return method_id in self.accepted_methods
    
    def set_accepted_methods(self, method_ids):
        """Set accepted payment methods"""
        self.accepted_methods = method_ids
    
    def get_available_methods(self):
        """Get available payment methods for this event"""
        from .payment_config import PaymentMethodConfig
        
        available_methods = PaymentMethodConfig.get_available_methods(self.preferred_currency)
        return [m for m in available_methods if m.method_id in self.accepted_methods]
    
    @classmethod
    def get_or_create(cls, event_id, user_id, preferred_currency='UGX'):
        """Get or create payment preference for an event"""
        preference = cls.query.filter_by(event_id=event_id).first()
        if not preference:
            preference = cls(event_id=event_id, user_id=user_id, preferred_currency=preferred_currency)
            # Default to accepting all available methods
            from .payment_config import PaymentMethodConfig
            available_methods = PaymentMethodConfig.get_available_methods(preferred_currency)
            preference.set_accepted_methods([m.method_id for m in available_methods])
            db.session.add(preference)
            db.session.commit()
        return preference
