"""
Organisation Payment Gateway Configuration
Allows each organisation to configure their own payment gateways for receiving funds,
refunds, fines, etc.
"""

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, Text, JSON, ForeignKey, Numeric, Enum, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel
import enum


class PaymentGatewayProvider(enum.Enum):
    FLUTTERWAVE = "flutterwave"
    PAYSTACK = "paystack"
    MTN_MOMO = "mtn_momo"
    AIRTEL_MONEY = "airtel_money"
    VISA = "visa"
    MASTERCARD = "mastercard"
    PAYPAL = "paypal"
    ALIPAY = "alipay"
    WECHAT_PAY = "wechat_pay"
    BANK_TRANSFER = "bank_transfer"
    STRIPE = "stripe"
    MPESA = "mpesa"


class PaymentGatewayEnvironment(enum.Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class OrganisationPaymentGateway(BaseModel):
    """
    Organisation-specific payment gateway configuration.
    Each organisation can configure their own credentials for receiving payments.
    """
    __tablename__ = 'organisation_payment_gateways'
    __table_args__ = (
        UniqueConstraint('organisation_id', 'provider', name='uq_org_gateway_provider'),
        Index('ix_org_gateway_org_active', 'organisation_id', 'is_active'),
    )

    organisation_id = Column(BigInteger, ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Gateway identification
    provider = Column(Enum(PaymentGatewayProvider, name='payment_gateway_provider'), nullable=False)
    environment = Column(Enum(PaymentGatewayEnvironment, name='gateway_environment'), default=PaymentGatewayEnvironment.SANDBOX, nullable=False)
    
    # Display
    display_name = Column(String(100), nullable=True)
    
    # API Credentials (encrypted in practice)
    api_key = Column(String(255), nullable=True)           # Public key / Client ID
    api_secret = Column(String(255), nullable=True)        # Secret key / Client Secret
    merchant_id = Column(String(100), nullable=True)       # Merchant ID for card networks
    
    # Additional configuration
    webhook_url = Column(String(500), nullable=True)
    config_json = Column(JSON, default=dict)               # Provider-specific config
    
    # Supported currencies for this gateway
    supported_currencies = Column(JSON, default=list)
    
    # Limits
    min_amount = Column(Numeric(10, 2), default=0.00)
    max_amount = Column(Numeric(10, 2), default=1000000.00)
    
    # Fee configuration
    transaction_fee = Column(Numeric(5, 4), default=0.0000)
    fee_currency = Column(String(3), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    last_test_result = Column(String(20), nullable=True)
    last_error_message = Column(Text, nullable=True)
    
    # Audit
    created_by = Column(BigInteger, nullable=True)
    updated_by = Column(BigInteger, nullable=True)
    
    # Relationships
    organisation = relationship("Organisation", backref="payment_gateways")
    
    def __init__(self, organisation_id, provider, **kwargs):
        self.organisation_id = organisation_id
        self.provider = provider
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    @property
    def is_configured(self):
        """Check if gateway has required credentials"""
        if self.provider in [PaymentGatewayProvider.FLUTTERWAVE, PaymentGatewayProvider.PAYSTACK]:
            return bool(self.api_key and self.api_secret)
        elif self.provider in [PaymentGatewayProvider.VISA, PaymentGatewayProvider.MASTERCARD]:
            return bool(self.merchant_id and self.api_secret)
        elif self.provider == PaymentGatewayProvider.PAYPAL:
            return bool(self.api_key and self.api_secret)
        elif self.provider in [PaymentGatewayProvider.MTN_MOMO, PaymentGatewayProvider.AIRTEL_MONEY, PaymentGatewayProvider.MPESA]:
            return bool(self.api_key and self.api_secret)
        return bool(self.api_key)
    
    @property
    def provider_config(self):
        """Get provider-specific configuration schema"""
        configs = {
            PaymentGatewayProvider.FLUTTERWAVE: {
                'fields': [
                    {'name': 'api_key', 'label': 'Public Key', 'type': 'text', 'required': True},
                    {'name': 'api_secret', 'label': 'Secret Key', 'type': 'password', 'required': True},
                    {'name': 'encryption_key', 'label': 'Encryption Key', 'type': 'password', 'required': True},
                    {'name': 'webhook_url', 'label': 'Webhook URL', 'type': 'url', 'required': False},
                ],
                'currencies': ['UGX', 'KES', 'NGN', 'GHS', 'ZAR', 'USD', 'EUR', 'GBP'],
                'description': 'Flutterwave payment gateway for Africa - supports cards, mobile money, bank transfers'
            },
            PaymentGatewayProvider.PAYSTACK: {
                'fields': [
                    {'name': 'api_key', 'label': 'Public Key', 'type': 'text', 'required': True},
                    {'name': 'api_secret', 'label': 'Secret Key', 'type': 'password', 'required': True},
                    {'name': 'webhook_url', 'label': 'Webhook URL', 'type': 'url', 'required': False},
                ],
                'currencies': ['NGN', 'GHS', 'ZAR', 'USD', 'KES'],
                'description': 'Paystack payment gateway for Nigeria/Ghana - supports cards, bank transfers, mobile money'
            },
            PaymentGatewayProvider.MTN_MOMO: {
                'fields': [
                    {'name': 'api_key', 'label': 'API Key / Subscription Key', 'type': 'text', 'required': True},
                    {'name': 'api_secret', 'label': 'API Secret / Target Environment', 'type': 'password', 'required': True},
                    {'name': 'config_json', 'label': 'Collection Environment', 'type': 'select', 'options': ['sandbox', 'production'], 'required': True},
                ],
                'currencies': ['UGX', 'RWF', 'ZMW', 'XOF', 'XAF'],
                'description': 'MTN Mobile Money for collecting payments via mobile money'
            },
            PaymentGatewayProvider.AIRTEL_MONEY: {
                'fields': [
                    {'name': 'api_key', 'label': 'Client ID', 'type': 'text', 'required': True},
                    {'name': 'api_secret', 'label': 'Client Secret', 'type': 'password', 'required': True},
                    {'name': 'config_json', 'label': 'Country', 'type': 'select', 'options': ['UG', 'KE', 'TZ', 'RW', 'MG', 'ML', 'NE', 'TD'], 'required': True},
                ],
                'currencies': ['UGX', 'KES', 'TZS', 'RWF', 'XOF', 'XAF'],
                'description': 'Airtel Money for collecting payments via mobile money across Africa'
            },
            PaymentGatewayProvider.MPESA: {
                'fields': [
                    {'name': 'api_key', 'label': 'Consumer Key', 'type': 'text', 'required': True},
                    {'name': 'api_secret', 'label': 'Consumer Secret', 'type': 'password', 'required': True},
                    {'name': 'merchant_id', 'label': 'Shortcode / Business ID', 'type': 'text', 'required': True},
                    {'name': 'config_json', 'label': 'Passkey', 'type': 'password', 'required': True},
                ],
                'currencies': ['KES'],
                'description': 'M-PESA (Safaricom) for Kenya - STK Push, B2C, C2B'
            },
            PaymentGatewayProvider.PAYPAL: {
                'fields': [
                    {'name': 'api_key', 'label': 'Client ID', 'type': 'text', 'required': True},
                    {'name': 'api_secret', 'label': 'Client Secret', 'type': 'password', 'required': True},
                    {'name': 'config_json', 'label': 'Webhook ID', 'type': 'text', 'required': False},
                ],
                'currencies': ['USD', 'EUR', 'GBP', 'KES', 'NGN', 'ZAR'],
                'description': 'PayPal for international payments'
            },
            PaymentGatewayProvider.STRIPE: {
                'fields': [
                    {'name': 'api_key', 'label': 'Publishable Key', 'type': 'text', 'required': True},
                    {'name': 'api_secret', 'label': 'Secret Key', 'type': 'password', 'required': True},
                    {'name': 'config_json', 'label': 'Webhook Secret', 'type': 'password', 'required': False},
                ],
                'currencies': ['USD', 'EUR', 'GBP', 'KES', 'NGN', 'ZAR', 'UGX'],
                'description': 'Stripe for international card payments'
            },
            PaymentGatewayProvider.BANK_TRANSFER: {
                'fields': [
                    {'name': 'display_name', 'label': 'Bank Name', 'type': 'text', 'required': True},
                    {'name': 'config_json', 'label': 'Account Name', 'type': 'text', 'required': True},
                    {'name': 'config_json', 'label': 'Account Number', 'type': 'text', 'required': True},
                    {'name': 'config_json', 'label': 'Bank Code / SWIFT', 'type': 'text', 'required': True},
                    {'name': 'config_json', 'label': 'Branch', 'type': 'text', 'required': False},
                ],
                'currencies': ['UGX', 'KES', 'NGN', 'TZS', 'RWF', 'USD', 'EUR', 'GBP'],
                'description': 'Direct bank transfer details for manual reconciliation'
            },
        }
        return configs.get(self.provider, {'fields': [], 'currencies': [], 'description': ''})
    
    def get_config_fields(self):
        """Get configuration fields for this provider"""
        return self.provider_config.get('fields', [])
    
    def get_supported_currencies(self):
        """Get supported currencies for this provider"""
        return self.provider_config.get('currencies', [])
    
    def get_description(self):
        """Get provider description"""
        return self.provider_config.get('description', '')
    
    @classmethod
    def get_for_organisation(cls, organisation_id):
        """Get all payment gateways for an organisation"""
        return cls.query.filter_by(organisation_id=organisation_id).all()
    
    @classmethod
    def get_active_for_organisation(cls, organisation_id):
        """Get active payment gateways for an organisation"""
        return cls.query.filter_by(organisation_id=organisation_id, is_active=True).all()
    
    @classmethod
    def get_by_provider(cls, organisation_id, provider):
        """Get specific gateway for organisation"""
        return cls.query.filter_by(organisation_id=organisation_id, provider=provider).first()
    
    @classmethod
    def create_or_update(cls, organisation_id, provider, **kwargs):
        """Create or update gateway configuration"""
        gateway = cls.get_by_provider(organisation_id, provider)
        if not gateway:
            gateway = cls(organisation_id=organisation_id, provider=provider)
            db.session.add(gateway)
        
        for key, value in kwargs.items():
            if hasattr(gateway, key):
                setattr(gateway, key, value)
        
        gateway.updated_by = kwargs.get('updated_by')
        db.session.commit()
        return gateway