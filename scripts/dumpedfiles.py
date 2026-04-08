# app/auth/user.py

#import uuid
#from datetime import datetime
#from sqlalchemy import Column, Integer, ForeignKey, Boolean, DateTime, String
#from sqlalchemy.orm import relationship
#from app.extensions import db
#from app.models.base import TimestampMixin
#from passlib.hash import argon2
"""
def gen_uuid():
    return str(uuid.uuid4())

# -----------------------------
# User Model
# -----------------------------
class User(TimestampMixin, db.Model):
    "1""
    Application user model.
    - Soft-delete supported via is_deleted/deleted_at.
    - Role assignments are mapped via UserRole (app.identity.models.UserRole).
    - MFA secrets moved to app.identity.models.MFASecret; keep mfa_enabled flag here.
    - Sessions are exposed via Session.user backref (do NOT declare sessions relationship here).
    "1""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), unique=True, nullable=False, default=gen_uuid, index=True)

    # organisations
    # NOTE: ondelete behavior is handled in identity models; keep FK name for compatibility.
    default_org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    organizations = relationship("OrgUser", back_populates="user", lazy="select", cascade="all, delete-orphan")

    # identity
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=True, index=True)

    # auth
    password_hash = db.Column(db.String(255), nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)

    # MFA: keep enabled flag; secrets moved to MFASecret table (app.identity.models.MFASecret)
    mfa_enabled = db.Column(db.Boolean, default=False, nullable=False)

    # Soft-delete fields (new)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    deleted_at = db.Column(db.DateTime, nullable=True, index=True)

    # risk & lifecycle
    failed_logins = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # relationships
    # Use the mapped UserRole model (app/identity/user.py) for role assignments.
    # This relationship returns UserRole objects; to get Role names use user.role_names property.
    # lazy="joined" reduces N+1 for auth checks; change to "select" if you prefer fewer joins.
    roles = relationship("UserRole", back_populates="user", lazy="joined", cascade="all, delete-orphan")

    # profile and kyc
    #profile = relationship("UserProfile", uselist=False, back_populates="user", cascade="all, delete-orphan", lazy="joined")
    #kyc_records = relationship("KycRecord", back_populates="user", cascade="all, delete-orphan", lazy="select")

    # NOTE: Do NOT declare sessions relationship here. Session.user creates a backref "sessions".
    # Declaring sessions here can cause mapper ordering errors during CLI/migration runs.

    def set_password(self, password: str):
        self.password_hash = argon2.hash(password)

    def verify_password(self, password: str) -> bool:
        try:
            return argon2.verify(password, self.password_hash)
        except Exception:
            return False

    @property
    def role_names(self):
        "1""
        Convenience property: returns a list of role names for this user.
        Works whether roles are assigned via UserRole (org/global) or future mappings.
        "1""
        names = []
        for ur in getattr(self, "roles", []) or []:
            # ur is a UserRole instance; it should have .role relationship
            r = getattr(ur, "role", None)
            if r and getattr(r, "name", None):
                names.append(r.name)
        return names

    def soft_delete(self, actor_id=None):
        "1""
        Soft-delete wrapper. Delegates to app.identity.services.soft_delete_user.
        Use services to ensure related records (OrgUser, OrgUserRole, Session, APIKey, MFASecret)
        are marked inactive/revoked consistently.
        "1""
        from app.identity.services import soft_delete_user  # avoid circular import
        return soft_delete_user(self.id, actor_id=actor_id)

    def restore(self, actor_id=None):
        "1""
        Restore wrapper. Delegates to app.identity.services.restore_user.
        Restores OrgUser links but does NOT automatically re-enable sessions or API keys.
        "1""
        from app.identity.services import restore_user
        return restore_user(self.id, actor_id=actor_id)

    def __repr__(self):
        return f"<User {self.username}>"
"""
