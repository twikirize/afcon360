"""Focused evidence for the production login identifier contract.

Contract (app/auth/routes.py::login):
    identifier = username or email      # username takes precedence when both supplied

The route normalizes the submitted form field and passes a single identifier
into the existing authenticate_user() lookup, which already resolves a user by
username OR email. No second authentication mechanism is involved.
"""

import uuid

from flask import url_for
from werkzeug.security import generate_password_hash

from app.identity.models.user import User
from app.extensions import db


def _make_user(label):
    """Create a unique user; identifiers are randomized to avoid collisions."""
    token = uuid.uuid4().hex[:12]
    return User(
        id=uuid.uuid4().int & ((1 << 63) - 1),
        username=f"{label}_{token}",
        email=f"{label}_{token}@test.com",
        password_hash=generate_password_hash("password"),
        is_verified=True,
        is_active=True,
        email_verified=True,
    )


def _authed_user_id(client):
    with client.session_transaction() as sess:
        return sess.get("_user_id")


class TestLoginIdentifierContract:
    """Both `username` and `email` are valid login identifiers."""

    def _login(self, client, **form):
        return client.post(url_for("auth.login", _external=False), data=form)

    def _persist(self, db_session, *users):
        """Persist users and capture primitive identities before any request."""
        db_session.add_all(users)
        db_session.commit()
        return [(user.username, user.email, user.public_id) for user in users]

    def test_username_only_authenticates(self, client, db_session):
        user = _make_user("login_user_only")
        [(username, _, public_id)] = self._persist(db_session, user)

        resp = self._login(client, username=username, password="password")

        assert resp.status_code == 302
        assert _authed_user_id(client) == public_id

    def test_email_only_authenticates(self, client, db_session):
        user = _make_user("login_email_only")
        [(_, email, public_id)] = self._persist(db_session, user)

        resp = self._login(client, email=email, password="password")

        assert resp.status_code == 302
        assert _authed_user_id(client) == public_id

    def test_both_fields_valid_uses_username(self, client, db_session):
        user_a = _make_user("login_both_a")
        user_b = _make_user("login_both_b")
        [(username_a, _, public_id_a), (_, email_b, public_id_b)] = self._persist(
            db_session, user_a, user_b
        )

        resp = self._login(
            client,
            username=username_a,
            email=email_b,
            password="password",
        )

        assert resp.status_code == 302
        assert _authed_user_id(client) == public_id_a
        assert _authed_user_id(client) != public_id_b

    def test_blank_username_with_valid_email_authenticates_email(self, client, db_session):
        user = _make_user("login_blank_u")
        [(_, email, public_id)] = self._persist(db_session, user)

        resp = self._login(client, username="", email=email, password="password")

        assert resp.status_code == 302
        assert _authed_user_id(client) == public_id

    def test_valid_username_with_blank_email_authenticates_username(self, client, db_session):
        user = _make_user("login_blank_e")
        [(username, _, public_id)] = self._persist(db_session, user)

        resp = self._login(client, username=username, email="", password="password")

        assert resp.status_code == 302
        assert _authed_user_id(client) == public_id

    def test_invalid_username_with_valid_email_does_not_fall_back(self, client, db_session):
        user_b = _make_user("login_fallback_b")
        [(_, email_b, _)] = self._persist(db_session, user_b)

        resp = self._login(
            client,
            username="does-not-exist",
            email=email_b,
            password="password",
        )

        assert resp.status_code == 200
        assert b"Invalid username or password." in resp.data
        assert _authed_user_id(client) is None

    def test_both_blank_fails(self, client, db_session):
        resp = self._login(client, username="", email="", password="password")

        assert resp.status_code == 200
        assert b"Invalid username or password." in resp.data
        assert _authed_user_id(client) is None

    def test_missing_identifier_fails(self, client, db_session):
        resp = self._login(client, password="password")

        assert resp.status_code == 200
        assert b"Invalid username or password." in resp.data
        assert _authed_user_id(client) is None

    def test_invalid_identifier_fails(self, client, db_session):
        resp = self._login(client, username="ghost_user", password="password")

        assert resp.status_code == 200
        assert b"Invalid username or password." in resp.data
        assert _authed_user_id(client) is None

    def test_wrong_password_fails(self, client, db_session):
        user = _make_user("login_wrong_pw")
        [(username, _, _)] = self._persist(db_session, user)

        resp = self._login(client, username=username, password="not-the-password")

        assert resp.status_code == 200
        assert b"Invalid username or password." in resp.data
        assert _authed_user_id(client) is None
