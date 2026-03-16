# app/auth/decorators.py
"""
Route-level authorisation decorators.

All decorators resolve the current user from ``flask_login.current_user``
(with a ``g.current_user`` fallback for API routes that set it manually).

Stacking order
--------------
Always place ``@login_required`` **above** these decorators so Flask-Login
handles the unauthenticated redirect before the role check runs::

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
    Abort 403 if user does not hold any of the named roles within
    the org identified by the ``org_id`` URL parameter.

@require_permission(permission, org_scoped=False)
    Abort 403 if user is not authorised for the named permission.

@owner_only
    Abort 403 for anyone who is not the platform ``owner``.
    Use on the most sensitive routes: module toggles, system config,
    permission seeding, danger-zone actions.

Notes
-----
* ``owner`` satisfies every ``@require_role`` check — no need to include
  it explicitly.
* All access denials are logged with structured context for audit trails.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Callable

from flask import abort, current_app, g
from flask_login import current_user

from app.auth.policy import can

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal: resolve current user
# ---------------------------------------------------------------------------

def _get_current_user():
    """
    Return the active user from Flask-Login or ``g.current_user``.

    Flask-Login is preferred (session-based web views).
    ``g.current_user`` is used by API routes that authenticate via token.
    """
    if current_user and current_user.is_authenticated:
        return current_user
    return getattr(g, "current_user", None)


def _log_denied(reason: str, user, endpoint: str, **extra) -> None:
    log.warning(
        "access_denied %s",
        reason,
        extra={
            "user_id":  getattr(user, "id",   None),
            "username": getattr(user, "username", None),
            "endpoint": endpoint,
            **extra,
        },
    )


# ---------------------------------------------------------------------------
# @require_role
# ---------------------------------------------------------------------------

def require_role(*roles: str) -> Callable:
    """
    Abort with **403** if the current user does not hold any of *roles*.

    ``owner`` satisfies every check implicitly.

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
                abort(401)

            from app.auth.helpers import has_global_role
            if not has_global_role(user, *roles):
                _log_denied(
                    "role_check", user, fn.__qualname__,
                    required_roles=roles,
                    user_roles=getattr(user, "role_names", []),
                )
                abort(403)

            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# @require_org_role
# ---------------------------------------------------------------------------

def require_org_role(*roles: str) -> Callable:
    """
    Abort with **403** if the current user does not hold any of *roles*
    within the organisation identified by the ``org_id`` route parameter.

    Platform owners bypass this check.

    Args:
        *roles: One or more org-scoped role name strings,
                e.g. ``"org_owner"``, ``"org_admin"``.

    Example::

        @require_org_role("org_owner", "org_admin")
        def org_settings(org_id):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user   = _get_current_user()
            org_id = kwargs.get("org_id")

            if not user:
                abort(401)

            if org_id is None:
                current_app.logger.error(
                    "@require_org_role used on route without org_id param: %s",
                    fn.__qualname__,
                )
                abort(500)

            from app.auth.helpers import has_org_role
            if not has_org_role(user, org_id, *roles):
                _log_denied(
                    "org_role_check", user, fn.__qualname__,
                    org_id=org_id,
                    required_roles=roles,
                )
                abort(403)

            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# @require_permission
# ---------------------------------------------------------------------------

def require_permission(permission: str, *, org_scoped: bool = False) -> Callable:
    """
    Abort with **403** if the current user is not authorised for
    *permission*.

    Args:
        permission: Dot-namespaced capability string, e.g. ``"wallet.manage"``.
        org_scoped: When ``True``, resolve against the ``org_id`` route
                    parameter (org-scoped check). Default ``False`` (global).

    Examples::

        @require_permission("wallet.manage")
        def wallet_settings():
            ...

        @require_permission("orgs.manage", org_scoped=True)
        def org_edit(org_id):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user   = _get_current_user()
            org_id = kwargs.get("org_id") if org_scoped else None

            if not user:
                abort(401)

            if not can(user, permission, org_id=org_id):
                _log_denied(
                    "permission_check", user, fn.__qualname__,
                    permission=permission,
                    org_id=org_id,
                )
                abort(403)

            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# @owner_only
# ---------------------------------------------------------------------------

def owner_only(fn: Callable) -> Callable:
    """
    Abort with **403** for anyone who is not the platform ``owner``.

    Use on the most sensitive routes: module toggles, system config,
    role seeding, danger-zone actions.

    Example::

        @owner_only
        def toggle_module(module):
            ...
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _get_current_user()

        if not user:
            abort(401)

        from app.auth.helpers import is_owner
        if not is_owner(user):
            _log_denied("owner_only", user, fn.__qualname__)
            abort(403)

        return fn(*args, **kwargs)
    return wrapper