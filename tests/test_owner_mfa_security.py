"""Security regressions for persistent platform-owner MFA enforcement."""
from datetime import datetime, timezone

import pyotp

from app.extensions import db
from app.identity.models.user import MFASecret
from app.models.system_config import SystemConfig
from sqlalchemy import inspect as sa_inspect
from flask import url_for


def test_persisted_owner_mfa_policy_overrides_process_config(app):
    with app.app_context():
        app.config["REQUIRE_OWNER_MFA"] = False
        SystemConfig.set(
            "REQUIRE_OWNER_MFA",
            True,
            value_type="bool",
            category="security",
            commit=True,
        )
        from app.auth.security_policy import owner_mfa_required
        assert owner_mfa_required() is True

        SystemConfig.set(
            "REQUIRE_OWNER_MFA",
            False,
            value_type="bool",
            category="security",
            commit=True,
        )
        assert owner_mfa_required() is False





def test_owner_mfa_policy_fails_closed_when_database_unavailable_in_docker(app, monkeypatch):
    from app.auth.security_policy import owner_mfa_required
    from app.models.system_config import SystemConfig

    with app.app_context():
        original_app_env = app.config.get("APP_ENV")
        original_flask_env = app.config.get("FLASK_ENV")
        app.config["APP_ENV"] = "docker"
        app.config["FLASK_ENV"] = "development"
        app.config["REQUIRE_OWNER_MFA"] = False

        def unavailable(*args, **kwargs):
            raise RuntimeError("settings store unavailable")

        monkeypatch.setattr(SystemConfig, "get", classmethod(lambda cls, *a, **k: unavailable()))
        assert owner_mfa_required() is True

        app.config["APP_ENV"] = original_app_env
        app.config["FLASK_ENV"] = original_flask_env


def test_owner_mfa_toggle_requires_every_active_owner_to_have_verified_totp(
    app, admin_client, test_admin
):
    from app.identity.models.user import User, UserRole
    from app.identity.models.roles_permission import get_or_create_role
    from app.auth.security_policy import totp_proof_setting_key

    # Capture the database identity while the fixture is still attached.
    from sqlalchemy import inspect as sa_inspect
    owner_pk = sa_inspect(test_admin).identity[0]
    owner_suffix = str(owner_pk)
    with app.test_request_context():
        owner_mfa_url = url_for("admin.owner.update_owner_mfa_requirement")

    with app.app_context():
        SystemConfig.set(
            "REQUIRE_OWNER_MFA", False, value_type="bool",
            category="security", commit=True,
        )
        owner_role = get_or_create_role("owner", scope="global", level=1)
        current_owner = db.session.get(User, owner_pk)
        assert current_owner is not None
        current_owner.mfa_enabled = True
        current_owner_verified_at = datetime.now(timezone.utc)
        current_owner_secret = pyotp.random_base32()
        current_owner_factor = MFASecret(
            user_id=current_owner.id,
            mfa_type="totp",
            secret=current_owner_secret,
            is_active=True,
            last_used=current_owner_verified_at,
        )
        current_owner_factor.set_totp_secret(current_owner_secret)
        db.session.add(current_owner_factor)
        from app.auth.security_policy import record_totp_proof
        record_totp_proof(
            current_owner,
            current_owner_verified_at,
            secret=current_owner_secret,
            commit=False,
        )

        # A second active owner has not yet enrolled.
        other_owner = User(
            username=f"not_enrolled_{owner_suffix}",
            email=f"not_enrolled_{owner_suffix}@test.example.com",
            is_active=True,
            is_verified=True,
        )
        other_owner.set_password("TestPass123!")
        db.session.add(other_owner)
        db.session.flush()
        db.session.add(UserRole(user_id=other_owner.id, role_id=owner_role.id))
        db.session.commit()
        other_owner_id = other_owner.id

    # The acting owner has a fresh, actual TOTP step-up for this policy change.
    with admin_client.session_transaction() as browser_session:
        browser_session["mfa_verified"] = True
        browser_session["mfa_verified_at"] = datetime.now(timezone.utc).isoformat()
        browser_session["mfa_verified_method"] = "totp"

    response = admin_client.post(
        owner_mfa_url,
        data={"require_owner_mfa": "on"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert SystemConfig.get("REQUIRE_OWNER_MFA", False) is False

        other_owner = db.session.get(User, other_owner_id)
        other_owner.mfa_enabled = True
        other_owner_verified_at = datetime.now(timezone.utc)
        other_owner_secret = pyotp.random_base32()
        other_owner_factor = MFASecret(
            user_id=other_owner.id,
            mfa_type="totp",
            secret=other_owner_secret,
            is_active=True,
            last_used=other_owner_verified_at,
        )
        other_owner_factor.set_totp_secret(other_owner_secret)
        db.session.add(other_owner_factor)
        record_totp_proof(
            other_owner,
            other_owner_verified_at,
            secret=other_owner_secret,
            commit=False,
        )
        db.session.commit()

    response = admin_client.post(
        owner_mfa_url,
        data={"require_owner_mfa": "on"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert SystemConfig.get("REQUIRE_OWNER_MFA", False) is True


def test_new_owner_must_enroll_and_prove_totp_before_sign_in(
    app, client, test_admin
):
    from sqlalchemy import inspect as sa_inspect

    # Do not use a detached ORM instance after leaving the fixture's session.
    owner_pk = sa_inspect(test_admin).identity[0]
    with app.app_context():
        SystemConfig.set(
            "REQUIRE_OWNER_MFA", True, value_type="bool",
            category="security", commit=True,
        )
        owner = db.session.get(type(test_admin), owner_pk)
        assert owner is not None
        owner_username = owner.username
        owner_public_id = owner.public_id
        owner.mfa_enabled = False
        db.session.query(MFASecret).filter_by(user_id=owner.id).delete()
        db.session.commit()

    # A correct password earns only a limited, short-lived enrollment session.
    response = client.post(
        "/login",
        data={"username": owner_username, "password": "TestPass123!"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/mfa/setup")
    with client.session_transaction() as browser_session:
        assert "_user_id" not in browser_session
        assert browser_session.get("pending_owner_mfa_setup_user") == owner_public_id

    setup_page = client.get("/mfa/setup")
    assert setup_page.status_code == 200
    assert b"Verify the authenticator" in setup_page.data

    generated = client.post(
        "/mfa/enable",
        data={"device_name": "Owner authenticator"},
    )
    assert generated.status_code == 200
    setup = generated.get_json()
    assert setup["success"] is True
    assert setup["qr_code"].startswith("data:image/png;base64,")
    assert len(setup["backup_codes"]) == 10

    # No active MFA record is created before the TOTP possession proof.
    with app.app_context():
        owner = db.session.get(type(test_admin), owner_pk)
        assert owner.mfa_enabled is False
        assert (
            db.session.query(MFASecret)
            .filter_by(user_id=owner.id, mfa_type="totp", is_active=True)
            .first()
            is None
        )

    invalid = client.post("/mfa/confirm", json={"code": "ABC123"})
    assert invalid.status_code == 400
    with app.app_context():
        owner = db.session.get(type(test_admin), owner_pk)
        assert owner.mfa_enabled is False
        assert (
            db.session.query(MFASecret)
            .filter_by(user_id=owner.id, mfa_type="totp", is_active=True)
            .first()
            is None
        )

    # A live TOTP code proves possession; only now does the database record activate.
    code = pyotp.TOTP(setup["secret"]).now()
    confirmed = client.post("/mfa/confirm", json={"code": code})
    assert confirmed.status_code == 200
    assert confirmed.get_json()["success"] is True
    assert confirmed.get_json()["next_url"].endswith("/login")

    with app.app_context():
        owner = db.session.get(type(test_admin), owner_pk)
        assert owner.mfa_enabled is True
        record = (
            db.session.query(MFASecret)
            .filter_by(user_id=owner.id, mfa_type="totp", is_active=True)
            .one()
        )
        assert record.last_used is not None
        from app.auth.security_policy import totp_proof_setting_key
        assert SystemConfig.get(totp_proof_setting_key(owner)) is not None
        assert len(record.get_backup_codes()) == 10

    with client.session_transaction() as browser_session:
        assert "_user_id" not in browser_session
        assert "pending_owner_mfa_setup_user" not in browser_session

    # The owner must now sign in again with both factors.
    challenge = client.post(
        "/login",
        data={"username": owner_username, "password": "TestPass123!"},
        follow_redirects=False,
    )
    assert challenge.status_code == 200
    assert b'name="mfa_code"' in challenge.data

    code = pyotp.TOTP(setup["secret"]).now()
    completed = client.post(
        "/login",
        data={
            "username": owner_username,
            "password": "TestPass123!",
            "mfa_code": code,
        },
        follow_redirects=False,
    )
    assert completed.status_code == 302
    with client.session_transaction() as browser_session:
        assert browser_session.get("_user_id") == owner_public_id
        assert browser_session.get("mfa_verified") is True


def test_mfa_setup_page_requires_a_valid_enrollment_identity(app, client):
    response = client.get("/mfa/setup", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_recent_backup_code_login_can_safely_replace_legacy_authenticator(
    app, admin_client, test_admin
):
    from sqlalchemy import inspect as sa_inspect
    from app.identity.models.user import User
    from app.auth.security_policy import totp_proof_setting_key

    owner_pk = sa_inspect(test_admin).identity[0]
    old_secret = pyotp.random_base32()

    with app.app_context():
        owner = db.session.get(User, owner_pk)
        owner.mfa_enabled = True
        old_record = MFASecret(
            user_id=owner.id,
            mfa_type="totp",
            secret=old_secret,
            is_active=True,
        )
        db.session.add(old_record)
        db.session.commit()

    # An old active secret must not be replaced from a password-only session.
    with admin_client.session_transaction() as browser_session:
        browser_session.pop("mfa_verified", None)
        browser_session.pop("mfa_verified_at", None)
        browser_session.pop("mfa_verified_method", None)
        browser_session["_fresh"] = True

    denied_page = admin_client.get("/mfa/setup", follow_redirects=False)
    assert denied_page.status_code == 302
    assert denied_page.headers["Location"].endswith("/mfa/status")

    denied_generate = admin_client.post(
        "/mfa/enable",
        data={"device_name": "Replacement authenticator"},
    )
    assert denied_generate.status_code == 403

    # A recent successful one-time backup-code login is a valid factor for
    # replacing a lost authenticator, but does not count as TOTP proof for the
    # platform-wide MFA policy toggle.
    with admin_client.session_transaction() as browser_session:
        browser_session["mfa_verified"] = True
        browser_session["mfa_verified_at"] = datetime.now(timezone.utc).isoformat()
        browser_session["mfa_verified_method"] = "backup"
        browser_session["_fresh"] = True

    replacement_page = admin_client.get("/mfa/setup")
    assert replacement_page.status_code == 200
    assert b"replace the old one only after" in replacement_page.data

    generated = admin_client.post(
        "/mfa/enable",
        data={"device_name": "Replacement authenticator"},
    )
    assert generated.status_code == 200
    setup = generated.get_json()
    assert setup["success"] is True
    assert setup["secret"] != old_secret

    # The old factor remains stored until proof of possession of the new one.
    with app.app_context():
        owner = db.session.get(User, owner_pk)
        record = db.session.query(MFASecret).filter_by(
            user_id=owner.id, mfa_type="totp", is_active=True
        ).one()
        assert record.secret == old_secret

    new_code = pyotp.TOTP(setup["secret"]).now()
    confirmed = admin_client.post("/mfa/confirm", json={"code": new_code})
    assert confirmed.status_code == 200
    assert confirmed.get_json()["success"] is True

    with app.app_context():
        owner = db.session.get(User, owner_pk)
        record = db.session.query(MFASecret).filter_by(
            user_id=owner.id, mfa_type="totp", is_active=True
        ).one()
        assert record.get_totp_secret() == setup["secret"]
        from app.auth.security_policy import totp_proof_matches
        assert totp_proof_matches(owner, setup["secret"]) is True


def test_global_owner_policy_requires_recent_totp_not_backup_code(app):
    from flask import session
    from app.auth.security_policy import recent_owner_totp_proof

    with app.test_request_context():
        session["mfa_verified"] = True
        session["mfa_verified_at"] = datetime.now(timezone.utc).isoformat()
        session["mfa_verified_method"] = "totp"
        assert recent_owner_totp_proof(max_age_seconds=300) is True

        session["mfa_verified_method"] = "backup"
        assert recent_owner_totp_proof(max_age_seconds=300) is False

        session["mfa_verified_method"] = "totp"
        session["mfa_verified_at"] = (
            datetime.now(timezone.utc).replace(year=2020).isoformat()
        )
        assert recent_owner_totp_proof(max_age_seconds=300) is False
