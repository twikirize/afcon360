"""Transport P0 driver-dashboard 500 regression.

Route `transport.driver_dashboard` rendered the deleted
`transport/driver_dashboard.html` (concurrent move to
`transport/driver/driver_dashboard.html`), and the moved template
referenced the never-existing `transport.vehicle_marketplace`
endpoint. Both are pinned here: ownership chain (route -> view ->
template) renders HTTP 200 with the workspace sections for a real
driver-context session established through the real switch route.
"""

import re
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
    assert 'id="driverMap"' in html
    assert 'data-geo-map-status="pending"' in html
    assert "tile.openstreetmap.org" in html
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


def test_driver_dashboard_offer_sound_picker(app, client):
    """Account panel offers a device-local alert-sound choice with preview."""
    user_id, code = _seed_driver(app)
    _login_as(app, client, user_id)
    resp = client.post("/switch-context",
                       json={"type": "driver", "public_id": code,
                             "role": "driver"})
    assert resp.status_code == 200, resp.data.decode("utf-8")[:300]
    resp = client.get("/transport/driver-dashboard")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Offer alert sound" in html
    for value in ("value=\"chime\"", "value=\"urgent\"",
                  "value=\"bell\"", "value=\"horn\"",
                  "value=\"custom\""):
        assert value in html
    assert "alertSoundPreview" in html
    assert "driver_alerts.js" in html
    from pathlib import Path
    alerts_script = (
        Path(__file__).resolve().parents[1]
        / "static" / "js" / "modules" / "transport" / "driver_alerts.js"
    ).read_text(encoding="utf-8")
    assert "window.AFCONDriverSound" in alerts_script
    assert "customSoundFile" in html
    assert "customSoundRemove" in html

def test_csrf_refresh_keeps_existing_dashboard_token_valid(app, client):
    """A refresh must not invalidate a token already held by another tab."""
    user_id, code = _seed_driver(app)
    _login_as(app, client, user_id)
    switched = client.post(
        "/switch-context",
        json={"type": "driver", "public_ref": code,
              "public_id": code, "role": "driver"},
    )
    assert switched.status_code == 200

    dashboard = client.get("/transport/driver-dashboard")
    assert dashboard.status_code == 200
    match = re.search(
        r'<meta name="csrf-token" content="([^"]+)"',
        dashboard.get_data(as_text=True),
    )
    assert match, "driver shell did not render its session-bound CSRF token"
    page_token = match.group(1)

    previous_setting = app.config.get("WTF_CSRF_ENABLED", False)
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        refreshed = client.get("/api/csrf-token")
        assert refreshed.status_code == 200
        assert refreshed.headers.get("Cache-Control", "").startswith("private, no-store")
        assert refreshed.headers.get("Vary") == "Cookie"
        assert refreshed.get_json()["csrf_token"]

        from app.transport.models import DriverProfile
        with app.app_context():
            driver_id = DriverProfile.query.filter_by(
                driver_code=code, is_deleted=False
            ).one().id

        response = client.post(
            f"/api/transport/drivers/{driver_id}/status",
            json={"is_online": False},
            headers={"X-CSRFToken": page_token},
        )
        assert response.status_code == 200, response.get_data(as_text=True)
    finally:
        app.config["WTF_CSRF_ENABLED"] = previous_setting
