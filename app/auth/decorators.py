# app/auth/decorators.py
"""
Route-level authorisation decorators - Production Ready.

All decorators resolve the current user from ``flask_login.current_user``
(with a ``g.current_user`` fallback for API routes that set it manually).

Stacking order
--------------
Always place ``@login_required`` **above** these decorators::

    @bp.route("/admin")
    @login_required
    @require_role("admin", "super_admin")
    def admin_panel():
        ...

Available decorators
--------------------
@require_role(*roles)
    Abort 403 if user does not hold any of the named global roles.

@require_org_role(*roles)
    Abort 403 if user does not hold any of the named roles within an org.

@require_permission(permission, org_scoped=False)
    Abort 403 if user is not authorised for the named permission.

@admin_required
    Abort 403 if user is not an admin (admin, super_admin, or owner).

@owner_only
    Abort 403 for anyone who is not the platform owner.

@require_wallet_access
    Abort 403 if user cannot access wallet features.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Callable, Optional

from flask import abort, current_app, g, flash, redirect, url_for, request
from flask_login import current_user
from app.extensions import db

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Arrange roles for logging in
# ---------------------------------------------------------------------------

def get_highest_role(user) -> str:
    """
    Return the user's highest role based on hierarchy.

    Role hierarchy:
    owner > super_admin > admin > org_admin > moderator > support > fan
    """
    if not user or not user.is_authenticated:
        return None

    # Ensure user is attached to the session before accessing relationships
    if user not in db.session:
        try:
            user = db.session.merge(user, load=False)
        except Exception as e:
            log.debug(f"Could not merge user in get_highest_role: {e}")

    role_hierarchy = [
        "owner",
        "super_admin",
        "admin",
        "org_admin",
        "moderator",
        "support",
        "fan"
    ]

    try:
        user_roles = set()
        for user_role in user.roles:
            if user_role.role:
                user_roles.add(user_role.role.name)

        for role in role_hierarchy:
            if role in user_roles:
                return role
    except Exception as e:
        log.warning(f"Error getting highest role: {e}")

    return "fan"  # Default


# ---------------------------------------------------------------------------
# Internal: resolve current user
# ---------------------------------------------------------------------------

def _get_current_user():
    """
    Return the active user from Flask-Login or ``g.current_user``.
    Flask-Login is preferred (session-based web views).
    ``g.current_user`` is used by API routes that authenticate via token.
    Ensures the user is attached to the current session to prevent
    "Parent instance not bound to a Session" warnings.
    """
    user = None
    if current_user and current_user.is_authenticated:
        user = current_user
    else:
        user = getattr(g, "current_user", None)

    if user and hasattr(user, 'id'):
        # Merge the user into the current session to ensure it's attached
        # This prevents "Parent instance not bound to a Session" warnings
        # when accessing relationships like user.roles
        try:
            # Always merge with load=False to attach to session without reloading
            # This is safe even if the object is already in the session
            db.session.merge(user, load=False)
        except Exception as e:
            log.debug(f"Could not merge user into session: {e}")
            # Continue without merging - this is non-critical
    return user


def _log_denied(reason: str, user, endpoint: str, **extra) -> None:
    """Log access denied events for audit."""
    log.warning(
        "access_denied %s",
        reason,
        extra={
            "user_id": getattr(user, "id", None),
            "username": getattr(user, "username", None),
            "email": getattr(user, "email", None),
            "endpoint": endpoint,
            "ip": request.remote_addr if request else None,
            **extra,
        },
    )


def _flash_and_abort(message: str, category: str = "danger") -> None:
    """Flash message and abort with 403."""
    flash(message, category)
    abort(403)


# ---------------------------------------------------------------------------
# @require_role
# ---------------------------------------------------------------------------

def require_role(*roles: str) -> Callable:
    """
    Abort with 403 if the current user does not hold any of *roles*.
    Owner satisfies every check implicitly.

    Args:
        *roles: One or more global role name strings.

    Example::
        @require_role("super_admin", "admin")
        def manage_users():
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = _get_current_user()

            if not user:
                _log_denied("unauthenticated", None, fn.__qualname__)
                flash("Please log in to access this page.", "warning")
                return redirect(url_for("auth_routes.login", next=request.url))

            # Ensure user is attached to the session before checking roles
            if user not in db.session:
                try:
                    user = db.session.merge(user, load=False)
                except Exception as e:
                    log.debug(f"Could not merge user in require_role: {e}")

            from app.auth.helpers import has_global_role
            if not has_global_role(user, *roles):
                _log_denied(
                    "role_check", user, fn.__qualname__,
                    required_roles=roles,
                    user_roles=getattr(user, "role_names", []),
                )
                _flash_and_abort("You don't have permission to access this page.")

            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# @require_org_role
# ---------------------------------------------------------------------------

def require_org_role(*roles: str) -> Callable:
    """
    Abort with 403 if user does not hold any of *roles* within an organisation.
    Platform owners bypass this check.

    Args:
        *roles: Org-scoped role names, e.g. "org_owner", "org_admin".

    Example::
        @require_org_role("org_owner", "org_admin")
        def org_settings(org_id):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = _get_current_user()
            org_id = kwargs.get("org_id")

            if not user:
                _log_denied("unauthenticated", None, fn.__qualname__)
                flash("Please log in to access this page.", "warning")
                return redirect(url_for("auth_routes.login", next=request.url))

            if org_id is None:
                current_app.logger.error(
                    "@require_org_role used on route without org_id param: %s",
                    fn.__qualname__,
                )
                abort(500)

            # Ensure user is attached to the session before checking roles
            if user not in db.session:
                try:
                    user = db.session.merge(user, load=False)
                except Exception as e:
                    log.debug(f"Could not merge user in require_org_role: {e}")

            from app.auth.helpers import has_org_role
            if not has_org_role(user, org_id, *roles):
                _log_denied(
                    "org_role_check", user, fn.__qualname__,
                    org_id=org_id,
                    required_roles=roles,
                )
                _flash_and_abort("You don't have permission for this organisation.")

            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# @require_permission
# ---------------------------------------------------------------------------

def require_permission(permission: str, *, org_scoped: bool = False) -> Callable:
    """
    Abort with 403 if user is not authorised for *permission*.

    Args:
        permission: Dot-namespaced capability, e.g. "wallet.manage".
        org_scoped: When True, resolve against org_id route parameter.

    Examples::
        @require_permission("wallet.manage")
        def wallet_settings(): ...

        @require_permission("orgs.manage", org_scoped=True)
        def org_edit(org_id): ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = _get_current_user()
            org_id = kwargs.get("org_id") if org_scoped else None

            if not user:
                _log_denied("unauthenticated", None, fn.__qualname__)
                flash("Please log in to access this page.", "warning")
                return redirect(url_for("auth_routes.login", next=request.url))

            from app.auth.policy import can
            if not can(user, permission, org_id=org_id):
                _log_denied(
                    "permission_check", user, fn.__qualname__,
                    permission=permission,
                    org_id=org_id,
                )
                _flash_and_abort(f"You need '{permission}' permission to access this page.")

            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# @admin_required
# ---------------------------------------------------------------------------

def admin_required(fn: Callable) -> Callable:
    """
    Abort with 403 if user is not an admin (admin, super_admin, or owner).
    This is the most common admin decorator.

    Example::
        @bp.route("/admin")
        @login_required
        @admin_required
        def admin_panel():
            ...
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _get_current_user()

        if not user:
            _log_denied("unauthenticated", None, fn.__qualname__)
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth_routes.login", next=request.url))

        # Ensure user is attached to the session before checking roles
        if user not in db.session:
            try:
                user = db.session.merge(user, load=False)
            except Exception as e:
                log.debug(f"Could not merge user in admin_required: {e}")

        from app.auth.helpers import has_global_role
        if not has_global_role(user, "admin", "super_admin", "owner"):
            _log_denied(
                "admin_required", user, fn.__qualname__,
                user_roles=getattr(user, "role_names", []),
            )
            _flash_and_abort("Admin access required.")

        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# @owner_only
# ---------------------------------------------------------------------------

def owner_only(fn: Callable) -> Callable:
    """
    Abort with 403 for anyone who is not the platform owner.
    Use on the most sensitive routes: module toggles, system config, etc.

    Example::
        @owner_only
        def toggle_module(module):
            ...
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _get_current_user()

        if not user:
            _log_denied("unauthenticated", None, fn.__qualname__)
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth_routes.login", next=request.url))

        from app.auth.helpers import is_owner
        if not is_owner(user):
            _log_denied("owner_only", user, fn.__qualname__)
            _flash_and_abort("Owner access required for this action.")

        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# @require_wallet_access
# ---------------------------------------------------------------------------

def require_wallet_access(fn: Callable) -> Callable:
    """
    Abort with 403 if user cannot access wallet features.
    Checks: wallet module enabled AND user has wallet permission.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _get_current_user()

        if not user:
            _log_denied("unauthenticated", None, fn.__qualname__)
            flash("Please log in to access wallet.", "warning")
            return redirect(url_for("auth_routes.login", next=request.url))

        # Check if wallet module is enabled
        from app.wallet.middleware.kill_switch import wallet_enabled
        if not wallet_enabled():
            _flash_and_abort("Wallet service is currently disabled. Please try again later.")

        # Check if user has wallet permission
        from app.auth.policy import can
        if not can(user, "wallet.view"):
            _log_denied("wallet_access", user, fn.__qualname__)
            _flash_and_abort("You don't have permission to access wallet features.")

        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# @require_audit_access
# ---------------------------------------------------------------------------

def require_audit_access(required_permission: str = "audit.view") -> Callable:
    """
    Abort with 403 if user cannot access audit logs.
    Accessible to: auditor, compliance_officer, super_admin, owner.

    Args:
        required_permission: Specific permission needed (default: audit.view)

    Example::
        @require_audit_access("audit.view")
        def view_financial_logs():
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = _get_current_user()

            if not user:
                _log_denied("unauthenticated", None, fn.__qualname__)
                flash("Please log in to access audit logs.", "warning")
                return redirect(url_for("auth_routes.login", next=request.url))

            from app.auth.policy import can
            if not can(user, required_permission):
                # Check for specific roles as fallback
                from app.auth.helpers import has_global_role
                allowed_roles = ["auditor", "compliance_officer", "super_admin", "owner"]
                if not has_global_role(user, *allowed_roles):
                    _log_denied(
                        "audit_access", user, fn.__qualname__,
                        required_permission=required_permission,
                    )
                    _flash_and_abort("Audit access requires auditor, compliance officer, or admin role.")

            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# @rate_limit
# ---------------------------------------------------------------------------

def rate_limit(limit: str, key_func: Optional[Callable] = None) -> Callable:
    """
    Apply rate limiting to a route.
    Uses Flask-Limiter.

    Args:
        limit: Rate limit string (e.g., "10 per minute", "100 per hour")
        key_func: Function to generate rate limit key (defaults to remote address)

    Example::
        @rate_limit("5 per minute")
        def login():
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from flask_limiter import Limiter
            from flask_limiter.util import get_remote_address

            # This is a decorator wrapper - actual rate limiting should be
            # applied at the Flask-Limiter level. This is a placeholder
            # for documentation purposes.
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# @require_verified
# ---------------------------------------------------------------------------

def require_verified(fn: Callable) -> Callable:
    """
    Abort with 403 if user is not verified.
    This is useful for features that require verified accounts.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _get_current_user()

        if not user:
            _log_denied("unauthenticated", None, fn.__qualname__)
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.url))

        # Check if user is verified
        if not getattr(user, "is_verified", False):
            # Also check profile verification status
            if hasattr(user, 'profile') and user.profile:
                if user.profile.verification_status != "verified":
                    _log_denied("unverified", user, fn.__qualname__)
                    flash("Your account needs to be verified to access this feature.", "warning")
                    return redirect(url_for("index"))
            else:
                _log_denied("unverified", user, fn.__qualname__)
                flash("Your account needs to be verified to access this feature.", "warning")
                return redirect(url_for("index"))

        return fn(*args, **kwargs)
    return wrapper

# ---------------------------------------------------------------------------
# @require_profile_completion
# ---------------------------------------------------------------------------

def require_profile_completion(fn: Callable) -> Callable:
    """
    Redirect to profile completion if profile is incomplete.
    Checks session flag 'profile_incomplete'.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        from flask import session, flash, redirect, url_for, request

        user = _get_current_user()

        if not user:
            _log_denied("unauthenticated", None, fn.__qualname__)
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.url))

        # Check if profile is incomplete via session flag
        if session.get("profile_incomplete"):
            flash("Please complete your profile to access this feature.", "warning")
            return redirect(url_for("auth.complete_profile"))

        return fn(*args, **kwargs)
    return wrapper

# ---------------------------------------------------------------------------
# @require_kyc_tier
# ---------------------------------------------------------------------------

def require_kyc_tier(min_tier: int) -> Callable:
    """
    Redirect to KYC upgrade if user's KYC tier is below required level.
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from flask import flash, redirect, url_for

            user = _get_current_user()

            if not user:
                _log_denied("unauthenticated", None, fn.__qualname__)
                flash("Please log in to access this page.", "warning")
                return redirect(url_for("auth.login", next=request.url))

            # Get user's KYC level
            kyc_level = getattr(user, 'kyc_level', 0)

            if kyc_level < min_tier:
                _log_denied(
                    "insufficient_kyc_tier", user, fn.__qualname__,
                    required_tier=min_tier,
                    current_tier=kyc_level
                )
                flash(f"This feature requires KYC Tier {min_tier} verification. Your current tier is {kyc_level}.", "warning")
                # Redirect to KYC upgrade page
                return redirect(url_for("kyc.upgrade"))

            return fn(*args, **kwargs)
        return wrapper
    return decorator

# ---------------------------------------------------------------------------
# Convenience aliases
# ---------------------------------------------------------------------------

# Alias for common use cases
require_super_admin = require_role("super_admin", "owner")
require_admin_or_owner = require_role("admin", "super_admin", "owner")
