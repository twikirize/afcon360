"""
Regression proof — base navigation must follow the CANONICAL active context.

Observed defect: after a logged-in organisation member switches from
Organisation context to Personal (or another non-org context), the shared
``base.html`` navigation still shows organisation items.

The reported journey is:

    1. User has an active organisation membership and (at login, or after org
       onboarding) the legacy session keys ``current_context="organization"``
       and ``current_org_id`` / ``current_org_name`` are written.
    2. The user switches context through the canonical selector
       (``/switch-context``), which writes ONLY the canonical keys
       ``active_context_type / _id / _role`` (``app/auth/context.py``
       ``switch_context`` — asserted by test_auth_context.py
       ``test_switch_preserves_identity_and_writes_only_selection``).
    3. On the very next request the ``inject_sitewide`` context processor in
       ``app/__init__.py`` resolved the canonical context to Personal, but a
       legacy fallback block re-read ``current_context == "organization"``
       and flipped the nav BACK to organisation — overriding the live
       canonical selection. That fallback is the defect.

These tests drive the REAL production context processor
(``app/__init__.py: inject_sitewide``) against the real session + a real
PostgreSQL org membership, so they prove the navigation-state source exactly
as the template consumes it (``nav_in_org_context``, ``nav_org_id``,
``nav_org_name``).
"""

import uuid

import pytest
from flask import session
from flask_login import login_user, logout_user

from app.auth.roles import assign_org_role
from app.extensions import db
from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember
from app.identity.models.user import User
from app.identity.services.organisation_role_provisioning import (
    provision_organisation_roles,
)


def _inject_sitewide(app):
    """Return the REAL ``inject_sitewide`` context processor registered by the
    application factory (the one that feeds ``base.html``)."""
    for group in app.template_context_processors.values():
        for fn in group:
            if getattr(fn, "__name__", "") == "inject_sitewide":
                return fn
    raise AssertionError("inject_sitewide is not registered on the test app")


def _nav_for(app, user, session_entries):
    """Resolve the shared-nav dict the way a rendered ``base.html`` request
    would: real authenticated principal + real session state + the real
    ``inject_sitewide`` processor."""
    inject = _inject_sitewide(app)
    with app.test_request_context("/"):
        login_user(user, remember=False)
        session.clear()
        session.update(session_entries)
        try:
            return inject()
        finally:
            session.clear()
            logout_user()


@pytest.fixture(scope="function")
def org_member_handles(app):
    """A live user with an ACTIVE organisation membership and an org role."""
    with app.app_context():
        org = Organisation(
            org_id=str(uuid.uuid4()),
            legal_name=f"Nav Org {uuid.uuid4().hex[:6]}",
            country="UG",
            region="Central",
            org_type="business",
            contact_email=f"nav-{uuid.uuid4().hex[:6]}@example.com",
        )
        db.session.add(org)
        db.session.flush()
        provision_organisation_roles(org)

        user = User(
            public_id=str(uuid.uuid4()),
            username=f"nav_{uuid.uuid4().hex[:8]}",
            email=f"nav_{uuid.uuid4().hex[:8]}@example.com",
            is_active=True,
            is_verified=True,
            email_verified=True,
        )
        user.set_password("TestPass123!")
        db.session.add(user)
        db.session.flush()

        member = OrganisationMember(
            user_id=user.id,
            organisation_id=org.id,
            is_active=True,
        )
        db.session.add(member)
        db.session.flush()
        assign_org_role(user.id, org.id, "org_owner")
        member.invalidate_permission_cache()
        db.session.commit()

        return {
            "user_id": user.id,
            "public_id": str(user.public_id),
            "org_id": str(org.org_id),
            "org_internal_id": org.id,
            "org_legal_name": org.legal_name,
        }


def test_legacy_only_org_session_still_resolves_org_nav(app, org_member_handles):
    """Compatibility baseline: a pre-canonical session that carries valid
    legacy org keys (no canonical selection) must still resolve to org nav
    through the canonical resolver's read-only compatibility path."""
    user = User.query.get(org_member_handles["user_id"])
    nav = _nav_for(
        app,
        user,
        {
            "_user_id": org_member_handles["public_id"],
            "current_context": "organization",
            "current_org_id": org_member_handles["org_id"],
            "current_org_name": org_member_handles["org_legal_name"],
        },
    )

    assert nav["nav_in_org_context"] is True
    assert nav["nav_org_id"] == org_member_handles["org_id"]


def test_nav_is_personal_after_switch_when_legacy_org_keys_are_stale(
    app, org_member_handles
):
    """THE DEFECT. After a canonical switch to Personal the nav MUST follow
    Personal even when stale legacy ``current_context="organization"`` keys
    are still present in the session (they are written by the login/org
    routes and are never touched by ``switch_context``).

    This reproduces the reported journey: login as an org member, switch
    Organisation->Personal, and the shared navigation must stop showing the
    organisation workspace.
    """
    user = User.query.get(org_member_handles["user_id"])
    nav = _nav_for(
        app,
        user,
        {
            "_user_id": org_member_handles["public_id"],
            "active_context_type": "personal",
            "active_context_id": None,
            "active_role": "user",
            # Stale legacy keys left over from the login/default-org path.
            "current_context": "organization",
            "current_org_id": org_member_handles["org_id"],
            "current_org_name": org_member_handles["org_legal_name"],
        },
    )

    assert nav["nav_in_org_context"] is False
    assert nav["nav_org_id"] is None
    assert nav["nav_org_name"] is None


def test_nav_reports_org_context_from_canonical_selection(app, org_member_handles):
    """Positive control: when the CANONICAL selection is the organisation, the
    nav must render organisation items regardless of legacy key state."""
    user = User.query.get(org_member_handles["user_id"])
    nav = _nav_for(
        app,
        user,
        {
            "_user_id": org_member_handles["public_id"],
            "active_context_type": "organisation",
            "active_context_id": org_member_handles["org_id"],
            "active_role": "org_owner",
            "current_context": "organization",
            "current_org_id": org_member_handles["org_id"],
            "current_org_name": org_member_handles["org_legal_name"],
        },
    )

    assert nav["nav_in_org_context"] is True
    assert nav["nav_org_id"] == org_member_handles["org_id"]


def test_nav_never_exposes_internal_org_id(app, org_member_handles):
    """Dual-ID invariant (§12.1): the shared nav must never surface an
    internal organisation id. A stale legacy ``current_org_id`` holding the
    user's INTERNAL ``default_org_id`` (login default-org path writes the
    internal id) must not leak into ``nav_org_id``."""
    user = User.query.get(org_member_handles["user_id"])
    org_internal_id = org_member_handles["org_internal_id"]

    nav = _nav_for(
        app,
        user,
        {
            "_user_id": org_member_handles["public_id"],
            "active_context_type": "personal",
            "active_context_id": None,
            "active_role": "user",
            "current_context": "organization",
            "current_org_id": org_internal_id,
            "current_org_name": org_member_handles["org_legal_name"],
        },
    )

    assert nav["nav_in_org_context"] is False
    assert str(nav["nav_org_id"]) != str(org_internal_id)