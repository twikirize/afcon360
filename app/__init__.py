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
from datetime import datetime

# Load environment variables at the very beginning
from dotenv import load_dotenv
load_dotenv()

# Ensure ENCRYPTION_KEY is set for development
if not os.getenv('ENCRYPTION_KEY'):
    # Generate a temporary key for development
    import secrets
    temp_key = secrets.token_urlsafe(32)
    os.environ['ENCRYPTION_KEY'] = temp_key
    logging.warning(f"ENCRYPTION_KEY not set. Generated a temporary key for development. "
                    f"Please add ENCRYPTION_KEY={temp_key} to your .env file for consistency.")

# Now we can safely import other modules that may depend on environment variables

# Import Redis conditionally. Allow forcing disable via DISABLE_REDIS env var for local runs.
try:
    import redis
    # Allow developer to force-disable Redis checks when running locally
    if os.getenv('DISABLE_REDIS', 'false').lower() in ('1', 'true', 'yes'):
        redis = None
        REDIS_AVAILABLE = False
        logging.warning("Redis checks disabled via DISABLE_REDIS environment variable")
    else:
        REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False
    logging.warning("Redis not available - some features may be limited")

# Import IDGuard for runtime protection against ID mixing
try:
    from app.utils.id_guard import init_id_guard, register_id_guard_commands
    IDGUARD_AVAILABLE = True
except ImportError:
    IDGUARD_AVAILABLE = False
    logging.warning("IDGuard not available - ID mixing protection disabled")
from flask import Flask, flash, redirect, render_template, session, current_app, url_for, request, jsonify

try:
    from flask_session import Session

    FLASK_SESSION_AVAILABLE = True
except ImportError:
    Session = None
    FLASK_SESSION_AVAILABLE = False
    logging.warning("Flask-Session not available - using fallback sessions")
from flask_wtf.csrf import CSRFError
from typing import Dict
from app.config import Config
from app.extensions import db, migrate, login_manager, csrf, limiter, cache, redis_client
from app.services.module_toggle_service import ModuleToggleService


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


def require_redis(url: str, purpose: str, existing_client=None):
    """
    Ensure Redis is available before starting the app.
    Raises RuntimeError if Redis connection fails.
    """
    if existing_client:
        # Test the existing client connection with shorter timeout
        try:
            existing_client.ping()
            return existing_client
        except Exception:
            pass  # Fall through silently to create new connection

    if not REDIS_AVAILABLE:
        logging.warning(f"Redis not available for {purpose} - using fallback")
        return None

    try:
        # Optimization: much shorter timeout for startup, no decode for performance
        client = redis.Redis.from_url(url, decode_responses=False, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return client
    except Exception as e:
        error_msg = f"Redis must be running at {url} for AFCON360 to start ({purpose}). Error: {e}"
        logging.error(error_msg)
        raise RuntimeError(error_msg) from e


def create_app(config_object=None) -> Flask:
    """
    Application factory pattern.
    """
    start_time = time.time()

    base_dir = os.path.abspath(os.path.dirname(__file__))
    template_path = os.path.join(base_dir, "..", "templates")
    project_root = os.path.abspath(os.path.join(base_dir, ".."))
    static_path = os.path.join(project_root, "static")

    # Environment already loaded at module level

    app = Flask(__name__, static_folder=static_path, template_folder=template_path)

    # Remove Flask's default handler to prevent duplicate logging
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

    # Load configuration
    app.config.from_object(config_object or Config)

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
    # Redis & Extensions (Shared)
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

    # Configure Redis for caching
    cache.config.update({
        "CACHE_TYPE": "RedisCache",
        "CACHE_REDIS_URL": redis_url,
        "CACHE_DEFAULT_TIMEOUT": 300
    })
    redis_client.configure(redis_url)

    # Configure Flask-Limiter to use Redis
    # Set storage URI in app config
    app.config["RATELIMIT_STORAGE_URI"] = redis_url
    # Also update the limiter instance
    limiter.storage_uri = redis_url

    # Get Redis client for sessions - reuse existing connection
    redis_session_client = None
    try:
        redis_session_client = redis_client.client
        # Skip ping test to avoid delay - trust the existing connection
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

    if REDIS_AVAILABLE:
        cache.init_app(app, config={"CACHE_TYPE": "RedisCache", "CACHE_REDIS_URL": redis_url})
    else:
        cache.init_app(app, config={"CACHE_TYPE": "SimpleCache"})

    # Initialize limiter with app
    # The storage URI should already be set in app.config["RATELIMIT_STORAGE_URI"]
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

    @app.after_request
    def log_response(response):
        """Clean response logging"""
        # Skip static assets
        if request.path.startswith(('/static/', '/favicon.ico', '/theme/css/')):
            return response
        
        # Determine icon based on status
        if response.status_code >= 500:
            icon = "💥"
            log_func = logger.error
        elif response.status_code >= 400:
            icon = "⚠️"
            log_func = logger.warning
        else:
            icon = "✅"
            log_func = logger.debug
        
        # Log only non-200 responses in normal mode, all in debug
        if response.status_code != 200 or app.debug:
            log_func(f"{icon} {request.method} {request.path} → {response.status_code}")
        
        return response
    
    # Keep 404 handler but make it cleaner
    @app.errorhandler(404)
    def handle_404(error):
        """Clean 404 handler"""
        # Don't log missing favicon or static files
        if request.path.startswith(('/favicon.ico', '/static/')):
            return render_template('errors/404.html'), 404
        
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
                    "timestamp": datetime.utcnow().isoformat(),
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
    from app.core.model_registry import register_all_models
    register_all_models()

    # Verify Redis is available for rate limiting only if needed
    if REDIS_AVAILABLE and app.config.get("RATELIMIT_STORAGE_URI", "").startswith("redis://"):
        # Skip verification to avoid startup delay - trust the connection
        pass

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

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

    # ------------------------------------------------------------------
    # SESSION SECURITY (Corrected for Localhost)
    # ------------------------------------------------------------------
    # Only enforce secure cookies in production (not in debug mode)
    app.config["SESSION_COOKIE_SECURE"] = not app.config.get('DEBUG', False)
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    # ------------------------------------------------------------------
    # Global Identity Context Loader
    # ------------------------------------------------------------------
    @app.before_request
    def load_identity_context():
        """Inject real actor and effective user into request context for every request."""
        try:
            from flask_login import current_user
            from flask import session as flask_session, request as flask_request
            from app.core.context import RequestContext
            from app.identity.models.user import User
            from app.extensions import db

            # Real actor is the authenticated Flask-Login user
            actor_user = current_user if getattr(current_user, "is_authenticated", False) else None
            RequestContext.set_actor(actor_user)

            # Effective user is impersonated user if set, else the actor
            effective_user = actor_user
            impersonated_id = flask_session.get("impersonated_user_id")
            if impersonated_id:
                try:
                    # Prefer session.get via SQLAlchemy 2 if available
                    user = db.session.get(User, impersonated_id) if hasattr(db.session, 'get') else None
                except Exception:
                    db.session.rollback()
                    user = None
                if not user:
                    try:
                        user = User.query.get(impersonated_id)
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
        try:
            db.session.remove()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass

    @app.teardown_request
    def handle_transaction(exception=None):
        try:
            if exception:
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
    _deferred_done = threading.Event()
    _deferred_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Middleware - Module Runtime Checks
    # ------------------------------------------------------------------
    @app.before_request
    def check_module_enabled():
        """Check if requested module is enabled before processing request"""
        from flask import request, render_template
        from app.utils.module_guard import module_enabled
        
        # Skip checks for static files, health checks, and admin routes
        if request.path.startswith('/static') or request.path.startswith('/health') or request.path.startswith('/admin'):
            return
        
        # Extract module name from path (e.g., /tourism/... -> tourism)
        path_parts = request.path.strip('/').split('/')
        if path_parts and path_parts[0] in ['tourism', 'transport', 'accommodation', 'tournament', 'wallet', 'events']:
            module_name = path_parts[0]
            if not module_enabled(module_name):
                return render_template('module_disabled.html', module=module_name), 404

    # ------------------------------------------------------------------
    # Redis Pub/Sub Subscriber for Real-Time Module Updates
    # ------------------------------------------------------------------
    def start_module_toggle_subscriber():
        """Subscribe to Redis Pub/Sub for real-time module toggle updates"""
        try:
            from app.extensions import redis_client
            redis_client.client  # Trigger connection
            pubsub = redis_client.pubsub()
            pubsub.subscribe('module_toggles')
            logger.info("Redis Pub/Sub subscriber started for module toggles")
            
            def listen_for_toggles():
                """Background thread to listen for module toggle events"""
                try:
                    for message in pubsub.listen():
                        if message['type'] == 'message':
                            data = message['data'].decode('utf-8')
                            module, enabled = data.split(':')
                            enabled = enabled.lower() == 'true'
                            
                            # Update in-memory config immediately
                            app.config['MODULE_FLAGS'][module] = enabled
                            app.config[f"{module.upper()}_ENABLED"] = enabled
                            
                            # Invalidate request-scoped cache
                            from flask import g
                            if hasattr(g, 'module_flags_loaded'):
                                g.module_flags_loaded = False
                            
                            logger.info(f"Module toggle received via Pub/Sub: {module}={enabled}")
                except Exception as e:
                    logger.error(f"Error in module toggle subscriber: {e}")
            
            # Start listener in background thread
            import threading
            subscriber_thread = threading.Thread(target=listen_for_toggles, daemon=True)
            subscriber_thread.start()
            
        except Exception as e:
            logger.warning(f"Failed to start module toggle subscriber: {e}")

    @app.before_request
    def _run_deferred_startup():
        if _deferred_done.is_set():
            return
        with _deferred_lock:
            if _deferred_done.is_set():
                return
            _deferred_done.set()
            # 1. DB module flags already loaded during create_app (single source of truth)
            # No need to reload here
            # 2. Validate DB schema (purely informational)
            try:
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

    # ------------------------------------------------------------------
    # Lazy Imports - Blueprints & Models
    # ------------------------------------------------------------------
    from app.identity import models as identity_models
    from app.profile import models as profile_models
    from app.audit import models as audit_models
    from app.auth import roles as role_models
    from app.admin import models as admin_models  # Required for Alembic to detect ModerationLog

    # Core Web Blueprints
    from app.auth.routes import auth_bp
    from app.auth.onboarding_routes import onboarding_bp
    from app.fan.routes import fan_bp
    from app.user.routes import user_bp  # Added user blueprint
    # from app.wallet.routes import wallet_bp  # DELETED - will be rebuilt
    from app.admin import admin_bp
    try:
        from app.events import events_bp
    except ImportError as e:
        logger.warning(f"Events blueprint not found: {e}")
        # Create a dummy blueprint to prevent crashes
        from flask import Blueprint
        events_bp = Blueprint('events', __name__)
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

    optional_blueprints = [
        ('org_bp', 'app.identity.routes'),
        ('compliance_bp', 'app.admin.compliance.routes'),
        ('auditor_bp', 'app.admin.auditor.routes'),
        ('support_bp', 'app.admin.support.routes'),
        ('moderator_bp', 'app.admin.moderator'),
    ]

    for bp_name, module_path in optional_blueprints:
        try:
            module = import_module(module_path)
            bp = getattr(module, bp_name, None)
            if bp:
                locals()[bp_name] = bp
            else:
                logger.debug(f"Blueprint {bp_name} not found in {module_path}")
        except ImportError:
            logger.debug(f"Module {module_path} not available - blueprint {bp_name} skipped")
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

    # Add auth KYC blueprint if available
    if auth_kyc_bp:
        core_blueprints.append((auth_kyc_bp, None))

    # Removed registration of non-existent blueprints
    # Their functionality is handled within admin_bp

    for bp, prefix in core_blueprints:
        app.register_blueprint(bp, url_prefix=prefix)

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

    # 2. Register API Blueprints
    api_blueprints = [wallet_api_bp, fx_api_bp, webhooks_bp, admin_api_bp]
    for bp in api_blueprints:
        app.register_blueprint(bp)

    # 3. Load database module flags BEFORE blueprint registration (single source of truth)
    with app.app_context():
        try:
            from app.services.module_toggle_service import ModuleToggleService
            ModuleToggleService.load_overrides_into_app()
            logger.debug("✅ Module flags loaded from DB (single source of truth)")
        except Exception as exc:
            logger.warning(f"Failed to load module flags from DB: {exc}")

        # Start Redis Pub/Sub subscriber for real-time module updates
        start_module_toggle_subscriber()

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

    # Events module - already registered in core_blueprints

    # Wallet module
    try:
        from app.wallet.routes import wallet_bp
        app.register_blueprint(wallet_bp)
        app.logger.info("✅ Wallet module registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register wallet module: {e}")

    # JSON PIN API
    try:
        from app.wallet.routes_pin import pin_bp
        app.register_blueprint(pin_bp)
    except ImportError:
        app.logger.warning('wallet.routes_pin not found; PIN JSON API endpoints not registered')
    
    # Payment methods API (register under admin)
    try:
        from app.admin.services.payment_methods import payment_methods_bp
        app.register_blueprint(payment_methods_bp)
    except ImportError:
        logger.warning('admin.services.payment_methods not found; payment methods API not registered')

    # 4. Event Listeners
    try:
        from app.transport.listeners import register_event_listeners
        register_event_listeners()
    except ImportError:
        pass

    # ------------------------------------------------------------------
    # CLI Commands
    # ------------------------------------------------------------------
    from app.cli.owner import register_owner_commands
    register_owner_commands(app)

    try:
        from app.cli import register_all_cli_commands
        register_all_cli_commands(app)
    except ImportError:
        pass

    # Register IDGuard CLI commands if available
    if IDGUARD_AVAILABLE:
        try:
            register_id_guard_commands(app)
            logger.info("✅ IDGuard CLI commands registered")
        except Exception as e:
            logger.error(f"Failed to register IDGuard CLI commands: {e}")
    else:
        logger.warning("IDGuard CLI commands not available - skipping")

    # ------------------------------------------------------------------
    # Initialize Event Signal Handlers
    # ------------------------------------------------------------------
    try:
        from app.events.signal_handlers import connect_event_signal_handlers
        connect_event_signal_handlers()
        logger.info("✅ Event signal handlers connected")
    except ImportError as e:
        logger.warning(f"Could not import event signal handlers: {e}")
    except Exception as e:
        logger.error(f"Failed to connect event signal handlers: {e}")

    # ------------------------------------------------------------------
    # Module disabled page handler (always register - handles disabled modules gracefully)
    # ------------------------------------------------------------------
    try:
        from app.utils.module_disabled import module_disabled_bp
        app.register_blueprint(module_disabled_bp)
        app.logger.info("✅ Module disabled page handler registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register module disabled page handler: {e}")

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
                pass
            _in_org_context = _session.get("current_context") == "organization"
            if _in_org_context:
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
            "nav_in_org_context":    _in_org_context,
            "nav_org_name":          _org_name,
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
        links["wallet_home"] = _safe_url("wallet.wallet_home") if modules.get("wallet") and "wallet.wallet_home" in vf else "#"
        links["wallet_dashboard"] = _safe_url("wallet.wallet_dashboard") if modules.get("wallet") and "wallet.wallet_dashboard" in vf else "#"
        links["tournament_home"] = _safe_url("tournament.home") if modules.get("tournament") and "tournament.home" in vf else "#"
        links["tourism_home"] = _safe_url("tourism.home") if modules.get("tourism") and "tourism.home" in vf else "#"
        links["transport_home"] = _safe_url("transport.home") if modules.get("transport") and "transport.home" in vf else "#"
        links["accommodation_index"] = _safe_url("accommodation.guest.search") if modules.get("accommodation") and "accommodation.guest.search" in vf else "#"
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
            'raw_csrf_token': token,      # For meta tags and JavaScript
            'csrf_token': csrf_token_func  # Callable - use {{ csrf_token() }}
        }

    @app.context_processor
    def inject_wallet_status() -> Dict:
        user_has_wallet = False
        if session.get('user_id'):
            try:
                from app.wallet.repositories.wallet_repository import WalletRepository
                repo = WalletRepository()
                user_has_wallet = repo.get_by_user_id(session.get('user_id')) is not None
            except:
                pass
        return {'user_has_wallet': user_has_wallet}

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
        """Make wallet status available in all templates"""
        from flask_login import current_user
        from app.wallet.services.wallet_status_service import WalletStatusService
        
        def get_wallet_status():
            if current_user.is_authenticated:
                return WalletStatusService.get_wallet_status(current_user)
            return None
        
        def get_sidebar_items():
            if current_user.is_authenticated:
                return WalletStatusService.get_visible_sidebar_items(current_user)
            return []
        
        def get_action_buttons():
            if current_user.is_authenticated:
                return WalletStatusService.get_action_buttons(current_user)
            return []
        
        def get_wallet_banner():
            if current_user.is_authenticated:
                return WalletStatusService.get_wallet_banner(current_user)
            return None
        
        return {
            'get_wallet_status': get_wallet_status,
            'get_sidebar_items': get_sidebar_items,
            'get_action_buttons': get_action_buttons,
            'get_wallet_banner': get_wallet_banner
        }

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
        from app.profile.models import get_profile_by_user

        if not current_user.is_authenticated:
            return {}

        # Calculate profile completion percentage (use g-cache to avoid duplicate DB query)
        profile_completion = 0
        try:
            from flask import g as _g
            if not hasattr(_g, '_req_profiles'):
                _g._req_profiles = {}
            _pk = str(current_user.public_id)
            if _pk not in _g._req_profiles:
                _g._req_profiles[_pk] = get_profile_by_user(current_user.public_id)
            profile = _g._req_profiles[_pk]
            if profile:
                # Check various profile fields
                fields_to_check = [
                    ('full_name', bool(getattr(profile, 'full_name', None))),
                    ('phone_number', bool(getattr(profile, 'phone_number', None))),
                    ('email_verified', getattr(profile, 'email_verified', False)),
                    ('phone_verified', getattr(profile, 'phone_verified', False)),
                    ('address', bool(getattr(profile, 'address', None))),
                ]
                completed = sum(1 for _, is_complete in fields_to_check if is_complete)
                profile_completion = int((completed / len(fields_to_check)) * 100)
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

        # Get organization role if in org context
        org_role_name = None
        if session.get('current_context') == 'organization' and session.get('current_org_id'):
            org_role_name = session.get('org_role_name', 'Member')

        return {
            'profile_completion': profile_completion,
            'user_highest_role': user_highest_role,
            'wallet_balance': wallet_balance,
            'kyc_tier': kyc_tier,
            'org_role_name': org_role_name,
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
        try:
            return (
                db.session.query(User)
                .options(joinedload(User.roles))
                .filter_by(public_id=public_id)
                .first()
            )
        except Exception:
            db.session.rollback()
            return None

    @app.route('/')
    def index():
        try:
            from app.events.services import EventService
            featured_event = EventService.get_featured_event()
            other_events = EventService.get_upcoming_events(limit=2, exclude_featured=True)
            return render_template('public_home.html', featured_event=featured_event, other_events=other_events)
        except:
            return render_template('public_home.html', featured_event=None, other_events=[])

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
        return {"csp_nonce": getattr(g, "csp_nonce", None)}

    @app.after_request
    def apply_security_headers(response):
        from flask import g
        nonce = getattr(g, "csp_nonce", "")
        # Strict CSP for scripts using per-request nonce. We still allow inline styles for now to
        # avoid regressions; a Report-Only header below shows violations for a future no-inline style policy.
        csp_enforce = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "upgrade-insecure-requests;"
        )
        response.headers["Content-Security-Policy"] = csp_enforce

        # Report-Only header to monitor a stricter style policy (no inline styles)
        csp_report_only = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self' https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "upgrade-insecure-requests; "
            "report-to csp-endpoint; report-uri /csp-report"
        )
        response.headers["Content-Security-Policy-Report-Only"] = csp_report_only

        # Reporting endpoints (Report-To / Reporting-Endpoints for broader browser support)
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
        # Additional modern security headers
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        if session.get("user_id"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        return response

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




    #===================================================
    #Whre am i
    #===================================
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
        from sqlalchemy import inspect, text
        import os

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        # Try raw SQL
        try:
            result = db.session.execute(text("SELECT COUNT(*) FROM users")).fetchone()
            user_count = result[0]
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
    except Exception as e:
        app.logger.error(f"❌ Failed to register module API blueprint: {e}")

    try:
        from app.api.health import health_bp
        app.register_blueprint(health_bp)
        app.logger.info("✅ Health API blueprint registered")
    except Exception as e:
        app.logger.error(f"❌ Failed to register health API blueprint: {e}")

    # ------------------------------------------------------------------
    # Module reload middleware for instant toggle effect
    # ------------------------------------------------------------------
    try:
        from app.middleware.reload_modules import init_module_reload
        init_module_reload(app)
    except Exception as e:
        app.logger.error(f"❌ Failed to initialize module reload middleware: {e}")

    # ── Theme CSS generation deferred to first request ──────────────────────────────
    # Global theme CSS will be generated on first access via theme routes
    # This prevents EventTheme initialization issues during app startup

    logger.info(f"✅ App factory completed in {time.time() - start_time:.2f} seconds")
    return app

    # Diagnostic routes for identity separation testing
    
