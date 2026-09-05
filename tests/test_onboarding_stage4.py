"""
Stage 4 tests: Organisation Onboarding architecture.

Confirms the new onboarding model:
  Organisation Type = canonical organisation type (-> Organisation.business_category)
  + optional Provider Capabilities[] (-> provider_participations org rows,
    status=intent, via the canonical ProviderParticipation service — Stage 4B-3)

Proves:
  * organisation type persists to business_category
  * zero / one / multiple provider capabilities are all valid
  * consumer is NOT an organisation type
  * a capability creates NO member authority / role change
  * a capability creates NO domain resources / profiles
  * the organisation commit is atomic (no partial organisation on failure)
  * organisation type validation rejects invalid types
  * capability validation rejects unknown capabilities
  * /onboarding/standard remains reachable
  * organisation context / default-org behaviour is preserved
"""

import uuid
from types import SimpleNamespace

import pytest

from app.auth.onboarding_routes import (
    _commit_organisation_onboarding,
    _normalise_capabilities,
    _validate_organisation_type,
)
from app.identity.models import (
    Organisation,
    ProviderCapabilityStatus,
)
from app.identity.models.provider_participation import ProviderParticipation
from app.identity.models.organisation_member import OrganisationMember


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _new_user(app):
    """Create a bare User row (no profile/roles) for commit-helper tests."""
    from app.extensions import db
    from app.identity.models.user import User

    user = User(
        username=f"onb_{uuid.uuid4().hex[:8]}",
        email=f"onb_{uuid.uuid4().hex[:8]}@example.com",
    )
    user.set_password("TestPassword123!")
    user.is_active = True
    db.session.add(user)
    db.session.flush()
    return user


def _commit(app, capabilities=None, org_type="hotel"):
    """Run the real commit helper inside the app context."""
    from app.extensions import db

    user = _new_user(app)
    data = {
        "step1": {
            "full_name": f"Stage4 User {uuid.uuid4().hex[:6]}",
            "legal_name": f"Org {uuid.uuid4().hex[:8]}",
            "country": "UG",
            "org_type": org_type,
            "provider_capabilities": capabilities or [],
        }
    }
    org = _commit_organisation_onboarding(user, data)
    db.session.flush()
    return org, user


def _cap_codes(db, org_id):
    rows = ProviderParticipation.query.filter_by(
        organisation_id=org_id, user_id=None, is_deleted=False
    ).all()
    # force evaluation + ordering
    return [r.capability_code for r in rows]


def _org_role_names_for(db, user_id, org_id):
    membership = OrganisationMember.query.filter_by(
        user_id=user_id, organisation_id=org_id
    ).first()
    if membership is None:
        return set()
    return {our.role.name for our in membership.roles}


@pytest.fixture(autouse=True, scope="session")
def _seed_org_roles(app):
    """Seed the authoritative global org-scoped Role taxonomy.

    Uses the production seeding machinery (``seed_all``) so the test
    exercises the same source-of-truth ``ORG_ROLE_DEFS`` /
    ``ORG_ROLE_TEMPLATES`` that onboarding and ``provision_organisation_roles``
    rely on, rather than a hand-maintained role list that can drift out of
    sync with the real taxonomy.
    """
    from app.auth.seed_roles import seed_all

    with app.app_context():
        seed_all()
    # Yield OUTSIDE the with-block so the app_context is closed before tests
    # run.  Holding it open pinned flask.g across test-client requests, which
    # let g._cached_user carry a stale (detached) User into the next request
    # and triggered DetachedInstanceError on current_user.is_authenticated.


@pytest.fixture
def verified_user(app):
    from app.extensions import db
    from app.identity.models.user import User, UserRole
    from app.identity.models.roles_permission import get_or_create_role
    from app.profile.models import UserProfile

    with app.app_context():
        user_role = get_or_create_role("user", level=6)
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"customer_{uuid.uuid4().hex[:8]}",
            email=f"customer_{uuid.uuid4().hex[:8]}@example.com",
        )
        user.set_password("TestPassword123!")
        user.is_active = True
        user.is_verified = True
        user.email_verified = True
        db.session.add(user)
        db.session.flush()

        db.session.add(UserRole(user_id=user.id, role_id=user_role.id))
        db.session.add(
            UserProfile(
                user_id=user.public_id,
                full_name="Test Customer",
                profile_completed=False,
            )
        )
        db.session.commit()
        yield SimpleNamespace(
            public_id=user.public_id,
            id=user.id,
            email=user.email,
            username=user.username,
        )


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# End-to-end HTTP flow helpers
# ---------------------------------------------------------------------------

def _http_login(client, user):
    """Login via Flask-Login test helper (works with current_user on routes)."""
    from app.extensions import cache
    try:
        cache.clear()
    except Exception:
        pass
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.public_id)
        sess["_fresh"] = True


def _fresh_get(client, url, **kwargs):
    """GET that clears the Flask-Caching user cache before the request.
    The user_loader Redis cache returns a user ID, then db.session.get()
    returns a detached instance from a previous request's session scope.
    Clearing the cache forces the full DB query path which returns a
    properly-bound instance."""
    from app.extensions import cache
    try:
        cache.clear()
    except Exception:
        pass
    return client.get(url, **kwargs)


def _fresh_post(client, url, data=None, **kwargs):
    """POST that clears the Flask-Caching user cache first."""
    from app.extensions import cache
    try:
        cache.clear()
    except Exception:
        pass
    return client.post(url, data=data, **kwargs)


def _session_login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.public_id
        sess["_fresh"] = True


# ---------------------------------------------------------------------------
# 1. Organisation type persists to business_category
# ---------------------------------------------------------------------------

def test_organisation_type_persists_to_business_category(app):
    org, user = _commit(app, org_type="hotel")
    val = (
        org.business_category.value
        if hasattr(org.business_category, "value")
        else org.business_category
    )
    assert str(val) == "hotel"


def test_organisation_type_persists_football_club(app):
    org, user = _commit(app, org_type="football_team")
    val = (
        org.business_category.value
        if hasattr(org.business_category, "value")
        else org.business_category
    )
    assert str(val) == "football_team"


def test_legacy_org_type_field_untouched(app):
    """Stage 4 must not write the legacy org_type field."""
    org, user = _commit(app, org_type="hotel")
    assert org.org_type is None or org.org_type == ""


# ---------------------------------------------------------------------------
# 2. Zero provider capabilities is valid
# ---------------------------------------------------------------------------

def test_zero_capabilities_creates_organisation(app):
    from app.extensions import db
    org, user = _commit(app, capabilities=[])
    assert org is not None
    assert org.id is not None
    assert _cap_codes(db, org.id) == []


# ---------------------------------------------------------------------------
# 3. One capability creates a single row with status=intent
# ---------------------------------------------------------------------------

def test_one_capability_intent(app):
    from app.extensions import db
    org, user = _commit(app, capabilities=["accommodation"])
    rows = ProviderParticipation.query.filter_by(
        organisation_id=org.id, user_id=None, is_deleted=False
    ).all()
    assert len(rows) == 1
    assert rows[0].capability_code == "accommodation"
    assert rows[0].status == ProviderCapabilityStatus.INTENT.value

    from app.identity.models.organisation_provider_capability import (
        OrganisationProviderCapability,
    )
    assert OrganisationProviderCapability.query.filter_by(
        organisation_id=org.id, is_deleted=False
    ).count() == 0


# ---------------------------------------------------------------------------
# 4. Multiple capabilities all under the same organisation
# ---------------------------------------------------------------------------

def test_multiple_capabilities_same_organisation(app):
    from app.extensions import db
    org, user = _commit(app, capabilities=["accommodation", "transport", "venue"])
    rows = ProviderParticipation.query.filter_by(
        organisation_id=org.id, user_id=None, is_deleted=False
    ).all()
    assert {r.capability_code for r in rows} == {
        "accommodation", "transport", "venue",
    }
    # all rows belong to the SAME organisation
    assert len({r.organisation_id for r in rows}) == 1
    assert rows[0].organisation_id == org.id


# ---------------------------------------------------------------------------
# 5. Consumer is not an organisation type
# ---------------------------------------------------------------------------

def test_consumer_is_not_an_organisation_type(app):
    from app.identity.models.organization_types import OrganizationType
    values = [t.value for t in OrganizationType]
    assert "consumer" not in values


# ---------------------------------------------------------------------------
# 6. Capability does not create authority / change creator role
# ---------------------------------------------------------------------------

def test_capability_does_not_grant_authority(app):
    from app.extensions import db
    org, user = _commit(app, capabilities=["accommodation"])
    role_names = _org_role_names_for(db, user.id, org.id)
    # Creator is org_owner; a capability creates NO extra domain role.
    assert "org_owner" in role_names
    assert not (role_names - {"org_owner"})


# ---------------------------------------------------------------------------
# 7. Capability does not create domain resources / profiles
# ---------------------------------------------------------------------------

def test_capability_creates_no_domain_resources(app):
    from app.extensions import db
    from app.accommodation.models import Property
    from app.transport.models import OrganisationTransportProfile, Vehicle
    from app.events.models import Event

    org, user = _commit(
        app,
        capabilities=["accommodation", "transport", "events", "tourism", "venue"],
    )

    # Accommodation properties
    assert Property.query.filter_by(owner_org_id=org.id).count() == 0

    # Transport profiles
    assert OrganisationTransportProfile.query.filter_by(
        organisation_id=org.id
    ).count() == 0

    # Vehicles — none linked to this org
    owner_col = "owner_org_id" if hasattr(Vehicle, "owner_org_id") else None
    if owner_col:
        assert Vehicle.query.filter_by(**{owner_col: org.id}).count() == 0

    # Events — none owned by this org (organization_id is the org FK)
    assert Event.query.filter_by(organization_id=org.id).count() == 0


# ---------------------------------------------------------------------------
# 8. Atomicity — capability failure leaves no partial organisation
# ---------------------------------------------------------------------------

def test_atomicity_no_partial_organisation_on_capability_failure(app, monkeypatch):
    """
    Force capability persistence to fail after the organisation has been
    created. The commit must roll back everything — no partial organisation.
    """
    from app.extensions import db
    import app.auth.onboarding_routes as mod

    user = _new_user(app)
    legal_name = f"Atomic Org {uuid.uuid4().hex[:8]}"
    data = {
        "step1": {
            "legal_name": legal_name,
            "country": "UG",
            "org_type": "hotel",
            "provider_capabilities": ["accommodation"],
        }
    }

    # Make normalisation return a code that is NOT in the DB CHECK constraint,
    # so the capability row fails at flush time, after org creation has begun.
    monkeypatch.setattr(
        mod,
        "_normalise_capabilities",
        lambda raw: ["capability_that_violates_check_constraint"],
    )

    with pytest.raises(Exception):
        _commit_organisation_onboarding(user, data)

    db.session.rollback()  # clear the rolled-back session state

    # No partial organisation may remain.
    assert Organisation.query.filter_by(legal_name=legal_name).count() == 0


# ---------------------------------------------------------------------------
# 9. Invalid organisation type rejected
# ---------------------------------------------------------------------------

def test_invalid_organisation_type_rejected(app):
    with pytest.raises(ValueError):
        _validate_organisation_type("not_a_real_type")


def test_missing_organisation_type_rejected(app):
    from app.extensions import db
    user = _new_user(app)
    data = {
        "step1": {
            "legal_name": f"Org {uuid.uuid4().hex[:8]}",
            "country": "UG",
            "org_type": "",
            "provider_capabilities": [],
        }
    }
    with pytest.raises(ValueError):
        _commit_organisation_onboarding(user, data)
    db.session.rollback()


# ---------------------------------------------------------------------------
# 10. Invalid / malformed capability handling
# ---------------------------------------------------------------------------

def test_unknown_capability_dropped(app):
    assert _normalise_capabilities(["accommodation", "bogus", "transport"]) == [
        "accommodation", "transport",
    ]


def test_capability_duplicates_normalised(app):
    assert _normalise_capabilities(["accommodation", "accommodation", "venue"]) == [
        "accommodation", "venue",
    ]


def test_malformed_capability_normalised(app):
    assert _normalise_capabilities([None, "", "  accommodation  "]) == ["accommodation"]


# ---------------------------------------------------------------------------
# 11. /onboarding/standard remains reachable
# ---------------------------------------------------------------------------

def test_standard_onboarding_reachable(client, verified_user):
    _session_login(client, verified_user)
    response = client.get("/onboarding/standard")
    assert response.status_code in (200, 302)


# ---------------------------------------------------------------------------
# 12. Context establishment preserved after creation
# ---------------------------------------------------------------------------

def test_context_establishment_preserved(app):
    from app.extensions import db
    from app.identity.models.user import User

    org, user = _commit(app, capabilities=["transport"])
    db_user = db.session.get(User, user.id)
    assert db_user.default_org_id == org.id


# ---------------------------------------------------------------------------
# 12b. Optional tax_id — blank means NULL (not empty string)
# ---------------------------------------------------------------------------
# Domain contract: a missing/blank organisation tax ID is "not provided" and
# must be persisted as SQL NULL, so the (country, tax_id) unique constraint
# does not reject multiple orgs in the same country that have no tax ID.
# A real tax ID stays a string; same country + same real tax ID is still
# rejected.

def _commit_tax_id(app, tax_id):
    """Commit an onboarding org with an explicit tax_id value (or absence)."""
    from app.extensions import db
    from app.identity.models.user import User

    user = _new_user(app)
    data = {
        "step1": {
            "full_name": f"TaxID User {uuid.uuid4().hex[:6]}",
            "legal_name": f"TaxOrg {uuid.uuid4().hex[:8]}",
            "country": "UG",
            "org_type": "hotel",
            "provider_capabilities": [],
        }
    }
    if tax_id is not None:
        data["step1"]["tax_id"] = tax_id
    org = _commit_organisation_onboarding(user, data)
    db.session.flush()
    db_user = db.session.get(User, user.id)
    return org, user, db_user


def test_blank_tax_id_stored_as_none(app):
    """Blank tax ID input must persist as None (SQL NULL)."""
    from app.extensions import db
    org, user, _ = _commit_tax_id(app, "")
    # Re-load from DB to force a bare column read
    db.session.expire(org)
    assert org.tax_id is None


def test_absent_tax_id_stored_as_none(app):
    """No tax_id key at all must persist as None."""
    from app.extensions import db
    org, user, _ = _commit_tax_id(app, None)
    db.session.expire(org)
    assert org.tax_id is None


def test_multiple_orgs_same_country_blank_tax_id_allowed(app):
    """Two organisations in the same country with no tax ID must both persist
    (NULLs are distinct to the unique constraint)."""
    from app.extensions import db
    org1, u1, _ = _commit_tax_id(app, "")
    org2, u2, _ = _commit_tax_id(app, "")
    assert org1.id != org2.id


def test_same_country_same_real_tax_id_rejected(app):
    """Two organisations in the same country with the SAME real tax ID must
    be rejected by the unique constraint."""
    from app.extensions import db
    from sqlalchemy.exc import IntegrityError

    real_tax = f"TIN-{uuid.uuid4().hex[:8]}"
    org1, u1, _ = _commit_tax_id(app, real_tax)
    db.session.commit()

    user2 = _new_user(app)
    data = {
        "step1": {
            "full_name": f"TaxID User {uuid.uuid4().hex[:6]}",
            "legal_name": f"TaxOrg {uuid.uuid4().hex[:8]}",
            "country": "UG",
            "org_type": "hotel",
            "provider_capabilities": [],
            "tax_id": real_tax,
        }
    }
    with pytest.raises(IntegrityError):
        _commit_organisation_onboarding(user2, data)
    db.session.rollback()


def test_same_country_different_real_tax_ids_allowed(app):
    """Two organisations in the same country with DIFFERENT real tax IDs must
    both persist."""
    from app.extensions import db
    org1, u1, _ = _commit_tax_id(app, f"TIN-{uuid.uuid4().hex[:8]}")
    org2, u2, _ = _commit_tax_id(app, f"TIN-{uuid.uuid4().hex[:8]}")
    assert org1.id != org2.id


# ---------------------------------------------------------------------------
# 13. End-to-end HTTP flow tests
# ---------------------------------------------------------------------------
# These exercise the real HTTP onboarding wizard through every route,
# verifying the full lifecycle from login through org creation, role
# provisioning, capability persistence, context establishment and the
# final redirect to the organisation dashboard.

class TestEndToEndOrganisationOnboarding:
    """Full HTTP-level onboarding wizard tests."""

    def _make_e2e_user(self, app):
        """Create a fresh user for E2E testing within a persistent app context."""
        from app.extensions import db
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import get_or_create_role
        from app.profile.models import UserProfile
        ns = SimpleNamespace()

        with app.app_context():
            user_role = get_or_create_role("user", level=6)
            user = User(
                public_id=str(uuid.uuid4()),
                username=f"e2e_{uuid.uuid4().hex[:8]}",
                email=f"e2e_{uuid.uuid4().hex[:8]}@example.com",
            )
            user.set_password("TestPassword123!")
            user.is_active = True
            user.is_verified = True
            user.email_verified = True
            db.session.add(user)
            db.session.flush()
            db.session.add(UserRole(user_id=user.id, role_id=user_role.id))
            db.session.add(
                UserProfile(
                    user_id=user.public_id,
                    full_name="E2E Test Customer",
                    profile_completed=False,
                )
            )
            db.session.commit()
            ns.public_id = user.public_id
            ns.id = user.id
            ns.email = user.email
            ns.username = user.username
        return ns

    def test_complete_flow_with_capabilities(self, app, client):
        """Complete the entire onboarding wizard via HTTP POST/GET:

        choose → choose/organisation → POST type+caps → step1 → POST →
        step2 → POST → redirect to org dashboard.

        Verify: ONE Organisation created, business_category correct,
        capability rows exist with status=intent, creator is org_owner,
        OrgUserRole.role_id references org_roles.id, default_org_id set,
        session context set, NO wallet created.
        """
        from app.extensions import db
        from app.identity.models import Organisation, ProviderCapabilityStatus
        from app.identity.models.organisation_member import OrganisationMember, OrgRole, OrgUserRole
        from app.identity.models.organisation_provider_capability import (
            OrganisationProviderCapability,
        )
        from app.identity.models.provider_participation import ProviderParticipation
        from app.identity.models.user import User
        import uuid as _uuid

        verified_user = self._make_e2e_user(app)
        _http_login(client, verified_user)

        # Record starting counts
        from app.wallet.models.ledger import AccountModel
        with app.app_context():
            org_count_before = Organisation.query.count()
            accounts_before = AccountModel.query.count()

        # Step 0: GET /onboarding/choose
        r = _fresh_get(client, "/onboarding/choose")
        assert r.status_code == 200
        assert b"Individual" in r.data
        assert b"Organisation" in r.data

        # Step 0b: GET /onboarding/choose/organisation
        r = _fresh_get(client, "/onboarding/choose/organisation")
        assert r.status_code == 200
        assert b"Set up your organisation" in r.data
        assert b"accommodation" in r.data
        assert b"transport" in r.data

        # POST organisation type + capabilities → redirect to step 1
        r = _fresh_post(
            client,
            "/onboarding/organisation",
            data={
                "org_type": "hotel",
                "provider_capabilities": ["accommodation", "transport"],
            },
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "/onboarding/organisation/step/1" in r.headers["Location"]

        # GET step 1 → details form
        r = _fresh_get(client, "/onboarding/organisation/step/1")
        assert r.status_code == 200
        assert b"Organisation" in r.data
        assert b"Details" in r.data

        # POST step 1 → redirect to step 2
        unique_suffix = _uuid.uuid4().hex[:8]
        r = _fresh_post(
            client,
            "/onboarding/organisation/step/1",
            data={
                "full_name": "E2E Test User",
                "legal_name": f"E2E Hotel {unique_suffix}",
                "country": "UG",
                "contact_email": f"e2e_{unique_suffix}@test.com",
            },
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "/onboarding/organisation/step/2" in r.headers["Location"]

        # GET step 2 → confirm page
        r = _fresh_get(client, "/onboarding/organisation/step/2")
        assert r.status_code == 200
        assert b"Confirm" in r.data
        assert b"E2E Hotel" in r.data

        # POST step 2 → commit → redirect to org dashboard
        r = _fresh_post(
            client,
            "/onboarding/organisation/step/2",
            data={"confirm": "on"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "/org/" in r.headers["Location"]

        # ---- Verify database state ----
        with app.app_context():
            # 1. ONE new Organisation created
            org_count_after = Organisation.query.count()
            assert org_count_after == org_count_before + 1, (
                f"Expected +1 Organisation, got {org_count_after - org_count_before}"
            )

            org = Organisation.query.order_by(Organisation.id.desc()).first()

            # 2. business_category = hotel
            bc = org.business_category
            bc_val = bc.value if hasattr(bc, "value") else bc
            assert str(bc_val) == "hotel", f"Expected 'hotel', got {bc_val!r}"

            # 3. Two capability rows with status=intent (PP — no OPC writes)
            caps = ProviderParticipation.query.filter_by(
                organisation_id=org.id, user_id=None, is_deleted=False,
            ).all()
            assert len(caps) == 2, f"Expected 2 capabilities, got {len(caps)}"
            cap_codes = sorted(c.capability_code for c in caps)
            assert cap_codes == ["accommodation", "transport"]
            for c in caps:
                assert c.status == ProviderCapabilityStatus.INTENT.value
            assert OrganisationProviderCapability.query.filter_by(
                organisation_id=org.id, is_deleted=False,
            ).count() == 0

            # 4. Creator membership exists
            member = OrganisationMember.query.filter_by(
                user_id=verified_user.id, organisation_id=org.id,
            ).first()
            assert member is not None, "Creator OrganisationMember not found"

            # 5. Creator is org_owner — role_id references org_roles.id
            org_owner_role = OrgRole.query.filter_by(
                organisation_id=org.id, name="org_owner",
            ).first()
            assert org_owner_role is not None, "org_owner OrgRole not found"

            our = OrgUserRole.query.filter_by(
                organisation_member_id=member.id,
                role_id=org_owner_role.id,
            ).first()
            assert our is not None, "OrgUserRole member→org_owner not found"

            # 6. default_org_id set
            db_user = db.session.get(User, verified_user.id)
            assert db_user.default_org_id == org.id

            # 7. Session context set (verified via redirect URL contains /org/)
            # Already asserted above via 302 Location header

            # 8. NO wallet / AccountModel rows created by onboarding
            accounts_after = AccountModel.query.count()
            assert accounts_after == accounts_before, (
                f"Onboarding must not create wallet rows; "
                f"before={accounts_before} after={accounts_after}"
            )

    def test_zero_capabilities_flow(self, app, client):
        """Organisation type + zero provider capabilities must be valid.
        Verify: organisation created, zero ProviderParticipation capability rows."""
        from app.extensions import db
        from app.identity.models import Organisation
        from app.identity.models.organisation_member import OrganisationMember, OrgRole, OrgUserRole
        from app.identity.models.organisation_provider_capability import (
            OrganisationProviderCapability,
        )
        from app.identity.models.provider_participation import ProviderParticipation
        from app.identity.models.user import User
        import uuid as _uuid

        verified_user = self._make_e2e_user(app)
        _http_login(client, verified_user)

        unique_suffix = _uuid.uuid4().hex[:8]

        # POST type with no capabilities
        r = _fresh_post(
            client,
            "/onboarding/organisation",
            data={"org_type": "sports_team"},
            follow_redirects=False,
        )
        assert r.status_code == 302

        # POST step 1
        r = _fresh_post(
            client,
            "/onboarding/organisation/step/1",
            data={
                "full_name": "Zero Cap User",
                "legal_name": f"Zero Cap Club {unique_suffix}",
                "country": "UG",
            },
            follow_redirects=False,
        )
        assert r.status_code == 302

        # POST step 2
        r = _fresh_post(
            client,
            "/onboarding/organisation/step/2",
            data={"confirm": "on"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "/org/" in r.headers["Location"]

        with app.app_context():
            org = Organisation.query.order_by(Organisation.id.desc()).first()
            assert org is not None

            caps = ProviderParticipation.query.filter_by(
                organisation_id=org.id, user_id=None, is_deleted=False,
            ).all()
            assert len(caps) == 0, (
                f"Zero-capability onboarding must produce 0 rows; got {len(caps)}"
            )
            assert OrganisationProviderCapability.query.filter_by(
                organisation_id=org.id, is_deleted=False,
            ).count() == 0

            # Verify creator is org_owner
            member = OrganisationMember.query.filter_by(
                user_id=verified_user.id, organisation_id=org.id,
            ).first()
            assert member is not None

            org_owner_role = OrgRole.query.filter_by(
                organisation_id=org.id, name="org_owner",
            ).first()
            assert org_owner_role is not None

            our = OrgUserRole.query.filter_by(
                organisation_member_id=member.id,
                role_id=org_owner_role.id,
            ).first()
            assert our is not None

    def test_multiple_capabilities_no_duplicates(self, app, client):
        """Selecting accommodation + transport + tourism must produce exactly
        3 ProviderParticipation rows with no duplicates."""
        from app.extensions import db
        from app.identity.models import Organisation, ProviderCapabilityStatus
        from app.identity.models.organisation_provider_capability import (
            OrganisationProviderCapability,
        )
        from app.identity.models.provider_participation import ProviderParticipation
        import uuid as _uuid

        verified_user = self._make_e2e_user(app)
        _http_login(client, verified_user)

        unique_suffix = _uuid.uuid4().hex[:8]

        # POST type + 3 capabilities
        r = _fresh_post(
            client,
            "/onboarding/organisation",
            data={
                "org_type": "tour_operator",
                "provider_capabilities": ["accommodation", "transport", "tourism"],
            },
            follow_redirects=False,
        )
        assert r.status_code == 302

        # POST step 1
        r = _fresh_post(
            client,
            "/onboarding/organisation/step/1",
            data={
                "full_name": "Multi Cap User",
                "legal_name": f"Multi Cap TO {unique_suffix}",
                "country": "UG",
            },
            follow_redirects=False,
        )
        assert r.status_code == 302

        # POST step 2
        r = _fresh_post(
            client,
            "/onboarding/organisation/step/2",
            data={"confirm": "on"},
            follow_redirects=False,
        )
        assert r.status_code == 302

        with app.app_context():
            org = Organisation.query.order_by(Organisation.id.desc()).first()
            caps = ProviderParticipation.query.filter_by(
                organisation_id=org.id, user_id=None, is_deleted=False,
            ).all()
            assert len(caps) == 3
            codes = sorted(c.capability_code for c in caps)
            assert codes == ["accommodation", "tourism", "transport"]
            for c in caps:
                assert c.status == ProviderCapabilityStatus.INTENT.value
            assert OrganisationProviderCapability.query.filter_by(
                organisation_id=org.id, is_deleted=False,
            ).count() == 0

    def test_invalid_type_rejected_no_partial_org(self, app, client):
        """POSTing an invalid organisation type must redirect back to the
        chooser with a flash error.  No Organisation or capability rows
        must be created."""
        from app.identity.models import Organisation

        verified_user = self._make_e2e_user(app)
        _http_login(client, verified_user)

        with app.app_context():
            org_count_before = Organisation.query.count()

        # POST invalid type
        r = _fresh_post(
            client,
            "/onboarding/organisation",
            data={
                "org_type": "consumer",
                "provider_capabilities": ["accommodation"],
            },
            follow_redirects=False,
        )
        # Must redirect back to chooser (type validation failed)
        assert r.status_code == 302
        assert "/onboarding/choose/organisation" in r.headers["Location"]

        with app.app_context():
            org_count_after = Organisation.query.count()
            assert org_count_after == org_count_before, (
                "Invalid type must not create any Organisation"
            )

    def test_step1_without_type_redirects_to_chooser(self, app, client):
        """GET /onboarding/organisation/step/1 with no org_type in session
        must redirect to the chooser (type-first flow)."""
        verified_user = self._make_e2e_user(app)
        _http_login(client, verified_user)

        # Clear any session state first
        with client.session_transaction() as sess:
            sess.pop("org_onboarding_type", None)
            sess.pop("org_onboarding_capabilities", None)
            sess.pop("org_onboarding", None)

        r = _fresh_get(client, "/onboarding/organisation/step/1")
        assert r.status_code == 302
        assert "/onboarding/choose/organisation" in r.headers["Location"]

    def test_all_roles_provisioned_by_onboarding(self, app, client):
        """Onboarding must provision the complete authoritative set of
        organisation roles from ``ORG_ROLE_TEMPLATES``, not just
        ``org_owner``.  The expected set is taken from the production
        source of truth rather than duplicated here."""
        from app.identity.models import Organisation
        from app.identity.models.organisation_member import OrgRole, OrgUserRole, OrganisationMember
        from app.auth.seed_roles import ORG_ROLE_TEMPLATES
        import uuid as _uuid

        verified_user = self._make_e2e_user(app)
        _http_login(client, verified_user)

        unique_suffix = _uuid.uuid4().hex[:8]

        # Complete full wizard
        _fresh_post(
            client,
            "/onboarding/organisation",
            data={"org_type": "corporate"},
            follow_redirects=False,
        )
        _fresh_post(
            client,
            "/onboarding/organisation/step/1",
            data={
                "full_name": "Roles Test User",
                "legal_name": f"Roles Corp {unique_suffix}",
                "country": "UG",
            },
            follow_redirects=False,
        )
        r = _fresh_post(
            client,
            "/onboarding/organisation/step/2",
            data={"confirm": "on"},
            follow_redirects=False,
        )
        assert r.status_code == 302

        with app.app_context():
            org = Organisation.query.order_by(Organisation.id.desc()).first()

            # All authoritative org roles must exist for this organisation
            expected_roles = set(ORG_ROLE_TEMPLATES.keys())
            actual_roles = {r.name for r in OrgRole.query.filter_by(
                organisation_id=org.id,
            ).all()}
            assert actual_roles == expected_roles, (
                f"Expected {expected_roles}, got {actual_roles}"
            )

            # Creator must be assigned org_owner
            member = OrganisationMember.query.filter_by(
                user_id=verified_user.id, organisation_id=org.id,
            ).first()
            assert member is not None
            owner_role = OrgRole.query.filter_by(
                organisation_id=org.id, name="org_owner",
            ).first()
            our = OrgUserRole.query.filter_by(
                organisation_member_id=member.id,
                role_id=owner_role.id,
            ).first()
            assert our is not None
