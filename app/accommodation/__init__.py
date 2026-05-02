# app/accommodation/__init__.py
"""
Accommodation Module for AFCON360
"""

from flask import Blueprint, current_app, abort, redirect, url_for
from functools import wraps
from flask_login import login_required, current_user

# Create main blueprint
accommodation_bp = Blueprint('accommodation', __name__, url_prefix='/accommodation')


# ==============================
# FEATURE FLAG CHECK
# ==============================
def module_enabled(f):
    """Check if accommodation module is enabled."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        module_config = current_app.config.get('FEATURE_FLAGS', {}).get('accommodation', {})
        if not module_config.get('enabled', False):
            abort(404, description="Accommodation module is disabled")
        return f(*args, **kwargs)
    return decorated_function


# ==============================
# PERMISSION CHECK
# ==============================
def require_accommodation_permission(permission):
    """Check user permissions inside accommodation module."""
    def decorator(f):
        @wraps(f)
        @module_enabled
        @login_required
        def decorated_function(*args, **kwargs):
            from app.auth.policy import can
            if not can(current_user, permission):
                abort(403, description="You do not have access to this resource")
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ==============================
# IMPORT BLUEPRINTS
# ==============================
from app.accommodation.routes import guest, host, admin

# ==============================
# REGISTER BLUEPRINTS
# ==============================
accommodation_bp.register_blueprint(guest, url_prefix='/guest')
accommodation_bp.register_blueprint(host, url_prefix='/host')
accommodation_bp.register_blueprint(admin, url_prefix='/admin')


# ==============================
# ROUTES
# ==============================
@accommodation_bp.route("/")
@module_enabled
def index():
    return redirect(url_for('accommodation.guest.search'))


@accommodation_bp.route("/<identifier>", endpoint="legacy_detail")
@module_enabled
def legacy_detail(identifier):
    return redirect(
        url_for('accommodation.guest.detail', identifier=identifier)
    )


__all__ = ['accommodation_bp', 'module_enabled', 'require_accommodation_permission']

try:
    from app.admin.moderator.registry import register_module
    from flask import url_for
    register_module('accommodation_property', 'Accommodation Property',
                   review_url_fn=lambda id: url_for('accommodation.admin.moderate_property', id=id),
                   module_name='Accommodation', icon='fa-building')
    register_module('accommodation_booking', 'Accommodation Booking',
                   review_url_fn=lambda id: url_for('accommodation.admin.moderate_booking', id=id),
                   module_name='Accommodation', icon='fa-bed')
    register_module('accommodation_review', 'Accommodation Review',
                   review_url_fn=lambda id: url_for('accommodation.admin.moderate_review', id=id),
                   module_name='Accommodation', icon='fa-star')
except Exception:
    pass
