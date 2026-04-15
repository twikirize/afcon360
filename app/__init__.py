# app/__init__.py
"""
# Changes vs original:
#   [P0] REMOVED remove_csp() — it was stripping CSP in production due to
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
from datetime import datetime, date, timedelta

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

# Import Redis conditionally
try:
    import redis

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
from flask import Flask, flash, redirect, render_template, session, current_app, url_for, request, Response, jsonify

try:
    from flask_session import Session

    FLASK_SESSION_AVAILABLE = True
except ImportError:
    Session = None
    FLASK_SESSION_AVAILABLE = False
    logging.warning("Flask-Session not available - using fallback sessions")
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFError
from typing import Dict, List
from app.config import Config
from app.extensions import db, migrate, login_manager, csrf, limiter, cache, redis_client


# Configure logging globally at the entry point
def configure_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
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
        # Test the existing client connection
        try:
            existing_client.ping()
            logging.info(f"Redis connected for {purpose} using existing client at {url}")
            return existing_client
        except Exception as e:
            logging.warning(f"Existing Redis client failed ping for {purpose}: {e}. Creating new connection.")
            # Fall through to create new connection

    if not REDIS_AVAILABLE:
        logging.warning(f"Redis not available for {purpose} - using fallback")
        return None

    try:
        # Optimization: shorter timeout for startup check
        client = redis.Redis.from_url(url, decode_responses=False, socket_connect_timeout=2)
        client.ping()
        logging.info(f"Redis connected for {purpose} at {url}")
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

    # Load configuration
    app.config.from_object(config_object or Config)

    # Set default rate limit to 100 requests per minute
    app.config['RATELIMIT_DEFAULT'] = "100 per minute"

    # CSRF Configuration
    app.config['WTF_CSRF_ENABLED'] = os.getenv('WTF_CSRF_ENABLED', 'true').lower() == 'true'
    app.config['WTF_CSRF_SECRET_KEY'] = os.getenv('WTF_CSRF_SECRET_KEY') or app.config.get('SECRET_KEY')
    app.config['WTF_CSRF_TIME_LIMIT'] = int(os.getenv('WTF_CSRF_TIME_LIMIT', '3600'))
    app.config['WTF_CSRF_SSL_STRICT'] = os.getenv('WTF_CSRF_SSL_STRICT', 'false').lower() == 'true'
    app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken', 'X-CSRF-Token']
    app.config['WTF_CSRF_FIELD_NAME'] = 'csrf_token'
    app.config['WTF_CSRF_CHECK_DEFAULT'] = True
    app.config['WTF_CSRF_METHODS'] = ['POST', 'PUT', 'PATCH', 'DELETE']

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

    # Get Redis client for sessions
    redis_session_client = None
    try:
        redis_session_client = redis_client.client
        redis_session_client.ping()
    except Exception:
        redis_session_client = None

    if redis_session_client:
        try:
            redis_session_client = require_redis(redis_url, "sessions", existing_client=redis_session_client)
        except Exception:
            redis_session_client = require_redis(redis_url, "sessions")
    else:
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

    # Verify Redis is available for rate limiting if configured
    if REDIS_AVAILABLE and app.config.get("RATELIMIT_STORAGE_URI", "").startswith("redis://"):
        try:
            require_redis(app.config["RATELIMIT_STORAGE_URI"], "rate limiting")
        except Exception as e:
            logger.warning(f"Rate limiting Redis connection failed: {e}")

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Your session has expired. Please log in again.'
    login_manager.login_message_category = 'warning'

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
    # Lazy Imports - Blueprints & Models
    # ------------------------------------------------------------------
    from app.identity import models as identity_models
    from app.profile import models as profile_models
    from app.audit import models as audit_models
    from app.auth import roles as role_models

    # Attempt to load KYC models
    try:
        from app.kyc import models as kyc_models
    except ImportError:
        kyc_models = None

    # Core Web Blueprints
    from app.auth.routes import auth_bp
    from app.fan.routes import fan_bp
    from app.wallet.routes import wallet_bp
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

    # Import auth KYC blueprint
    try:
        from app.auth.kyc_routes import auth_kyc_bp
    except ImportError as e:
        auth_kyc_bp = None
        logger.warning(f"Auth KYC routes not found: {e}")

    # Missing blueprints - import with fallback
    org_bp = None
    compliance_bp = None
    auditor_bp = None
    support_bp = None
    moderator_bp = None

    try:
        from app.org.routes import org_bp
    except ImportError:
        logger.warning("org_bp not found - skipping registration")

    try:
        from app.admin.compliance.routes import compliance_bp
    except ImportError:
        logger.warning("compliance_bp not found - skipping registration")

    try:
        from app.admin.auditor.routes import auditor_bp
    except ImportError:
        logger.warning("auditor_bp not found - skipping registration")

    try:
        from app.admin.support.routes import support_bp
    except ImportError:
        logger.warning("support_bp not found - skipping registration")

    try:
        from app.admin.moderator.routes import moderator_bp
    except ImportError:
        logger.warning("moderator_bp not found - skipping registration")
    # API Blueprints
    from app.wallet.api.wallet_api import wallet_api_bp
    from app.wallet.api.admin_api import admin_wallet_bp
    from app.wallet.api.audit_api import audit_bp
    from app.wallet.api.webhook_api import webhook_bp

    # Feature-Based Blueprints
    from app.tournament import tournament_bp
    from app.tourism import tourism_bp
    from app.transport import transport_bp, transport_admin_bp
    from app.accommodation import accommodation_bp

    # ------------------------------------------------------------------
    # Register Blueprints
    # ------------------------------------------------------------------

    # 1. Register Core & Static Blueprints
    core_blueprints = [
        (admin_bp, None),
        (auth_bp, None),
        (fan_bp, None),
        (wallet_bp, None),
        (events_bp, None),
        (theme_bp, None),
        (kyc_bp, '/kyc'),  # Fixed: Added KYC with prefix
    ]

    # Add auth KYC blueprint if available
    if auth_kyc_bp:
        core_blueprints.append((auth_kyc_bp, None))

    # Removed registration of non-existent blueprints
    # Their functionality is handled within admin_bp

    for bp, prefix in core_blueprints:
        app.register_blueprint(bp, url_prefix=prefix)

    # 2. Register API Blueprints
    api_blueprints = [wallet_api_bp, admin_wallet_bp, audit_bp, webhook_bp]
    for bp in api_blueprints:
        app.register_blueprint(bp)

    # 3. Conditional Feature Blueprints
    if app.config.get("TOURNAMENT_ENABLED", True):
        app.register_blueprint(tournament_bp)

    if app.config.get("TOURISM_ENABLED", True):
        app.register_blueprint(tourism_bp)

    if app.config.get("TRANSPORT_ENABLED", True):
        from app.transport import init_transport_module
        init_transport_module(app)
        app.register_blueprint(transport_bp, url_prefix='/transport')
        app.register_blueprint(transport_admin_bp, url_prefix='/transport/admin')

    if app.config.get("ACCOMMODATION_ENABLED", True):
        app.register_blueprint(accommodation_bp)

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
        # Connect event signal handlers
        with app.app_context():
            connect_event_signal_handlers()
        logger.info("✅ Event signal handlers connected")
    except ImportError as e:
        logger.warning(f"Could not import event signal handlers: {e}")
    except Exception as e:
        logger.error(f"Failed to connect event signal handlers: {e}")

    # ------------------------------------------------------------------
    # Context processors
    # ------------------------------------------------------------------
    @app.context_processor
    def inject_impersonation_status():
        is_impersonating = bool(session.get('impersonated_by') or session.get('owner_impersonating'))
        # Get values from session, ensuring they are strings and not None
        impersonated_role = session.get('impersonated_role')
        impersonated_by = session.get('impersonated_by_name')

        # Convert to empty string if None
        if impersonated_role is None:
            impersonated_role = ''
        else:
            # Ensure it's a string
            impersonated_role = str(impersonated_role)

        if impersonated_by is None:
            impersonated_by = ''
        else:
            # Ensure it's a string
            impersonated_by = str(impersonated_by)

        return {
            'is_impersonating': is_impersonating,
            'impersonated_role': impersonated_role,
            'impersonated_by': impersonated_by
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
        return {
            "app_name": current_app.config.get("APP_NAME", "AFCON 360"),
            "tournament_name": current_app.config.get("TOURNAMENT_NAME", "AFCON Tournament"),
            "year": current_app.config.get("YEAR", 2025),
        }

    @app.context_processor
    def inject_links() -> Dict:
        def resolve_endpoint(candidates, default="#"):
            for ep in candidates:
                try:
                    return url_for(ep)
                except:
                    continue
            return default

        modules = {
            "wallet_home": ["wallet.wallet_home"],
            "wallet_dashboard": ["wallet.wallet_dashboard"],
            "tournament_home": ["tournament.home"],
            "auth_login": ["auth.login"],
            "auth_register": ["auth.register"],
            "index": ["index"],
        }
        links = {k: resolve_endpoint(v, f"/{k}") for k, v in modules.items()}
        return {"links": links, **inject_sitewide()}

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
    def inject_kyc_data():
        """Inject KYC tier data into all templates."""
        from flask_login import current_user
        if current_user.is_authenticated:
            try:
                db.session.rollback()   # ensure clean state before any query
                from app.auth.kyc_compliance import calculate_kyc_tier, get_user_limits
                # current_user.id is internal BIGINT id (from User model)
                kyc_info = calculate_kyc_tier(current_user.id)
                user_limits = get_user_limits(current_user.id)
                return {
                    'kyc_info': kyc_info,
                    'kyc_tier': kyc_info.get('tier', 0),
                    'kyc_tier_name': kyc_info.get('tier_name', 'Unregistered'),
                    'kyc_limits': user_limits,
                    'kyc_missing_reqs': kyc_info.get('missing_requirements', []),
                    'tier_colors': {0: 'secondary', 1: 'info', 2: 'primary',
                                   3: 'success', 4: 'warning', 5: 'danger'}
                }
            except Exception as e:
                db.session.rollback()
                logger.warning(f"KYC data injection error: {e}")
        return {
            'kyc_info': None,
            'kyc_tier': 0,
            'kyc_tier_name': 'Unregistered',
            'kyc_limits': {},
            'kyc_missing_reqs': [],
            'tier_colors': {0: 'secondary', 1: 'info', 2: 'primary',
                           3: 'success', 4: 'warning', 5: 'danger'}
        }

    @app.context_processor
    def inject_audit_summary():
        """Inject recent audit events for current user."""
        from flask_login import current_user
        if current_user.is_authenticated:
            try:
                db.session.rollback()   # ensure clean state before any query
                from app.audit.forensic_audit import ForensicAuditService
                # Use public_id for entity_id
                timeline = ForensicAuditService.get_audit_timeline(
                    entity_type="user",
                    entity_id=str(current_user.public_id),
                    days=7
                )
                return {'audit_summary': timeline[:5]}
            except Exception as e:
                db.session.rollback()
                logger.warning(f"Audit summary injection error: {e}")
                return {'audit_summary': []}
        return {'audit_summary': []}

    @login_manager.user_loader
    def load_user(public_id):
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

    @app.after_request
    def apply_security_headers(response):
        csp = "default-src 'self'; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; img-src 'self' data: *; font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self';"
        response.headers["Content-Security-Policy"] = csp
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if session.get("user_id"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        return response

    with app.app_context():
        # Validate Dual ID System
        from sqlalchemy import inspect
        try:
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('users')]
            if 'id' in columns and 'user_id' in columns:
                logger.info("✅ Dual ID system validated.")
        except:
            pass




    #===================================================
    #Whre am i
    #===================================
    @app.route('/where-am-i')
    def where_am_i():
        from flask import current_app
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

    # ── Regenerate theme CSS on startup ──────────────────────────────
    with app.app_context():
        try:
            from app.tools.theme_service import ThemeService
            ThemeService.update_global_theme_css()
        except Exception as e:
            logger.warning(f"Could not regenerate global theme CSS on startup: {e}")

    logger.info(f"✅ App factory completed in {time.time() - start_time:.2f} seconds")
    return app
