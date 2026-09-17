# app/core/transport_permissions.py
"""
Dynamic Transport Permissions System.

Per-grantee (not per-role-universal) transport management permissions.
Grants are dynamic - owner/super_admin can grant/revoke specific permissions
to individual users/roles without affecting other users.

This is a SQLAlchemy model (inherits BaseModel) stored in the
``transport_permissions`` table, distinct from the Role/Permission system
(app.identity.models.roles_permission).

Permissions checked at runtime by:
- ``transport_permission_required`` decorator
- Enhanced ``require_role`` decorator
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import validates

from app.extensions import db


class TransportPermission(db.Model):
    """
    Dynamic transport permission grant.

    Stores owner/super_admin grants of transport management permissions
    to individual users/roles. These are separate from the Role/Permission
    system and provide granular, dynamic access control.

    Attributes:
        id: Primary key
        grantee_user_id: User who receives this permission
        grantee_role: Role name (e.g. "admin", "dispatcher")
        can_manage_drivers: Grant driver verification/rejection/suspension
        can_manage_vehicles: Grant vehicle creation/edit/deletion
        can_view_dashboard: Grant dashboard view access
        is_active: Whether the permission is currently active
        granted_by_user_id: Who granted this permission (audit trail)
        granted_at: When the permission was granted
        expires_at: When it auto-revokes (NULL = never expires)
    """

    __tablename__ = "transport_permissions"
    __table_args__ = (
        UniqueConstraint("grantee_user_id", "grantee_role", name="uq_tp_grantee_role"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    grantee_user_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="User who receives this transport permission",
    )
    grantee_role = Column(
        String(50),
        nullable=False,
        default="",
        comment="Role name (e.g. 'admin', 'dispatcher', 'transport_admin')",
    )
    can_manage_drivers = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Can verify/reject/suspend drivers",
    )
    can_manage_vehicles = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Can create/edit/delete vehicles",
    )
    can_view_dashboard = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Can view transport dashboard",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether the permission is currently active",
    )
    granted_by_user_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="User who granted this permission (for audit)",
    )
    granted_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="When the permission was granted",
    )
    expires_at = Column(
        DateTime,
        nullable=True,
        comment="When it auto-revokes (NULL = never expires)",
    )

    __table_args__ = (
        UniqueConstraint("grantee_user_id", "grantee_role", name="uq_tp_grantee_role"),
    )

    def __repr__(self) -> str:
        return (
            f"<TransportPermission id={self.id} "
            f"grantee_user_id={self.grantee_user_id} "
            f"grantee_role={self.grantee_role!r} "
            f"active={self.is_active}>"
        )

    # --- Business Logic ---

    def is_expired(self) -> bool:
        """Check if this permission has expired."""
        if self.expires_at is None:
            return False
        now = datetime.now(timezone.utc)
        return now > self.expires_at

    def is_valid(self) -> bool:
        """Check if this permission is active and not expired."""
        return self.is_active and not self.is_expired()

    @classmethod
    def get_active_by_user(cls, user_id: int) -> list:
        """Get all active (non-expired) permissions for a user."""
        from sqlalchemy import and_

        query = cls.query.filter(
            and_(
                cls.grantee_user_id == user_id,
                cls.is_active == True,
            )
        )
        # Filter out expired permissions (where expires_at is set and in the past)
        query = query.filter(
            (cls.expires_at.is_(None)) | (cls.expires_at > datetime.now(timezone.utc))
        )
        return query.all()

    @classmethod
    def grant_permission(
        cls,
        grantee_user_id: int,
        grantee_role: str,
        can_manage_drivers: bool = False,
        can_manage_vehicles: bool = False,
        can_view_dashboard: bool = False,
        granted_by_user_id: int = None,
        expires_at: Optional[datetime] = None,
    ) -> "TransportPermission":
        """
        Grant a transport permission (idempotent - creates or updates).

        Args:
            grantee_user_id: User receiving the permission
            grantee_role: Role name (e.g. "admin")
            can_manage_drivers: Grant driver management
            can_manage_vehicles: Grant vehicle management
            can_view_dashboard: Grant dashboard view access
            granted_by_user_id: User granting the permission (the owner/super_admin)
            expires_at: Optional expiry datetime

        Returns:
            TransportPermission record
        """
        # Check if an active permission already exists for this grantee+role
        existing = cls.query.filter_by(
            grantee_user_id=grantee_user_id,
            grantee_role=grantee_role,
            is_active=True,
        ).first()

        if existing:
            # Update existing permission (idempotent)
            existing.can_manage_drivers = can_manage_drivers
            existing.can_manage_vehicles = can_manage_vehicles
            existing.can_view_dashboard = can_view_dashboard
            existing.granted_by_user_id = granted_by_user_id
            existing.granted_at = datetime.now(timezone.utc)
            existing.expires_at = expires_at
            existing.is_active = True
            db.session.add(existing)
            db.session.commit()
            return existing
        else:
            # Create new permission
            perm = cls(
                grantee_user_id=grantee_user_id,
                grantee_role=grantee_role,
                can_manage_drivers=can_manage_drivers,
                can_manage_vehicles=can_manage_vehicles,
                can_view_dashboard=can_view_dashboard,
                granted_by_user_id=granted_by_user_id,
                expires_at=expires_at,
                is_active=True,
                granted_at=datetime.now(timezone.utc),
            )
            db.session.add(perm)
            db.session.commit()
            return perm

    @classmethod
    def revoke_permission(cls, permission_id: int) -> bool:
        """
        Revoke a transport permission by setting is_active=False.

        Args:
            permission_id: The permission record ID

        Returns:
            True if revoked, False if not found
        """
        perm = cls.query.get(permission_id)
        if not perm:
            return False

        perm.is_active = False
        db.session.add(perm)
        db.session.commit()
        return True

    @classmethod
    def purge_expired(cls) -> int:
        """
        Auto-revoke all expired permissions.

        Runs as a daily Celery task. Sets is_active=False for all
        permissions where expires_at < now.

        Returns:
            Number of permissions revoked
        """
        from sqlalchemy import and_

        count = cls.query.filter(
            and_(
                cls.is_active == True,
                cls.expires_at < datetime.now(timezone.utc),
            )
        ).update({"is_active": False}, synchronize_session=False)
        db.session.commit()
        return count