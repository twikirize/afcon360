# app/identity/services/capability_service.py
"""
Organisation capability API compatibility adapter (Stage 4B-3).

LEGACY STATUS — NOT a source of truth.
The canonical organisation provider-participation service is
``app.identity.services.provider_participation_service`` and
``provider_participations`` is the single production source of truth for
organisation capability state (Stage 4A Option A, ADR-4A-001/010).

This module keeps the historical organisation *capability* function surface
(``list_capabilities``, ``get_capability``, ``activate_capability``,
``deactivate_capability``, ``suspend_capability``, ``revoke_capability``,
``capability_to_dict``) as a thin compatibility adapter that delegates to the
canonical ProviderParticipation service. It performs NO direct writes to
``org_provider_capabilities`` (OPC). The OPC model/table is retained only for
the OPC→PP compatibility window and retirement (ADR-4A-010); it is never
dual-written.

Authority model (identical to the canonical service — frozen, Stage 4B-3 §6):
  - View capabilities: any active org member
  - Activate / Deactivate: org_owner only
  - Suspend / Revoke: org_owner or platform super_admin
  - Capabilities do NOT grant permissions, domain resources, or wallet access.

Lifecycle (delegates to the canonical service transition table):
  intent -> activated -> deactivated  (reversible)
  intent -> activated -> suspended    (owner or admin)
  any -> revoked                      (owner or admin — terminal)
"""

from __future__ import annotations

from typing import List, Optional

from app.identity.models.provider_participation import ProviderParticipation
from app.identity.services.provider_participation_service import (
    ParticipationNotFoundError,
    ParticipationPermissionError,
    ParticipationTransitionError,
    ParticipationValidationError,
    activate_organisation_intention,
    deactivate_organisation_intention,
    get_organisation_intention,
    list_organisation_intentions,
    participation_to_dict,
    revoke_organisation_intention,
    suspend_organisation_intention,
)


# ---------------------------------------------------------------------------
# Errors (compat surface — same names, translated from canonical errors)
# ---------------------------------------------------------------------------

class CapabilityTransitionError(ValueError):
    """Raised when a capability status transition is not permitted."""


class CapabilityNotFoundError(Exception):
    """Raised when the requested capability row does not exist."""


class CapabilityPermissionError(PermissionError):
    """Raised when the actor lacks authority for the requested operation."""


def _translate(exc: Exception) -> Exception:
    """Map canonical participation errors onto the compatibility surface."""
    if isinstance(exc, ParticipationPermissionError):
        return CapabilityPermissionError(str(exc))
    if isinstance(exc, ParticipationNotFoundError):
        return CapabilityNotFoundError(str(exc))
    if isinstance(exc, ParticipationTransitionError):
        return CapabilityTransitionError(str(exc))
    if isinstance(exc, ParticipationValidationError):
        # A code rejected by the canonical vocabulary is "not found" at the
        # org capability boundary (matches the historical behaviour).
        return CapabilityNotFoundError(str(exc))
    return exc


# ---------------------------------------------------------------------------
# Read (organisation rows backed by provider_participations)
# ---------------------------------------------------------------------------

def list_capabilities(org_id: int) -> List[ProviderParticipation]:
    """Return all non-deleted organisation participation rows (PP-backed)."""
    return list_organisation_intentions(org_id)


def get_capability(org_id: int, code: str) -> Optional[ProviderParticipation]:
    """Return a single organisation participation row or None (PP-backed)."""
    return get_organisation_intention(org_id, code)


# ---------------------------------------------------------------------------
# Write — lifecycle transitions (delegate to the canonical PP service)
# ---------------------------------------------------------------------------

def activate_capability(user, org_id: int, code: str) -> ProviderParticipation:
    """Activate an organisation capability (PP-backed). Requires org_owner."""
    try:
        return activate_organisation_intention(user, org_id, code)
    except Exception as exc:  # noqa: BLE001 — translated below
        raise _translate(exc) from exc


def deactivate_capability(user, org_id: int, code: str) -> ProviderParticipation:
    """Deactivate an organisation capability (PP-backed). Requires org_owner."""
    try:
        return deactivate_organisation_intention(user, org_id, code)
    except Exception as exc:  # noqa: BLE001 — translated below
        raise _translate(exc) from exc


def suspend_capability(user, org_id: int, code: str) -> ProviderParticipation:
    """Suspend an organisation capability (PP-backed). Requires owner or admin."""
    try:
        return suspend_organisation_intention(user, org_id, code)
    except Exception as exc:  # noqa: BLE001 — translated below
        raise _translate(exc) from exc


def revoke_capability(user, org_id: int, code: str) -> ProviderParticipation:
    """Revoke an organisation capability (PP-backed, terminal). Owner or admin."""
    try:
        return revoke_organisation_intention(user, org_id, code)
    except Exception as exc:  # noqa: BLE001 — translated below
        raise _translate(exc) from exc


def capability_to_dict(cap: ProviderParticipation) -> dict:
    """Serialise an organisation participation row (dual-ID safe).

    Delegates to the canonical ``participation_to_dict`` serializer; the
    ``subject_type`` is resolved from the row ('organisation' for org rows).
    Internal BIGINT ids are never serialised (AGENTS.md §12.1).
    """
    return participation_to_dict(cap)