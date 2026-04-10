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


# --------------------------------------
# User Model (Core Identity)
# --------------------------------------
class User(UserMixin, ProtectedModel):
    """
    Enterprise user with Dual ID System:
    - id: BIGINT (internal, for database relations/FKs)
    - user_id: String(64) (external, for public exposure/APIs/URLs)
    """
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_user_email"),
        UniqueConstraint("phone", name="uq_user_phone"),
        Index("ix_user_email", "email"),
        Index("ix_user_phone", "phone"),
        Index("ix_user_is_deleted", "is_deleted"),
    )

    # INTERNAL ID (BIGINT) - PK Inherited from ProtectedModel

    # EXTERNAL ID (UUID) - Use for ALL public exposure
    user_id = Column(String(64), unique=True, nullable=False, index=True, default=lambda: str(uuid_lib.uuid4()))

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

    # Default organisation
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

    # Timestamps Inherited from ProtectedModel

    # ---------------------------
    # Relationships
    # ---------------------------
    profile = relationship("UserProfile", back_populates="user", uselist=False)
    default_org = relationship(
        "Organisation",
        foreign_keys=[default_org_id],
        back_populates="default_users",
        lazy="joined"
    )
    organisations = relationship("OrganisationMember", back_populates="user", cascade="all, delete-orphan")
    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan", foreign_keys="UserRole.user_id")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    mfa_secrets = relationship("MFASecret", back_populates="user", cascade="all, delete-orphan")
    kyc_records = relationship("KycRecord", back_populates="user", cascade="all, delete-orphan")
    verifications = relationship(
        "IndividualVerification",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="[IndividualVerification.user_id]"
    )
    documents = relationship("IndividualKYCDocument", back_populates="user", cascade="all, delete-orphan")
    wallet = relationship("Wallet", back_populates="user", uselist=False)
    controllers = relationship(
        "OrganisationController",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="OrganisationController.user_id"
    )

    # ---------------------------
    # Dual ID Helpers
    # ---------------------------
    @property
    def public_id(self):
        """Use this for URLs, APIs, any public exposure"""
        return self.user_id

    @property
    def private_id(self):
        """Use this for internal database relations"""
        return self.id

    def get_id_for_fk(self):
        """Explicit method for foreign key usage"""
        return self.id

    def get_id_for_url(self):
        """Explicit method for URL/public usage"""
        return self.user_id

    @classmethod
    def get_by_public_id(cls, public_uuid):
        """Find user by public UUID (for API endpoints)"""
        return cls.query.filter_by(user_id=public_uuid).first()

    @classmethod
    def get_by_private_id(cls, internal_id):
        """Find user by internal ID (for database operations)"""
        return cls.query.get(internal_id)

    # ---------------------------
    # Flask-Login integration
    # ---------------------------
    def get_id(self):
        """Return the UUID-style user_id for session tracking (external reference)."""
        return str(self.user_id)

    # ---------------------------
    # Password helpers
    # ---------------------------
    def set_password(self, password: str):
        """Hash and store the user's password."""
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = datetime.utcnow()

        # Set password expiration (e.g., 90 days from now)
        self.password_expires_at = datetime.utcnow() + timedelta(days=90)

    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    # ---------------------------
    # Login helpers
    # ---------------------------
    def record_failed_login(self, session):
        """Increment failed login counter and apply lockout if threshold reached."""
        self.failed_logins += 1
        if self.failed_logins >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=15)
        session.add(self)

    def reset_failed_login(self, session):
        """Reset failed login counter and clear lockout."""
        self.failed_logins = 0
        self.locked_until = None
        session.add(self)

    def is_locked(self):
        """Return True if account is currently locked."""
        return self.locked_until and datetime.utcnow() < self.locked_until

    def requires_mfa(self):
        """Return True if MFA is globally enabled and user has MFA enabled."""
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
        """Return a list of all role names assigned to this user."""
        return [ur.role.name for ur in self.roles if ur.role]

    def is_app_owner(self) -> bool:
        """Return True if the user has the global 'owner' role."""
        return "owner" in self.role_names

    def is_super_admin(self) -> bool:
        """Return True if the user is owner or super_admin."""
        return self.is_app_owner() or "super_admin" in self.role_names

    def has_global_role(self, *role_names: str) -> bool:
        """Return True if the user has any of the given global roles."""
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
        """Placeholder for IAM-style policies later. For now: role-based."""
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

    def __repr__(self):
        return f"<User id={self.id} user_id={self.user_id} username={self.username} email={self.email}>"

    # ---------------------------
    # Validators
    # ---------------------------
    @validates("email")
    def validate_email(self, key, email):
        if email and not isinstance(email, str):
            raise ValueError("Email must be a string")
        return email.strip().lower() if email else email

    @validates("phone")
    def validate_phone(self, key, phone):
        if phone and not isinstance(phone, str):
            raise ValueError("Phone must be a string")
        return phone.strip().replace(" ", "") if phone else phone


# ---------------------------
# Pre-KYC Duplicate Check
# ---------------------------
def check_user_duplicates(connection, target, is_update=False):
    """Ensure email/phone/username uniqueness pre-KYC."""
    users_table = User.__table__

    # Check email
    if target.email:
        duplicate_email = connection.execute(
            select(users_table.c.id).where(users_table.c.email == target.email)
        ).first()
        if duplicate_email and not is_update:
            raise ValueError("Duplicate user email found")

    # Check username
    if target.username:
        duplicate_username = connection.execute(
            select(users_table.c.id).where(users_table.c.username == target.username)
        ).first()
        if duplicate_username and not is_update:
            raise ValueError("Duplicate username found")

    # Check phone
    if target.phone:
        duplicate_phone = connection.execute(
            select(users_table.c.id).where(users_table.c.phone == target.phone)
        ).first()
        if duplicate_phone and not is_update:
            raise ValueError("Duplicate phone number found")


@event.listens_for(User, "before_insert")
def user_before_insert(mapper, connection, target):
    if not target.user_id:
        target.user_id = str(uuid_lib.uuid4())
    check_user_duplicates(connection, target, is_update=False)

@event.listens_for(User, "before_update")
def user_before_update(mapper, connection, target):
    check_user_duplicates(connection, target, is_update=True)


# --------------------------------------
# UserRole (global role)
# --------------------------------------
class UserRole(ProtectedModel):
    __tablename__ = "user_roles"

    # id inherited from ProtectedModel
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="roles", lazy="joined")
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

    # id inherited from ProtectedModel
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mfa_type = Column(String(32), nullable=False, index=True)  # totp, sms, webauthn
    secret = Column(String(1024), nullable=False)  # encrypted
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Timestamps inherited from ProtectedModel

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

    # id inherited from ProtectedModel
    session_id = Column(String(128), unique=True, nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(128), index=True)
    ip = Column(String(64), index=True)
    user_agent = Column(String(512))

    # Timestamps inherited from ProtectedModel
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

    # id inherited from ProtectedModel
    key_id = Column(String(64), nullable=False, index=True)
    key_hash = Column(String(512), nullable=False)
    owner_type = Column(String(32), nullable=False, index=True)  # user or organisation
    owner_id = Column(BigInteger, nullable=False, index=True)
    scopes = Column(JSON, nullable=False, default=dict)

    # Timestamps inherited from ProtectedModel
    revoked_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("key_id", "owner_type", name="uq_apikey_keyid_ownertype"),
        Index("ix_apikey_owner_type_owner_id", "owner_type", "owner_id"),
    )

    def __repr__(self):
        return f"<APIKey key_id={self.key_id} owner_type={self.owner_type}>"
