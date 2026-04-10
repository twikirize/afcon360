# app/identity/models/organisation_member.py
"""
Organisation membership models.

Hierarchy within an organisation:
    OrgUserRole      links a member to an OrgRole (role assignment)
    OrgRole          org-specific role definition (references global Role via template_name)
    OrgRolePermission links OrgRoles to global Permissions
    OrgMemberPermission direct per-member permission grant/deny (overrides role)

Org roles are stored in ``org_roles`` (per-org definitions) and reference
the global ``roles`` table via ``template_name`` for default permission sets
defined in seed.py.

OrgUserRole.role_id  →  org_roles.id   (org-specific role instance)
helpers.has_org_role →  walks this chain to check membership
"""

from __future__ import annotations

from datetime import datetime
from functools import cached_property

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey,
    Index, JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.extensions import db


# ---------------------------------------------------------------------------
# OrganisationMember
# ---------------------------------------------------------------------------

class OrganisationMember(db.Model):
    """
    Links a ``User`` to an ``Organisation`` (many-to-many join).

    A member can hold multiple ``OrgUserRole`` assignments within the
    same organisation and may also have direct ``OrgMemberPermission``
    grants or denies that override role defaults.
    """

    __tablename__ = "organisation_members"
    __table_args__ = (
        UniqueConstraint("user_id", "organisation_id", name="uq_org_member_user_org"),
        Index("ix_org_member_active", "organisation_id", "is_active"),
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id         = Column(BigInteger, ForeignKey("users.id",          ondelete="CASCADE"),  nullable=False, index=True)
    organisation_id = Column(BigInteger, ForeignKey("organisations.id",  ondelete="CASCADE"),  nullable=False, index=True)

    # Optional free-text job title (display purposes only)
    job_title = Column(String(128), nullable=True)

    # Lifecycle
    is_active  = Column(Boolean,  default=True,  nullable=False, index=True)
    is_deleted = Column(Boolean,  default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)

    # Flexible metadata (onboarding state, notes, etc.)
    meta = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # --- relationships -------------------------------------------------------

    user         = relationship("User",         back_populates="organisations", lazy="joined")
    organisation = relationship("Organisation", back_populates="users",         lazy="joined")

    roles = relationship(
        "OrgUserRole",
        back_populates="organisation_member",
        cascade="all, delete-orphan",
        lazy="select",
    )

    direct_permissions = relationship(
        "OrgMemberPermission",
        back_populates="member",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # --- computed properties -------------------------------------------------

    @cached_property
    def effective_permissions(self) -> set[str]:
        """
        Return the complete set of permission name strings this member has.

        Resolution order (last write wins on conflict):
            1. Role-based permissions  (from OrgRole → OrgRolePermission)
            2. Direct grants           (OrgMemberPermission.granted = True)
            3. Direct denies           (OrgMemberPermission.granted = False)

        ``org_owner`` always receives all org-prefixed permissions regardless
        of explicit assignments.
        """
        perms: set[str] = set()

        # 1. Role-based permissions
        for our in self.roles:
            if our.role:
                perms.update(our.role.permission_names)

        # 2 & 3. Direct permission overrides
        for dp in self.direct_permissions:
            if not dp.permission:
                continue
            if dp.granted:
                perms.add(dp.permission.name)
            else:
                perms.discard(dp.permission.name)

        # org_owner gets all org.* permissions unconditionally
        if any(our.role and our.role.name == "org_owner" for our in self.roles):
            from app.identity.models.roles_permission import Permission
            org_perms = Permission.query.filter(
                Permission.name.startswith("org.")
            ).all()
            perms.update(p.name for p in org_perms)

        return perms

    def has_permission(self, permission_name: str) -> bool:
        """Return ``True`` if this member has the named permission."""
        return permission_name in self.effective_permissions

    def invalidate_permission_cache(self) -> None:
        """
        Clear the ``effective_permissions`` cache after role/permission changes.

        Call this whenever an ``OrgUserRole`` or ``OrgMemberPermission``
        is added, updated, or removed for this member.
        """
        self.__dict__.pop("effective_permissions", None)

    # --- lifecycle helpers ---------------------------------------------------

    def soft_delete(self) -> None:
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()

    def restore(self) -> None:
        self.is_deleted = False
        self.deleted_at = None

    def __repr__(self) -> str:
        return (
            f"<OrganisationMember user_id={self.user_id} "
            f"org_id={self.organisation_id}>"
        )


# ---------------------------------------------------------------------------
# OrgUserRole  (role assignment for a member)
# ---------------------------------------------------------------------------

class OrgUserRole(db.Model):
    """
    Assigns an ``OrgRole`` to an ``OrganisationMember``.

    One member can hold multiple roles within the same organisation
    (e.g. both ``finance_manager`` and ``org_admin``).
    """

    __tablename__ = "org_user_roles"
    __table_args__ = (
        UniqueConstraint("organisation_member_id", "role_id", name="uq_org_user_role"),
        Index("ix_org_user_role_member", "organisation_member_id"),
    )

    id                     = Column(BigInteger, primary_key=True, autoincrement=True)
    organisation_member_id = Column(BigInteger, ForeignKey("organisation_members.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id                = Column(BigInteger, ForeignKey("org_roles.id",            ondelete="CASCADE"), nullable=False, index=True)
    assigned_by            = Column(BigInteger, ForeignKey("users.id",                ondelete="SET NULL"), nullable=True,  index=True)
    assigned_at            = Column(DateTime, default=datetime.utcnow, nullable=False)

    organisation_member = relationship("OrganisationMember", back_populates="roles",         lazy="joined")
    role                = relationship("OrgRole",            lazy="joined")
    assigned_by_user    = relationship("User",               foreign_keys=[assigned_by],      lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<OrgUserRole member_id={self.organisation_member_id} "
            f"role_id={self.role_id}>"
        )


# ---------------------------------------------------------------------------
# OrgRole  (org-specific role definition)
# ---------------------------------------------------------------------------

class OrgRole(db.Model):
    """
    An organisation-specific role definition.

    Each organisation gets its own role instances created from the global
    templates defined in ``seed.ORG_ROLE_DEFS``.  The ``template_name``
    column links back to the seed template so the permission set can be
    re-applied when needed.

    ``org_roles.id``  is what ``OrgUserRole.role_id`` references.
    ``template_name`` matches names in ``seed.ORG_ROLE_DEFS`` and
                      ``seed.ORG_ROLE_TEMPLATES``.
    """

    __tablename__ = "org_roles"
    __table_args__ = (
        UniqueConstraint("name", "organisation_id", name="uq_org_role_name_org"),
        Index("ix_org_role_org", "organisation_id"),
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    name            = Column(String(64),  nullable=False, index=True)
    organisation_id = Column(BigInteger, ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, index=True)
    description     = Column(Text, nullable=True)

    # Link to the global seed template (e.g. "finance_manager")
    template_name   = Column(String(64), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    organisation = relationship("Organisation", back_populates="custom_roles")
    permissions  = relationship("OrgRolePermission", back_populates="role", cascade="all, delete-orphan")
    assignments  = relationship("OrgUserRole", back_populates="role")

    @property
    def permission_names(self) -> set[str]:
        """Return all permission name strings granted to this role."""
        return {rp.permission.name for rp in self.permissions if rp.permission}

    def __repr__(self) -> str:
        return (
            f"<OrgRole id={self.id} name={self.name!r} "
            f"org_id={self.organisation_id}>"
        )


# ---------------------------------------------------------------------------
# OrgRolePermission  (links OrgRole → global Permission)
# ---------------------------------------------------------------------------

class OrgRolePermission(db.Model):
    """
    Many-to-many link between an ``OrgRole`` and a global ``Permission``.

    Org roles share the global permission namespace (``"org.finance.view"``,
    ``"org.transport.manage"``, etc.) rather than defining their own.
    """

    __tablename__ = "org_role_permissions"
    __table_args__ = (
        UniqueConstraint("org_role_id", "permission_id", name="uq_org_role_permission"),
    )

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    org_role_id   = Column(BigInteger, ForeignKey("org_roles.id",    ondelete="CASCADE"), nullable=False, index=True)
    permission_id = Column(BigInteger, ForeignKey("permissions.id",  ondelete="CASCADE"), nullable=False, index=True)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)

    role       = relationship("OrgRole",      back_populates="permissions")
    permission = relationship("Permission")

    def __repr__(self) -> str:
        return (
            f"<OrgRolePermission role_id={self.org_role_id} "
            f"perm_id={self.permission_id}>"
        )


# ---------------------------------------------------------------------------
# OrgMemberPermission  (direct per-member permission grant or deny)
# ---------------------------------------------------------------------------

class OrgMemberPermission(db.Model):
    """
    A direct permission grant or explicit deny for a single member.

    These override role-based permissions.  Use sparingly — role
    assignments should cover 95% of cases.  Direct denies are the
    exceptional case where a member needs a role but must be excluded
    from one specific permission.

    ``granted = True``   adds the permission (grant)
    ``granted = False``  removes it even if a role would grant it (deny)
    """

    __tablename__ = "org_member_permissions"
    __table_args__ = (
        UniqueConstraint("member_id", "permission_id", name="uq_member_permission"),
    )

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    member_id     = Column(BigInteger, ForeignKey("organisation_members.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = Column(BigInteger, ForeignKey("permissions.id",          ondelete="CASCADE"), nullable=False, index=True)
    granted       = Column(Boolean, default=True, nullable=False)   # True = grant, False = explicit deny
    granted_by    = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at    = Column(DateTime, default=datetime.utcnow, nullable=False)

    member     = relationship("OrganisationMember", back_populates="direct_permissions")
    permission = relationship("Permission")
    grantor    = relationship("User", foreign_keys=[granted_by])

    def __repr__(self) -> str:
        action = "grant" if self.granted else "deny"
        return (
            f"<OrgMemberPermission member_id={self.member_id} "
            f"perm_id={self.permission_id} action={action}>"
        )
