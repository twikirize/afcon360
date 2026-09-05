"""
ISSUE 1 tests: Universal provider participation registry.

Covers:
  * Individual: create / retrieve / list intentions across all five domains
    (accommodation, transport, events, tourism, venue)
  * Duplicate declaration is idempotent (no duplicate row)
  * Isolation: one user cannot manage another user's intentions
  * Lifecycle: intent -> activated -> deactivated (+ invalid transitions)
  * Separation: declaring an intention creates NO Property / Vehicle /
    Event / Wallet resource and does not touch UserProfile/KYC state
  * Organisation: membership authority respected; organisation onboarding
    now writes ProviderParticipation ONLY (Stage 4B-3) and legacy OPC rows
    still behave through the legacy relationship

These tests are additive. They do not rewrite any pre-existing test.
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.identity.models import (
    Organisation,
    OrganisationProviderCapability,
    ProviderCapabilityCode,
    ProviderCapabilityStatus,
    ProviderParticipation,
)
from app.identity.models.organisation_member import (
    OrganisationMember,
    OrgUserRole,
    OrgRole,
)
from app.identity.services.provider_participation_service import (
    ParticipationNotFoundError,
    ParticipationPermissionError,
    ParticipationTransitionError,
    ParticipationValidationError,
    activate_individual_intention,
    activate_organisation_intention,
    create_individual_intention,
    create_organisation_intention,
    deactivate_individual_intention,
    get_individual_intention,
    get_organisation_intention,
    list_individual_intentions,
    list_organisation_intentions,
    participation_to_dict,
)


ALL_CODES = (
    ProviderCapabilityCode.ACCOMMODATION.value,
    ProviderCapabilityCode.TRANSPORT.value,
    ProviderCapabilityCode.EVENTS.value,
    ProviderCapabilityCode.TOURISM.value,
    ProviderCapabilityCode.VENUE.value,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _seed_org_roles(app):
    """Seed global org-scoped Role definitions once, so
    provision_organisation_roles() can create OrgRole instances.

    Mirrors tests/test_capability_operations.py: without org-scoped global
    roles, role provisioning is skipped and every org-authority test fails.
    """
    from app.auth.seed_roles import seed_all
    with app.app_context():
        seed_all()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db_session, suffix=None):
    from app.identity.models.user import User
    suffix = suffix or uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"ppart_{suffix}",
        email=f"ppart_{suffix}@example.com",
    )
    user.set_password("TestPassword123!")
    user.is_active = True
    db_session.add(user)
    db_session.flush()
    return user


def _make_org(db_session, suffix=None):
    suffix = suffix or uuid.uuid4().hex[:8]
    org = Organisation(
        legal_name=f"Participation Org {suffix}",
        org_id=str(uuid.uuid4()),
        country="UG",
    )
    db_session.add(org)
    db_session.flush()
    return org


def _assign_org_role(db_session, user, org, role_name):
    from app.identity.services.organisation_role_provisioning import (
        provision_organisation_roles,
    )
    provision_organisation_roles(org, commit=False)
    db_session.flush()
    membership = OrganisationMember(
        user_id=user.id,
        organisation_id=org.id,
        is_active=True,
    )
    db_session.add(membership)
    db_session.flush()
    org_role = OrgRole.query.filter_by(
        organisation_id=org.id, name=role_name,
    ).first()
    assert org_role is not None
    db_session.add(OrgUserRole(
        organisation_member_id=membership.id,
        role_id=org_role.id,
        assigned_by=user.id,
    ))
    db_session.flush()
    return membership


# ---------------------------------------------------------------------------
# Individual: create / retrieve / list
# ---------------------------------------------------------------------------

def test_individual_can_create_accommodation_intention(db_session):
    user = _make_user(db_session)
    row = create_individual_intention(
        user, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    assert row.user_id == user.id
    assert row.organisation_id is None
    assert row.capability_code == "accommodation"
    assert str(row.status) == ProviderCapabilityStatus.INTENT.value


def test_individual_can_retrieve_intention(db_session):
    user = _make_user(db_session)
    create_individual_intention(
        user, ProviderCapabilityCode.TRANSPORT.value,
    )
    db_session.flush()
    found = get_individual_intention(
        user.id, ProviderCapabilityCode.TRANSPORT.value,
    )
    assert found is not None
    assert found.user_id == user.id


def test_individual_can_hold_all_five_domain_intentions(db_session):
    user = _make_user(db_session)
    for code in ALL_CODES:
        create_individual_intention(user, code)
    db_session.flush()
    rows = list_individual_intentions(user.id)
    assert {str(r.capability_code) for r in rows} == set(ALL_CODES)


def test_duplicate_individual_intention_is_idempotent(db_session):
    user = _make_user(db_session)
    first = create_individual_intention(
        user, ProviderCapabilityCode.EVENTS.value,
    )
    db_session.flush()
    second = create_individual_intention(
        user, ProviderCapabilityCode.EVENTS.value,
    )
    db_session.flush()
    assert first.id == second.id
    assert ProviderParticipation.query.filter_by(
        user_id=user.id,
        capability_code=ProviderCapabilityCode.EVENTS.value,
        is_deleted=False,
    ).count() == 1


def test_duplicate_individual_intention_rejected_at_db_level(db_session):
    user = _make_user(db_session)
    db_session.add(ProviderParticipation(
        user_id=user.id,
        organisation_id=None,
        capability_code=ProviderCapabilityCode.VENUE.value,
        status=ProviderCapabilityStatus.INTENT.value,
    ))
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.add(ProviderParticipation(
            user_id=user.id,
            organisation_id=None,
            capability_code=ProviderCapabilityCode.VENUE.value,
            status=ProviderCapabilityStatus.INTENT.value,
        ))
        db_session.flush()
    db_session.rollback()


def test_unknown_capability_code_rejected(db_session):
    user = _make_user(db_session)
    with pytest.raises(ParticipationValidationError):
        create_individual_intention(user, "accommodation_provider")


# ---------------------------------------------------------------------------
# Individual: isolation
# ---------------------------------------------------------------------------

def test_individual_cannot_activate_another_users_intention(db_session):
    owner = _make_user(db_session)
    intruder = _make_user(db_session)
    create_individual_intention(
        owner, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    # The owner's row is a bare intent before the attack.
    assert str(get_individual_intention(
        owner.id, ProviderCapabilityCode.ACCOMMODATION.value,
    ).status) == ProviderCapabilityStatus.INTENT.value
    # The intruder's own lookup finds nothing: they cannot see, touch, or
    # gain anything from the owner's row.
    with pytest.raises(ParticipationNotFoundError):
        activate_individual_intention(
            intruder, ProviderCapabilityCode.ACCOMMODATION.value,
        )
    # The failed attempt wrote nothing (lookup-only); the owner's row is
    # untouched and still a bare intent.
    assert str(get_individual_intention(
        owner.id, ProviderCapabilityCode.ACCOMMODATION.value,
    ).status) == ProviderCapabilityStatus.INTENT.value


def test_individual_cannot_declare_for_someone_else(db_session):
    owner = _make_user(db_session)
    _make_user(db_session)
    row = create_individual_intention(
        owner, ProviderCapabilityCode.TOURISM.value,
    )
    db_session.flush()
    # The service binds the row to the acting user; there is no
    # "create for user X" path — the row always belongs to the caller.
    assert row.user_id == owner.id


# ---------------------------------------------------------------------------
# Individual: lifecycle (explicit transitions only — never automatic)
# ---------------------------------------------------------------------------

def test_individual_lifecycle_intent_activated_deactivated(db_session):
    user = _make_user(db_session)
    create_individual_intention(
        user, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    activated = activate_individual_intention(
        user, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    assert str(activated.status) == ProviderCapabilityStatus.ACTIVATED.value
    assert getattr(activated, "activated_at", None) is not None
    db_session.flush()
    deactivated = deactivate_individual_intention(
        user, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    assert str(deactivated.status) == ProviderCapabilityStatus.DEACTIVATED.value


def test_invalid_transition_rejected(db_session):
    user = _make_user(db_session)
    create_individual_intention(
        user, ProviderCapabilityCode.TRANSPORT.value,
    )
    db_session.flush()
    row = get_individual_intention(
        user.id, ProviderCapabilityCode.TRANSPORT.value,
    )
    from app.identity.services.provider_participation_service import (
        _apply_transition,
    )
    with pytest.raises(ParticipationTransitionError):
        _apply_transition(
            row, ProviderCapabilityStatus.SUSPENDED.value,
        )
    db_session.rollback()


def test_activate_missing_intention_raises_not_found(db_session):
    user = _make_user(db_session)
    with pytest.raises(ParticipationNotFoundError):
        activate_individual_intention(
            user, ProviderCapabilityCode.VENUE.value,
        )
    db_session.rollback()


def test_participation_to_dict_uses_no_internal_subject_id(db_session):
    user = _make_user(db_session)
    row = create_individual_intention(
        user, ProviderCapabilityCode.EVENTS.value,
    )
    db_session.flush()
    data = participation_to_dict(row)
    assert data["subject_type"] == "individual"
    assert data["capability_code"] == "events"
    assert data["status"] == "intent"
    assert "user_id" not in data
    assert "organisation_id" not in data


# ---------------------------------------------------------------------------
# Separation: intention creates zero domain resources
# ---------------------------------------------------------------------------

def test_intention_creates_no_domain_resources(db_session):
    from app.accommodation.models import Property
    from app.transport.models import Vehicle
    from app.wallet.models.ledger import AccountModel
    user = _make_user(db_session)
    props_before = Property.query.filter_by(owner_user_id=user.id).count()
    # Vehicle has no per-user owner (owner_id/owner_type point at driver/org
    # profiles), so assert the global count is unchanged.
    vehicles_before = Vehicle.query.count()
    wallets_before = AccountModel.query.filter_by(user_id=user.id).count()
    for code in ALL_CODES:
        create_individual_intention(user, code)
    db_session.flush()
    assert Property.query.filter_by(owner_user_id=user.id).count() == props_before
    assert Vehicle.query.filter_by(
        owner_type="user", owner_id=user.id,
    ).count() == vehicles_before
    assert AccountModel.query.filter_by(user_id=user.id).count() == wallets_before
    assert ProviderParticipation.query.filter_by(
        user_id=user.id, is_deleted=False,
    ).count() == len(ALL_CODES)


def test_intention_does_not_bypass_host_eligibility(db_session):
    from app.accommodation.services.identity_service import (
        AccommodationIdentityService,
    )
    user = _make_user(db_session)
    can_host_before, _ = AccommodationIdentityService.can_host(user)
    create_individual_intention(
        user, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    can_host_after, _ = AccommodationIdentityService.can_host(user)
    # Declaring an intention must not grant accommodation eligibility.
    assert can_host_before is False
    assert can_host_after is False


def test_intention_does_not_touch_user_profile(db_session):
    from app.profile.models import get_profile_by_user
    user = _make_user(db_session)
    profile_before = get_profile_by_user(user.public_id)
    create_individual_intention(
        user, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    assert get_profile_by_user(user.public_id) == profile_before


# ---------------------------------------------------------------------------
# Organisation: authority respected, existing capability model intact
# ---------------------------------------------------------------------------

def test_org_member_can_declare_org_intention(db_session):
    org = _make_org(db_session)
    user = _make_user(db_session)
    _assign_org_role(db_session, user, org, "org_member")
    row = create_organisation_intention(
        user, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    assert row.organisation_id == org.id
    assert row.user_id is None
    assert str(row.status) == ProviderCapabilityStatus.INTENT.value


def test_org_non_member_cannot_declare_org_intention(db_session):
    org = _make_org(db_session)
    outsider = _make_user(db_session)
    with pytest.raises(ParticipationPermissionError):
        create_organisation_intention(
            outsider, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
        )
    db_session.rollback()


def test_org_member_cannot_activate_org_intention(db_session):
    org = _make_org(db_session)
    member = _make_user(db_session)
    _assign_org_role(db_session, member, org, "org_member")
    create_organisation_intention(
        member, org.id, ProviderCapabilityCode.TRANSPORT.value,
    )
    db_session.flush()
    with pytest.raises(ParticipationPermissionError):
        activate_organisation_intention(
            member, org.id, ProviderCapabilityCode.TRANSPORT.value,
        )
    db_session.rollback()


def test_org_owner_can_activate_org_intention(db_session):
    org = _make_org(db_session)
    owner = _make_user(db_session)
    _assign_org_role(db_session, owner, org, "org_owner")
    create_organisation_intention(
        owner, org.id, ProviderCapabilityCode.TOURISM.value,
    )
    db_session.flush()
    row = activate_organisation_intention(
        owner, org.id, ProviderCapabilityCode.TOURISM.value,
    )
    assert str(row.status) == ProviderCapabilityStatus.ACTIVATED.value


def test_existing_org_capability_behaviour_intact(db_session):
    org = _make_org(db_session)
    cap = OrganisationProviderCapability(
        organisation_id=org.id,
        capability_code=ProviderCapabilityCode.ACCOMMODATION.value,
        status=ProviderCapabilityStatus.INTENT.value,
    )
    db_session.add(cap)
    db_session.flush()
    assert len(org.provider_capabilities) == 1
    # New universal table holds no org rows unless explicitly declared there.
    assert get_organisation_intention(
        org.id, ProviderCapabilityCode.ACCOMMODATION.value,
    ) is None
    assert list_organisation_intentions(org.id) == []


# ---------------------------------------------------------------------------
# STAGE 3B: production wiring — individual accommodation host onboarding
# (ProviderParticipation is the first real production consumer)
# ---------------------------------------------------------------------------

def _host_onboarding_data():
    return {
        "step1": {
            "full_name": "Stage 3B Host",
            "national_id": "CIV-S3B-123456",
            "proof_of_address": "Kampala",
        },
        "step2": {
            "property_name": "Stage 3B Property",
            "description": "test",
            "address": "123 Test St",
            "city": "Kampala",
            "country": "UG",
            "property_type": "house",
            "number_of_rooms": "2",
        },
    }


def test_host_onboarding_records_individual_accommodation_intention(db_session):
    """The production host onboarding flow must create exactly one
    ProviderParticipation row: subject=individual, ACCOMMODATION, INTENT."""
    from app.auth.onboarding_routes import _commit_host_onboarding
    user = _make_user(db_session)
    _commit_host_onboarding(user, _host_onboarding_data())
    db_session.flush()
    rows = ProviderParticipation.query.filter_by(
        user_id=user.id,
        is_deleted=False,
    ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.organisation_id is None
    assert row.capability_code == ProviderCapabilityCode.ACCOMMODATION.value
    assert str(row.status) == ProviderCapabilityStatus.INTENT.value


def test_host_onboarding_intention_creates_no_domain_resources(db_session):
    """Declaring individual accommodation participation during host onboarding
    must create NO Property / Vehicle / HostProfile resource / Wallet /
    Booking / Payment — those stay in their owning domains."""
    from app.auth.onboarding_routes import _commit_host_onboarding
    from app.accommodation.models import Property, HostProfile
    from app.accommodation.models.booking import AccommodationBooking
    from app.accommodation.models.booking_payment import AccommodationBookingPayment
    from app.transport.models import Vehicle
    from app.wallet.models.ledger import AccountModel
    user = _make_user(db_session)
    props_before = Property.query.filter_by(owner_user_id=user.id).count()
    host_profiles_before = HostProfile.query.count()
    vehicles_before = Vehicle.query.count()
    bookings_before = AccommodationBooking.query.count()
    payments_before = AccommodationBookingPayment.query.count()
    wallets_before = AccountModel.query.filter_by(user_id=user.id).count()

    _commit_host_onboarding(user, _host_onboarding_data())
    db_session.flush()

    assert Property.query.filter_by(owner_user_id=user.id).count() == props_before
    assert HostProfile.query.count() == host_profiles_before
    assert Vehicle.query.count() == vehicles_before
    assert AccommodationBooking.query.count() == bookings_before
    assert AccommodationBookingPayment.query.count() == payments_before
    assert AccountModel.query.filter_by(user_id=user.id).count() == wallets_before
    assert ProviderParticipation.query.filter_by(
        user_id=user.id, is_deleted=False,
    ).count() == 1


def test_host_onboarding_intention_is_idempotent(db_session):
    """Re-running the host onboarding commit must not duplicate the
    ProviderParticipation row."""
    from app.auth.onboarding_routes import _commit_host_onboarding
    user = _make_user(db_session)
    _commit_host_onboarding(user, _host_onboarding_data())
    db_session.flush()
    _commit_host_onboarding(user, _host_onboarding_data())
    db_session.flush()
    assert ProviderParticipation.query.filter_by(
        user_id=user.id,
        capability_code=ProviderCapabilityCode.ACCOMMODATION.value,
        is_deleted=False,
    ).count() == 1


def test_org_onboarding_writes_provider_participation_only(db_session):
    """Organisation onboarding must write exactly one ProviderParticipation org
    row (status=INTENT — Stage 4B-3) and must NOT write any
    OrganisationProviderCapability row (no dual-write; ProviderParticipation is
    the single authoritative org capability source)."""
    from app.auth.onboarding_routes import _commit_organisation_onboarding
    user = _make_user(db_session)
    data = {
        "step1": {
            "full_name": "Stage 3B Org Owner",
            "legal_name": f"Stage3B Org {uuid.uuid4().hex[:8]}",
            "country": "UG",
            "org_type": "hotel",
            "provider_capabilities": [ProviderCapabilityCode.ACCOMMODATION.value],
        }
    }
    org = _commit_organisation_onboarding(user, data)
    db_session.flush()
    pp_org = ProviderParticipation.query.filter_by(
        organisation_id=org.id,
        capability_code=ProviderCapabilityCode.ACCOMMODATION.value,
        is_deleted=False,
    ).one()
    assert pp_org.user_id is None
    assert str(pp_org.status) == ProviderCapabilityStatus.INTENT.value
    org_cap_rows = OrganisationProviderCapability.query.filter_by(
        organisation_id=org.id,
        capability_code=ProviderCapabilityCode.ACCOMMODATION.value,
        is_deleted=False,
    ).count()
    assert org_cap_rows == 0
