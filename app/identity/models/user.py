# app/identity/user.py

from datetime import datetime, timedelta
import uuid as uuid_lib
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, ForeignKey, JSON,
    Index, UniqueConstraint, event, select
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, validates
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models.base import ProtectedModel
from flask_login import UserMixin
from flask import current_app
# KycRecord is imported via string reference in the relationship
# No direct import to avoid circular imports


# --------------------------------------
# User Model (Core Identity)
# --------------------------------------
class User(UserMixin, ProtectedModel):
    """
    Enterprise user with Dual ID System:
    - id:        BIGINT (internal, for database relations/Foreign Keys and joins only — never expose)
    - public_id: String(64) UUID (external, for APIs/URLs/Flask-Login sessions)
    # Rule: if a human sees it → public_id. If only DB sees it → id
    """
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_user_email"),
        UniqueConstraint("phone", name="uq_user_phone"),
        Index("ix_user_email", "email"),
        Index("ix_user_phone", "phone"),
        Index("ix_user_is_deleted", "is_deleted"),
        Index("ix_user_public_id", "public_id"),
    )

    # EXTERNAL ID (UUID) — Use for ALL public exposure, URLs, Flask-Login sessions
    public_id = Column(
        String(64), unique=True, nullable=False, index=True,
        default=lambda: str(uuid_lib.uuid4())
    )

    username = Column(String(80), nullable=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(32), unique=True, nullable=True, index=True)
    password_hash = Column(String(512), nullable=False)
    password_changed_at = Column(DateTime, nullable=True)
    password_expires_at = Column(DateTime, nullable=True)

    # Lifecycle flags
    is_verified = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    mfa_enabled = Column(Boolean, default=False, nullable=False)

    # KYC / login state
    kyc_level = Column(BigInteger, default=0, nullable=False)
    failed_logins = Column(BigInteger, default=0, nullable=False)

    # Default organisation — use_alter=True prevents circular dependency on table creation
    default_org_id = Column(
        BigInteger,
        ForeignKey(
            "organisations.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_users_default_org_id"
        ),
        nullable=True,
        index=True
    )

    # ---------------------------
    # Relationships
    # ---------------------------
    profile = relationship(
        "UserProfile",
        primaryjoin="foreign(UserProfile.user_id) == User.public_id",
        back_populates="user",
        uselist=False
    )
    default_org = relationship(
        "Organisation",
        foreign_keys=[default_org_id],
        back_populates="default_users",
        lazy="joined"
    )
    organisations = relationship(
        "OrganisationMember", back_populates="user", cascade="all, delete-orphan"
    )
    roles = relationship(
        "UserRole", back_populates="user",
        cascade="all, delete-orphan", foreign_keys="UserRole.user_id",
        lazy="joined"  # ← add this
    )

    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    mfa_secrets = relationship("MFASecret", back_populates="user", cascade="all, delete-orphan")
    kyc_records = relationship(
        "KycRecord",                        # String reference to avoid circular imports
        foreign_keys="[KycRecord.user_id]",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    verifications = relationship(
        "IndividualVerification",           # Short name — safer than full module path
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="IndividualVerification.user_id"
    )
    documents = relationship(
        "IndividualKYCDocument", back_populates="user", cascade="all, delete-orphan"
    )
    wallet = relationship("Wallet", back_populates="user", uselist=False)
    controllers = relationship(
        "OrganisationController",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="[OrganisationController.user_id]"
    )

    # ---------------------------
    # Dual ID Helpers
    # ---------------------------
    @property
    def external_id(self):
        """Use for URLs, APIs, any public exposure."""
        return self.public_id

    @property
    def private_id(self):
        """Use for internal database relations only."""
        return self.id

    def get_id_for_fk(self):
        """Explicit helper — foreign key usage (internal BIGINT)."""
        return self.id

    def get_id_for_url(self):
        """Explicit helper — URL/public usage (UUID string)."""
        return self.public_id

    @classmethod
    def get_by_public_id(cls, public_uuid: str):
        """Find user by public UUID — use this in all API endpoints."""
        return cls.query.filter_by(public_id=public_uuid).first()

    @classmethod
    def get_by_private_id(cls, internal_id: int):
        """Find user by internal BIGINT — use this for DB-only operations."""
        return cls.query.get(internal_id)

    # ---------------------------
    # Flask-Login integration
    # ---------------------------
    def get_id(self):
        """
        Returns public_id (UUID string) for Flask-Login session tracking.
        Flask-Login will store and reload using this value, so it must
        match what user_loader queries on — query by public_id, NOT by id.

        Ensure your user_loader looks like:
            @login_manager.user_loader
            def load_user(public_id):
                return User.get_by_public_id(public_id)
        """
        return str(self.public_id)

    # ---------------------------
    # Password helpers
    # ---------------------------
    def set_password(self, password: str, changed_by_user_id: int = None):
        # Audit password change
        from app.audit.comprehensive_audit import AuditService, DataChangeLog
        from flask import request

        old_hash = self.password_hash

        self.password_hash = generate_password_hash(password)
        self.password_changed_at = datetime.utcnow()
        self.password_expires_at = datetime.utcnow() + timedelta(days=90)

        # Log the password change
        try:
            AuditService.data_change(
                entity_type="user",
                entity_id=self.id,
                operation="password_change",
                old_value={"password_changed_at": str(self.password_changed_at)},
                new_value={"password_changed_at": str(datetime.utcnow())},
                changed_by=changed_by_user_id or self.id,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "password_changed": True,
                    "changed_by_self": changed_by_user_id is None or changed_by_user_id == self.id
                }
            )
        except Exception as e:
            # Don't fail password change if audit fails
            import logging
            logging.error(f"Failed to audit password change: {e}")

    def verify_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # ---------------------------
    # Login helpers
    # ---------------------------
    def record_failed_login(self, session):
        self.failed_logins += 1
        if self.failed_logins >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=15)
        session.add(self)

    def reset_failed_login(self, session):
        self.failed_logins = 0
        self.locked_until = None
        session.add(self)

    def is_locked(self):
        return self.locked_until and datetime.utcnow() < self.locked_until

    def requires_mfa(self):
        return current_app.config.get("ENABLE_MFA", False) and self.mfa_enabled

    # ---------------------------
    # Compliance helpers
    # ---------------------------
    def is_fully_verified(self):
        latest = max(self.verifications, key=lambda v: v.requested_at, default=None)
        return latest and latest.status == "verified" and (
            not latest.expires_at or latest.expires_at >= datetime.utcnow()
        )

    def has_partial_verification(self):
        latest = max(self.verifications, key=lambda v: v.requested_at, default=None)
        return latest and latest.status in ["pending", "manual_review"]

    @property
    def role_names(self) -> list[str]:
        return [ur.role.name for ur in self.roles if ur.role]

    def is_app_owner(self) -> bool:
        return "owner" in self.role_names

    def is_super_admin(self) -> bool:
        return self.is_app_owner() or "super_admin" in self.role_names

    def has_global_role(self, *role_names: str) -> bool:
        try:
            if self.is_app_owner():
                return True
            return any(rn in role_names for rn in self.role_names)
        except Exception as e:
            current_app.logger.error(f"RBAC Error for user {self.id}: {e}")
            return False

    # ---------------------------
    # Organisation role helpers
    # ---------------------------
    def has_org_role(self, org_id: int, *role_names: str) -> bool:
        for membership in self.organisations:
            if membership.organisation_id != org_id:
                continue
            for our in membership.roles:
                if our.role.name in role_names:
                    return True
        return False

    def is_org_owner(self, org_id: int) -> bool:
        return self.has_org_role(org_id, "org_owner")

    def has_org_permission(self, org_id: int, permission: str) -> bool:
        if self.is_org_owner(org_id):
            return True
        ROLE_PERMISSION_MAP = {
            "org_admin": {"manage_members", "manage_resources"},
            "org_moderator": {"manage_members"},
        }
        for membership in self.organisations:
            if membership.organisation_id != org_id:
                continue
            for our in membership.roles:
                perms = ROLE_PERMISSION_MAP.get(our.role.name, set())
                if permission in perms:
                    return True
        return False

    # ---------------------------
    # Organization Audit helpers
    # ---------------------------
    @staticmethod
    def audit_org_member_added(org_id: int, user_id: int, added_by: int, role_names: list):
        """Audit organization member addition"""
        from app.audit.comprehensive_audit import AuditService
        from flask import request

        try:
            AuditService.data_change(
                entity_type="organisation_member",
                entity_id=f"{org_id}-{user_id}",
                operation="add",
                old_value=None,
                new_value={
                    "organisation_id": org_id,
                    "user_id": user_id,
                    "roles": role_names
                },
                changed_by=added_by,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "added_by": added_by,
                    "role_names": role_names
                }
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to audit organization member addition: {e}")

    @staticmethod
    def audit_org_member_removed(org_id: int, user_id: int, removed_by: int, reason: str = None):
        """Audit organization member removal"""
        from app.audit.comprehensive_audit import AuditService
        from flask import request

        try:
            AuditService.data_change(
                entity_type="organisation_member",
                entity_id=f"{org_id}-{user_id}",
                operation="remove",
                old_value={"organisation_id": org_id, "user_id": user_id},
                new_value=None,
                changed_by=removed_by,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "removed_by": removed_by,
                    "reason": reason
                }
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to audit organization member removal: {e}")

    @staticmethod
    def audit_org_role_assigned(org_id: int, user_id: int, role_name: str, assigned_by: int):
        """Audit organization role assignment"""
        from app.audit.comprehensive_audit import AuditService
        from flask import request

        try:
            AuditService.data_change(
                entity_type="organisation_role",
                entity_id=f"{org_id}-{user_id}-{role_name}",
                operation="assign",
                old_value=None,
                new_value={
                    "organisation_id": org_id,
                    "user_id": user_id,
                    "role_name": role_name
                },
                changed_by=assigned_by,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "assigned_by": assigned_by
                }
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to audit organization role assignment: {e}")

    @staticmethod
    def audit_org_role_revoked(org_id: int, user_id: int, role_name: str, revoked_by: int, reason: str = None):
        """Audit organization role revocation"""
        from app.audit.comprehensive_audit import AuditService
        from flask import request

        try:
            AuditService.data_change(
                entity_type="organisation_role",
                entity_id=f"{org_id}-{user_id}-{role_name}",
                operation="revoke",
                old_value={"organisation_id": org_id, "user_id": user_id, "role_name": role_name},
                new_value=None,
                changed_by=revoked_by,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "revoked_by": revoked_by,
                    "reason": reason
                }
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to audit organization role revocation: {e}")

    def __repr__(self):
        return (
            f"<User id={self.id} public_id={self.public_id} "
            f"username={self.username} email={self.email}>"
        )

    # ---------------------------
    # Admin Impersonation Audit
    # ---------------------------
    @staticmethod
    def audit_admin_impersonation_start(admin_id: int, target_user_id: int, reason: str = None):
        """Audit when admin starts impersonating another user"""
        from app.audit.comprehensive_audit import AuditService
        from flask import request

        try:
            AuditService.security(
                event_type="admin_impersonation_start",
                severity="WARNING",
                description=f"Admin {admin_id} started impersonating user {target_user_id}",
                user_id=admin_id,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "target_user_id": target_user_id,
                    "reason": reason,
                    "impersonation_started_at": datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to audit admin impersonation start: {e}")

    @staticmethod
    def audit_admin_impersonation_end(admin_id: int, target_user_id: int, duration_seconds: float):
        """Audit when admin stops impersonating another user"""
        from app.audit.comprehensive_audit import AuditService
        from flask import request

        try:
            AuditService.security(
                event_type="admin_impersonation_end",
                severity="INFO",
                description=f"Admin {admin_id} stopped impersonating user {target_user_id}",
                user_id=admin_id,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "target_user_id": target_user_id,
                    "duration_seconds": duration_seconds,
                    "impersonation_ended_at": datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to audit admin impersonation end: {e}")

    # ---------------------------
    # MFA Audit helpers
    # ---------------------------
    def enable_mfa(self, mfa_type: str, enabled_by_user_id: int = None):
        """Enable MFA with audit logging"""
        from app.audit.comprehensive_audit import AuditService
        from flask import request

        old_mfa_enabled = self.mfa_enabled
        self.mfa_enabled = True

        # Log MFA enablement
        try:
            AuditService.data_change(
                entity_type="user",
                entity_id=self.id,
                operation="mfa_enabled",
                old_value={"mfa_enabled": old_mfa_enabled},
                new_value={"mfa_enabled": True, "mfa_type": mfa_type},
                changed_by=enabled_by_user_id or self.id,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "mfa_type": mfa_type,
                    "enabled_by_self": enabled_by_user_id is None or enabled_by_user_id == self.id
                }
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to audit MFA enablement: {e}")

    def disable_mfa(self, disabled_by_user_id: int = None, reason: str = None):
        """Disable MFA with audit logging"""
        from app.audit.comprehensive_audit import AuditService
        from flask import request

        old_mfa_enabled = self.mfa_enabled
        self.mfa_enabled = False

        # Log MFA disablement
        try:
            AuditService.data_change(
                entity_type="user",
                entity_id=self.id,
                operation="mfa_disabled",
                old_value={"mfa_enabled": old_mfa_enabled},
                new_value={"mfa_enabled": False},
                changed_by=disabled_by_user_id or self.id,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "reason": reason,
                    "disabled_by_self": disabled_by_user_id is None or disabled_by_user_id == self.id
                }
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to audit MFA disablement: {e}")

    # ---------------------------
    # Validators
    # ---------------------------
    @validates("email")
    def validate_email(self, key, email):
        if email and not isinstance(email, str):
            raise ValueError("Email must be a string")

        new_email = email.strip().lower() if email else email

        # Audit email change if it's different
        if hasattr(self, 'email') and self.email and new_email != self.email:
            from app.audit.comprehensive_audit import AuditService
            from flask import request

            try:
                AuditService.data_change(
                    entity_type="user",
                    entity_id=self.id,
                    operation="email_change",
                    old_value={"email": self.email},
                    new_value={"email": new_email},
                    changed_by=self.id,
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request and request.user_agent else None,
                    extra_data={"email_changed": True}
                )
            except Exception as e:
                import logging
                logging.error(f"Failed to audit email change: {e}")

        return new_email

    @validates("phone")
    def validate_phone(self, key, phone):
        if phone and not isinstance(phone, str):
            raise ValueError("Phone must be a string")

        new_phone = phone.strip().replace(" ", "") if phone else phone

        # Audit phone change if it's different
        if hasattr(self, 'phone') and self.phone and new_phone != self.phone:
            from app.audit.comprehensive_audit import AuditService
            from flask import request

            try:
                AuditService.data_change(
                    entity_type="user",
                    entity_id=self.id,
                    operation="phone_change",
                    old_value={"phone": self.phone},
                    new_value={"phone": new_phone},
                    changed_by=self.id,
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.user_agent.string if request and request.user_agent else None,
                    extra_data={"phone_changed": True}
                )
            except Exception as e:
                import logging
                logging.error(f"Failed to audit phone change: {e}")

        return new_phone


# ---------------------------
# Duplicate Check (pre-DB)
# ---------------------------
def check_user_duplicates(connection, target, is_update=False):
    """
    Pre-flight uniqueness check before insert/update.

    The DB UniqueConstraints are the final safety net (and handle race conditions).
    This function catches duplicates early to give friendlier error messages.

    For updates: excludes the current record's own id so a user can save
    without changing their email/phone and not trigger a false positive.
    """
    users_table = User.__table__

    def verify(column, value, label):
        if not value:
            return
        query = select(users_table.c.id).where(column == value)
        if is_update and target.id:
            # Exclude the current record — don't flag a user's own existing values
            query = query.where(users_table.c.id != target.id)
        result = connection.execute(query).first()
        if result:
            raise ValueError(f"Duplicate {label} found: {value}")

    verify(users_table.c.email,     target.email,     "email")
    verify(users_table.c.username,  target.username,  "username")
    verify(users_table.c.phone,     target.phone,     "phone")
    verify(users_table.c.public_id, target.public_id, "public_id")


@event.listens_for(User, "before_insert")
def user_before_insert(mapper, connection, target):
    if not target.public_id:
        target.public_id = str(uuid_lib.uuid4())
    check_user_duplicates(connection, target, is_update=False)


@event.listens_for(User, "before_update")
def user_before_update(mapper, connection, target):
    check_user_duplicates(connection, target, is_update=True)


# --------------------------------------
# UserRole
# --------------------------------------
class UserRole(ProtectedModel):
    __tablename__ = "user_roles"

    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    role_id = Column(
        BigInteger, ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    assigned_by = Column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship(
        "User", foreign_keys=[user_id], back_populates="roles", lazy="joined"
    )
    assigned_by_user = relationship("User", foreign_keys=[assigned_by], lazy="joined")
    role = relationship("Role", foreign_keys=[role_id], back_populates="user_roles", lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )

    def __repr__(self):
        return f"<UserRole user_id={self.user_id} role_id={self.role_id}>"


# --------------------------------------
# MFASecret
# --------------------------------------
class MFASecret(ProtectedModel):
    __tablename__ = "mfa_secrets"

    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    mfa_type = Column(String(32), nullable=False, index=True)
    secret = Column(String(1024), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    user = relationship("User", back_populates="mfa_secrets", lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "mfa_type", name="uq_mfa_user_type"),
    )

    @validates("mfa_type")
    def validate_type(self, key, value):
        allowed = ("totp", "sms", "webauthn")
        if value not in allowed:
            raise ValueError(f"mfa_type must be one of {allowed}")
        return value

    def __repr__(self):
        return f"<MFASecret user_id={self.user_id} type={self.mfa_type}>"


# --------------------------------------
# Session
# --------------------------------------
class Session(ProtectedModel):
    __tablename__ = "sessions"

    session_id = Column(String(128), unique=True, nullable=False, index=True)
    user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    device_id = Column(String(128), index=True)
    ip = Column(String(64), index=True)
    user_agent = Column(String(512))
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    revoked_reason = Column(String(255))

    user = relationship("User", back_populates="sessions", lazy="joined")

    def __repr__(self):
        return f"<Session id={self.id} user_id={self.user_id}>"


# --------------------------------------
# APIKey
# --------------------------------------
class APIKey(ProtectedModel):
    __tablename__ = "api_keys"

    key_id = Column(String(64), nullable=False, index=True)
    key_hash = Column(String(512), nullable=False)
    owner_type = Column(String(32), nullable=False, index=True)
    owner_id = Column(BigInteger, nullable=False, index=True)
    scopes = Column(JSON, nullable=False, default=dict)
    revoked_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("key_id", "owner_type", name="uq_apikey_keyid_ownertype"),
        Index("ix_apikey_owner_type_owner_id", "owner_type", "owner_id"),
    )

    def __repr__(self):
        return f"<APIKey key_id={self.key_id} owner_type={self.owner_type}>"

    @classmethod
    def create_with_audit(cls, key_id: str, key_hash: str, owner_type: str, owner_id: int,
                         scopes: dict, created_by: int = None):
        """Create API key with audit logging"""
        from app.audit.comprehensive_audit import AuditService
        from flask import request

        api_key = cls(
            key_id=key_id,
            key_hash=key_hash,
            owner_type=owner_type,
            owner_id=owner_id,
            scopes=scopes
        )

        # Log API key creation
        try:
            AuditService.data_change(
                entity_type="api_key",
                entity_id=key_id,
                operation="create",
                old_value=None,
                new_value={
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "scopes": scopes
                },
                changed_by=created_by or owner_id,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "key_id": key_id,
                    "created_by_self": created_by is None or created_by == owner_id
                }
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to audit API key creation: {e}")

        return api_key

    def revoke_with_audit(self, revoked_by: int = None, reason: str = None):
        """Revoke API key with audit logging"""
        from app.audit.comprehensive_audit import AuditService
        from flask import request

        old_revoked_at = self.revoked_at
        self.revoked_at = datetime.utcnow()

        # Log API key revocation
        try:
            AuditService.data_change(
                entity_type="api_key",
                entity_id=self.key_id,
                operation="revoke",
                old_value={"revoked_at": old_revoked_at},
                new_value={"revoked_at": self.revoked_at.isoformat()},
                changed_by=revoked_by or self.owner_id,
                ip_address=request.remote_addr if request else None,
                user_agent=request.user_agent.string if request and request.user_agent else None,
                extra_data={
                    "reason": reason,
                    "owner_type": self.owner_type,
                    "owner_id": self.owner_id,
                    "revoked_by_self": revoked_by is None or revoked_by == self.owner_id
                }
            )
        except Exception as e:
            import logging
            logging.error(f"Failed to audit API key revocation: {e}")
