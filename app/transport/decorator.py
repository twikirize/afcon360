# app/transport/decorator.py
"""
Transport-specific decorators
"""
from functools import wraps
from flask import abort, redirect, url_for, flash, current_app
from flask_login import current_user

# -------------------------------
# Transport module decorator
# -------------------------------
def module_enabled_required(module_name):
    """
    Decorator to check if a module is enabled.
    Usage: @module_enabled_required("transport")
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Access config safely inside the request context
            # This runs when the route is actually called, not at import time
            module_flags = current_app.config.get("MODULE_FLAGS", {})

            if not module_flags.get(module_name, False):
                if current_user.is_authenticated:
                    if hasattr(current_user, 'has_global_role') and current_user.has_global_role('admin'):
                        flash(
                            f'{module_name.title()} module is disabled. '
                            f'Enable it from admin dashboard or set ENABLE_{module_name.upper()}=true in .env',
                            'warning'
                        )
                        return redirect(url_for('admin.super_dashboard'))
                    else:
                        flash(f'{module_name.title()} services are currently unavailable.', 'info')
                        return redirect(url_for('index'))
                else:
                    abort(404)

            return f(*args, **kwargs)

        return decorated_function

    return decorator

# Alias for routes.py
#module_enabled_required = transport_enabled_required

# -------------------------------
# Role decorator (example)
# -------------------------------
def role_required(role_name):
    """
    Simple role check for transport routes.
    Replace with your actual role system.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or role_name not in getattr(current_user, 'roles', []):
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for("transport.home"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# -------------------------------
# Rate limit decorator (example)
# -------------------------------
def rate_limit(key, per_minute=5):
    """
    Example rate limiter for transport routes.
    Connects to Flask-Limiter or custom logic.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Add real rate limit logic here if needed
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# -------------------------------
# Feature decorator
# -------------------------------
def transport_feature_enabled(feature_name):
    """
    Decorator factory for transport feature flags
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            module_flags = current_app.config.get("MODULE_FLAGS", {})
            if not module_flags.get("transport", False):
                if current_user.is_authenticated:
                    flash('Transport module is disabled.', 'info')
                    return redirect(url_for('index'))
                else:
                    abort(404)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
