"""Driver workspace deep-link entry and request-scoped context recovery.

An account without a saved workspace preference starts in Personal. A driver
can then open a bookmarked Driver Workspace URL after the server validates
the live profile, without persisting that request-local workspace into the
session. Operational go-live permissions remain independent.
"""

import uuid


def _seed_driver(app, tier="PLATFORM_VERIFIED"):
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import DriverProfile, VerificationTier
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"cx_{uid}", email=f"cx_{uid}@test.example.com",
                    is_active=True, is_verified=True, email_verified=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()
        profile = DriverProfile(
            user_id=user.id, driver_code=f"CX-{uid[:6].upper()}",
            verification_tier=getattr(VerificationTier, tier),
            compliance_status="approved",
            is_active=True, is_online=False, is_available=True,
            max_passenger_capacity=4, vehicle_classes=["comfort"])
        db.session.add(profile)
        db.session.commit()
        return user.username, profile.driver_code


def _login(client, username):
    return client.post("/login", data={"username": username,
                                       "password": "TestPassword123!"},
                       follow_redirects=False)


def test_verified_driver_login_keeps_personal_default_and_bookmark_opens_workspace(app, client):
    username, code = _seed_driver(app)
    resp = _login(client, username)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/user/dashboard")

    with client.session_transaction() as stored:
        assert stored.get("active_context_type") == "personal"
        assert stored.get("active_role") == "user"

    page = client.get("/transport/driver-dashboard")
    assert page.status_code == 200
    html = page.data.decode("utf-8")
    assert code in html
    assert "Traceback" not in html

    # Opening a bookmark resolves Driver only for this request; another tab
    # and the saved login default remain in Personal.
    with client.session_transaction() as stored:
        assert stored.get("active_context_type") == "personal"
        assert stored.get("active_role") == "user"


def test_pending_driver_keeps_personal_default_but_can_enter_workspace_without_go_live(app, client):
    username, _ = _seed_driver(app, tier="PENDING")
    resp = _login(client, username)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/user/dashboard")

    # Workspace access is participation, not operational approval. A pending
    # driver can complete setup but must not receive the online/go-live control.
    page = client.get("/transport/driver-dashboard")
    assert page.status_code == 200
    html = page.data.decode("utf-8")
    assert "Go-live checklist" in html or "Requirements" in html
    assert "data-online-toggle" not in html

    with client.session_transaction() as stored:
        assert stored.get("active_context_type") == "personal"
        assert stored.get("active_role") == "user"


def test_non_driver_cannot_enter_workspace(app, authenticated_client):
    resp = authenticated_client.get("/transport/driver-dashboard",
                                    follow_redirects=False)
    assert resp.status_code == 403


def test_anonymous_redirected_from_workspace(app, anonymous_client):
    resp = anonymous_client.get("/transport/driver-dashboard",
                                follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_invalid_context_switch_is_rejected_without_blocking_valid_driver_bookmark(app, client):
    from tests.conftest import _login_client
    from app.identity.models.user import User
    username, _ = _seed_driver(app)
    with app.app_context():
        from app.extensions import db
        user = db.session.query(User).filter_by(username=username).first()
        _login_client(client, user)

    with client.session_transaction() as stored:
        before = (
            stored.get("active_context_type"),
            stored.get("active_context_id"),
            stored.get("active_role"),
        )

    resp = client.post("/switch-context",
                       json={"type": "driver", "public_id": "NOPE-000",
                             "role": "driver"})
    assert resp.status_code in (400, 403, 404)
    assert resp.is_json
    assert resp.get_json()["success"] is False

    # The invalid public ID was not selected. The signed-in owner can still
    # open their own valid Driver bookmark through request-local resolution.
    with client.session_transaction() as stored:
        after_rejected_switch = (
            stored.get("active_context_type"),
            stored.get("active_context_id"),
            stored.get("active_role"),
        )
    assert after_rejected_switch == before

    page = client.get("/transport/driver-dashboard", follow_redirects=False)
    assert page.status_code == 200

    # The bookmarked route must not persist its request-local context either.
    with client.session_transaction() as stored:
        after_bookmark = (
            stored.get("active_context_type"),
            stored.get("active_context_id"),
            stored.get("active_role"),
        )
    assert after_bookmark == before
