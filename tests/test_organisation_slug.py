"""
Organisation slug policy tests (approved "Organisation Browser Identity &
Slug Policy", implemented in ``app/identity/services/organisation_slug.py``).

Coverage:
  * base slug derivation (first two MEANINGFUL words, stopwords removed,
    punctuation stripped, lowercased, ``_``-joined)
  * deterministic ``org_id``-based fallback when no meaningful words exist
  * application-level global uniqueness (``-2``/``-3`` colliders)
  * slug immutability: a later ``legal_name`` change MUST NOT alter the slug
  * route resolution accepts both the slug and the stable ``org_id`` UUID
  * legacy UUID GET routes 301-canonicalize to the slug URL
  * the slug is a routing identifier, NOT an authorization boundary — access
    is still enforced by org membership/role, never by knowing a slug
"""

import uuid

import pytest

from app.identity.models.organisation import Organisation
from app.identity.services.organisation_slug import (
    STOPWORDS,
    _fallback_slug,
    slugify_org_name,
)


# ---------------------------------------------------------------------------
# Unit: slug derivation
# ---------------------------------------------------------------------------

class TestSlugifyOrgName:
    def test_two_meaningful_words(self):
        assert slugify_org_name("Miracle Center Ministries") == "miracle_center"

    def test_stopwords_skipped(self):
        assert slugify_org_name("The City of Kampala") == "city_kampala"

    def test_all_stopwords_returns_empty(self):
        assert slugify_org_name("The Company of Ltd") == ""

    def test_punctuation_stripped(self):
        assert slugify_org_name("Zen! & <Co> Ltd.") == "zen"

    def test_single_meaningful_word(self):
        assert slugify_org_name("Kampala") == "kampala"

    def test_whitespace_and_case_normalized(self):
        assert slugify_org_name("  OUTER  CITY  ") == "outer_city"

    def test_none_and_empty(self):
        assert slugify_org_name(None) == ""
        assert slugify_org_name("") == ""

    def test_stopwords_are_the_contracted_set(self):
        assert STOPWORDS == frozenset({
            "the", "of", "and", "for", "ltd", "limited",
            "company", "co", "corporation",
        })


class TestFallbackSlug:
    def test_deterministic_from_org_id(self):
        org = _FakeOrg("123e4567-e89b-12d3-a456-426614174000")
        assert _fallback_slug(org) == "123e4567_e89b_12d3_a456_426614174000"
        assert _fallback_slug(org) == _fallback_slug(org)

    def test_empty_org_id_falls_back_to_organisation(self):
        assert _fallback_slug(_FakeOrg(None)) == "organisation"


# ---------------------------------------------------------------------------
# DB: listener, uniqueness, immutability, resolution
# ---------------------------------------------------------------------------

class TestSlugPersistence:
    def _make_org(self, db_session, legal_name):
        org = Organisation(
            org_id=str(uuid.uuid4()),
            legal_name=legal_name,
            country="UG",
        )
        db_session.add(org)
        db_session.flush()
        return org

    def test_before_insert_listener_assigns_slug(self, db_session):
        org = self._make_org(db_session, "Miracle Center Ministries")
        assert org.slug == "miracle_center"

    def test_duplicate_names_get_numeric_collider(self, db_session):
        org_a = self._make_org(db_session, "ABC Hotel")
        org_b = self._make_org(db_session, "ABC Hotel & Suites")
        assert org_a.slug == "abc_hotel"
        assert org_b.slug == "abc_hotel-2"

    def test_slug_immutable_when_legal_name_changes(self, db_session):
        org = self._make_org(db_session, "Original Name")
        original_slug = org.slug
        org.legal_name = "A Completely Different Name"
        db_session.flush()
        db_session.refresh(org)
        assert org.slug == original_slug

    def test_slug_unique_violation_is_db_enforced(self, db_session):
        org_a = self._make_org(db_session, "Same Name")
        with pytest.raises(Exception):
            org_b = Organisation(
                org_id=str(uuid.uuid4()),
                legal_name="Same Name Copy",
                slug=org_a.slug,
                country="UG",
            )
            db_session.add(org_b)
            db_session.flush()
        db_session.rollback()


class TestSlugResolution:
    def _make_org(self, db_session, legal_name):
        org = Organisation(
            org_id=str(uuid.uuid4()),
            legal_name=legal_name,
            country="UG",
        )
        db_session.add(org)
        db_session.flush()
        return org

    def test_resolves_by_slug_and_by_legacy_org_id(self, db_session):
        from app.identity.routes import _get_organisation_by_public_id
        org = self._make_org(db_session, "Resolve Me Hostel")

        assert _get_organisation_by_public_id(org.slug).id == org.id
        assert _get_organisation_by_public_id(org.org_id).id == org.id

    def test_unknown_identifier_aborts_404(self, db_session):
        from werkzeug.exceptions import NotFound
        from app.identity.routes import _get_organisation_by_public_id
        self._make_org(db_session, "Resolve Noop Hotel")

        with pytest.raises(NotFound):
            _get_organisation_by_public_id("does-not-exist")


# ---------------------------------------------------------------------------
# HTTP: canonical redirect + slug is not an authorization boundary
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _seed_global_org_roles(app):
    """Seed global roles + permissions once (mirrors sibling suites)."""
    from app.auth.seed_roles import seed_all
    with app.app_context():
        seed_all()
    yield


class TestCanonicalRedirect:
    def _setup(self, db_session):
        from app.identity.models.organisation_member import OrganisationMember
        from app.identity.models.user import User
        from app.auth.roles import assign_org_role
        from app.identity.services.organisation_role_provisioning import (
            provision_organisation_roles,
        )

        org = Organisation(
            org_id=str(uuid.uuid4()),
            legal_name="Canonical Redirect Hotel",
            country="UG",
        )
        db_session.add(org)
        db_session.flush()
        provision_organisation_roles(org)
        org_id = org.id
        org_uuid = str(org.org_id)
        slug = org.slug

        user = User(
            public_id=str(uuid.uuid4()),
            username=f"slug_owner_{uuid.uuid4().hex[:8]}",
            email=f"slug_owner_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed",
            is_active=True,
            is_verified=True,
            email_verified=True,
        )
        db_session.add(user)
        db_session.flush()
        member = OrganisationMember(
            user_id=user.id,
            organisation_id=org_id,
            is_active=True,
        )
        db_session.add(member)
        db_session.flush()
        assign_org_role(user.id, org_id, "org_owner")
        member.invalidate_permission_cache()
        db_session.commit()
        return {"public_id": str(user.public_id), "uuid": org_uuid, "slug": slug}

    def test_legacy_uuid_dashboard_redirects_301_to_slug(self, app, client, db_session):
        handles = self._setup(db_session)
        with client.session_transaction() as sess:
            sess["_user_id"] = handles["public_id"]
            sess["_fresh"] = True

        resp = client.get(f"/org/{handles['uuid']}/dashboard")
        assert resp.status_code == 301
        location = resp.headers.get("Location") or ""
        assert location == f"/org/{handles['slug']}/dashboard"

    def test_slug_dashboard_renders_200(self, app, client, db_session):
        handles = self._setup(db_session)
        with client.session_transaction() as sess:
            sess["_user_id"] = handles["public_id"]
            sess["_fresh"] = True

        resp = client.get(f"/org/{handles['slug']}/dashboard")
        assert resp.status_code == 200


class TestSlugIsNotAuthorizationBoundary:
    def _setup(self, db_session):
        from app.identity.models.organisation_member import OrganisationMember
        from app.identity.models.user import User
        from app.auth.roles import assign_org_role
        from app.identity.services.organisation_role_provisioning import (
            provision_organisation_roles,
        )

        org_a = Organisation(
            org_id=str(uuid.uuid4()),
            legal_name="Owner Org",
            country="UG",
        )
        org_b = Organisation(
            org_id=str(uuid.uuid4()),
            legal_name="Other Org",
            country="UG",
        )
        db_session.add(org_a)
        db_session.add(org_b)
        db_session.flush()
        provision_organisation_roles(org_a)
        provision_organisation_roles(org_b)

        user = User(
            public_id=str(uuid.uuid4()),
            username=f"slug_boundary_{uuid.uuid4().hex[:8]}",
            email=f"slug_boundary_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hashed",
            is_active=True,
            is_verified=True,
            email_verified=True,
        )
        db_session.add(user)
        db_session.flush()
        member = OrganisationMember(
            user_id=user.id,
            organisation_id=org_a.id,
            is_active=True,
        )
        db_session.add(member)
        db_session.flush()
        assign_org_role(user.id, org_a.id, "org_owner")
        member.invalidate_permission_cache()
        db_session.commit()
        return {
            "user": user,
            "public_id": str(user.public_id),
            "org_a_id": org_a.id,
            "org_b_id": org_b.id,
            "org_b_slug": org_b.slug,
        }

    def test_knowing_slug_does_not_grant_authority(self, db_session):
        from app.identity.services.capability_service import (
            CapabilityPermissionError,
            activate_capability,
        )
        handles = self._setup(db_session)

        # The slug genuinely resolves to org B (routing is working) …
        from app.identity.routes import _get_organisation_by_public_id
        assert _get_organisation_by_public_id(handles["org_b_slug"]).id == handles["org_b_id"]

        # … but an owner of org A acting on org B is still denied.
        with pytest.raises(CapabilityPermissionError):
            activate_capability(handles["user"], handles["org_b_id"], "accommodation")

    def test_http_org_b_by_slug_denied_for_org_a_owner(self, app, client, db_session):
        from app.identity.models.provider_participation import ProviderParticipation
        from app.identity.models.provider_participation import ProviderCapabilityStatus

        handles = self._setup(db_session)
        cap = ProviderParticipation(
            organisation_id=handles["org_b_id"],
            capability_code="accommodation",
            status=ProviderCapabilityStatus.INTENT.value,
            meta={},
        )
        db_session.add(cap)
        db_session.commit()

        with client.session_transaction() as sess:
            sess["_user_id"] = handles["public_id"]
            sess["_fresh"] = True

        resp = client.post(
            f"/org/{handles['org_b_slug']}/capabilities/accommodation/activate"
        )
        assert resp.status_code == 403


class _FakeOrg:
    """Minimal org stand-in for ``_fallback_slug`` (no DB required)."""

    def __init__(self, org_id):
        self.org_id = org_id