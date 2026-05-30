# afcon360_app/app/config.py
# ============================================================================
#  FLASK CONFIGURATION — Multi-environment layered loading
#
#  LOADING ORDER (each layer overrides the previous):
#    1. .env              — shared safe defaults
#    2. .env.{APP_ENV}    — environment-specific (local / docker / prod)
#
#  HOW TO USE:
#    local  → APP_ENV=local  → loads .env + .env.local
#    docker → APP_ENV=docker → loads .env + .env.docker
#    prod   → APP_ENV=prod   → loads .env + .env.prod
#
#  Set APP_ENV before launching the app, e.g.:
#    export APP_ENV=docker && flask run
#    or in Docker Compose env_file / environment block
# ============================================================================

import os
import logging
from decimal import Decimal
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ============================================================================
# LAYERED ENV LOADING
# ============================================================================
def _load_env():
    """
    Load environment in two layers:
      1. Base .env  (shared defaults, no secrets, no DB URLs)
      2. .env.{APP_ENV}  (environment-specific overrides)

    Searches from current working directory upward so this works
    whether you run from the project root or the app/ subdirectory.
    """
    # Find project root (where .env lives)
    cwd = Path.cwd()
    candidates = [cwd, cwd.parent, cwd.parent.parent]
    root = next((p for p in candidates if (p / ".env").exists()), cwd)

    # Layer 1: base defaults
    base_env = root / ".env"
    if base_env.exists():
        load_dotenv(base_env, override=False)
        logger.debug(f"Loaded base env: {base_env}")
    else:
        logger.warning(f".env not found at {root}")

    # Layer 2: environment-specific overrides
    app_env = os.getenv("APP_ENV", "local")
    specific_env = root / f".env.{app_env}"
    if specific_env.exists():
        load_dotenv(specific_env, override=True)
        logger.debug(f"Loaded {specific_env.name} (overrides applied)")
    else:
        logger.warning(
            f".env.{app_env} not found at {root}. "
            f"Only base .env values are active. "
            f"Set APP_ENV correctly or create .env.{app_env}"
        )


_load_env()


# ============================================================================
# BRANDING (optional config module)
# ============================================================================
try:
    import config as branding
except ImportError:
    class _Branding:
        APP_NAME = "AFCON 360"
        TOURNAMENT_NAME = "AFCON 360"
        YEAR = 2025
        VERSION = "0.1.0"
    branding = _Branding()


# ============================================================================
# MAIN CONFIGURATION CLASS
# ============================================================================
class Config:

    # ---- Identity -----------------------------------------------------------
    APP_NAME        = getattr(branding, "APP_NAME",        os.getenv("APP_NAME",        "AFCON 360"))
    TOURNAMENT_NAME = getattr(branding, "TOURNAMENT_NAME", os.getenv("TOURNAMENT_NAME", "AFCON 360"))
    YEAR            = getattr(branding, "YEAR",            int(os.getenv("YEAR",        "2025")))
    VERSION         = getattr(branding, "VERSION",         os.getenv("VERSION",         "0.1.0"))

    # Which environment are we in?
    APP_ENV   = os.getenv("APP_ENV", "local")   # local | docker | prod
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG     = FLASK_ENV != "production"

    # ---- Auth secrets -------------------------------------------------------
    SECRET_KEY    = os.getenv("SECRET_KEY")
    SECURITY_SALT = os.getenv("SECURITY_SALT")

    # ---- Database -----------------------------------------------------------
    # Config reads DATABASE_URL first; falls back to individual components.
    # NEVER hardcode a URL here — always read from env.
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "afcon360_prod")
    DB_USER = os.getenv("APP_DB_USER") or os.getenv("DB_USER")
    DB_PASS = os.getenv("APP_DB_PASS") or os.getenv("DB_PASS")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    if not SQLALCHEMY_DATABASE_URI and DB_USER and DB_PASS:
        SQLALCHEMY_DATABASE_URI = (
            f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "isolation_level": os.getenv("DB_ISOLATION_LEVEL", "REPEATABLE_READ"),
        "pool_size":        int(os.getenv("DB_POOL_SIZE",     "5")),
        "max_overflow":     int(os.getenv("DB_MAX_OVERFLOW",  "10")),
        "pool_timeout":     int(os.getenv("DB_POOL_TIMEOUT",  "30")),
        "pool_recycle":     int(os.getenv("DB_POOL_RECYCLE",  "1800")),
        "pool_pre_ping":    True,
    }

    # ---- Redis (single source of truth) -------------------------------------
    # CRITICAL: @ in Redis password must be percent-encoded as %40 in URLs.
    # Correct:   redis://:MyP%40ss@redis:6379/0
    # Wrong:     redis://:MyP@ss@redis:6379/0   ← breaks URL parsing
    REDIS_URL              = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL      = os.getenv("CELERY_BROKER_URL",  REDIS_URL)
    CELERY_RESULT_BACKEND  = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

    # ---- Sessions -----------------------------------------------------------
    SESSION_TYPE             = "redis"
    SESSION_PERMANENT        = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    SESSION_USE_SIGNER       = True
    SESSION_COOKIE_HTTPONLY  = True
    SESSION_COOKIE_SAMESITE  = os.getenv("SESSION_COOKIE_SAMESITE", "Strict")
    SESSION_COOKIE_SECURE    = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
    SESSION_SERIALIZER       = "json"
    SESSION_REDIS_URL        = REDIS_URL

    # ---- Rate limiting ------------------------------------------------------
    RATELIMIT_STORAGE_URI   = REDIS_URL
    RATELIMIT_STRATEGY      = "fixed-window"
    RATELIMIT_DEFAULT       = os.getenv("RATELIMIT_DEFAULT", "2000 per day;500 per hour")
    RATELIMIT_ENABLED       = True
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_SWALLOW_ERRORS  = False

    # ---- Module toggles (kill switches) ------------------------------------
    # NOTE: Dashboard is the live source of truth.
    # These are startup defaults only; ModuleToggleService overrides from DB.
    MODULE_FLAGS = {
        "wallet":         os.getenv("ENABLE_WALLET",        "true").lower()  == "true",
        "tourism":        os.getenv("ENABLE_TOURISM",       "false").lower() == "true",
        "transport":      os.getenv("ENABLE_TRANSPORT",     "true").lower()  == "true",
        "accommodation":  os.getenv("ENABLE_ACCOMMODATION", "true").lower()  == "true",
        "tournament":     os.getenv("ENABLE_TOURNAMENT",    "true").lower()  == "true",
        "events":         True,
        "agents":         os.getenv("ENABLE_AGENTS",        "false").lower() == "true",
        "admin":          os.getenv("ENABLE_ADMIN",         "true").lower()  == "true",
    }

    # ---- Wallet feature flags -----------------------------------------------
    WALLET_FEATURES = {
        "enabled": MODULE_FLAGS["wallet"],
        "deposit":  {"enabled": os.getenv("WALLET_DEPOSIT_ENABLED",  "true").lower()  == "true"},
        "withdraw": {
            "enabled":              os.getenv("WALLET_WITHDRAW_ENABLED",             "true").lower()  == "true",
            "daily_limit":          int(os.getenv("WALLET_WITHDRAW_DAILY_LIMIT",     "1000")),
            "require_verification": os.getenv("WALLET_WITHDRAW_REQUIRE_VERIFICATION","true").lower()  == "true",
        },
        "peer_send":       {"enabled": os.getenv("WALLET_PEER_SEND_ENABLED",        "true").lower()  == "true"},
        "refund":          {"enabled": os.getenv("WALLET_REFUND_ENABLED",           "true").lower()  == "true"},
        "multi_currency":  {"enabled": os.getenv("WALLET_MULTI_CURRENCY_ENABLED",   "true").lower()  == "true"},
        "convert_currency":{"enabled": os.getenv("WALLET_CONVERT_ENABLED",         "true").lower()  == "true"},
        "audit_trail":     {"enabled": os.getenv("WALLET_AUDIT_ENABLED",           "true").lower()  == "true"},
    }

    WALLET_DAILY_LIMIT_HOME = Decimal(os.getenv("WALLET_DAILY_LIMIT_HOME", "10000"))
    WALLET_DAILY_LIMIT_LOCAL = Decimal(os.getenv("WALLET_DAILY_LIMIT_LOCAL", "37000000"))
    WALLET_MAX_DEPOSIT   = Decimal(os.getenv("WALLET_MAX_DEPOSIT",   "10000"))
    WALLET_MAX_WITHDRAWAL = Decimal(os.getenv("WALLET_MAX_WITHDRAWAL", "5000"))
    WALLET_MAX_TRANSFER  = Decimal(os.getenv("WALLET_MAX_TRANSFER",  "2000"))

    # ---- Email --------------------------------------------------------------
    MAIL_SERVER         = os.getenv("MAIL_SERVER",    "smtp.gmail.com")
    MAIL_PORT           = int(os.getenv("MAIL_PORT",  "587"))
    MAIL_USE_TLS        = os.getenv("MAIL_USE_TLS",   "true").lower()  == "true"
    MAIL_USE_SSL        = os.getenv("MAIL_USE_SSL",   "false").lower() == "true"
    MAIL_USERNAME       = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD       = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "noreply@example.com")
    MAIL_DEBUG          = os.getenv("MAIL_DEBUG", "false").lower() == "true"

    # ---- Flask-Security -----------------------------------------------------
    SECURITY_PASSWORD_SALT    = os.getenv("SECURITY_PASSWORD_SALT", SECURITY_SALT) if SECURITY_SALT else os.getenv("SECURITY_PASSWORD_SALT")
    SECURITY_REGISTERABLE     = os.getenv("SECURITY_REGISTERABLE",          "true").lower()  == "true"
    SECURITY_SEND_REGISTER_EMAIL = os.getenv("SECURITY_SEND_REGISTER_EMAIL","false").lower() == "true"
    SECURITY_RECOVERABLE      = os.getenv("SECURITY_RECOVERABLE",           "true").lower()  == "true"
    SECURITY_CHANGEABLE       = os.getenv("SECURITY_CHANGEABLE",            "true").lower()  == "true"
    SECURITY_CONFIRMABLE      = os.getenv("SECURITY_CONFIRMABLE",           "false").lower() == "true"
    SECURITY_TRACKABLE        = os.getenv("SECURITY_TRACKABLE",             "true").lower()  == "true"
    SECURITY_URL_PREFIX       = os.getenv("SECURITY_URL_PREFIX",            "/security")
    SECURITY_POST_LOGIN_VIEW  = os.getenv("SECURITY_POST_LOGIN_VIEW",       "/dashboard")
    SECURITY_POST_LOGOUT_VIEW = os.getenv("SECURITY_POST_LOGOUT_VIEW",      "/")
    SECURITY_POST_REGISTER_VIEW = os.getenv("SECURITY_POST_REGISTER_VIEW",  "/dashboard")

    REQUIRE_EMAIL_VERIFICATION = os.getenv("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"
    ALLOW_USERNAME_LOGIN       = os.getenv("ALLOW_USERNAME_LOGIN",       "true").lower()  == "true"

    # ---- CSRF ---------------------------------------------------------------
    WTF_CSRF_ENABLED      = os.getenv("WTF_CSRF_ENABLED",    "true").lower()  == "true"
    WTF_CSRF_SECRET_KEY   = os.getenv("WTF_CSRF_SECRET_KEY") or SECRET_KEY
    WTF_CSRF_TIME_LIMIT   = int(os.getenv("WTF_CSRF_TIME_LIMIT", "3600"))
    WTF_CSRF_SSL_STRICT   = os.getenv("WTF_CSRF_SSL_STRICT", "false").lower() == "true"
    WTF_CSRF_HEADERS      = ["X-CSRFToken", "X-CSRF-Token"]
    WTF_CSRF_FIELD_NAME   = "csrf_token"
    WTF_CSRF_CHECK_DEFAULT = True
    WTF_CSRF_METHODS      = ["POST", "PUT", "PATCH", "DELETE"]

    # ---- Idempotency & Audit ------------------------------------------------
    IDEMPOTENCY = {
        "enabled":                  os.getenv("IDEMPOTENCY_ENABLED",         "true").lower() == "true",
        "require_client_request_id": os.getenv("IDEMPOTENCY_REQUIRE_CLIENT_ID","true").lower() == "true",
        "ttl_seconds":              int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "86400")),
    }
    AUDIT = {
        "enabled":        os.getenv("AUDIT_ENABLED",        "true").lower() == "true",
        "retention_days": int(os.getenv("AUDIT_RETENTION_DAYS", "3650")),
    }

    # =========================================================================
    @classmethod
    def validate_for_production(cls):
        """
        Hard-fail on startup if required production variables are missing.
        Called automatically when APP_ENV=prod or FLASK_ENV=production.
        """
        if cls.FLASK_ENV != "production":
            return

        missing = []

        if not cls.SQLALCHEMY_DATABASE_URI:
            missing.append("DATABASE_URL (or DB_HOST/DB_USER/DB_PASS)")
        if not cls.SECRET_KEY or cls.SECRET_KEY.startswith("REPLACE_"):
            missing.append("SECRET_KEY")
        if not cls.SECURITY_SALT or cls.SECURITY_SALT.startswith("REPLACE_"):
            missing.append("SECURITY_SALT")
        if not cls.ENCRYPTION_KEY_VALUE or cls.ENCRYPTION_KEY_VALUE.startswith("REPLACE_"):
            missing.append("ENCRYPTION_KEY")

        # Warn (not fail) for service credentials — they may not be needed at boot
        warnings = []
        if not cls.MAIL_USERNAME:
            warnings.append("MAIL_USERNAME")
        if not cls.MAIL_PASSWORD:
            warnings.append("MAIL_PASSWORD")

        if warnings:
            logger.warning(
                f"[CONFIG] Production service credentials not set: {', '.join(warnings)}"
            )

        if missing:
            raise RuntimeError(
                f"[CONFIG] FATAL: Missing required production environment variables:\n"
                f"  → {chr(10).join('  → ' + m for m in missing)}\n"
                f"  Check your .env.prod file."
            )

    # Expose ENCRYPTION_KEY as attribute for validation
    ENCRYPTION_KEY_VALUE = os.getenv("ENCRYPTION_KEY", "")



# ============================================================================
# TESTING CONFIGURATION
# ============================================================================
class TestingConfig(Config):
    """
    Testing configuration.
    Uses a separate test database — NEVER the production DB.
    """
    TESTING = True
    DEBUG   = True

    SQLALCHEMY_DATABASE_URI = (
        os.getenv("TEST_DATABASE_URL")
        or os.getenv("DATABASE_URL", "postgresql://localhost:5432/afcon360") + "_test"
    )

    WTF_CSRF_ENABLED = False
    SERVER_NAME          = "localhost.localdomain"
    PREFERRED_URL_SCHEME = "http"
    APPLICATION_ROOT     = "/"

    # Disable expensive infrastructure for unit tests
    SESSION_TYPE      = "simple"
    SESSION_REDIS_URL = None
    RATELIMIT_ENABLED = False

    SECURITY_PASSWORD_SALT = "test-salt-only-not-for-production"

    MODULE_FLAGS = {
        "wallet":         True,
        "tourism":        True,
        "transport":      True,
        "accommodation":  True,
        "tournament":     True,
        "events":         True,
        "agents":         False,
        "admin":          True,
    }


# ============================================================================
# CONFIG REGISTRY  — used by app factory
# ============================================================================
config_map = {
    "local":       Config,
    "docker":      Config,
    "prod":        Config,
    "testing":     TestingConfig,
    "development": Config,   # fallback alias
    "production":  Config,   # fallback alias
}

def get_config(app_env: str = None) -> Config:
    """
    Return the correct config class for the current environment.

    Usage in app factory:
        from app.config import get_config
        app.config.from_object(get_config())
    """
    env = app_env or os.getenv("APP_ENV") or os.getenv("FLASK_ENV", "local")
    cfg = config_map.get(env, Config)
    cfg.validate_for_production()
    return cfg