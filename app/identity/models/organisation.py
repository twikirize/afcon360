# app/identity/models/organisation.py
from datetime import datetime, timezone, date
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Date, BigInteger, ForeignKey, Enum,
    UniqueConstraint, Index, JSON,select, event
)
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel
from app.identity.models.organization_types import OrganizationType, get_organization_capabilities


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
        UniqueConstraint("country", "tax_id", name="uq_org_country_tax"),
        UniqueConstraint("country", "vat_number", name="uq_org_country_vat"),
        Index("ix_org_is_deleted_is_active", "is_deleted", "is_active"),
        Index("ix_org_is_operational", "is_operational"),
        Index("ix_org_verification_status_country", "verification_status", "country"),
    )

    # -------------------
    # Core Identifiers
    # -------------------
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

    # Internal moderation notes (separate from verification notes which go to org)
    moderation_notes = Column(Text, nullable=True)

    # -------------------
    # Compliance Integration (KYB)
    # -------------------
    compliance_case_id = Column(BigInteger, ForeignKey("compliance_cases.id"), nullable=True, index=True)
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
        Enum(OrganizationType, name="org_business_category"),
        index=True
    )
    
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
    is_active = Column(Boolean, default=True, nullable=False, index=True)

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
    controllers = relationship("OrganisationController", back_populates="organisation", cascade="all, delete-orphan")
    default_users = relationship("User", foreign_keys="User.default_org_id", back_populates="default_org")
    primary_contact_user = relationship("User", foreign_keys=[primary_contact_user_id])
    custom_roles = relationship("OrgRole", back_populates="organisation", cascade="all, delete-orphan")

    # -------------------
    # Wallet Account Relationships
    # -------------------
    accounts = relationship(
        'AccountModel',
        primaryjoin='Organisation.id == foreign(AccountModel.user_id)',
        viewonly=True,
        lazy='dynamic'
    )

    # -------------------
    # Methods
    # -------------------
    def __repr__(self):
        return f"<Organisation {self.org_id} {self.legal_name}>"

    def soft_delete(self):
        self.is_deleted = True
        self.is_active = False
        self.deleted_at = datetime.now(timezone.utc)

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
            not latest.expires_at or latest.expires_at >= datetime.now(timezone.utc)
        )

    def has_partial_verification(self):
        latest = max(self.verifications, key=lambda v: v.requested_at, default=None)
        return latest and latest.status in ["pending", "manual_review"]
    
    # -------------------
    # Organization Type Methods
    # -------------------
    
    def get_capabilities(self):
        """Get capabilities based on organization type"""
        if not self.business_category:
            return get_organization_capabilities(OrganizationType.MERCHANT)
        return get_organization_capabilities(self.business_category)
    
    def can_manage_staff(self):
        """Check if organization can manage staff"""
        return self.get_capabilities().can_manage_staff
    
    def can_create_events(self):
        """Check if organization can create events"""
        return self.get_capabilities().can_create_events
    
    def can_manage_accommodation(self):
        """Check if organization can manage accommodation"""
        return self.get_capabilities().can_manage_accommodation
    
    def can_manage_transport(self):
        """Check if organization can manage transport"""
        return self.get_capabilities().can_manage_transport
    
    def can_manage_tourism(self):
        """Check if organization can manage tourism"""
        return self.get_capabilities().can_manage_tourism
    
    def can_process_payments(self):
        """Check if organization can process payments"""
        return self.get_capabilities().can_process_payments
    
    def requires_license(self):
        """Check if organization requires license"""
        return self.get_capabilities().requires_license
    
    def requires_insurance(self):
        """Check if organization requires insurance"""
        return self.get_capabilities().requires_insurance
    
    def get_setting(self, key, default=None):
        """Get organization-specific setting"""
        return self.org_settings.get(key, default)
    
    def set_setting(self, key, value):
        """Set organization-specific setting"""
        if not self.org_settings:
            self.org_settings = {}
        self.org_settings[key] = value
    
    def get_active_modules(self):
        """Get list of active modules for this organization"""
        capabilities = self.get_capabilities()
        modules = []
        
        if capabilities.integrates_with_events:
            modules.append('events')
        if capabilities.integrates_with_accommodation:
            modules.append('accommodation')
        if capabilities.integrates_with_transport:
            modules.append('transport')
        if capabilities.integrates_with_wallet:
            modules.append('wallet')
        if capabilities.can_manage_tourism:
            modules.append('tourism')
            
        return modules

    @property
    def has_expired_license(self):
        return any(lic.expires_at and lic.expires_at < date.today() for lic in self.licenses)

    @property
    def has_expired_document(self):
        return any(doc.expires_at and doc.expires_at < date.today() for doc in self.documents)

    # -------------------
    # Wallet Account Properties
    # -------------------
    @property
    def primary_account(self):
        """Get the primary account for this organisation."""
        from app.wallet.models.ledger import AccountModel, AccountOwnerType
        return AccountModel.query.filter_by(
            user_id=self.id,
            owner_type=AccountOwnerType.ORGANISATION
        ).first()

    @property
    def wallet_balance(self):
        """Get current wallet balance (derived from ledger)."""
        account = self.primary_account
        if not account:
            from decimal import Decimal
            return Decimal('0')

        from app.wallet.services.wallet_service import WalletService
        try:
            return WalletService.get_balance(account.id)
        except Exception:
            from decimal import Decimal
            return Decimal('0')

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
