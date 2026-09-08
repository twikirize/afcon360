"""Stage 4B-2 / Phase 2 tests: G-3 individual capability API + two-gate rule.

Covers:
  * Canonical read-only ``is_capability_operational()`` helper semantics
  * G-3 self-only individual capability REST API
    - list / activate / deactivate
    - self-only subject isolation (public_id responses, no internal ids)
    - invalid code -> 400, undeclared -> 404, invalid transition -> 409
    - individual ACCOMMODATION activation is eligibility-gated (can_host)
    - other individual codes stay lifecycle-only (e.g. transport)
  * Two-gate operational rule at ``host_create_listing``
    - eligible + not activated  -> blocked (flash + redirect to host dashboard)
    - eligible + activated      -> allowed (listing form renders)
    - activated + later-ineligible -> blocked at the eligibility half
  * Invariants: activation creates no domain resources / roles / permissions

Run: pytest tests/test_stage4b2_capability_enforcement.py -v
"""

import json
import uuid
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.identity.models.organisation_provider_capability import (
    ProviderCapabilityCode,
    ProviderCapabilityStatus,
)
from app.identity.models.roles_permission import get_or_create_role
from app.identity.models.user import User, UserRole
from app.identity.services.provider_participation_service import (
    create_individual_intention,
    is_capability_operational,
)
from app.profile.models import UserProfile


# ---------------------------------------------------------------------------
# Fixtures (isolated app contexts — HTTP tests must NOT pull db_session)
# ---------------------------------------------------------------------------

def _make_user(app, *, owner=False):
    with app.app_context():
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"u_{uuid.uuid4().hex[:8]}",
            email=f"u_{uuid.uuid4().hex[:8]}@example.com",
        )
        user.set_password("TestPassword123!")
        user.is_active = True
        user.is_verified = True
        user.email_verified = True
        db.session.add(user)
        db.session.flush()

        role_name, level = ("owner", 1) if owner else ("user", 6)
        role = get_or_create_role(role_name, level=level)
        db.session.add(UserRole(user_id=user.id, role_id=role.id))
        # Owner bypasses the KYC/profile eligibility gates (can_host True);
        # the plain user has no verification record -> can_host False.
        db.session.add(
            UserProfile(
                user_id=user.public_id,
                full_name="Test User",
                profile_completed=owner,
            )
        )
        db.session.commit()
        return SimpleNamespace(
            id=user.id,
            public_id=user.public_id,
            username=user.username,
            email=user.email,
        )


@pytest.fixture
def plain_user(app):
    """A verified, non-owner user: NOT eligible to host (no KYC verification)."""
    return _make_user(app, owner=False)


@pytest.fixture
def eligible_host(app):
    """An owner-role user: can_host() returns True (owner eligibility bypass)."""
    return _make_user(app, owner=True)


@pytest.fixture
def client(app):
    """Function-scoped client — avoids cross-test session leakage."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.public_id)
        sess["_fresh"] = True


def _set_host_context(client, public_id):
    with client.session_transaction() as sess:
        sess["active_context_type"] = "accommodation_host"
        sess["active_context_id"] = str(public_id)
        sess["active_role"] = "accommodation_host"


@pytest.fixture
def accommodation_module_on(app):
    """Temporarily enable the accommodation module for HTTP tests.

    Every request triggers refresh_module_flags(), which RE-READS the
    DB-persisted MODULE_FLAGS override (SystemConfig) into app.config. The
    test DB stores {"accommodation": false}, so mutating app.config alone is
    insufficient — the DB flag must be flipped (and restored) instead.
    """
    from app.models.system_config import SystemConfig
    from app.utils.module_toggle_service import ModuleToggleService

    with app.app_context():
        stored = SystemConfig.query.filter_by(key="MODULE_FLAGS").first()
        prev_null = stored is None or stored.value is None
        prev = ModuleToggleService._fetch_stored_flags()

        merged = dict(prev)
        merged["accommodation"] = True
        SystemConfig.set(
            "MODULE_FLAGS", json.dumps(merged), value_type="json",
            description="Module flags", commit=True,
        )
        ModuleToggleService.load_overrides_into_app()

    yield

    with app.app_context():
        if prev_null:
            row = SystemConfig.query.filter_by(key="MODULE_FLAGS").first()
            if row is not None:
                db.session.delete(row)
                db.session.commit()
        else:
            SystemConfig.set(
                "MODULE_FLAGS", json.dumps(prev), value_type="json",
                description="Module flags", commit=True,
            )
        ModuleToggleService.load_overrides_into_app()


def _declare(app, user_id, code):
    with app.app_context():
        user = db.session.get(User, user_id)
        row = create_individual_intention(user, code)
        db.session.commit()
        return row


def _force_status(app, user_id, code, status, *, soft_delete=False):
    """Force a participation status/state directly (for states/edges the
    individual public routes cannot reach themselves)."""
    from app.identity.models.provider_participation import ProviderParticipation
    with app.app_context():
        row = (
            ProviderParticipation.query.filter_by(
                user_id=user_id,
                capability_code=code,
                is_deleted=False,
            )
            .first()
        )
        if row is None:
            raise AssertionError("participation row must be declared first")
        if soft_delete:
            row.soft_delete()
        else:
            row.status = status
        db.session.commit()
        return row


def _rows_for(app, user_id):
    from app.identity.models.provider_participation import ProviderParticipation
    with app.app_context():
        return (
            ProviderParticipation.query.filter_by(
                user_id=user_id,
                is_deleted=False,
            )
            .all()
        )


# ===========================================================================
# 1. Read-only helper is_capability_operational
# ===========================================================================

class TestIsCapabilityOperational:

    def test_true_only_when_activated(self, app, plain_user):
        _declare(app, plain_user.id, ProviderCapabilityCode.EVENTS.value)
        assert is_capability_operational(
            "individual", plain_user.id, ProviderCapabilityCode.EVENTS.value,
        ) is False
        with app.app_context():
            from app.identity.services.provider_participation_service import (
                activate_individual_intention,
            )
            user = db.session.get(User, plain_user.id)
            activate_individual_intention(
                user, ProviderCapabilityCode.EVENTS.value,
            )
            db.session.commit()
        assert is_capability_operational(
            "individual", plain_user.id, ProviderCapabilityCode.EVENTS.value,
        ) is True

    def test_false_after_deactivation(self, app, plain_user):
        _declare(app, plain_user.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _force_status(
            app, plain_user.id,
            ProviderCapabilityCode.ACCOMMODATION.value,
            ProviderCapabilityStatus.DEACTIVATED.value,
        )
        assert is_capability_operational(
            "individual", plain_user.id, ProviderCapabilityCode.ACCOMMODATION.value,
        ) is False

    def test_false_for_unknown_code(self, app, plain_user):
        assert is_capability_operational("individual", plain_user.id, "nope") is False

    def test_false_for_unknown_subject_type(self, app, plain_user):
        _declare(app, plain_user.id, ProviderCapabilityCode.TOURISM.value)
        assert is_capability_operational(
            "bogus", plain_user.id, ProviderCapabilityCode.TOURISM.value,
        ) is False

    def test_false_for_nil_subject(self, app):
        assert is_capability_operational("individual", None, ProviderCapabilityCode.EVENTS.value) is False

    def test_wrong_subject_kind_cannot_see_row(self, app, plain_user):
        # Organisation rows are invisible to the individual subject lookup,
        # even when the org holds an ACTIVATED row for the same code.
        from app.identity.models.organisation import Organisation
        from app.identity.models.provider_participation import ProviderParticipation
        with app.app_context():
            org = Organisation(
                legal_name=f"Participation Org {uuid.uuid4().hex[:8]}",
                org_id=str(uuid.uuid4()),
                country="UG",
            )
            db.session.add(org)
            db.session.flush()
            db.session.add(
                ProviderParticipation(
                    organisation_id=org.id,
                    capability_code=ProviderCapabilityCode.ACCOMMODATION.value,
                    status=ProviderCapabilityStatus.ACTIVATED.value,
                )
            )
            db.session.commit()
            org_id = org.id
        assert is_capability_operational(
            "organisation", org_id, ProviderCapabilityCode.ACCOMMODATION.value,
        ) is True
        assert is_capability_operational(
            "individual", plain_user.id, ProviderCapabilityCode.ACCOMMODATION.value,
        ) is False

    def test_deleted_row_is_not_operational(self, app, plain_user):
        _declare(app, plain_user.id, ProviderCapabilityCode.VENUE.value)
        _force_status(
            app, plain_user.id,
            ProviderCapabilityCode.VENUE.value,
            ProviderCapabilityStatus.ACTIVATED.value,
            soft_delete=True,
        )
        assert is_capability_operational(
            "individual", plain_user.id, ProviderCapabilityCode.VENUE.value,
        ) is False

    def test_helper_is_read_only(self, app, plain_user):
        _declare(app, plain_user.id, ProviderCapabilityCode.TRANSPORT.value)
        assert is_capability_operational(
            "individual", plain_user.id, ProviderCapabilityCode.TRANSPORT.value,
        ) is False
        # The read did not advance, delete, or create anything.
        row = _rows_for(app, plain_user.id)
        assert len(row) == 1
        assert str(row[0].status) == ProviderCapabilityStatus.INTENT.value


# ===========================================================================
# 2. G-3 HTTP API — list
# ===========================================================================

class TestListCapabilities:

    def test_requires_login(self, client):
        r = client.get("/me/capabilities")
        assert r.status_code in (302, 401)

    def test_empty_list_returns_own_public_id(self, client, plain_user):
        _login(client, plain_user)
        r = client.get("/me/capabilities")
        assert r.status_code == 200
        data = r.get_json()
        assert data["user_id"] == plain_user.public_id
        assert data["capabilities"] == []

    def test_lists_own_intentions(self, app, client, plain_user):
        _declare(app, plain_user.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _declare(app, plain_user.id, ProviderCapabilityCode.TRANSPORT.value)
        _login(client, plain_user)
        r = client.get("/me/capabilities")
        assert r.status_code == 200
        data = r.get_json()
        codes = [c["capability_code"] for c in data["capabilities"]]
        assert codes == ["accommodation", "transport"]
        assert all(c["status"] == "intent" for c in data["capabilities"])

    def test_subject_isolation_between_users(self, app, client, plain_user):
        other = _make_user(app, owner=False)
        _declare(app, plain_user.id, ProviderCapabilityCode.VENUE.value)
        _login(client, other)
        r = client.get("/me/capabilities")
        data = r.get_json()
        assert data["capabilities"] == []
        _login(client, plain_user)
        r = client.get("/me/capabilities")
        assert [c["capability_code"] for c in r.get_json()["capabilities"]] == ["venue"]

    def test_never_exposes_internal_ids(self, app, client, plain_user):
        _declare(app, plain_user.id, ProviderCapabilityCode.EVENTS.value)
        _login(client, plain_user)
        body = client.get("/me/capabilities").get_json()
        assert body["user_id"] == plain_user.public_id
        cap = body["capabilities"][0]
        assert "id" not in cap
        assert "user_id" not in cap
        assert "organisation_id" not in cap
        assert cap["subject_type"] == "individual"


# ===========================================================================
# 3. G-3 HTTP API — activate / deactivate
# ===========================================================================

class TestActivateCapability:

    def test_requires_login(self, app, client, plain_user):
        _declare(app, plain_user.id, ProviderCapabilityCode.EVENTS.value)
        r = client.post("/me/capabilities/events/activate")
        assert r.status_code in (302, 401)

    def test_invalid_code_400(self, client, plain_user):
        _login(client, plain_user)
        r = client.post("/me/capabilities/bogus/activate")
        assert r.status_code == 400

    def test_undeclared_404(self, client, plain_user):
        _login(client, plain_user)
        r = client.post("/me/capabilities/events/activate")
        assert r.status_code == 404

    def test_accommodation_activation_denied_when_ineligible(self, app, client, plain_user):
        _declare(app, plain_user.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _login(client, plain_user)
        r = client.post("/me/capabilities/accommodation/activate")
        assert r.status_code == 403
        assert "not fully verified" in r.get_json()["error"].lower()

    def test_accommodation_activation_succeeds_when_eligible(self, app, client, eligible_host):
        _declare(app, eligible_host.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _login(client, eligible_host)
        r = client.post("/me/capabilities/accommodation/activate")
        assert r.status_code == 200
        data = r.get_json()
        assert data["user_id"] == eligible_host.public_id
        assert data["capability"]["capability_code"] == "accommodation"
        assert data["capability"]["status"] == "activated"
        assert data["capability"]["activated_at"] is not None
        assert "id" not in data
        assert "id" not in data["capability"]

    def test_activation_persists_for_followup_requests(self, app, client, eligible_host):
        _declare(app, eligible_host.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _login(client, eligible_host)
        r = client.post("/me/capabilities/accommodation/activate")
        assert r.status_code == 200
        r = client.get("/me/capabilities")
        assert r.get_json()["capabilities"][0]["status"] == "activated"

    def test_reactivate_conflict_409(self, app, client, eligible_host):
        _declare(app, eligible_host.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _login(client, eligible_host)
        assert client.post("/me/capabilities/accommodation/activate").status_code == 200
        assert client.post("/me/capabilities/accommodation/activate").status_code == 409

    def test_other_codes_are_lifecycle_only(self, app, client, plain_user):
        # transport has NO eligibility hook yet — activation is lifecycle-only.
        _declare(app, plain_user.id, ProviderCapabilityCode.TRANSPORT.value)
        _login(client, plain_user)
        r = client.post("/me/capabilities/transport/activate")
        assert r.status_code == 200
        assert r.get_json()["capability"]["status"] == "activated"


class TestDeactivateCapability:

    def test_requires_login(self, app, client, plain_user):
        _declare(app, plain_user.id, ProviderCapabilityCode.EVENTS.value)
        _force_status(
            app, plain_user.id,
            ProviderCapabilityCode.EVENTS.value,
            ProviderCapabilityStatus.ACTIVATED.value,
        )
        r = client.post("/me/capabilities/events/deactivate")
        assert r.status_code in (302, 401)

    def test_invalid_code_400(self, client, plain_user):
        _login(client, plain_user)
        r = client.post("/me/capabilities/bogus/deactivate")
        assert r.status_code == 400

    def test_undeclared_404(self, client, plain_user):
        _login(client, plain_user)
        assert client.post("/me/capabilities/events/deactivate").status_code == 404

    def test_deactivate_roundtrip(self, app, client, eligible_host):
        _declare(app, eligible_host.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _login(client, eligible_host)
        assert client.post("/me/capabilities/accommodation/activate").status_code == 200
        r = client.post("/me/capabilities/accommodation/deactivate")
        assert r.status_code == 200
        assert r.get_json()["capability"]["status"] == "deactivated"
        # deactivating an already-deactivated row is an invalid transition
        assert client.post("/me/capabilities/accommodation/deactivate").status_code == 409
        # deactivated -> activated is legal (reversible lifecycle)
        assert client.post("/me/capabilities/accommodation/activate").status_code == 200

    def test_deactivate_persists(self, app, client, eligible_host):
        _declare(app, eligible_host.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _login(client, eligible_host)
        client.post("/me/capabilities/accommodation/activate")
        client.post("/me/capabilities/accommodation/deactivate")
        r = client.get("/me/capabilities")
        assert r.get_json()["capabilities"][0]["status"] == "deactivated"


# ===========================================================================
# 4. Two-gate operational rule at host_create_listing
# ===========================================================================

class TestTwoGateHostListing:

    def test_blocked_when_no_participation(self, app, client, eligible_host, accommodation_module_on):
        _login(client, eligible_host)
        _set_host_context(client, eligible_host.public_id)
        r = client.get("/accommodation/host/listings/create", follow_redirects=False)
        assert r.status_code == 302
        assert "/host/dashboard" in r.headers["Location"]

    def test_blocked_when_intent_not_activated(self, app, client, eligible_host, accommodation_module_on):
        _declare(app, eligible_host.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _login(client, eligible_host)
        _set_host_context(client, eligible_host.public_id)
        r = client.get("/accommodation/host/listings/create", follow_redirects=False)
        assert r.status_code == 302
        assert "/host/dashboard" in r.headers["Location"]

    def test_block_warning_flashed(self, app, client, eligible_host, accommodation_module_on):
        _declare(app, eligible_host.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _login(client, eligible_host)
        _set_host_context(client, eligible_host.public_id)
        r = client.get("/accommodation/host/listings/create", follow_redirects=True)
        assert r.status_code == 200
        assert b"Activate your accommodation provider capability" in r.data

    def test_allowed_when_activated(self, app, client, eligible_host, accommodation_module_on):
        _declare(app, eligible_host.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _login(client, eligible_host)
        _set_host_context(client, eligible_host.public_id)
        assert client.post("/me/capabilities/accommodation/activate").status_code == 200
        r = client.get("/accommodation/host/listings/create")
        assert r.status_code == 200

    def test_reblocked_after_deactivation(self, app, client, eligible_host, accommodation_module_on):
        _declare(app, eligible_host.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _login(client, eligible_host)
        _set_host_context(client, eligible_host.public_id)
        client.post("/me/capabilities/accommodation/activate")
        assert client.get("/accommodation/host/listings/create").status_code == 200
        client.post("/me/capabilities/accommodation/deactivate")
        r = client.get("/accommodation/host/listings/create", follow_redirects=False)
        assert r.status_code == 302
        assert "/host/dashboard" in r.headers["Location"]

    def test_activation_cannot_bypass_eligibility(self, app, client, plain_user, accommodation_module_on):
        """A user who loses eligibility (or never had it) must not reach the
        listing form even when the participation row is ACTIVATED."""
        _declare(app, plain_user.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _force_status(
            app, plain_user.id,
            ProviderCapabilityCode.ACCOMMODATION.value,
            ProviderCapabilityStatus.ACTIVATED.value,
        )
        _login(client, plain_user)
        _set_host_context(client, plain_user.public_id)
        r = client.get("/accommodation/host/listings/create", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["Location"].rstrip("/") in ("", "/")
        r = client.get("/accommodation/host/listings/create", follow_redirects=True)
        assert b"Cannot access host tools" in r.data


# ===========================================================================
# 5. Invarants — activation creates no domain resources / roles
# ===========================================================================

class TestActivationInvariants:

    def test_activation_creates_no_domain_resources(self, app, client, eligible_host):
        from app.accommodation.models import HostProfile
        from app.accommodation.models.property import Property
        from app.transport.models import Vehicle
        from app.wallet.models.ledger import AccountModel

        with app.app_context():
            props_before = Property.query.filter_by(owner_user_id=eligible_host.id).count()
            vehicles_before = Vehicle.query.count()
            wallets_before = AccountModel.query.filter_by(user_id=eligible_host.id).count()
            host_profiles_before = HostProfile.query.count()
            roles_before = UserRole.query.filter_by(user_id=eligible_host.id).count()

        _declare(app, eligible_host.id, ProviderCapabilityCode.ACCOMMODATION.value)
        _login(client, eligible_host)
        r = client.post("/me/capabilities/accommodation/activate")
        assert r.status_code == 200

        with app.app_context():
            assert Property.query.filter_by(owner_user_id=eligible_host.id).count() == props_before
            assert Vehicle.query.count() == vehicles_before
            assert AccountModel.query.filter_by(user_id=eligible_host.id).count() == wallets_before
            assert HostProfile.query.count() == host_profiles_before
            assert UserRole.query.filter_by(user_id=eligible_host.id).count() == roles_before
            assert len(_rows_for(app, eligible_host.id)) == 1