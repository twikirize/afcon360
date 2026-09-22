"""Regression tests for the ``policy.can()`` org-id contract (Node C).

Proves the minimal authorization-context bridge fix:

1. ``can(user, permission)`` with ``org_id=None`` is a GLOBAL permission
   check only. Stale legacy session keys (``active_context_type``,
   ``active_context_id``, ``current_context``, ``current_org_id``,
   ``organisation_id``) must NEVER select an organisation scope, regardless
   of identifier shape (internal PK or public ``org.org_id``).

2. ``can(user, permission, org_id=<internal Organisation.id>)`` still
   delegates to ``has_org_permission`` (unchanged contract, matches
   ``tests/test_org_permission_read_path.py::test_policy_can_integration``).

3. Granting is membership/role-authoritative: stale keys cannot grant an
   org-scoped permission to a user with no membership in the org.

This is the regression proof for Case A1 / A2 / B1 / B2 of the legacy
context-key audit: the only valid org authorization path through ``can()``
is the explicit internal-PK ``org_id``; otherwise org-scoped permissions
resolve via membership/context entry points (``can_in_context``,
``OrganisationMember.has_permission``).
"""
import uuid

import pytest

from app.identity.models.organisation import Organisation
from app.identity.models.organisation_member import OrganisationMember
from app.identity.models.roles_permission import Role
from app.identity.models.user import User, UserRole
from app.auth.roles import assign_org_role
from app.identity.services.organisation_role_provisioning import (
    provision_organisation_roles,
)
from app.extensions import db


@pytest.fixture(autouse=True, scope="session")
def _seed_global_roles(app):
    """Seed global roles + permissions + org-role templates once."""
    from app.auth.seed_roles import seed_all

    with app.app_context():
        seed_all()
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(role_names=None):
    org = Organisation(
        legal_name=f"Policy Org {uuid.uuid4().hex[:8]}",
        org_id=str(uuid.uuid4()),
        country="UG",
    )
    db.session.add(org)
    db.session.flush()
    return org


def _make_user(role_names=()):
    suffix = uuid.uuid4().hex[:8]
    user = User(
        public_id=str(uuid.uuid4()),
        username=f"pcan_{suffix}",
        email=f"pcan-{suffix}@example.com",
        password_hash="hashed",
        is_active=True,
    )
    db.session.add(user)
    db.session.flush()
    for name in role_names:
        role = Role.query.filter_by(name=name, scope="global").first()
        assert role is not None, f"global role {name!r} must be seeded"
        db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.flush()
    return user


def _add_member(org, user):
    member = OrganisationMember(
        user_id=user.id,
        organisation_id=org.id,
    )
    db.session.add(member)
    db.session.flush()
    return member


def _make_org_admin_member():
    org = _make_org()
    user = _make_user()
    _add_member(org, user)
    provision_organisation_roles(org, roles={"org_admin"})
    assign_org_role(user.id, org.id, "org_admin")
    db.session.expire_all()
    return org.id, str(org.org_id), user.id


def _stale_org_session(org_internal, org_public, *, public_id=True):
    """Stale legacy + canonical org-context keys (worst case for the bug)."""
    return {
        "active_context_type": "organisation",
        "active_context_id": org_public,
        "active_role": "org_admin",
        "current_context": "organisation",
        "current_org_id": org_internal,
        "organisation_id": org_public if public_id else org_internal,
    }


def _can_in_session(app, user_internal, permission, *, org_id=None, stale=None):
    """Run ``can()`` inside a request context with an optional session fill."""
    from app.auth.policy import can

    with app.app_context(), app.test_request_context():
        from flask import session

        if stale is not None:
            session.clear()
            session.update(stale)
        user = db.session.get(User, user_internal)
        assert user is not None, "user must exist"
        if org_id is not None:
            return can(user, permission, org_id=org_id)
        return can(user, permission)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_org_scope_via_explicit_internal_org_id_only(app):
    """An org_admin member passes org-scoped checks ONLY via explicit
    internal ``org_id``; the omissive `can()` never resolves org scope."""
    with app.app_context():
        org_internal, org_public, user_internal = _make_org_admin_member()
        db.session.commit()

    # Contract preserved: explicit internal-PK org_id delegates to
    # has_org_permission (only valid org authorization path through can()).
    assert (
        _can_in_session(app, user_internal, "org.finance.view", org_id=org_internal)
        is True
    )
    assert (
        _can_in_session(app, user_internal, "org.settings.manage", org_id=org_internal)
        is False
    )

    # Omissive can() (no org_id) is global-only even inside an escalating
    # stale org session (legacy PUBLIC and INTERNAL identifier shapes).
    assert (
        _can_in_session(
            app,
            user_internal,
            "org.finance.view",
            stale=_stale_org_session(org_internal, org_public, public_id=True),
        )
        is False
    )
    assert (
        _can_in_session(
            app,
            user_internal,
            "org.finance.view",
            stale=_stale_org_session(org_internal, org_public, public_id=False),
        )
        is False
    )


def test_stale_org_keys_do_not_grant_org_scope_to_non_member(app):
    """Case B2 regression: a user with NO membership in the org cannot pass
    an org-scoped permission via stale legacy keys, regardless of shape."""
    with app.app_context():
        org = _make_org()
        org_internal = org.id
        org_public = str(org.org_id)
        outsider = _make_user()
        db.session.commit()
        outsider_internal = outsider.id

    # Worst case: stale INTERNAL org PK (the former Case B2 grant path).
    assert (
        _can_in_session(
            app,
            outsider_internal,
            "org.finance.view",
            stale=_stale_org_session(org_internal, org_public, public_id=False),
        )
        is False
    )
    assert (
        _can_in_session(
            app,
            outsider_internal,
            "org.accommodation.manage",
            stale=_stale_org_session(org_internal, org_public, public_id=False),
        )
        is False
    )

    # Stale PUBLIC org ID (former Case A1 path) is equally inert.
    assert (
        _can_in_session(
            app,
            outsider_internal,
            "org.finance.view",
            stale=_stale_org_session(org_internal, org_public, public_id=True),
        )
        is False
    )


def test_global_check_unaffected_by_stale_session(app):
    """Global permissions resolve identically regardless of session state."""
    with app.app_context():
        org = _make_org()
        org_internal = org.id
        org_public = str(org.org_id)
        admin = _make_user(role_names=("transport_admin",))
        db.session.commit()
        admin_internal = admin.id

    stale = _stale_org_session(org_internal, org_public, public_id=True)
    assert _can_in_session(app, admin_internal, "transport.view", stale=stale) is True
    assert (
        _can_in_session(app, admin_internal, "transport.settings", stale=stale) is False
    )
    # Stale org keys must not widen the global grant set.
    assert (
        _can_in_session(app, admin_internal, "org.finance.view", stale=stale) is False
    )


def test_owner_bypass_is_preserved(app):
    """The owner bypass (checked once, centrally) is untouched."""
    with app.app_context():
        org = _make_org()
        org_internal = org.id
        org_public = str(org.org_id)
        owner = _make_user(role_names=("owner",))
        db.session.commit()
        owner_internal = owner.id

    stale = _stale_org_session(org_internal, org_public, public_id=False)
    assert (
        _can_in_session(app, owner_internal, "org.finance.view", org_id=org_internal)
        is True
    )
    assert (
        _can_in_session(app, owner_internal, "org.finance.view", stale=stale) is True
    )