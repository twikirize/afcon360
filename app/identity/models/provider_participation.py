"""
Universal provider participation registry (ISSUE 1).

Durable, domain-neutral representation of a subject's provider participation
in a service domain — the OPTION A lifecycle: a declared intention (INTENT)
that can be explicitly activated and then suspended, revoked, or deactivated.
One row per (subject, capability_code).

Subjects:
    * Individual  -> user_id (FK users.id), organisation_id IS NULL
    * Organisation -> organisation_id (FK organisations.id), user_id IS NULL

This is participation intent + operational lifecycle, NOT:
    * Identity / KYC / KYB (no verification state here)
    * Eligibility (checked by domain services, e.g. can_host())
    * Provider context (operating context, resolved at request time)
    * Domain resource (creates NO Property / Vehicle / Event / Service / Wallet)

Activation is NEVER automatic: INTENT -> ACTIVATED (and back-transitions) are
explicit, separately authorised service operations (see
``provider_participation_service``).

Canonical identifiers are reused from
``app.identity.models.organisation_provider_capability``:
    * ProviderCapabilityCode   (accommodation, transport, events, tourism, venue)
    * ProviderCapabilityStatus (intent, activated, suspended, revoked, deactivated)

ProviderParticipation is the SINGLE authoritative source of truth for BOTH
individual and organisation provider-participation rows (Stage 4A decision,
Option A — see STAGE_4A_UNIVERSAL_PROVIDER_ARCHITECTURE_DECISION_REPORT.md
ADR-4A-001/010). OrganisationProviderCapability is retained only as a
compatibility/migration source during the OPC→PP consolidation window; it is
NOT a concurrent authority and must never be dual-written. After the OPC→PP
data backfill executes, OrganisationProviderCapability is retired.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.extensions import db
from app.models.base import BaseModel
from app.identity.models.organisation_provider_capability import (
    ProviderCapabilityCode,
    ProviderCapabilityStatus,
    _capability_code_check,
    _capability_status_check,
)


class ProviderParticipation(BaseModel):
    """
    One persisted provider participation row for one subject in one domain.

    The row carries the full OPTION A participation lifecycle: ``status``
    starts at INTENT (declaration) and may be explicitly advanced to
    ACTIVATED (operational participation) or CONCLUDED states (SUSPENDED,
    REVOKED, DEACTIVATED) via the provider-participation service. It is the
    durable record of intention AND its operational lifecycle — not a domain
    resource, not eligibility, not a provider context.

    Exactly one of ``user_id`` / ``organisation_id`` is set per row.
    One row per ``(subject, capability_code)``: a subject may hold zero,
    one, or many domain participations.
    """

    __tablename__ = "provider_participations"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "capability_code",
            name="uq_provider_participation_user_code",
        ),
        UniqueConstraint(
            "organisation_id",
            "capability_code",
            name="uq_provider_participation_org_code",
        ),
        Index(
            "ix_provider_participation_code_status",
            "capability_code",
            "status",
        ),
        Index(
            "ix_provider_participation_user_deleted",
            "user_id",
            "is_deleted",
        ),
        Index(
            "ix_provider_participation_org_deleted",
            "organisation_id",
            "is_deleted",
        ),
        CheckConstraint(
            "((user_id IS NOT NULL AND organisation_id IS NULL) "
            "OR (user_id IS NULL AND organisation_id IS NOT NULL))",
            name="ck_provider_participations_single_subject",
        ),
        CheckConstraint(
            _capability_code_check(),
            name="ck_provider_participations_capability_code",
        ),
        CheckConstraint(
            _capability_status_check(),
            name="ck_provider_participations_status",
        ),
    )

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    organisation_id = Column(
        BigInteger,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    capability_code = Column(String(40), nullable=False)

    status = Column(
        String(20),
        nullable=False,
        default=ProviderCapabilityStatus.INTENT.value,
    )

    activated_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)

    meta = Column(JSON, nullable=False, default=dict)

    # ------------------------------------------------------------------
    # Relationships (distinct backrefs — no collision with existing ones)
    # ------------------------------------------------------------------
    user = relationship(
        "User",
        foreign_keys=[user_id],
        backref="individual_provider_participations",
    )
    organisation = relationship(
        "Organisation",
        foreign_keys=[organisation_id],
        backref="org_provider_participations",
    )

    @property
    def subject_type_computed(self) -> str:
        """Return 'individual' or 'organisation' for this row."""
        return "individual" if self.user_id is not None else "organisation"

    @property
    def is_intent_status(self) -> bool:
        """True when this row is a bare intention (not yet activated)."""
        return str(self.status) == ProviderCapabilityStatus.INTENT.value

    def __repr__(self) -> str:
        return (
            f"<ProviderParticipation subject="
            f"{self.subject_type_computed}:{self.user_id or self.organisation_id} "
            f"code={self.capability_code} status={self.status}>"
        )
