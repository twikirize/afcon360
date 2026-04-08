# app/identity/models/organisation.py
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Date, BigInteger, ForeignKey, Enum,
    UniqueConstraint, Index, JSON,select, event
)
from sqlalchemy.orm import relationship
from app.extensions import db


# -------------------------------
# Organisation Core Identity
# -------------------------------
class Organisation(db.Model):
    """
    Global-grade organisation identity authority.
    Africa-first, regulator-ready, payment-safe.
    """
    __allow_unmapped__ = True
    __tablename__ = "organisations"
    __table_args__ = (
        UniqueConstraint("org_id", name="uq_org_id"),
        UniqueConstraint("country", "tax_id", name="uq_org_country_tax"),
        UniqueConstraint("country", "vat_number", name="uq_org_country_vat"),
        Index("ix_org_is_deleted_is_active", "is_deleted", "is_active"),
        Index("ix_org_is_operational", "is_operational"),
        Index("ix_org_verification_status_country", "verification_status", "country"),
    )

    # -------------------
    # Core Identifiers
    # -------------------
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    org_id = Column(String(64), unique=True, nullable=False, index=True)

    # -------------------
    # Legal Jurisdiction
    # -------------------
    country = Column(String(2), nullable=False, index=True)   # ISO 3166-1
    region = Column(String(64), index=True)                   # State / Province

    # -------------------
    # Legal Identity
    # -------------------
    legal_name = Column(String(255), nullable=False, index=True)
    org_type = Column(String(128), index=True)
    registration_no = Column(String(128), index=True)

    # -------------------
    # Compliance IDs
    # -------------------
    tax_id = Column(String(64), index=True)
    vat_number = Column(String(64), index=True)

    # -------------------
    # Verification
    # -------------------
    verification_status = Column(
        Enum("unverified", "pending", "verified", "rejected", "suspended", "expired", name="org_verification_status"),
        default="unverified",
        nullable=False,
        index=True
    )
    verification_scope = Column(JSON, nullable=False, default=dict)
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(String(128), nullable=True)

    # -------------------
    # Lifecycle
    # -------------------
    lifecycle_state = Column(
        Enum("draft", "registered", "approved", "suspended", "closed", name="org_lifecycle_state"),
        default="registered",
        nullable=False,
        index=True
    )
    is_operational = Column(Boolean, default=False, nullable=False, index=True)

    # -------------------
    # Ownership / Control
    # -------------------
    primary_contact_user_id = Column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_orgs_primary_contact_user_id"
        ),
        nullable=True,
        index=True
    )

    # -------------------
    # Classification
    # -------------------
    industry_code = Column(String(32), index=True)
    business_category = Column(
        Enum("merchant", "service_provider", "marketplace_seller", "non_profit", name="org_business_category"),
        index=True
    )

    # -------------------
    # Contact Info
    # -------------------
    contact_email = Column(String(255), index=True)
    contact_phone = Column(String(32), index=True)
    headquarters_address = Column(Text)
    website = Column(String(255))

    # -------------------
    # Data Residency
    # -------------------
    data_residency_country = Column(String(2), index=True)

    # -------------------
    # Flexible Metadata
    # -------------------
    meta = Column(JSON, nullable=False, default=lambda: {
        "preferred_payment_methods": [],
        "default_currency": None,
        "kyb_provider_id": None,
        "risk_score": None,
        "payment_verified": False,
    })

    # -------------------
    # Lifecycle Flags
    # -------------------
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, index=True)

    # -------------------
    # Audit
    # -------------------
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # -------------------
    # Relationships
    # -------------------
    users = relationship("OrganisationMember", back_populates="organisation", cascade="all, delete-orphan")
    wallet = relationship("Wallet", back_populates="organisation", uselist=False)
    licenses = relationship("OrganisationLicense", back_populates="organisation", cascade="all, delete-orphan")
    documents = relationship("OrganisationDocument", back_populates="organisation", cascade="all, delete-orphan")
    audit_logs = relationship("OrganisationAuditLog", back_populates="organisation", cascade="all, delete-orphan")
    verifications = relationship("OrganisationVerification", back_populates="organisation",
                                 cascade="all, delete-orphan")
    kyb_checks = relationship("OrganisationKYBCheck", back_populates="organisation", cascade="all, delete-orphan")
    ubos = relationship("OrganisationUBO", back_populates="organisation", cascade="all, delete-orphan")
    kyb_documents = relationship("OrganisationKYBDocument", back_populates="organisation", cascade="all, delete-orphan",
                                 foreign_keys="[OrganisationKYBDocument.organisation_id]")
    controllers = relationship("OrganisationController", back_populates="organisation", cascade="all, delete-orphan")
    default_users = relationship("User", foreign_keys="User.default_org_id", back_populates="default_org")
    primary_contact_user = relationship("User", foreign_keys=[primary_contact_user_id])
    custom_roles = relationship("OrgRole", back_populates="organisation", cascade="all, delete-orphan")

    # -------------------
    # Methods
    # -------------------
    def __repr__(self):
        return f"<Organisation {self.org_id} {self.legal_name}>"

    def soft_delete(self):
        self.is_deleted = True
        self.is_active = False
        self.deleted_at = datetime.utcnow()

    def restore(self):
        self.is_deleted = False
        self.is_active = True
        self.deleted_at = None

    def update_operational_status(self):
        """Update `is_operational` based on verification, documents, licenses."""
        docs_verified = all(doc.verification_status == "verified" and (not doc.expires_at or doc.expires_at >= date.today()) for doc in self.documents)
        licenses_active = all(lic.is_active and (not lic.expires_at or lic.expires_at >= date.today()) for lic in self.licenses)
        self.is_operational = docs_verified and licenses_active and self.verification_status == "verified"

    def is_fully_verified(self):
        latest = max(self.verifications, key=lambda v: v.requested_at, default=None)
        return latest and latest.status == "verified" and (
            not latest.expires_at or latest.expires_at >= datetime.utcnow()
        )

    def has_partial_verification(self):
        latest = max(self.verifications, key=lambda v: v.requested_at, default=None)
        return latest and latest.status in ["pending", "manual_review"]

    @property
    def has_expired_license(self):
        return any(lic.expires_at and lic.expires_at < date.today() for lic in self.licenses)

    @property
    def has_expired_document(self):
        return any(doc.expires_at and doc.expires_at < date.today() for doc in self.documents)

# -------------------------------
# Organisation Duplicates
# -------------------------------
def check_org_duplicates(connection, target, is_update=False):
    orgs_table = Organisation.__table__

    # Check duplicate legal name
    duplicate_name = connection.execute(
        select(orgs_table.c.id).where(orgs_table.c.legal_name == target.legal_name)
    ).first()
    if duplicate_name and not is_update:
        raise ValueError("Duplicate organisation legal name found")

    # Check duplicate contact email
    if target.contact_email:
        duplicate_email = connection.execute(
            select(orgs_table.c.id).where(orgs_table.c.contact_email == target.contact_email)
        ).first()
        if duplicate_email and not is_update:
            raise ValueError("Duplicate organisation contact email found")


@event.listens_for(Organisation, "before_insert")
def organisation_before_insert(mapper, connection, target):
    check_org_duplicates(connection, target, is_update=False)

@event.listens_for(Organisation, "before_update")
def organisation_before_update(mapper, connection, target):
    check_org_duplicates(connection, target, is_update=True)
