"""Focused tests for the classification-admin category-edit RESTRICT guard.

Covers ``app/admin/classification.py::category_edit`` against the live
PostgreSQL schema:

1. Renaming a referenced category code is rejected with an actionable
   message (reassign-first), before any database update is attempted.
2. The rejected request leaves the stored category code unchanged.
3. Non-code edits on a referenced category remain allowed.
4. Renaming an unreferenced category still succeeds.

Conventions (matches tests/test_org_admin_remediation_http.py and
tests/test_auth_require_role.py): scalar handles only, ``db_session``
fixture with teardown rollback, Flask-Login session login via public id
read while the instance is attached.
"""

import uuid

import pytest

from app.extensions import db
from app.identity.models.organisation_catalogues import (
    OrganisationCategory,
    OrganisationTypeCatalogue,
)


def _uid(prefix):
    return "%s_%s" % (prefix, uuid.uuid4().hex[:8])


def _make_super_admin(db_session):
    """User holding the global super_admin role; returns public-id string."""
    from app.identity.models.roles_permission import Role
    from app.identity.models.user import User, UserRole

    user = User(
        public_id=str(uuid.uuid4()),
        username=_uid("clsadmin"),
        email="%s@example.com" % _uid("clsadmin"),
        password_hash="hashed",
        is_active=True,
        is_verified=True,
        email_verified=True,
    )
    user.set_password("TestPassword123!")
    db_session.add(user)
    db_session.flush()
    role = Role.query.filter_by(name="super_admin").first()
    if role is None:
        role = Role(name="super_admin", scope="global")
        db_session.add(role)
        db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    db_session.flush()
    return str(user.public_id)


def _make_category(db_session, code):
    """Persisted category; returns scalar (id, code)."""
    cat = OrganisationCategory(
        code=code,
        label="Test %s" % code,
        sort_order=0,
        is_active=True,
    )
    db_session.add(cat)
    db_session.flush()
    return {"id": cat.id, "code": cat.code}


def _make_type(db_session, code, category_code, is_active=True):
    """Persisted catalogue type referencing a category code."""
    typ = OrganisationTypeCatalogue(
        code=code,
        label="Test %s" % code,
        category_code=category_code,
        sort_order=0,
        is_active=is_active,
    )
    db_session.add(typ)
    db_session.flush()
    return {"id": typ.id, "code": typ.code}


def _login(client, public_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = public_id
        sess["_fresh"] = True


def _post_edit(client, category_id, name, display_order="0", active=True):
    # NOTE: classification_bp carries its own url_prefix and is nested
    # under admin_bp (see flask routes) — the mounted path is doubled.
    # This is closed-workstream registration, not under test here.
    form = {"name": name, "display_order": display_order, "description": ""}
    if active:
        form["is_active"] = "on"
    return client.post(
        "/admin/admin/classification/%s/edit" % category_id,
        data=form,
        follow_redirects=True,
    )


def _stored_code(category_id):
    row = OrganisationCategory.query.get(category_id)
    assert row is not None
    return row.code


class TestReferencedRenameGuard:
    def test_rename_referenced_category_rejected_with_actionable_message(
        self, app, db_session
    ):
        admin_pid = _make_super_admin(db_session)
        cat = _make_category(db_session, "clsaguard")
        _make_type(db_session, "clsaguard_type", cat["code"])
        db_session.commit()
        client = app.test_client()
        _login(client, admin_pid)

        resp = _post_edit(client, cat["id"], "renamed_guard")

        assert resp.status_code == 200, resp.status_code
        assert b"Reassign" in resp.data, resp.data[:2000]

    def test_rejected_rename_leaves_stored_code_unchanged(
        self, app, db_session
    ):
        admin_pid = _make_super_admin(db_session)
        cat = _make_category(db_session, "clsastable")
        _make_type(db_session, "clsastable_type", cat["code"])
        db_session.commit()
        client = app.test_client()
        _login(client, admin_pid)

        _post_edit(client, cat["id"], "renamed_stable")

        assert _stored_code(cat["id"]) == "clsastable"

    def test_non_code_edit_allowed_while_referenced(
        self, app, db_session
    ):
        admin_pid = _make_super_admin(db_session)
        cat = _make_category(db_session, "clsaedit")
        _make_type(db_session, "clsaedit_type", cat["code"])
        db_session.commit()
        client = app.test_client()
        _login(client, admin_pid)

        resp = _post_edit(
            client, cat["id"], "clsaedit", display_order="7"
        )

        assert resp.status_code == 200, resp.status_code
        fresh = OrganisationCategory.query.get(cat["id"])
        assert fresh is not None
        assert fresh.code == "clsaedit"
        assert fresh.sort_order == 7

    def test_rename_unreferenced_category_succeeds(
        self, app, db_session
    ):
        admin_pid = _make_super_admin(db_session)
        cat = _make_category(db_session, "clsafree")
        db_session.commit()
        client = app.test_client()
        _login(client, admin_pid)

        resp = _post_edit(client, cat["id"], "clsafree_new")

        assert resp.status_code == 200, resp.status_code
        assert _stored_code(cat["id"]) == "clsafree_new"
