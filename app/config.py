# app/config.py
# ============================================================================
#  FLASK CONFIGURATION  — Security-hardened production settings
# ============================================================================

import os
from datetime import timedelta
import importlib.util
from dotenv import load_dotenv

load_dotenv()

branding_spec = importlib.util.spec_from_file_location(
    "branding", os.path.join(os.path.dirname(__file__), "../../afcon360_app/config.py")
)
branding = importlib.util.module_from_spec(branding_spec)
branding_spec.loader.exec_module(branding)


class Config:
    APP_NAME        = getattr(branding, "APP_NAME",        os.getenv("APP_NAME",        "AFCON 360"))
    TOURNAMENT_NAME = getattr(branding, "TOURNAMENT_NAME", os.getenv("TOURNAMENT_NAME", "AFCON 360"))
    YEAR            = getattr(branding, "YEAR",            int(os.getenv("YEAR",        "2025")))
    VERSION         = getattr(branding, "VERSION",         os.getenv("VERSION",         "0.1.0"))

    SECRET_KEY    = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY")
    SECURITY_SALT = os.getenv("SECURITY_SALT")

    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG     = FLASK_ENV != "production"

    DB_HOST      = os.getenv("DB_HOST",     "localhost")
    DB_PORT      = int(os.getenv("DB_PORT", "5432"))
    DB_NAME      = os.getenv("DB_NAME",     "afcon360_prod")
    DB_USER      = os.getenv("DB_USER")
    DB_PASS      = os.getenv("DB_PASS")
    APP_DB_USER  = os.getenv("APP_DB_USER")
    APP_DB_PASS  = os.getenv("APP_DB_PASS")

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Sessions
    SESSION_TYPE              = "redis"
    SESSION_PERMANENT         = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    SESSION_USE_SIGNER        = True
    SESSION_COOKIE_HTTPONLY   = True
    SESSION_COOKIE_SAMESITE   = os.getenv("SESSION_COOKIE_SAMESITE", "Strict")
    SESSION_COOKIE_SECURE     = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"

    # SECURITY FIX: "pickle" → "json"
    # Pickle allows Remote Code Execution on deserialization if Redis is ever compromised.
    # JSON is safe — it cannot execute code on deserialization.
    # Migration note: existing sessions will be invalidated once (users log out once).
    # This is acceptable for the security upgrade.
    SESSION_SERIALIZER = "json"

    # Rate limiting
    RATELIMIT_STORAGE_URL = REDIS_URL
    RATELIMIT_DEFAULT     = os.getenv("RATELIMIT_DEFAULT", "2000 per day;500 per hour")

    # Module toggles
    MODULE_FLAGS = {
        "wallet":        True,
        "tourism":       os.getenv("ENABLE_TOURISM",       "false").lower() == "true",
        "transport":     os.getenv("ENABLE_TRANSPORT",     "true").lower()  == "true",
        "accommodation": os.getenv("ENABLE_ACCOMMODATION", "true").lower()  == "true",
        "tournament":    True,
        "agents":        os.getenv("ENABLE_AGENTS",        "false").lower() == "true",
        "admin":         True,
    }

    WALLET_FEATURES = {
        "enabled": True,
        "deposit":       {"enabled": True},
        "withdraw":      {"enabled": True, "daily_limit": int(os.getenv("WITHDRAW_LIMIT", "1000")), "require_verification": True},
        "peer_send":     {"enabled": True},
        "refund":        {"enabled": True},
        "multi_currency":{"enabled": True},
        "convert_currency":{"enabled": True},
        "audit_trail":   {"enabled": True},
    }

    SUPPORTED_CURRENCIES  = ["USD", "UGX", "KES", "TZS", "NGN", "EUR", "CFA"]
    CONVERSION_FEE_PCT    = os.getenv("CONVERSION_FEE_PCT", "0.02")
    FX_PROVIDER           = os.getenv("FX_PROVIDER")
    FX_CACHE_TTL_SECONDS  = int(os.getenv("FX_CACHE_TTL_SECONDS", "300"))

    IDEMPOTENCY = {"enabled": True, "require_client_request_id": True}
    AUDIT       = {"enabled": True, "retention_days": 3650, "archive_after_days": 365, "max_query_limit": 1000}
    METRICS     = {"enabled": True, "namespace": "wallet"}
    LOGGING     = {"level": os.getenv("LOG_LEVEL", "INFO"), "structured": True}

    FEATURE_FLAGS = {
        'accommodation': {
            'enabled':      True,
            'dependencies': ['wallet', 'identity'],
            'version':      '1.0.0',
            'description':  'Accommodation booking and hosting module',
        },
        'transport': {'enabled': False, 'dependencies': ['wallet', 'identity'], 'version': '1.0.0'},
        'tourism':   {'enabled': False, 'dependencies': ['identity'],            'version': '1.0.0'},
    }

    ACCOMMODATION_SETTINGS = {
        'max_photos_per_property': 20,
        'max_guests_per_property': 50,
        'default_currency':        'USD',
        'service_fee_percentage':  10.0,
        'booking_expiry_minutes':  15,
        'refund_window_days':      7,
        'enable_reviews':          True,
        'enable_messaging':        True,
    }

    @classmethod
    def validate_for_production(cls):
        if cls.FLASK_ENV == "production":
            missing = []
            if not cls.REDIS_URL:
                missing.append("REDIS_URL")
            if not cls.SECRET_KEY:
                missing.append("SECRET_KEY")
            if not cls.SECURITY_SALT:
                missing.append("SECURITY_SALT")
            if cls.WALLET_FEATURES.get("multi_currency", {}).get("enabled") and not cls.FX_PROVIDER:
                missing.append("FX_PROVIDER")
            if missing:
                raise RuntimeError(
                    f"Missing required production environment variables: {', '.join(missing)}"
                )