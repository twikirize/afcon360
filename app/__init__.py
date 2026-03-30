# app/__init__.py
"""
# Changes vs original:
#   [P0] REMOVED remove_csp() — it was stripping CSP in production due to
#        Flask's LIFO after_request execution order (registered first = runs last)
#   [P0] Consolidated security headers into single after_request handler
#   [P1] SESSION_SERIALIZER changed to json (pickle = RCE risk)
#   All module registration, Redis enforcement, blueprints: UNCHANGED
# ============================================================================
"""

import os
import redis
import logging
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
from app.identity.models.user import User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")


def require_redis(url: str, purpose: str) -> redis.Redis:
    """
    Ensure Redis is available before starting the app.
    Raises RuntimeError if Redis connection fails.
    """
    try:
        client = redis.Redis.from_url(url, decode_responses=False, socket_connect_timeout=5)
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

    Security features:
        - Redis-backed sessions (server-side, not client cookies)
        - CSRF protection via Flask-WTF
        - Rate limiting with Redis storage
        - Security headers (CSP, HSTS, etc.)
        - No pickle serialization (JSON only)
    """
    base_dir = os.path.abspath(os.path.dirname(__file__))
    template_path = os.path.join(base_dir, "..", "templates")
    project_root = os.path.abspath(os.path.join(base_dir, ".."))
    static_path = os.path.join(project_root, "static")

    load_dotenv()

    app = Flask(__name__, static_folder=static_path, template_folder=template_path)
    app.config.from_object(config_object or Config)
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY")

    # SECURITY FIX: Explicitly set JSON serializer — pickle allows RCE
    app.config["SESSION_SERIALIZER"] = "json"

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ------------------------------------------------------------------
    # Sessions (Redis enforced)
    # ------------------------------------------------------------------
    redis_session_client = require_redis(app.config["REDIS_URL"], "sessions")
    app.config["SESSION_TYPE"] = "redis"
    app.config["SESSION_REDIS"] = redis_session_client
    Session(app)
    cache.init_app(app)

    # ------------------------------------------------------------------
    # Rate limiting (Redis enforced)
    # ------------------------------------------------------------------
    require_redis(app.config["RATELIMIT_STORAGE_URL"], "rate limiting")
    limiter_instance = Limiter(
        key_func=get_remote_address,
        storage_uri=app.config["RATELIMIT_STORAGE_URL"],
        default_limits=[app.config["RATELIMIT_DEFAULT"]],
    )
    limiter_instance.init_app(app)

    # ------------------------------------------------------------------
    # Database and extensions
    # ------------------------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Ensure secure cookie defaults
    app.config.setdefault("SESSION_COOKIE_SECURE", True)
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    # ------------------------------------------------------------------
    # Import models so Alembic sees them
    # ------------------------------------------------------------------
    from app.identity import models as identity_models
    from app.profile import models as profile_models
    from app.kyc import models as kyc_models
    from app.audit import models as audit_models
    from app.auth import roles as role_models

    # ------------------------------------------------------------------
    # Blueprints
    # ------------------------------------------------------------------
    from app.auth.routes import auth_routes as auth_bp
    from app.fan.routes import fan_routes as fan_bp
    from app.wallet.routes import wallet_routes as wallet_bp
    from app.tournament import tournament_bp
    from app.tourism import tourism_bp
    from app.transport import transport_bp, transport_admin_bp
    from app.accommodation import accommodation_bp
    from app.admin import admin_bp

    for bp in [admin_bp, auth_bp, fan_bp, wallet_bp]:
        app.register_blueprint(bp)

    if app.config.get("TOURNAMENT_ENABLED", True):
        app.register_blueprint(tournament_bp)

    if app.config.get("TOURISM_ENABLED", True):
        app.register_blueprint(tourism_bp)

    if app.config.get("TRANSPORT_ENABLED", True):
        from app.transport import transport_bp, transport_admin_bp, init_transport_module
        init_transport_module(app)
        app.register_blueprint(transport_bp, url_prefix='/transport')
        app.register_blueprint(transport_admin_bp, url_prefix='/transport/admin')
        logger.info("Transport blueprint registered")

    if app.config.get("ACCOMMODATION_ENABLED", True):
        app.register_blueprint(accommodation_bp)

    from app.cli.owner import register_owner_commands
    register_owner_commands(app)

    # ------------------------------------------------------------------
    # Context processors
    # ------------------------------------------------------------------
    @app.context_processor
    def inject_sitewide() -> Dict:
        """Inject site-wide variables into all templates."""
        return {
            "app_name": current_app.config.get("APP_NAME", "AFCON 360"),
            "tournament_name": current_app.config.get("TOURNAMENT_NAME", "AFCON Tournament"),
            "year": current_app.config.get("YEAR", 2025),
        }

    @app.context_processor
    def inject_links() -> Dict:
        """
        Inject URL links into all templates.
        Resolves endpoint names to URLs with fallbacks.
        """

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
            "auth_login": ["auth.login", "auth_routes.login"],
            "auth_register": ["auth.register", "auth_routes.register"],
            "index": ["index"],
        }
        links = {
            key: resolve_endpoint(endpoints, default=f"/{key.replace('_', '/')}")
            for key, endpoints in modules.items()
        }
        return {"links": links, **inject_sitewide()}

    # ------------------------------------------------------------------
    # Login manager
    # ------------------------------------------------------------------
    @login_manager.user_loader
    def load_user(user_id):
        """Load user from database by ID for Flask-Login."""
        return User.query.filter_by(user_id=user_id).first()

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    from app.accommodation.services.events_service import EventService

    @app.route('/')
    def index():
        """Public home page with featured and upcoming events."""
        featured_event = EventService.get_featured_event()
        other_events = EventService.get_upcoming_events(limit=2, exclude_featured=True)
        return render_template(
            'public_home.html',
            featured_event=featured_event,
            other_events=other_events,
        )

    @app.route("/fan/profile")
    def fan_profile():
        """Fan profile page — requires authentication."""
        if "user_id" not in session:
            return redirect(url_for("index"))
        return render_template("fan_profile.html")

    # ------------------------------------------------------------------
    # CSRF error handler
    # ------------------------------------------------------------------
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        """Handle CSRF token validation failures."""
        if request.is_json:
            return jsonify({"status": "error", "message": "CSRF token missing or invalid"}), 400
        flash("Your session expired. Please refresh the page and try again.", "warning")
        return redirect(url_for("auth_routes.register"))

    # ------------------------------------------------------------------
    # SECURITY HEADERS — ONE consolidated handler
    #
    # SECURITY FIX: Removed remove_csp() which was stripping CSP headers.
    # Flask registers after_request handlers in LIFO order. Previously:
    #   1. remove_csp() registered first → ran LAST (stripped CSP)
    #   2. set_global_security_headers() registered last → ran FIRST (added CSP)
    # Net result: NO CSP in production.
    #
    # Now: single handler, no conflicts, no stripping.
    # ------------------------------------------------------------------
    @app.after_request
    def apply_security_headers(response):
        """
        Apply security headers to every response.
        - Content Security Policy (CSP) prevents XSS
        - HSTS enforces HTTPS
        - Various headers prevent clickjacking, MIME sniffing, etc.
        """
        env = app.config.get("FLASK_ENV", "production")

        # ------------------------------------------------------------------
        # Content Security Policy
        # ------------------------------------------------------------------
        if env == "development":
            # Relaxed CSP for dev: allow inline styles (useful for dev tools)
            # TODO: Consider removing unsafe-inline when moving to production
            csp = (
                "default-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "base-uri 'self';"
            )
        else:
            # Production: strict CSP — no unsafe-inline
            # Future enhancement: add nonce-based CSP for script/style tags
            csp = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "base-uri 'self';"
            )
        response.headers["Content-Security-Policy"] = csp

        # ------------------------------------------------------------------
        # HSTS — only set over HTTPS
        # ------------------------------------------------------------------
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        # ------------------------------------------------------------------
        # Standard hardening headers
        # ------------------------------------------------------------------
        response.headers["X-Content-Type-Options"] = "nosniff"  # Prevent MIME sniffing
        response.headers["X-Frame-Options"] = "DENY"  # Prevent clickjacking
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"  # Disable sensitive APIs
        )

        # ------------------------------------------------------------------
        # Cache control — never cache authenticated responses
        # ------------------------------------------------------------------
        if session.get("user_id"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        # ------------------------------------------------------------------
        # Remove server fingerprinting headers
        # ------------------------------------------------------------------
        response.headers.pop("Server", None)  # Remove server version
        response.headers.pop("X-Powered-By", None)  # Remove tech stack info

        return response

    # ------------------------------------------------------------------
    # Metrics endpoint (Prometheus)
    # ------------------------------------------------------------------
    from prometheus_client import generate_latest

    @app.route("/metrics")
    def metrics():
        """Prometheus metrics endpoint for monitoring."""
        return Response(generate_latest(), mimetype="text/plain; charset=utf-8")

    return app