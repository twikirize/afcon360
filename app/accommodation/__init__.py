# app/accommodation/__init__.py
"""
Accommodation Module for AFCON360
"""

from flask import Blueprint, current_app, abort, redirect, url_for
from functools import wraps
from flask_login import login_required, current_user

# Create blueprint
accommodation_bp = Blueprint('accommodation', __name__, url_prefix='/accommodation')

# FIX 1: Was url_for("accommodation_guest.search") — blueprint is registered as a
# nested child so the full endpoint is "accommodation.accommodation_guest.search".
# FIX 2: Removed the duplicate `/` route (`legacy_home`) defined further below —
# Flask cannot have two routes with the same path on the same blueprint.
@accommodation_bp.route("/")
def index():
    return redirect(url_for("accommodation.accommodation_guest.search"))


def module_enabled(f):
    """Decorator to check if accommodation module is enabled."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        module_config = current_app.config.get('FEATURE_FLAGS', {}).get('accommodation', {})
        if not module_config.get('enabled', False):
            abort(404, description="Accommodation module is currently disabled")
        return f(*args, **kwargs)
    return decorated_function


def require_accommodation_permission(permission):
    """Decorator for permission checks within accommodation module."""
    def decorator(f):
        @wraps(f)
        @module_enabled
        @login_required
        def decorated_function(*args, **kwargs):
            from app.auth.policy import can
            if not can(current_user, permission):
                abort(403, description=f"Insufficient permissions: {permission} required")
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Import routes
from app.accommodation.routes import guest, host, admin

# Register sub-blueprints
accommodation_bp.register_blueprint(guest, url_prefix='/guest')
accommodation_bp.register_blueprint(host, url_prefix='/host')
accommodation_bp.register_blueprint(admin, url_prefix='/admin')


# FIX 3: Legacy detail route also had wrong endpoint name.
# Was 'accommodation.guest.detail' — correct is 'accommodation.accommodation_guest.detail'
@accommodation_bp.route("/<identifier>", endpoint="legacy_detail")
@module_enabled
def legacy_detail(identifier):
    """Legacy route - redirects to new detail"""
    return redirect(url_for('accommodation.accommodation_guest.detail', identifier=identifier))


__all__ = ['accommodation_bp', 'module_enabled', 'require_accommodation_permission']