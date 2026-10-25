"""Seed a probe user, verify E1-E10 behaviors, clean up."""

import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, ".")

from app import create_app
from app.extensions import db
from app.utils.exceptions import ValidationError

app = create_app()

with app.app_context():
    from app.identity.models.user import User
    from app.transport.models import Booking
    from app.transport.services.booking_service import get_booking_service

    TEST_EMAIL = "probe_do_not_commit@afcon360.local"

    # Clean any prior seed (defensive)
    prior = User.query.filter_by(email=TEST_EMAIL).first()
    if prior:
        Booking.query.filter_by(user_id=prior.id).delete()
        db.session.delete(prior)
        db.session.commit()

    # Seed via ORM — uses model defaults for required columns
    user = User(email=TEST_EMAIL, is_active=True, is_verified=True)
    import uuid
    if hasattr(User, 'public_id') and not getattr(user, 'public_id', None):
        user.public_id = uuid.uuid4()
    db.session.add(user)
    db.session.commit()
    user_id = user.id
    print(f"Seeded probe user id={user_id}, email={TEST_EMAIL}")

    TEST_REFERENCES = []
    results = []

    def try_booking(label, payload):
        try:
            r = get_booking_service().create_booking(user_id, payload)
            ref = r["data"]["booking_reference"]
            TEST_REFERENCES.append(ref)
            results.append((label, "SUCCESS", ref))
        except ValidationError as e:
            results.append((label, "ValidationError", str(e.message)[:80]))
        except Exception as e:
            results.append((label, type(e).__name__, str(e)[:80]))

    def base_payload(mode, pickup_time):
        return {
            "service_type": "on_demand",
            "provider_type": "individual_driver",
            "pickup_latitude": 0.3136,
            "pickup_longitude": 32.5811,
            "dropoff_latitude": 0.3476,
            "dropoff_longitude": 32.5825,
            "pickup_location": "Kampala",
            "dropoff_location": "Entebbe",
            "pickup_time": pickup_time.isoformat(),
            "passenger_count": 1,
            "currency": "USD",
            "payment_method": "cash",
            "vehicle_class": "comfort",
            "booking_mode": mode,
        }

    now = datetime.now(timezone.utc)
    nairobi = ZoneInfo("Africa/Nairobi")

    try_booking("instant + now", base_payload("instant", now))
    try_booking("scheduled + 30min", base_payload("scheduled", now + timedelta(minutes=30)))
    try_booking("scheduled + 3min (should fail)", base_payload("scheduled", now + timedelta(minutes=3)))
    # CORRECTED naive: 20min in future expressed as Nairobi wall time
    naive_future = (now + timedelta(minutes=20)).astimezone(nairobi).replace(tzinfo=None)
    try_booking("scheduled + 20min naive (Nairobi)", base_payload("scheduled", naive_future))

    print()
    print(f"{'CASE':<42} {'RESULT':<18} {'DETAIL'}")
    print("-" * 92)
    for label, result, detail in results:
        print(f"{label:<42} {result:<18} {detail}")

    # Cleanup: bookings first, then user (FK order)
    print()
    print(f"Cleaning up {len(TEST_REFERENCES)} bookings + user {user_id}...")
    Booking.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    print("Done. DB restored to empty.")
