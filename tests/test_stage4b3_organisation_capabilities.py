"""
Stage 4B-3 architectural-invariant tests.

Prove that after re-pointing organisation provider participation onto the
canonical ProviderParticipation service, the following invariants hold:

  1. An organisation declaration writes EXACTLY ONE provider_participations
     row with status=INTENT (idempotent on re-declaration).
  2. No org_provider_capabilities (OPC) row is ever written by organisation
     onboarding or the capability API (no dual-write).
  3. Subject correctness: organisation rows set organisation_id and keep
     user_id NULL (ck_provider_participations_single_subject).
  4. API compatibility: the capability API exposes the PUBLIC organisation
     identifier (org.org_id) and never serialises internal BIGINT ids.
  5. Authority matrix preserved: active member may declare; non-member may
     not; org_owner only activates/deactivates; org_owner or platform
     super_admin suspends/revokes.
  6. Activation is an explicit lifecycle toggle, independent of KYB
     eligibility (activation changes no KYB state and grants no domain right).
  7. Declaring/activating creates no domain resources (Property / Vehicle /
     Event / Wallet / Booking / domain profiles).

Run: pytest tests/test_stage4b3_organisation_capabilities.py -q
"""

import uuid

import pytest

from app.extensions import db
from app.identity.models import (
    Organisation,
    ProviderCapabilityCode,
    ProviderCapabilityStatus,
)
from app.identity.models.organisation_member import (
    OrganisationMember,
    OrgRole,
    OrgUserRole,
)
from app.identity.models.organisation_provider_capability import (
    OrganisationProviderCapability,
)
from app.identity.models.provider_participation import ProviderParticipation
from app.identity.services.provider_participation_service import (
    ParticipationPermissionError,
    ParticipationTransitionError,
    activate_organisation_intention,
    create_organisation_intention,
    deactivate_organisation_intention,
    list_organisation_intentions,
    revoke_organisation_intention,
    suspend_organisation_intention,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(session, suffix=None):
    suffix = suffix or uuid.uuid4().hex[:8]
    org = Organisation(
        legal_name=f"Stage4B3 Org {suffix}",
        org_id=str(uuid.uuid4()),
        country="UG",
        verification_status="verified",
    )
    session.add(org)
    session.flush()
    return org


def _make_user(session, suffix=None):
    from app.identity.models.user import User
    suffix = suffix or uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"s4b3_{suffix}",
        email=f"s4b3_{suffix}@example.com",
    )
    user.set_password("TestPassword123!")
    user.is_active = True
    user.is_verified = True
    user.email_verified = True
    session.add(user)
    session.flush()
    return user


def _assign_org_role(session, user, org, role_name):
    from app.identity.services.organisation_role_provisioning import (
        provision_organisation_roles,
    )
    provision_organisation_roles(org, commit=False)
    session.flush()

    membership = OrganisationMember(
        user_id=user.id,
        organisation_id=org.id,
        is_active=True,
    )
    session.add(membership)
    session.flush()

    org_role = OrgRole.query.filter_by(
        organisation_id=org.id,
        name=role_name,
    ).first()
    assert org_role is not None

    session.add(
        OrgUserRole(
            organisation_member_id=membership.id,
            role_id=org_role.id,
            assigned_by=user.id,
        )
    )
    session.flush()
    return membership


def _make_owner(session, org):
    user = _make_user(session, suffix=f"owner_{uuid.uuid4().hex[:8]}")
    _assign_org_role(session, user, org, "org_owner")
    return user


def _make_member(session, org):
    user = _make_user(session, suffix=f"member_{uuid.uuid4().hex[:8]}")
    _assign_org_role(session, user, org, "org_member")
    return user


def _make_super_admin(session):
    from app.identity.models.roles_permission import get_or_create_role
    from app.identity.models.user import UserRole
    admin_role = get_or_create_role("super_admin", level=2)
    admin = _make_user(session, suffix="admin")
    session.add(UserRole(user_id=admin.id, role_id=admin_role.id))
    session.flush()
    return admin


def _org_pp_count(org_id, code=None):
    q = ProviderParticipation.query.filter_by(
        organisation_id=org_id, user_id=None, is_deleted=False,
    )
    if code:
        q = q.filter_by(capability_code=code)
    return q.count()


def _opc_count(org_id):
    return OrganisationProviderCapability.query.filter_by(
        organisation_id=org_id, is_deleted=False,
    ).count()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _seed_org_roles(app):
    from app.auth.seed_roles import seed_all
    with app.app_context():
        seed_all()


@pytest.fixture
def org(db_session):
    return _make_org(db_session)


@pytest.fixture
def owner_user(db_session, org):
    return _make_owner(db_session, org)


@pytest.fixture
def member_user(db_session, org):
    return _make_member(db_session, org)


# ===========================================================================
# 1. Declaration → EXACTLY ONE PP org row at INTENT (idempotent)
# ===========================================================================

def test_declaration_creates_exactly_one_pp_org_row_intent(db_session, org, member_user):
    row = create_organisation_intention(
        member_user, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    assert str(row.status) == ProviderCapabilityStatus.INTENT.value
    assert _org_pp_count(org.id, ProviderCapabilityCode.ACCOMMODATION.value) == 1

    # Re-declaration is idempotent — still exactly one row.
    create_organisation_intention(
        member_user, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    assert _org_pp_count(org.id, ProviderCapabilityCode.ACCOMMODATION.value) == 1


# ===========================================================================
# 2. No OPC write (organisation onboarding + capability API are PP-only)
# ===========================================================================

def test_no_opc_written_on_declaration(db_session, org, member_user):
    create_organisation_intention(
        member_user, org.id, ProviderCapabilityCode.TRANSPORT.value,
    )
    db_session.flush()
    assert _org_pp_count(org.id, ProviderCapabilityCode.TRANSPORT.value) == 1
    assert _opc_count(org.id) == 0


def test_no_opc_written_through_organisation_onboarding(app):
    from app.auth.onboarding_routes import _commit_organisation_onboarding
    from app.identity.models.user import User

    with app.app_context():
        user = User(
            username=f"ob_{uuid.uuid4().hex[:8]}",
            email=f"ob_{uuid.uuid4().hex[:8]}@example.com",
        )
        user.set_password("TestPassword123!")
        user.is_active = True
        db.session.add(user)
        db.session.flush()
        data = {
            "step1": {
                "full_name": "Invariant Onboarder",
                "legal_name": f"Invariant Org {uuid.uuid4().hex[:8]}",
                "country": "UG",
                "org_type": "hotel",
                "provider_capabilities": [ProviderCapabilityCode.ACCOMMODATION.value],
            }
        }
        org = _commit_organisation_onboarding(user, data)
        db.session.flush()
        assert _org_pp_count(org.id, ProviderCapabilityCode.ACCOMMODATION.value) == 1
        assert _opc_count(org.id) == 0


# ===========================================================================
# 3. Subject correctness (org_id NOT NULL, user_id NULL)
# ===========================================================================

def test_org_row_subject_is_correct(db_session, org, member_user):
    row = create_organisation_intention(
        member_user, org.id, ProviderCapabilityCode.EVENTS.value,
    )
    db_session.flush()
    assert row.organisation_id == org.id
    assert row.user_id is None
    assert row.subject_type_computed == "organisation"

    # Co-signed users must never appear in org rows.
    org_rows = ProviderParticipation.query.filter_by(
        organisation_id=org.id, is_deleted=False,
    ).all()
    assert all(r.user_id is None for r in org_rows)


# ===========================================================================
# 4. API compatibility — public org_id, no internal ids
# ===========================================================================

def _login(app, client, user):
    with app.app_context():
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.public_id)
            sess["_fresh"] = True


def test_api_list_returns_public_org_id_and_no_internal_ids(
    app, client, db_session, owner_user, org,
):
    internal_id = org.id
    public_id = str(org.org_id)
    row = create_organisation_intention(
        owner_user, internal_id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()

    _login(app, client, owner_user)
    r = client.get(f"/org/{public_id}/capabilities")
    assert r.status_code == 200
    data = r.get_json()
    assert data["organisation_id"] == public_id
    caps = data["capabilities"]
    assert len(caps) == 1
    assert caps[0]["subject_type"] == "organisation"
    assert caps[0]["capability_code"] == "accommodation"
    assert caps[0]["status"] == "intent"
    payload = str(data)
    assert "organisation_id" not in str(caps[0]), payload
    assert f'"{internal_id}"' not in payload
    assert '"id"' not in str(caps[0])


def test_api_activate_returns_public_org_id_and_no_internal_ids(
    app, client, db_session, owner_user, org,
):
    internal_id = org.id
    public_id = str(org.org_id)
    row = create_organisation_intention(
        owner_user, internal_id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()

    _login(app, client, owner_user)
    r = client.post(f"/org/{public_id}/capabilities/accommodation/activate")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["organisation_id"] == public_id
    assert payload["capability"]["status"] == "activated"
    assert '"id"' not in str(payload["capability"])


# ===========================================================================
# 5. Authority matrix
# ===========================================================================

def test_active_member_can_declare(db_session, org, member_user):
    create_organisation_intention(
        member_user, org.id, ProviderCapabilityCode.VENUE.value,
    )
    db_session.flush()
    assert _org_pp_count(org.id, ProviderCapabilityCode.VENUE.value) == 1


def test_non_member_cannot_declare(db_session, org):
    outsider = _make_user(db_session, suffix="outsider")
    with pytest.raises(ParticipationPermissionError):
        create_organisation_intention(
            outsider, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
        )
    db_session.rollback()


def test_owner_activates_member_denied(db_session, org, owner_user, member_user):
    create_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    with pytest.raises(ParticipationPermissionError):
        activate_organisation_intention(
            member_user, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
        )
    row = activate_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    assert str(row.status) == ProviderCapabilityStatus.ACTIVATED.value


def test_owner_or_admin_may_suspend_and_revoke(db_session, org, owner_user):
    create_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.TRANSPORT.value,
    )
    db_session.flush()
    admin = _make_super_admin(db_session)
    membership = OrganisationMember(
        user_id=admin.id,
        organisation_id=org.id,
        is_active=True,
    )
    db_session.add(membership)
    db_session.flush()

    row = activate_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.TRANSPORT.value,
    )
    assert str(row.status) == ProviderCapabilityStatus.ACTIVATED.value

    row = suspend_organisation_intention(
        admin, org.id, ProviderCapabilityCode.TRANSPORT.value,
    )
    assert str(row.status) == ProviderCapabilityStatus.SUSPENDED.value

    row = revoke_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.TRANSPORT.value,
    )
    assert str(row.status) == ProviderCapabilityStatus.REVOKED.value


def test_owner_cannot_activate_other_org(db_session):
    org_a = _make_org(db_session, suffix="A")
    org_b = _make_org(db_session, suffix="B")
    owner_a = _make_owner(db_session, org_a)
    member_b = _make_member(db_session, org_b)
    create_organisation_intention(
        member_b, org_b.id, ProviderCapabilityCode.EVENTS.value,
    )
    db_session.flush()
    with pytest.raises(ParticipationPermissionError):
        activate_organisation_intention(
            owner_a, org_b.id, ProviderCapabilityCode.EVENTS.value,
        )
    db_session.rollback()


# ===========================================================================
# 6. Activation is a lifecycle toggle, independent of KYB eligibility
# ===========================================================================

def test_activation_is_lifecycle_toggle_and_kyb_independent(
    db_session, org, owner_user,
):
    from app.identity.models.kyb import OrganisationKYBCheck, OrganisationUBO

    kyb_before = (
        OrganisationKYBCheck.query.filter_by(organisation_id=org.id).count()
        + OrganisationUBO.query.filter_by(organisation_id=org.id).count()
    )
    kyb_status_before = org.verification_status

    create_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    row = activate_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()

    assert str(row.status) == ProviderCapabilityStatus.ACTIVATED.value
    # KYB is untouched: no eligibility state is written or auto-granted.
    kyb_after = (
        OrganisationKYBCheck.query.filter_by(organisation_id=org.id).count()
        + OrganisationUBO.query.filter_by(organisation_id=org.id).count()
    )
    assert kyb_after == kyb_before
    assert org.verification_status == kyb_status_before

    from app.identity.services.organisation_kyb_service import OrganisationKYBService
    assert callable(getattr(OrganisationKYBService, "compute_status", None))


# ===========================================================================
# 7. No domain resources created by declaration or activation
# ===========================================================================

def test_declare_and_activate_create_no_domain_resources(db_session, org, owner_user):
    from app.accommodation.models.property import Property
    from app.identity.models.kyb import OrganisationKYBCheck, OrganisationUBO
    from app.transport.models import OrganisationTransportProfile
    from app.wallet.models.ledger import AccountModel

    baseline = {
        "properties": Property.query.count(),
        "transport_profiles": OrganisationTransportProfile.query.count(),
        "wallets": AccountModel.query.count(),
        "kyb_checks": OrganisationKYBCheck.query.count(),
        "ubos": OrganisationUBO.query.count(),
    }

    create_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    activate_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()

    assert Property.query.count() == baseline["properties"]
    assert OrganisationTransportProfile.query.count() == baseline["transport_profiles"]
    assert AccountModel.query.count() == baseline["wallets"]
    assert OrganisationKYBCheck.query.count() == baseline["kyb_checks"]
    assert OrganisationUBO.query.count() == baseline["ubos"]
    assert _org_pp_count(org.id, ProviderCapabilityCode.ACCOMMODATION.value) == 1


def test_participation_does_not_grant_wallet_authority(db_session, org, owner_user):
    from app.wallet.models.ledger import AccountModel

    create_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    activate_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.ACCOMMODATION.value,
    )
    db_session.flush()
    # Row belongs to the owner's org, never to the owner-as-individual.
    assert AccountModel.query.filter_by(user_id=owner_user.id).count() == 0


# ===========================================================================
# Invalid transition still rejected through the PP-backed path
# ===========================================================================

def test_invalid_transition_still_rejected(db_session, org, owner_user):
    # INTENT -> SUSPENDED is not in the frozen transition table.
    create_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.TRANSPORT.value,
    )
    db_session.flush()
    with pytest.raises(ParticipationTransitionError):
        suspend_organisation_intention(
            owner_user, org.id, ProviderCapabilityCode.TRANSPORT.value,
        )
    # The valid path INTENT -> ACTIVATED -> SUSPENDED still works.
    create_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.TRANSPORT.value,
    )
    db_session.flush()
    activate_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.TRANSPORT.value,
    )
    db_session.flush()
    row = suspend_organisation_intention(
        owner_user, org.id, ProviderCapabilityCode.TRANSPORT.value,
    )
    assert str(row.status) == ProviderCapabilityStatus.SUSPENDED.value


def test_list_returns_pp_org_rows(db_session, org, owner_user):
    for code in ("accommodation", "transport", "venue"):
        create_organisation_intention(owner_user, org.id, code)
    db_session.flush()
    rows = list_organisation_intentions(org.id)
    assert {r.capability_code for r in rows} == {"accommodation", "transport", "venue"}
    assert all(r.user_id is None for r in rows)