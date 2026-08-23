# app/__init__.py
"""
# Changes vs original:
#   [P0] REMOVED remove_csp() - it was stripping CSP in production due to
#        Flask's LIFO after_request execution order (registered first = runs last)
#   [P0] Consolidated security headers into single after_request handler
#   [P1] SESSION_SERIALIZER changed to json (pickle = RCE risk)
#   [P2] Added wallet module with feature flag support
#   [P3] Added audit API blueprints and CLI commands
#   [P4] Added wallet status endpoint and context processor
#   [OPTIMIZATION] Deep Lazy Loading for modules (startup time < 2s)
#   [OPTIMIZATION] Shared Redis client and connection reuse
#   [FIX] Moved all DB URI logic to config.py and fixed Limiter storage
#   [TRANSACTION] Added explicit session lifecycle management
# ============================================================================
"""

import os
import logging
import time
import threading
from datetime import datetime, timezone

# ============================================================================
# ENVIRONMENT LOADING — layered: .env (base defaults) → .env.{APP_ENV} (overrides)
#
# APP_ENV controls which overlay is loaded:
#   local  → .env + .env.local   (your machine, localhost DB/Redis)
#   docker → .env + .env.docker  (Docker Compose, service names db/redis)
#   prod   → .env + .env.prod    (Oracle Cloud / bare metal)
#
# Set before starting:
#   export APP_ENV=local | docker | prod
# ============================================================================
# ENV loading is handled by config.py (_load_env) when get_config() is imported.
# No duplicate load needed here.

# ============================================================================
# NOTE: ENCRYPTION_KEY guard has been moved inside create_app(), after
# get_config() loads .env.{APP_ENV}. Checking it here (module level) fires
# before .env.local is loaded, causes a temp key to be written to os.environ,
# and then blocks the real value from .env.local from taking effect.
# ============================================================================
# REDIS AVAILABILITY CHECK
# ============================================================================
try:
    import redis

    if os.getenv("DISABLE_REDIS", "false").lower() in ("1", "true", "yes"):
        redis = None
        REDIS_AVAILABLE = False
        logging.warning("[ENV] Redis disabled via DISABLE_REDIS env var")
    else:
        REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False
    logging.warning("[ENV] Redis not installed — some features will be limited")

# ============================================================================
# OPTIONAL IMPORTS
# ============================================================================
try:
    from app.utils.id_guard import init_id_guard, register_id_guard_commands

    IDGUARD_AVAILABLE = True
except ImportError:
    IDGUARD_AVAILABLE = False
    logging.warning("[ENV] IDGuard not available — ID mixing protection disabled")

from flask import Flask, flash, redirect, render_template, session, current_app, url_for, request, jsonify, g

try:
    from flask_session import Session

    FLASK_SESSION_AVAILABLE = True
except ImportError:
    Session = None
    FLASK_SESSION_AVAILABLE = False
    logging.warning("[ENV] Flask-Session not available — using fallback sessions")

from flask_wtf.csrf import CSRFError
from typing import Dict
from app.config import get_config  # layered config with env validation
from app.extensions import db, migrate, login_manager, csrf, limiter, cache, redis_client, mail, socketio
from app.utils.module_toggle_service import ModuleToggleService


# Configure logging globally at the entry point
def configure_logging():
    root = logging.getLogger()
    if root.handlers:
        return

    # Get log level from environment or use default based on FLASK_ENV
    log_level_str = os.getenv('LOG_LEVEL', '').upper()
    flask_env = os.getenv('FLASK_ENV', 'development').lower()

    # Determine logging level
    if log_level_str == 'DEBUG':
        root.setLevel(logging.DEBUG)
    elif log_level_str == 'INFO':
        root.setLevel(logging.INFO)
    elif log_level_str == 'WARNING':
        root.setLevel(logging.WARNING)
    elif log_level_str == 'ERROR':
        root.setLevel(logging.ERROR)
    elif log_level_str == 'CRITICAL':
        root.setLevel(logging.CRITICAL)
    else:
        # Default based on environment
        if flask_env == 'production':
            root.setLevel(logging.INFO)
        else:
            root.setLevel(logging.DEBUG)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    root.addHandler(handler)


configure_logging()
logger = logging.getLogger("app")


def should_upgrade_insecure():
    """Check if upgrade-insecure-requests should be enabled"""
    from flask import current_app
    try:
        with current_app.app_context():
            from app.models.system_config import SystemConfig
            setting = SystemConfig.query.filter_by(key='CSP_UPGRADE_INSECURE').first()
            return setting and setting.value == 'true'
    except:
        return False


def require_redis(url: str, purpose: str, existing_client=None):
    """
    Ensure Redis is available before starting the app.
    Never raises RuntimeError – always falls back to None and logs error.
    """
    if existing_client:
        try:
            existing_client.ping()
            return existing_client
        except Exception:
            pass

    if not REDIS_AVAILABLE:
        logging.warning(f"Redis not available for {purpose} - using fallback")
        return None

    try:
        client = redis.Redis.from_url(url, decode_responses=False, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return client
    except Exception as e:
        logging.error(f"Redis not available for {purpose}. Error: {e}")
        return None


def create_app(config_object=None) -> Flask:
    """
    Application factory pattern.
    """
    start_time = time.time()
    if config_object is None and os.getenv('FLASK_ENV') == 'testing':
        from app.config import TestingConfig
        config_object = TestingConfig

    base_dir = os.path.abspath(os.path.dirname(__file__))
    template_path = os.path.join(base_dir, "..", "templates")
    project_root = os.path.abspath(os.path.join(base_dir, ".."))
    static_path = os.path.join(project_root, "static")

    # Environment already loaded at module level

    app = Flask(__name__, static_folder=static_path, template_folder=template_path)

    # Remove Flask's default handler to prevent duplicate logging
    # Only clear if no handlers already exist (safe for Gunicorn)
    if not app.logger.handlers:
        app.logger.handlers.clear()

    # ------------------------------------------------------------------
    # PERMANENT FIX: Custom Jinja2 Loader with Encoding Fallback
    # ------------------------------------------------------------------
    from jinja2 import FileSystemLoader
    import warnings

    class EncodingSafeLoader(FileSystemLoader):
        """Custom loader that handles encoding errors gracefully."""

        def get_source(self, environment, template):
            for searchpath in self.searchpath:
                filename = os.path.join(searchpath, template)
                if os.path.exists(filename):
                    encodings = ['utf-8', 'utf-8-sig', 'cp1252', 'latin-1', 'iso-8859-1']
                    for encoding in encodings:
                        try:
                            with open(filename, 'r', encoding=encoding) as f:
                                contents = f.read()
                            if encoding != 'utf-8':
                                warnings.warn(
                                    f"Template {template} was encoded as {encoding}, not UTF-8.",
                                    UserWarning
                                )
                            mtime = os.path.getmtime(filename)

                            def uptodate():
                                try:
                                    return os.path.getmtime(filename) == mtime
                                except OSError:
                                    return False

                            return contents, filename, uptodate
                        except UnicodeDecodeError:
                            continue
                    raise UnicodeDecodeError(
                        'utf-8', b'', 0, 0,
                        f"Could not decode template {template} with any known encoding."
                    )
            raise Exception(f"Template {template} not found")

    # Replace the default loader with our encoding-safe one
    app.jinja_env.loader = EncodingSafeLoader(template_path)

    # -------------------------------------------------------------------------
    # FLASH CATEGORY NORMALIZATION (validation vs notification boundary)
    # Single source of truth: any flash category is mapped to a Bootstrap-safe
    # alert class. 'error' (legacy) -> 'danger'. Unknown -> 'info'.
    # This enforces the rule in notifications/_notification_implement.md §8 so
    # inline flash loops and the shared macro render consistently everywhere.
    # -------------------------------------------------------------------------
    def flash_alert_class(category):
        if category in ("error", "danger"):
            return "danger"
        if category in ("success", "warning", "info"):
            return category
        return "info"

    app.jinja_env.globals["flash_alert_class"] = flash_alert_class

    # Load configuration — this triggers _load_env() in config.py which loads
    # .env (base) then .env.{APP_ENV} (local/docker/prod) before we read anything
    app.config.from_object(config_object or get_config())

    # -------------------------------------------------------------------------
    # ENCRYPTION KEY GUARD — must run AFTER get_config() so .env.local is loaded
    # -------------------------------------------------------------------------
    if not os.getenv("ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY", "").startswith("REPLACE_"):
        import secrets as _secrets
        _temp_key = _secrets.token_urlsafe(32)
        os.environ["ENCRYPTION_KEY"] = _temp_key
        logging.warning(
            f"[ENV] ENCRYPTION_KEY not set. Generated a temporary key for this session. "
            f"Add ENCRYPTION_KEY={_temp_key} to your .env.local for consistency."
        )

    # Critical Config Fallbacks with validation
    # SECRET_KEY validation
    secret_key = app.config.get('SECRET_KEY') or os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY")
    if not secret_key:
        flask_env = os.getenv("FLASK_ENV", "production")
        if flask_env == "production":
            raise RuntimeError(
                "SECRET_KEY must be set in production. "
                "Set SECRET_KEY environment variable."
            )
        else:
            # Development fallback - generate a deterministic key for development
            import hashlib
            dev_secret = hashlib.sha256(b"afcon360_dev_secret_do_not_use_in_prod").hexdigest()[:32]
            secret_key = dev_secret
            logger.warning("Using development SECRET_KEY. Set SECRET_KEY environment variable for production.")
    app.config['SECRET_KEY'] = secret_key

    # DATABASE URI validation
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI") or os.getenv("DATABASE_URL")

    if not db_uri:
        flask_env = os.getenv("FLASK_ENV", "production")
        if flask_env == "production":
            raise RuntimeError(
                "DATABASE_URL must be set in production. "
                "Set DATABASE_URL environment variable or configure SQLALCHEMY_DATABASE_URI in config."
            )
        else:
            # Development fallback - use local PostgreSQL with default credentials
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "5432")
            db_name = os.getenv("DB_NAME", "afcon360_dev")
            db_user = os.getenv("DB_USER", "postgres")
            db_pass = os.getenv("DB_PASSWORD", "")

            if db_pass:
                db_uri = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
            else:
                db_uri = f"postgresql://{db_user}@{db_host}:{db_port}/{db_name}"

            logger.warning(f"Using development database: {db_uri.replace(db_pass, '***') if db_pass else db_uri}")
            logger.warning("Set DATABASE_URL environment variable for production.")

    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_SERIALIZER"] = "json"

    # ------------------------------------------------------------------
    # Redis & Extensions (Shared) – resilient fallback
    # ------------------------------------------------------------------
    redis_url = app.config.get("REDIS_URL") or os.getenv("REDIS_URL")

    if not redis_url:
        flask_env = os.getenv("FLASK_ENV", "production")
        if flask_env == "production":
            raise RuntimeError("REDIS_URL must be set in production.")
        else:
            redis_url = "redis://localhost:6379/0"
            logger.warning("Using development Redis URL.")

    from app.extensions import limiter, cache, redis_client

    # Try to configure Redis for caching; fallback to SimpleCache
    _redis_available_for_cache = False
    try:
        if REDIS_AVAILABLE:
            cache.config.update({
                "CACHE_TYPE": "RedisCache",
                "CACHE_REDIS_URL": redis_url,
                "CACHE_DEFAULT_TIMEOUT": 300
            })
            redis_client.configure(redis_url)
            _redis_available_for_cache = True
        else:
            cache.config.update({"CACHE_TYPE": "SimpleCache"})
    except Exception:
        cache.config.update({"CACHE_TYPE": "SimpleCache"})
        logger.warning("Redis cache configuration failed – using SimpleCache")

    # Configure Flask-Limiter to use Redis if available, else memory
    app.config["RATELIMIT_STORAGE_URI"] = redis_url if _redis_available_for_cache else "memory://"
    limiter.storage_uri = app.config["RATELIMIT_STORAGE_URI"]

    # Get Redis client for sessions – reuse existing connection
    redis_session_client = None
    try:
        if _redis_available_for_cache:
            redis_session_client = redis_client.client
    except Exception:
        pass

    if not redis_session_client:
        redis_session_client = require_redis(redis_url, "sessions")

    if REDIS_AVAILABLE and redis_session_client and FLASK_SESSION_AVAILABLE:
        app.config["SESSION_TYPE"] = "redis"
        app.config["SESSION_REDIS"] = redis_session_client
        Session(app)
    elif FLASK_SESSION_AVAILABLE:
        app.config["SESSION_TYPE"] = "filesystem"
        Session(app)
        logging.warning("Using filesystem sessions - Redis not available")

    if _redis_available_for_cache:
        cache.init_app(app, config={"CACHE_TYPE": "RedisCache", "CACHE_REDIS_URL": redis_url})
    else:
        cache.init_app(app, config={"CACHE_TYPE": "SimpleCache"})

    # Initialize limiter with app
    limiter.init_app(app)

    # Configure Flask error logging
    if not app.debug:
        # In production, ensure errors are still logged
        app.logger.setLevel(logging.INFO)
        # Ensure Flask's error handlers propagate exceptions
        app.config['PROPAGATE_EXCEPTIONS'] = True
        app.config['TRAP_HTTP_EXCEPTIONS'] = False
    else:
        # In development, show all logs
        app.logger.setLevel(logging.DEBUG)

    # ============================================================
    # CLEAN REQUEST LOGGING (without clutter)
    # ============================================================

    # Ensure all Flask loggers are visible
    flask_loggers = ['app', 'flask', 'admin', 'admin.owner', 'admin.trust_settings']
    for logger_name in flask_loggers:
        log = logging.getLogger(logger_name)
        log.setLevel(logging.DEBUG)
        log.propagate = False
        if not log.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            ))
            log.addHandler(handler)

    # Restore werkzeug INFO so the startup URL link and dev-server warning are visible.
    # Filter only the per-request access lines (e.g. "127.0.0.1 - - GET /...")
    # since we already have a custom request logger above.
    class _SuppressAccessLogs(logging.Filter):
        def filter(self, record):
            return not (' HTTP/1.' in record.getMessage())

    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.addFilter(_SuppressAccessLogs())
    # Ensure no duplicate handlers (safe for Gunicorn)
    if len(werkzeug_logger.handlers) > 1:
        werkzeug_logger.handlers = werkzeug_logger.handlers[:1]

    @app.before_request
    def log_request():
        """Clean request logging - one line per request"""
        # Skip static assets and favicon
        if request.path.startswith(('/static/', '/favicon.ico', '/theme/css/')):
            return

        # Determine log level based on method
        if request.method == 'GET':
            log_func = logger.debug
        else:
            log_func = logger.info

        # Log in a clean format
        log_func(f"📡 {request.method} {request.path}")

    # ── Combined after_request pipeline ──────────────────────────────
    @app.after_request
    def after_request_pipeline(response):
        """Single after_request handler that runs logging then security headers."""
        # 1. Logging
        if not request.path.startswith(('/static/', '/favicon.ico', '/theme/css/')):
            if response.status_code >= 500:
                icon = "💥"
                log_func = logger.error
            elif response.status_code >= 400:
                icon = "⚠️"
                log_func = logger.warning
            else:
                icon = "✅"
                log_func = logger.debug
            if response.status_code != 200 or app.debug:
                log_func(f"{icon} {request.method} {request.path} → {response.status_code}")

        # 2. Security headers (CSP, HSTS, etc.)
        from flask import g
        nonce = getattr(g, "csp_nonce", "")
        csp_enforce = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://use.fontawesome.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com https://use.fontawesome.com https://cdn.jsdelivr.net; "
            "connect-src 'self' https://cdn.jsdelivr.net; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "upgrade-insecure-requests;" if should_upgrade_insecure() else ""
        )
        response.headers["Content-Security-Policy"] = csp_enforce

        csp_report_only = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
            "style-src 'self' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://use.fontawesome.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com https://use.fontawesome.com https://cdn.jsdelivr.net; "
            "connect-src 'self' https://cdn.jsdelivr.net; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "upgrade-insecure-requests; " if should_upgrade_insecure() else ""
                                                                            "report-to csp-endpoint; report-uri /csp-report"
        )
        response.headers["Content-Security-Policy-Report-Only"] = csp_report_only

        response.headers["Report-To"] = (
            '{"group":"csp-endpoint","max_age":10886400,'
            '"endpoints":[{"url":"/csp-report"}],"include_subdomains":true}'
        )
        response.headers["Reporting-Endpoints"] = "csp-endpoint=\"/csp-report\""

        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        if session.get("user_id"):
            # Don't override Cache-Control on routes that deliberately set their own
            # (theme preferences API uses private short-lived cache for performance)
            if 'Cache-Control' not in response.headers:
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        return response

    # Keep 404 handler but make it cleaner
    @app.errorhandler(404)
    def handle_404(error):
        """Clean 404 handler"""
        # Static file 404s: return bare response — no template, no user_loader
        if request.path.startswith(('/favicon.ico', '/static/')):
            return '', 404

        # Log once, clearly
        logger.warning(f"❓ 404: {request.method} {request.path} - Page not found")

        # For API requests, return JSON
        if request.path.startswith('/api/'):
            return jsonify({"error": "Not found", "path": request.path}), 404

        return render_template('errors/404.html'), 404

    # Keep 500 handler for errors
    @app.errorhandler(Exception)
    def handle_exception(e):
        """Clean error logging with full traceback for debugging"""
        import traceback
        from flask_login import current_user
        from app.audit.models import AuditLog

        # Log to console/file
        logger.error(f"💥 Exception: {type(e).__name__}: {str(e)}")
        logger.debug(f"Full traceback:", exc_info=True)

        # Reset the failed PostgreSQL transaction before attempting audit
        # logging, otherwise the audit query/write hides the original error.
        try:
            db.session.rollback()
        except Exception as rollback_error:
            logger.error(f"Failed to rollback failed request transaction: {rollback_error}")

        # Log to database for admin visibility
        try:
            user_id = current_user.id if current_user.is_authenticated else None
            org_id = current_user.org_id if hasattr(current_user, 'org_id') else None

            error_traceback = traceback.format_exc()

            AuditLog.log(
                user_id=user_id,
                org_id=org_id,
                action="ERROR_OCCURRED",
                resource_type="application_error",
                resource_id=None,  # Not a specific entity, so pass None to avoid IDGuard violations
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else None,
                meta={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "request_method": request.method,
                    "request_path": request.path,  # Store path in meta instead
                    "traceback": error_traceback,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                db_session=db.session
            )
            db.session.commit()
        except Exception as log_error:
            # Don't let error logging crash the error handler
            logger.error(f"Failed to log error to database: {log_error}")
            db.session.rollback()

        if request.path.startswith('/api/'):
            return jsonify({"error": str(e)}), 500
        return render_template('errors/500.html'), 500

    # ------------------------------------------------------------------
    # CRITICAL: Register ALL models before SQLAlchemy initialization
    # ------------------------------------------------------------------
    _boot_t0 = time.time()
    from app.core.model_registry import register_all_models
    register_all_models()
    logger.info(f"⏱ register_all_models() took {time.time() - _boot_t0:.2f}s")

    _boot_t1 = time.time()
    db.init_app(app)
    socketio.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    logger.info(f"⏱ core extension init_app calls took {time.time() - _boot_t1:.2f}s")

    # Initialize mail
    _boot_t2 = time.time()
    mail.init_app(app)

    # Initialize socketio
    from app.accommodation.sockets import HostDashboardNamespace
    socketio.on_namespace(HostDashboardNamespace('/ws/host-dashboard'))
    logger.info(f"⏱ mail + socketio namespace init took {time.time() - _boot_t2:.2f}s")

    logger.info("✅ Mail extension initialized")

    # Module flag DB overrides are loaded on first request (see _run_deferred_startup)
    # This avoids a blocking DB query at startup.

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Your session has expired. Please log in again.'
    login_manager.login_message_category = 'warning'

    @login_manager.unauthorized_handler
    def unauthorized():
        """Return JSON for API requests instead of redirecting to login page."""
        # Check if this is an AJAX request (fetch sends Content-Type: application/json)
        if request.is_json or request.headers.get('Content-Type') == 'application/json':
            return jsonify({"ok": False, "error": "Not authenticated"}), 401
        flash('Your session has expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login', next=request.url))

    # Initialize IDGuard for runtime protection against ID mixing
    if IDGUARD_AVAILABLE:
        try:
            init_id_guard(app)
            logger.info("✅ IDGuard initialized for runtime ID mixing protection")
        except Exception as e:
            logger.error(f"Failed to initialize IDGuard: {e}")
    else:
        logger.warning("IDGuard not available - skipping ID mixing protection")

    # Dynamic rate limit settings wiring
    # NOTE: The initial DB fetch of default_limits (RateLimitService.get_default_limits())
    # used to run here at boot, blocking startup for ~3s — it was the FIRST real DB query
    # in the whole app factory, which forces SQLAlchemy's one-time configure_mappers() pass
    # across every registered model. That fetch has been moved into _run_deferred_startup
    # (see below), which runs in a background thread on the first real request instead.
    # limiter.default_limits keeps whatever Limiter was constructed with until that thread
    # updates it — functionally identical, just non-blocking.
    try:
        from app.admin.owner.rate_limit_service import RateLimitService

        @app.before_request
        def _apply_dynamic_rate_limits():
            """Dynamically enable/disable rate limiter based on owner settings"""
            try:
                limiter.enabled = RateLimitService.is_enabled()
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Rate limit settings wiring failed: {e}")

    # ------------------------------------------------------------------
    # SESSION SECURITY
    # SESSION_COOKIE_SECURE is set by config.py from .env.{APP_ENV} — do NOT
    # override it here. .env.local sets false (HTTP dev), .env.docker/.env.prod
    # set true (HTTPS only). setdefault is safe — only fills if not already set.
    # ------------------------------------------------------------------
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    # ------------------------------------------------------------------
    # Global Identity Context Loader
    # ------------------------------------------------------------------
    @app.before_request
    def load_identity_context():
        """Inject real actor and effective user into request context for every request.
        Uses flask.g to cache per-request to avoid duplicate DB queries."""
        if request.path.startswith('/static/'):
            return
        try:
            from flask import g as _g
            if hasattr(_g, '_identity_loaded'):
                return
            _g._identity_loaded = True

            from flask_login import current_user
            from flask import session as flask_session
            from app.core.context import RequestContext
            from app.identity.models.user import User
            from app.extensions import db

            actor_user = current_user if getattr(current_user, "is_authenticated", False) else None
            # Cache current_user in flask.g to prevent redundant user_loader calls
            # within the same request (context processors, templates, etc.)
            if actor_user:
                _g._cached_user = actor_user
                _g._cached_user_pubid = str(actor_user.public_id)
            RequestContext.set_actor(actor_user)

            effective_user = actor_user
            impersonated_id = flask_session.get("impersonated_user_id")
            if impersonated_id:
                try:
                    user = db.session.get(User, impersonated_id) if hasattr(db.session, 'get') else None
                except Exception:
                    db.session.rollback()
                    user = None
                if not user:
                    try:
                        user = db.session.get(User, impersonated_id)
                    except Exception:
                        db.session.rollback()
                        user = None
                if user:
                    effective_user = user
            RequestContext.set_effective_user(effective_user)
        except Exception as e:
            try:
                current_app.logger.warning(f"Identity context load failed: {e}")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Database Transaction Lifecycle
    # ------------------------------------------------------------------
    @app.before_request
    def ensure_clean_transaction():
        if request.path.startswith('/static/'):
            return
        # A previous request may have swallowed a database exception.  A
        # scoped session can then still be present but unusable until its
        # failed transaction is explicitly rolled back.
        try:
            if not db.session.is_active:
                db.session.rollback()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
        # expire_all() marks cached ORM state as stale without detaching objects
        # or destroying the session scope. db.session.remove() was causing
        # g._login_user to hold a detached User instance, forcing user_loader
        # to re-fire on every attribute access across context processors.
        try:
            db.session.expire_all()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass

    @app.teardown_request
    def handle_transaction(exception=None):
        try:
            # Roll back at every request boundary, not only for exceptions
            # Flask sees.  Service code can intentionally catch an exception
            # after SQLAlchemy has marked the transaction inactive; leaving
            # that transaction open can poison later work in the same scoped
            # session or connection pool.  Explicit commits have already
            # completed and are unaffected by this cleanup rollback.
            db.session.rollback()
        except Exception:
            pass
        finally:
            try:
                db.session.remove()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Deferred Startup — runs once on first real request, not at boot time
    # Moves blocking DB operations out of the startup critical path.
    # ------------------------------------------------------------------
    import threading
    _deferred_lock = threading.Lock()

    @app.before_request
    def _run_deferred_startup():
        """Safe idempotent startup guard – never blocks the request."""
        if request.path.startswith('/static/'):
            return
        if app.config.get("STARTUP_DONE"):
            return
        with _deferred_lock:
            if app.config.get("STARTUP_DONE"):
                return
            app.config["STARTUP_DONE"] = True
            # Non-blocking background validation (purely informational)
            import threading
            def _validate_schema():
                try:
                    with app.app_context():
                        from sqlalchemy import inspect as _sa_inspect
                        _ins = _sa_inspect(db.engine)
                        _cols = [c['name'] for c in _ins.get_columns('users')]
                        if 'id' in _cols and 'user_id' in _cols:
                            logger.info("✅ Dual ID system validated.")
                        _idxs = _ins.get_indexes('transactions')
                        if any(i.get('column_names') == ['client_request_id'] and i.get('unique') for i in _idxs):
                            logger.info("✅ transactions.client_request_id unique index present")
                        else:
                            logger.critical(
                                "Missing unique index on transactions.client_request_id – "
                                "idempotency may be broken. Add a DB migration."
                            )
                except Exception as exc:
                    logger.warning(f"Deferred startup – DB validation: {exc}")

            threading.Thread(target=_validate_schema, daemon=True).start()

            # Deferred rate-limit default_limits fetch — this DB call used to sit
            # at boot time and cost ~3s (it was the first query in the whole app,
            # forcing SQLAlchemy's one-time configure_mappers() pass). Moved here
            # so it runs after the server is already accepting requests.
            def _load_rate_limit_defaults():
                try:
                    with app.app_context():
                        from app.admin.owner.rate_limit_service import RateLimitService
                        default_limits = RateLimitService.get_default_limits()
                        limiter.default_limits = default_limits
                        logger.info("✅ Rate limit default_limits loaded (deferred)")
                except Exception as exc:
                    logger.warning(f"Deferred rate limit defaults load failed: {exc}")

            threading.Thread(target=_load_rate_limit_defaults, daemon=True).start()

    # ------------------------------------------------------------------
    # Lazy Imports - Blueprints & Models
    # ------------------------------------------------------------------
    _boot_t3 = time.time()
    from app.identity import models as identity_models
    from app.profile import models as profile_models
    from app.audit import models as audit_models
    from app.auth import roles as role_models
    from app.admin import models as admin_models  # Required for Alembic to detect ModerationLog
    from app.event_accommodation import \
        models as event_accommodation_models  # Required for Alembic to detect event accommodation models
    logger.info(
        f"⏱ lazy model imports (identity/profile/audit/roles/admin/event_accommodation) took {time.time() - _boot_t3:.2f}s")

    # Core Web Blueprints
    from app.auth.routes import auth_bp
    from app.auth.onboarding_routes import onboarding_bp
    from app.fan.routes import fan_bp
    from app.user.routes import user_bp  # Added user blueprint
    # from app.wallet.routes import wallet_bp  # DELETED - will be rebuilt
    from app.admin import admin_bp
    from app.admin.route_modules.settings import settings_bp
    try:
        from app.admin.routes_ultimate import admin_ultimate_bp
    except ImportError:
        admin_ultimate_bp = None

    try:
        from app.events import event_favorites_api_bp, events_bp
    except ImportError as e:
        logger.warning(f"Events blueprint not found: {e}")
        # Create a dummy blueprint to prevent crashes
        from flask import Blueprint
        events_bp = Blueprint('events', __name__)
        event_favorites_api_bp = None
    from app.tools.theme_routes import theme_bp
    from app.kyc.routes import kyc_bp  # Integrated KYC
    from app.profile.routes import profile_bp
    from app.placeholder import placeholder_bp

    # Import auth KYC blueprint
    try:
        from app.auth.kyc_routes import auth_kyc_bp
    except ImportError as e:
        auth_kyc_bp = None
        logger.warning(f"Auth KYC routes not found: {e}")

    # Missing blueprints - import with fallback (suppress warnings)
    from importlib import import_module

    # ── Safe optional blueprint resolution ──────────────────────────
    _optional_blueprint_map = {
        'org_bp': ('app.identity.routes', 'org_bp'),
        'compliance_bp': ('app.admin.compliance.routes', 'compliance_bp'),
        'auditor_bp': ('app.admin.auditor.routes', 'auditor_bp'),
        'support_bp': ('app.admin.support.routes', 'support_bp'),
        'moderator_bp': ('app.admin.moderator', 'moderator_bp'),
    }
    _resolved_blueprints = {}
    for bp_name, (module_path, attr_name) in _optional_blueprint_map.items():
        try:
            module = import_module(module_path)
            bp = getattr(module, attr_name, None)
            if bp:
                _resolved_blueprints[bp_name] = bp
            else:
                logger.debug(f"Blueprint {bp_name} not found in {module_path}")
        except ImportError:
            logger.debug(f"Module {module_path} not available - blueprint {bp_name} skipped")
    # Assign to local variables for later registration
    org_bp = _resolved_blueprints.get('org_bp')
    compliance_bp = _resolved_blueprints.get('compliance_bp')
    auditor_bp = _resolved_blueprints.get('auditor_bp')
    support_bp = _resolved_blueprints.get('support_bp')
    moderator_bp = _resolved_blueprints.get('moderator_bp')
    # API Blueprints
    from app.wallet.api.wallet_api import wallet_api_bp
    from app.wallet.api.fx_api import fx_api_bp
    from app.wallet.api.webhooks import webhooks_bp
    from app.wallet.api.admin_api import admin_api_bp
    # from app.wallet.api.audit_api import audit_bp  # DELETED

    # Feature-Based Blueprints — imported lazily inside each flag check below

    # ------------------------------------------------------------------
    # Register Blueprints
    # ------------------------------------------------------------------

    # 1. Register Core & Static Blueprints
    core_blueprints = [
        (admin_bp, None),
        (settings_bp, None),
        (auth_bp, None),
        (onboarding_bp, None),
        (fan_bp, None),
        (user_bp, None),  # Added user blueprint for user dashboard
        # (wallet_bp, None),  # DELETED - routes.py removed
        (events_bp, None),
        (theme_bp, None),
        (kyc_bp, '/kyc'),  # Fixed: Added KYC with prefix
        (profile_bp, None),
        (placeholder_bp, None),
    ]

    # Add ultimate admin blueprint if available
    if admin_ultimate_bp:
        core_blueprints.append((admin_ultimate_bp, None))

    # Removed registration of non-existent blueprints
    # Their functionality is handled within admin_bp

    for bp, prefix in core_blueprints:
        app.register_blueprint(bp, url_prefix=prefix)

    if event_favorites_api_bp:
        app.register_blueprint(event_favorites_api_bp)

    if auth_kyc_bp:
        def _auth_kyc_upload_alias():
            return redirect(url_for('auth_kyc.overview'))

        app.add_url_rule('/auth/kyc/upload', endpoint='auth.kyc_routes.kyc_upload', view_func=_auth_kyc_upload_alias)

    # Note: Compliance blueprint is already registered under admin_bp in app/admin/__init__.py

    # Register organization blueprint
    try:
        from app.identity.routes import org_bp
        app.register_blueprint(org_bp)
    except ImportError as e:
        logger.warning(f"Organization blueprint not found: {e}")
        # Create a dummy blueprint to prevent crashes
        from flask import Blueprint
        org_bp = Blueprint('org', __name__)
        app.register_blueprint(org_bp)
    except Exception as e:
        logger.error(f"Failed to register organization blueprint: {e}")

    # 2. Register API Blueprints
    from app.media.routes import media_bp
    api_blueprints = [wallet_api_bp, fx_api_bp, webhooks_bp, admin_api_bp, media_bp]
    for bp in api_blueprints:
        app.register_blueprint(bp)

    # Register media admin blueprint
    try:
        from app.media.admin_routes import media_admin_bp
        app.register_blueprint(media_admin_bp)
        app.logger.info("✅ Media admin blueprint registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register media admin blueprint: {e}")

    # 4. Register ALL blueprints at startup (runtime checks handle module status)
    # Tournament module
    try:
        from app.tournament import tournament_bp
        app.register_blueprint(tournament_bp)
        app.logger.info("✅ Tournament module registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register tournament module: {e}")

    # Tourism module
    try:
        from app.tourism import tourism_bp
        from app.tourism import routes  # noqa: F401 – attaches routes to blueprint
        app.register_blueprint(tourism_bp)
        app.logger.info("✅ Tourism module registered with routes")
    except Exception as e:
        app.logger.error(f"❌ Failed to register tourism module: {e}")

    # Transport module
    try:
        from app.transport import transport_bp, transport_admin_bp, init_transport_module
        init_transport_module(app)
        app.register_blueprint(transport_bp, url_prefix='/transport')
        app.register_blueprint(transport_admin_bp, url_prefix='/transport/admin')
        app.logger.info("✅ Transport module registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register transport module: {e}")

    # Accommodation module
    try:
        from app.accommodation import accommodation_bp
        app.register_blueprint(accommodation_bp)
        app.logger.info("✅ Accommodation module registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register accommodation module: {e}")

    # Feed module (homepage dynamic feed + sidebar ads)
    try:
        from app.feed import feed_bp
        app.register_blueprint(feed_bp)
        app.logger.info("✅ Feed module registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register feed module: {e}")

    # Event Accommodation module (Layer 1-4 trust & discovery architecture)
    try:
        from app.event_accommodation import event_accommodation_bp
        app.register_blueprint(event_accommodation_bp)
        app.logger.info("✅ Event Accommodation module registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register event accommodation module: {e}")

    # Events module - already registered in core_blueprints

    # Wallet module
    try:
        from app.wallet.routes import wallet_bp
        app.register_blueprint(wallet_bp)
        app.logger.info("✅ Wallet module registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register wallet module: {e}")

    # Notifications module
    try:
        from app.notifications import notifications_api
        app.register_blueprint(notifications_api)
        from app.notifications.pages import communication_pages
        app.register_blueprint(communication_pages)
        app.logger.info("✅ Notifications module registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register notifications module: {e}")

    # Notification signal listeners (decoupled lifecycle notifications)
    try:
        from app.notifications.listeners import register_notification_listeners
        register_notification_listeners()
    except Exception as e:
        app.logger.error(f"❌ Failed to register notification listeners: {e}")

    # Platform event backbone admin/observability API (/api/events)
    try:
        from app.notifications.events.routes import events_api
        app.register_blueprint(events_api)
        app.logger.info("✅ Event backbone API registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register event backbone API: {e}")

    # Correlation-ID propagation for the platform event backbone.
    # Binds X-AFCON360-Correlation-Id per request so every domain event,
    # notification and delivery attempt in one user journey shares a trace id.
    try:
        from app.notifications.events.context import install_request_correlation
        install_request_correlation(app)
        app.logger.info("✅ Event correlation middleware registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register correlation middleware: {e}")

    # CSP Status Routes
    try:
        from app.admin.owner.csp_routes import csp_bp
        app.register_blueprint(csp_bp, url_prefix='/owner/csp')
        app.logger.info("✅ CSP status routes registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register CSP routes: {e}")

    # JSON PIN API
    try:
        from app.wallet.routes_pin import pin_bp
        app.register_blueprint(pin_bp)
    except ImportError:
        app.logger.warning('wallet.routes_pin not found; PIN JSON API endpoints not registered')

    # Payment methods API (register under admin)
    try:
        from app.admin.admin_services.payment_methods import payment_methods_bp
        app.register_blueprint(payment_methods_bp)
    except ImportError:
        logger.warning('admin.admin_services.payment_methods not found; payment methods API not registered')

    # 4. Event Listeners
    try:
        from app.transport.listeners import register_event_listeners
        register_event_listeners()
    except ImportError:
        logger.debug("Transport event listeners not found – skipping")

    # ------------------------------------------------------------------
    # CLI Commands
    # ------------------------------------------------------------------
    from app.cli.owner import register_owner_commands
    register_owner_commands(app)

    try:
        from app.cli import register_all_cli_commands
        register_all_cli_commands(app)
    except ImportError:
        logger.debug("CLI commands not found – skipping")

    # Register IDGuard CLI commands if available
    if IDGUARD_AVAILABLE:
        try:
            register_id_guard_commands(app)
            logger.info("✅ IDGuard CLI commands registered")
        except ImportError:
            logger.warning("IDGuard CLI commands not found – skipping")
        except Exception as e:
            logger.error(f"Failed to register IDGuard CLI commands: {e}")
    else:
        logger.warning("IDGuard CLI commands not available - skipping")

    # ------------------------------------------------------------------
    # Module disabled page handler (always register - handles disabled modules gracefully)
    # ------------------------------------------------------------------
    try:
        from app.utils.module_disabled import module_disabled_bp
        app.register_blueprint(module_disabled_bp)
        app.logger.info("✅ Module disabled page handler registered")
    except ImportError:
        app.logger.warning("Module disabled page handler not found – skipping")
    except Exception as e:
        app.logger.error(f"❌ Failed to register module disabled page handler: {e}")

    # ------------------------------------------------------------------
    # Owner mission-control live monitor (/monitor)
    # ------------------------------------------------------------------
    try:
        from app.monitor import monitor_bp
        app.register_blueprint(monitor_bp)
        app.logger.info("✅ Monitor blueprint registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register monitor blueprint: {e}")

    # ------------------------------------------------------------------
    # Template helpers for module isolation
    # ------------------------------------------------------------------
    from app.utils.template_helpers import register_template_helpers
    register_template_helpers(app)

    # ------------------------------------------------------------------
    # Context processors
    # ------------------------------------------------------------------
    @app.context_processor
    def inject_impersonation_status():
        from flask import session as flask_session
        from app.core.context import RequestContext
        is_impersonating = bool(flask_session.get('impersonated_user_id'))
        impersonated_by = flask_session.get('impersonation_by')
        impersonation_started_at = flask_session.get('impersonation_started_at')
        effective_user = RequestContext.get_effective_user()
        actor_user = RequestContext.get_actor()

        return {
            'is_impersonating': is_impersonating,
            'impersonated_user_id': flask_session.get('impersonated_user_id'),
            'impersonation_by': impersonated_by,
            'impersonation_started_at': impersonation_started_at,
            'effective_user': effective_user,
            'actor_user': actor_user,
        }

    @app.context_processor
    def inject_user_role_info():
        from flask_login import current_user
        from app.auth.decorators import get_highest_role
        from app.auth.routes import _dashboard_for_user

        def user_highest_role():
            if current_user and current_user.is_authenticated:
                return get_highest_role(current_user)
            return None

        def user_dashboard_url():
            if current_user and current_user.is_authenticated:
                return _dashboard_for_user(current_user)
            return url_for('index')

        return {'user_highest_role': user_highest_role(), 'user_dashboard_url': user_dashboard_url()}

    @app.context_processor
    def inject_sitewide() -> Dict:
        # ── resolve nav state ───────────────────────────────────────
        from flask import session as _session
        from flask_login import current_user as _cu

        _profile_completed = False
        _in_org_context = False
        _org_name = None
        _org_id = None
        _org_role = None

        if _cu.is_authenticated:
            try:
                from flask import g as _g
                if not hasattr(_g, '_req_profiles'):
                    _g._req_profiles = {}
                _pk = str(_cu.public_id)
                if _pk not in _g._req_profiles:
                    from app.profile.models import get_profile_by_user
                    _g._req_profiles[_pk] = get_profile_by_user(_cu.public_id)
                _p = _g._req_profiles[_pk]
                _profile_completed = bool(_p and _p.profile_completed)
            except Exception:
                db.session.rollback()
                pass
            # The canonical context resolver is the source of truth for the
            # shared navigation.  The legacy session keys remain a fallback
            # for older sessions, but must not override a live assignment.
            try:
                from app.auth.context import get_active_context

                _active_context = get_active_context(_cu)
                if _active_context.type.value == "organisation":
                    _in_org_context = True
                    _org_id = _active_context.public_id
                    _org_role = _active_context.role
                    _org_name = (_active_context.label or "Organisation").split(" — ", 1)[0]
            except Exception:
                logger.debug("Could not resolve canonical navigation context", exc_info=True)

            if not _in_org_context and _session.get("current_context") == "organization":
                _in_org_context = True
                _org_id = _session.get("current_org_id")
                _org_name = _session.get("current_org_name", "Organisation")
        # ── end nav state ───────────────────────────────────────────

        return {
            "app_name": current_app.config.get("APP_NAME", "AFCON 360"),
            "tournament_name": current_app.config.get("TOURNAMENT_NAME", "AFCON Tournament"),
            "year": current_app.config.get("YEAR", 2025),
            "require_email_verification": current_app.config.get("REQUIRE_EMAIL_VERIFICATION", False),
            "allow_username_login": current_app.config.get("ALLOW_USERNAME_LOGIN", True),
            "tournament_mode": current_app.config.get("MODULE_FLAGS", {}).get("tournament", False),
            # ADD THESE FOUR at the end of the return dict:
            "nav_profile_completed": _profile_completed,
            "nav_in_org_context": _in_org_context,
            "nav_org_name": _org_name,
            "nav_org_id": _org_id,
            "nav_org_role": _org_role,
            "active_global_role": _session.get("active_global_role"),
        }

    def _safe_url(endpoint, *args, **kwargs):
        """Generate URL if endpoint exists, otherwise return '#'.

        This prevents BuildError when a module is disabled or endpoint is missing.
        Catches all exceptions to ensure template rendering never crashes.
        Used by context processors to prevent routing crashes.
        """
        try:
            return url_for(endpoint, *args, **kwargs)
        except Exception:
            logger.debug(f"safe_url: endpoint '{endpoint}' not found or invalid, returning '#'")
            return "#"

    @app.context_processor
    def inject_feature_flags() -> Dict:
        """Inject module feature flags and safe config into all templates.

        Templates MUST use `modules.<feature>` for feature toggling and
        `config.<key>` for application settings.  Access to Flask internals
        such as `current_app` or `view_functions` inside templates is
        STRICTLY FORBIDDEN.
        """
        modules = current_app.config.get("MODULE_FLAGS", {})

        return {
            "modules": modules,
            "config": {
                "app_name": current_app.config.get("APP_NAME", "AFCON 360"),
                "tournament_name": current_app.config.get("TOURNAMENT_NAME", "AFCON Tournament"),
                "year": current_app.config.get("YEAR", 2025),
                "require_email_verification": current_app.config.get("REQUIRE_EMAIL_VERIFICATION", False),
                "allow_username_login": current_app.config.get("ALLOW_USERNAME_LOGIN", True),
            },
            "safe_url": _safe_url,
        }

    @app.context_processor
    def inject_links() -> Dict:
        """Resolve safe links using module flags rather than runtime reflection.

        All URL generation uses _safe_url() to prevent BuildError crashes
        when endpoints are missing or modules are disabled.
        """
        modules = current_app.config.get("MODULE_FLAGS", {})

        # Use _safe_url for all URL generation to prevent BuildError
        links = {
            "auth_login": _safe_url("auth.login"),
            "auth_register": _safe_url("auth.register"),
            "index": _safe_url("index"),
        }
        vf = current_app.view_functions
        links["wallet_home"] = _safe_url("wallet.wallet_home") if modules.get(
            "wallet") and "wallet.wallet_home" in vf else "#"
        links["wallet_dashboard"] = _safe_url("wallet.wallet_dashboard") if modules.get(
            "wallet") and "wallet.wallet_dashboard" in vf else "#"
        links["tournament_home"] = _safe_url("tournament.home") if modules.get(
            "tournament") and "tournament.home" in vf else "#"
        links["tourism_home"] = _safe_url("tourism.home") if modules.get("tourism") and "tourism.home" in vf else "#"
        links["transport_home"] = _safe_url("transport.home") if modules.get(
            "transport") and "transport.home" in vf else "#"
        links["accommodation_index"] = _safe_url("accommodation.guest_search") if modules.get(
            "accommodation") and "accommodation.guest_search" in vf else "#"
        links["kyc_index"] = _safe_url("kyc.index") if "kyc.index" in vf else "#"
        links["profile_public"] = _safe_url("profile.my_public_profile") if "profile.my_public_profile" in vf else "#"
        links["profile_account"] = _safe_url("profile.account_overview") if "profile.account_overview" in vf else "#"
        links["events_list"] = _safe_url("events.list") if "events.list" in vf else "#"
        return {"links": links}

    # ------------------------------------------------------------------
    # CSRF FIX: Returning plain string to prevent double-encoding
    # ------------------------------------------------------------------

    @app.context_processor
    def inject_csrf_token() -> Dict:
        """Inject CSRF token directly to ensure it's not double-encoded"""
        from flask_wtf.csrf import generate_csrf

        # Get the token once
        token = generate_csrf()

        # Define a function that returns the token (makes it callable)
        def csrf_token_func():
            return token

        # Return both - string version and callable version
        return {
            'raw_csrf_token': token,  # For meta tags and JavaScript
            'csrf_token': csrf_token_func  # Callable - use {{ csrf_token() }}
        }

    @app.context_processor
    def inject_wallet_status() -> Dict:
        """Inject wallet status using the centralized service. Cached on g per request."""
        from flask_login import current_user
        from flask import g as _g

        user_has_wallet = False
        wallet_status = None

        if current_user.is_authenticated:
            try:
                if not hasattr(_g, '_wallet_status'):
                    from app.wallet.services.wallet_status_service import WalletStatusService
                    _g._wallet_status = WalletStatusService.get_wallet_status(current_user)
                wallet_status = _g._wallet_status
                user_has_wallet = wallet_status.exists if wallet_status else False
            except Exception:
                pass

        return {
            'user_has_wallet': user_has_wallet,
            'global_wallet_status': wallet_status,
        }

    @app.context_processor
    def utility_processor() -> Dict:
        def intcomma(value):
            """Format number with commas as thousands separators."""
            if value is None:
                return ''
            try:
                return f"{int(value):,}"
            except (ValueError, TypeError):
                return str(value)

        return {'intcomma': intcomma}

    @app.context_processor
    def wallet_utility_processor():
        """Make wallet utilities available in all templates. Reads from g-cache — no extra DB hit."""
        from flask_login import current_user
        from flask import g as _g

        def _get_ws():
            if not current_user.is_authenticated:
                return None
            if not hasattr(_g, '_wallet_status'):
                from app.wallet.services.wallet_status_service import WalletStatusService
                _g._wallet_status = WalletStatusService.get_wallet_status(current_user)
            return _g._wallet_status

        def get_wallet_status():
            return _get_ws()

        def get_sidebar_items():
            if current_user.is_authenticated:
                from app.wallet.services.wallet_status_service import WalletStatusService
                return WalletStatusService.get_visible_sidebar_items(current_user)
            return []

        def get_action_buttons():
            if current_user.is_authenticated:
                from app.wallet.services.wallet_status_service import WalletStatusService
                return WalletStatusService.get_action_buttons(current_user)
            return []

        def get_wallet_banner():
            if current_user.is_authenticated:
                from app.wallet.services.wallet_status_service import WalletStatusService
                return WalletStatusService.get_wallet_banner(current_user)
            return None

        return {
            'get_wallet_status': get_wallet_status,
            'get_sidebar_items': get_sidebar_items,
            'get_action_buttons': get_action_buttons,
            'get_wallet_banner': get_wallet_banner,
        }

    @app.context_processor
    def notification_context_processor():
        """Inject notification + message badge counts and recent items into all templates."""
        from app.notifications.context import inject_notification_context
        return inject_notification_context()

    # ------------------------------------------------------------------
    # Per-module notification scoping
    # ------------------------------------------------------------------
    # AFCON360 runs several independent businesses (accommodation, transport,
    # events, wallet, tourism, tournament) on ONE notification system. When a
    # user is inside a module's console, the notification bell should show that
    # module's activity — not a hotel booking mixed in with a bus booking.
    #
    # Done centrally by URL prefix so each module blueprint stays untouched and
    # new routes are covered automatically. A blueprint can still override by
    # setting `g.notification_module` itself.
    _MODULE_URL_PREFIXES = (
        ('/accommodation', 'accommodation'),
        ('/transport',     'transport'),
        ('/api/transport', 'transport'),
        ('/events',        'events'),
        ('/wallet',        'wallet'),
        ('/api/wallet',    'wallet'),
        ('/tourism',       'tourism'),
        ('/tournament',    'tournament'),
    )

    @app.before_request
    def _scope_notification_module():
        """Tag the request with its originating module for the notification bell."""
        try:
            path = (request.path or '').lower()
            for prefix, module in _MODULE_URL_PREFIXES:
                if path.startswith(prefix):
                    g.notification_module = module
                    return
        except Exception:
            # Never let notification scoping break a request.
            pass

    # Add format_number template filter
    @app.template_filter('format_number')
    def format_number_filter(value):
        """Format number with commas as thousands separators (template filter version)."""
        if value is None:
            return ''
        try:
            # Try to convert to integer first
            return f"{int(value):,}"
        except (ValueError, TypeError):
            # If it's a float, format with 2 decimal places
            try:
                return f"{float(value):,.2f}"
            except (ValueError, TypeError):
                return str(value)

    @app.context_processor
    def inject_kyc_data():
        """Inject KYC tier data into all templates (cached 5 min per user)."""
        from flask_login import current_user
        _empty = {
            'kyc_info': None, 'kyc_tier': 0, 'kyc_tier_name': 'Unregistered',
            'kyc_limits': {}, 'kyc_missing_reqs': [],
            'tier_colors': {0: 'secondary', 1: 'info', 2: 'primary',
                            3: 'success', 4: 'warning', 5: 'danger'}
        }
        if not current_user.is_authenticated:
            return _empty
        _cache_key = f'kyc_ctx_{current_user.id}'
        _cached = cache.get(_cache_key)
        if _cached is not None:
            return _cached
        try:
            from app.auth.kyc_compliance import calculate_kyc_tier, get_user_limits
            kyc_info = calculate_kyc_tier(current_user.id)
            user_limits = get_user_limits(current_user.id)
            result = {
                'kyc_info': kyc_info,
                'kyc_tier': kyc_info.get('tier', 0),
                'kyc_tier_name': kyc_info.get('tier_name', 'Unregistered'),
                'kyc_limits': user_limits,
                'kyc_missing_reqs': kyc_info.get('missing_requirements', []),
                'tier_colors': {0: 'secondary', 1: 'info', 2: 'primary',
                                3: 'success', 4: 'warning', 5: 'danger'}
            }
            cache.set(_cache_key, result, timeout=300)
            return result
        except Exception as e:
            db.session.rollback()
            logger.warning(f"KYC data injection error: {e}")
            return _empty

    @app.context_processor
    def inject_audit_summary():
        """Inject recent audit events for current user (cached 60s per user)."""
        from flask_login import current_user
        if not current_user.is_authenticated:
            return {'audit_summary': []}
        _cache_key = f'audit_summary_{current_user.public_id}'
        _cached = cache.get(_cache_key)
        if _cached is not None:
            return {'audit_summary': _cached}
        try:
            from app.audit.forensic_audit import ForensicAuditService
            timeline = ForensicAuditService.get_audit_timeline(
                entity_type="user",
                entity_id=str(current_user.public_id),
                days=7
            )
            result = timeline[:5]
            cache.set(_cache_key, result, timeout=60)
            return {'audit_summary': result}
        except Exception as e:
            db.session.rollback()
            logger.warning(f"Audit summary injection error: {e}")
            cache.set(_cache_key, [], timeout=60)
            return {'audit_summary': []}

    # Add user context processor
    @app.context_processor
    def inject_user_context():
        """Inject user context into all templates."""
        from flask_login import current_user

        if not current_user.is_authenticated:
            return {}

        # Use the KYC calculator as the single source for identity progress.
        # The profile model has a separate legacy completeness score, which
        # includes optional address fields and can disagree with KYC readiness.
        profile_completion = 0
        try:
            from app.auth.kyc_compliance import calculate_kyc_tier
            profile_completion = int(
                calculate_kyc_tier(current_user.id).get("fulfillment_percentage", 0)
            )
        except Exception as e:
            logger.warning(f"Profile completion calculation error: {e}")

        # Get highest role
        user_highest_role = "Fan"
        if hasattr(current_user, 'is_app_owner') and current_user.is_app_owner():
            user_highest_role = "Owner"
        elif hasattr(current_user, 'has_global_role'):
            if current_user.has_global_role('super_admin'):
                user_highest_role = "Super Admin"
            elif current_user.has_global_role('admin'):
                user_highest_role = "Admin"
            elif current_user.has_global_role('org_admin'):
                user_highest_role = "Org Admin"
            elif current_user.has_global_role('moderator'):
                user_highest_role = "Moderator"
            elif current_user.has_global_role('support'):
                user_highest_role = "Support"

        # Get wallet balance (cached 30s to avoid per-request DB hit)
        wallet_balance = "UGX 0"
        try:
            _wb_key = f'wallet_balance_{current_user.id}'
            _wb_cached = cache.get(_wb_key)
            if _wb_cached is None:
                from app.wallet.services.wallet_service import WalletService
                service = WalletService()
                balance_data = service.get_balance(current_user.id)
                balance_value = balance_data.get('balance', '0.00') if isinstance(balance_data, dict) else '0.00'
                _wb_cached = f"UGX {balance_value}"
                cache.set(_wb_key, _wb_cached, timeout=30)
            wallet_balance = _wb_cached
        except Exception as e:
            logger.warning(f"Wallet balance query error: {e}")

        # Get KYC tier from session or default
        from flask import session
        kyc_tier = session.get('kyc_tier', 0)

        # Canonical operating context.  The resolver revalidates the selected
        # assignment on every request; permissions are deliberately not stored
        # in Flask session.
        try:
            from app.auth.context import (
                get_active_context,
                get_available_contexts,
                resolve_effective_permissions,
            )
            from app.auth.policy import can_in_context

            active_context = get_active_context(current_user)
            available_contexts = get_available_contexts(current_user)
            effective_permissions = resolve_effective_permissions(
                current_user,
                active_context,
            )

            def context_can(permission):
                return can_in_context(
                    current_user,
                    permission,
                    context=active_context,
                )
        except Exception as exc:
            logger.warning("Canonical context injection failed: %s", exc)
            from app.auth.context import ContextType, ContextDescriptor

            active_context = ContextDescriptor(
                type=ContextType.PERSONAL,
                public_id=None,
                label="Personal",
                role="user",
            )
            available_contexts = [active_context]
            effective_permissions = set()

            def context_can(_permission):
                return False

        # Get organization role if in org context
        org_role_name = None
        if active_context.type.value == 'organisation':
            org_role_name = active_context.role or 'Member'

        return {
            'profile_completion': profile_completion,
            'user_highest_role': user_highest_role,
            'wallet_balance': wallet_balance,
            'kyc_tier': kyc_tier,
            'org_role_name': org_role_name,
            'active_context': active_context,
            'available_contexts': available_contexts,
            'effective_permissions': effective_permissions,
            'can': context_can,
        }

    @login_manager.user_loader
    def load_user(public_id):
        """
        Load user by public_id for Flask-Login.

        CONTRACT: The returned User object is a session-scoped identity token,
        NOT a live database object carrier. It is safe for:
            - user.id, user.public_id, user.email (scalar columns)
            - user.roles (UserRole join records, role names via ur.role.name only)

        It is NOT safe for:
            - Any nested relationship beyond one level (role.permissions, etc.)
            - Lazy-loaded attributes accessed outside the request context

        Permission checks MUST use app/auth/helpers.py which queries the DB
        directly by role IDs - never walk role.permissions on detached objects.
        """
        from app.identity.models.user import User
        from sqlalchemy.orm import joinedload
        # Flask-Login sessions must contain User.get_id() (public_id).
        if not public_id:
            return None
        current_app.logger.debug(
            f"USER_LOADER called path={request.path} public_id={public_id}"
        )
        # Check per-request cache first to avoid redundant DB queries
        from flask import g as _g
        if hasattr(_g, '_cached_user_pubid') and _g._cached_user_pubid == public_id:
            return _g._cached_user

        # Check Redis user cache (L2) to avoid DB queries
        _cache_key = f"user:{public_id}"
        _cached = cache.get(_cache_key)
        if _cached is not None:
            # Reconstruct user from cached dict — query by PK only (no expensive joins)
            try:
                user = db.session.get(User, _cached['id'])
                if user:
                    _g._cached_user = user
                    _g._cached_user_pubid = str(user.public_id)
                    current_app.logger.debug(f"USER_LOADER cache hit for {public_id}")
                    return user
            except Exception:
                pass  # Fall through to full query on cache reconstruction failure

        try:
            user = (
                db.session.query(User)
                .options(joinedload(User.roles))
                .filter_by(public_id=public_id)
                .first()
            )
            # Cache the loaded user for the remainder of this request
            if user:
                _g._cached_user = user
                _g._cached_user_pubid = str(user.public_id)  # plain string — safe if user is later detached
                # Store in Redis cache for future requests (L2)
                try:
                    cache.set(_cache_key, {
                        'id': user.id,
                        'public_id': user.public_id,
                        'email': user.email,
                        'username': user.username,
                        'is_active': user.is_active,
                        'is_verified': user.is_verified,
                        'kyc_level': user.kyc_level,
                        'mfa_enabled': user.mfa_enabled,
                    }, timeout=300)
                except Exception:
                    pass  # Cache failure is non-critical
            current_app.logger.debug(
                f"USER_LOADER found={user is not None}"
            )
            return user
        except Exception:
            db.session.rollback()
            current_app.logger.warning(
                f"USER_LOADER exception public_id={public_id}"
            )
            return None

    def invalidate_user_cache(public_id):
        """Invalidate cached user data — call after any user data change."""
        try:
            cache.delete(f"user:{public_id}")
        except Exception:
            pass

    @app.route('/')
    def index():
        try:
            from app.feed.services import FeedService
            from app.models.system_config import SystemConfig

            layout = SystemConfig.get('home_feed_layout', 'mixed')
            if layout not in ('mixed', 'sections', 'tabbed'):
                layout = 'mixed'

            user_id = session.get('user_id')
            page1 = FeedService.get_feed(page=1, per_page=10, layout=layout, user_id=user_id)
            left_ads = FeedService.get_sidebar_ads('home_left', limit=3)
            right_ads = FeedService.get_sidebar_ads('home_right', limit=3)

            return render_template(
                'public_home.html',
                feed_items=page1['items'],
                feed_layout=layout,
                feed_has_more=page1['has_more'],
                feed_next_page=2,
                feed_seed=page1['seed'],
                left_ads=left_ads,
                right_ads=right_ads,
            )
        except Exception as e:
            logger.error(f"Homepage feed error: {e}", exc_info=True)
            # Rollback the session so context processors (which query the DB
            # for current_user) don't fail with InFailedSqlTransaction
            try:
                from app.extensions import db
                db.session.rollback()
            except Exception:
                pass
            return render_template(
                'public_home.html',
                feed_items=[],
                feed_layout='mixed',
                feed_has_more=False,
                feed_next_page=2,
                feed_seed='',
                left_ads=[],
                right_ads=[],
            )

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.is_json:
            return jsonify({"status": "error", "message": "CSRF token missing or invalid"}), 400
        session.clear()
        flash("Your session has expired. Please log in again.", "warning")
        return redirect(url_for("auth.login"))

    @app.before_request
    def set_csp_nonce():
        # Generate a per-request CSP nonce
        import secrets
        from flask import g
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def inject_csp_nonce():
        from flask import g
        nonce = getattr(g, "csp_nonce", None)
        if nonce is None:
            # Fallback if middleware ordering changed
            import secrets
            nonce = secrets.token_urlsafe(16)
        return {"csp_nonce": nonce}

    @app.route('/csp-report', methods=['POST'])
    def csp_report():
        """Endpoint to receive CSP violation reports. Logs payload for analysis."""
        try:
            report = request.get_json(force=True, silent=True) or {}
        except Exception:
            report = {}
        try:
            current_app.logger.warning(f"CSP REPORT: {report}")
        except Exception:
            pass
        return ("", 204)

    # DB schema validation moved to _run_deferred_startup (first-request handler)

    # ===================================================
    # Whre am i
    # ===================================
    from flask import abort
    from flask_login import login_required
    from app.auth.decorators import require_role
    @app.route('/where-am-i')
    @login_required
    @require_role('owner')
    def where_am_i():
        from flask import current_app
        if current_app.config.get('FLASK_ENV') == 'production':
            abort(404)
        from app.extensions import db
        from sqlalchemy import func, inspect, select
        from app.identity.models.user import User
        import os

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        try:
            user_count = db.session.scalar(select(func.count()).select_from(User)) or 0
        except:
            user_count = 0

        return f"""
        <h1>Database Connection Info</h1>
        <p><strong>Config URL:</strong> {current_app.config.get('SQLALCHEMY_DATABASE_URI')}</p>
        <p><strong>Engine URL:</strong> {db.engine.url}</p>
        <p><strong>Tables found:</strong> {tables}</p>
        <p><strong>User count:</strong> {user_count}</p>
        <p><strong>Instance path:</strong> {current_app.instance_path}</p>
        <p><strong>SQLite files:</strong> {[f for f in os.listdir(current_app.instance_path) if f.endswith('.db')]}</p>
        <p><strong>ENV:</strong> FLASK_ENV={os.getenv('FLASK_ENV')}, APP_ENV={os.getenv('APP_ENV')}</p>
        """

    # ------------------------------------------------------------------
    # Module isolation API endpoints
    # ------------------------------------------------------------------
    try:
        from app.admin.owner.api.module_api import module_api_bp
        app.register_blueprint(module_api_bp)
        app.logger.info("✅ Module API blueprint registered")
    except ImportError:
        app.logger.warning("Module API blueprint not found – skipping")
    except Exception as e:
        app.logger.error(f"❌ Failed to register module API blueprint: {e}")

    try:
        from app.api.health import health_bp
        app.register_blueprint(health_bp)
        app.logger.info("✅ Health API blueprint registered")
    except ImportError:
        app.logger.warning("Health API blueprint not found – skipping")
    except Exception as e:
        app.logger.error(f"❌ Failed to register health API blueprint: {e}")

    # ------------------------------------------------------------------
    # Module reload middleware for instant toggle effect
    # ------------------------------------------------------------------
    try:
        from app.middleware.reload_modules import init_module_reload
        # In the stable version, this should actually do something.
        # I'll update reload_modules.py to actually reload.
        init_module_reload(app)
    except Exception as e:
        app.logger.error(f"❌ Failed to initialize module reload middleware: {e}")

    @app.before_request
    def check_module_enabled():
        """Check if requested module is enabled before processing request"""
        from flask import request, render_template
        from app.utils.module_guard import module_enabled

        # Skip checks for static files, health checks, and admin routes
        if request.path.startswith('/static') or request.path.startswith('/health') or request.path.startswith(
                '/admin'):
            return

        # Extract module name from path
        path_parts = request.path.strip('/').split('/')
        if path_parts and path_parts[0] in ['tourism', 'transport', 'accommodation', 'tournament', 'wallet', 'events']:
            module_name = path_parts[0]
            if not module_enabled(module_name):
                return render_template('module_disabled.html', module=module_name), 404

    # ── Theme CSS generation deferred to first request ──────────────────────────────
    # Global theme CSS will be generated on first access via theme routes
    # This prevents EventTheme initialization issues during app startup

    # ------------------------------------------------------------------
    # Startup Endpoint Validator (non-blocking, runs in background)
    # ------------------------------------------------------------------
    def _validate_endpoint_references():
        """Check known endpoint references against actual app.url_map."""
        import logging as _logging
        _log = _logging.getLogger("app.endpoint_validator")

        _known_refs = [
            "admin.owner.dashboard",
            "admin.owner.settings",
            "admin.owner.manage_aggregators",
            "admin.owner.configure_fraud_detection",
            "admin.owner.configure_nonce_protection",
            "admin.owner.configure_travel_rule",
            "admin.owner.add_payment_gateway",
            "admin.owner.security_dashboard",
            "admin.owner.audit_logs",
            "admin.owner.users",
            "admin.owner.manage_roles",
            "admin.owner.danger_zone",
            "admin.owner.system_health",
            "admin.owner.error_logs",
            "admin.owner.impersonate_page",
            "admin.owner.kyc_tier_management",
            "admin.owner.compliance_dashboard",
            "admin.owner.auth_settings",
            "accommodation.guest_search",
            "accommodation.admin_dashboard",
            "accommodation.admin_main_dashboard",
            "accommodation.legacy_detail",
            "wallet.wallet_home",
            "wallet.wallet_dashboard",
            "events.list",
            "events.events_hub",
            "events.event_staff",
            "events.staff_dashboard",
            "events.search_users",
            "events.update_staff",
            "events.remove_staff",
            "auth.login",
            "auth.register",
            "user.dashboard",
            "profile.my_public_profile",
            "profile.account_overview",
            "kyc.index",
            "tourism.home",
            "transport.home",
            "tournament.home",
        ]

        _rules = {rule.endpoint for rule in app.url_map.iter_rules()}
        _missing = [ref for ref in _known_refs if ref not in _rules]

        if _missing:
            _log.warning(
                "⚠️  Missing endpoint references detected (will cause url_for errors):\n%s",
                "\n".join(f"  - {m}" for m in _missing)
            )
        else:
            _log.info("✅ All known endpoint references validated successfully")

    # Run in background thread to avoid blocking startup
    import threading
    threading.Thread(target=_validate_endpoint_references, daemon=True).start()

    logger.info(f"✅ App factory completed in {time.time() - start_time:.2f} seconds")
    return app
