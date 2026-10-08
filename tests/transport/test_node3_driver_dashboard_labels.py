"""Node 3 (D1) — driver dashboard renders canonical rider labels.

Defect: every trip route on the driver dashboard rendered the literal
fallback 'Pickup' / 'Dropoff'.

Cause:
  * ModelSerializer serializes COLUMNS only, so the derived
    ``pickup_location_text`` / ``dropoff_location_text`` properties of
    Booking never reached the dashboard context.
  * ``pickup_address`` / ``dropoff_address`` are declared columns but
    have no writers, so that fallback branch was always empty too.
  * The template therefore always fell through to the literal.

Proof pinned here: a booking persisted with canonical snapshots carrying
rider labels renders those labels in the Active Trip focus card, the
Upcoming Assignments list and the All trips list — and no trip route
renders the literal fallback.
"""

import re
import uuid
from datetime import datetime, timedelta, timezone

PICKUP_LABEL = "Nakawa Riders Pickup Point"
DROPOFF_LABEL = "Entebbe Airside Gate"

_ROUTE_RE = re.compile(
    r'<div class="trip-route">\s*(.*?)\s*<i class="fa-solid fa-arrow-right"',
    re.S,
)


def _seed_driver(app):
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import (ComplianceStatus, DriverProfile,
                                      VerificationTier)
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"n3d1_{uid}", email=f"n3d1_{uid}@test.example.com",
                    is_active=True, is_verified=True, email_verified=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.flush()
        profile = DriverProfile(
            user_id=user.id, driver_code=f"N3D1-{uid[:6].upper()}",
            verification_tier=VerificationTier.PLATFORM_VERIFIED,
            compliance_status=ComplianceStatus.APPROVED,
            is_active=True, is_online=True, is_available=True,
            max_passenger_capacity=4, vehicle_classes=["comfort"])
        db.session.add(profile)
        db.session.commit()
        return user.id, profile.id, profile.driver_code


def _canonical(label, latitude, longitude):
    from app.transport.services.location_snapshot import (
        build_canonical_location_snapshot,
    )
    return build_canonical_location_snapshot(
        location_payload={
            "latitude": latitude,
            "longitude": longitude,
            "label": label,
        },
        source="map",
        resolution_method="map_pin",
    )


def _seed_booking(app, user_id, profile_id):
    from app.extensions import db
    from app.transport.models import (Booking, BookingStatus, Currency,
                                      PaymentStatus, ProviderType, ServiceType)
    with app.app_context():
        booking = Booking(
            user_id=user_id,
            provider_type=ProviderType.INDIVIDUAL_DRIVER,
            service_type=ServiceType.ON_DEMAND,
            pickup_location=_canonical(PICKUP_LABEL, 0.3136, 32.5811),
            dropoff_location=_canonical(DROPOFF_LABEL, 0.3476, 32.5825),
            pickup_time=datetime.now(timezone.utc) + timedelta(hours=3),
            passenger_count=2,
            base_price=50000,
            subtotal=50000,
            total_amount=50000,
            final_price=50000,
            currency=Currency.UGX,
            payment_status=PaymentStatus.PENDING,
            status=BookingStatus.ASSIGNED,
            booking_reference=f"TB{uuid.uuid4().hex[:10].upper()}",
            assigned_driver_id=profile_id,
        )
        db.session.add(booking)
        db.session.commit()
        return booking.booking_reference


def _login_and_enter_workspace(app, client, user_id, driver_code):
    from app.identity.models.user import User
    from app.extensions import db
    from tests.conftest import _login_client
    with app.app_context():
        _login_client(client, db.session.get(User, user_id))
    resp = client.post("/switch-context",
                       json={"type": "driver", "public_ref": driver_code,
                             "public_id": driver_code, "role": "driver"})
    assert resp.status_code == 200, resp.data.decode("utf-8")[:300]


def test_driver_trip_rows_expose_canonical_display_text(app):
    """get_driver_bookings (+ upcoming/recent) carry the derived text."""
    from app.transport.services.booking_service import BookingService
    user_id, profile_id, _code = _seed_driver(app)
    _seed_booking(app, user_id, profile_id)

    service = BookingService()
    for rows in (
        service.get_driver_bookings(user_id),
        service.get_driver_upcoming_bookings(user_id, limit=5),
        service.get_driver_recent_bookings(user_id, limit=5),
    ):
        assert rows, "expected the seeded booking in every driver listing"
        assert rows[0]["pickup_location_text"] == PICKUP_LABEL, rows[0]
        assert rows[0]["dropoff_location_text"] == DROPOFF_LABEL, rows[0]


def test_driver_dashboard_renders_rider_labels_not_literal_fallback(app,
                                                                    client):
    user_id, _profile_id, code = _seed_driver(app)
    _seed_booking(app, user_id, _profile_id)
    _login_and_enter_workspace(app, client, user_id, code)

    resp = client.get("/transport/driver-dashboard")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")

    # The canonical labels reach the page.
    assert PICKUP_LABEL in html, "pickup rider label not rendered"
    assert DROPOFF_LABEL in html, "dropoff rider label not rendered"

    # No trip route renders the literal fallback.
    routes = [m.strip() for m in _ROUTE_RE.findall(html)]
    assert routes, "expected at least one rendered trip route"
    literal = [r for r in routes if r in ("Pickup", "Dropoff")]
    assert not literal, f"literal fallback rendered: {literal}"
