
# app/identity/models/organisation.py

import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    event,
    select,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import foreign, relationship, validates

from app.extensions import db
from app.identity.models.organization_types import (
    OrganizationCapability,
    OrganizationType,
    get_organization_capabilities,
)
from app.models.base import BaseModel
from app.utils.enums import (
    OrgVerificationStatus,
    OrgLifecycleState,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Legacy platform-role labels
#
# These values may exist in business_category but describe platform
# relationships rather than organisation classifications.
# ---------------------------------------------------------------------------

_LEGACY_ROLE_LABELS = frozenset(
    {
        "merchant",
        "service_provider",
        "marketplace_seller",
        "non_profit",
    }
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _enum_value(value):
    """Return an enum member's value or the original input."""
    return getattr(value, "value", value)


def _expiry_is_valid(expires_at, *, today=None, now=None):
    """Return whether an optional date or datetime expiry is still valid.

    A missing expiry means no expiry is recorded. DateTime values are
    compared using compatible timezone awareness. Unknown expiry types
    fail closed rather than being treated as valid.
    """
    if expires_at is None:
        return True

    if isinstance(expires_at, datetime):
        if now is None:
            reference = datetime.now(
                expires_at.tzinfo or timezone.utc
            )
        else:
            reference = now

        if expires_at.tzinfo is None:
            if reference.tzinfo is not None:
                reference = reference.replace(tzinfo=None)
        elif reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)

        return expires_at >= reference

    if isinstance(expires_at, date):
        return expires_at >= (today or date.today())

    return False


# ---------------------------------------------------------------------------
# Unclassified organisation capabilities
# ---------------------------------------------------------------------------

def _unclassified_org_capability() -> OrganizationCapability:
    """Return capabilities without granting type-derived privileges.

    An absent or invalid classification is not proof of eligibility for
    any capability or proof that a regulatory requirement applies.

    Capability grants and module integrations are denied. Compliance
    requirement flags are not used to invent universal legal obligations;
    callers must explicitly handle unresolved classification.
    """
    return OrganizationCapability(
        # Capability grants: deny.
        can_manage_staff=False,
        can_manage_wallet=False,
        can_create_events=False,
        can_manage_accommodation=False,
        can_manage_transport=False,
        can_manage_tourism=False,
        can_sell_tickets=False,
        can_process_payments=False,
        can_manage_inventory=False,
        can_provide_services=False,

        # Do not infer universal regulatory requirements.
        requires_license=False,
        requires_insurance=False,
        requires_certification=False,

        # Module integrations: disabled.
        integrates_with_events=False,
        integrates_with_accommodation=False,
        integrates_with_transport=False,
        integrates_with_wallet=False,
    )


# ---------------------------------------------------------------------------
# Organisation core identity
# ---------------------------------------------------------------------------

class Organisation(BaseModel):
    """Organisation identity, classification, verification, and lifecycle.

    Classification describes what an organisation is. It does not establish
    provider participation, platform activation, financial privileges,
    regulatory approval, or member permissions.
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
        Index(
            "ix_org_verification_status_country",
            "verification_status",
            "country",
        ),
        Index("ix_org_slug_unique", "slug", unique=True),
    )

    # -----------------------------------------------------------------------
    # Core identifiers
    # -----------------------------------------------------------------------

    org_id = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )

    # Human-readable routing identifier. Never an authorization credential.
    slug = Column(String(120), nullable=False)

    # -----------------------------------------------------------------------
    # Legal jurisdiction
    # -----------------------------------------------------------------------

    country = Column(String(2), nullable=False)
    region = Column(String(64), index=True)

    # -----------------------------------------------------------------------
    # Legal identity
    # -----------------------------------------------------------------------

    legal_name = Column(String(255), nullable=False, index=True)
    org_type = Column(String(128), index=True)
    registration_no = Column(String(128), index=True)

    # -----------------------------------------------------------------------
    # Compliance identifiers
    # -----------------------------------------------------------------------

    tax_id = Column(String(64), index=True)
    vat_number = Column(String(64), index=True)

    # -----------------------------------------------------------------------
    # Verification
    # -----------------------------------------------------------------------

    verification_status = Column(
        PgEnum(
            OrgVerificationStatus,
            name="org_verification_status",
            create_type=False,
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        default=OrgVerificationStatus.UNVERIFIED.value,
        nullable=False,
        index=True,
    )

    verification_scope = Column(
        JSON,
        nullable=False,
        default=dict,
    )

    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(String(128), nullable=True)

    moderation_notes = Column(Text, nullable=True)

    # -----------------------------------------------------------------------
    # Compliance integration (KYB)
    # -----------------------------------------------------------------------

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

    compliance_status = Column(String(50), nullable=True, index=True)
    compliance_notes = Column(Text, nullable=True)
    compliance_reviewed_at = Column(DateTime(timezone=True), nullable=True)

    compliance_reviewed_by = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )

    referred_to_compliance = Column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    referred_at = Column(DateTime(timezone=True), nullable=True)

    referred_by = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    lifecycle_state = Column(
        PgEnum(
            OrgLifecycleState,
            name="org_lifecycle_state",
            create_type=False,
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        default=OrgLifecycleState.REGISTERED.value,
        nullable=False,
        index=True,
    )

    is_operational = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    # -----------------------------------------------------------------------
    # Ownership and control
    # -----------------------------------------------------------------------

    primary_contact_user_id = Column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_orgs_primary_contact_user_id",
        ),
        nullable=True,
        index=True,
    )

    # -----------------------------------------------------------------------
    # Classification
    # -----------------------------------------------------------------------

    # Canonical classification code. organisation_types.code is the public
    # contract; this column is the canonical write target.
    organisation_type_code = Column(
        String(40),
        ForeignKey("organisation_types.code"),
        nullable=True,
        index=True,
    )

    industry_code = Column(String(32), index=True)

    # Legacy read fallback. Preserve its permissive validation for
    # backwards compatibility.
    business_category = Column(String(40), index=True)

    # -----------------------------------------------------------------------
    # Organisation settings
    # -----------------------------------------------------------------------

    org_settings = Column(
        JSON,
        nullable=False,
        default=dict,
    )

    # -----------------------------------------------------------------------
    # Contact information
    # -----------------------------------------------------------------------

    contact_email = Column(String(255), index=True)
    contact_phone = Column(String(32), index=True)
    headquarters_address = Column(Text)
    website = Column(String(255))

    # -----------------------------------------------------------------------
    # Data residency
    # -----------------------------------------------------------------------

    data_residency_country = Column(String(2), index=True)

    # -----------------------------------------------------------------------
    # Flexible metadata
    # -----------------------------------------------------------------------

    meta = Column(
        JSON,
        nullable=False,
        default=lambda: {
            "preferred_payment_methods": [],
            "default_currency": None,
            "kyb_provider_id": None,
            "risk_score": None,
            "payment_verified": False,
        },
    )

    # -----------------------------------------------------------------------
    # Lifecycle flags
    # -----------------------------------------------------------------------

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    users = relationship(
        "OrganisationMember",
        back_populates="organisation",
        cascade="all, delete-orphan",
    )

    licenses = relationship(
        "OrganisationLicense",
        back_populates="organisation",
        cascade="all, delete-orphan",
    )

    documents = relationship(
        "OrganisationDocument",
        back_populates="organisation",
        cascade="all, delete-orphan",
    )

    audit_logs = relationship(
        "OrganisationAuditLog",
        back_populates="organisation",
        cascade="all, delete-orphan",
    )

    verifications = relationship(
        "OrganisationVerification",
        back_populates="organisation",
        cascade="all, delete-orphan",
    )

    kyb_checks = relationship(
        "OrganisationKYBCheck",
        back_populates="organisation",
        cascade="all, delete-orphan",
    )

    ubos = relationship(
        "OrganisationUBO",
        back_populates="organisation",
        cascade="all, delete-orphan",
    )

    kyb_documents = relationship(
        "OrganisationKYBDocument",
        back_populates="organisation",
        cascade="all, delete-orphan",
        foreign_keys="[OrganisationKYBDocument.organisation_id]",
    )

    # Inverse of User.default_org.
    controllers = relationship(
        "OrganisationController",
        back_populates="organisation",
        cascade="all, delete-orphan",
    )

    default_users = relationship(
        "User",
        foreign_keys="User.default_org_id",
        back_populates="default_org",
    )

    custom_roles = relationship(
        "OrgRole",
        back_populates="organisation",
        cascade="all, delete-orphan",
    )

    # Legacy OPC-backed relationship retained for compatibility.
    provider_capabilities = relationship(
        "OrganisationProviderCapability",
        back_populates="organisation",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # -----------------------------------------------------------------------
    # Validators
    # -----------------------------------------------------------------------

    @validates("verification_status")
    def validate_verification_status(self, key, status):
        if status is None:
            return status

        status = _enum_value(status)

        if status not in OrgVerificationStatus.values():
            raise ValueError(
                "Invalid verification_status. Must be one of: "
                f"{OrgVerificationStatus.values()}"
            )

        return status

    @validates("lifecycle_state")
    def validate_lifecycle_state(self, key, state):
        if state is None:
            return state

        state = _enum_value(state)

        if state not in OrgLifecycleState.values():
            raise ValueError(
                "Invalid lifecycle_state. Must be one of: "
                f"{OrgLifecycleState.values()}"
            )

        return state

    @validates("business_category")
    def validate_business_category(self, key, category):
        # Legacy field: normalize OrganizationType members to their .name
        # (current application behavior for this column — distinct from the
        # lowercase .value stored in organisation_type_code and from the
        # former PostgreSQL enum's lowercase label set); leave plain strings
        # and None unchanged.
        if category is None:
            return None
        if isinstance(category, OrganizationType):
            return category.name
        return category

    @validates("organisation_type_code")
    def validate_organisation_type_code(self, key, value):
        """Normalize canonical catalogue codes.

        None and blank strings become None. Valid OrganizationType members
        and values are accepted. Invalid non-empty values raise ValueError.
        """
        if value is None:
            return None

        if isinstance(value, OrganizationType):
            return value.value

        normalized = str(value).strip().lower()

        if not normalized:
            return None

        try:
            return OrganizationType(normalized).value
        except ValueError as exc:
            raise ValueError(
                f"Invalid organisation_type_code {value!r}. "
                "Must be a valid catalogue code or None."
            ) from exc

    # -----------------------------------------------------------------------
    # Effective organisation type resolution
    # -----------------------------------------------------------------------

    @staticmethod
    def _parse_org_type(value):
        """Parse a canonical organisation type or return None."""
        raw = _enum_value(value)

        if raw is None:
            return None

        normalized = str(raw).strip().lower()

        if not normalized or normalized in _LEGACY_ROLE_LABELS:
            return None

        try:
            return OrganizationType(normalized)
        except (TypeError, ValueError):
            return None

    def has_explicit_org_type(self) -> bool:
        """Return whether a valid explicit classification is available.

        The CORPORATE compatibility fallback does not count as an explicit
        classification. An invalid non-empty canonical code must not be
        masked by a legacy business_category value.
        """
        code = (self.organisation_type_code or "").strip()

        if code:
            return self._parse_org_type(code) is not None

        return self._parse_org_type(self.business_category) is not None

    def get_effective_org_type(self) -> OrganizationType:
        """Resolve classification under the transitional compatibility rules.

        Precedence:
          1. Canonical organisation_type_code.
          2. Valid legacy business_category when the canonical code is absent.
          3. CORPORATE compatibility default.

        An invalid non-empty canonical value never falls through to legacy
        classification. org_type remains a legacy field and is not consulted.
        """
        code = (self.organisation_type_code or "").strip()

        if code:
            return (
                self._parse_org_type(code)
                or OrganizationType.CORPORATE
            )

        return (
            self._parse_org_type(self.business_category)
            or OrganizationType.CORPORATE
        )

    # -----------------------------------------------------------------------
    # Capability projection
    # -----------------------------------------------------------------------

    def get_capabilities(self) -> OrganizationCapability:
        """Return type-derived capability metadata, not authorization.

        An organisation without an explicit valid classification receives
        no type-derived grants or module integrations. Its unresolved
        classification must be handled by registration and review callers.
        """
        if not self.has_explicit_org_type():
            return _unclassified_org_capability()

        return get_organization_capabilities(
            self.get_effective_org_type()
        )

    def can_manage_staff(self):
        return self.get_capabilities().can_manage_staff

    def can_create_events(self):
        return self.get_capabilities().can_create_events

    def can_manage_accommodation(self):
        return self.get_capabilities().can_manage_accommodation

    def can_manage_transport(self):
        return self.get_capabilities().can_manage_transport

    def can_manage_tourism(self):
        return self.get_capabilities().can_manage_tourism

    def can_process_payments(self):
        return self.get_capabilities().can_process_payments

    def requires_license(self):
        return self.get_capabilities().requires_license

    def requires_insurance(self):
        return self.get_capabilities().requires_insurance

    # -----------------------------------------------------------------------
    # Settings
    # -----------------------------------------------------------------------

    def get_setting(self, key, default=None):
        """Read a setting safely, including malformed legacy JSON."""
        settings = self.org_settings

        if not isinstance(settings, dict):
            return default

        return settings.get(key, default)

    def set_setting(self, key, value):
        """Update settings using copy-and-reassign for JSON change tracking."""
        settings = self.org_settings

        if not isinstance(settings, dict):
            settings = {}

        updated_settings = dict(settings)
        updated_settings[key] = value
        self.org_settings = updated_settings

    def get_active_modules(self):
        """Return the legacy capability-based module projection.

        This does not prove activation, participation approval, or authority.
        """
        capabilities = self.get_capabilities()
        modules = []

        if capabilities.integrates_with_events:
            modules.append("events")

        if capabilities.integrates_with_accommodation:
            modules.append("accommodation")

        if capabilities.integrates_with_transport:
            modules.append("transport")

        if capabilities.integrates_with_wallet:
            modules.append("wallet")

        if capabilities.can_manage_tourism:
            modules.append("tourism")

        return modules

    # -----------------------------------------------------------------------
    # Operational status
    # -----------------------------------------------------------------------

    def update_operational_status(self):
        """Refresh operational status from verification, documents, licences."""
        today = date.today()

        docs_verified = all(
            doc.verification_status == "verified"
            and _expiry_is_valid(doc.expires_at, today=today)
            for doc in self.documents
        )

        licences_active = all(
            licence.is_active
            and _expiry_is_valid(licence.expires_at, today=today)
            for licence in self.licenses
        )

        self.is_operational = bool(
            docs_verified
            and licences_active
            and _enum_value(self.verification_status) == "verified"
        )

    # -----------------------------------------------------------------------
    # Verification helpers
    # -----------------------------------------------------------------------

    def is_fully_verified(self):
        """Return whether the latest verification is valid and unexpired."""
        latest = max(
            self.verifications,
            key=lambda item: item.requested_at,
            default=None,
        )

        if latest is None:
            return False

        if _enum_value(latest.status) != "verified":
            return False

        return _expiry_is_valid(latest.expires_at)

    def has_partial_verification(self):
        """Return whether the latest verification is pending or in review."""
        latest = max(
            self.verifications,
            key=lambda item: item.requested_at,
            default=None,
        )

        return bool(
            latest is not None
            and _enum_value(latest.status)
            in ("pending", "manual_review")
        )

    @property
    def has_expired_license(self):
        """Return whether any recorded licence has expired."""
        today = date.today()

        return any(
            licence.expires_at is not None
            and not _expiry_is_valid(
                licence.expires_at,
                today=today,
            )
            for licence in self.licenses
        )

    @property
    def has_expired_document(self):
        """Return whether any recorded document has expired."""
        today = date.today()

        return any(
            document.expires_at is not None
            and not _expiry_is_valid(
                document.expires_at,
                today=today,
            )
            for document in self.documents
        )

    # -----------------------------------------------------------------------
    # Wallet
    # -----------------------------------------------------------------------

    @property
    def primary_account(self):
        """Return the primary wallet account owned by this organisation."""
        from app.wallet.models.ledger import (
            AccountModel,
            AccountOwnerType,
        )

        return AccountModel.query.filter_by(
            organisation_id=self.id,
            owner_type=AccountOwnerType.ORGANISATION,
        ).first()

    @property
    def wallet_balance(self):
        """Return the ledger-derived balance using the legacy fallback.

        This is a display-oriented compatibility property, not an
        authorization check or an authoritative payment decision.
        """
        account = self.primary_account

        if account is None:
            return Decimal("0")

        from app.wallet.repositories.ledger_repository import (
            LedgerRepository,
        )

        try:
            balance = LedgerRepository().get_balance(
                account.id,
                account.currency,
            )

            if balance is None:
                logger.error(
                    "Ledger returned no balance for organisation account "
                    "id=%s",
                    account.id,
                )
                return Decimal("0")

            return balance

        except Exception:
            logger.exception(
                "Failed to retrieve wallet balance for organisation "
                "id=%s, account_id=%s",
                self.id,
                account.id,
            )
            return Decimal("0")

    # -----------------------------------------------------------------------
    # Representation and lifecycle
    # -----------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def check_org_duplicates(connection, target, is_update=False):
    """Detect duplicate legal names and contact emails.

    Updates exclude the current row while continuing to detect collisions
    with other organisations. Database constraints remain responsible for
    concurrency-safe uniqueness.
    """
    orgs_table = Organisation.__table__

    def exclude_self(query):
        if is_update and target.id is not None:
            query = query.where(orgs_table.c.id != target.id)

        return query

    if target.legal_name:
        name_query = exclude_self(
            select(orgs_table.c.id).where(
                orgs_table.c.legal_name == target.legal_name
            )
        )

        duplicate_name = connection.execute(
            name_query.limit(1)
        ).first()

        if duplicate_name:
            raise ValueError("Duplicate organisation legal name found")

    if target.contact_email:
        email_query = exclude_self(
            select(orgs_table.c.id).where(
                orgs_table.c.contact_email == target.contact_email
            )
        )

        duplicate_email = connection.execute(
            email_query.limit(1)
        ).first()

        if duplicate_email:
            raise ValueError("Duplicate organisation contact email found")


@event.listens_for(Organisation, "before_insert")
def organisation_before_insert(mapper, connection, target):
    check_org_duplicates(
        connection,
        target,
        is_update=False,
    )


@event.listens_for(Organisation, "before_update")
def organisation_before_update(mapper, connection, target):
    check_org_duplicates(
        connection,
        target,
        is_update=True,
    )


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

@event.listens_for(Organisation, "before_insert")
def organisation_before_insert_slug(mapper, connection, target):
    if not (target.slug or "").strip():
        from app.identity.services.organisation_slug import (
            ensure_unique_slug,
        )

        ensure_unique_slug(target)

    if not (target.slug or "").strip():
        raise ValueError("Organisation slug must not be empty")


@event.listens_for(Organisation, "before_update")
def organisation_before_update_slug(mapper, connection, target):
    if not (target.slug or "").strip():
        from app.identity.services.organisation_slug import (
            ensure_unique_slug,
        )

        ensure_unique_slug(target)

    if not (target.slug or "").strip():
        raise ValueError("Organisation slug must not be empty")