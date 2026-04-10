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
from datetime import datetime

# Import Redis conditionally
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False
    logging.warning("Redis not available - some features may be limited")
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
from dotenv import load_dotenv
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

    # Ensure environment is loaded
    load_dotenv()

    app = Flask(__name__, static_folder=static_path, template_folder=template_path)

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
            # This is for development convenience only
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
            raise RuntimeError(
                "REDIS_URL must be set in production. "
                "Set REDIS_URL environment variable."
            )
        else:
            # Development fallback
            redis_url = "redis://localhost:6379/0"
            logger.warning("Using development Redis URL. Set REDIS_URL environment variable for production.")

    # Configure extensions with validated Redis URL
    from app.extensions import limiter, cache, redis_client

    # Configure limiter
    limiter.storage_uri = redis_url

    # Configure cache
    cache.config.update({
        "CACHE_TYPE": "RedisCache",
        "CACHE_REDIS_URL": redis_url,
        "CACHE_DEFAULT_TIMEOUT": 300
    })

    # Configure Redis client
    redis_client.configure(redis_url)

    # Get Redis client for sessions
    redis_session_client = None
    try:
        # First try to use the configured redis_client
        redis_session_client = redis_client.client
        # Test the connection
        redis_session_client.ping()
        logger.info(f"Redis session client connected successfully")
    except Exception as e:
        logger.error(f"Failed to get Redis client: {e}")
        redis_session_client = None

    # Use require_redis for session client
    if redis_session_client:
        try:
            redis_session_client = require_redis(redis_url, "sessions", existing_client=redis_session_client)
        except Exception as e:
            logger.error(f"require_redis failed with existing client: {e}")
            redis_session_client = require_redis(redis_url, "sessions")
    else:
        redis_session_client = require_redis(redis_url, "sessions")

    if REDIS_AVAILABLE and redis_session_client and FLASK_SESSION_AVAILABLE:
        app.config["SESSION_TYPE"] = "redis"
        app.config["SESSION_REDIS"] = redis_session_client
        Session(app)
    elif FLASK_SESSION_AVAILABLE:
        # Fallback to filesystem sessions
        app.config["SESSION_TYPE"] = "filesystem"
        Session(app)
        logging.warning("Using filesystem sessions - Redis not available")
    else:
        logging.error("No session backend available")

    # Init cache
    if REDIS_AVAILABLE:
        cache.init_app(app, config={"CACHE_TYPE": "RedisCache", "CACHE_REDIS_URL": redis_url})
    else:
        cache.init_app(app, config={"CACHE_TYPE": "SimpleCache"})

    # Rate limiting
    if REDIS_AVAILABLE:
        rate_limit_url = app.config.get("RATELIMIT_STORAGE_URL", redis_url)
        existing_client = redis_session_client if rate_limit_url == redis_url else None
        require_redis(rate_limit_url, "rate limiting", existing_client=existing_client)
        limiter.init_app(app)
        limiter.storage_uri = rate_limit_url
    else:
        limiter.init_app(app)
        logging.warning("Rate limiting disabled - Redis not available")

    # Database and base extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Updated login_view to reflect new blueprint name
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Your session has expired. Please log in again.'
    login_manager.login_message_category = 'warning'

    # Ensure secure cookie defaults
    app.config.setdefault("SESSION_COOKIE_SECURE", True)
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    # ------------------------------------------------------------------
    # Database Transaction Lifecycle
    # ------------------------------------------------------------------
    @app.before_request
    def ensure_clean_transaction():
        """
        Ensure a completely clean transaction before every request.
        session.remove() returns the connection to the pool, guaranteeing
        no leftover failed transaction state from a previous request.
        """
        try:
            db.session.remove()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass

    @app.teardown_request
    def handle_transaction(exception=None):
        """Always return session to pool at end of request."""
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
    try:
        from app.kyc import models as kyc_models
    except ImportError as e:
        logger.warning(f"KYC models not available: {e}")
        kyc_models = None

    from app.audit import models as audit_models
    from app.auth import roles as role_models

    # Updated blueprint imports to reflect new names
    from app.auth.routes import auth_bp
    from app.fan.routes import fan_bp
    from app.wallet.routes import wallet_bp # This will be updated next
    from app.tournament import tournament_bp
    from app.tourism import tourism_bp
    from app.transport import transport_bp, transport_admin_bp
    from app.accommodation import accommodation_bp
    from app.admin import admin_bp # admin_bp now includes owner_bp
    from app.events import events_bp
    from app.tools.theme_routes import theme_bp

    from app.wallet.api.wallet_api import wallet_api_bp
    from app.wallet.api.admin_api import admin_wallet_bp
    from app.wallet.api.audit_api import audit_bp
    from app.wallet.api.webhook_api import webhook_bp

    # Register core blueprints - owner_bp is now registered via admin_bp
    # Check each blueprint exists before registering
    blueprints_to_register = []

    # Check each blueprint variable exists
    if 'admin_bp' in locals():
        blueprints_to_register.append(admin_bp)
    if 'auth_bp' in locals():
        blueprints_to_register.append(auth_bp)
    if 'fan_bp' in locals():
        blueprints_to_register.append(fan_bp)
    if 'wallet_bp' in locals():
        blueprints_to_register.append(wallet_bp)
    if 'events_bp' in locals():
        blueprints_to_register.append(events_bp)
    if 'theme_bp' in locals():
        blueprints_to_register.append(theme_bp)

    for bp in blueprints_to_register:
        app.register_blueprint(bp)

    # Register wallet API blueprints
    app.register_blueprint(wallet_api_bp)  # /api/wallet/*
    app.register_blueprint(admin_wallet_bp)  # /api/admin/wallet/*
    app.register_blueprint(audit_bp)  # /api/admin/audit/*
    app.register_blueprint(webhook_bp)  # /api/webhooks/*

    # ------------------------------------------------------------------
    # Module registrations with feature flags
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # CLI Commands
    # ------------------------------------------------------------------
    from app.cli.owner import register_owner_commands
    register_owner_commands(app)

    try:
        from app.auth.seed import register_commands as register_seed_commands
        register_seed_commands(app)
    except ImportError:
        pass

    # Register new CLI commands
    try:
        from app.cli import register_all_cli_commands
        register_all_cli_commands(app)
    except ImportError:
        pass

    # Register ultimate admin routes
    try:
        from app.admin.routes_ultimate import register_admin_routes
        register_admin_routes(app)
    except ImportError:
        pass

    # Register extended admin routes
    try:
        from app.admin.routes_extended import admin_extended_bp
        app.register_blueprint(admin_extended_bp)
    except ImportError:
        pass

    # ------------------------------------------------------------------
    # Context processors
    # ------------------------------------------------------------------
    @app.context_processor
    def inject_impersonation_status():
        """Inject impersonation status into all templates."""
        from flask import session

        is_impersonating = bool(session.get('impersonated_by') or session.get('owner_impersonating'))
        impersonated_role = session.get('impersonated_role')
        impersonated_by = session.get('impersonated_by_name')

        return {
            'is_impersonating': is_impersonating,
            'impersonated_role': impersonated_role,
            'impersonated_by': impersonated_by
        }

    @app.context_processor
    def inject_user_role_info():
        """Inject user's highest role into all templates."""
        from flask_login import current_user
        from flask import url_for
        from app.auth.decorators import get_highest_role
        from app.auth.routes import _dashboard_for_user # This import is fine, function is internal

        def user_highest_role():
            if current_user and current_user.is_authenticated:
                return get_highest_role(current_user)
            return None

        def user_dashboard_url():
            if current_user and current_user.is_authenticated:
                return _dashboard_for_user(current_user)
            return url_for('index')

        return {
            'user_highest_role': user_highest_role(),
            'user_dashboard_url': user_dashboard_url()
        }

    @app.context_processor
    def inject_sitewide() -> Dict:
        return {
            "app_name": current_app.config.get("APP_NAME", "AFCON 360"),
            "tournament_name": current_app.config.get("TOURNAMENT_NAME", "AFCON Tournament"),
            "year": current_app.config.get("YEAR", 2025),
        }

    @app.context_processor
    def inject_links() -> Dict:
        def resolve_endpoint(candidates: List[str], default: str = "#") -> str:
            for ep in candidates:
                try:
                    return url_for(ep)
                except Exception:
                    continue
            return default

        modules = {
            # Updated endpoint names
            "wallet_home": ["wallet.wallet_home"],
            "wallet_dashboard": ["wallet.wallet_dashboard"],
            "tournament_home": ["tournament.home", "tournament.index"],
            "matches_index": ["matches.index", "tournament.home", "index"],
            "tourism_home": ["tourism.home", "tourism.index"],
            "transport_home": ["transport.home", "transport.index"],
            "accommodation_home": ["accommodation.index"],
            "auth_login": ["auth.login"],
            "auth_register": ["auth.register"],
            "index": ["index"],
        }
        links = {
            key: resolve_endpoint(endpoints, default=f"/{key.replace('_', '/')}")
            for key, endpoints in modules.items()
        }
        return {"links": links, **inject_sitewide()}

    @app.context_processor
    def inject_wallet_status() -> Dict:
        user_has_wallet = False
        if session.get('user_id'):
            try:
                from app.wallet.repositories.wallet_repository import WalletRepository
                repo = WalletRepository()
                wallet = repo.get_by_user_id(session.get('user_id'))
                user_has_wallet = wallet is not None
            except Exception:
                pass
        return {'user_has_wallet': user_has_wallet}

    # ------------------------------------------------------------------
    # Login manager
    # ------------------------------------------------------------------
    @login_manager.user_loader
    def load_user(user_id):
        from app.identity.models.user import User
        try:
            # Ensure clean session state before loading user
            # This prevents InFailedSqlTransaction errors in RBAC checks
            db.session.rollback()
            # Dual ID System: user_id for login_manager is the external UUID (String)
            return User.query.filter_by(user_id=user_id).first()
        except Exception as e:
            logger.warning(f"user_loader failed for {user_id}: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass
            return None

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    from app.events.services import EventService

    @app.route('/')
    def index():
        featured_event = EventService.get_featured_event()
        other_events = EventService.get_upcoming_events(limit=2, exclude_featured=True)
        return render_template('public_home.html', featured_event=featured_event, other_events=other_events)

    @app.route("/api/wallet/status", methods=["GET"])
    def wallet_module_status():
        from app.wallet.middleware.kill_switch import wallet_enabled
        return jsonify({
            "status": "success",
            "wallet_enabled": wallet_enabled(),
            "module": "wallet",
            "timestamp": datetime.utcnow().isoformat()
        })

    # ------------------------------------------------------------------
    # Error Handlers
    # ------------------------------------------------------------------
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.is_json:
            return jsonify({"status": "error", "message": "CSRF token missing or invalid"}), 400
        session.clear()
        flash("Your session has expired. Please log in again to continue.", "warning")
        return redirect(url_for("auth.login"))

    # ------------------------------------------------------------------
    # SECURITY HEADERS
    # ------------------------------------------------------------------
    @app.after_request
    def apply_security_headers(response):
        env = app.config.get("FLASK_ENV", "production")
        # Update CSP to allow data: images and unsafe-inline for theme system
        csp = "default-src 'self'; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; img-src 'self' data: *; font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self';"
        response.headers["Content-Security-Policy"] = csp
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if session.get("user_id"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # ------------------------------------------------------------------
    # Dual ID System Validation
    # ------------------------------------------------------------------
    def validate_id_system():
        """Validate that the dual ID system is working correctly"""
        from app.identity.models.user import User
        from sqlalchemy import inspect

        try:
            inspector = inspect(db.engine)
            # Check users table has both id and user_id (the external UUID)
            columns = [col['name'] for col in inspector.get_columns('users')]
            if 'id' not in columns or 'user_id' not in columns:
                logger.error("Users table missing required id or user_id columns")
                return

            logger.info("✅ Dual ID system validated: Internal IDs (BIGINT) and External UUIDs")
        except Exception as e:
            logger.warning(f"Could not validate ID system on startup: {e}")

    # Call this after app context is ready
    with app.app_context():
        validate_id_system()

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    try:
        from prometheus_client import generate_latest
        @app.route("/metrics")
        def metrics():
            return Response(generate_latest(), mimetype="text/plain; charset=utf-8")
    except ImportError:
        pass

    logger.info(f"✅ App factory completed in {time.time() - start_time:.2f} seconds")
    return app
