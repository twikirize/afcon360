"""
Safeguard tests for the Organisation Classification Redesign repair path.

These tests drive the ACTUAL settings route in ``app/identity/routes.py``
through the Flask test client against live PostgreSQL and assert the
classification-repair invariants:

    A. authorised editor (org_owner via ``org.settings.manage``) can repair an
       organisation that was never classified
    B. an invalid type code is rejected server-side; the org stays unchanged
    C. an empty submission preserves the existing classification
    D. a member without ``org.settings.manage`` cannot repair
    E. classification repair NEVER auto-activates provider participation
       (provider = explicit intent, never derived from org type)
    F. category is never accepted from the client / ``business_category`` is
       never written by the repair path (category derived server-side only)

Isolation notes (matches tests/conftest.py:_login_client):
    - ``client.session_transaction()`` opens a nested request context that
      tears down the SQLAlchemy session and detaches ORM instances created
      before it. Helpers therefore extract scalar handles while instances are
      still attached, and assertions re-query fresh rows after requests.
    - The frozen classification catalogue is seeded once per session
      (idempotent) because ``organisation_types.code`` is a real FK target.

This suite is additive; it changes no wallet, onboarding, or domain code.
"""

import uuid

import pytest

from app.auth.roles import assign_org_role
from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_catalogues import (
    OrganisationCategory,
    OrganisationTypeCatalogue,
)
from app.identity.models.organisation_member import OrganisationMember
from app.identity.models.organization_types import OrganizationType
from app.identity.models.provider_participation import ProviderParticipation
from app.identity.models.user import User
from app.identity.services.organisation_role_provisioning import (
    provision_organisation_roles,
)

from tests.test_organisation_classification import (
    ORGANISATION_CATEGORIES,
    ORGANISATION_TYPE_CATALOG,
)


# ---------------------------------------------------------------------------
# Session-scoped global seeding (same contract as test_assign_revoke_org_role)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _seed_global_org_roles(app):
    """Seed global roles + permissions + role-permission links once."""
    from app.auth.seed_roles import seed_all

    with app.app_context():
        seed_all()
    yield


@pytest.fixture(autouse=True, scope="module")
def _seed_catalogue_module(app):
    """Seed the frozen classification catalogue once for this module so FK
    writes to ``organisation_types.code`` succeed during HTTP requests
    (mirrors scripts/seed_organisation_catalogues.py).

    The rows are committed because the request path reads them through a
    separate session. Teardown intentionally does NOT delete them: seeding is
    idempotent everywhere and organisations committed by these tests (and by
    sibling modules) reference ``organisation_types.code`` via FK
    ``organisations_organisation_type_code_fkey``, so deleting them would
    raise a ForeignKeyViolation on the shared test DB.
    """
    with app.app_context():
        _seed_catalog_rows()
        db.session.commit()
    yield


def _seed_catalog_rows():
    for sort_order, (code, label) in enumerate(ORGANISATION_CATEGORIES.items()):
        if (
            db.session.query(OrganisationCategory)
            .filter_by(code=code)
            .first()
            is None
        ):
            db.session.add(
                OrganisationCategory(
                    code=code, label=label, sort_order=sort_order, is_active=True,
                )
            )
    db.session.flush()
    for sort_order, (code, meta) in enumerate(ORGANISATION_TYPE_CATALOG.items()):
        if (
            db.session.query(OrganisationTypeCatalogue)
            .filter_by(code=code)
            .first()
            is None
        ):
            db.session.add(
                OrganisationTypeCatalogue(
                    code=code,
                    label=meta["label"],
                    category_code=meta["category_code"],
                    sort_order=sort_order,
                    is_active=True,
                )
            )


# ---------------------------------------------------------------------------
# Helpers (scalar handles only — never cross-context ORM instances)
# ---------------------------------------------------------------------------

def _make_org(tag, organisation_type_code=None):
    org = Organisation(
        org_id=str(uuid.uuid4()),
        legal_name=f"Classify Org {tag} {uuid.uuid4().hex[:6]}",
        country="UG",
        region="Central",
        org_type="business",
        contact_email=f"classify-{tag}-{uuid.uuid4().hex[:6]}@example.com",
        organisation_type_code=organisation_type_code,
        verification_status="pending",
        lifecycle_state="registered",
        is_active=True,
        is_operational=False,
    )
    db.session.add(org)
    db.session.flush()
    return org


def _org_handle(org):
    return {
        "id": org.id,
        "org_id": org.org_id,
        "legal_name": org.legal_name,
        "contact_email": org.contact_email,
    }


def _make_user(tag):
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"{tag}_{uuid.uuid4().hex[:8]}",
        email=f"{tag}_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed",
        is_active=True,
        is_verified=True,
        email_verified=True,
    )
    db.session.add(user)
    db.session.flush()
    return {
        "id": user.id,
        "public_id": str(user.public_id),
        "email": user.email,
    }


def _make_member(org_handle, user_handle):
    member = OrganisationMember(
        user_id=user_handle["id"],
        organisation_id=org_handle["id"],
        is_active=True,
    )
    db.session.add(member)
    db.session.flush()
    return member


def _setup_provisioned_org(tag, organisation_type_code=None):
    """Provisioned org with owner + plain-member actors.

    Returns scalar handles: (org_handle, actors) where actors maps
    owner/plain to user handles.
    """
    org = _make_org(tag, organisation_type_code=organisation_type_code)
    provision_organisation_roles(org)
    org_handle = _org_handle(org)

    owner = _make_user(f"{tag}_owner")
    owner_member = _make_member(org_handle, owner)
    assign_org_role(owner["id"], org_handle["id"], "org_owner")
    owner_member.invalidate_permission_cache()

    plain = _make_user(f"{tag}_plain")
    plain_member = _make_member(org_handle, plain)
    assign_org_role(plain["id"], org_handle["id"], "org_member")
    plain_member.invalidate_permission_cache()

    db.session.commit()
    return org_handle, {"owner": owner, "plain": plain}


def _login(client, public_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = public_id
        sess["_fresh"] = True


def _settings_post_data(org_handle, organisation_type_code=""):
    """Valid minimal settings payload (legal_name + contact_email are
    DataRequired fields on OrganizationSettingsForm)."""
    return {
        "legal_name": org_handle["legal_name"],
        "contact_email": org_handle["contact_email"],
        "organisation_type_code": organisation_type_code,
    }


def _fresh_org(org_handle):
    return db.session.get(Organisation, org_handle["id"])


# ---------------------------------------------------------------------------
# A. Authorised editor can repair an unclassified organisation
# ---------------------------------------------------------------------------

class TestAuthorisedRepair:

    def test_owner_can_repair_unclassified_org(self, app):
        org, actors = _setup_provisioned_org("a_repair")
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.post(
            f"/org/{org['org_id']}/settings",
            data=_settings_post_data(org, "hotel"),
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        row = _fresh_org(org)
        assert row.organisation_type_code == "hotel"
        assert row.get_effective_org_type() is OrganizationType.HOTEL
        assert row.can_manage_accommodation() is True

    def test_repair_persists_type_not_business_category(self, app):
        org, actors = _setup_provisioned_org("a_legacy")
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.post(
            f"/org/{org['org_id']}/settings",
            data=_settings_post_data(org, "football_team"),
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        row = _fresh_org(org)
        assert row.organisation_type_code == "football_team"
        assert row.business_category is None

    def test_repair_does_not_create_provider_participation(self, app):
        org, actors = _setup_provisioned_org("a_nohost")
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.post(
            f"/org/{org['org_id']}/settings",
            data=_settings_post_data(org, "hotel"),
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        count = ProviderParticipation.query.filter_by(
            organisation_id=org["id"], is_deleted=False
        ).count()
        assert count == 0

    def test_repair_preserves_unrelated_org_state(self, app):
        org, actors = _setup_provisioned_org("a_state")
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        data = _settings_post_data(org, "restaurant")
        data["legal_name"] = "Renamed during repair"
        resp = client.post(
            f"/org/{org['org_id']}/settings",
            data=data,
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        row = _fresh_org(org)
        assert row.legal_name == "Renamed during repair"
        assert row.organisation_type_code == "restaurant"


# ---------------------------------------------------------------------------
# B. Invalid type rejected server-side
# ---------------------------------------------------------------------------

class TestInvalidTypeRejected:

    def test_invalid_type_rejected_org_unchanged(self, app):
        org, actors = _setup_provisioned_org("b_invalid")
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.post(
            f"/org/{org['org_id']}/settings",
            data=_settings_post_data(org, "made_up_type"),
            follow_redirects=False,
        )

        assert resp.status_code == 200, resp.status_code
        row = _fresh_org(org)
        assert row.organisation_type_code is None
        assert row.business_category is None


# ---------------------------------------------------------------------------
# C. Empty submission preserves the existing classification
# ---------------------------------------------------------------------------

class TestEmptyPreserves:

    def test_empty_submission_preserves_classification(self, app):
        org, actors = _setup_provisioned_org(
            "c_preserve", organisation_type_code="football_team"
        )
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        resp = client.post(
            f"/org/{org['org_id']}/settings",
            data=_settings_post_data(org, ""),
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        row = _fresh_org(org)
        assert row.organisation_type_code == "football_team"


# ---------------------------------------------------------------------------
# D. Unauthorised member cannot repair
# ---------------------------------------------------------------------------

class TestUnauthorisedCannotRepair:

    def test_plain_member_cannot_repair_classification(self, app):
        org, actors = _setup_provisioned_org("d_noauth")
        client = app.test_client()
        _login(client, actors["plain"]["public_id"])

        resp = client.post(
            f"/org/{org['org_id']}/settings",
            data=_settings_post_data(org, "hotel"),
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        assert "/dashboard" in resp.headers.get("Location", "")
        row = _fresh_org(org)
        assert row.organisation_type_code is None
        assert row.business_category is None


# ---------------------------------------------------------------------------
# F. Category never accepted from client / business_category never written
# ---------------------------------------------------------------------------

class TestCategoryServerSideOnly:

    def test_category_field_from_client_is_ignored(self, app):
        org, actors = _setup_provisioned_org("f_category")
        client = app.test_client()
        _login(client, actors["owner"]["public_id"])

        data = _settings_post_data(org, "hotel")
        data["business_category"] = "financial_services"
        data["category"] = "financial_services"
        resp = client.post(
            f"/org/{org['org_id']}/settings",
            data=data,
            follow_redirects=False,
        )

        assert resp.status_code == 302, resp.status_code
        row = _fresh_org(org)
        assert row.organisation_type_code == "hotel"
        assert row.business_category is None


# ---------------------------------------------------------------------------
# Import sanity
# ---------------------------------------------------------------------------

class TestImportSanity:

    def test_create_app_import_sanity(self, app):
        from app.models.base import BaseModel

        assert issubclass(Organisation, BaseModel)