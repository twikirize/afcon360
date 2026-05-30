# Authentication & Verification System Architecture

## Overview

This document outlines the authentication and verification system for AFCON360, designed to be cost-effective, scalable, and configurable through an owner settings dashboard.

## Architecture Goals

1. **Zero Development Investment**: Use free tiers for development and small-scale deployment
2. **Easy Switching**: Seamlessly switch between services as needs grow
3. **Location-Aware Routing**: Route SMS based on user location (Africa vs Global)
4. **Feature Flags**: Enable/disable verification requirements without code changes
5. **Owner Control**: App owner can configure all settings via dashboard

## Selected Services

### 1. Google OAuth (Primary Authentication)
- **Cost**: FREE - No per-user charges
- **Purpose**: Primary signup/login method
- **Benefits**: 
  - Auto-verified email from Google
  - No email verification needed
  - Reduced signup friction
  - No password management
- **Implementation**: OAuth 2.0 with Flask

### 2. SendGrid (Email Service)
- **Free Tier**: 100 emails/day
- **Paid Tier**: $15/month for 40,000 emails
- **Purpose**: Email verification for non-Google users
- **Fallback**: Self-hosted SMTP for development

### 3. Twilio (Global SMS)
- **Cost**: $0.0079 per SMS to Uganda
- **Free Trial**: $15 credit (~1,898 SMS)
- **Purpose**: SMS verification for global users
- **Coverage**: 180+ countries

### 4. Africa's Talking (African SMS)
- **Cost**: $0.004 per SMS to Uganda
- **Purpose**: SMS verification for African users
- **Coverage**: 20+ African countries
- **Advantage**: Best rates in Africa

## System Components

### 1. AuthConfiguration Model
Stores service settings and feature flags:

```python
class AuthConfiguration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Google OAuth
    google_oauth_enabled = db.Column(db.Boolean, default=True)
    google_client_id = db.Column(db.String)
    google_client_secret = db.Column(db.String)
    
    # SendGrid
    sendgrid_enabled = db.Column(db.Boolean, default=True)
    sendgrid_api_key = db.Column(db.String)
    sendgrid_from_email = db.Column(db.String)
    
    # Twilio
    twilio_enabled = db.Column(db.Boolean, default=False)
    twilio_account_sid = db.Column(db.String)
    twilio_auth_token = db.Column(db.String)
    twilio_phone_number = db.Column(db.String)
    
    # Africa's Talking
    africa_talking_enabled = db.Column(db.Boolean, default=False)
    africa_talking_username = db.Column(db.String)
    africa_talking_api_key = db.Column(db.String)
    
    # SMS Routing
    sms_provider_preference = db.Column(db.String, default='auto')  # auto, twilio, africa_talking
    african_countries = db.Column(db.JSON)  # List of country codes for Africa's Talking
    
    # Feature Flags
    email_verification_required = db.Column(db.Boolean, default=False)
    phone_verification_required = db.Column(db.Boolean, default=False)
    google_oauth_required = db.Column(db.Boolean, default=False)
    
    # KYC Requirements
    kyc_required_for_tier_2 = db.Column(db.Boolean, default=True)
    kyc_required_for_tier_3 = db.Column(db.Boolean, default=True)
    
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
```

### 2. SMS Routing Service

Routes SMS based on user location and configuration:

```python
class SMSService:
    def send_verification(self, phone_number, country_code, code):
        """
        Route SMS to appropriate provider based on:
        1. Owner preference setting
        2. User location (Africa vs Global)
        3. Provider availability
        """
        config = AuthConfiguration.query.first()
        
        # Check owner preference
        if config.sms_provider_preference == 'twilio':
            return self._send_via_twilio(phone_number, code)
        elif config.sms_provider_preference == 'africa_talking':
            return self._send_via_africa_talking(phone_number, code)
        
        # Auto routing based on location
        if country_code in config.african_countries:
            if config.africa_talking_enabled:
                return self._send_via_africa_talking(phone_number, code)
            else:
                return self._send_via_twilio(phone_number, code)
        else:
            return self._send_via_twilio(phone_number, code)
```

### 3. Feature Flag Service

Checks if verification requirements are enabled:

```python
class VerificationService:
    def is_email_verification_required(self):
        config = AuthConfiguration.query.first()
        return config.email_verification_required
    
    def is_phone_verification_required(self):
        config = AuthConfiguration.query.first()
        return config.phone_verification_required
    
    def is_google_oauth_required(self):
        config = AuthConfiguration.query.first()
        return config.google_oauth_required
```

### 4. Owner Settings Dashboard

UI for configuring all auth services:

**Location**: `/admin/owner/settings/auth`

**Features**:
- Enable/disable each service
- Enter API credentials
- Set feature flags
- Configure SMS routing rules
- Test service connectivity
- View usage statistics

## Implementation Phases

### Phase 1: Core Infrastructure (Priority 1)
- [ ] Create AuthConfiguration model
- [ ] Create migration for new table
- [ ] Create owner auth settings routes
- [ ] Create settings.html template
- [ ] Implement feature flag service

### Phase 2: Google OAuth (Priority 1)
- [ ] Install authlib library
- [ ] Configure Google OAuth credentials
- [ ] Implement OAuth callback routes
- [ ] Auto-verify email from Google
- [ ] Update signup/login templates

### Phase 3: SendGrid Integration (Priority 2)
- [ ] Install sendgrid library
- [ ] Configure SendGrid API
- [ ] Implement email verification service
- [ ] Update email templates
- [ ] Add test email functionality

### Phase 4: SMS Services (Priority 3)
- [ ] Install Twilio library
- [ ] Install Africa's Talking SDK
- [ ] Implement Twilio SMS service
- [ ] Implement Africa's Talking SMS service
- [ ] Create SMS routing logic
- [ ] Add test SMS functionality

### Phase 5: Integration (Priority 4)
- [ ] Update signup flow with feature flags
- [ ] Update KYC verification flow
- [ ] Update profile completion logic
- [ ] Add error handling for disabled services
- [ ] Create monitoring dashboard

## Configuration Settings

### Development Mode (Free Tiers)
```yaml
google_oauth_enabled: true
sendgrid_enabled: true
twilio_enabled: false
africa_talking_enabled: false
email_verification_required: false
phone_verification_required: false
google_oauth_required: false
```

### Production Mode (Small Scale)
```yaml
google_oauth_enabled: true
sendgrid_enabled: true (free tier)
twilio_enabled: false
africa_talking_enabled: false
email_verification_required: true
phone_verification_required: false
google_oauth_required: false
```

### Production Mode (Scale)
```yaml
google_oauth_enabled: true
sendgrid_enabled: true (paid tier)
twilio_enabled: true
africa_talking_enabled: true
email_verification_required: true
phone_verification_required: true
google_oauth_required: false
sms_provider_preference: auto
```

## Cost Projections

### Development (0 users)
- Google OAuth: $0
- SendGrid: $0
- Twilio: $0
- Africa's Talking: $0
- **Total: $0/month**

### Small Scale (100 users/month)
- Google OAuth: $0
- SendGrid: $0 (100 emails/day free tier)
- SMS: $0 (not required initially)
- **Total: $0/month**

### Medium Scale (1,000 users/month)
- Google OAuth: $0
- SendGrid: $0 (100 emails/day sufficient)
- SMS: $4/month (1,000 SMS via Africa's Talking)
- **Total: $4/month**

### Large Scale (10,000 users/month)
- Google OAuth: $0
- SendGrid: $15/month (40,000 emails)
- SMS: $40/month (10,000 SMS via Africa's Talking)
- **Total: $55/month**

## Security Considerations

1. **API Key Storage**: Encrypt all API keys in database
2. **Credential Rotation**: Support for rotating API keys
3. **Access Control**: Only owner role can access settings
4. **Audit Logging**: Log all configuration changes
5. **Fallback Mechanisms**: Graceful degradation when services fail

## Monitoring & Alerts

1. **Service Health**: Monitor API availability
2. **Usage Tracking**: Track email/SMS usage
3. **Cost Alerts**: Alert when approaching limits
4. **Error Logging**: Log failed verification attempts
5. **Success Rates**: Monitor verification success rates

## Migration Path

From Development to Production:
1. Upgrade SendGrid to paid tier when hitting 100 emails/day
2. Enable SMS verification for KYC Tier 2+
3. Configure SMS routing based on user location
4. Monitor costs and adjust as needed

## References

- Google OAuth 2.0: https://developers.google.com/identity/protocols/oauth2
- SendGrid API: https://docs.sendgrid.com/api-reference/
- Twilio API: https://www.twilio.com/docs/sms/api
- Africa's Talking API: https://developers.africastalking.com/
