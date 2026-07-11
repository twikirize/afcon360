from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Boolean,
    String,
    Integer,
    DateTime,
    JSON,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel


class AuthConfiguration(BaseModel):
    """
    Stores authentication and verification service settings.
    Only accessible by app owner role.
    """
    __tablename__ = "auth_configurations"
    
    # Google OAuth
    google_oauth_enabled = Column(Boolean, default=True, nullable=False)
    google_client_id = Column(String(255), nullable=True)
    google_client_secret = Column(String(255), nullable=True)
    
    # SendGrid Email Service
    sendgrid_enabled = Column(Boolean, default=True, nullable=False)
    sendgrid_api_key = Column(String(255), nullable=True)
    sendgrid_from_email = Column(String(255), nullable=True)
    sendgrid_from_name = Column(String(255), default="AFCON360", nullable=True)
    
    # Twilio SMS Service (Global)
    twilio_enabled = Column(Boolean, default=False, nullable=False)
    twilio_account_sid = Column(String(255), nullable=True)
    twilio_auth_token = Column(String(255), nullable=True)
    twilio_phone_number = Column(String(255), nullable=True)
    
    # Africa's Talking SMS Service (Africa)
    africa_talking_enabled = Column(Boolean, default=False, nullable=False)
    africa_talking_username = Column(String(255), nullable=True)
    africa_talking_api_key = Column(String(255), nullable=True)
    
    # SMS Routing Configuration
    sms_provider_preference = Column(
        String(50), 
        default='auto', 
        nullable=False
    )  # Options: auto, twilio, africa_talking
    african_countries = Column(
        JSON, 
        default=lambda: ['UG', 'KE', 'TZ', 'RW', 'BI', 'CD', 'SS', 'ET', 'SO', 'DZ', 'AO', 'BW', 'NA', 'ZA', 'ZW', 'ZM', 'MW', 'MZ', 'NG', 'GH', 'CI', 'SN', 'ML', 'BF', 'NE', 'TD', 'SD', 'LY', 'EG', 'MA', 'TN', 'DZ'],
        nullable=False
    )
    
    # Feature Flags - Verification Requirements
    email_verification_required = Column(Boolean, default=False, nullable=False)
    phone_verification_required = Column(Boolean, default=False, nullable=False)
    google_oauth_required = Column(Boolean, default=False, nullable=False)
    
    # Feature Flags - KYC Requirements
    kyc_required_for_tier_2 = Column(Boolean, default=True, nullable=False)
    kyc_required_for_tier_3 = Column(Boolean, default=True, nullable=False)
    
    # Feature Flags - Signup Restrictions
    allow_email_password_signup = Column(Boolean, default=True, nullable=False)
    allow_google_oauth_signup = Column(Boolean, default=True, nullable=False)
    
    # Rate Limiting
    email_verification_rate_limit = Column(Integer, default=5, nullable=False)  # Per hour
    sms_verification_rate_limit = Column(Integer, default=3, nullable=False)  # Per hour
    
    # Audit fields
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    updated_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Relationships
    updater = relationship('User', foreign_keys=[updated_by])
    
    def __repr__(self):
        return f"<AuthConfiguration id={self.id} google_oauth={self.google_oauth_enabled}>"
    
    def get_active_sms_provider(self, country_code):
        """
        Determine which SMS provider to use based on configuration and location.
        
        Args:
            country_code: 2-letter ISO country code (e.g., 'UG', 'US')
            
        Returns:
            String: 'twilio' or 'africa_talking'
        """
        if self.sms_provider_preference == 'twilio':
            return 'twilio' if self.twilio_enabled else None
        elif self.sms_provider_preference == 'africa_talking':
            return 'africa_talking' if self.africa_talking_enabled else None
        
        # Auto routing based on location
        if country_code in self.african_countries:
            if self.africa_talking_enabled:
                return 'africa_talking'
            elif self.twilio_enabled:
                return 'twilio'
        else:
            if self.twilio_enabled:
                return 'twilio'
            elif self.africa_talking_enabled:
                return 'africa_talking'
        
        return None
    
    @classmethod
    def get_config(cls):
        """Get the current auth configuration (singleton pattern)"""
        config = cls.query.first()
        if not config:
            # Create default configuration
            config = cls(
                google_oauth_enabled=True,
                sendgrid_enabled=True,
                twilio_enabled=False,
                africa_talking_enabled=False,
                sms_provider_preference='auto',
                email_verification_required=False,
                phone_verification_required=False,
                google_oauth_required=False,
                allow_email_password_signup=True,
                allow_google_oauth_signup=True,
            )
            db.session.add(config)
            db.session.commit()
        return config
    
    def to_dict(self, include_secrets=False):
        """
        Convert configuration to dictionary.
        Secrets are excluded by default for security.
        
        Args:
            include_secrets: If True, include API keys and secrets
            
        Returns:
            Dictionary representation
        """
        data = {
            'id': self.id,
            'google_oauth_enabled': self.google_oauth_enabled,
            'sendgrid_enabled': self.sendgrid_enabled,
            'twilio_enabled': self.twilio_enabled,
            'africa_talking_enabled': self.africa_talking_enabled,
            'sms_provider_preference': self.sms_provider_preference,
            'african_countries': self.african_countries,
            'email_verification_required': self.email_verification_required,
            'phone_verification_required': self.phone_verification_required,
            'google_oauth_required': self.google_oauth_required,
            'kyc_required_for_tier_2': self.kyc_required_for_tier_2,
            'kyc_required_for_tier_3': self.kyc_required_for_tier_3,
            'allow_email_password_signup': self.allow_email_password_signup,
            'allow_google_oauth_signup': self.allow_google_oauth_signup,
            'email_verification_rate_limit': self.email_verification_rate_limit,
            'sms_verification_rate_limit': self.sms_verification_rate_limit,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_secrets:
            data.update({
                'google_client_id': self.google_client_id,
                'google_client_secret': self.google_client_secret,
                'sendgrid_api_key': self.sendgrid_api_key,
                'sendgrid_from_email': self.sendgrid_from_email,
                'sendgrid_from_name': self.sendgrid_from_name,
                'twilio_account_sid': self.twilio_account_sid,
                'twilio_auth_token': self.twilio_auth_token,
                'twilio_phone_number': self.twilio_phone_number,
                'africa_talking_username': self.africa_talking_username,
                'africa_talking_api_key': self.africa_talking_api_key,
            })
        
        return data
