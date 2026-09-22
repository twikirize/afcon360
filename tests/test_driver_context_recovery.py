"""Transport P1 driver 403 / context-switch recovery.

Proves the login recovery journey: a verified driver with exactly one
eligible Driver context lands on a working Driver Workspace (context
auto-established through the same switch service as the UI path),
while guards stay intact for everyone else. No authorization is
weakened: the switch service enforces eligibility; the dashboard
decorator still denies missing/wrong contexts.
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


def test_verified_driver_login_lands_on_working_dashboard(app, client):
    username, code = _seed_driver(app)
    resp = _login(client, username)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/transport/driver-dashboard")
    page = client.get("/transport/driver-dashboard")
    assert page.status_code == 200
    html = page.data.decode("utf-8")
    assert code in html
    assert "Traceback" not in html


def test_unverified_driver_not_routed_to_workspace(app, client):
    username, _ = _seed_driver(app, tier="PENDING")
    resp = _login(client, username)
    assert resp.status_code == 302
    assert not resp.headers["Location"].endswith("/transport/driver-dashboard")


def test_non_driver_cannot_enter_workspace(app, authenticated_client):
    resp = authenticated_client.get("/transport/driver-dashboard",
                                    follow_redirects=False)
    assert resp.status_code == 403


def test_anonymous_redirected_from_workspace(app, anonymous_client):
    resp = anonymous_client.get("/transport/driver-dashboard",
                                follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_invalid_context_switch_denied(app, client):
    from tests.conftest import _login_client
    from app.identity.models.user import User
    username, _ = _seed_driver(app)
    with app.app_context():
        from app.extensions import db
        user = db.session.query(User).filter_by(username=username).first()
        _login_client(client, user)
    resp = client.post("/switch-context",
                       json={"type": "driver", "public_id": "NOPE-000",
                             "role": "driver"})
    assert resp.status_code in (400, 403, 404)
    denied = client.get("/transport/driver-dashboard",
                        follow_redirects=False)
    assert denied.status_code == 403
