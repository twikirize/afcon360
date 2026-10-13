# app/identity/models/organisation.py
from datetime import datetime, timezone, date
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Date, BigInteger, ForeignKey,
    UniqueConstraint, Index, JSON, select, event, CheckConstraint
)
from sqlalchemy.orm import relationship, validates
from app.extensions import db
from app.models.base import BaseModel
from app.identity.models.organization_types import OrganizationType, get_organization_capabilities
from app.utils.enums import (
    OrgVerificationStatus,
    OrgLifecycleState,
    OrgKybCheckType,
    OrgKybCheckStatus,
    UboType,
    KybDocStatus,
    IndVerificationStatus,
    IndDocumentType,
    DocVerificationStatus,
    OrgChangeType,
    OrgChangeSource,
    EntityType,
    ComplianceDecision,
    RiskTier,
    ComplianceEnforcementLevel,
    PaymentGatewayProvider,
    PaymentGatewayEnvironment,
)


# -------------------------------
# Organisation Core Identity
# -------------------------------
class Organisation(BaseModel):
    """
    Global-grade organisation identity authority.
    Africa-first, regulator-ready, payment-safe.
    """
    __allow_unmapped__ = True
    __tablename__ = "organisations"
    __table_args__ = (
        UniqueConstraint("org_id", name="uq_org_id"),
        UniqueConstraint("slug", name="uq_org_slug"),
        UniqueConstraint("country", "tax_id", name="uq_org_country_tax"),
        UniqueConstraint("country", "vat_number", name="uq_org_country_vat"),
        Index("ix_org_is_deleted_is_active", "is_deleted", "is_active"),
        Index("ix_org_is_operational", "is_operational"),
        Index("ix_org_verification_status_country", "verification_status", "country"),
        Index("ix_org_slug_unique", "slug", unique=True),
        # CHECK constraints for enum-like columns
        CheckConstraint(OrgVerificationStatus.check_constraint(), name="ck_org_verification_status"),
        CheckConstraint(OrgLifecycleState.check_constraint(), name="ck_org_lifecycle_state"),
    )

    # -------------------
    # Core Identifiers
    # -------------------
    org_id = Column(String(64), unique=True, nullable=False, index=True)

    # Browser-facing routing identifier. Human-readable, unique, stable.
    # Generated from the first two meaningful words of ``legal_name`` at
    # creation (see organisation_slug). Never used for authorization.
    slug = Column(String(120), nullable=False)

    # -------------------
    # Legal Jurisdiction
    # -------------------
    country = Column(String(2), nullable=False)   # ISO 3166-1
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
    # Use String + CHECK constraint instead of PostgreSQL ENUM
    verification_status = Column(
        String(20),
        default=OrgVerificationStatus.UNVERIFIED.value,
        nullable=False,
        index=True
    )
    verification_scope = Column(JSON, nullable=False, default=dict)
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(String(128), nullable=True)

    # Internal moderation notes (separate from verification notes which go to org)
    moderation_notes = Column(Text, nullable=True)

    # -------------------
    # Compliance Integration (KYB)
    # -------------------
    # Break the organisations <-> compliance_cases cycle:
    # compliance_cases.organisation_id also references organisations, so a normal
    # (immediate) FK on this side makes the two tables un-sortable for Alembic
    # (SAWarning: unresolvable cycles). use_alter=True defers DDL emission for
    # this FK so Alembic can compute a valid table creation order, while
    # deferrable=True keeps runtime in-transaction insert ordering unchanged.
    compliance_case_id = Column(
        BigInteger,
        ForeignKey(
            "compliance_cases.id",
            use_alter=True,
            deferrable=True,
            initially="deferred",
        ),
        nullable=True,
        index=True,
    )
    compliance_status = Column(String(50), nullable=True, index=True)  # pending, approved, rejected, escalated
    compliance_notes = Column(Text, nullable=True)
    compliance_reviewed_at = Column(DateTime, nullable=True)
    compliance_reviewed_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    referred_to_compliance = Column(Boolean, default=False, nullable=False, index=True)
    referred_at = Column(DateTime, nullable=True)
    referred_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)

    # -------------------
    # Lifecycle
    # -------------------
    # Use String + CHECK constraint instead of PostgreSQL ENUM
    lifecycle_state = Column(
        String(20),
        default=OrgLifecycleState.REGISTERED.value,
        nullable=False,
        index=True
    )
    is_operational = Column(Boolean, default=False, nullable=False, )

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
    # Canonical type from the frozen classification catalogue
    # (organisation_types.code — 1:1 with OrganizationType values). This is the
    # write target for new organisations, resolved via
    # get_effective_org_type(). Do NOT add an organisation_type_id — the
    # catalogue code is the public contract.
    organisation_type_code = Column(
        String(40),
        ForeignKey("organisation_types.code"),
        nullable=True,
        index=True,
    )
    industry_code = Column(String(32), index=True)
    # LEGACY / RETIRE AFTER COMPATIBILITY VERIFICATION: kept as a read
    # fallback for organisations created before organisation_type_code existed.
    # New organisations no longer write this column.
    # Use String + CHECK constraint instead of PostgreSQL ENUM
    business_category = Column(String(40), index=True)

    # Organization-specific settings
    org_settings = Column(JSON, nullable=False, default=dict)  # Store org-specific configurations

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
    is_active = Column(Boolean, default=True, nullable=False)

    # -------------------
    # Relationships
    # -------------------
    users = relationship("OrganisationMember", back_populates="organisation", cascade="all, delete-orphan")
    licenses = relationship("OrganisationLicense", back_populates="organisation", cascade="all, delete-orphan")
    documents = relationship("OrganisationDocument", back_populates="organisation", cascade="all, delete-orphan")
    audit_logs = relationship("OrganisationAuditLog", back_populates="organisation", cascade="all, delete-orphan")
    verifications = relationship("OrganisationVerification", back_populates="organisation",
                                 cascade="all, delete-orphan")
    kyb_checks = relationship("OrganisationKYBCheck", back_populates="organisation", cascade="all, delete-orphan")
    ubos = relationship("OrganisationUBO", back_populates="organisation", cascade="all, delete-orphan")
    kyb_documents = relationship("OrganisationKYBDocument", back_populates="organisation", cascade="all, delete-orphan",
                                 foreign_keys="[OrganisationKYBDocument.organisation_id]")
    # Inverse of User.default_org (User.default_org_id -> organisations.id).
    # Restored from 1847e67: User.default_org declares back_populates="default_users".
    controllers = relationship("OrganisationController", back_populates="organisation", cascade="all, delete-orphan")
    default_users = relationship("User", foreign_keys="User.default_org_id", back_populates="default_org")
    custom_roles = relationship("OrgRole", back_populates="organisation", cascade="all, delete-orphan")
    # LEGACY / RETIRE AFTER COMPATIBILITY VERIFICATION (Stage 4B-3):
    # OPC-backed relationship. Production writes/reads now target
    # ProviderParticipation; this relationship is referenced only by legacy
    # OPC tests and awaits the ADR-4A-010 retirement step.
    provider_capabilities = relationship(
        "OrganisationProviderCapability",
        back_populates="organisation",
        cascade="all, delete-orphan",
        lazy="select",
    )

    @validates("verification_status")
    def validate_verification_status(self, key, status):
        if status and status not in OrgVerificationStatus.values():
            raise ValueError(f"Invalid verification_status. Must be one of: {OrgVerificationStatus.values()}")
        return status

    @validates("lifecycle_state")
    def validate_lifecycle_state(self, key, state):
        if state and state not in OrgLifecycleState.values():
            raise ValueError(f"Invalid lifecycle_state. Must be one of: {OrgLifecycleState.values()}")
        return state

    @validates("business_category")
    def validate_business_category(self, key, category):
        # This is a legacy field, validate against OrganizationType if needed
        return category