from datetime import datetime, date, timezone
import re
from sqlalchemy import (
    Enum as SAEnum,
    CheckConstraint,
    UniqueConstraint,
    Index,
    Column,
    BigInteger,
    String,
    Boolean,
    DateTime,
    Date,
    Integer,
    event,
    ForeignKey,
    Text,
    JSON,
)
from sqlalchemy.orm import validates, relationship
from app.extensions import db
from app.models.base import BaseModel

# ---------------------------
# Enumerations
# ---------------------------
VERIFICATION_STATUS = ("pending", "verified", "rejected", "suspended")
KYC_LEVELS = ("basic", "enhanced", "government")
GENDERS = ("male", "female", "other", "unspecified")
ID_TYPES = ("passport", "national_id", "driver_license", "other")

# Immutable fields after verification
IMMUTABLE_AFTER_VERIFICATION = {
    "full_name", "date_of_birth", "gender", "nationality",
    "id_type", "id_number", "id_document_url", "id_document_mime", "id_document_size",
}

# ---------------------------
# UserProfile Table
# ---------------------------
class UserProfile(BaseModel):
    """
    Authoritative store for personal and KYC information.
    - Separated from User (login/auth)
    - Enforces immutability after verification
    - Validates inputs
    - Supports auditability
    - Provides safe serialization
    """
    __tablename__ = "user_profiles"
    __table_args__ = (
        # Updated constraint name to match new ID system logic
        UniqueConstraint("user_id", name="uq_userprofile_public_id"),
        UniqueConstraint("email", name="uq_userprofile_email"),  # global email uniqueness
        UniqueConstraint("phone_number", name="uq_userprofile_phone"),  # global phone uniqueness
        CheckConstraint("length(full_name) > 0", name="ck_full_name_not_empty"),
        Index("ix_userprofile_verification_kyc", "verification_status", "kyc_level"),
        Index("ix_userprofile_is_deleted", "is_deleted"),
        Index("ix_userprofile_email_phone", "email", "phone_number"),
    )

    # 🌍 External identity join
    # CRITICAL FIX: ForeignKey now points to users.public_id (the UUID string)
    user_id = Column(String(64), ForeignKey("users.public_id", ondelete="CASCADE"), nullable=False, unique=True,
                     index=True)
    user = relationship("User", back_populates="profile", uselist=False)

    # Personal info
    full_name = Column(String(128), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(SAEnum(*GENDERS, name="gender_enum"), nullable=True)
    nationality = Column(String(64), nullable=True)
    address = Column(String(256), nullable=True)
    city = Column(String(128), nullable=True)
    country = Column(String(64), nullable=True)
    phone_number = Column(String(32), nullable=True, index=True)
    email = Column(String(128), nullable=True, index=True)

    # Identity documents
    id_type = Column(SAEnum(*ID_TYPES, name="id_type_enum"), nullable=True)
    id_number = Column(String(64), nullable=True, index=True)
    id_document_url = Column(String(512), nullable=True)
    id_document_mime = Column(String(64), nullable=True)
    id_document_size = Column(Integer, nullable=True)

    # Verification & workflow
    verification_status = Column(
        SAEnum(*VERIFICATION_STATUS, name="verification_status_enum"),
        nullable=False,
        default="pending",
        index=True,
    )
    rejected_reason = Column(String(256), nullable=True)
    verified_by = Column(String(64), nullable=True)
    last_reviewed_at = Column(DateTime, nullable=True)
    kyc_level = Column(
        SAEnum(*KYC_LEVELS, name="kyc_level_enum"),
        nullable=False,
        default="basic",
        index=True,
    )

    # Flags
    email_verified = Column(Boolean, default=False, nullable=False)
    phone_verified = Column(Boolean, default=False, nullable=False)
    profile_completed = Column(Boolean, default=False, nullable=False)

    # Soft delete
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)

    # Lifecycle tracking
    suspended_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<UserProfile id={self.id} user_id={self.user_id} full_name={self.full_name}>"

    # ---------------------------
    # Serialization
    # ---------------------------
    def to_dict(self):
        """Full internal serialization."""
        data = {}
        for col in self.__table__.columns:
            val = getattr(self, col.name)
            if isinstance(val, (datetime, date)):
                data[col.name] = val.isoformat()
            else:
                data[col.name] = val
        return data

    def public_dict(self):
        """Minimal PII for external use."""
        return {
            "full_name": self.full_name,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else None,
            "gender": self.gender,
            "nationality": self.nationality,
            "phone_number": self.phone_number,
            "email": self.email,
            "verification_status": self.verification_status,
            "kyc_level": self.kyc_level,
        }

    def safe_dict(self):
        """Strict external serialization (no sensitive identity docs)."""
        return {
            "full_name": self.full_name,
            "verification_status": self.verification_status,
            "kyc_level": self.kyc_level,
        }

    def get_completion_percentage(self):
        """
        Calculate profile completion percentage based on:
        - email_verified (20%)
        - phone_verified (20%)
        - full_name (20%)
        - address (20%)
        - city (10%)
        - country (10%)
        """
        percentage = 0

        # Check each component
        if self.email_verified:
            percentage += 20
        if self.phone_verified:
            percentage += 20
        if self.full_name and len(self.full_name.strip()) > 0:
            percentage += 20
        if self.address and len(self.address.strip()) > 0:
            percentage += 20
        if self.city and len(self.city.strip()) > 0:
            percentage += 10
        if self.country and len(self.country.strip()) > 0:
            percentage += 10

        return percentage

    def get_completion_breakdown(self):
        """
        Return a dictionary with completion status for each component.
        """
        return {
            'email_verified': {
                'completed': bool(self.email_verified),
                'weight': 20,
                'label': 'Email Verified'
            },
            'phone_verified': {
                'completed': bool(self.phone_verified),
                'weight': 20,
                'label': 'Phone Verified'
            },
            'full_name': {
                'completed': bool(self.full_name and len(self.full_name.strip()) > 0),
                'weight': 20,
                'label': 'Full Name'
            },
            'address': {
                'completed': bool(self.address and len(self.address.strip()) > 0),
                'weight': 20,
                'label': 'Address'
            },
            'city': {
                'completed': bool(self.city and len(self.city.strip()) > 0),
                'weight': 10,
                'label': 'City'
            },
            'country': {
                'completed': bool(self.country and len(self.country.strip()) > 0),
                'weight': 10,
                'label': 'Country'
            }
        }

    # ---------------------------
    # Verification / Admin
    # ---------------------------
    def mark_verified(self, reviewer: str):
        self.verification_status = "verified"
        self.rejected_reason = None
        self.verified_by = reviewer
        self.last_reviewed_at = datetime.now(timezone.utc)

    def mark_rejected(self, reviewer: str, reason: str):
        if not reason:
            raise ValueError("Rejection reason is required.")
        self.verification_status = "rejected"
        self.rejected_reason = reason
        self.verified_by = reviewer
        self.last_reviewed_at = datetime.now(timezone.utc)

    def suspend_account(self):
        self.verification_status = "suspended"
        self.suspended_at = datetime.now(timezone.utc)

    def reactivate_account(self):
        self.verification_status = "pending"
        self.suspended_at = None

    def request_reverification(self, fields: list):
        allowed_fields = {"address", "phone_number", "email"}
        if any(f not in allowed_fields for f in fields):
            raise ValueError("Only address, phone, or email can trigger re-verification.")
        self.verification_status = "pending"
        self.last_reviewed_at = None

    # ---------------------------
    # Validators
    # ---------------------------
    @validates("full_name")
    def validate_full_name(self, key, name):
        return name.strip() if name else name

    @validates("date_of_birth")
    def validate_date_of_birth(self, key, dob):
        if dob:
            if dob > date.today():
                raise ValueError("date_of_birth cannot be in the future.")
            if dob.year < 1900:
                raise ValueError("date_of_birth is unrealistic.")
        return dob

    @validates("email")
    def validate_email(self, key, email):
        if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            raise ValueError("Invalid email format.")
        return email.strip().lower() if email else email

    @validates("phone_number")
    def validate_phone(self, key, phone):
        if phone and not re.match(r"^\+?\d{7,15}$", phone):
            raise ValueError("Invalid phone number format.")
        return phone.strip().replace(" ", "") if phone else phone

# ---------------------------
# Immutable change audit
# ---------------------------
class UserProfileAudit(BaseModel):
    """
    Tracks attempts to modify immutable fields after verification.
    """
    __tablename__ = "user_profile_audit"

    user_profile_id = Column(BigInteger, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name = Column(String(64), nullable=False)
    old_value = Column(Text, nullable=True)
    attempted_value = Column(Text, nullable=True)
    attempted_by_user_id = Column(BigInteger, nullable=True)

    user_profile = relationship("UserProfile", backref="audit_logs")


# ---------------------------
# Event-based immutability enforcement + audit
# ---------------------------
@event.listens_for(UserProfile, "before_update")
def enforce_immutable_after_verification(mapper, connection, target):
    if target.verification_status == "verified":
        state = db.inspect(target)
        for field in IMMUTABLE_AFTER_VERIFICATION:
            hist = state.attrs[field].history
            if hist.has_changes():
                # Log audit attempt
                connection.execute(
                    UserProfileAudit.__table__.insert().values(
                        user_profile_id=target.id,
                        field_name=field,
                        old_value=str(hist.deleted[0]) if hist.deleted else None,
                        attempted_value=str(hist.added[0]) if hist.added else None,
                        attempted_at=datetime.now(timezone.utc),
                        attempted_by_user_id=getattr(target, "_current_user_id", None),
                    )
                )

                # Log blocked attempt using Forensic Audit
                from app.audit.forensic_audit import ForensicAuditService
                ForensicAuditService.log_blocked(
                    entity_type="user_profile",
                    entity_id=str(target.id),
                    action=f"update_{field}",
                    user_id=getattr(target, "_current_user_id", None),
                    reason=f"{field} cannot be changed after verification",
                    attempted_value=str(hist.added[0]) if hist.added else None,
                    old_value=str(hist.deleted[0]) if hist.deleted else None
                )

                raise ValueError(f"{field} cannot be changed after verification.")


# ---------------------------
# Helper Functions
# ---------------------------
def get_profile_by_user(user_or_public_id):
    """
    Safe UserProfile lookup. Always use this instead of
    UserProfile.query.filter_by(user_id=...) directly.
    Accepts a User object or a public_id UUID string.
    Never accepts a raw integer.
    """
    if isinstance(user_or_public_id, int):
        raise ValueError(
            f"get_profile_by_user() received integer {user_or_public_id}. "
            f"Pass user.public_id (UUID string) or a User object, never user.id."
        )
    public_id = (
        user_or_public_id.public_id
        if hasattr(user_or_public_id, 'public_id')
        else user_or_public_id
    )
    return UserProfile.query.filter_by(user_id=public_id).first()

def calculate_profile_completion(profile):
    """
    Calculate profile completion percentage.

    Args:
        profile: UserProfile instance

    Returns:
        int: Percentage (0-100)
    """
    if not profile:
        return 0

    # Define important fields to check
    important_fields = [
        'full_name', 'date_of_birth', 'gender',
        'nationality', 'address', 'phone_number', 'email'
    ]

    completed_fields = 0
    for field in important_fields:
        value = getattr(profile, field, None)
        if value:
            completed_fields += 1

    return int((completed_fields / len(important_fields)) * 100)

if __name__ == '__main__':
    # Test that integer input is rejected
    try:
        get_profile_by_user(1)
        print("❌ FAILED — integer should have been rejected")
    except ValueError as e:
        print(f"✅ PASSED — integer correctly rejected: {e}")
