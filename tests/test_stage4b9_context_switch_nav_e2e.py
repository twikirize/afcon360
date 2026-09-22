"""
NODE CONTEXT-SWITCH-E2E — Real HTTP proof that context switching changes the
OPERATING CONTEXT and the base navigation follows the canonical active context.

This drives the FULL production journey over the real Flask test client against
the live PostgreSQL test DB — no stub of ``app.auth.context`` and no shortcut
through ``inject_sitewide``'s return value. The base menu assertions are made
on the RENDERED html of real routes.

What is proven:

    A. Personal -> Organisation  : real login, real form POST /switch-context,
                                   real org dashboard render. The base nav
                                   swaps to the organisation header
                                   ("Switch to Personal", org wallet link).
    B. Organisation -> Personal  : the base-nav "Switch to Personal" form.
                                   The base nav swaps back to the personal
                                   header; identity is untouched.
    C. Organisation -> Driver    : a third valid operating context (driver) is
                                   reachable and leaves the org menu behind;
                                   Driver -> Organisation restores it.
    D. Stale legacy state        : canonical = personal with stale legacy
                                   ``current_context="organization"`` +
                                   ``current_org_id`` (including the internal
                                   id the login default-org path writes) still
                                   renders the PERSONAL nav.
    E. URL/ID safety             : the switch redirect and every org link in
                                   the rendered nav use the public org slug;
                                   internal organisation/user ids never appear
                                   in the switch payload or rendered links.

Run with: pytest tests/test_stage4b9_context_switch_nav_e2e.py -q --tb=short
"""

import uuid

import pytest

from app.auth.roles import assign_org_role
from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember
from app.identity.models.user import User
from app.identity.services.organisation_role_provisioning import (
    provision_organisation_roles,
)
from app.profile.models import UserProfile


@pytest.fixture(autouse=True, scope="session")
def _seed_org_roles(app):
    from app.auth.seed_roles import seed_all

    with app.app_context():
        seed_all()
    yield


# -- Rendered base-menu markers ----------------------------------------------
ORG_MENU_MARKER = "Switch to Personal"              # base.html STATE 3 (org)
PERSONAL_ORG_MARKER = "Switch to Organisation"      # base.html STATE 2 (personal)


def _snapshot_session(client):
    """Plain dict of the real Flask session (production keys)."""
    with client.session_transaction() as sess:
        return {k: v for k, v in sess.items() if not k.startswith("_flashes")}


def _make_org(tag, slug):
    org = Organisation(
        org_id=str(uuid.uuid4()),
        slug=slug,
        legal_name=f"Nav E2E {tag} {uuid.uuid4().hex[:6]}",
        country="UG",
        region="Central",
        org_type="business",
        contact_email=f"nave2e-{tag}-{uuid.uuid4().hex[:6]}@example.com",
    )
    db.session.add(org)
    db.session.flush()
    return org


def _make_user(tag):
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"nave2e_{tag}_{uuid.uuid4().hex[:8]}",
        email=f"nave2e_{tag}_{uuid.uuid4().hex[:8]}@example.com",
        is_active=True,
        is_verified=True,
        email_verified=True,
    )
    user.set_password("TestPass123!")
    db.session.add(user)
    db.session.flush()
    profile = UserProfile(
        user_id=user.public_id,
        full_name=f"Nav E2E {tag}",
        profile_completed=True,
    )
    db.session.add(profile)
    db.session.flush()
    return user


def _make_driver_profile(user, driver_code):
    from app.transport.models import ComplianceStatus, DriverProfile, VerificationTier

    profile = DriverProfile(
        user_id=user.id,
        driver_code=driver_code,
        verification_tier=VerificationTier.PENDING,
        compliance_status=ComplianceStatus.PENDING_REVIEW,
        is_active=True,
    )
    db.session.add(profile)
    db.session.flush()
    return profile


def _login(client, email):
    resp = client.post(
        "/login",
        data={"username": email, "password": "TestPass123!"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    return resp


class TestContextSwitchNavE2E:
    """Real HTTP journey: login -> rendered nav -> switch -> rendered nav."""

    def _setup_org_user_and_driver(self, app):
        """One verified user: member+org_owner of Org A, plus a live DriverProfile."""
        with app.app_context():
            org = _make_org("NODE", "afcon360-node-e2e")
            provision_organisation_roles(org)
            user = _make_user("node")
            member = OrganisationMember(
                user_id=user.id,
                organisation_id=org.id,
                is_active=True,
            )
            db.session.add(member)
            db.session.flush()
            assign_org_role(user.id, org.id, "org_owner")
            member.invalidate_permission_cache()
            driver_code = "DRV" + uuid.uuid4().hex[:12]
            _make_driver_profile(user, driver_code)
            db.session.commit()
            return {
                "email": user.email,
                "public_id": str(user.public_id),
                "org_public_id": str(org.org_id),
                "org_internal_id": org.id,
                "org_slug": org.slug,
                "org_legal_name": org.legal_name,
                "driver_code": driver_code,
            }

    def test_rendered_nav_follows_org_personal_driver(self, app, client):
        handles = self._setup_org_user_and_driver(app)

        # -- 1. Real login -------------------------------------------------
        _login(client, handles["email"])
        sess = _snapshot_session(client)
        assert sess["_user_id"] == handles["public_id"]
        assert sess.get("active_context_type") in (None, "personal")

        # -- 2. Personal baseline rendered nav ----------------------------
        resp = client.get("/user/dashboard")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # Personal header (user has orgs, so the switcher block renders).
        assert PERSONAL_ORG_MARKER in html
        assert ORG_MENU_MARKER not in html
        # Personal context active in the shell switcher.
        assert "data-context-type=\"personal\"" in html
        assert "data-context-type=\"organisation\"" in html

        # -- 3. Personal -> Organisation (real form POST, base-nav shape) --
        resp = client.post(
            "/switch-context",
            data={
                "type": "organisation",
                "public_id": handles["org_public_id"],
                "role": "org_owner",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        org_url = resp.headers["Location"]
        assert f"/org/{handles['org_slug']}/dashboard" in org_url
        assert f"/org/{handles['org_internal_id']}" not in org_url

        sess = _snapshot_session(client)
        assert sess["active_context_type"] == "organisation"
        assert sess["active_context_id"] == handles["org_public_id"]
        assert sess["active_role"] == "org_owner"
        assert sess["_user_id"] == handles["public_id"]  # same human

        # Rendered org dashboard shows the ORG base header.
        resp = client.get(f"/org/{handles['org_slug']}/dashboard")
        assert resp.status_code == 200
        org_html = resp.get_data(as_text=True)
        assert ORG_MENU_MARKER in org_html            # org header present
        assert PERSONAL_ORG_MARKER not in org_html     # personal header gone
        assert "nav-org-name" in org_html
        assert "afcon360-node-e2e" in org_html         # slug-based org links
        assert f"org_id={handles['org_internal_id']}" not in org_html

        # -- 4. Organisation -> Personal (base-nav form) -------------------
        resp = client.post(
            "/switch-context",
            data={"type": "personal", "role": "user"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/user/dashboard" in resp.headers["Location"]

        sess = _snapshot_session(client)
        assert sess["active_context_type"] == "personal"
        assert sess["active_context_id"] is None
        assert sess["_user_id"] == handles["public_id"]

        back = client.get("/user/dashboard")
        assert back.status_code == 200
        back_html = back.get_data(as_text=True)
        assert PERSONAL_ORG_MARKER in back_html        # personal header back
        assert ORG_MENU_MARKER not in back_html

        # -- 5. Organisation -> Driver -> Organisation ---------------------
        resp = client.post(
            "/switch-context",
            json={
                "type": "organisation",
                "public_id": handles["org_public_id"],
                "role": "org_owner",
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["context"]["type"] == "organisation"

        resp = client.post(
            "/switch-context",
            json={
                "type": "driver",
                "public_id": handles["driver_code"],
                "role": "driver",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["context"]["type"] == "driver"

        sess = _snapshot_session(client)
        assert sess["active_context_type"] == "driver"
        assert sess["active_context_id"] == handles["driver_code"]
        assert sess["_user_id"] == handles["public_id"]  # identity preserved
        # A non-org context leaves the org base header.
        driver_page = client.get("/user/dashboard")
        assert driver_page.status_code == 200
        driver_html = driver_page.get_data(as_text=True)
        assert ORG_MENU_MARKER not in driver_html

        # Driver -> Organisation restores the org header.
        resp = client.post(
            "/switch-context",
            json={
                "type": "organisation",
                "public_id": handles["org_public_id"],
                "role": "org_owner",
            },
        )
        assert resp.status_code == 200
        sno = _snapshot_session(client)
        assert sno["active_context_type"] == "organisation"
        org_again = client.get(f"/org/{handles['org_slug']}/dashboard")
        assert org_again.status_code == 200
        assert ORG_MENU_MARKER in org_again.get_data(as_text=True)

    def test_stale_legacy_org_keys_render_personal_nav(self, app, client):
        """THE reported defect path, proven on a rendered page: canonical
        selection = personal + stale legacy ``current_context="organization"``
        (with the internal org id the login default-org path writes) must still
        render the PERSONAL base menu."""
        handles = self._setup_org_user_and_driver(app)
        _login(client, handles["email"])

        with client.session_transaction() as sess:
            sess["active_context_type"] = "personal"
            sess["active_context_id"] = None
            sess["active_role"] = "user"
            sess["current_context"] = "organization"
            sess["current_org_id"] = handles["org_internal_id"]
            sess["current_org_name"] = handles["org_legal_name"]

        resp = client.get("/user/dashboard")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert PERSONAL_ORG_MARKER in html                  # personal menu
        assert ORG_MENU_MARKER not in html                  # no org menu
        assert "nav-org-name" not in html
        assert f"org_id={handles['org_internal_id']}" not in html

        # Stale legacy packets reach the switch handler but never win:
        # switching explicitly back to the organisation overrides the legacy
        # keys through the canonical resolver.
        resp = client.post(
            "/switch-context",
            data={
                "type": "organisation",
                "public_id": handles["org_public_id"],
                "role": "org_owner",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert f"/org/{handles['org_slug']}/dashboard" in resp.headers["Location"]
        sess = _snapshot_session(client)
        assert sess["active_context_type"] == "organisation"
        assert sess["active_context_id"] == handles["org_public_id"]

        org_html = client.get(
            f"/org/{handles['org_slug']}/dashboard"
        ).get_data(as_text=True)
        assert ORG_MENU_MARKER in org_html
        assert f"org_id={handles['org_internal_id']}" not in org_html