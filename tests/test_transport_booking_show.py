"""Transport booking-show 500 regression (GEO-18 audit finding).

`bookings/show.html` dereferences `booking.scheduled_pickup_time`,
which never existed as a column. The contract is now defined once in
`Booking.to_dict()` as the required `pickup_time` (ISO-8601, same as
every other serialized datetime), so the template's
`|datetimeformat|default('-')` chain degrades safely instead of
raising UndefinedError.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.transport.models import BookingStatus


def _seed_booking(app):
    from app.extensions import db
    from app.identity.models.user import User
    from app.transport.models import (Booking, ProviderType, ServiceType)
    with app.app_context():
        uid = uuid.uuid4().hex[:8]
        user = User(username=f"show_{uid}", email=f"show_{uid}@test.example.com",
                    is_active=True)
        user.set_password("TestPassword123!")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        now = datetime.now(timezone.utc)
        booking = Booking(
            booking_reference=f"SHOW-{uid[:6].upper()}",
            user_id=user_id, provider_type=ProviderType.INDIVIDUAL_DRIVER,
            service_type=ServiceType.ON_DEMAND,
            pickup_location={"latitude": 0.3150, "longitude": 32.5820},
            dropoff_location={"latitude": 0.3350, "longitude": 32.6000},
            pickup_time=now + timedelta(hours=1),
            passenger_count=1, base_price=Decimal("10.00"),
            subtotal=Decimal("10.00"), total_amount=Decimal("10.00"),
            final_price=Decimal("10.00"), status=BookingStatus.CONFIRMED)
        db.session.add(booking)
        db.session.commit()
        return booking.id, booking.booking_reference


def test_to_dict_defines_scheduled_pickup_time_alias(app):
    from app.extensions import db
    from app.transport.models import Booking

    booking_id, _ = _seed_booking(app)
    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        data = booking.to_dict()
    assert data["scheduled_pickup_time"] == booking.pickup_time.isoformat()
    # include/exclude contract honored
    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        assert "scheduled_pickup_time" in booking.to_dict(
            include=["id", "scheduled_pickup_time"])
        assert "scheduled_pickup_time" not in booking.to_dict(
            exclude=["scheduled_pickup_time"])


def test_booking_show_page_renders_200(app, admin_client):
    booking_id, ref = _seed_booking(app)
    resp = admin_client.get(f"/transport/bookings/{booking_id}")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert ref in html
    assert "UndefinedError" not in html
    assert "Traceback" not in html


def test_booking_api_detail_carries_alias(app, admin_client):
    from app.extensions import db
    from app.transport.models import Booking

    _, ref = _seed_booking(app)
    resp = admin_client.get(f"/api/transport/bookings/{ref}")
    assert resp.status_code == 200
    payload = resp.get_json()
    data = payload.get("data", payload)
    booking_data = data.get("booking", data)
    with app.app_context():
        booking = Booking.query.filter_by(booking_reference=ref).first()
        expected = booking.pickup_time.isoformat()
    assert booking_data.get("scheduled_pickup_time") == expected
