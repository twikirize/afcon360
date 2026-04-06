# app/auth/roles.py
"""
Runtime role assignment and revocation utilities.

These functions are the write side of the RBAC system — they mutate the
database.  The read side (checking whether a user *has* a role) lives in
:mod:`app.auth.helpers`.

Global roles  →  persisted via :class:`~app.identity.models.user.UserRole`.
Org roles     →  persisted via :class:`~app.identity.models.organisation_member.OrgUserRole`.

All assignment functions are idempotent — calling them twice has no
additional effect.  All revocation functions return ``False`` gracefully
if the assignment did not exist.

Every mutation is audit-logged at ``INFO`` level with structured context.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.extensions import db
from app.identity.models.organisation_member import OrgUserRole, OrganisationMember
from app.identity.models.roles_permission import Role
from app.identity.models.user import UserRole

log = logging.getLogger(__name__)

DEFAULT_SCOPE = "global"
# ============================================================================
# ROLE CONSTANTS
# ============================================================================

# Global roles
ROLE_OWNER = "owner"
ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLE_AUDITOR = "auditor"                     # NEW: read-only audit access
ROLE_COMPLIANCE_OFFICER = "compliance_officer"  # NEW: AML review access
ROLE_USER = "user"

# Org roles
ROLE_ORG_ADMIN = "org_admin"
ROLE_ORG_MEMBER = "org_member"

# All global roles
ALL_GLOBAL_ROLES = [
    ROLE_OWNER,
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_COMPLIANCE_OFFICER,
    ROLE_USER,
]

# Role → permissions mapping
ROLE_PERMISSIONS = {
    ROLE_OWNER: ["audit:read", "audit:export", "audit:delete", "aml:review", "aml:resolve"],
    ROLE_SUPER_ADMIN: ["audit:read", "audit:export", "aml:review"],
    ROLE_ADMIN: ["audit:read", "audit:export"],
    ROLE_AUDITOR: ["audit:read"],
    ROLE_COMPLIANCE_OFFICER: ["audit:read", "aml:review", "aml:resolve"],
    ROLE_USER: [],
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_role(name: str, scope: str) -> Role:
    """
    Fetch a role by name and scope, raising ``ValueError`` if not found.

    Intentionally strict — callers should always pass a valid, seeded
    role name.  If you see this error, run ``flask seed-roles``.
    """
    role = Role.query.filter_by(name=name, scope=scope).first()
    if not role:
        raise ValueError(
            f"Role {name!r} (scope={scope!r}) not found. "
            "Run `flask seed-roles` to seed the database."
        )
    return role


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def get_role_by_name(name: str, scope: str = DEFAULT_SCOPE) -> Optional[Role]:
    """
    Return the ``Role`` with the given name and scope, or ``None``.

    Args:
        name:  Role name string, e.g. ``"admin"``.
        scope: ``"global"`` (default) or ``"org"``.
    """
    return Role.query.filter_by(name=name, scope=scope).first()


def list_roles(scope: str = DEFAULT_SCOPE) -> List[Role]:
    """
    Return all ``Role`` instances for *scope*, ordered by level ascending.

    Args:
        scope: ``"global"`` (default) or ``"org"``.
    """
    return (
        Role.query
        .filter_by(scope=scope)
        .order_by(Role.level.asc().nullslast())
        .all()
    )


# ---------------------------------------------------------------------------
# Global role assignment
# ---------------------------------------------------------------------------

def assign_global_role(
    user_id: int,
    role_name: str,
    *,
    assigned_by_id: Optional[int] = None,
) -> UserRole:
    """
    Assign a global role to a user.

    Idempotent — returns the existing ``UserRole`` if already assigned.

    Args:
        user_id:        Primary key of the target ``User``.
        role_name:      Name of the global role to assign.
        assigned_by_id: PK of the admin performing the action (for audit).

    Returns:
        The ``UserRole`` instance (new or existing).

    Raises:
        ValueError: If the role does not exist in the database.
    """
    role = _get_role(role_name, scope="global")

    existing = UserRole.query.filter_by(user_id=user_id, role_id=role.id).first()
    if existing:
        return existing

    ur = UserRole(
        user_id=user_id,
        role_id=role.id,
        assigned_by=assigned_by_id,
    )
    try:
        db.session.add(ur)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log.error("Failed to assign global role %s to user %s: %s", role_name, user_id, e)
        raise

    log.info(
        "global_role_assigned",
        extra={
            "user_id":     user_id,
            "role":        role_name,
            "assigned_by": assigned_by_id,
        },
    )

    return ur


def revoke_global_role(
    user_id: int,
    role_name: str,
    *,
    revoked_by_id: Optional[int] = None,
) -> bool:
    """
    Revoke a global role from a user.

    Args:
        user_id:       Primary key of the target ``User``.
        role_name:     Name of the role to revoke.
        revoked_by_id: PK of the admin performing the action (for audit).

    Returns:
        ``True`` if the role was found and removed, ``False`` if the user
        did not hold that role.

    Raises:
        ValueError: If the role does not exist in the database.
    """
    role = _get_role(role_name, scope="global")

    ur = UserRole.query.filter_by(user_id=user_id, role_id=role.id).first()
    if not ur:
        return False

    try:
        db.session.delete(ur)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log.error("Failed to revoke global role %s from user %s: %s", role_name, user_id, e)
        raise

    log.info(
        "global_role_revoked",
        extra={
            "user_id":    user_id,
            "role":       role_name,
            "revoked_by": revoked_by_id,
        },
    )

    return True


# ---------------------------------------------------------------------------
# Organisation role assignment
# ---------------------------------------------------------------------------

def assign_org_role(
    user_id: int,
    org_id: int,
    role_name: str,
    *,
    assigned_by_id: Optional[int] = None,
) -> OrgUserRole:
    """
    Assign an organisation-scoped role to a user.

    Idempotent — returns the existing ``OrgUserRole`` if already assigned.

    Args:
        user_id:        Primary key of the target ``User``.
        org_id:         Primary key of the target ``Organisation``.
        role_name:      Name of the org role, e.g. ``"org_admin"``.
        assigned_by_id: PK of the admin performing the action (for audit).

    Returns:
        The ``OrgUserRole`` instance (new or existing).

    Raises:
        ValueError: If the role does not exist or the user is not a member.
    """
    role = _get_role(role_name, scope="org")

    membership = OrganisationMember.query.filter_by(
        user_id=user_id,
        organisation_id=org_id,
    ).first()

    if not membership:
        raise ValueError(
            f"User {user_id} is not a member of organisation {org_id}. "
            "Add them as a member before assigning an org role."
        )

    existing = OrgUserRole.query.filter_by(
        organisation_member_id=membership.id,
        role_id=role.id,
    ).first()
    if existing:
        return existing

    our = OrgUserRole(
        organisation_member_id=membership.id,
        role_id=role.id,
        assigned_by=assigned_by_id,
    )
    try:
        db.session.add(our)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log.error("Failed to assign org role %s in org %s: %s", role_name, org_id, e)
        raise

    log.info(
        "org_role_assigned",
        extra={
            "user_id":     user_id,
            "org_id":      org_id,
            "role":        role_name,
            "assigned_by": assigned_by_id,
        },
    )

    return our


def revoke_org_role(
    user_id: int,
    org_id: int,
    role_name: str,
    *,
    revoked_by_id: Optional[int] = None,
) -> bool:
    """
    Revoke an org-scoped role from a user.

    Args:
        user_id:       Primary key of the target ``User``.
        org_id:        Primary key of the target ``Organisation``.
        role_name:     Name of the role to revoke.
        revoked_by_id: PK of the admin performing the action (for audit).

    Returns:
        ``True`` if the assignment was found and removed, ``False``
        if it did not exist.

    Raises:
        ValueError: If the role does not exist in the database.
    """
    role = _get_role(role_name, scope="org")

    membership = OrganisationMember.query.filter_by(
        user_id=user_id,
        organisation_id=org_id,
    ).first()

    if not membership:
        return False

    our = OrgUserRole.query.filter_by(
        organisation_member_id=membership.id,
        role_id=role.id,
    ).first()

    if not our:
        return False

    try:
        db.session.delete(our)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log.error("Failed to revoke org role %s in org %s: %s", role_name, org_id, e)
        raise

    log.info(
        "org_role_revoked",
        extra={
            "user_id":    user_id,
            "org_id":     org_id,
            "role":       role_name,
            "revoked_by": revoked_by_id,
        },
    )

    return True