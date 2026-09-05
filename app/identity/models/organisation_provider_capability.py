"""
Organisation provider capability registry.

LEGACY / RETIRE AFTER COMPATIBILITY VERIFICATION (Stage 4B-3).
``org_provider_capabilities`` is NO LONGER a production write or read target:
organisation onboarding and the organisation capability API write/read
``provider_participations`` (Stage 4A Option A — ADR-4A-001/010, universal
``ProviderParticipation``). This model/table is retained ONLY for the OPC→PP
compatibility window and the controlled retirement step (ADR-4A-010). Do NOT
dual-write it and do NOT add production readers. The canonical enums
``ProviderCapabilityCode`` / ``ProviderCapabilityStatus`` defined here are
still imported by the participation service and routes.

Minimal persisted organisation-level signal that an Organisation can provide a
service. Independent of:

    * Organisation Type       (identity/classification, not capability)
    * Member Authority (RBAC) (one capability grants no user any permission)
    * Domain Resources        (capability creation creates no rooms/vehicles/events)

One row per ``(organisation_id, capability_code)``. An organisation may hold
zero, one, or many capabilities. Consumer participation is a universal
invariant and is intentionally NOT modelled here.

Stage 3 -- data model + database migration only.
"""

from __future__ import annotations

import enum

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


def _capability_code_check() -> str:
    """Generate CHECK constraint SQL from the canonical capability codes."""
    values = ",".join(f"'{v.value}'" for v in ProviderCapabilityCode)
    return f"capability_code IN ({values})"


def _capability_status_check() -> str:
    """Generate CHECK constraint SQL from the canonical capability statuses."""
    values = ",".join(f"'{v.value}'" for v in ProviderCapabilityStatus)
    return f"status IN ({values})"


class ProviderCapabilityCode(str, enum.Enum):
    """
    Canonical application-level provider capability codes.

    This is the single source of truth for the capability reference set and
    the ``ck_org_provider_capabilities_capability_code`` CHECK constraint.
    """

    ACCOMMODATION = "accommodation"
    TRANSPORT = "transport"
    EVENTS = "events"
    TOURISM = "tourism"
    VENUE = "venue"


class ProviderCapabilityStatus(str, enum.Enum):
    """
    Lifecycle of an organisation's provider capability.

    intent
        organisation has selected/intends to provide the service
    activated
        capability has been explicitly activated / is being actively provided
    suspended
        temporarily stopped (e.g. compliance pause)
    revoked
        withdrawn (e.g. compliance failure) - not grantable again without review
    deactivated
        permanently turned off by the organisation/admin (reversible)
    """

    INTENT = "intent"
    ACTIVATED = "activated"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    DEACTIVATED = "deactivated"


class OrganisationProviderCapability(BaseModel):
    """
    One persisted capability for one Organisation.

    Capability status is NOT: a user permission, an organisation role, a KYC
    tier, a KYB status, a licence, a domain resource, or a domain profile.
    """

    __tablename__ = "org_provider_capabilities"
    __table_args__ = (
        UniqueConstraint(
            "organisation_id",
            "capability_code",
            name="uq_org_provider_capability_org_code",
        ),
        Index(
            "ix_org_provider_capability_code_status",
            "capability_code",
            "status",
        ),
        Index(
            "ix_org_provider_capability_org_deleted",
            "organisation_id",
            "is_deleted",
        ),
        CheckConstraint(
            _capability_code_check(),
            name="ck_org_provider_capabilities_capability_code",
        ),
        CheckConstraint(
            _capability_status_check(),
            name="ck_org_provider_capabilities_status",
        ),
    )

    organisation_id = Column(
        BigInteger,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
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
    # Relationships
    # ------------------------------------------------------------------
    organisation = relationship(
        "Organisation",
        back_populates="provider_capabilities",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<OrganisationProviderCapability org_id={self.organisation_id} "
            f"code={self.capability_code} status={self.status}>"
        )
