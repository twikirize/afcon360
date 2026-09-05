"""
Stage 3 tests: Organisation Provider Capability registry.

Covers:
  * model invariants (zero / one / many capabilities, belongs-to-org,
    duplicate rejection, invalid-code rejection, status persistence,
    soft-delete behaviour)
  * isolation (a capability row creates NO accommodation/transport/events/
    tourism resources, NO org roles/permissions/memberships)
  * existing-architecture integrity (adding a capability does not break
    existing Organisation / OrganisationMember / role / context structures)

These tests are additive to the existing suite. They do not rewrite any
pre-existing test.
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.identity.models import (
    Organisation,
    OrganisationProviderCapability,
    ProviderCapabilityCode,
    ProviderCapabilityStatus,
)
from app.identity.models.organisation_member import OrganisationMember, OrgUserRole, OrgRole


def _make_org(db_session, suffix=None):
    suffix = suffix or str(uuid.uuid4())[:8]
    org = Organisation(
        legal_name=f"Capability Org {suffix}",
        org_id=str(uuid.uuid4()),
        country="US",
    )
    db_session.add(org)
    db_session.flush()
    return org


def _add_capability(db_session, org, code, status=ProviderCapabilityStatus.INTENT.value):
    cap = OrganisationProviderCapability(
        organisation_id=org.id,
        capability_code=code,
        status=status,
    )
    db_session.add(cap)
    db_session.flush()
    return cap


# ---------------------------------------------------------------------------
# Model invariants
# ---------------------------------------------------------------------------

def test_organisation_can_have_zero_capabilities(db_session):
    org = _make_org(db_session)
    db_session.flush()
    assert org.provider_capabilities == []
    assert OrganisationProviderCapability.query.filter_by(
        organisation_id=org.id
    ).count() == 0


def test_organisation_can_have_one_capability(db_session):
    org = _make_org(db_session)
    _add_capability(db_session, org, ProviderCapabilityCode.ACCOMMODATION.value)
    db_session.flush()
    assert len(org.provider_capabilities) == 1
    assert org.provider_capabilities[0].capability_code == "accommodation"


def test_organisation_can_have_multiple_capabilities(db_session):
    org = _make_org(db_session)
    for code in (
        ProviderCapabilityCode.ACCOMMODATION.value,
        ProviderCapabilityCode.TRANSPORT.value,
        ProviderCapabilityCode.EVENTS.value,
        ProviderCapabilityCode.TOURISM.value,
        ProviderCapabilityCode.VENUE.value,
    ):
        _add_capability(db_session, org, code)
    db_session.flush()
    codes = {c.capability_code for c in org.provider_capabilities}
    assert codes == {
        "accommodation", "transport", "events", "tourism", "venue",
    }


def test_capability_belongs_to_organisation(db_session):
    org = _make_org(db_session)
    cap = _add_capability(db_session, org, ProviderCapabilityCode.TRANSPORT.value)
    assert cap.organisation_id == org.id
    assert cap.organisation is org


def test_duplicate_organisation_capability_rejected(db_session):
    org = _make_org(db_session)
    code = ProviderCapabilityCode.ACCOMMODATION.value
    _add_capability(db_session, org, code)
    with pytest.raises(IntegrityError):
        _add_capability(db_session, org, code)
    db_session.rollback()


def test_duplicate_across_different_organisations_allowed(db_session):
    org_a = _make_org(db_session, suffix="A")
    org_b = _make_org(db_session, suffix="B")
    code = ProviderCapabilityCode.EVENTS.value
    _add_capability(db_session, org_a, code)
    _add_capability(db_session, org_b, code)
    db_session.flush()
    assert OrganisationProviderCapability.query.filter_by(
        organisation_id=org_a.id, capability_code=code, is_deleted=False
    ).count() == 1
    assert OrganisationProviderCapability.query.filter_by(
        organisation_id=org_b.id, capability_code=code, is_deleted=False
    ).count() == 1


def test_invalid_capability_code_rejected(db_session):
    org = _make_org(db_session)
    bad = OrganisationProviderCapability(
        organisation_id=org.id,
        capability_code="bogus_code",
        status=ProviderCapabilityStatus.INTENT.value,
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_invalid_capability_status_rejected(db_session):
    org = _make_org(db_session)
    bad = OrganisationProviderCapability(
        organisation_id=org.id,
        capability_code=ProviderCapabilityCode.VENUE.value,
        status="not_a_status",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_status_persists_correctly(db_session):
    org = _make_org(db_session)
    cap = _add_capability(
        db_session,
        org,
        ProviderCapabilityCode.ACCOMMODATION.value,
        status=ProviderCapabilityStatus.ACTIVATED.value,
    )
    db_session.flush()
    assert cap.status == "activated"
    assert OrganisationProviderCapability.query.get(cap.id).status == "activated"


def test_default_status_is_intent(db_session):
    org = _make_org(db_session)
    cap = OrganisationProviderCapability(
        organisation_id=org.id,
        capability_code=ProviderCapabilityCode.TRANSPORT.value,
    )
    db_session.add(cap)
    db_session.flush()
    assert cap.status == "intent"


def test_soft_delete_behaviour(db_session):
    org = _make_org(db_session)
    cap = _add_capability(db_session, org, ProviderCapabilityCode.TOURISM.value)
    assert cap.is_deleted is False
    assert cap.deleted_at is None
    cap.soft_delete()
    db_session.flush()
    assert cap.is_deleted is True
    assert cap.deleted_at is not None


def test_meta_column_persisted(db_session):
    org = _make_org(db_session)
    cap = _add_capability(db_session, org, ProviderCapabilityCode.VENUE.value)
    cap.meta = {"source": "stage3_test"}
    db_session.flush()
    assert OrganisationProviderCapability.query.get(cap.id).meta == {
        "source": "stage3_test",
    }


def test_timestamps_populated(db_session):
    org = _make_org(db_session)
    cap = _add_capability(db_session, org, ProviderCapabilityCode.EVENTS.value)
    assert cap.created_at is not None
    assert cap.updated_at is not None


# ---------------------------------------------------------------------------
# Isolation: a capability creates / modifies nothing else
# ---------------------------------------------------------------------------

def _count(model_cls, **filters):
    return model_cls.query.filter_by(**filters).count()


def test_capability_creates_no_domain_resources(db_session, app):
    org = _make_org(db_session)
    db_session.flush()

    from app.accommodation.models import Property
    from app.transport.models import OrganisationTransportProfile, Vehicle
    from app.events.models import Event

    before = {
        "properties": _count(Property, owner_org_id=org.id),
        "transport_profiles": _count(OrganisationTransportProfile, organisation_id=org.id),
        "vehicles": _count(Vehicle),
        "events": Event.query.filter(
            (Event.organization_id == org.id)
            | (Event.current_owner_id == org.id)
        ).count(),
    }

    _add_capability(db_session, org, ProviderCapabilityCode.ACCOMMODATION.value)
    _add_capability(db_session, org, ProviderCapabilityCode.TRANSPORT.value)
    _add_capability(db_session, org, ProviderCapabilityCode.EVENTS.value)
    db_session.flush()

    after_properties = _count(Property, owner_org_id=org.id)
    after_transport_profiles = _count(OrganisationTransportProfile, organisation_id=org.id)
    after_vehicles = _count(Vehicle)
    after_events = Event.query.filter(
        (Event.organization_id == org.id)
        | (Event.current_owner_id == org.id)
    ).count()

    assert after_properties == before["properties"]
    assert after_transport_profiles == before["transport_profiles"]
    assert after_vehicles == before["vehicles"]
    assert after_events == before["events"]


def test_capability_creates_no_membership_or_role_or_permission(db_session):
    org = _make_org(db_session)
    db_session.flush()

    from app.identity.models.organisation_member import OrgRole as _OrgRole
    from app.identity.models.roles_permission import Permission

    members_before = OrganisationMember.query.filter_by(
        organisation_id=org.id
    ).count()
    roles_before = _OrgRole.query.filter_by(
        organisation_id=org.id
    ).count()
    perms_before = Permission.query.count()
    assignments_before = OrgUserRole.query.filter_by(
        organisation_id=org.id
    ).count() if hasattr(OrgUserRole, "organisation_id") else 0

    _add_capability(db_session, org, ProviderCapabilityCode.EVENTS.value)
    db_session.flush()

    assert OrganisationMember.query.filter_by(organisation_id=org.id).count() == members_before
    assert _OrgRole.query.filter_by(organisation_id=org.id).count() == roles_before
    assert Permission.query.count() == perms_before
    if hasattr(OrgUserRole, "organisation_id"):
        assert OrgUserRole.query.filter_by(organisation_id=org.id).count() == assignments_before


# ---------------------------------------------------------------------------
# Existing architecture integrity
# ---------------------------------------------------------------------------

def test_capability_does_not_break_existing_organisation_and_context(db_session):
    org = _make_org(db_session)
    db_session.flush()

    _add_capability(db_session, org, ProviderCapabilityCode.ACCOMMODATION.value)
    db_session.flush()

    reloaded = Organisation.query.get(org.id)
    assert reloaded is not None
    assert reloaded.legal_name == org.legal_name
    assert reloaded.is_deleted is False
    assert reloaded.provider_capabilities


def test_capability_supports_org_with_member(db_session):
    org = _make_org(db_session)
    db_session.flush()

    from app.identity.models.user import User

    user = User(
        email=f"member-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    member = OrganisationMember(
        user_id=user.id,
        organisation_id=org.id,
    )
    db_session.add(member)
    db_session.flush()

    _add_capability(db_session, org, ProviderCapabilityCode.TRANSPORT.value)
    db_session.flush()

    assert OrganisationMember.query.filter_by(
        user_id=user.id, organisation_id=org.id
    ).count() == 1
    assert len(org.provider_capabilities) == 1
