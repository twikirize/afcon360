# Authentication System Implementation Guide

## Status: Infrastructure Complete, Services Pending

**Last Updated:** 2026-05-04

## What's Been Implemented

### 1. Database Infrastructure ✅

**Model:** `app/auth/config_model.py`

The `AuthConfiguration` model stores all authentication service settings:

```python
class AuthConfiguration(BaseModel):
    # Google OAuth
    google_oauth_enabled
    google_client_id
    google_client_secret
    
    # SendGrid
    sendgrid_enabled
    sendgrid_api_key
    sendgrid_from_email
    sendgrid_from_name
    
    # Twilio
    twilio_enabled
    twilio_account_sid
    twilio_auth_token
    twilio_phone_number
    
    # Africa's Talking
    africa_talking_enabled
    africa_talking_username
    africa_talking_api_key
    
    # SMS Routing
    sms_provider_preference  # auto, twilio, africa_talking
    african_countries  # JSON list of country codes
    
    # Feature Flags
    email_verification_required
    phone_verification_required
    google_oauth_required
    kyc_required_for_tier_2
    kyc_required_for_tier_3
    allow_email_password_signup
    allow_google_oauth_signup
    
    # Rate Limiting
    email_verification_rate_limit
    sms_verification_rate_limit
```

**Migration:** `migrations/versions/add_auth_configuration_table.py` ✅ Applied successfully

**Database Table:** `auth_configurations` created with default configuration

---

### 2. Owner Settings Dashboard ✅

**Route:** `/owner/settings/auth` (GET, POST)

**File:** `app/admin/owner/routes.py` (lines 1402-1547)

**Features:**
- Update all service configurations
- Enable/disable services with toggles
- Enter API credentials
- Configure SMS routing strategy
- Set feature flags
- Configure rate limits
- Test service connectivity

**Template:** `templates/admin/owner/auth_settings.html`

**Features:**
- Modern UI with service cards
- Enable/disable toggles for each service
- API credential input fields
- Cost badges showing free/paid tiers
- Test connection buttons
- Feature flag switches
- Rate limit configuration
- SMS routing strategy selector

---

## What's Pending Implementation

### 1. Google OAuth Integration

**Status:** Not implemented

**Required Steps:**
1. Install `authlib` library
   ```bash
   pip install authlib
   ```

2. Add to `requirements.txt`:
   ```
   authlib>=1.3.0
   ```

3. Create OAuth service in `app/auth/oauth_service.py`:
   ```python
   from authlib.integrations.flask_client import OAuth
   from flask import session
   
   oauth = OAuth()
   
   def init_google_oauth(app):
       config = AuthConfiguration.get_config()
       if config.google_oauth_enabled:
           oauth.register(
               name='google',
               client_id=config.google_client_id,
               client_secret=config.google_client_secret,
               server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
               client_kwargs={
                   'scope': 'openid email profile'
               }
           )
   
   def get_google_auth_url():
       return url_for('google.login', _external=True)
   ```

4. Create OAuth routes in `app/auth/oauth_routes.py`:
   ```python
   @auth_bp.route('/login/google')
   def login_google():
       redirect_uri = url_for('google.authorize', _external=True)
       return oauth.google.authorize_redirect(redirect_uri)
   
   @auth_bp.route('/authorize/google')
   def authorize_google():
       token = oauth.google.authorize_access_token()
       user_info = token['userinfo']
       # Create or update user account
       # Auto-verify email from Google
       return redirect(url_for('profile.account_overview'))
   ```

5. Update signup template to include Google OAuth button

**Google Cloud Console Setup:**
1. Go to https://console.cloud.google.com
2. Create new project
3. Enable Google+ API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URIs (e.g., `http://localhost:5000/authorize/google`)
6. Copy Client ID and Client Secret to owner settings

---

### 2. SendGrid Email Service

**Status:** Not implemented

**Required Steps:**
1. Install SendGrid library
   ```bash
   pip install sendgrid
   ```

2. Add to `requirements.txt`:
   ```
   sendgrid>=6.10.0
   ```

3. Create email service in `app/services/email_service.py`:
   ```python
   from sendgrid import SendGridAPIClient
   from sendgrid.helpers.mail import Mail
   
   def send_verification_email(email, verification_code):
       config = AuthConfiguration.get_config()
       if not config.sendgrid_enabled:
           # Fallback to console log
           print(f"Email verification code for {email}: {verification_code}")
           return True
       
       message = Mail(
           from_email=config.sendgrid_from_email,
           to_emails=email,
           subject='Verify your AFCON360 account',
           html_content=f'<p>Your verification code is: <strong>{verification_code}</strong></p>'
       )
       
       sg = SendGridAPIClient(config.sendgrid_api_key)
       response = sg.send(message)
       return response.status_code == 202
   ```

4. Update signup flow to use email service

**SendGrid Setup:**
1. Sign up at https://sendgrid.com
2. Create API key
3. Verify sender email/domain
4. Copy API key to owner settings

---

### 3. Twilio SMS Service

**Status:** Not implemented

**Required Steps:**
1. Install Twilio library
   ```bash
   pip install twilio
   ```

2. Add to `requirements.txt`:
   ```
   twilio>=8.10.0
   ```

3. Create SMS service in `app/services/sms_service.py`:
   ```python
   from twilio.rest import Client
   
   def send_sms_via_twilio(phone_number, message):
       config = AuthConfiguration.get_config()
       if not config.twilio_enabled:
           return False
       
       client = Client(config.twilio_account_sid, config.twilio_auth_token)
       message = client.messages.create(
           body=message,
           from_=config.twilio_phone_number,
           to=phone_number
       )
       return message.sid is not None
   ```

**Twilio Setup:**
1. Sign up at https://www.twilio.com
2. Get Account SID and Auth Token
3. Purchase phone number
4. Copy credentials to owner settings

---

### 4. Africa's Talking SMS Service

**Status:** Not implemented

**Required Steps:**
1. Install Africa's Talking SDK
   ```bash
   pip install africastalking
   ```

2. Add to `requirements.txt`:
   ```
   africastalking>=1.2.0
   ```

3. Add to SMS service:
   ```python
   from africastalking.AfricasTalking import AfricasTalking
   
   def send_sms_via_africa_talking(phone_number, message):
       config = AuthConfiguration.get_config()
       if not config.africa_talking_enabled:
           return False
       
       at = AfricasTalking(config.africa_talking_username, config.africa_talking_api_key)
       result = at.sms.send(message, [phone_number])
       return result['SMSMessageData']['Recipients'][0]['status'] == 'Success'
   ```

**Africa's Talking Setup:**
1. Sign up at https://africastalking.com
2. Get username and API key
3. Copy credentials to owner settings

---

### 5. SMS Routing Logic

**Status:** Not implemented

**Create in `app/services/sms_routing_service.py`:**
```python
class SMSRoutingService:
    @staticmethod
    def send_verification_sms(phone_number, country_code, code):
        """
        Route SMS to appropriate provider based on configuration and location.
        """
        config = AuthConfiguration.get_config()
        message = f"Your AFCON360 verification code is: {code}"
        
        provider = config.get_active_sms_provider(country_code)
        
        if provider == 'twilio':
            return send_sms_via_twilio(phone_number, message)
        elif provider == 'africa_talking':
            return send_sms_via_africa_talking(phone_number, message)
        else:
            # Fallback: log to console
            print(f"SMS verification code for {phone_number}: {code}")
            return True
```

---

### 6. Feature Flags Integration

**Status:** Not implemented

**Create service in `app/auth/feature_flags.py`:**
```python
class FeatureFlags:
    @staticmethod
    def is_email_verification_required():
        config = AuthConfiguration.get_config()
        return config.email_verification_required
    
    @staticmethod
    def is_phone_verification_required():
        config = AuthConfiguration.get_config()
        return config.phone_verification_required
    
    @staticmethod
    def is_google_oauth_required():
        config = AuthConfiguration.get_config()
        return config.google_oauth_required
    
    @staticmethod
    def can_signup_with_email_password():
        config = AuthConfiguration.get_config()
        return config.allow_email_password_signup
    
    @staticmethod
    def can_signup_with_google_oauth():
        config = AuthConfiguration.get_config()
        return config.allow_google_oauth_signup
```

**Update signup flow:**
```python
@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if not FeatureFlags.can_signup_with_email_password():
        flash('Email/password signup is disabled. Please use Google OAuth.', 'warning')
        return redirect(url_for('auth.login_google'))
    
    # ... existing signup logic ...
    
    if FeatureFlags.is_email_verification_required():
        send_verification_email(user.email, verification_code)
```

---

## How to Use the Auth Settings Dashboard

1. **Navigate to:** `http://localhost:5000/owner/settings/auth`

2. **Configure Services:**
   - Toggle services on/off
   - Enter API credentials
   - Test connections

3. **Set Feature Flags:**
   - Enable/disable verification requirements
   - Control signup methods
   - Configure KYC requirements

4. **Configure SMS Routing:**
   - Choose auto routing (recommended)
   - Or force specific provider

---

## Cost Summary

### Development (Current State)
- Google OAuth: $0
- SendGrid: $0 (not configured)
- Twilio: $0 (not configured)
- Africa's Talking: $0 (not configured)
- **Total: $0/month**

### Production with Free Tiers
- Google OAuth: $0
- SendGrid: $0 (100 emails/day)
- SMS: Pay as needed
- **Total: $0 + SMS costs**

### Production Scale (10,000 users/month)
- Google OAuth: $0
- SendGrid: $15/month
- SMS: $40/month (Africa's Talking)
- **Total: $55/month**

---

## Next Steps

1. **Immediate:**
   - Install required libraries (authlib, sendgrid, twilio, africastalking)
   - Update requirements.txt
   - Test owner settings dashboard

2. **Phase 1 - Google OAuth:**
   - Implement Google OAuth service
   - Create OAuth routes
   - Update signup/login templates
   - Test with Google Cloud Console credentials

3. **Phase 2 - SendGrid:**
   - Implement email service
   - Update verification flow
   - Test with SendGrid API

4. **Phase 3 - SMS:**
   - Implement Twilio service
   - Implement Africa's Talking service
   - Create routing logic
   - Test SMS delivery

5. **Phase 4 - Feature Flags:**
   - Integrate feature flags into signup flow
   - Update KYC verification
   - Test all configurations

---

## Testing Checklist

- [ ] Owner can access `/owner/settings/auth`
- [ ] Service toggles work correctly
- [ ] API credentials save to database
- [ ] Feature flags save to database
- [ ] Test connection buttons work (after services implemented)
- [ ] SMS routing configuration saves correctly
- [ ] Rate limits save correctly

---

## Security Notes

1. **API Keys:** Stored in database, should be encrypted in production
2. **Access Control:** Only owner role can access settings
3. **Audit Logging:** All configuration changes are logged
4. **Fallback:** If service is disabled, system logs to console

---

## References

- Architecture Document: `app/Documentation/AUTH_SYSTEM_ARCHITECTURE.md`
- Model: `app/auth/config_model.py`
- Routes: `app/admin/owner/routes.py` (lines 1402-1547)
- Template: `templates/admin/owner/auth_settings.html`
- Migration: `migrations/versions/add_auth_configuration_table.py`
