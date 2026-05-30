"""
Payment Provider Configuration Model
Stores API keys and settings securely in database with encryption
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from app.extensions import db
from cryptography.fernet import Fernet
from flask import current_app


class PaymentProviderConfig(db.Model):
    """
    Configuration for payment providers (Flutterwave, Paystack, etc.)
    API keys are encrypted at rest
    """
    __tablename__ = 'payment_provider_configs'
    
    id = Column(Integer, primary_key=True)
    
    # Provider identification
    provider_name = Column(String(50), nullable=False, unique=True, index=True)
    display_name = Column(String(100), nullable=False)
    
    # Environment (sandbox/production)
    is_sandbox = Column(Boolean, default=True, nullable=False)
    
    # API Credentials (encrypted)
    _secret_key = Column('secret_key', Text, nullable=True)
    _public_key = Column('public_key', Text, nullable=True)
    _encryption_key = Column('encryption_key', Text, nullable=True)
    
    # Additional configuration (JSON)
    config_json = Column(JSON, default=dict)
    
    # Webhook settings
    webhook_url = Column(String(255), nullable=True)
    webhook_secret = Column(String(255), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=False, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)  # Kill switch
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, nullable=True)  # User ID who last updated
    
    # Audit
    last_tested_at = Column(DateTime, nullable=True)
    last_test_result = Column(String(20), nullable=True)  # success, failed
    last_error_message = Column(Text, nullable=True)
    
    def __init__(self, provider_name, display_name, is_sandbox=True):
        self.provider_name = provider_name
        self.display_name = display_name
        self.is_sandbox = is_sandbox
    
    @property
    def secret_key(self):
        """Decrypt and return secret key"""
        if not self._secret_key:
            return None
        try:
            return self._decrypt(self._secret_key)
        except Exception as e:
            current_app.logger.error(f"Failed to decrypt secret key for {self.provider_name}: {e}")
            return None
    
    @secret_key.setter
    def secret_key(self, value):
        """Encrypt and store secret key"""
        if value:
            self._secret_key = self._encrypt(value)
        else:
            self._secret_key = None
    
    @property
    def public_key(self):
        """Decrypt and return public key"""
        if not self._public_key:
            return None
        try:
            return self._decrypt(self._public_key)
        except Exception as e:
            current_app.logger.error(f"Failed to decrypt public key for {self.provider_name}: {e}")
            return None
    
    @public_key.setter
    def public_key(self, value):
        """Encrypt and store public key"""
        if value:
            self._public_key = self._encrypt(value)
        else:
            self._public_key = None
    
    @property
    def encryption_key(self):
        """Decrypt and return encryption key"""
        if not self._encryption_key:
            return None
        try:
            return self._decrypt(self._encryption_key)
        except Exception as e:
            current_app.logger.error(f"Failed to decrypt encryption key for {self.provider_name}: {e}")
            return None
    
    @encryption_key.setter
    def encryption_key(self, value):
        """Encrypt and store encryption key"""
        if value:
            self._encryption_key = self._encrypt(value)
        else:
            self._encryption_key = None
    
    def _get_fernet(self):
        """Get Fernet instance for encryption/decryption"""
        # Use app's encryption key or generate from SECRET_KEY
        encryption_key = current_app.config.get('DB_ENCRYPTION_KEY')
        if not encryption_key:
            # Derive from SECRET_KEY if no specific DB encryption key
            import base64
            import hashlib
            secret = current_app.config.get('SECRET_KEY', 'default-secret')
            key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
            encryption_key = key
        
        return Fernet(encryption_key)
    
    def _encrypt(self, plaintext):
        """Encrypt plaintext"""
        f = self._get_fernet()
        return f.encrypt(plaintext.encode()).decode()
    
    def _decrypt(self, ciphertext):
        """Decrypt ciphertext"""
        f = self._get_fernet()
        return f.decrypt(ciphertext.encode()).decode()
    
    def to_dict(self, include_secrets=False):
        """Convert to dictionary (secrets masked by default)"""
        data = {
            "id": self.id,
            "provider_name": self.provider_name,
            "display_name": self.display_name,
            "is_sandbox": self.is_sandbox,
            "is_active": self.is_active,
            "is_enabled": self.is_enabled,
            "webhook_url": self.webhook_url,
            "config_json": self.config_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_tested_at": self.last_tested_at.isoformat() if self.last_tested_at else None,
            "last_test_result": self.last_test_result,
            "has_secret_key": bool(self._secret_key),
            "has_public_key": bool(self._public_key),
        }
        
        if include_secrets:
            data["secret_key"] = self.secret_key
            data["public_key"] = self.public_key
            data["encryption_key"] = self.encryption_key
        else:
            # Mask the keys
            if self._secret_key:
                data["secret_key_preview"] = f"{self.secret_key[:8]}...{self.secret_key[-4:]}" if self.secret_key else None
            if self._public_key:
                data["public_key_preview"] = f"{self.public_key[:8]}...{self.public_key[-4:]}" if self.public_key else None
        
        return data
    
    def test_connection(self):
        """Test connection to payment provider"""
        # This would be implemented per provider
        # For now, just check if keys are present
        if not self.secret_key:
            return False, "Secret key not configured"
        
        # Provider-specific test logic would go here
        return True, "Configuration valid"
    
    @classmethod
    def get_active_config(cls, provider_name):
        """Get active configuration for a provider"""
        return cls.query.filter_by(
            provider_name=provider_name,
            is_active=True,
            is_enabled=True
        ).first()
    
    @classmethod
    def get_all_configs(cls):
        """Get all provider configurations"""
        return cls.query.all()
    
    @classmethod
    def initialize_defaults(cls):
        """Initialize default provider configurations"""
        defaults = [
            {
                "provider_name": "flutterwave",
                "display_name": "Flutterwave",
                "is_sandbox": True,
                "config_json": {
                    "base_url": "https://api.flutterwave.com/v3",
                    "sandbox_url": "https://api.flutterwave.com/v3",
                    "supported_countries": ["NG", "GH", "KE", "UG", "ZA", "TZ"],
                    "supported_methods": ["card", "bank_transfer", "mobile_money", "ussd"]
                }
            },
            {
                "provider_name": "paystack",
                "display_name": "Paystack",
                "is_sandbox": True,
                "config_json": {
                    "base_url": "https://api.paystack.co",
                    "supported_countries": ["NG", "GH"],
                    "supported_methods": ["card", "bank_transfer", "ussd", "qr"]
                }
            },
            {
                "provider_name": "mtn_momo",
                "display_name": "MTN Mobile Money",
                "is_sandbox": True,
                "config_json": {
                    "supported_countries": ["UG", "GH", "CM", "CI", "RW", "ZA", "ZM"],
                    "supported_methods": ["mobile_money"]
                }
            },
            {
                "provider_name": "airtel_money",
                "display_name": "Airtel Money",
                "is_sandbox": True,
                "config_json": {
                    "supported_countries": ["UG", "KE", "TZ", "ZM", "MW", "RW"],
                    "supported_methods": ["mobile_money"]
                }
            }
        ]
        
        for config_data in defaults:
            existing = cls.query.filter_by(provider_name=config_data["provider_name"]).first()
            if not existing:
                config = cls(**config_data)
                db.session.add(config)
        
        db.session.commit()


class WalletSystemConfig(db.Model):
    """
    General wallet system configuration
    Transaction limits, fees, etc.
    """
    __tablename__ = 'wallet_system_configs'
    
    id = Column(Integer, primary_key=True)
    
    # Feature flags
    deposits_enabled = Column(Boolean, default=True, nullable=False)
    withdrawals_enabled = Column(Boolean, default=True, nullable=False)
    transfers_enabled = Column(Boolean, default=True, nullable=False)
    fx_enabled = Column(Boolean, default=True, nullable=False)
    
    # Transaction limits
    max_deposit_amount = Column(db.Numeric(18, 2), default=1000000)  # Default 1M
    max_withdrawal_amount = Column(db.Numeric(18, 2), default=500000)  # Default 500K
    max_transfer_amount = Column(db.Numeric(18, 2), default=1000000)  # Default 1M
    
    # Fee settings (percentage)
    deposit_fee_percent = Column(db.Numeric(5, 2), default=0)  # No fee
    withdrawal_fee_percent = Column(db.Numeric(5, 2), default=1)  # 1%
    transfer_fee_percent = Column(db.Numeric(5, 2), default=0.5)  # 0.5%
    fx_spread_percent = Column(db.Numeric(5, 2), default=1.5)  # 1.5%
    
    # Notification settings
    notify_large_transactions = Column(Boolean, default=True)
    large_transaction_threshold = Column(db.Numeric(18, 2), default=10000)
    
    # Compliance settings
    require_kyc_for_deposits = Column(Boolean, default=False)
    require_kyc_for_withdrawals = Column(Boolean, default=True)
    require_kyc_for_transfers = Column(Boolean, default=False)
    
    # Audit
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, nullable=True)
    
    @classmethod
    def get_config(cls):
        """Get or create system config"""
        config = cls.query.first()
        if not config:
            config = cls()
            db.session.add(config)
            db.session.commit()
        return config
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "deposits_enabled": self.deposits_enabled,
            "withdrawals_enabled": self.withdrawals_enabled,
            "transfers_enabled": self.transfers_enabled,
            "fx_enabled": self.fx_enabled,
            "max_deposit_amount": float(self.max_deposit_amount),
            "max_withdrawal_amount": float(self.max_withdrawal_amount),
            "max_transfer_amount": float(self.max_transfer_amount),
            "deposit_fee_percent": float(self.deposit_fee_percent),
            "withdrawal_fee_percent": float(self.withdrawal_fee_percent),
            "transfer_fee_percent": float(self.transfer_fee_percent),
            "fx_spread_percent": float(self.fx_spread_percent),
            "notify_large_transactions": self.notify_large_transactions,
            "large_transaction_threshold": float(self.large_transaction_threshold),
            "require_kyc_for_deposits": self.require_kyc_for_deposits,
            "require_kyc_for_withdrawals": self.require_kyc_for_withdrawals,
            "require_kyc_for_transfers": self.require_kyc_for_transfers,
        }


__all__ = ['PaymentProviderConfig', 'WalletSystemConfig']
</CodeContent>
<parameter=EmptyFile>false</parameter>
</function>

<function=write_to_file>
<parameter=TargetFile>C:\Users\ADMIN\Desktop\afcon360_app\app\admin\owner\wallet_config.py
