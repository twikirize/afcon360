# afcon 360_1pp/config.py
APP_NAME = "AFCON 360"
TOURNAMENT_NAME = "AFCON 360"
YEAR = 2025
VERSION = "1.0.0"
REQUIRE_EMAIL_VERIFICATION = False

# Email Configuration for Flask-Mail
MAIL_SERVER = 'smtp.gmail.com'  # Default to Gmail SMTP
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_USERNAME = ''  # Set in environment or override in production config
MAIL_PASSWORD = ''  # Set in environment or override in production config
MAIL_DEFAULT_SENDER = ('AFCON360', 'noreply@afcon360.com')
MAIL_DEBUG = False  # Set to True for development

# SMS Provider Configuration
SMS_PROVIDER = "console"  # Options: "twilio", "africas_talking", "console"
TWILIO_ACCOUNT_SID = ""
TWILIO_AUTH_TOKEN = ""
TWILIO_PHONE_NUMBER = ""
AFRICAS_TALKING_USERNAME = ""
AFRICAS_TALKING_API_KEY = ""
AFRICAS_TALKING_SENDER_ID = ""
