# app/identity/models/roles_permission.py
"""
Role, Permission, and RolePermission models.

Global role hierarchy (level — lower = more privileged):
    1  owner        Ultimate platform authority
    2  super_admin  Full system admin (except ownership transfer)
    3  admin        Manages regular users and organisations
    4  moderator    Content moderation and user support
    5  support      Read-heavy; assists users with issues
    6  fan          Default end-user; no admin access

Organisation-scoped roles live in organisation_member.py (OrgRole/OrgUserRole).
Permissions are dot-namespaced strings: "<resource>.<action>", e.g. "users.manage".

Factory helpers
---------------
    get_or_create_role()          Idempotent global/org role upsert
    get_or_create_org_role()      Shortcut for scope="org"
    get_or_create_permission()    Idempotent permission upsert
    assign_permission_to_role()   Idempotent role→permission link
    remove_permission_from_role() Tear down a role→permission link
"""

from __future__ import annotations

import warnings
from datetime import datetime
from typing import Optional, Set

from sqlalchemy import Index, UniqueConstraint, event
from sqlalchemy.orm import relationship, validates

from app.extensions import db


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def get_or_create_role(
    name: str,
    *,
    scope: str = "global",
    description: Optional[str] = None,
    level: Optional[int] = None,
    commit: bool = True,
) -> "Role":
    """
    Idempotent role factory.

    Returns the existing Role if (name, scope) already exists.
    Creates and persists a new one otherwise.

    If the role exists but ``level`` is provided and differs from the stored
    value, the level is updated — useful for re-seeding after hierarchy changes.

    Args:
        name:        Role identifier, e.g. ``"owner"``, ``"admin"``.
        scope:       ``"global"`` (platform-wide) or ``"org"`` (per-organisation).
        description: Human-readable summary shown in the admin UI.
        level:       Numeric privilege rank — lower = more privileged (owner=1).
        commit:      Commit immediately. Pass ``False`` when batching inserts.

    Returns:
        The ``Role`` instance (new or existing).
    """
    role = Role.query.filter_by(name=name, scope=scope).first()

    if role:
        if level is not None and role.level != level:
            role.level = level
            if commit:
                db.session.commit()
            else:
                db.session.flush()
        return role

    role = Role(name=name, scope=scope, description=description, level=level)
    db.session.add(role)

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return role


def get_or_create_org_role(
    name: str,
    *,
    description: Optional[str] = None,
    level: Optional[int] = None,
    commit: bool = True,
) -> "Role":
    """
    Convenience wrapper for organisation-scoped roles.

    Equivalent to ``get_or_create_role(name, scope="org", ...)``.
    """
    return get_or_create_role(
        name,
        scope="org",
        description=description,
        level=level,
        commit=commit,
    )


def get_or_create_permission(
    name: str,
    *,
    description: Optional[str] = None,
    commit: bool = True,
) -> "Permission":
    """
    Idempotent permission factory.

    Returns the existing ``Permission`` if already registered, otherwise
    creates it.

    Args:
        name:        Dot-namespaced capability string, e.g. ``"wallet.manage"``.
        description: Human-readable explanation for the admin UI.
        commit:      Commit immediately. Pass ``False`` when batching.
    """
    perm = Permission.query.filter_by(name=name).first()
    if perm:
        return perm

    perm = Permission(name=name, description=description)
    db.session.add(perm)

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return perm


def assign_permission_to_role(
    role: "Role",
    permission: "Permission",
    *,
    commit: bool = True,
) -> "RolePermission":
    """
    Idempotent link between a role and a permission.

    Safe to call multiple times — returns the existing link if already present.

    Args:
        role:       The ``Role`` instance to grant the permission to.
        permission: The ``Permission`` instance to grant.
        commit:     Commit immediately. Pass ``False`` when batching.

    Returns:
        The ``RolePermission`` link (new or existing).
    """
    # Ensure PKs are assigned before querying the link table.
    if not role.id or not permission.id:
        db.session.flush()

    link = RolePermission.query.filter_by(
        role_id=role.id,
        permission_id=permission.id,
    ).first()

    if link:
        return link

    link = RolePermission(role_id=role.id, permission_id=permission.id)
    db.session.add(link)

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return link


def remove_permission_from_role(
    role: "Role",
    permission: "Permission",
    *,
    commit: bool = True,
) -> bool:
    """
    Remove a permission from a role.

    Args:
        role:       The ``Role`` instance.
        permission: The ``Permission`` instance to revoke.
        commit:     Commit immediately.

    Returns:
        ``True`` if the link was found and deleted, ``False`` if it did
        not exist.
    """
    link = RolePermission.query.filter_by(
        role_id=role.id,
        permission_id=permission.id,
    ).first()

    if not link:
        return False

    db.session.delete(link)

    if commit:
        db.session.commit()
    else:
        db.session.flush()

    return True


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------

class Role(db.Model):
    """
    A named, scoped role definition.

    Roles are reusable blueprints. Users are granted roles via ``UserRole``
    (global) or ``OrgUserRole`` (per-organisation).

    Scope values
    ------------
    ``"global"``  Platform-wide roles (owner, super_admin, admin, …).
    ``"org"``     Organisation-scoped roles (org_owner, org_admin, …).

    Level values (global scope)
    ---------------------------
    1 owner · 2 super_admin · 3 admin · 4 moderator · 5 support · 6 fan
    """

    __allow_unmapped__ = True
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("name", "scope", name="uq_role_name_scope"),
        Index("ix_role_level_scope", "level", "scope"),
    )

    id          = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name        = db.Column(db.String(64),  nullable=False, index=True)
    scope       = db.Column(db.String(20),  nullable=False, index=True, default="global")
    level       = db.Column(db.BigInteger,  nullable=True,  index=True)
    description = db.Column(db.Text,        nullable=True)

    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at  = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # --- relationships -------------------------------------------------------

    permissions: list["RolePermission"] = relationship(
        "RolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
        lazy="select",
    )

    user_roles: list = relationship(
        "UserRole",
        back_populates="role",
        cascade="all, delete-orphan",
        foreign_keys="UserRole.role_id",
        lazy="select",
    )

    # --- computed properties -------------------------------------------------

    @property
    def permission_names(self) -> Set[str]:
        """Return the set of permission name strings granted to this role."""
        return {rp.permission.name for rp in self.permissions if rp.permission}

    @property
    def is_global(self) -> bool:
        """Return ``True`` if this is a platform-wide role."""
        return self.scope == "global"

    @property
    def is_org_scoped(self) -> bool:
        """Return ``True`` if this is an organisation-scoped role."""
        return self.scope == "org"

    # --- permission helpers --------------------------------------------------

    def has_permission(self, name: str) -> bool:
        """Return ``True`` if this role carries the named permission."""
        return name in self.permission_names

    def grant_permission(
        self, permission: "Permission", *, commit: bool = True
    ) -> "RolePermission":
        """Grant a permission to this role (idempotent)."""
        return assign_permission_to_role(self, permission, commit=commit)

    def revoke_permission(
        self, permission: "Permission", *, commit: bool = True
    ) -> bool:
        """Revoke a permission from this role."""
        return remove_permission_from_role(self, permission, commit=commit)

    def __repr__(self) -> str:
        return (
            f"<Role id={self.id} name={self.name!r} "
            f"scope={self.scope!r} level={self.level}>"
        )


# ---------------------------------------------------------------------------
# Permission
# ---------------------------------------------------------------------------

class Permission(db.Model):
    """
    A granular, named capability.

    Naming convention: ``"<resource>.<action>"``
    Examples: ``"users.manage"``, ``"wallet.withdraw"``, ``"system.modules"``

    Permissions are assigned to roles via ``RolePermission`` and checked
    at runtime through ``app.auth.helpers.has_global_permission`` or
    ``app.auth.policy.can``.
    """

    __allow_unmapped__ = True
    __tablename__ = "permissions"

    id          = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name        = db.Column(db.String(128), nullable=False, unique=True, index=True)
    description = db.Column(db.Text, nullable=True)

    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at  = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    roles: list["RolePermission"] = relationship(
        "RolePermission",
        back_populates="permission",
        cascade="all, delete-orphan",
        lazy="select",
    )

    @property
    def role_names(self) -> Set[str]:
        """Return the set of role names that carry this permission."""
        return {rp.role.name for rp in self.roles if rp.role}

    def assigned_to(self, role: "Role") -> bool:
        """Return ``True`` if this permission is assigned to *role*."""
        return any(rp.role_id == role.id for rp in self.roles)

    def __repr__(self) -> str:
        return f"<Permission id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# RolePermission  (association table)
# ---------------------------------------------------------------------------

class RolePermission(db.Model):
    """
    Many-to-many link between :class:`Role` and :class:`Permission`.

    Use :func:`assign_permission_to_role` to create links — it is
    idempotent and handles the uniqueness constraint gracefully.
    """

    __allow_unmapped__ = True
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        Index("ix_rp_role_id",       "role_id"),
        Index("ix_rp_permission_id", "permission_id"),
    )

    id            = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    role_id       = db.Column(
        db.BigInteger,
        db.ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_id = db.Column(
        db.BigInteger,
        db.ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role:       "Role"       = relationship("Role",       back_populates="permissions", lazy="joined")
    permission: "Permission" = relationship("Permission", back_populates="roles",       lazy="joined")

    @validates("role_id", "permission_id")
    def validate_ids(self, key, value):
        if value is not None and value <= 0:
            raise ValueError(f"{key} must be a positive integer")
        return value

    def __repr__(self) -> str:
        return (
            f"<RolePermission role_id={self.role_id} "
            f"permission_id={self.permission_id}>"
        )


# ---------------------------------------------------------------------------
# ORM event listeners  (data integrity enforced at the persistence layer)
# ---------------------------------------------------------------------------

@event.listens_for(Role, "before_insert")
@event.listens_for(Role, "before_update")
def _validate_role(mapper, connection, target: Role) -> None:
    """Enforce scope enum and level range before any DB write."""
    if target.scope not in ("global", "org"):
        raise ValueError(
            f"Invalid role scope {target.scope!r}. Must be 'global' or 'org'."
        )
    if target.level is not None and target.level < 1:
        raise ValueError(
            f"Role level must be >= 1 (lower = more privileged). Got {target.level}."
        )


@event.listens_for(Permission, "before_insert")
@event.listens_for(Permission, "before_update")
def _validate_permission(mapper, connection, target: Permission) -> None:
    """Reject empty names; warn on non-conventional naming."""
    if not target.name or not target.name.strip():
        raise ValueError("Permission name cannot be empty.")
    if "." not in target.name:
        warnings.warn(
            f"Permission {target.name!r} does not follow the "
            "'resource.action' naming convention.",
            stacklevel=2,
        )