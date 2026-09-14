"""
Stage 4B-8 / USER-A1 — Final end-to-end context-switch proof.

This test drives the REAL HTTP/session/DB journey for a NORMAL User (owner
excluded) so the invariant is proven against production code, not a mocked
permission-service shortcut:

    AUTHENTICATED USER + SELECTED CANONICAL CONTEXT + LIVE DB
    MEMBERSHIP/ROLE/PERMISSION RESOLUTION

It uses:
    - the real   POST /login              route (form post, real password)
    - the real   POST /switch-context     route (JSON body, production
              `app.auth.context` resolver chain, forensic audit)
    - the real Flask session               (`client.session_transaction()`,
              reading the exact Redis-backed session values the switch route
              wrote — the same values the next HTTP request reads)
    - the real `validate_context` + `resolve_effective_permissions(user, ctx)`
              chain against the live test PostgreSQL DB (the identical
              validator/perm-resolver the route-level middleware calls).

What is proven:
    1. Creating/login as a normal User leaves the default PERSONAL context.
    2. Switching to Organisation A keeps the SAME authenticated human
       (``_user_id`` / public_id identical) and changes only the selected
       canonical context keys (``active_context_type / _id / _role``).
    3. Effective permissions after switching to A come from A's live
       membership role; a permission granted ONLY in A is effective; a
       permission granted ONLY in another org (B) is NOT effective.
    4. Switching back to PERSONAL removes A's org permissions while keeping
       the identity and the personal resolution path intact.
    5. Switching Personal -> Org B never leaks A; permissions resolve from B.
    6. Foreign / fabricated org contexts fail closed (400, no assignment),
       and the previously-selected context stays authoritative.
    7. The authenticated user object is the same before and after every
       switch (no identity switch, no cross-organisation leakage).

This test intentionally runs the FULL real-path journey and does not stub
``app.auth.context`` functions. See tests/test_auth_context.py for the
isolated resolver unit coverage; this file is the HTTP integration proof.

Run with: pytest tests/test_stage4b8_context_switch_e2e_proof.py -q --tb=short
"""

import uuid

import pytest

from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember
from app.identity.models.user import User
from app.identity.services.organisation_role_provisioning import (
    provision_organisation_roles,
)
from app.auth.roles import assign_org_role


# ---------------------------------------------------------------------------
# Fixtures & minimal setup helpers (mirrors the remediation suite style)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _seed_org_roles(app):
    """Seed the standard global + org role templates once per session. The
    remediation suite uses the same ``seed_all`` pattern; assign_org_role also
    provisions on demand, so this is belt-and-braces only."""
    from app.auth.seed_roles import seed_all

    with app.app_context():
        seed_all()
    yield


def _snapshot_session(client):
    """Return a plain dict of the real Flask session (production keys)."""
    with client.session_transaction() as sess:
        return {k: v for k, v in sess.items() if not k.startswith("_flashes")}


def _active_context(app, client, public_id):
    """Resolve the active context for *public_id* against the live DB using
    the real production chain.

    Session values are read from the REAL HTTP session object (Flask-Session,
    Redis-backed) exposed by ``client.session_transaction()`` — the exact
    values the switch route wrote. The context is then validated with the
    production ``validate_context`` (the same validator ``switch_context`` and
    ``get_active_context`` call) and permissions are resolved with the
    production ``resolve_effective_permissions``. The nested
    ``flask.session`` proxy is deliberately not used here because its binding
    is fragile inside ``session_transaction``; the session dict itself is the
    authoritative, real-path source the app reads on the next request."""
    from app.auth.context import (
        ContextType,
        _personal_context,
        validate_context,
        resolve_effective_permissions,
    )

    with client.session_transaction() as sess:
        snapshot = {
            k: v for k, v in sess.items() if not k.startswith("_flashes")
        }
    with app.app_context():
        user = User.query.filter_by(public_id=public_id).first()
        context_type = snapshot.get("active_context_type") or "personal"
        if context_type == ContextType.PERSONAL.value or context_type == "personal":
            context = _personal_context(user)
        else:
            context = validate_context(
                user,
                {
                    "type": context_type,
                    "id": snapshot.get("active_context_id"),
                    "role": snapshot.get("active_role"),
                },
            )
            assert context is not None, (
                f"production validate_context rejected {context_type} "
                f"{snapshot.get('active_context_id')} for {public_id}"
            )
        permissions = resolve_effective_permissions(user, context)
        return {
            "type": context.type.value,
            "public_id": context.public_id,
            "role": context.role,
            "permissions": permissions,
        }


def _make_org(tag):
    org = Organisation(
        org_id=str(uuid.uuid4()),
        legal_name=f"Switch Org {tag} {uuid.uuid4().hex[:6]}",
        country="UG",
        region="Central",
        org_type="business",
        contact_email=f"switch-{tag}-{uuid.uuid4().hex[:6]}@example.com",
    )
    db.session.add(org)
    db.session.flush()
    return org


def _make_user(tag):
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"{tag}_{uuid.uuid4().hex[:8]}",
        email=f"{tag}_{uuid.uuid4().hex[:8]}@example.com",
        is_active=True,
        is_verified=True,
        email_verified=True,
    )
    user.set_password("TestPass123!")
    db.session.add(user)
    db.session.flush()
    return user


def _membership(org, user):
    member = OrganisationMember(
        user_id=user.id,
        organisation_id=org.id,
        is_active=True,
    )
    db.session.add(member)
    db.session.flush()
    return member


def _switch(client, payload):
    """Real POST /switch-context JSON round-trip."""
    return client.post("/switch-context", json=payload)


# Permission pick: hr_manager (Org A) holds org.members.view + org.members.manage.
# transport_manager (Org B) holds org.transport.view + org.transport.manage
# + org.transport.dispatch.  "org.members.manage" is therefore A-only,
# "org.transport.dispatch" is B-only.
A_ONLY_PERMISSION = "org.members.manage"
B_ONLY_PERMISSION = "org.transport.dispatch"
A_VIEW_PERMISSION = "org.members.view"


class TestContextSwitchE2EProof:
    """End-to-end proof — real login -> real switch -> real permission
    resolution, on the live PostgreSQL test DB."""

    def test_real_login_personal_org_back_never_leaks(self, app, fresh_client):
        handles = _setup_two_org_user(app)
        user = handles["user"]

        # -- 1. Real login as a normal User ----------------------------------
        login_resp = fresh_client.post(
            "/login",
            data={"username": user["email"], "password": "TestPass123!"},
            follow_redirects=False,
        )
        assert login_resp.status_code == 302
        assert "/user/dashboard" in login_resp.headers["Location"]

        pre = _snapshot_session(fresh_client)
        # Flask-Login identity key is set by the real login flow.
        assert pre.get("_user_id") == user["public_id"]

        # Baseline: default PERSONAL context.
        personal = _active_context(app, fresh_client, user["public_id"])
        assert personal["type"] == "personal"
        assert personal["public_id"] is None
        assert A_ONLY_PERMISSION not in personal["permissions"]
        assert B_ONLY_PERMISSION not in personal["permissions"]

        # -- 2. Personal -> Organisation A (role hr_manager) ------------------
        resp = _switch(
            fresh_client,
            {
                "type": "organisation",
                "public_id": handles["org_a"]["public_id"],
                "role": "hr_manager",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["context"]["type"] == "organisation"
        assert body["context"]["public_id"] == handles["org_a"]["public_id"]
        assert body["context"]["role"] == "hr_manager"

        after_a = _snapshot_session(fresh_client)
        # IDENTITY IS PRESERVED — same authenticated human, only selection changed.
        assert after_a.get("_user_id") == pre.get("_user_id") == user["public_id"]
        assert after_a.get("active_context_type") == "organisation"
        assert after_a.get("active_context_id") == handles["org_a"]["public_id"]
        assert after_a.get("active_role") == "hr_manager"

        ctx_a = _active_context(app, fresh_client, user["public_id"])
        assert ctx_a["type"] == "organisation"
        assert ctx_a["public_id"] == handles["org_a"]["public_id"]
        # Positive: permission granted ONLY in A is effective now.
        assert A_ONLY_PERMISSION in ctx_a["permissions"]
        assert A_VIEW_PERMISSION in ctx_a["permissions"]
        # Negative: permission granted ONLY in another org (B) is NOT effective.
        assert B_ONLY_PERMISSION not in ctx_a["permissions"]

        # -- 3. Organisation A -> Personal (back) -----------------------------
        resp = _switch(fresh_client, {"type": "personal"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["context"]["type"] == "personal"

        back = _snapshot_session(fresh_client)
        # Still the same human.
        assert back.get("_user_id") == user["public_id"]
        assert back.get("active_context_type") == "personal"
        assert back.get("active_context_id") is None

        ctx_back = _active_context(app, fresh_client, user["public_id"])
        assert ctx_back["type"] == "personal"
        # Org permissions from A are no longer effective.
        assert A_ONLY_PERMISSION not in ctx_back["permissions"]
        assert B_ONLY_PERMISSION not in ctx_back["permissions"]

        # -- 4. Personal -> Organisation B (never A) --------------------------
        resp = _switch(
            fresh_client,
            {
                "type": "organisation",
                "public_id": handles["org_b"]["public_id"],
                "role": "transport_manager",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["context"]["public_id"] == handles["org_b"]["public_id"]

        after_b = _snapshot_session(fresh_client)
        assert after_b.get("_user_id") == user["public_id"]
        assert after_b.get("active_context_id") == handles["org_b"]["public_id"]

        ctx_b = _active_context(app, fresh_client, user["public_id"])
        # Context is B — never A.
        assert ctx_b["type"] == "organisation"
        assert ctx_b["public_id"] == handles["org_b"]["public_id"]
        # B-only permission is effective only in B.
        assert B_ONLY_PERMISSION in ctx_b["permissions"]
        # A-only permission is NOT effective in B.
        assert A_ONLY_PERMISSION not in ctx_b["permissions"]

        # -- 5. Foreign / fabricated organisation fails closed -----------------
        resp = _switch(
            fresh_client,
            {
                "type": "organisation",
                "public_id": handles["fake_org"]["public_id"],
                "role": "org_owner",
            },
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body.get("success") is False

        after_fake = _snapshot_session(fresh_client)
        # Fail-closed: no foreign context ever becomes active.
        assert after_fake.get("active_context_id") == handles["org_b"]["public_id"]
        assert after_fake.get("_user_id") == user["public_id"]

        ctx_fake = _active_context(app, fresh_client, user["public_id"])
        assert ctx_fake["public_id"] == handles["org_b"]["public_id"]
        assert B_ONLY_PERMISSION in ctx_fake["permissions"]
        assert A_ONLY_PERMISSION not in ctx_fake["permissions"]

        # Completely fabricated UUID also fails closed.
        resp = _switch(
            fresh_client,
            {
                "type": "organisation",
                "public_id": str(uuid.uuid4()),
                "role": "org_owner",
            },
        )
        assert resp.status_code == 400
        after_fake2 = _snapshot_session(fresh_client)
        assert after_fake2.get("active_context_id") == handles["org_b"]["public_id"]


def _setup_two_org_user(app):
    """Create a plain verified User who is a member of Org A (hr_manager) and
    Org B (transport_manager), plus a fabricated third org they do NOT belong
    to. Returns scalar handles only (never ORM instances across requests)."""
    with app.app_context():
        org_a = _make_org("A")
        provision_organisation_roles(org_a)
        org_b = _make_org("B")
        provision_organisation_roles(org_b)
        fake_org = _make_org("FOREIGN")
        provision_organisation_roles(fake_org)

        user = _make_user("switch")
        member_a = _membership(org_a, user)
        assign_org_role(user.id, org_a.id, "hr_manager")
        member_a.invalidate_permission_cache()
        member_b = _membership(org_b, user)
        assign_org_role(user.id, org_b.id, "transport_manager")
        member_b.invalidate_permission_cache()

        db.session.commit()

        return {
            "user": {"public_id": str(user.public_id), "email": user.email},
            "org_a": {"public_id": org_a.org_id, "legal_name": org_a.legal_name},
            "org_b": {"public_id": org_b.org_id, "legal_name": org_b.legal_name},
            "fake_org": {"public_id": fake_org.org_id},
        }


@pytest.fixture
def fresh_client(app):
    """A fresh test client per test — real session isolation."""
    return app.test_client()