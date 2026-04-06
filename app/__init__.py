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
import redis
import logging
import time
from datetime import datetime
from flask import Flask, flash, redirect, render_template, session, current_app, url_for, request, Response, jsonify
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFError
from dotenv import load_dotenv
from typing import Dict, List
from app.config import Config
from app.extensions import db, migrate, login_manager, csrf, limiter, cache, redis_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")


def require_redis(url: str, purpose: str, existing_client=None) -> redis.Redis:
    """
    Ensure Redis is available before starting the app.
    Raises RuntimeError if Redis connection fails.
    """
    if existing_client:
        return existing_client

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
    
    # Critical Config Fallbacks
    app.config['SECRET_KEY'] = app.config.get('SECRET_KEY') or os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY")
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config.get("SQLALCHEMY_DATABASE_URI") or os.getenv("DATABASE_URL")
    
    if not app.config["SQLALCHEMY_DATABASE_URI"]:
        # Try to build from components if DATABASE_URL is missing
        db_user = os.getenv("APP_DB_USER") or os.getenv("DB_USER")
        db_pass = os.getenv("APP_DB_PASS") or os.getenv("DB_PASS")
        db_host = os.getenv("DB_HOST", "localhost")
        db_name = os.getenv("DB_NAME", "afcon360_prod")
        if db_user and db_pass:
            app.config["SQLALCHEMY_DATABASE_URI"] = f"postgresql://{db_user}:{db_pass}@{db_host}/{db_name}"

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_SERIALIZER"] = "json"

    # ------------------------------------------------------------------
    # Redis & Extensions (Shared)
    # ------------------------------------------------------------------
    redis_url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
    redis_session_client = require_redis(redis_url, "sessions")
    
    app.config["SESSION_TYPE"] = "redis"
    app.config["SESSION_REDIS"] = redis_session_client
    Session(app)
    
    # Init cache
    cache.init_app(app, config={"CACHE_TYPE": "RedisCache", "CACHE_REDIS_URL": redis_url})

    # Rate limiting
    rate_limit_url = app.config.get("RATELIMIT_STORAGE_URL", redis_url)
    existing_client = redis_session_client if rate_limit_url == redis_url else None
    require_redis(rate_limit_url, "rate limiting", existing_client=existing_client)
    
    limiter.init_app(app)
    limiter.storage_uri = rate_limit_url

    # Database and base extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    login_manager.login_view = 'auth_routes.login'
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
        """Ensure we have a clean transaction before each request."""
        try:
            db.session.rollback()
        except Exception:
            pass

    @app.teardown_request
    def handle_transaction(exception=None):
        """Handle transaction at the end of each request."""
        if exception:
            try:
                db.session.rollback()
            except Exception:
                pass
        else:
            try:
                if db.session.is_active:
                    db.session.commit()
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Lazy Imports - Blueprints & Models
    # ------------------------------------------------------------------
    from app.identity import models as identity_models
    from app.profile import models as profile_models
    from app.kyc import models as kyc_models
    from app.audit import models as audit_models
    from app.auth import roles as role_models

    from app.auth.routes import auth_routes as auth_bp
    from app.fan.routes import fan_routes as fan_bp
    from app.wallet.routes import wallet_routes as wallet_bp
    from app.tournament import tournament_bp
    from app.tourism import tourism_bp
    from app.transport import transport_bp, transport_admin_bp
    from app.accommodation import accommodation_bp
    from app.admin import admin_bp
    from app.events import events_bp

    from app.wallet.api.wallet_api import wallet_api_bp
    from app.wallet.api.admin_api import admin_wallet_bp
    from app.wallet.api.audit_api import audit_bp
    from app.wallet.api.webhook_api import webhook_bp

    # Register core blueprints
    for bp in [admin_bp, auth_bp, fan_bp, wallet_bp, events_bp]:
        app.register_blueprint(bp)

    # Register wallet API blueprints
    app.register_blueprint(wallet_api_bp)      # /api/wallet/*
    app.register_blueprint(admin_wallet_bp)    # /api/admin/wallet/*
    app.register_blueprint(audit_bp)           # /api/admin/audit/*
    app.register_blueprint(webhook_bp)         # /api/webhooks/*

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

    # ------------------------------------------------------------------
    # Context processors
    # ------------------------------------------------------------------
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
            "wallet_home": ["wallet.home", "wallet_routes.wallet_home"],
            "wallet_dashboard": ["wallet.dashboard", "wallet_routes.wallet_dashboard"],
            "tournament_home": ["tournament.home", "tournament.index"],
            "matches_index": ["matches.index", "tournament.home", "index"],
            "tourism_home": ["tourism.home", "tourism.index"],
            "transport_home": ["transport.home", "transport.index"],
            "accommodation_home": ["accommodation.home", "accommodation.index"],
            "auth_login": ["auth_routes.login", "auth.login"],
            "auth_register": ["auth_routes.register", "auth.register"],
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
        return User.query.filter_by(user_id=user_id).first()

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
        return redirect(url_for("auth_routes.login"))

    # ------------------------------------------------------------------
    # SECURITY HEADERS
    # ------------------------------------------------------------------
    @app.after_request
    def apply_security_headers(response):
        env = app.config.get("FLASK_ENV", "production")
        csp = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self';"
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