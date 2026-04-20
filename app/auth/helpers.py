# app/auth/helpers.py
"""
Stateless role and permission helper functions.

These functions accept a ``User`` ORM instance and inspect its loaded
relationships. They never hit the database directly — callers are
responsible for ensuring the relevant relationships are loaded.

Global helpers  →  operate on ``user.roles``         (UserRole → Role)
Org helpers     →  operate on ``user.organisations``  (OrganisationMember
                   → OrgUserRole → OrgRole)

Owner bypass
------------
The ``owner`` role satisfies every role and permission check
unconditionally. This is the single place that rule is enforced — every
other check delegates here so the bypass is never duplicated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.identity.models.organisation_member import OrganisationMember
    from app.identity.models.user import User
else:
    # Import for runtime
    try:
        from app.identity.models.organisation_member import OrganisationMember
        from app.identity.models.user import User
    except ImportError:
        # For TYPE_CHECKING only
        pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Roles considered platform staff (used for quick access gating).
STAFF_ROLES: frozenset[str] = frozenset({
    "owner", "super_admin", "admin", "moderator", "support",
})

#: Privilege order — index 0 = highest privilege.
ROLE_HIERARCHY: tuple[str, ...] = (
    "owner",
    "super_admin",
    "admin",
    "moderator",
    "support",
    "fan",
)


# ---------------------------------------------------------------------------
# Global role helpers
# ---------------------------------------------------------------------------

def is_owner(user: "User") -> bool:
    """Return ``True`` if the user holds the ``owner`` role."""
    return has_global_role(user, "owner")


def is_system_admin(user: "User") -> bool:
    """
    Return ``True`` if the user is at least an ``admin``
    (i.e. owner, super_admin, or admin).
    """
    return has_global_role(user, "owner", "super_admin", "admin")


def has_global_role(user: "User", *role_names: str) -> bool:
    """
    Return ``True`` if the user holds **any** of the named global roles.

    ``owner`` implicitly satisfies every role check — an owner can do
    anything any other role can do.

    Args:
        user:        The authenticated ``User`` instance.
        *role_names: One or more role name strings to check against.

    Example::

        if has_global_role(current_user, "admin", "super_admin"):
            ...
    """
    if not user or not user.roles:
        return False

    role_set = frozenset(role_names)

    for ur in user.roles:
        if not ur.role:
            continue
        name = ur.role.name
        if name == "owner":
            return True
        if name in role_set:
            return True

    return False


def highest_role(user: "User") -> Optional[str]:
    """
    Return the name of the user's most-privileged global role, or
    ``None`` if the user has no roles.

    Uses :data:`ROLE_HIERARCHY` for ordering (index 0 = highest privilege).
    Roles not present in the hierarchy are treated as lowest priority.
    """
    if not user or not user.roles:
        return None

    user_role_names = {ur.role.name for ur in user.roles if ur.role}

    for role_name in ROLE_HIERARCHY:
        if role_name in user_role_names:
            return role_name

    return next(iter(user_role_names), None)


def has_global_permission(user: "User", permission_name: str) -> bool:
    """
    Return ``True`` if any of the user's global roles carries the named
    permission.

    ``owner`` short-circuits to ``True`` without consulting the permission
    table — the platform owner is never locked out.

    Args:
        user:            The authenticated ``User`` instance.
        permission_name: Dot-namespaced string, e.g. ``"users.manage"``.
    """
    if not user or not user.roles:
        return False

    for ur in user.roles:
        role = ur.role
        if not role:
            continue

        if role.name == "owner":
            return True

        for rp in role.permissions:
            if rp.permission and rp.permission.name == permission_name:
                return True

    return False


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def get_current_context():
    """
    Get the current context (individual or organization) from session.
    Returns a tuple of (context_type, org_id_or_none)
    """
    from flask import session
    context = session.get("current_context", "individual")
    org_id = session.get("current_org_id")
    return context, org_id

def is_acting_as_organization():
    """Check if user is currently acting as an organization."""
    context, org_id = get_current_context()
    return context == "organization" and org_id is not None

def get_current_org_id():
    """Get the current organization ID if in organization context."""
    context, org_id = get_current_context()
    return org_id if context == "organization" else None

# ---------------------------------------------------------------------------
# Profile completion helpers
# ---------------------------------------------------------------------------

def get_profile_completion_data(user: "User"):
    """
    Get profile completion data for a user.
    Returns a dictionary with completion percentage and breakdown.
    """
    if not user:
        return {
            'percentage': 0,
            'breakdown': {},
            'needs_completion': False
        }

    # Try to get the user's profile
    try:
        from app.profile.models import get_profile_by_user
        profile = get_profile_by_user(user.public_id)

        if profile:
            percentage = profile.get_completion_percentage()
            breakdown = profile.get_completion_breakdown()
            return {
                'percentage': percentage,
                'breakdown': breakdown,
                'needs_completion': percentage < 100
            }
    except Exception:
        # If there's any error, fall back to default
        pass

    return {
        'percentage': 0,
        'breakdown': {},
        'needs_completion': True
    }

# ---------------------------------------------------------------------------
# Organisation role helpers
# ---------------------------------------------------------------------------

def get_org_member(
    user: "User",
    org_id: int,
) -> "OrganisationMember | None":
    """
    Return the active ``OrganisationMember`` linking *user* to *org_id*,
    or ``None`` if the user is not a member or the membership is
    soft-deleted.
    """
    for membership in (user.organisations or []):
        if (
            membership.organisation_id == org_id
            and not membership.is_deleted
        ):
            return membership
    return None


def has_org_role(user: "User", org_id: int, *role_names: str) -> bool:
    """
    Return ``True`` if the user holds **any** of the named roles within
    *org_id*.

    Platform owners bypass this check and always return ``True`` —
    they have implicit access to every organisation.

    Args:
        user:        The authenticated ``User`` instance.
        org_id:      The target organisation's primary key.
        *role_names: One or more org-scoped role name strings.
    """
    if not user:
        return False

    if is_owner(user):
        return True

    member = get_org_member(user, org_id)
    if not member:
        return False

    role_set = frozenset(role_names)

    return any(
        our.role and our.role.name in role_set
        for our in (member.roles or [])
    )


def has_org_permission(
    user: "User",
    org_id: int,
    permission_name: str,
) -> bool:
    """
    Return ``True`` if the user's org-scoped roles within *org_id* carry
    the named permission.

    Platform owners bypass this check unconditionally.

    Args:
        user:            The authenticated ``User`` instance.
        org_id:          The target organisation's primary key.
        permission_name: Dot-namespaced permission string.
    """
    if not user:
        return False

    if is_owner(user):
        return True

    member = get_org_member(user, org_id)
    if not member:
        return False

    for our in (member.roles or []):
        role = our.role
        if not role:
            continue
        for rp in role.permissions:
            if rp.permission and rp.permission.name == permission_name:
                return True

    return False
