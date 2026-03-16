# app/auth/policy.py
"""
Central authorisation policy.

``can(user, permission)`` is the single public entry point for all
permission checks across the application.

Design decisions
----------------
* **Owner bypass** — the ``owner`` role is always granted. Enforced in
  :mod:`app.auth.helpers`, not here, so the rule is never duplicated.
* **DB-driven** — permissions are resolved against the ``role_permissions``
  table via :func:`~app.auth.helpers.has_global_permission` /
  :func:`~app.auth.helpers.has_org_permission`. Seed the DB with
  :mod:`app.auth.seed` to populate them.
* **Fail-closed** — any unknown permission returns ``False``.
* **No side effects** — every function here is pure and stateless.

Usage
-----
::

    from app.auth.policy import can

    # Global check
    if can(current_user, "wallet.manage"):
        ...

    # Org-scoped check
    if can(current_user, "orgs.manage", org_id=org.id):
        ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.auth.helpers import (
    has_global_permission,
    has_org_permission,
    is_owner,
)

if TYPE_CHECKING:
    from app.identity.models.user import User


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def can(
    user: "User",
    permission: str,
    *,
    org_id: Optional[int] = None,
) -> bool:
    """
    Return ``True`` if *user* is authorised for *permission*.

    Args:
        user:       The authenticated ``User`` ORM instance.
        permission: Dot-namespaced capability string, e.g. ``"users.manage"``.
        org_id:     When provided, the check is scoped to that organisation.
                    When ``None``, a global permission check is performed.

    Returns:
        ``True`` if authorised, ``False`` otherwise (fail-closed).
    """
    if user is None:
        return False

    # Owner has unconditional access everywhere — checked once, here.
    if is_owner(user):
        return True

    if org_id is None:
        return has_global_permission(user, permission)

    return has_org_permission(user, org_id, permission)


# ---------------------------------------------------------------------------
# Convenience wrappers  (keeps view code readable)
# ---------------------------------------------------------------------------

def can_manage_users(user: "User") -> bool:
    return can(user, "users.manage")


def can_assign_roles(user: "User") -> bool:
    return can(user, "users.assign_roles")


def can_manage_orgs(user: "User") -> bool:
    return can(user, "orgs.manage")


def can_view_audit(user: "User") -> bool:
    return can(user, "audit.view")


def can_export_audit(user: "User") -> bool:
    return can(user, "audit.export")


def can_manage_wallet(user: "User") -> bool:
    return can(user, "wallet.manage")


def can_approve_withdrawals(user: "User") -> bool:
    return can(user, "wallet.approve_withdrawals")


def can_toggle_modules(user: "User") -> bool:
    """Only the ``owner`` can enable or disable platform modules."""
    return can(user, "system.modules")


def can_manage_content(user: "User") -> bool:
    return can(user, "content.manage")


def can_moderate_content(user: "User") -> bool:
    return can(user, "content.moderate")


def can_manage_transport(user: "User") -> bool:
    return can(user, "transport.manage")


def can_configure_transport(user: "User") -> bool:
    return can(user, "transport.settings")


def can_view_system_health(user: "User") -> bool:
    return can(user, "system.health")


def can_manage_permissions(user: "User") -> bool:
    """Only the ``owner`` can create permissions and link them to roles."""
    return can(user, "permissions.manage")