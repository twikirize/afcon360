# app/config.py
# ============================================================================
#  FLASK CONFIGURATION — Security-hardened production settings
# ============================================================================

import os
from decimal import Decimal
from datetime import timedelta
from dotenv import load_dotenv

# Optimization: Load dotenv once
load_dotenv()

# Optimization: Faster branding load
try:
    import config as branding
except ImportError:
    # Create minimal branding object
    class Branding:
        APP_NAME = "AFCON 360"
        TOURNAMENT_NAME = "AFCON 360"
        YEAR = 2025
        VERSION = "0.1.0"
    branding = Branding()


class Config:
    APP_NAME = getattr(branding, "APP_NAME", os.getenv("APP_NAME", "AFCON 360"))
    TOURNAMENT_NAME = getattr(branding, "TOURNAMENT_NAME", os.getenv("TOURNAMENT_NAME", "AFCON 360"))
    YEAR = getattr(branding, "YEAR", int(os.getenv("YEAR", "2025")))
    VERSION = getattr(branding, "VERSION", os.getenv("VERSION", "0.1.0"))

    SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY")
    SECURITY_SALT = os.getenv("SECURITY_SALT")

    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = FLASK_ENV != "production"

    # Database Components
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "afcon360_prod")
    DB_USER = os.getenv("APP_DB_USER") or os.getenv("DB_USER")
    DB_PASS = os.getenv("APP_DB_PASS") or os.getenv("DB_PASS")

    # Construct SQLALCHEMY_DATABASE_URI if not provided directly
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    if not SQLALCHEMY_DATABASE_URI and DB_USER and DB_PASS:
        SQLALCHEMY_DATABASE_URI = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Redis URL (single source of truth)
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Sessions
    SESSION_TYPE = "redis"
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    SESSION_USE_SIGNER = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Strict")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
    SESSION_SERIALIZER = "json"
    SESSION_REDIS_URL = REDIS_URL

    # Rate limiting - using same Redis
    RATELIMIT_STORAGE_URL = REDIS_URL
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "2000 per day;500 per hour")
    RATELIMIT_ENABLED = True
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_SWALLOW_ERRORS = False

    # ============================================================================
    # MODULE TOGGLES (KILL SWITCHES)
    # ============================================================================
    MODULE_FLAGS = {
        "wallet": os.getenv("ENABLE_WALLET", "true").lower() == "true",
        "tourism": os.getenv("ENABLE_TOURISM", "false").lower() == "true",
        "transport": os.getenv("ENABLE_TRANSPORT", "true").lower() == "true",
        "accommodation": os.getenv("ENABLE_ACCOMMODATION", "true").lower() == "true",
        "tournament": os.getenv("ENABLE_TOURNAMENT", "true").lower() == "true",
        "agents": os.getenv("ENABLE_AGENTS", "false").lower() == "true",
        "admin": os.getenv("ENABLE_ADMIN", "true").lower() == "true",
    }

    # ============================================================================
    # WALLET FEATURE FLAGS
    # ============================================================================
    WALLET_FEATURES = {
        "enabled": MODULE_FLAGS["wallet"],
        "deposit": {"enabled": os.getenv("WALLET_DEPOSIT_ENABLED", "true").lower() == "true"},
        "withdraw": {
            "enabled": os.getenv("WALLET_WITHDRAW_ENABLED", "true").lower() == "true",
            "daily_limit": int(os.getenv("WALLET_WITHDRAW_DAILY_LIMIT", "1000")),
            "require_verification": os.getenv("WALLET_WITHDRAW_REQUIRE_VERIFICATION", "true").lower() == "true"
        },
        "peer_send": {"enabled": os.getenv("WALLET_PEER_SEND_ENABLED", "true").lower() == "true"},
        "refund": {"enabled": os.getenv("WALLET_REFUND_ENABLED", "true").lower() == "true"},
        "multi_currency": {"enabled": os.getenv("WALLET_MULTI_CURRENCY_ENABLED", "true").lower() == "true"},
        "convert_currency": {"enabled": os.getenv("WALLET_CONVERT_ENABLED", "true").lower() == "true"},
        "audit_trail": {"enabled": os.getenv("WALLET_AUDIT_ENABLED", "true").lower() == "true"},
    }

    WALLET_DAILY_LIMIT_HOME = Decimal(os.getenv("WALLET_DAILY_LIMIT_HOME", "10000"))
    WALLET_DAILY_LIMIT_LOCAL = Decimal(os.getenv("WALLET_DAILY_LIMIT_LOCAL", "37000000"))
    WALLET_MAX_DEPOSIT = Decimal(os.getenv("WALLET_MAX_DEPOSIT", "10000"))
    WALLET_MAX_WITHDRAWAL = Decimal(os.getenv("WALLET_MAX_WITHDRAWAL", "5000"))
    WALLET_MAX_TRANSFER = Decimal(os.getenv("WALLET_MAX_TRANSFER", "2000"))

    # ============================================================================
    # IDEMPOTENCY & AUDIT
    # ============================================================================
    IDEMPOTENCY = {
        "enabled": os.getenv("IDEMPOTENCY_ENABLED", "true").lower() == "true",
        "require_client_request_id": os.getenv("IDEMPOTENCY_REQUIRE_CLIENT_ID", "true").lower() == "true",
        "ttl_seconds": int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "86400")),
    }

    AUDIT = {
        "enabled": os.getenv("AUDIT_ENABLED", "true").lower() == "true",
        "retention_days": int(os.getenv("AUDIT_RETENTION_DAYS", "3650")),
    }

    @classmethod
    def validate_for_production(cls):
        """Validate required production configuration."""
        if cls.FLASK_ENV == "production":
            missing = []
            if not cls.SQLALCHEMY_DATABASE_URI:
                missing.append("DATABASE_URL or DB components")
            if not cls.SECRET_KEY:
                missing.append("SECRET_KEY")
            if missing:
                raise RuntimeError(f"Missing required production environment variables: {', '.join(missing)}")
