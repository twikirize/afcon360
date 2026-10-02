"""Admin driver-location page shows relative fix age (D3 follow-up).

Additive display-only proof: GET /transport/drivers/<id>/location renders
"· Xm ago" next to the Updated timestamp when a fix exists, and renders no
age text when there is no fix — so an online driver with a stale fix is
never mistaken for live. No freshness semantics (D5), heartbeat cadence
(D2), stale-UI logic (D6), or recovery behaviour (D7) is changed here.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db

pytestmark = pytest.mark.usefixtures("db_session")


def _seed_driver(app, *, age=None):
    from app.identity.models.user import User
    from app.transport.models import (
        ComplianceStatus,
        DriverProfile,
        VerificationTier,
    )

    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(
            public_id=str(uuid.uuid4()),
            username=f"la_{uid}",
            email=f"la_{uid}@test.example.com",
        )
        user.is_active = True
        user.is_verified = True
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()

        profile = DriverProfile(
            user_id=user.id,
            driver_code=f"LA-{uid[:6].upper()}",
            verification_tier=VerificationTier.PENDING,
            compliance_status=ComplianceStatus.APPROVED,
            is_active=True,
            is_online=True,
            is_available=True,
            max_passenger_capacity=4,
            vehicle_classes=["comfort"],
            service_types=["on_demand"],
        )
        if age is not None:
            profile.last_location = {
                "latitude": -1.2921,
                "longitude": 36.8219,
                "accuracy": 12.0,
            }
            profile.location_updated_at = datetime.now(timezone.utc) - age
        db.session.add(profile)
        db.session.commit()
        return profile.id, profile.driver_code


def test_location_page_shows_relative_age_for_stale_online_driver(
        app, admin_client):
    # Online + 10-minute-old fix: the exact D3 background scenario.
    driver_id, code = _seed_driver(app, age=timedelta(minutes=10))
    resp = admin_client.get(f"/transport/drivers/{driver_id}/location")
    assert resp.status_code == 200, resp.status_code
    body = resp.data.decode("utf-8")
    assert code in body
    assert "10m ago" in body


def test_location_page_shows_no_age_without_fix(app, admin_client):
    driver_id, code = _seed_driver(app, age=None)
    resp = admin_client.get(f"/transport/drivers/{driver_id}/location")
    assert resp.status_code == 200, resp.status_code
    body = resp.data.decode("utf-8")
    assert code in body
    assert "ago" not in body
