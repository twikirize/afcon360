# app/identity/services/provider_participation_service.py
"""
Universal provider participation service (ISSUE 1).

Domain-neutral lifecycle for provider participation across all service domains
(accommodation, transport, events, tourism, venue) for both individuals and
organisations.

Semantics (OPTION A — resolves the "intention only" contradiction):
A provider_participations row IS the participant's full participation
lifecycle: it starts as an INTENT declaration, and the service performs
explicit, separately authorised transitions (activate/deactivate/suspend/
revoke). The word "intention" names the initial declared state, not the
whole row.

Boundaries (architectural invariants):
  - Participation creates NO domain resource (no Property / Vehicle /
    Event / Service / Wallet / Booking). Only a provider_participations row.
  - Participation is NOT eligibility: no KYC/KYB check here. Domain services
    (e.g. AccommodationIdentityService.can_host()) remain the eligibility
    authority and are untouched.
  - Participation does NOT auto-activate: INTENT -> ACTIVATED is an explicit,
    separately authorised transition.
  - ProviderParticipation is the single authoritative source of truth for BOTH
    subjects (Stage 4A Option A, ADR-4A-001/010). OrganisationProviderCapability
    is retained only as a compatibility/migration source during the OPC→PP
    consolidation window; it is NOT a concurrent authority and must never be
    dual-written. After the OPC→PP data backfill executes, OPC is retired.
  - As of Stage 4B-3, organisation onboarding (create_organisation_intention)
    and the organisation capability API (list/activate/deactivate/suspend/
    revoke via app/identity/routes.py) write/read through this service — OPC is
    no longer a production write or read target.

Authority model:
  - Individual rows: the user themself only (user.id match on a live account).
  - Organisation rows: active org membership to declare; org_owner to
    activate/deactivate; org_owner or platform admin to suspend/revoke.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from flask import current_app

from app.extensions import db
from app.identity.models.organisation_provider_capability import (
    ProviderCapabilityCode,
    ProviderCapabilityStatus,
)
from app.identity.models.provider_participation import ProviderParticipation


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ParticipationNotFoundError(Exception):
    """Raised when the requested participation row does not exist."""


class ParticipationPermissionError(PermissionError):
    """Raised when the actor lacks authority for the requested operation."""


class ParticipationTransitionError(ValueError):
    """Raised when a status transition is not permitted."""


class ParticipationValidationError(ValueError):
    """Raised when the capability code or subject is invalid."""


# ---------------------------------------------------------------------------
# Canonical vocabulary (single source of truth lives in
# organisation_provider_capability — reused here, never duplicated)
# ---------------------------------------------------------------------------

_VALID_CODES = frozenset(c.value for c in ProviderCapabilityCode)

_ALLOWED_TRANSITIONS = frozenset({
    (ProviderCapabilityStatus.INTENT.value, ProviderCapabilityStatus.ACTIVATED.value),
    (ProviderCapabilityStatus.ACTIVATED.value, ProviderCapabilityStatus.DEACTIVATED.value),
    (ProviderCapabilityStatus.DEACTIVATED.value, ProviderCapabilityStatus.ACTIVATED.value),
    (ProviderCapabilityStatus.ACTIVATED.value, ProviderCapabilityStatus.SUSPENDED.value),
    (ProviderCapabilityStatus.SUSPENDED.value, ProviderCapabilityStatus.ACTIVATED.value),
    (ProviderCapabilityStatus.INTENT.value, ProviderCapabilityStatus.DEACTIVATED.value),
    (ProviderCapabilityStatus.DEACTIVATED.value, ProviderCapabilityStatus.INTENT.value),
})


def _validate_code(code: str) -> str:
    normalised = str(code or "").strip().lower()
    if normalised not in _VALID_CODES:
        raise ParticipationValidationError(
            f"Unknown capability code '{code}'. "
            f"Expected one of: {sorted(_VALID_CODES)}."
        )
    return normalised


def _assert_live_user(user) -> None:
    if (
        user is None
        or not getattr(user, "is_active", False)
        or getattr(user, "is_deleted", False)
    ):
        raise ParticipationPermissionError("Account is inactive or deleted.")


def _assert_self(user, user_id: int) -> None:
    _assert_live_user(user)
    if getattr(user, "id", None) != user_id:
        raise ParticipationPermissionError(
            "You can only manage your own provider intentions."
        )


def _assert_org_member(user, org_id: int) -> None:
    from app.identity.models.organisation_member import OrganisationMember
    _assert_live_user(user)
    membership = OrganisationMember.query.filter_by(
        user_id=user.id,
        organisation_id=org_id,
        is_active=True,
        is_deleted=False,
    ).first()
    if membership is None:
        raise ParticipationPermissionError(
            "You are not a member of this organisation."
        )


def _assert_org_owner(user, org_id: int) -> None:
    _assert_org_member(user, org_id)
    if not user.is_org_owner(org_id):
        raise ParticipationPermissionError(
            "Only the organisation owner can perform this operation."
        )


def _assert_owner_or_admin(user, org_id: int) -> None:
    _assert_org_member(user, org_id)
    is_owner = user.is_org_owner(org_id)
    is_admin = getattr(user, "is_super_admin", lambda: False)()
    if not (is_owner or is_admin):
        raise ParticipationPermissionError(
            "Only the organisation owner or a platform administrator "
            "can perform this operation."
        )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_individual_intention(user_id: int, code: str) -> Optional[ProviderParticipation]:
    """Return one individual's non-deleted intention row or None."""
    return (
        ProviderParticipation.query
        .filter_by(
            user_id=user_id,
            organisation_id=None,
            capability_code=_validate_code(code),
            is_deleted=False,
        )
        .first()
    )


def list_individual_intentions(user_id: int) -> List[ProviderParticipation]:
    """Return all non-deleted intention rows for one individual."""
    return (
        ProviderParticipation.query
        .filter_by(user_id=user_id, is_deleted=False)
        .filter(ProviderParticipation.organisation_id.is_(None))
        .order_by(ProviderParticipation.capability_code)
        .all()
    )


def get_organisation_intention(org_id: int, code: str) -> Optional[ProviderParticipation]:
    """Return one organisation's non-deleted intention row or None."""
    return (
        ProviderParticipation.query
        .filter_by(
            organisation_id=org_id,
            user_id=None,
            capability_code=_validate_code(code),
            is_deleted=False,
        )
        .first()
    )


def list_organisation_intentions(org_id: int) -> List[ProviderParticipation]:
    """Return all non-deleted intention rows for one organisation."""
    return (
        ProviderParticipation.query
        .filter_by(organisation_id=org_id, is_deleted=False)
        .filter(ProviderParticipation.user_id.is_(None))
        .order_by(ProviderParticipation.capability_code)
        .all()
    )


# ---------------------------------------------------------------------------
# Write — declaration (always INTENT; never activates, never creates resources)
# ---------------------------------------------------------------------------

def create_individual_intention(user, code: str, meta: Optional[dict] = None) -> ProviderParticipation:
    """Declare an individual's provider intention in a domain.

    Idempotent: declaring twice returns the existing row (no duplicate).
    Creates NOTHING except the participation row.
    """
    _assert_self(user, user.id)
    normalised = _validate_code(code)
    existing = get_individual_intention(user.id, normalised)
    if existing is not None:
        return existing
    row = ProviderParticipation(
        user_id=user.id,
        organisation_id=None,
        capability_code=normalised,
        status=ProviderCapabilityStatus.INTENT.value,
        meta=dict(meta or {}),
    )
    db.session.add(row)
    db.session.flush()
    current_app.logger.info(
        "Provider intention '%s' declared by user %s", normalised, user.id,
    )
    return row


def create_organisation_intention(
    user, org_id: int, code: str, meta: Optional[dict] = None,
) -> ProviderParticipation:
    """Declare an organisation's provider intention in a domain.

    Requires active org membership. Idempotent. Creates NOTHING except the
    participation row. Existing OrganisationProviderCapability flows are
    untouched — nothing is dual-written.
    """
    _assert_org_member(user, org_id)
    normalised = _validate_code(code)
    existing = get_organisation_intention(org_id, normalised)
    if existing is not None:
        return existing
    row = ProviderParticipation(
        user_id=None,
        organisation_id=org_id,
        capability_code=normalised,
        status=ProviderCapabilityStatus.INTENT.value,
        meta=dict(meta or {}),
    )
    db.session.add(row)
    db.session.flush()
    current_app.logger.info(
        "Provider intention '%s' declared for org %s by user %s",
        normalised, org_id, user.id,
    )
    return row


# ---------------------------------------------------------------------------
# Write — lifecycle transitions (explicit; never automatic)
# ---------------------------------------------------------------------------

def _apply_transition(row: ProviderParticipation, target_status: str) -> None:
    current = str(row.status)
    if (current, target_status) not in _ALLOWED_TRANSITIONS:
        raise ParticipationTransitionError(
            f"Cannot transition participation '{row.capability_code}' "
            f"from '{current}' to '{target_status}'."
        )
    setattr(row, "status", target_status)
    now = datetime.now(timezone.utc)
    if target_status == ProviderCapabilityStatus.ACTIVATED.value:
        setattr(row, "activated_at", now)


def _resolve_subject(row: ProviderParticipation) -> tuple:
    if row.user_id is not None:
        return ("individual", row.user_id)
    return ("organisation", row.organisation_id)


def activate_individual_intention(user, code: str) -> ProviderParticipation:
    """Activate own intention (intent -> activated). Owner: the user themself."""
    _assert_self(user, user.id)
    row = get_individual_intention(user.id, code)
    if row is None:
        raise ParticipationNotFoundError(
            f"No '{code}' intention found for this user."
        )
    _apply_transition(row, ProviderCapabilityStatus.ACTIVATED.value)
    db.session.flush()
    return row


def deactivate_individual_intention(user, code: str) -> ProviderParticipation:
    """Deactivate own intention (reversible). Owner: the user themself."""
    _assert_self(user, user.id)
    row = get_individual_intention(user.id, code)
    if row is None:
        raise ParticipationNotFoundError(
            f"No '{code}' intention found for this user."
        )
    _apply_transition(row, ProviderCapabilityStatus.DEACTIVATED.value)
    db.session.flush()
    return row


def activate_organisation_intention(user, org_id: int, code: str) -> ProviderParticipation:
    """Activate an organisation intention. Requires org_owner authority."""
    _assert_org_owner(user, org_id)
    row = get_organisation_intention(org_id, code)
    if row is None:
        raise ParticipationNotFoundError(
            f"No '{code}' intention found for organisation {org_id}."
        )
    _apply_transition(row, ProviderCapabilityStatus.ACTIVATED.value)
    db.session.flush()
    return row


def deactivate_organisation_intention(user, org_id: int, code: str) -> ProviderParticipation:
    """Deactivate an organisation intention (reversible). Requires org_owner."""
    _assert_org_owner(user, org_id)
    row = get_organisation_intention(org_id, code)
    if row is None:
        raise ParticipationNotFoundError(
            f"No '{code}' intention found for organisation {org_id}."
        )
    _apply_transition(row, ProviderCapabilityStatus.DEACTIVATED.value)
    db.session.flush()
    return row


def suspend_organisation_intention(user, org_id: int, code: str) -> ProviderParticipation:
    """Suspend an organisation intention. Requires org_owner or admin."""
    _assert_owner_or_admin(user, org_id)
    row = get_organisation_intention(org_id, code)
    if row is None:
        raise ParticipationNotFoundError(
            f"No '{code}' intention found for organisation {org_id}."
        )
    _apply_transition(row, ProviderCapabilityStatus.SUSPENDED.value)
    db.session.flush()
    return row


def revoke_organisation_intention(user, org_id: int, code: str) -> ProviderParticipation:
    """Revoke an organisation intention (terminal). Requires org_owner or admin."""
    _assert_owner_or_admin(user, org_id)
    row = get_organisation_intention(org_id, code)
    if row is None:
        raise ParticipationNotFoundError(
            f"No '{code}' intention found for organisation {org_id}."
        )
    if str(row.status) == ProviderCapabilityStatus.REVOKED.value:
        raise ParticipationTransitionError(
            f"Participation '{code}' is already revoked."
        )
    setattr(row, "status", ProviderCapabilityStatus.REVOKED.value)
    db.session.flush()
    return row


def participation_to_dict(row: ProviderParticipation) -> dict:
    """Serialise a participation row (internal service boundary).

    NOTE: subject ids here are internal BIGINTs for service/test use.
    Any future API response must resolve to public_id at the route layer
    (dual-ID rule) — no route exists yet (Issue 2+).
    """
    subject_type, _ = _resolve_subject(row)
    activated_at = getattr(row, "activated_at", None)
    verified_at = getattr(row, "verified_at", None)
    created_at = getattr(row, "created_at", None)
    updated_at = getattr(row, "updated_at", None)
    return {
        "subject_type": subject_type,
        "capability_code": getattr(row, "capability_code", None),
        "status": str(getattr(row, "status", None)),
        "activated_at": activated_at.isoformat() if activated_at else None,
        "verified_at": verified_at.isoformat() if verified_at else None,
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }
