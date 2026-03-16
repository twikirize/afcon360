# app/__init__.py
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

import logging

# -------------------------------
# Logging
# -------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("app")

# -------------------------------
# Redis helper
# -------------------------------
def require_redis(url: str, purpose: str) -> redis.Redis:
    """
    Helper to enforce Redis availability.
    - url: Redis connection string
    - purpose: human-readable purpose (e.g. 'sessions', 'rate limiting')
    Returns a connected Redis client or raises RuntimeError with traceable details.
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

# -------------------------------
# Application Factory
# -------------------------------
def create_app(config_object=None) -> Flask:
    """
    Application factory for AFCON360.
    Enforces Redis for sessions and rate limiting.
    Fails fast with traceable errors if Redis is unavailable.
    """

    # -------------------------------
    # Paths for templates and static files
    # -------------------------------
    base_dir = os.path.abspath(os.path.dirname(__file__))
    template_path = os.path.join(base_dir, "..", "templates")
    project_root = os.path.abspath(os.path.join(base_dir, ".."))
    static_path = os.path.join(project_root, "static")

    # -------------------------------
    # Load environment variables
    # -------------------------------
    load_dotenv()

    # -------------------------------
    # Create Flask app instance
    # -------------------------------
    app = Flask(__name__, static_folder=static_path, template_folder=template_path)

    # -------------------------------
    # app/__init__.py - add this after creating the app
    # -------------------------------

    @app.after_request
    def remove_csp(response):
        """Remove CSP header for development"""
        response.headers.pop('Content-Security-Policy', None)
        response.headers.pop('X-Content-Security-Policy', None)  # Some browsers use this
        return response

    app.config.from_object(config_object or Config)
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY")

    # -------------------------------
    # Database (always use DATABASE_URL from env)
    # -------------------------------
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # -------------------------------
    # Sessions (Redis enforced)
    # -------------------------------
    redis_client = require_redis(app.config["REDIS_URL"], "sessions")
    app.config["SESSION_TYPE"] = "redis"
    app.config["SESSION_REDIS"] = redis_client
    Session(app)
    cache.init_app(app)

    # -------------------------------
    # Rate limiting (Redis enforced)
    # -------------------------------
    require_redis(app.config["RATELIMIT_STORAGE_URL"], "rate limiting")
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=app.config["RATELIMIT_STORAGE_URL"],
        default_limits=[app.config["RATELIMIT_DEFAULT"]],
    )
    limiter.init_app(app)

    # -------------------------------
    # Initialize core extensions
    # -------------------------------
    db.init_app(app)             # SQLAlchemy
    migrate.init_app(app, db)    # Alembic migrations
    login_manager.init_app(app)  # Flask-Login
    csrf.init_app(app)           # CSRF protection

    # -------------------------------
    # Security cookie flags
    # -------------------------------
    app.config.setdefault("SESSION_COOKIE_SECURE", True)
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    # -------------------------------
    # Import models so Alembic sees them
    # -------------------------------
    from app.identity import models as identity_models
    from app.profile import models as profile_models
    from app.kyc import models as kyc_models
    from app.audit import models as audit_models
    from app.auth import roles as role_models  # keep if you need role constants

    # -------------------------------
    # Import blueprints
    # -------------------------------
    from app.auth.routes import auth_routes as auth_bp
    from app.fan.routes import fan_routes as fan_bp
    from app.wallet.routes import wallet_routes as wallet_bp
    from app.tournament import tournament_bp
    from app.tourism import tourism_bp
    from app.transport import transport_bp, transport_admin_bp
    from app.accommodation import accommodation_bp
    from app.admin import admin_bp

    # Register core blueprints
    for bp in [admin_bp, auth_bp, fan_bp, wallet_bp]:
        app.register_blueprint(bp)

    # Conditional module registration
    if app.config.get("TOURNAMENT_ENABLED", True):
        app.register_blueprint(tournament_bp)

    if app.config.get("TOURISM_ENABLED", True):
        app.register_blueprint(tourism_bp)

        # In app/__init__.py — replace your transport registration block with this:
        #
        # Find this section in your create_app() function and replace it entirely.
        # Everything else in create_app() stays the same.

    if app.config.get("TRANSPORT_ENABLED", True):
        from app.transport import transport_bp, transport_admin_bp, init_transport_module

        # Initialize module first (attaches routes + API resources)
        init_transport_module(app)

        # Register blueprints WITH CORRECT URL PREFIXES
        app.register_blueprint(transport_bp, url_prefix='/transport')
        app.register_blueprint(transport_admin_bp, url_prefix='/transport/admin')

        # DEBUG: Print all registered routes
        print("\n" + "=" * 50)
        print("REGISTERED TRANSPORT ROUTES:")
        print("=" * 50)
        for rule in app.url_map.iter_rules():
            if 'transport' in str(rule):
                print(f"{rule.endpoint}: {rule}")
        print("=" * 50 + "\n")

        logger.info("Transport blueprint registered with prefixes")

    if app.config.get("ACCOMMODATION_ENABLED", True):
        app.register_blueprint(accommodation_bp)

    # -------------------------------
    # Context processors
    # -------------------------------
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
        """Inject dynamic navigation links with fallback URLs."""

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

    # -------------------------------
    # Login manager user loader
    # -------------------------------
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by UUID for Flask-Login."""
        return User.query.filter_by(user_id=user_id).first()

    # -------------------------------
    # Routes
    # -------------------------------
    @app.route("/")
    def index():
        """Public home page."""
        return render_template("public_home.html")

    @app.route("/fan/profile")
    def fan_profile():
        """Legacy fan profile route. Redirects unauthenticated users to home."""
        if "user_id" not in session:
            return redirect(url_for("index"))
        return render_template("fan_profile.html")

    # ----------------------------
    # Global CSRF error handler
    # ---------------------------
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        """Handle CSRF failures globally."""
        if request.is_json:  # JSON API requests
            return jsonify({"status":"error","message":"CSRF token missing"}), 400
        flash("Your session expired. Please refresh the page and try again.", "warning")
        return redirect(url_for("auth_routes.register"))

    # -------------------------------
    # Global security headers
    # -------------------------------
    @app.after_request
    def set_global_security_headers(response):
        """Apply security headers to all responses."""
        response.headers["Content-Security-Policy"] = "default-src 'self';"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    # -------------------------------
    # Prometheus metrics endpoint
    # -------------------------------
    from prometheus_client import generate_latest
    @app.route("/metrics")
    def metrics():
        """Expose Prometheus metrics for monitoring."""
        return Response(generate_latest(), mimetype="text/plain; charset=utf-8")

    return app
