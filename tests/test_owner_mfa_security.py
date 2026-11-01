"""Security regressions for persistent platform-owner MFA enforcement."""
from app.auth.security_policy import owner_mfa_required
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
        assert owner_mfa_required() is True

        SystemConfig.set(
            "REQUIRE_OWNER_MFA",
            False,
            value_type="bool",
            category="security",
            commit=True,
        )
        assert owner_mfa_required() is False


def test_owner_cannot_enable_global_mfa_until_every_active_owner_is_enrolled(
    app, admin_client, test_admin
):
    with app.app_context():
        SystemConfig.set(
            "REQUIRE_OWNER_MFA",
            False,
            value_type="bool",
            category="security",
            commit=True,
        )

    response = admin_client.post(
        "/owner/settings/owner-mfa",
        data={"require_owner_mfa": "on"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        assert SystemConfig.get("REQUIRE_OWNER_MFA", False) is False

        owner = db.session.get(type(test_admin), test_admin.id)
        assert owner is not None
        owner.mfa_enabled = True
        db.session.add(
            MFASecret(
                user_id=owner.id,
                mfa_type="totp",
                secret="JBSWY3DPEHPK3PXP",
                is_active=True,
            )
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


def test_owner_without_mfa_cannot_receive_authenticated_session_when_policy_is_on(
    app, client, test_admin
):
    with app.app_context():
        SystemConfig.set(
            "REQUIRE_OWNER_MFA",
            True,
            value_type="bool",
            category="security",
            commit=True,
        )
        owner = db.session.get(type(test_admin), test_admin.id)
        owner.mfa_enabled = False
        db.session.commit()

    response = client.post(
        "/login",
        data={"username": test_admin.username, "password": "TestPass123!"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert b"require an enrolled authenticator" in response.data
    with client.session_transaction() as session:
        assert "_user_id" not in session
