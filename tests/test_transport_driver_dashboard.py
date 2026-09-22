"""Transport P0 driver-dashboard 500 regression.

Route `transport.driver_dashboard` rendered the deleted
`transport/driver_dashboard.html` (concurrent move to
`transport/driver/driver_dashboard.html`), and the moved template
referenced the never-existing `transport.vehicle_marketplace`
endpoint. Both are pinned here: ownership chain (route -> view ->
template) renders HTTP 200 with the workspace sections for a real
driver-context session established through the real switch route.
"""

import uuid

import pytest


def _seed_driver(app):
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import (ComplianceStatus, DriverProfile,
                                      VerificationTier)
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"dd_{uid}", email=f"dd_{uid}@test.example.com",
                    is_active=True, is_verified=True, email_verified=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()
        profile = DriverProfile(
            user_id=user.id, driver_code=f"DD-{uid[:6].upper()}",
            verification_tier=VerificationTier.PLATFORM_VERIFIED,
            compliance_status=ComplianceStatus.APPROVED,
            is_active=True, is_online=True, is_available=True,
            max_passenger_capacity=4, vehicle_classes=["comfort"])
        db.session.add(profile)
        db.session.commit()
        return user.id, profile.driver_code


def _login_as(app, client, user_id):
    from tests.conftest import _login_client
    from app.identity.models.user import User
    with app.app_context():
        from app.extensions import db
        _login_client(client, db.session.get(User, user_id))


def test_driver_dashboard_renders_200_for_driver_context(app, client):
    user_id, code = _seed_driver(app)
    _login_as(app, client, user_id)
    resp = client.post("/switch-context",
                       json={"type": "driver", "public_ref": code,
                             "public_id": code, "role": "driver"})
    assert resp.status_code == 200, resp.data.decode("utf-8")[:300]
    resp = client.get("/transport/driver-dashboard")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert code in html
    assert "UndefinedError" not in html
    assert "Traceback" not in html


def test_driver_dashboard_preserves_workspace_sections(app, client):
    user_id, code = _seed_driver(app)
    _login_as(app, client, user_id)
    resp = client.post("/switch-context",
                       json={"type": "driver", "public_id": code,
                             "role": "driver"})
    assert resp.status_code == 200, resp.data.decode("utf-8")[:300]
    resp = client.get("/transport/driver-dashboard")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # Workspace functions intact: status/offers/trips/earnings/readiness.
    for marker in ("Ride Offers", "Active Trip", "Earnings",
                   "Go-live readiness", "Availability", "Online"):
        assert marker.lower() in html.lower(), marker


def test_driver_dashboard_denied_without_driver_context(app,
                                                        authenticated_client):
    resp = authenticated_client.get("/transport/driver-dashboard",
                                    follow_redirects=False)
    assert resp.status_code == 403
