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
                    If not provided and user is in organization context,
                    use the current organization ID.

    Returns:
        ``True`` if authorised, ``False`` otherwise (fail-closed).
    """
    if user is None:
        return False

    # Owner has unconditional access everywhere — checked once, here.
    if is_owner(user):
        return True

    # If org_id is not explicitly provided, check if we're in organization context
    if org_id is None:
        from app.auth.helpers import is_acting_as_organization, get_current_org_id
        if is_acting_as_organization():
            org_id = get_current_org_id()

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

# Add to app/auth/policy.py

def can_view_audit_logs(user: "User") -> bool:
    """Check if user can view audit logs."""
    return can(user, "audit.view") or can(user, "audit.read")


def can_review_aml(user: "User") -> bool:
    """Check if user can review AML flagged transactions."""
    return can(user, "aml.review")


def can_resolve_aml(user: "User") -> bool:
    """Check if user can resolve AML flagged transactions."""
    return can(user, "aml.resolve")
