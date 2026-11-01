"""Security regressions for persistent platform-owner MFA enforcement."""
from datetime import datetime, timezone

import pyotp

from app.extensions import db
from app.identity.models.user import MFASecret
from app.models.system_config import SystemConfig


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


def test_owner_mfa_toggle_requires_every_active_owner_to_have_verified_totp(
    app, admin_client, test_admin
):
    from app.identity.models.user import User, UserRole
    from app.identity.models.roles_permission import get_or_create_role

    with app.app_context():
        SystemConfig.set(
            "REQUIRE_OWNER_MFA", False, value_type="bool",
            category="security", commit=True,
        )
        owner_role = get_or_create_role("owner", scope="global", level=1)
        current_owner = db.session.get(User, test_admin.id)
        current_owner.mfa_enabled = True
        current_owner_verified_at = datetime.now(timezone.utc)
        db.session.add(
            MFASecret(
                user_id=current_owner.id,
                mfa_type="totp",
                secret=pyotp.random_base32(),
                is_active=True,
                last_used=current_owner_verified_at,
            )
        )
        from app.auth.security_policy import totp_proof_setting_key
        SystemConfig.set(
            totp_proof_setting_key(current_owner),
            current_owner_verified_at.isoformat(),
            value_type="str",
            category="security",
            commit=False,
        )

        # A second active owner has not yet enrolled.
        other_owner = User(
            username=f"not_enrolled_{test_admin.id}",
            email=f"not_enrolled_{test_admin.id}@test.example.com",
            is_active=True,
            is_verified=True,
        )
        other_owner.set_password("TestPass123!")
        db.session.add(other_owner)
        db.session.flush()
        db.session.add(UserRole(user_id=other_owner.id, role_id=owner_role.id))
        db.session.commit()
        other_owner_id = other_owner.id

    # The acting owner has passed MFA on this session (step-up requirement).
    with admin_client.session_transaction() as session:
        session["mfa_verified"] = True
        session["mfa_verified_at"] = datetime.now(timezone.utc).isoformat()
        session["mfa_verified_method"] = "totp"

    response = admin_client.post(
        "/owner/settings/owner-mfa",
        data={"require_owner_mfa": "on"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert SystemConfig.get("REQUIRE_OWNER_MFA", False) is False

        other_owner = db.session.get(User, other_owner_id)
        other_owner.mfa_enabled = True
        other_owner_verified_at = datetime.now(timezone.utc)
        db.session.add(
            MFASecret(
                user_id=other_owner.id,
                mfa_type="totp",
                secret=pyotp.random_base32(),
                is_active=True,
                last_used=other_owner_verified_at,
            )
        )
        SystemConfig.set(
            totp_proof_setting_key(other_owner),
            other_owner_verified_at.isoformat(),
            value_type="str",
            category="security",
            commit=False,
        )
        db.session.commit()

    response = admin_client.post(
        "/owner/settings/owner-mfa",
        data={"require_owner_mfa": "on"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert SystemConfig.get("REQUIRE_OWNER_MFA", False) is True


def test_new_owner_must_enroll_and_prove_totp_before_sign_in(
    app, client, test_admin
):
    with app.app_context():
        SystemConfig.set(
            "REQUIRE_OWNER_MFA", True, value_type="bool",
            category="security", commit=True,
        )
        owner = db.session.get(type(test_admin), test_admin.id)
        owner.mfa_enabled = False
        db.session.query(MFASecret).filter_by(user_id=owner.id).delete()
        db.session.commit()

    # A correct password earns only a limited, short-lived enrollment session.
    response = client.post(
        "/login",
        data={"username": test_admin.username, "password": "TestPass123!"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/mfa/setup")
    with client.session_transaction() as session:
        assert "_user_id" not in session
        assert session.get("pending_owner_mfa_setup_user") == test_admin.public_id

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

    # The account and database must not claim MFA is enabled before proof.
    with app.app_context():
        owner = db.session.get(type(test_admin), test_admin.id)
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
        owner = db.session.get(type(test_admin), test_admin.id)
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
        owner = db.session.get(type(test_admin), test_admin.id)
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

    with client.session_transaction() as session:
        assert "_user_id" not in session
        assert "pending_owner_mfa_setup_user" not in session

    # The owner must now sign in again with both factors.
    challenge = client.post(
        "/login",
        data={"username": test_admin.username, "password": "TestPass123!"},
        follow_redirects=False,
    )
    assert challenge.status_code == 200
    assert b'name="mfa_code"' in challenge.data

    code = pyotp.TOTP(setup["secret"]).now()
    completed = client.post(
        "/login",
        data={
            "username": test_admin.username,
            "password": "TestPass123!",
            "mfa_code": code,
        },
        follow_redirects=False,
    )
    assert completed.status_code == 302
    with client.session_transaction() as session:
        assert session.get("_user_id") == test_admin.public_id
        assert session.get("mfa_verified") is True


def test_mfa_setup_page_requires_a_valid_enrollment_identity(app, client):
    response = client.get("/mfa/setup", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
