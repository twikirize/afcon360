"""
Stage 4B — Organisation Classification & Eligibility Reconciliation.

Focused tests for ``AccommodationIdentityService.can_org_host()``.

The approved architecture (Option C):
  * ``Organisation.business_category`` is the canonical ``OrganizationType``
    classification (PostgreSQL enum ``org_business_category``).
  * Accommodation eligibility is derived from the repository-owned organisation
    capability mapping (``Organisation.get_capabilities().can_manage_accommodation``).
  * The legacy string vocabulary (``merchant``/``service_provider``/
    ``marketplace_seller``/``non_profit``) is NOT a canonical eligibility value.

Proves:
  * verified + operational org with an accommodation-capable type -> True
  * verified + operational org with a non-accommodation type       -> False
  * eligible type but unacceptable verification                    -> False
  * eligible type but non-operational org                          -> False
  * NULL ``business_category`` has no AttributeError -> controlled False
  * legacy vocabulary values are never treated as eligible

Run: pytest tests/test_can_org_host.py -v
"""

import uuid

import pytest

from app.accommodation.services.identity_service import AccommodationIdentityService
from app.identity.models.organisation import Organisation
from app.identity.models.organization_types import (
    ORGANIZATION_CAPABILITIES,
    OrganizationType,
)

# Canonical members the repository's capability mapping marks as
# accommodation-capable (can_manage_accommodation=True in ORGANIZATION_CAPABILITIES).
ACCOMMODATION_ELIGIBLE_TYPES = sorted(
    (t for t, caps in ORGANIZATION_CAPABILITIES.items() if caps.can_manage_accommodation),
    key=lambda t: t.name,
)

# Canonical members the mapping marks as NOT accommodation-capable.
NON_ACCOMMODATION_TYPES = sorted(
    (t for t in OrganizationType if t not in ACCOMMODATION_ELIGIBLE_TYPES),
    key=lambda t: t.name,
)


def _make_org(db_session, org_type, verification_status="verified", is_operational=True):
    """Create a fully-gated Organisation row for the given canonical type."""
    org = Organisation(
        org_id=f"org_{uuid.uuid4().hex[:10]}",
        legal_name=f"Org {uuid.uuid4().hex[:8]}",
        country="UG",
        business_category=org_type,
        verification_status=verification_status,
        lifecycle_state="registered",
        is_active=True,
        is_operational=is_operational,
    )
    db_session.add(org)
    db_session.flush()
    return org


def _can_org_host(org_id):
    return AccommodationIdentityService.can_org_host(org_id)


@pytest.mark.parametrize("org_type", ACCOMMODATION_ELIGIBLE_TYPES)
def test_eligible_classification_returns_true(db_session, org_type):
    org = _make_org(db_session, org_type)
    can, reason = _can_org_host(org.id)
    assert can is True
    assert reason == "OK"


@pytest.mark.parametrize("org_type", NON_ACCOMMODATION_TYPES)
def test_ineligible_classification_returns_false(db_session, org_type):
    org = _make_org(db_session, org_type)
    can, reason = _can_org_host(org.id)
    assert can is False
    assert "not eligible" in reason


def test_verification_failure_blocks_eligible_org(db_session):
    org = _make_org(db_session, OrganizationType.HOTEL, verification_status="pending")
    can, reason = _can_org_host(org.id)
    assert can is False
    assert "verif" in reason.lower()


def test_operational_failure_blocks_eligible_org(db_session):
    org = _make_org(db_session, OrganizationType.TOUR_OPERATOR, is_operational=False)
    can, reason = _can_org_host(org.id)
    assert can is False
    assert "operational" in reason.lower()


def test_inactive_org_blocked(db_session):
    org = _make_org(db_session, OrganizationType.HOTEL)
    org.is_active = False
    db_session.flush()
    can, reason = _can_org_host(org.id)
    assert can is False
    assert "inactive" in reason.lower()


def test_missing_classification_is_controlled_false(db_session):
    org = _make_org(db_session, None, verification_status="verified")
    can, reason = _can_org_host(org.id)
    assert can is False
    assert reason


def test_deleted_org_blocked(db_session):
    org = _make_org(db_session, OrganizationType.HOTEL)
    org.is_deleted = True
    db_session.flush()
    can, reason = _can_org_host(org.id)
    assert can is False
    assert "not found or deleted" in reason


def test_legacy_vocabulary_is_not_canonical(db_session):
    """Legacy strings must never be treated as eligible classification values."""
    valid_values = {m.value for m in OrganizationType}
    for legacy in ["merchant", "service_provider", "marketplace_seller", "non_profit"]:
        assert legacy not in valid_values, f"{legacy} is not a canonical OrganizationType value"